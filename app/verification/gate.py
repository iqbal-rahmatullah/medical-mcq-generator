from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from app.corpus.models import Document
from app.generation.evidence_format import render_evidence
from app.schemas.response import QuestionItem

LOGGER = logging.getLogger(__name__)

_ANSWER_RE = re.compile(r"\b([A-D])\b", re.IGNORECASE)


class VerificationReport(BaseModel):
    passed: bool = Field(alias="pass")
    failed_checks: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class ReviewerClient:
    def __init__(
        self,
        api_key: Optional[str],
        model: str,
        timeout_sec: float = 60.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout_sec = timeout_sec

    def review(self, question: QuestionItem, evidence_text: str) -> str:
        try:
            from google import genai
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(f"google-genai not available: {exc}") from exc

        prompt = _build_review_prompt(question, evidence_text)
        client = genai.Client(api_key=self._api_key)
        response = client.models.generate_content(
            model=self._model,
            contents=prompt,
            config={"temperature": 0.0},
        )
        text = getattr(response, "text", None)
        if not text:
            candidates = getattr(response, "candidates", None) or []
            if candidates:
                parts = getattr(candidates[0].content, "parts", None) or []
                text = "".join(getattr(part, "text", "") for part in parts)

        return _parse_reviewer_decision(text or "")


@dataclass
class VerificationResult:
    question: QuestionItem
    report: VerificationReport


def verify_questions(
    questions: Iterable[QuestionItem],
    evidence_docs: List[Document],
    reviewer: Optional[ReviewerClient] = None,
    run_reviewer: bool = True,
) -> List[VerificationResult]:
    results: List[VerificationResult] = []
    doc_lookup = {doc.doc_id: doc for doc in evidence_docs}
    adapter = TypeAdapter(QuestionItem)

    for question in questions:
        failed_checks: List[str] = []
        notes: List[str] = []

        try:
            adapter.validate_python(question.model_dump())
        except ValidationError as exc:
            failed_checks.append("schema_validation")
            notes.append(str(exc))

        failed_checks.extend(_check_evidence_spans(question, doc_lookup, notes))

        if (
            run_reviewer
            and reviewer is not None
            and question.status == "OK"
            and not failed_checks
        ):
            try:
                evidence_text = render_evidence(evidence_docs)
                decision = reviewer.review(question, evidence_text)
                if decision == "INSUFFICIENT":
                    failed_checks.append("reviewer_insufficient")
                    notes.append("reviewer returned INSUFFICIENT")
                elif decision != question.answer_key:
                    failed_checks.append("reviewer_mismatch")
                    notes.append(f"reviewer={decision} expected={question.answer_key}")
            except Exception as exc:
                failed_checks.append("reviewer_error")
                notes.append(str(exc))

        report = VerificationReport(
            **{"pass": len(failed_checks) == 0, "failed_checks": failed_checks, "notes": notes}
        )
        if failed_checks:
            question.status = "FAILED_VERIFICATION"

        verification_meta = dict(question.meta.verification or {})
        verification_meta["gate"] = report.model_dump(by_alias=True)
        question.meta.verification = verification_meta

        results.append(VerificationResult(question=question, report=report))

    return results


def _check_evidence_spans(
    question: QuestionItem,
    doc_lookup: dict[str, Document],
    notes: List[str],
) -> List[str]:
    failed_checks: List[str] = []

    if not question.evidence:
        if question.status == "OK":
            failed_checks.append("missing_evidence")
        return failed_checks

    for evidence in question.evidence:
        doc = doc_lookup.get(evidence.doc_id)
        if doc is None:
            failed_checks.append("evidence_doc_missing")
            notes.append(f"missing doc_id: {evidence.doc_id}")
            continue
        span_text = _normalize_match_text(evidence.span_text)
        if not span_text:
            failed_checks.append("evidence_span_empty")
            notes.append(f"empty span_text for doc_id: {evidence.doc_id}")
            continue
        doc_text = _normalize_match_text(f"{doc.title} {doc.text}")
        if span_text and span_text not in doc_text:
            failed_checks.append("evidence_span_mismatch")
            notes.append(f"span not found in doc_id: {evidence.doc_id}")

    return failed_checks


def _normalize_match_text(text: str) -> str:
    return " ".join(text.strip().split()).lower()


def _build_review_prompt(question: QuestionItem, evidence_text: str) -> str:
    options = "\n".join(
        [
            f"A. {question.options.A}",
            f"B. {question.options.B}",
            f"C. {question.options.C}",
            f"D. {question.options.D}",
        ]
    )
    return (
        "You are verifying if the question is answerable from the evidence.\n"
        "Reply with a single token: A, B, C, D, or INSUFFICIENT.\n"
        "Do not add extra text.\n\n"
        f"Question: {question.stem}\n"
        f"Options:\n{options}\n\n"
        f"Evidence:\n{evidence_text}\n"
    )


def _parse_reviewer_decision(text: str) -> str:
    normalized = text.strip().upper()
    if "INSUFFICIENT" in normalized:
        return "INSUFFICIENT"
    match = _ANSWER_RE.search(normalized)
    if match:
        return match.group(1).upper()
    return "INSUFFICIENT"
