"""Application-level validation beyond provider schema conformance."""

from pydantic import BaseModel

from ai_adoption_engine.models.candidate_process import CandidateBusinessProcess
from ai_adoption_engine.models.document import IngestedDocument


def validate_candidate_against_document(
    candidate: CandidateBusinessProcess,
    document: IngestedDocument,
) -> None:
    if candidate.source_document_id != document.document_id:
        raise ValueError("Candidate source document does not match extraction input")
    block_ids = {block.block_id for block in document.blocks}
    document_text = document.canonical_text

    def check_assertion(assertion: object) -> None:
        evidence = getattr(assertion, "evidence", None)
        if evidence is None:
            return
        for reference in evidence:
            if reference.document_id != document.document_id:
                raise ValueError("Candidate evidence references a different document")
            if reference.block_id not in block_ids:
                raise ValueError("Candidate evidence references an unknown block")
            resolved = document_text[
                reference.document_start_offset : reference.document_end_offset
            ]
            if resolved != reference.exact_snippet:
                raise ValueError("Candidate evidence offsets do not resolve exactly")

    def walk(value: object) -> None:
        check_assertion(value)
        if isinstance(value, BaseModel):
            for name in type(value).model_fields:
                walk(getattr(value, name))
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(candidate)
