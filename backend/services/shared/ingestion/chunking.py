from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass

# Rough token estimate: English averages ~4 characters per token. Using a
# character budget keeps chunking dependency-free and deterministic, which is
# all the splitter needs since embeddings are the expensive part.
_CHARS_PER_TOKEN = 4
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_PARAGRAPH_SPLIT = re.compile(r"\n{2,}")


def _max_chars(chunk_size: int) -> int:
    return max(200, chunk_size * _CHARS_PER_TOKEN)


def _normalize(text: str) -> str:
    normalized = re.sub(r"[ \t]+\n", "\n", (text or "").replace("\r\n", "\n"))
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _split_spans(text: str, pattern: re.Pattern[str]) -> list[tuple[int, int]]:
    """Split ``text`` on ``pattern``, returning ``(start, end)`` of each piece."""
    spans: list[tuple[int, int]] = []
    last = 0
    for match in pattern.finditer(text):
        spans.append((last, match.start()))
        last = match.end()
    spans.append((last, len(text)))
    return spans


def _trim_span(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


@dataclass
class Chunk:
    """A chunk of text plus its character span and source page range.

    ``start``/``end`` are offsets into the normalized text the chunker saw.
    ``page``/``page_end`` are 1-based source page numbers and are only set for
    paginated documents (PDFs); they are ``None`` otherwise.
    """

    text: str
    start: int
    end: int
    page: int | None = None
    page_end: int | None = None


@dataclass(frozen=True)
class _Unit:
    text: str
    start: int
    end: int


def _split_long(text: str, limit: int, base: int) -> list[_Unit]:
    units: list[_Unit] = []
    current = ""
    current_start = 0
    current_end = 0
    for start, end in _split_spans(text, _SENTENCE_SPLIT):
        sentence = text[start:end]
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= limit:
            if not current:
                current_start = base + start
            current = candidate
            current_end = base + end
            continue
        if current:
            units.append(_Unit(current, current_start, current_end))
        if len(sentence) <= limit:
            current = sentence
            current_start = base + start
            current_end = base + end
        else:
            for offset in range(0, len(sentence), limit):
                piece = sentence[offset : offset + limit]
                units.append(
                    _Unit(
                        piece,
                        base + start + offset,
                        base + start + offset + len(piece),
                    )
                )
            current = ""
    if current:
        units.append(_Unit(current, current_start, current_end))
    return units


def _units(text: str, limit: int) -> list[_Unit]:
    units: list[_Unit] = []
    for para_start, para_end in _split_spans(text, _PARAGRAPH_SPLIT):
        start, end = _trim_span(text, para_start, para_end)
        if start >= end:
            continue
        paragraph = text[start:end]
        if len(paragraph) <= limit:
            units.append(_Unit(paragraph, start, end))
        else:
            units.extend(_split_long(paragraph, limit, start))
    return units


def _chunk_spans(normalized: str, chunk_size: int, overlap: int) -> list[Chunk]:
    """Split normalized text into overlapping chunks, tracking source spans."""
    limit = _max_chars(chunk_size)
    overlap_chars = max(0, overlap) * _CHARS_PER_TOKEN
    if not normalized:
        return []

    chunks: list[Chunk] = []
    current = ""
    current_start = 0
    current_end = 0
    for unit in _units(normalized, limit):
        candidate = f"{current}\n\n{unit.text}" if current else unit.text
        if len(candidate) <= limit:
            if not current:
                current_start = unit.start
            current = candidate
            current_end = unit.end
            continue
        if current:
            chunks.append(Chunk(current, current_start, current_end))
        tail = current[-overlap_chars:] if current and overlap_chars else ""
        if tail:
            # Never let the carried-over overlap push the new chunk over the
            # limit: cap the tail so `tail + separator + unit` still fits.
            max_tail = max(0, limit - len(unit.text) - 2)
            tail = tail[-max_tail:] if max_tail else ""
        if tail:
            # The cut point is arbitrary, so start the overlap on a word
            # boundary — a chunk should never begin mid-word.
            offset = len(current) - len(tail)
            if offset > 0 and not current[offset - 1].isspace():
                match = re.search(r"\s", tail)
                tail = tail[match.end() :] if match else ""
        if tail:
            tail_start = max(current_start, current_end - len(tail))
            current = f"{tail}\n\n{unit.text}".strip()
            current_start = tail_start
            current_end = unit.end
        else:
            current = unit.text
            current_start = unit.start
            current_end = unit.end
    if current:
        chunks.append(Chunk(current, current_start, current_end))

    result: list[Chunk] = []
    for chunk in chunks:
        stripped = chunk.text.strip()
        if not stripped:
            continue
        lead = len(chunk.text) - len(chunk.text.lstrip())
        start = chunk.start + lead
        result.append(Chunk(stripped, start, start + len(stripped)))
    return result


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split text into overlapping chunks, preferring paragraph boundaries."""
    normalized = _normalize(text)
    return [chunk.text for chunk in _chunk_spans(normalized, chunk_size, overlap)]


def chunk_pages(pages: list[str], chunk_size: int, overlap: int) -> list[Chunk]:
    """Chunk per-page text and tag each chunk with its source page range.

    Pages are normalized individually and joined with blank lines so chunk
    boundaries stay the same as :func:`chunk_text`, while the offset of every
    page in the joined text is known. Each chunk is attributed to the page
    containing its first character (``page``) and its last character
    (``page_end``).
    """
    normalized_pages = [_normalize(page) for page in pages]
    joined = "\n\n".join(page for page in normalized_pages if page)
    if not joined:
        return []

    boundaries: list[int] = []
    page_numbers: list[int] = []
    offset = 0
    first = True
    for number, page in enumerate(normalized_pages, start=1):
        if not page:
            continue
        if not first:
            offset += 2  # the "\n\n" separator
        boundaries.append(offset)
        page_numbers.append(number)
        offset += len(page)
        first = False

    chunks = _chunk_spans(joined, chunk_size, overlap)
    for chunk in chunks:
        start_index = max(0, bisect_right(boundaries, chunk.start) - 1)
        end_index = max(
            0, bisect_right(boundaries, max(chunk.end - 1, chunk.start)) - 1
        )
        chunk.page = page_numbers[start_index]
        chunk.page_end = page_numbers[end_index]
    return chunks


@dataclass
class Parent:
    """A larger context unit (page or window) and its child chunks.

    Retrieval matches the small children but returns the parent's text, which is
    the "small-to-big" pattern. ``page``/``page_end`` are set for paginated
    formats (PDF) and ``None`` otherwise.
    """

    text: str
    start: int
    end: int
    page: int | None
    page_end: int | None
    children: list[Chunk]


def _children_for(
    text: str, chunk_size: int, overlap: int, page: int | None
) -> list[Chunk]:
    children = _chunk_spans(text, chunk_size, overlap)
    if page is not None:
        for child in children:
            child.page = page
            child.page_end = page
    return children


def chunk_parents(
    text: str,
    *,
    chunk_size: int,
    overlap: int,
    parent_size: int,
    page_texts: list[str] | None = None,
) -> list[Parent]:
    """Build parents and their child chunks for small-to-big retrieval.

    Paginated formats pass ``page_texts``: each page becomes a parent (split
    into several parents sharing the page number if the page is huge) and no
    child ever crosses a page boundary. Other formats are split into
    non-overlapping parent windows; children within a window may overlap.
    """
    parents: list[Parent] = []

    def add(page: int | None, source_text: str) -> None:
        for parent_chunk in _chunk_spans(source_text, parent_size, 0):
            children = _children_for(
                parent_chunk.text, chunk_size, overlap, page
            )
            if not children:
                continue
            parents.append(
                Parent(
                    text=parent_chunk.text,
                    start=parent_chunk.start,
                    end=parent_chunk.end,
                    page=page,
                    page_end=page,
                    children=children,
                )
            )

    if page_texts:
        for number, raw_page in enumerate(page_texts, start=1):
            normalized = _normalize(raw_page)
            if normalized:
                add(number, normalized)
    else:
        normalized = _normalize(text)
        if normalized:
            add(None, normalized)
    return parents
