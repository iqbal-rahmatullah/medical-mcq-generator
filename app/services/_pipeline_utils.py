"""Pure utility functions and constants shared across pipeline modules."""
from __future__ import annotations

import hashlib
import logging
import re
from typing import Dict, List, Optional, Set

from app.corpus.models import Document
from app.schemas.request import GenerateRequestItem
from app.schemas.response import EvidenceItem, Meta, Options, QuestionItem, QuestionStatus
from app.verification.gate import VerificationResult

LOGGER = logging.getLogger(__name__)

_GENERIC_FAILURE_MESSAGE = "generation_failed"


def _summarize_failure_reason(question: QuestionItem) -> str:
    verification_meta = question.meta.verification or {}
    retrieval_meta = question.meta.retrieval or {}
    reason = (
        verification_meta.get("error")
        or retrieval_meta.get("error")
        or question.explanation
        or question.status
    )
    return str(reason)


def _build_failure_question(
    item: GenerateRequestItem,
    status: QuestionStatus,
    error_message: str,
) -> QuestionItem:
    meta = Meta(
        retrieval={"error": error_message},
        verification={"error": error_message},
        timings_ms={},
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


def _normalize_stem(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _exact_question_hash(question: QuestionItem) -> str:
    opts = question.options
    content = "|".join([
        _normalize_stem(question.stem or ""),
        _normalize_stem(opts.A or ""),
        _normalize_stem(opts.B or ""),
        _normalize_stem(opts.C or ""),
        _normalize_stem(opts.D or ""),
        (question.answer_key or "").upper(),
    ])
    return hashlib.sha256(content.encode()).hexdigest()


def _truncate_log(value: str, limit: int = 160) -> str:
    cleaned = value.strip()
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit - 3].rstrip()}..."


def _format_doc_ids(doc_ids: List[str], limit: int = 4) -> str:
    if not doc_ids:
        return "none"
    head = ", ".join(doc_ids[:limit])
    if len(doc_ids) <= limit:
        return head
    return f"{head}, ... (+{len(doc_ids) - limit})"


def _matches_topic_competency(
    question: QuestionItem, topic: str, competency: str
) -> bool:
    return (
        question.topic.strip().lower() == topic.strip().lower()
        and question.competency.strip().lower() == competency.strip().lower()
    )


def _select_bank_question(
    bank_questions: List[QuestionItem],
    topic: str,
    competency: str,
    avoid_normalized: Set[str],
    allow_any_topic: bool,
) -> Optional[QuestionItem]:
    candidates = [
        q for q in bank_questions
        if q.status == "OK" and q.stem and _normalize_stem(q.stem) not in avoid_normalized
    ]
    if not candidates:
        return None
    matching = [q for q in candidates if _matches_topic_competency(q, topic, competency)]
    if matching:
        return QuestionItem.model_validate(matching[0].model_dump())
    if allow_any_topic:
        return QuestionItem.model_validate(candidates[0].model_dump())
    return None


def _merge_instructions(*parts: Optional[str]) -> Optional[str]:
    merged = " ".join(part.strip() for part in parts if part and part.strip())
    return merged or None


def _build_dedupe_instruction(avoid_stems: List[str], limit: int = 2) -> Optional[str]:
    if not avoid_stems:
        return None
    snippets: List[str] = []
    for stem in avoid_stems[-limit:]:
        snippet = stem.strip().replace("\n", " ")
        if len(snippet) > 120:
            snippet = f"{snippet[:117].rstrip()}..."
        if snippet:
            snippets.append(snippet)
    _dedup = "Generate a different question from previous ones; avoid repeating stems."
    if not snippets:
        return _dedup
    return f"{_dedup} Avoid these stems: {'; '.join(snippets)}."


def _get_llm_error_reason(question: QuestionItem) -> Optional[str]:
    for meta in (question.meta.verification, question.meta.retrieval):
        if isinstance(meta, dict):
            error = meta.get("error")
            if isinstance(error, str) and error.strip():
                return error
    return None


def _summarize_verification_results(
    verification_results: List[VerificationResult],
) -> tuple[Dict[str, int], List[str]]:
    status_counts: Dict[str, int] = {
        "OK": 0,
        "INSUFFICIENT_EVIDENCE": 0,
        "FAILED_VERIFICATION": 0,
    }
    failed_checks: Set[str] = set()
    for result in verification_results:
        status = result.question.status
        status_counts[status] = status_counts.get(status, 0) + 1
        failed_checks.update(result.report.failed_checks)
    return status_counts, sorted(failed_checks)


def _reattach_evidence_from_cache(
    question: QuestionItem,
    retrieval_cache: Dict[str, tuple],
) -> None:
    if question.evidence or not retrieval_cache:
        return

    stem_words = set(question.stem.lower().split())
    best_docs = []
    for _cache_key, (retrieval_result, _ms) in retrieval_cache.items():
        if not hasattr(retrieval_result, "evidence_docs"):
            continue
        for doc in retrieval_result.evidence_docs:
            text = getattr(doc, "text", "") or ""
            doc_words = set(text.lower().split())
            overlap = len(stem_words & doc_words) / max(len(stem_words), 1)
            best_docs.append((overlap, doc))

    best_docs.sort(key=lambda x: x[0], reverse=True)
    attached = []
    for score, doc in best_docs[:3]:
        if score < 0.2:
            continue
        text_snippet = (getattr(doc, "text", "") or "")[:500]
        doc_id = getattr(doc, "doc_id", "")
        source = getattr(doc, "source", "") or "knowledge_base"
        attached.append(
            EvidenceItem(
                source=source,
                doc_id=doc_id,
                title=getattr(doc, "title", "") or "",
                span_text=text_snippet,
            )
        )

    if attached:
        question.evidence = attached
        LOGGER.info(
            "Evidence re-attached: stem=%s docs=%d",
            _truncate_log(question.stem, 80),
            len(attached),
        )
