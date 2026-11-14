"""Generate timed ASS captions with per-word highlighting."""
import math
from pathlib import Path
from .transcribe import Word

COLORS = {"yellow": "00FFFF", "green": "00FF80", "blue": "FFAA00", "white": "FFFFFF"}
FONT_FAMILIES = {
    "vazirmatn": "Vazirmatn",
    "noto_sans_arabic": "Noto Sans Arabic",
    "noto_naskh_arabic": "Noto Naskh Arabic",
    "noto_sans": "Noto Sans",
    "noto_serif": "Noto Serif",
    "montserrat": "Montserrat",
}
FONT_FILES = {
    "vazirmatn": "Vazirmatn-Bold.ttf",
    "noto_sans_arabic": "NotoSansArabic-Bold.ttf",
    "noto_naskh_arabic": "NotoNaskhArabic-Bold.ttf",
    "noto_sans": "NotoSans-Bold.ttf",
    "noto_serif": "NotoSerif-Bold.ttf",
    "montserrat": "Montserrat-ExtraBold.ttf",
}
FONT_LABELS = {
    "vazirmatn": "Vazirmatn · فارسی",
    "noto_sans_arabic": "Noto Sans Arabic · ساده",
    "noto_naskh_arabic": "Noto Naskh Arabic · سنتی",
    "noto_sans": "Noto Sans · لاتین",
    "noto_serif": "Noto Serif · لاتین",
    "montserrat": "Montserrat · لاتین",
}
FONT_SIZES = {"small": 0.055, "medium": 0.065, "large": 0.078}
FONT_SIZE_LABELS = {"small": "کوچک", "medium": "متوسط", "large": "بزرگ"}


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
    ordered = sorted(
        (word for word in words if word.text.strip() and math.isfinite(word.start) and
         math.isfinite(word.end) and word.start >= 0 and word.end > word.start),
        key=lambda word: (word.start, word.end),
    )
    for word in ordered:
        count = len(word.text) + (1 if group else 0)
        if group and (len(group) >= 4 or length + count > 20 or word.start - group[-1].end > 0.8):
            yield group
            group, length = [], 0
        group.append(word)
        length += len(word.text) + (1 if len(group) > 1 else 0)
    if group:
        yield group


def write_ass(words: list[Word], path: Path, width: int, height: int, language: str, color: str,
              font: str | None = None, font_size: str = "medium") -> None:
    if color not in COLORS or width <= 0 or height <= 0 or font_size not in FONT_SIZES:
        raise ValueError("Invalid caption style or video size")
    if font is None:
        font = "vazirmatn" if language in {"fa", "ar", "ur"} else "montserrat"
    if font not in FONT_FAMILIES:
        raise ValueError("Invalid caption font")
    family = FONT_FAMILIES[font]
    size = max(24, round(min(width, height) * FONT_SIZES[font_size]))
    margin = round(height * 0.22)
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}",
        "WrapStyle: 2", "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        # Encoding -1 is a libass extension that lays out an event as a whole.
        # That keeps Unicode bidi ordering and Arabic/Persian shaping intact
        # across the override tags used to highlight each active word.
        f"Style: Default,{family},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,40,40,{margin},-1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    groups = list(_groups(words))
    for group_index, group in enumerate(groups):
        for index, word in enumerate(group):
            if index + 1 < len(group):
                end = group[index + 1].start
            elif group_index + 1 < len(groups) and groups[group_index + 1][0].start - word.end <= 0.8:
                # A group may end because it reached the line or word limit.
                # Stop it when the next group begins so the two captions never overlap.
                end = groups[group_index + 1][0].start
            else:
                end = word.end
            if end <= word.start or round(end * 100) <= round(word.start * 100):
                continue
            rendered = []
            for position, part in enumerate(group):
                text = _escape(part.text)
                if position == index:
                    text = r"{\1c&H" + COLORS[color] + r"&\fscx100\fscy100\t(0,100,\fscx115\fscy115)\t(100,200,\fscx100\fscy100)}" + text + r"{\r}"
                rendered.append(text)
            lines.append(f"Dialogue: 0,{_time(word.start)},{_time(end)},Default,,0,0,0,," + " ".join(rendered))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
