"""Private, single-job CPU audio separator for the bot's shared volume."""
import json
import logging
import os
import re
import shutil
import subprocess
import threading
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(os.environ.get("WORK_DIR", "/data")).resolve()
LOCK = threading.Lock()
SAMPLE_RATE = 44_100
WINDOW_FRAMES = 3 * SAMPLE_RATE
HOP_FRAMES = 2 * SAMPLE_RATE
OVERLAP_FRAMES = WINDOW_FRAMES - HOP_FRAMES


def run(args):
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, timeout=10800)


@lru_cache(maxsize=1)
def dialogue_model():
    import torch
    from dbs.models import DBSBSRNN

    torch.set_num_threads(2)
    return DBSBSRNN.from_pretrained(
        "JusperLee/DBS-BSRNN-DnR", revision="5af343f57f106fbb95efe8a60f1a3999eeb0aef8",
    ).eval()


def write_background(source, output):
    import numpy as np
    import soundfile as sf
    import torch
    from dbs.engine import separate as infer

    model = dialogue_model()
    fade = np.linspace(0, 1, OVERLAP_FRAMES, dtype=np.float32)[:, None]
    with sf.SoundFile(source) as audio, sf.SoundFile(
        output, mode="w", samplerate=SAMPLE_RATE, channels=audio.channels,
        format="RF64", subtype="FLOAT",
    ) as bed, torch.inference_mode():
        if audio.frames == 0 or audio.samplerate != SAMPLE_RATE:
            raise ValueError("invalid separator audio")
        previous_tail = None
        for start in range(0, audio.frames, HOP_FRAMES):
            audio.seek(start)
            samples = audio.read(WINDOW_FRAMES, dtype="float32", always_2d=True)
            frames = len(samples)
            if samples.any():
                # Process one mono channel at a time to keep memory bounded on
                # CPU servers. Keep both channels and discard the speech stem.
                identical = audio.channels == 2 and np.array_equal(samples[:, 0], samples[:, 1])
                background = np.empty_like(samples)
                for channel in range(1 if identical else audio.channels):
                    # A short final chunk only needs enough samples for the model's STFT.
                    padded = np.pad(samples[:, channel], (0, max(0, OVERLAP_FRAMES - frames)))
                    mixture = torch.from_numpy(padded).view(1, 1, -1)
                    music, effects, _ = infer(model, mixture)[0]
                    background[:, channel] = (music[:frames] + effects[:frames]).numpy()
                if identical:
                    background[:, 1] = background[:, 0]
                if not np.isfinite(background).all():
                    raise ValueError("invalid separation result")
            else:
                background = samples
            if previous_tail is not None:
                background[:OVERLAP_FRAMES] = (
                    previous_tail * (1 - fade) + background[:OVERLAP_FRAMES] * fade
                )
            if start + frames >= audio.frames:
                bed.write(background)
                break
            bed.write(background[:HOP_FRAMES])
            previous_tail = background[HOP_FRAMES:]


def separate(job_id, source, root=None):
    root = (root or ROOT).resolve()
    if not re.fullmatch(r"[0-9a-f]{32}", job_id) or Path(source).name != source:
        raise ValueError("invalid job or source")
    job = (root / job_id).resolve()
    video = (job / source).resolve()
    if job.parent != root or video.parent != job or not video.is_file():
        raise ValueError("invalid source")
    temp = job / "separator-work"
    shutil.rmtree(temp, ignore_errors=True)
    temp.mkdir()
    try:
        output = job / "dub-background.partial.wav"
        decoded = temp / "source.wav"
        run(["ffmpeg", "-v", "error", "-y", "-threads", "2", "-i", str(video),
             "-map", "0:a:0", "-ac", "2", "-ar", str(SAMPLE_RATE),
             "-c:a", "pcm_f32le", "-rf64", "auto", str(decoded)])
        write_background(decoded, output)
        output.replace(job / "dub-background.wav")
    finally:
        shutil.rmtree(temp, ignore_errors=True)
        (job / "dub-background.partial.wav").unlink(missing_ok=True)


class Handler(BaseHTTPRequestHandler):
    def respond(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.respond(200 if self.path == "/health" else 404, {"ok": self.path == "/health"})

    def do_POST(self):
        if self.path != "/separate":
            self.respond(404, {"ok": False})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 2048:
                raise ValueError("invalid request")
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict) or not isinstance(data.get("job_id"), str) or not isinstance(data.get("source"), str):
                raise ValueError("invalid request")
        except (ValueError, TypeError):
            self.respond(400, {"ok": False})
            return
        if not LOCK.acquire(blocking=False):
            self.respond(503, {"ok": False})
            return
        try:
            separate(data["job_id"], data["source"])
            self.respond(200, {"ok": True})
        except Exception:
            logging.exception("Audio separation failed")
            self.respond(500, {"ok": False})
        finally:
            LOCK.release()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ThreadingHTTPServer(("0.0.0.0", 8090), Handler).serve_forever()
