"""Deterministic document/block identifiers and canonical offset construction."""

from dataclasses import dataclass

from ai_adoption_engine.ingestion.normalization import BLOCK_SEPARATOR, PAGE_SEPARATOR
from ai_adoption_engine.models.document import DocumentInputType, TextBlock


@dataclass(frozen=True)
class BlockDraft:
    text: str
    page_number: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    has_extractable_text: bool = True


def build_blocks(
    drafts: list[BlockDraft],
    input_type: DocumentInputType,
) -> tuple[str, list[TextBlock]]:
    canonical = ""
    blocks: list[TextBlock] = []
    previous_page: int | None = None
    page_block_counts: dict[int, int] = {}

    for sequence, draft in enumerate(drafts, start=1):
        if input_type is DocumentInputType.PDF:
            assert draft.page_number is not None
            if previous_page is not None:
                canonical += (
                    PAGE_SEPARATOR
                    if draft.page_number != previous_page
                    else BLOCK_SEPARATOR
                )
            page_block_counts[draft.page_number] = (
                page_block_counts.get(draft.page_number, 0) + 1
            )
            block_number = page_block_counts[draft.page_number]
            block_id = f"p{draft.page_number:04d}-b{block_number:04d}"
            source_locator = f"page {draft.page_number}, block {block_number}"
            previous_page = draft.page_number
        else:
            if blocks:
                canonical += BLOCK_SEPARATOR
            block_number = sequence
            block_id = f"t-b{block_number:04d}"
            if draft.line_start == draft.line_end:
                source_locator = f"line {draft.line_start}"
            else:
                source_locator = f"lines {draft.line_start}-{draft.line_end}"

        start = len(canonical)
        canonical += draft.text
        end = len(canonical)
        blocks.append(
            TextBlock(
                block_id=block_id,
                sequence=sequence,
                page_number=draft.page_number,
                block_number=block_number,
                line_start=draft.line_start,
                line_end=draft.line_end,
                document_start_offset=start,
                document_end_offset=end,
                source_locator=source_locator,
                extracted_text=draft.text,
                has_extractable_text=draft.has_extractable_text,
            )
        )
    return canonical, blocks

