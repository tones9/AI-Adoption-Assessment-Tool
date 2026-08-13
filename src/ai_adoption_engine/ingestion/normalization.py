"""Canonical text representation for stable Phase 2 locators and offsets.

Contract:
- CRLF and CR line endings become LF.
- Leading/trailing horizontal whitespace is removed per line.
- Trailing blank lines are removed; internal blank lines are retained.
- Text is otherwise preserved: no case, punctuation, spelling, or semantic cleanup.
- Non-empty blocks within one text/page input are joined by ``\n\n``.
- PDF pages are joined by ``\n\f\n``; empty pages still occupy their page position.
- Half-open offsets count Python Unicode code points in ``canonical_text``.
"""

import re
from dataclasses import dataclass

BLOCK_SEPARATOR = "\n\n"
PAGE_SEPARATOR = "\n\f\n"


@dataclass(frozen=True)
class NormalizedBlock:
    text: str
    line_start: int | None = None
    line_end: int | None = None


def normalize_line_endings(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def normalize_text(text: str) -> str:
    lines = normalize_line_endings(text).split("\n")
    normalized = [line.strip(" \t") for line in lines]
    while normalized and normalized[-1] == "":
        normalized.pop()
    while normalized and normalized[0] == "":
        normalized.pop(0)
    return "\n".join(normalized)


def split_text_blocks(text: str) -> list[NormalizedBlock]:
    original_lines = normalize_line_endings(text).split("\n")
    normalized_lines = [line.strip(" \t") for line in original_lines]
    first = 0
    last = len(normalized_lines)
    while first < last and normalized_lines[first] == "":
        first += 1
    while last > first and normalized_lines[last - 1] == "":
        last -= 1
    if first == last:
        return []
    blocks: list[NormalizedBlock] = []
    start: int | None = None
    current: list[str] = []
    for index in range(first, last):
        line_number = index + 1
        line = normalized_lines[index]
        if line == "":
            if current and start is not None:
                blocks.append(
                    NormalizedBlock(
                        text="\n".join(current),
                        line_start=start,
                        line_end=line_number - 1,
                    )
                )
                current = []
                start = None
            continue
        if start is None:
            start = line_number
        current.append(line)
    if current and start is not None:
        blocks.append(
            NormalizedBlock(
                text="\n".join(current),
                line_start=start,
                line_end=last,
            )
        )
    return blocks


def split_pdf_page_blocks(text: str) -> list[NormalizedBlock]:
    """Split conservatively on blank lines without claiming semantic paragraphs."""

    return split_text_blocks(re.sub(r"\n[ \t]+\n", "\n\n", normalize_line_endings(text)))
