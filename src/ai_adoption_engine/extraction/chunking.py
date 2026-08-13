"""Deterministic, block-preserving chunk planning for Phase 3."""

from __future__ import annotations

from dataclasses import dataclass

from ai_adoption_engine.models.document import IngestedDocument, TextBlock


@dataclass(frozen=True)
class ChunkingConfig:
    max_characters: int = 40_000
    max_non_empty_blocks: int = 30
    overlap_blocks: int = 1

    def __post_init__(self) -> None:
        if self.max_characters < 1:
            raise ValueError("max_characters must be positive")
        if self.max_non_empty_blocks < 1:
            raise ValueError("max_non_empty_blocks must be positive")
        if self.overlap_blocks < 0:
            raise ValueError("overlap_blocks cannot be negative")
        if self.overlap_blocks >= self.max_non_empty_blocks:
            raise ValueError("overlap_blocks must be less than max_non_empty_blocks")


@dataclass(frozen=True)
class DocumentSlice:
    slice_id: str
    block_id: str
    block_sequence: int
    source_locator: str
    block_start_offset: int
    block_end_offset: int
    text: str


@dataclass(frozen=True)
class DocumentChunk:
    chunk_id: str
    sequence: int
    slices: tuple[DocumentSlice, ...]
    has_previous: bool
    has_next: bool

    @property
    def character_count(self) -> int:
        return sum(len(item.text) for item in self.slices)

    @property
    def block_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.block_id for item in self.slices))


def _split_block(block: TextBlock, max_characters: int) -> list[DocumentSlice]:
    if len(block.extracted_text) <= max_characters:
        return [
            DocumentSlice(
                slice_id=f"{block.block_id}-s0001",
                block_id=block.block_id,
                block_sequence=block.sequence,
                source_locator=block.source_locator,
                block_start_offset=0,
                block_end_offset=len(block.extracted_text),
                text=block.extracted_text,
            )
        ]

    slices: list[DocumentSlice] = []
    start = 0
    text = block.extracted_text
    while start < len(text):
        hard_end = min(start + max_characters, len(text))
        end = hard_end
        if hard_end < len(text):
            line_break = text.rfind("\n", start + 1, hard_end + 1)
            whitespace = text.rfind(" ", start + 1, hard_end + 1)
            boundary = max(line_break, whitespace)
            if boundary > start:
                end = boundary + 1
        slices.append(
            DocumentSlice(
                slice_id=f"{block.block_id}-s{len(slices) + 1:04d}",
                block_id=block.block_id,
                block_sequence=block.sequence,
                source_locator=block.source_locator,
                block_start_offset=start,
                block_end_offset=end,
                text=text[start:end],
            )
        )
        start = end
    return slices


def plan_chunks(
    document: IngestedDocument,
    config: ChunkingConfig | None = None,
) -> list[DocumentChunk]:
    """Create stable chunks without altering Phase 2 block identity or text."""

    settings = config or ChunkingConfig()
    block_groups = [
        _split_block(block, settings.max_characters)
        for block in document.blocks
        if block.has_extractable_text
    ]
    if not block_groups:
        return []

    raw_chunks: list[list[DocumentSlice]] = []
    current: list[DocumentSlice] = []
    current_blocks: list[str] = []
    current_characters = 0

    def flush() -> None:
        nonlocal current, current_blocks, current_characters
        if not current:
            return
        raw_chunks.append(current)
        overlap_ids = current_blocks[-settings.overlap_blocks :] if settings.overlap_blocks else []
        current = [item for item in current if item.block_id in overlap_ids]
        current_blocks = list(dict.fromkeys(item.block_id for item in current))
        current_characters = sum(len(item.text) for item in current)

    for group in block_groups:
        if len(group) > 1:
            flush()
            if current:
                # Do not duplicate a preceding block around an oversized block.
                current = []
                current_blocks = []
                current_characters = 0
            for item in group:
                raw_chunks.append([item])
            continue

        item = group[0]
        would_add_block = item.block_id not in current_blocks
        exceeds_blocks = would_add_block and (
            len(current_blocks) + 1 > settings.max_non_empty_blocks
        )
        exceeds_characters = current and (
            current_characters + len(item.text) > settings.max_characters
        )
        if exceeds_blocks or exceeds_characters:
            flush()
            if current and current_characters + len(item.text) > settings.max_characters:
                current = []
                current_blocks = []
                current_characters = 0
        current.append(item)
        if would_add_block:
            current_blocks.append(item.block_id)
        current_characters += len(item.text)
    if current:
        raw_chunks.append(current)

    total = len(raw_chunks)
    return [
        DocumentChunk(
            chunk_id=f"{document.document_id}-chunk-{index:04d}",
            sequence=index,
            slices=tuple(items),
            has_previous=index > 1,
            has_next=index < total,
        )
        for index, items in enumerate(raw_chunks, start=1)
    ]
