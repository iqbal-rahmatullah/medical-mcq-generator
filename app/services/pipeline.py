from __future__ import annotations

from typing import List

from app.schemas.request import GenerateRequestItem
from app.schemas.response import (
    EvidenceItem,
    Meta,
    Options,
    QuestionItem,
    QuestionStatus,
)


def _build_stub_question(item: GenerateRequestItem, index: int) -> QuestionItem:
    options = Options(
        A="Pilihan A (stub)",
        B="Pilihan B (stub)",
        C="Pilihan C (stub)",
        D="Pilihan D (stub)",
    )
    evidence = [
        EvidenceItem(
            source="stub",
            doc_id="stub-001",
            title=f"Stub reference for {item.topic}",
            span_text="Placeholder evidence span.",
        )
    ]
    meta = Meta(
        retrieval={"mode": "stub"},
        verification={"mode": "stub"},
        timings_ms={"total": 0.0},
    )
    return QuestionItem(
        topic=item.topic,
        competency=item.competency,
        stem=f"Stub question {index + 1} tentang {item.topic}",
        options=options,
        answer_key="A",
        explanation="Stub explanation.",
        evidence=evidence,
        status="OK",
        meta=meta,
    )


def _build_failure_question(
    item: GenerateRequestItem,
    status: QuestionStatus,
    error_message: str,
) -> QuestionItem:
    meta = Meta(
        retrieval={"error": error_message},
        verification={"error": error_message},
        timings_ms={"total": 0.0},
    )
    return QuestionItem(
        topic=item.topic,
        competency=item.competency,
        stem="",
        options=Options(A="", B="", C="", D=""),
        answer_key="A",
        explanation=error_message,
        evidence=[],
        status=status,
        meta=meta,
    )


def build_failure_batch(
    payload: List[GenerateRequestItem],
    error_message: str,
    status: QuestionStatus = "FAILED_VERIFICATION",
) -> List[QuestionItem]:
    results: List[QuestionItem] = []
    for item in payload:
        count = max(item.n_questions, 1)
        for _ in range(count):
            results.append(_build_failure_question(item, status, error_message))
    return results


def run_pipeline_batch(payload: List[GenerateRequestItem]) -> List[QuestionItem]:
    results: List[QuestionItem] = []

    for item in payload:
        try:
            if item.n_questions < 1:
                raise ValueError("n_questions must be >= 1")

            for index in range(item.n_questions):
                results.append(_build_stub_question(item, index))
        except ValueError as exc:
            results.extend(build_failure_batch([item], str(exc), status="FAILED_VERIFICATION"))
        except Exception as exc:
            results.extend(
                build_failure_batch([item], f"pipeline_error: {exc}", status="FAILED_VERIFICATION")
            )

    return results
