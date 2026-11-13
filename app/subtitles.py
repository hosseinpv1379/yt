"""Readable Persian subtitle cues built from timed source speech."""
import math
import re

MAX_SOURCE_SECONDS = 4.0
MAX_SOURCE_WORDS = 9
MAX_SOURCE_CHARS = 60
MAX_LINE_CHARS = 42
MAX_CUE_CHARS = MAX_LINE_CHARS * 2
PAUSE_SECONDS = 0.65
MIN_CUE_SECONDS = 0.20


def _field(item, key, default=None):
    return item.get(key, default) if isinstance(item, dict) else getattr(item, key, default)


def _valid_times(item):
    try:
        start, end = float(_field(item, 'start')), float(_field(item, 'end'))
        return (start, end) if math.isfinite(start) and math.isfinite(end) and 0 <= start < end else None
    except (TypeError, ValueError):
        return None


def _coverage(reference: str, words: list[dict]) -> bool:
    # Some providers return only a subset of word timings; never discard missing speech.
    normalize = lambda text: ''.join(re.findall(r'\w+', text.casefold(), flags=re.UNICODE))
    expected = normalize(reference)
    actual = normalize(' '.join(word['text'] for word in words))
    return bool(expected) and expected == actual


def _parts(text: str, max_chars: int, max_words: int) -> list[str]:
    words = re.findall(r'\S+', text)
    groups, current = [], []
    for word in words:
        candidate = ' '.join(current + [word])
        if current and (len(candidate) > max_chars or len(current) >= max_words):
            groups.append(' '.join(current)); current = []
        current.append(word)
        if re.search(r'[.!?؟؛。！？][”’"\']?$', word) and len(current) >= 3:
            groups.append(' '.join(current)); current = []
    if current:
        groups.append(' '.join(current))
    return groups


def _spread_text(text: str, start: float, end: float, *, max_chars: int, max_words: int, max_seconds: float) -> list[dict]:
    """Interpolate only when a provider has no usable word timestamps."""
    duration = end - start
    if duration <= 0:
        return []
    words = re.findall(r'\S+', text)
    # Bound subtitle duration even for compact, long source utterances.
    desired = max(1, math.ceil(duration / max_seconds))
    per_group = max(1, min(max_words, math.ceil(len(words) / desired)))
    parts = _parts(text, max_chars, per_group)
    if not parts:
        return []
    weights = [max(1, len(part.replace(' ', ''))) for part in parts]
    total = sum(weights)
    elapsed = 0
    cues = []
    for part, weight in zip(parts, weights):
        a = start + duration * elapsed / total
        elapsed += weight
        b = start + duration * elapsed / total
        cues.append({'start': a, 'end': b, 'text': part})
    return cues


def source_cues(segments: list[dict], raw_words, reference_text: str) -> tuple[list[dict], bool]:
    """Return speech-sized source cues, using word times only if complete."""
    words = []
    words_valid = True
    previous_end = 0.0
    for item in raw_words or []:
        times = _valid_times(item)
        text = str(_field(item, 'word', '') or '').strip()
        if not times or not text or times[0] < previous_end - 0.05:
            words_valid = False
            break
        words.append({'start': times[0], 'end': times[1], 'text': text})
        previous_end = times[1]
    if words_valid and words and _coverage(reference_text, words):
        result, current = [], []
        for word in words:
            if current:
                current_text = ' '.join(item['text'] for item in current)
                if (word['start'] - current[-1]['end'] >= PAUSE_SECONDS
                    or word['end'] - current[0]['start'] > MAX_SOURCE_SECONDS
                    or len(current) >= MAX_SOURCE_WORDS
                    or len(current_text) + len(word['text']) + 1 > MAX_SOURCE_CHARS
                    or (len(current) >= 3 and re.search(r'[.!?؟؛。！？][”’"\']?$', current[-1]['text']))):
                    result.append({'start': current[0]['start'], 'end': current[-1]['end'], 'text': current_text})
                    current = []
            current.append(word)
        if current:
            result.append({'start': current[0]['start'], 'end': current[-1]['end'],
                           'text': ' '.join(item['text'] for item in current)})
        return result, True

    # Recover complete word-timed segments individually. A single malformed or
    # missing word elsewhere must not discard precise timestamps for the rest.
    valid_words = []
    for item in raw_words or []:
        times = _valid_times(item)
        text = str(_field(item, 'word', '') or '').strip()
        if times and text:
            valid_words.append({'word': text, 'start': times[0], 'end': times[1]})
    valid_words.sort(key=lambda item: (item['start'], item['end']))
    ordered_segments = sorted(segments, key=lambda item: item['start'])
    assigned = [[] for _ in ordered_segments]
    for word in valid_words:
        midpoint = (word['start'] + word['end']) / 2
        for index, segment in enumerate(ordered_segments):
            if segment['start'] <= midpoint <= segment['end']:
                assigned[index].append(word)
                break
    result = []
    all_precise = bool(ordered_segments)
    for segment, candidates in zip(ordered_segments, assigned):
        if candidates:
            candidate_words = [{'text': item['word']} for item in candidates]
            if _coverage(segment['text'], candidate_words):
                timed, precise = source_cues([], candidates, segment['text'])
                if precise:
                    result.extend(timed)
                    continue
        all_precise = False
        result.extend(_spread_text(segment['text'], segment['start'], segment['end'],
                                   max_chars=MAX_SOURCE_CHARS, max_words=MAX_SOURCE_WORDS,
                                   max_seconds=MAX_SOURCE_SECONDS))
    return result, all_precise


def _caption_parts(text: str) -> list[str]:
    """Pack complete words only when they fit into at most two lines."""
    parts, current = [], []

    def fits(value: str) -> bool:
        if len(value) <= MAX_LINE_CHARS:
            return True
        return any(i <= MAX_LINE_CHARS and len(value) - i - 1 <= MAX_LINE_CHARS
                   for i, char in enumerate(value) if char == ' ')

    for word in re.findall(r'\S+', text):
        candidate = ' '.join(current + [word])
        if current and not fits(candidate):
            parts.append(' '.join(current))
            current = []
        current.append(word)
    if current:
        parts.append(' '.join(current))
    return parts


def _wrap_two_lines(text: str) -> str:
    if len(text) <= MAX_LINE_CHARS:
        return text
    spaces = [i for i, char in enumerate(text) if char == ' ']
    if not spaces:
        return text  # Avoid breaking a single word or URL in the middle.
    valid = [i for i in spaces if i <= MAX_LINE_CHARS and len(text) - i - 1 <= MAX_LINE_CHARS]
    cut = min(valid or spaces, key=lambda i: abs(len(text) / 2 - i))
    return text[:cut].strip() + '\n' + text[cut + 1:].strip()


def caption_cues(segments: list[dict]) -> list[dict]:
    """Ensure sequential short cues for SRT, VTT and the burned-in renderer."""
    expanded = []
    for segment in sorted(segments, key=lambda item: item['start']):
        start, end = float(segment['start']), float(segment['end'])
        text = re.sub(r'\s+', ' ', str(segment['text'])).strip()
        if not text or not math.isfinite(start) or not math.isfinite(end) or end <= start:
            continue
        # Group by line size; words are kept intact and never dropped.
        parts = _caption_parts(text)
        weights = [max(1, len(part.replace(' ', ''))) for part in parts]
        duration = end - start
        total = sum(weights)
        elapsed = 0
        for part, weight in zip(parts, weights):
            a = start + duration * elapsed / total
            elapsed += weight
            b = start + duration * elapsed / total
            expanded.append({'start': a, 'end': b, 'text': _wrap_two_lines(part)})

    # Providers sometimes return overlapping paragraphs. Share the available
    # interval among those cues instead of displaying all of them at once.
    clusters = []
    for cue in expanded:
        clusters.append([cue])
        # A later source segment may begin before several cues produced from
        # an earlier long segment. Merge backwards while preserving text order.
        while (len(clusters) > 1
               and min(item['start'] for item in clusters[-1]) < max(item['end'] for item in clusters[-2])):
            latest = clusters.pop()
            clusters[-1].extend(latest)

    sequential = []
    for cluster in clusters:
        if len(cluster) == 1:
            sequential.extend(cluster)
            continue
        start = min(item['start'] for item in cluster)
        end = max(item['end'] for item in cluster)
        weights = [max(1, len(re.sub(r'\s+', '', item['text']))) for item in cluster]
        total = sum(weights)
        span = end - start
        # Reserve a minimum viewing interval for each cue when the shared
        # window allows it; allocate the rest by text length.
        minimum = MIN_CUE_SECONDS if span >= len(cluster) * MIN_CUE_SECONDS else 0.0
        spare = max(0.0, span - minimum * len(cluster))
        cursor = start
        for index, (cue, weight) in enumerate(zip(cluster, weights)):
            next_time = end if index == len(cluster) - 1 else cursor + minimum + spare * weight / total
            sequential.append({**cue, 'start': cursor, 'end': next_time})
            cursor = next_time

    result = []
    for cue in sequential:
        start = max(cue['start'], result[-1]['end'] if result else 0.0)
        # Do not artificially lengthen a short utterance beyond the source
        # interval; the duration here reflects speech, not a reading estimate.
        end = max(cue['end'], start + 0.001)
        result.append({**cue, 'start': start, 'end': end})
    return result
