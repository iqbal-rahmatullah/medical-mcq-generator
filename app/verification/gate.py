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
        failed_checks.extend(
            _check_topic_relevance(
                question,
                notes,
                reviewer if run_reviewer else None,
            )
        )
        failed_checks.extend(_check_forbidden_option_formats(question, notes))
        failed_checks.extend(_check_clinical_vignette(question, notes))

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


def _check_topic_relevance(
    question: QuestionItem,
    notes: List[str],
    reviewer: Optional[ReviewerClient],
) -> List[str]:
    """Check if the generated question is actually about the requested topic using LLM."""
    if reviewer is None:
        return []
    if question.status != "OK":
        return []

    try:
        prompt = _build_topic_relevance_prompt(question.topic, question.stem)
        text = reviewer._llm_client.generate_text(prompt)
        if text is None:
            return []
        is_relevant = _parse_topic_coverage_decision(text)
        if not is_relevant:
            LOGGER.warning(
                "Topic guard FAILED: topic=%s stem=%s",
                question.topic,
                question.stem[:100],
            )
            notes.append(f"topic_relevance: question is not about '{question.topic}'")
            return ["topic_relevance"]
        else:
            LOGGER.info(
                "Topic guard OK: topic=%s",
                question.topic,
            )
    except Exception as exc:
        notes.append(f"topic_relevance_error: {exc}")

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
        "You are verifying whether a medical MCQ is answerable from evidence AND well-constructed.\n"
        "Reply with a single token: A, B, C, D, or INSUFFICIENT.\n"
        "Reply INSUFFICIENT if:\n"
        "  - The correct answer cannot be determined from the evidence\n"
        "  - The distractors (wrong options) are implausible or not medically relevant\n"
        "  - The question tests only trivial recall rather than clinical reasoning\n"
        "Do not add extra text.\n\n"
        f"Question: {question.stem}\n"
        f"Options:\n{options}\n\n"
        f"Evidence:\n{evidence_text}\n"
    )


def _build_topic_relevance_prompt(topic: str, stem: str) -> str:
    return (
        "You are checking whether a medical exam question is DIRECTLY about the given topic.\n"
        "The question must specifically test knowledge of the topic, not merely mention it.\n"
        "Reply with a single token: YES or NO.\n"
        "Do not add extra text.\n\n"
        f"Topic: {topic}\n\n"
        f"Question: {stem}\n"
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


_DEFINITIONAL_PATTERNS = [
    re.compile(r"^apa\s+(yang\s+)?(?:dimaksud|definisi|pengertian)", re.I),
    re.compile(r"^apa\s+(?:itu|adalah)\b", re.I),
    re.compile(r"bidang studi mana", re.I),
    re.compile(r"^definisi\s+", re.I),
    re.compile(r"^what\s+is\s+(?:the\s+)?(?:definition|meaning)\s+of\b", re.I),
    re.compile(r"^define\s+\w+", re.I),
    re.compile(r"^which\s+field\s+of\s+(?:study|medicine)", re.I),
    re.compile(r"^what\s+is\s+\w+\?\s*$", re.I),
    re.compile(r"^which\s+of\s+the\s+following\s+(?:bacteria|virus|organism|pathogen|drug|medication|antibiotic|enzyme|gene|chromosome)\b", re.I),
    re.compile(r"^what\s+is\s+the\s+(?:most\s+common\s+)?(?:cause|etiology|pathogen|agent)\s+of\b", re.I),
    re.compile(r"^what\s+is\s+the\s+(?:primary|recommended|preferred|main|standard)\s+(?:method|treatment|therapy|approach|benefit|goal|purpose)\s+(?:of|for)\b", re.I),
    re.compile(r"^what\s+is\s+the\s+(?:primary|recommended|preferred|current)\s+(?:understanding|concept|mechanism)\b", re.I),
    re.compile(r"^what\s+is\s+the\s+recommended\s+concentration\b", re.I),
    re.compile(r"^which\s+(?:mosquito|vector|organism|bacteria|virus)\s+(?:species|type)\s+is\b", re.I),
]


def _check_clinical_vignette(
    question: QuestionItem,
    notes: List[str],
) -> List[str]:
    """Block definitional/trivial stems that are not clinical vignettes."""
    if question.status != "OK":
        return []
    stem = question.stem.strip()
    for pattern in _DEFINITIONAL_PATTERNS:
        if pattern.search(stem):
            LOGGER.warning(
                "Clinical vignette gate FAILED: stem is definitional. topic=%s stem=%s",
                question.topic,
                stem[:120],
            )
            notes.append("clinical_vignette: stem is definitional, not a clinical question")
            return ["not_clinical_vignette"]
    return []


_FORBIDDEN_OPTION_PATTERNS = [
    re.compile(r"\ball\s+of\s+the\s+above\b", re.I),
    re.compile(r"\bnone\s+of\s+the\s+above\b", re.I),
    re.compile(r"\bboth\s+[a-d]\s+and\s+[a-d]\b", re.I),
    re.compile(r"\bsemua\s+(?:di\s+atas|jawaban\s+benar)\b", re.I),
    re.compile(r"\btidak\s+ada\s+(?:yang\s+benar|di\s+atas)\b", re.I),
]


def _check_forbidden_option_formats(
    question: QuestionItem,
    notes: List[str],
) -> List[str]:
    """Reject options like 'All of the above' or 'None of the above' — banned in standard MCQs."""
    if question.status != "OK":
        return []
    opts = [
        question.options.A or "",
        question.options.B or "",
        question.options.C or "",
        question.options.D or "",
    ]
    for opt_text in opts:
        for pattern in _FORBIDDEN_OPTION_PATTERNS:
            if pattern.search(opt_text):
                LOGGER.warning(
                    "Forbidden option format: topic=%s option=%s",
                    question.topic, opt_text[:80],
                )
                notes.append(f"forbidden_option: '{opt_text}'")
                return ["forbidden_option_format"]
    return []


_COMPETENCY_ANSWER_GUIDANCE = {
    "diagnosis": (
        "a diagnostic test, imaging modality, sign/symptom interpretation, "
        "scoring tool, or diagnostic criterion — NOT a treatment or drug"
    ),
    "treatment": (
        "a drug, procedure, therapeutic intervention, or management step — "
        "NOT a diagnostic test or pathophysiology explanation"
    ),
    "etiology": (
        "a cause, risk factor, pathogen, organism, or predisposing condition — "
        "NOT a treatment or purely diagnostic step"
    ),
    "pathology": (
        "a histological finding, pathological mechanism, cellular change, or "
        "morphological feature — NOT a drug or screening test"
    ),
    "basic sciences": (
        "a physiological mechanism, biochemical process, anatomical structure, "
        "or basic science concept — NOT a clinical management decision"
    ),
    "clinical practice": None,  # flexible, skip check
}


def _check_competency_alignment(
    question: QuestionItem,
    notes: List[str],
    reviewer: Optional[ReviewerClient],
) -> List[str]:
    """LLM gate: verify the correct answer type is consistent with the stated competency."""
    if reviewer is None:
        return []
    if question.status != "OK":
        return []

    competency_key = (question.competency or "").strip().lower()
    guidance = _COMPETENCY_ANSWER_GUIDANCE.get(competency_key)
    if guidance is None:
        return []  # clinical_practice is flexible — skip

    answer_letter = question.answer_key or "A"
    answer_text = getattr(question.options, answer_letter, "") or ""

    try:
        prompt = (
            f"You are checking whether a medical MCQ answer is appropriate for its competency.\n"
            f"Competency: {question.competency}\n"
            f"For this competency, the correct answer should be: {guidance}\n\n"
            f"Correct answer ({answer_letter}): {answer_text}\n\n"
            f"Is the correct answer consistent with the competency? Reply YES or NO only."
        )
        text = reviewer._llm_client.generate_text(prompt)
        if text is None:
            return []
        aligned = _parse_topic_coverage_decision(text)
        if not aligned:
            LOGGER.warning(
                "Competency alignment FAILED: topic=%s competency=%s answer=%s",
                question.topic, question.competency, answer_letter,
            )
            notes.append(
                f"competency_mismatch: answer '{answer_text}' does not match "
                f"competency '{question.competency}'"
            )
            return ["competency_mismatch"]
        else:
            LOGGER.debug(
                "Competency alignment OK: topic=%s competency=%s",
                question.topic, question.competency,
            )
    except Exception as exc:
        notes.append(f"competency_alignment_error: {exc}")

    return []

def _check_evidence_supports_answer(
    question: QuestionItem,
    doc_lookup: dict[str, Document],
    notes: List[str],
    reviewer: Optional[ReviewerClient],
) -> List[str]:
    """Check if the evidence EXPLICITLY supports the stated answer key."""
    if reviewer is None:
        return []
    if question.status != "OK":
        return []
    if not question.evidence:
        return []

    evidence_docs = [
        doc_lookup.get(e.doc_id)
        for e in question.evidence
        if e.doc_id in doc_lookup
    ]
    evidence_docs = [d for d in evidence_docs if d is not None]
    if not evidence_docs:
        return []

    try:
        evidence_text = render_evidence(
            evidence_docs,
            max_chars_per_doc=settings.EVIDENCE_MAX_CHARS_PER_DOC,
            max_total_chars=settings.EVIDENCE_MAX_TOTAL_CHARS,
        )
        answer_letter = question.answer_key or "A"
        answer_text = getattr(question.options, answer_letter, "") or ""
        options = "\n".join([
            f"A. {question.options.A}",
            f"B. {question.options.B}",
            f"C. {question.options.C}",
            f"D. {question.options.D}",
        ])
        prompt = (
            f"You are checking whether evidence EXPLICITLY supports the correct answer to a medical MCQ.\n"
            f"Stated correct answer: ({answer_letter}) {answer_text}\n\n"
            f"Question: {question.stem}\n"
            f"Options:\n{options}\n\n"
            f"Evidence:\n{evidence_text}\n\n"
            f"Does the evidence EXPLICITLY state or strongly imply that option {answer_letter} is correct?\n"
            f"Answer NO if the evidence only mentions the topic tangentially without supporting the specific answer.\n"
            f"Reply YES or NO only."
        )
        text = reviewer._llm_client.generate_text(prompt)
        if text is None:
            return []
        supported = _parse_topic_coverage_decision(text)
        if not supported:
            LOGGER.warning(
                "Evidence-answer alignment FAILED: topic=%s answer=%s text=%s",
                question.topic, answer_letter, answer_text[:60],
            )
            notes.append(
                f"evidence_answer_mismatch: evidence does not explicitly support "
                f"({answer_letter}) '{answer_text}'"
            )
            return ["evidence_answer_mismatch"]
        else:
            LOGGER.debug(
                "Evidence-answer alignment OK: topic=%s answer=%s",
                question.topic, answer_letter,
            )
    except Exception as exc:
        notes.append(f"evidence_answer_check_error: {exc}")

    return []

def _check_competency_alignment_nonblocking(
    question: "QuestionItem",
    notes: List[str],
    reviewer: Optional[ReviewerClient],
) -> None:
    """Non-blocking version: runs competency_alignment and logs result to notes only."""
    try:
        _check_competency_alignment(question, notes, reviewer)
    except Exception as exc:
        notes.append(f"competency_alignment_nb_error: {exc}")


def _check_evidence_supports_answer_nonblocking(
    question: "QuestionItem",
    doc_lookup: dict,
    notes: List[str],
    reviewer: Optional[ReviewerClient],
) -> None:
    """Non-blocking version: runs evidence_supports_answer and logs result to notes only."""
    try:
        _check_evidence_supports_answer(question, doc_lookup, notes, reviewer)
    except Exception as exc:
        notes.append(f"evidence_answer_nb_error: {exc}")
