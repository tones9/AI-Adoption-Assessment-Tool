import ast
from pathlib import Path

from ai_adoption_engine.ingestion.service import ingest_file, ingest_raw_text
from ai_adoption_engine.models.document import IngestedDocument, IngestionStatus


def test_service_ingests_pdf_and_text_files(
    tmp_path: Path, pdf_fixture_bytes: bytes
) -> None:
    pdf_path = tmp_path / "process.pdf"
    pdf_path.write_bytes(pdf_fixture_bytes)
    text_path = tmp_path / "process.txt"
    text_path.write_text("Step description", encoding="utf-8")
    assert ingest_file(pdf_path).document is not None
    assert ingest_file(text_path).document is not None


def test_service_rejects_unsupported_file_type(tmp_path: Path) -> None:
    path = tmp_path / "process.docx"
    path.write_bytes(b"unsupported")
    result = ingest_file(path)
    assert result.status is IngestionStatus.FAILED
    assert result.issues[0].code == "unsupported-file-type"


def test_raw_text_returns_document_contract_only() -> None:
    result = ingest_raw_text("A current-state process description.")
    assert isinstance(result.document, IngestedDocument)
    assert not hasattr(result.document, "steps")


def test_ingestion_source_has_no_phase1_decision_or_process_imports() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "ai_adoption_engine" / "ingestion"
    forbidden = {
        "ai_adoption_engine.decision",
        "ai_adoption_engine.models.process",
        "ai_adoption_engine.models.assessment",
    }
    imported: set[str] = set()
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
    assert not any(
        imported_name == item or imported_name.startswith(f"{item}.")
        for imported_name in imported
        for item in forbidden
    )

