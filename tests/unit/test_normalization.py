from ai_adoption_engine.ingestion.builders import BlockDraft, build_blocks
from ai_adoption_engine.ingestion.normalization import (
    PAGE_SEPARATOR,
    normalize_text,
    split_text_blocks,
)
from ai_adoption_engine.models.document import DocumentInputType


def test_canonical_normalisation_contract() -> None:
    source = "  Alpha  \r\n\tBeta\t\r\n\r\n Gamma ! \r\n\r\n"
    assert normalize_text(source) == "Alpha\nBeta\n\nGamma !"
    blocks = split_text_blocks(source)
    assert [(block.text, block.line_start, block.line_end) for block in blocks] == [
        ("Alpha\nBeta", 1, 2),
        ("Gamma !", 4, 4),
    ]


def test_page_boundaries_and_empty_page_positions_are_canonical() -> None:
    canonical, blocks = build_blocks(
        [
            BlockDraft(text="Page one", page_number=1),
            BlockDraft(text="", page_number=2, has_extractable_text=False),
            BlockDraft(text="Page three", page_number=3),
        ],
        DocumentInputType.PDF,
    )
    assert canonical == f"Page one{PAGE_SEPARATOR}{PAGE_SEPARATOR}Page three"
    assert [block.page_number for block in blocks] == [1, 2, 3]
    assert canonical[blocks[1].document_start_offset : blocks[1].document_end_offset] == ""

