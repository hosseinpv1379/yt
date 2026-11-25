"""Private, single-job CPU audio separator for the bot's shared volume."""
import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import shutil
import subprocess
import threading

ROOT = Path(os.environ.get("WORK_DIR", "/data")).resolve()
LOCK = threading.Lock()


def run(args):
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, timeout=10800)


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
        run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vn", "-ac", "2", "-ar", "44100", "-f", "segment", "-segment_time", "60", "-reset_timestamps", "1", str(temp / "part_%05d.wav")])
        chunks = sorted(temp.glob("part_*.wav"))
        if not chunks:
            raise ValueError("empty audio")
        stems = []
        for chunk in chunks:
            run(["spleeter", "separate", "-p", "spleeter:2stems", "-o", str(temp / "stems"), str(chunk)])
            stem = temp / "stems" / chunk.stem / "accompaniment.wav"
            if not stem.is_file():
                raise ValueError("missing separated audio")
            stems.append(stem)
            chunk.unlink()
        # Names are generated internally; use relative paths for concat safety.
        listing = temp / "list.txt"
        listing.write_text("".join(f"file 'stems/{stem.parent.name}/accompaniment.wav'\n" for stem in stems))
        output = job / "dub-background.partial.wav"
        run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "1", "-i", str(listing), "-c", "copy", str(output)])
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
