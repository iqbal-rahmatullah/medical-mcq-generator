from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from app.corpus.models import Document
from app.core.config import settings
from app.generation.evidence_format import render_evidence
from app.generation.llm_client import LLMClient
from app.schemas.response import QuestionItem

LOGGER = logging.getLogger(__name__)

_ANSWER_RE = re.compile(r"\b([A-D])\b", re.IGNORECASE)
_TOPIC_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


class VerificationReport(BaseModel):
    passed: bool = Field(alias="pass")
    failed_checks: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class ReviewerClient:
    def __init__(self, llm_client: LLMClient, model_name: str = "") -> None:
        self._llm_client = llm_client
        self._model_name = model_name

    def review(self, question: QuestionItem, evidence_text: str) -> str:
        prompt = _build_review_prompt(question, evidence_text)
        text = self._llm_client.generate_text(prompt)
        if text is None:
            raise RuntimeError("reviewer_empty_response")
        return _parse_reviewer_decision(text)

    def check_topic_coverage(self, topic: str, evidence_text: str) -> bool:
        prompt = _build_topic_coverage_prompt(topic, evidence_text)
        text = self._llm_client.generate_text(prompt)
        if text is None:
            raise RuntimeError("topic_coverage_empty_response")
        return _parse_topic_coverage_decision(text)


@dataclass
class VerificationResult:
    question: QuestionItem
    report: VerificationReport


class CrossCoVeReviewer:
    """Cross-Chain-of-Verification with 3 different LLM reviewers and majority voting."""
    
    def __init__(self, reviewers: List[ReviewerClient]) -> None:
        self._reviewers = reviewers
    
    def cross_verify(self, question: QuestionItem, evidence_text: str) -> str:
        """Run verification with all reviewers in parallel and return majority vote."""
        from collections import Counter
        from concurrent.futures import ThreadPoolExecutor, as_completed

        total_reviewers = len(self._reviewers)
        votes = []

        def _call_reviewer(reviewer: ReviewerClient) -> tuple:
            model_name = getattr(reviewer, '_model_name', 'unknown')
            decision = reviewer.review(question, evidence_text)
            return model_name, decision

        with ThreadPoolExecutor(max_workers=total_reviewers) as executor:
            futures = {
                executor.submit(_call_reviewer, r): r for r in self._reviewers
            }
            for future in as_completed(futures):
                try:
                    model_name, decision = future.result(timeout=30)
                    votes.append(decision)
                    LOGGER.info(
                        "\\nCross-CoVe vote: model=%s decision=%s",
                        model_name, decision,
                    )
                except Exception as exc:
                    LOGGER.warning("Cross-CoVe reviewer failed (skipped): %s", exc)
                    continue

        if not votes:
            return "INSUFFICIENT"

        min_quorum = (total_reviewers + 1) // 2
        if len(votes) < min_quorum:
            LOGGER.warning(
                "\\nCross-CoVe quorum not met: got %d/%d votes (need %d), returning INSUFFICIENT",
                len(votes), total_reviewers, min_quorum,
            )
            return "INSUFFICIENT"

        vote_counts = Counter(votes)
        majority_answer, count = vote_counts.most_common(1)[0]

        LOGGER.info(
            "\\nCross-CoVe result: votes=%s majority=%s count=%s",
            votes, majority_answer, count,
        )

        return majority_answer
    
    def check_topic_coverage(self, topic: str, evidence_text: str) -> bool:
        """Check topic coverage using first available reviewer."""
        for reviewer in self._reviewers:
            try:
                return reviewer.check_topic_coverage(topic, evidence_text)
            except Exception:
                continue
        return False



def verify_questions(
    questions: Iterable[QuestionItem],
    evidence_docs: List[Document],
    reviewer: Optional[ReviewerClient] = None,
    cross_cove_reviewer: Optional[CrossCoVeReviewer] = None,
    run_reviewer: bool = True,
) -> List[VerificationResult]:
    if not isinstance(questions, list):
        questions = list(questions)
    LOGGER.info(
        "\nVerification start: questions=%s reviewer_enabled=%s evidence_docs=%s",
        len(questions),
        bool(run_reviewer and reviewer is not None),
        len(evidence_docs),
    )
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
        failed_checks.extend(
            _check_topic_coverage_llm(
                question,
                doc_lookup,
                notes,
                reviewer if run_reviewer else None,
            )
        )

        if (
            run_reviewer
            and question.status == "OK"
            and not failed_checks
        ):
            try:
                evidence_text = render_evidence(
                    evidence_docs,
                    max_chars_per_doc=settings.EVIDENCE_MAX_CHARS_PER_DOC,
                    max_total_chars=settings.EVIDENCE_MAX_TOTAL_CHARS,
                )
                
                # Use Cross-CoVe if enabled and available
                if settings.COVE_ENABLED and cross_cove_reviewer is not None:
                    decision = cross_cove_reviewer.cross_verify(question, evidence_text)
                    reviewer_mode = "cross_cove"
                elif reviewer is not None:
                    decision = reviewer.review(question, evidence_text)
                    reviewer_mode = "single"
                else:
                    decision = None
                    reviewer_mode = "none"
                
                if decision is None:
                    pass
                elif decision == "INSUFFICIENT":
                    LOGGER.warning(
                        "\\nReviewer failed: reason=insufficient mode=%s topic=%s competency=%s answer_key=%s",
                        reviewer_mode,
                        question.topic,
                        question.competency,
                        question.answer_key,
                    )
                    failed_checks.append("reviewer_insufficient")
                    notes.append(f"reviewer ({reviewer_mode}) returned INSUFFICIENT")
                elif decision != question.answer_key:
                    LOGGER.warning(
                        "\\nReviewer failed: reason=mismatch mode=%s topic=%s competency=%s expected=%s got=%s",
                        reviewer_mode,
                        question.topic,
                        question.competency,
                        question.answer_key,
                        decision,
                    )
                    failed_checks.append("reviewer_mismatch")
                    notes.append(f"reviewer ({reviewer_mode})={decision} expected={question.answer_key}")
            except Exception as exc:
                LOGGER.warning(
                    "\\nReviewer error: topic=%s competency=%s error=%s",
                    question.topic,
                    question.competency,
                    exc,
                )
                failed_checks.append("reviewer_error")
                notes.append(str(exc))

        report = VerificationReport(
            **{"pass": len(failed_checks) == 0, "failed_checks": failed_checks, "notes": notes}
        )
        if failed_checks:
            if "topic_coverage" in failed_checks:
                question.status = "INSUFFICIENT_EVIDENCE"
            else:
                question.status = "FAILED_VERIFICATION"

        verification_meta = dict(question.meta.verification or {})
        verification_meta["gate"] = report.model_dump(by_alias=True)
        question.meta.verification = verification_meta

        results.append(VerificationResult(question=question, report=report))

    LOGGER.info(
        "\nVerification done: questions=%s passed=%s failed=%s",
        len(results),
        sum(1 for result in results if result.report.passed),
        sum(1 for result in results if not result.report.passed),
    )

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

    valid_evidence = []
    for evidence in question.evidence:
        doc = doc_lookup.get(evidence.doc_id)
        if doc is None:
            notes.append(f"stripped missing doc_id: {evidence.doc_id}")
            continue
        span_text = _normalize_match_text(evidence.span_text)
        if not span_text:
            notes.append(f"stripped empty span_text for doc_id: {evidence.doc_id}")
            continue
        doc_text = _normalize_match_text(f"{doc.title} {doc.text}")
        if span_text and span_text in doc_text:
            valid_evidence.append(evidence)
            continue
        if _span_fuzzy_match(span_text, doc_text, threshold=0.60):
            valid_evidence.append(evidence)
            continue
        notes.append(f"stripped mismatched span for doc_id: {evidence.doc_id}")

    question.evidence = valid_evidence
    if not valid_evidence and question.status == "OK":
        failed_checks.append("missing_evidence")

    return failed_checks


def _span_fuzzy_match(span: str, doc_text: str, threshold: float = 0.70) -> bool:
    """Return True if ≥threshold fraction of span tokens appear in the doc text."""
    span_tokens = set(span.split())
    if not span_tokens:
        return False
    doc_tokens = set(doc_text.split())
    overlap = len(span_tokens & doc_tokens)
    return (overlap / len(span_tokens)) >= threshold


def _check_topic_coverage_llm(
    question: QuestionItem,
    doc_lookup: dict[str, Document],
    notes: List[str],
    reviewer: Optional[ReviewerClient],
) -> List[str]:
    """Non-blocking topic coverage check. Results are logged as notes only,
    not as failed_checks, so Cross-CoVe always gets a chance to vote."""
    evidence_docs = [
        doc_lookup.get(evidence.doc_id)
        for evidence in question.evidence
        if evidence.doc_id in doc_lookup
    ]
    evidence_docs = [doc for doc in evidence_docs if doc is not None]
    if not evidence_docs:
        return []

    if reviewer is None:
        return []

    try:
        evidence_text = render_evidence(
            evidence_docs,
            max_chars_per_doc=settings.EVIDENCE_MAX_CHARS_PER_DOC,
            max_total_chars=settings.EVIDENCE_MAX_TOTAL_CHARS,
        )
        is_covered = reviewer.check_topic_coverage(question.topic, evidence_text)
        if not is_covered:
            notes.append("topic_coverage: reviewer says evidence may not cover topic (non-blocking)")
    except Exception as exc:
        notes.append(f"topic_coverage_error: {exc}")

    return []


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


def _build_topic_coverage_prompt(topic: str, evidence_text: str) -> str:
    return (
        "You are checking whether the evidence is relevant to the topic.\n"
        "Reply with a single token: YES or NO.\n"
        "Do not add extra text.\n\n"
        f"Topic: {topic}\n\n"
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


def _parse_topic_coverage_decision(text: str) -> bool:
    normalized = text.strip().upper()
    if "YES" in normalized:
        return True
    if "NO" in normalized:
        return False
    return False
