from __future__ import annotations

from app.corpus.models import Document
from app.schemas.response import EvidenceItem, Meta, Options, QuestionItem
from app.verification.gate import verify_questions


def test_evidence_span_mismatch_fails() -> None:
    doc = Document(
        doc_id="doc-1",
        source="test",
        title="Hypertension study",
        text="Treatment of severe hypertension with minoxidil.",
    )
    question = QuestionItem(
        topic="Hypertension",
        competency="Treatment",
        stem="What is one treatment for severe hypertension?",
        options=Options(A="A", B="B", C="C", D="D"),
        answer_key="C",
        explanation="Minoxidil is used.",
        evidence=[
            EvidenceItem(
                source="test",
                doc_id="doc-1",
                title="Hypertension study",
                span_text="This span does not exist.",
            )
        ],
        status="OK",
        meta=Meta(retrieval={}, verification={}, timings_ms={}),
    )

    results = verify_questions([question], [doc], reviewer=None, run_reviewer=False)

    assert results[0].report.passed is False
    assert "evidence_span_mismatch" in results[0].report.failed_checks
    assert results[0].question.status == "FAILED_VERIFICATION"
