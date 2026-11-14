"""Offline captions and one-pass video rendering for uploaded videos."""
import json
import subprocess
import threading
from pathlib import Path

from .ass_builder import write_ass
from .grading import Grader, GradeSettings
from .transcribe import transcribe


def probe(path: Path) -> dict:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=30, check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError("فرمت ویدیو قابل خواندن نیست یا بررسی آن بیش از حد طول کشید.") from exc
    data = json.loads(result.stdout)
    video = next((s for s in data["streams"] if s.get("codec_type") == "video"), None)
    if not video:
        raise ValueError("فرمت ویدیو قابل تشخیص نیست.")
    duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0)
    if duration <= 0 or duration > 90:
        raise ValueError("مدت ویدیو باید حداکثر ۹۰ ثانیه باشد.")
    width, height = int(video["width"]), int(video["height"])
    rotation = next((item.get("rotation") for item in video.get("side_data_list", []) if item.get("rotation") is not None),
                    video.get("tags", {}).get("rotate", 0))
    try:
        if abs(round(float(rotation))) % 180 == 90:
            width, height = height, width
    except (TypeError, ValueError):
        pass
    return {"duration": duration, "width": width, "height": height,
            "audio": any(s.get("codec_type") == "audio" for s in data["streams"])}


def render(source: Path, output: Path, mode: str, color: str, model_path: str,
           fonts_dir: Path, cancelled, progress, grade_settings: GradeSettings | None = None,
           timeout: int = 1800, language: str | None = None) -> tuple[dict, str | None, bool]:
    meta = probe(source)
    words = []
    if mode in {"caption", "both"} and meta["audio"]:
        progress("در حال تشخیص گفتار…")
        selected_language = language
        words, language = transcribe(source, model_path, selected_language)
        language_name = {"fa": "فارسی", "en": "انگلیسی"}.get(language, language)
        progress(f"زبان {'انتخاب‌شده' if selected_language else 'تشخیص‌داده‌شده'}: {language_name}")
    if cancelled.is_set():
        raise InterruptedError("لغو شد")
    ass_path = output.parent / "captions.ass"
    if words:
        progress("در حال ساخت زیرنویس…")
        write_ass(words, ass_path, meta["width"], meta["height"], language or "en", color)
    elif mode in {"caption", "both"}:
        progress("گفتاری پیدا نشد؛ فقط اصلاح رنگ انجام می‌شود.")
        mode = "color"
    filters = ["pad=ceil(iw/2)*2:ceil(ih/2)*2"]
    if words:
        escaped_fonts = str(fonts_dir.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        filters.append(f"ass=captions.ass:fontsdir='{escaped_fonts}'")
    output_args = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                   "-c:a", "aac", "-movflags", "+faststart", str(output)]
    progress("در حال اصلاح رنگ و رندر…" if mode in {"color", "both"} else "در حال رندر…")
    if mode == "caption":
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source)]
        if filters:
            cmd += ["-vf", ",".join(filters)]
        subprocess.run(cmd + output_args, cwd=output.parent, timeout=timeout, check=True, capture_output=True)
        meta["width"] += meta["width"] % 2
        meta["height"] += meta["height"] % 2
        return meta, language, bool(words)

    import cv2
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise ValueError("ویدیو برای اصلاح رنگ قابل خواندن نیست.")
    ok, frame = capture.read()
    fps = capture.get(cv2.CAP_PROP_FPS)
    if not ok or not fps or fps <= 0:
        capture.release()
        raise ValueError("فریم یا نرخ ویدیو در دسترس نیست.")
    height, width = frame.shape[:2]
    if (width, height) != (meta["width"], meta["height"]):
        meta["width"], meta["height"] = width, height
        if words:
            write_ass(words, ass_path, width, height, language or "en", color)
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
           "-s", f"{width}x{height}", "-r", str(fps), "-i", "pipe:0", "-i", str(source),
           "-map", "0:v:0", "-map", "1:a:0?"]
    if filters:
        cmd += ["-vf", ",".join(filters)]
    try:
        grader = Grader(grade_settings or GradeSettings())
    except Exception:
        capture.release()
        raise
    log_path = output.parent / "ffmpeg.log"
    try:
        with log_path.open("wb") as log:
            process = subprocess.Popen(cmd + output_args, cwd=output.parent, stdin=subprocess.PIPE, stderr=log)
            timer = threading.Timer(timeout, process.kill)
            timer.start()
            try:
                while ok:
                    if cancelled.is_set():
                        raise InterruptedError("لغو شد")
                    process.stdin.write(grader.frame(frame).tobytes())
                    ok, frame = capture.read()
                process.stdin.close()
                if process.wait() != 0:
                    raise RuntimeError("خطا در رندر ffmpeg؛ جزئیات در لاگ ثبت شد.")
            finally:
                timer.cancel()
                if process.poll() is None:
                    process.kill()
                    process.wait()
    finally:
        grader.close()
        capture.release()
    meta["width"] += meta["width"] % 2
    meta["height"] += meta["height"] % 2
    return meta, language, bool(words)
