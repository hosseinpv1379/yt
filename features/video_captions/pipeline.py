"""Offline captions and one-pass video rendering for uploaded videos."""
import json
import logging
import math
import statistics
import subprocess
import threading
from fractions import Fraction
from pathlib import Path

from .ass_builder import write_ass
from .grading import Grader, GradeSettings
from .transcribe import transcribe

logger = logging.getLogger(__name__)


def _variable_frame_timing(path: Path, time_base: str | None = None) -> bool | None:
    """Return True for VFR, False for CFR, or None when timestamps are unknown."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_frames",
             "-show_entries", "frame=best_effort_timestamp_time", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=30, check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        logger.warning("Could not inspect frame timestamps for %s; using source-PTS render fallback", path.name)
        return None

    timestamps = []
    for row in result.stdout.splitlines():
        value = row.split(",", 1)[0].strip()
        if not value or value == "N/A":
            return None
        try:
            timestamp = float(value)
        except ValueError:
            return None
        if not math.isfinite(timestamp):
            return None
        timestamps.append(timestamp)

    if len(timestamps) < 3:
        return False
    intervals = [later - earlier for earlier, later in zip(timestamps, timestamps[1:])]
    if any(interval <= 0 for interval in intervals):
        return True
    median_interval = statistics.median(intervals)
    try:
        timestamp_tick = float(Fraction(time_base)) if time_base else 0.0005
    except (ValueError, ZeroDivisionError):
        timestamp_tick = 0.0005
    # CFR timestamps can alternate by one container time-base tick due to
    # rounding (for example 29.97 fps in a 1/600 time base).
    tolerance = max(0.0005, timestamp_tick * 1.1, median_interval * 0.02)
    return max(intervals) - min(intervals) > tolerance


def probe(path: Path, inspect_frame_timing: bool = False) -> dict:
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
    audio_streams = [stream for stream in data["streams"] if stream.get("codec_type") == "audio"]
    pts_alignment_mismatch = False
    try:
        video_start_value = video.get("start_time")
        if video_start_value in (None, "N/A"):
            raise ValueError("video start timestamp is unavailable")
        video_start = float(video_start_value)
        # OpenCV's rawvideo pipe starts at zero, so a non-zero source offset
        # would be lost even when the audio track shares that same offset.
        pts_alignment_mismatch = abs(video_start) > 0.001
        if audio_streams:
            audio_start_value = audio_streams[0].get("start_time")
            if audio_start_value in (None, "N/A"):
                raise ValueError("audio start timestamp is unavailable")
            audio_start = float(audio_start_value)
            pts_alignment_mismatch = (
                pts_alignment_mismatch or abs(audio_start) > 0.001 or
                abs(video_start - audio_start) > 0.001
            )
    except (TypeError, ValueError):
        pts_alignment_mismatch = True
    rotation = next((item.get("rotation") for item in video.get("side_data_list", []) if item.get("rotation") is not None),
                    video.get("tags", {}).get("rotate", 0))
    try:
        if abs(round(float(rotation))) % 180 == 90:
            width, height = height, width
    except (TypeError, ValueError):
        pass
    metadata = {"duration": duration, "width": width, "height": height,
                "audio": bool(audio_streams), "source_pts_alignment_mismatch": pts_alignment_mismatch,
                "video_time_base": video.get("time_base")}
    if inspect_frame_timing:
        # Uploaded clips are capped at 90 seconds and 20 MB. Scan every video
        # frame within a fixed timeout so a VFR section near the end is caught.
        metadata["variable_frame_rate"] = _variable_frame_timing(path, video.get("time_base"))
    return metadata


def render(source: Path, output: Path, mode: str, color: str, model_path: str,
           fonts_dir: Path, cancelled, progress, grade_settings: GradeSettings | None = None,
           timeout: int = 1800, language: str | None = None, font: str | None = None,
           font_size: str = "medium") -> tuple[dict, str | None, bool]:
    color_requested = mode in {"color", "both"}
    if color_requested:
        progress("در حال بررسی زمان‌بندی فریم‌ها…")
    meta = probe(source, inspect_frame_timing=color_requested)
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
        write_ass(words, ass_path, meta["width"], meta["height"], language or "en", color, font, font_size)
    elif mode in {"caption", "both"}:
        progress("گفتاری پیدا نشد؛ فقط اصلاح رنگ انجام می‌شود.")
        mode = "color"
        if not color_requested:
            progress("در حال بررسی زمان‌بندی فریم‌ها…")
            meta["variable_frame_rate"] = _variable_frame_timing(source, meta.get("video_time_base"))
            color_requested = True
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
        cmd += ["-fps_mode", "passthrough"]
        subprocess.run(cmd + output_args, cwd=output.parent, timeout=timeout, check=True, capture_output=True)
        meta["width"] += meta["width"] % 2
        meta["height"] += meta["height"] % 2
        return meta, language, bool(words)

    timing_uncertain = (
        meta.get("variable_frame_rate", False) is not False or
        meta.get("source_pts_alignment_mismatch", False)
    )
    if color_requested and timing_uncertain:
        # The OpenCV pipe below assigns a single FPS to every frame. Avoid that
        # for VFR (or unknown) timestamps; source decoding keeps frame PTS,
        # subtitle times, and original audio on the same timeline.
        progress("زمان‌بندی فریم‌ها یا آغاز صدا و تصویر متغیر یا نامشخص است؛ برای حفظ هم‌زمانی، اصلاح رنگ کنار گذاشته می‌شود.")
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source)]
        if filters:
            cmd += ["-vf", ",".join(filters)]
        cmd += ["-fps_mode", "passthrough"]
        subprocess.run(cmd + output_args, cwd=output.parent, timeout=timeout, check=True, capture_output=True)
        meta["width"] += meta["width"] % 2
        meta["height"] += meta["height"] % 2
        meta["color_correction_skipped_timing"] = True
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
            write_ass(words, ass_path, width, height, language or "en", color, font, font_size)
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
           "-s", f"{width}x{height}", "-r", str(fps), "-i", "pipe:0", "-i", str(source),
           "-map", "0:v:0", "-map", "1:a:0?", "-fps_mode", "passthrough"]
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
