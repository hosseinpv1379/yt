"""Generate timed ASS captions with per-word highlighting."""
from pathlib import Path
from .transcribe import Word

COLORS = {"yellow": "00FFFF", "green": "00FF80", "blue": "FFAA00", "white": "FFFFFF"}


def _time(seconds: float) -> str:
    ticks = max(0, round(seconds * 100))
    hours, ticks = divmod(ticks, 360000)
    minutes, ticks = divmod(ticks, 6000)
    seconds, centis = divmod(ticks, 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centis:02d}"


def _escape(text: str) -> str:
    return text.replace("\\", "＼").replace("{", "｛").replace("}", "｝").replace("\n", " ")


def _groups(words: list[Word]):
    group: list[Word] = []
    length = 0
    for word in words:
        count = len(word.text) + (1 if group else 0)
        if group and (len(group) >= 4 or length + count > 20 or word.start - group[-1].end > 0.8):
            yield group
            group, length = [], 0
        group.append(word)
        length += len(word.text) + (1 if len(group) > 1 else 0)
    if group:
        yield group


def write_ass(words: list[Word], path: Path, width: int, height: int, language: str, color: str) -> None:
    if color not in COLORS or width <= 0 or height <= 0:
        raise ValueError("Invalid caption style or video size")
    font = "Vazirmatn" if language in {"fa", "ar", "ur"} else "Montserrat"
    size = max(24, round(min(width, height) * 0.065))
    margin = round(height * 0.22)
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}",
        "WrapStyle: 2", "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,40,40,{margin},1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for group in _groups(words):
        for index, word in enumerate(group):
            end = group[index + 1].start if index + 1 < len(group) else word.end
            if end <= word.start:
                continue
            rendered = []
            for position, part in enumerate(group):
                text = _escape(part.text)
                if position == index:
                    text = r"{\1c&H" + COLORS[color] + r"&\fscx100\fscy100\t(0,100,\fscx115\fscy115)\t(100,200,\fscx100\fscy100)}" + text + r"{\r}"
                rendered.append(text)
            lines.append(f"Dialogue: 0,{_time(word.start)},{_time(end)},Default,,0,0,0,," + " ".join(rendered))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
