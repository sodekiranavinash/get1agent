from __future__ import annotations

import re

# Rough token estimate: English averages ~4 characters per token. Using a
# character budget keeps chunking dependency-free and deterministic, which is
# all the splitter needs since embeddings are the expensive part.
_CHARS_PER_TOKEN = 4
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _max_chars(chunk_size: int) -> int:
    return max(200, chunk_size * _CHARS_PER_TOKEN)


def _split_long(text: str, limit: int) -> list[str]:
    sentences = _SENTENCE_SPLIT.split(text)
    units: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            units.append(current)
        if len(sentence) <= limit:
            current = sentence
        else:
            for start in range(0, len(sentence), limit):
                units.append(sentence[start : start + limit])
            current = ""
    if current:
        units.append(current)
    return units


def _units(text: str, limit: int) -> list[str]:
    units: list[str] = []
    for paragraph in re.split(r"\n{2,}", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) <= limit:
            units.append(paragraph)
        else:
            units.extend(_split_long(paragraph, limit))
    return units


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split text into overlapping chunks, preferring paragraph boundaries."""
    limit = _max_chars(chunk_size)
    overlap_chars = max(0, overlap) * _CHARS_PER_TOKEN
    normalized = re.sub(r"[ \t]+\n", "\n", (text or "").replace("\r\n", "\n"))
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    if not normalized:
        return []

    chunks: list[str] = []
    current = ""
    for unit in _units(normalized, limit):
        candidate = f"{current}\n\n{unit}" if current else unit
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        tail = current[-overlap_chars:] if current and overlap_chars else ""
        current = f"{tail}\n\n{unit}".strip() if tail else unit

    if current:
        chunks.append(current)

    return [chunk.strip() for chunk in chunks if chunk.strip()]
