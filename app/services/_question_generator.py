"""Single-question generation loop: retrieve → prompt → verify → retry."""
from __future__ import annotations

import hashlib
import logging
import re
import time
from typing import Dict, List, Optional

from app.core.config import settings
from app.generation.evidence_format import extract_evidence_spans, render_evidence
from app.generation.llm_client import LLMClient
from app.generation.prompt_templates import build_prompt
from app.retrieval.query_builder import build_query, build_query_varied
from app.retrieval.retriever import Retriever
from app.schemas.request import GenerateRequestItem
from app.schemas.response import QuestionItem
from app.verification.gate import CrossCoVeReviewer, ReviewerClient, verify_questions
from app.services._pipeline_utils import (
    _build_failure_question,
    _build_dedupe_instruction,
    _format_doc_ids,
    _get_llm_error_reason,
    _merge_instructions,
    _normalize_stem,
    _summarize_verification_results,
    _truncate_log,
)

LOGGER = logging.getLogger(__name__)

_MAX_ATTEMPTS = max(settings.LLM_MAX_ATTEMPTS, 1)
_CANDIDATES_PER_ATTEMPT = max(settings.LLM_CANDIDATES, 1)

_REQUOTE_INSTRUCTION = "re-quote exact evidence span"
_STRICT_JSON_INSTRUCTION = (
    "Return only valid JSON for the requested schema. "
    "Do not include extra text, markdown, or code fences. "
    "Ensure answer_key is one of A/B/C/D; if insufficient evidence, use 'A'. "
    "Do not omit any required keys; do not return empty options or an empty stem."
)
_EVIDENCE_FOCUS_INSTRUCTION = (
    "Ensure the correct answer is directly supported by the evidence and "
    "quote the exact supporting span."
)
_DEDUPLICATE_INSTRUCTION = (
    "Generate a different question from previous ones; avoid repeating stems."
)
_V2_FAILED_CHECKS = {
    "evidence_span_mismatch",
    "evidence_span_empty",
    "evidence_doc_missing",
}
_REWRITE_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _rewrite_query(topic: str, competency: str) -> str:
    base = build_query(topic, competency).strip()
    tokens = _REWRITE_TOKEN_RE.findall(competency)
    if not tokens:
        return base
    return f"{base} {' '.join(tokens)}".strip()


def _generate_single_question(
    item: GenerateRequestItem,
    retriever: Retriever,
    llm_client: LLMClient,
    reviewer_client: Optional[ReviewerClient],
    cross_cove_reviewer: Optional[CrossCoVeReviewer],
    avoid_stems: List[str],
    used_doc_ids: Optional[set[str]] = None,
    retrieval_cache: Optional[Dict[str, tuple]] = None,
) -> tuple[QuestionItem, List[Dict[str, object]]]:
    attempt_history: List[Dict[str, object]] = []
    attempt_logs: List[Dict[str, object]] = []
    final_question: Optional[QuestionItem] = None
    initial_top_k = max(settings.EVIDENCE_TOP_K, 0)
    expanded_top_k = max(settings.EVIDENCE_TOP_K_EXPANDED, 0)
    evidence_top_k = initial_top_k
    query_override: Optional[str] = None
    extra_instructions: Optional[str] = None
    attempt_reason = "initial"
    track_doc_ids = used_doc_ids is not None
    doc_id_tracker = used_doc_ids if used_doc_ids is not None else set()
    final_evidence_doc_ids: List[str] = []
    v2_requote_count = 0
    _retrieval_cache = retrieval_cache if retrieval_cache is not None else {}

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        query_used = (query_override or "").strip() or build_query(item.topic, item.competency)
        attempt_reason_used = attempt_reason
        retrieval_mode = settings.RETRIEVAL_MODE

        LOGGER.info(
            "\nAttempt start: topic=%s competency=%s attempt=%s reason=%s evidence_top_k=%s query=%s",
            item.topic, item.competency, attempt, attempt_reason_used, evidence_top_k,
            _truncate_log(query_used),
        )

        excluded_key = frozenset(doc_id_tracker) if doc_id_tracker else frozenset()
        cache_key = f"{query_used}|{evidence_top_k}|{excluded_key}"
        if cache_key in _retrieval_cache:
            retrieval_result, retrieval_ms = _retrieval_cache[cache_key]
            retrieval_ms = 0.0
            LOGGER.info(
                "\nRetrieval cached: topic=%s competency=%s attempt=%s (skipped ~14s)",
                item.topic, item.competency, attempt,
            )
        else:
            retrieval_start = time.perf_counter()
            retrieval_result = retriever.retrieve(
                item.topic,
                item.competency,
                evidence_top_k=evidence_top_k,
                query_override=query_override,
                exclude_doc_ids=doc_id_tracker if doc_id_tracker else None,
            )
            retrieval_ms = (time.perf_counter() - retrieval_start) * 1000.0
            _retrieval_cache[cache_key] = (retrieval_result, retrieval_ms)

        LOGGER.info(
            "\nRetrieval done: topic=%s competency=%s attempt=%s mode=%s ms=%.1f evidence_docs=%s bm25=%s dense=%s fused=%s",
            item.topic, item.competency, attempt, retrieval_mode, retrieval_ms,
            len(retrieval_result.evidence_docs),
            len(retrieval_result.bm25_doc_ids), len(retrieval_result.dense_doc_ids),
            len(retrieval_result.fused_doc_ids),
        )

        if not retrieval_result.evidence_docs:
            LOGGER.warning(
                "\nRetrieval empty: topic=%s competency=%s attempt=%s reason=%s",
                item.topic, item.competency, attempt, attempt_reason_used,
            )
            _empty_log = {
                "attempt": attempt, "reason": attempt_reason_used, "query": query_used,
                "evidence_top_k": evidence_top_k, "prompt_hash": "",
                "evidence_doc_ids": {
                    "bm25": retrieval_result.bm25_doc_ids,
                    "dense": retrieval_result.dense_doc_ids,
                    "fused": retrieval_result.fused_doc_ids,
                },
                "runtime_ms": {"retrieval": retrieval_ms, "llm": 0.0, "verification": 0.0},
                "retrieval_mode": retrieval_mode,
                "status_counts": {"INSUFFICIENT_EVIDENCE": 1},
                "failed_checks": ["insufficient_evidence"],
            }
            attempt_logs.append(_empty_log)
            attempt_history.append({
                "attempt": attempt, "reason": attempt_reason_used, "query": query_used,
                "evidence_top_k": evidence_top_k, "retrieval_ms": retrieval_ms,
                "retrieval_mode": retrieval_mode,
                "status_counts": {"INSUFFICIENT_EVIDENCE": 1},
                "failed_checks": ["insufficient_evidence"],
            })
            if attempt < _MAX_ATTEMPTS:
                evidence_top_k = expanded_top_k
                query_override = _rewrite_query(item.topic, item.competency)
                attempt_reason = "v3_insufficient"
                extra_instructions = None
                continue
            final_question = _build_failure_question(item, status="INSUFFICIENT_EVIDENCE", error_message="insufficient_evidence")
            final_question.meta.retrieval.setdefault("retrieval_mode", settings.RETRIEVAL_MODE)
            final_question.meta.timings_ms.setdefault("retrieval", retrieval_ms)
            final_question.meta.timings_ms.setdefault("llm", 0.0)
            final_question.meta.timings_ms.setdefault("verification", 0.0)
            break

        evidence_docs = list(retrieval_result.evidence_docs)
        if avoid_stems and evidence_docs:
            offset = len(avoid_stems) % len(evidence_docs)
            if offset:
                evidence_docs = evidence_docs[offset:] + evidence_docs[:offset]
        evidence_reused = False
        if doc_id_tracker:
            fresh_docs = [doc for doc in evidence_docs if doc.doc_id not in doc_id_tracker]
            if fresh_docs:
                evidence_docs = fresh_docs
            else:
                evidence_reused = True
                if attempt < _MAX_ATTEMPTS:
                    did_adjust = False
                    if evidence_top_k < expanded_top_k:
                        evidence_top_k = expanded_top_k
                        did_adjust = True
                    if not query_override:
                        query_override = _rewrite_query(item.topic, item.competency)
                        did_adjust = True
                    if did_adjust:
                        attempt_reason = "v8_evidence_diversity"
                        extra_instructions = None
                        continue

        evidence_docs_for_prompt = evidence_docs
        if settings.EVIDENCE_FIRST:
            extracted_docs = extract_evidence_spans(
                evidence_docs, item.topic, item.competency,
                max_sentences_per_doc=settings.EVIDENCE_FIRST_MAX_SENTENCES,
                max_chars_per_doc=settings.EVIDENCE_FIRST_MAX_CHARS,
            )
            if extracted_docs:
                evidence_docs_for_prompt = extracted_docs

        evidence_doc_ids = [doc.doc_id for doc in evidence_docs_for_prompt]
        LOGGER.info(
            "\nPrompt evidence: topic=%s competency=%s attempt=%s docs=%s reused=%s ids=%s",
            item.topic, item.competency, attempt,
            len(evidence_docs_for_prompt), evidence_reused, _format_doc_ids(evidence_doc_ids),
        )

        dedupe_instruction = _build_dedupe_instruction(avoid_stems)
        combined_instructions = _merge_instructions(extra_instructions, dedupe_instruction)
        evidence_text = render_evidence(
            evidence_docs_for_prompt,
            max_chars_per_doc=settings.EVIDENCE_MAX_CHARS_PER_DOC,
            max_total_chars=settings.EVIDENCE_MAX_TOTAL_CHARS,
        )
        candidate_count = _CANDIDATES_PER_ATTEMPT
        LOGGER.info(
            "\nLLM generate: topic=%s competency=%s attempt=%s candidates=%s",
            item.topic, item.competency, attempt, candidate_count,
        )
        prompt = build_prompt(
            item.topic, item.competency, evidence_text, candidate_count,
            extra_instructions=combined_instructions, language=item.language,
        )
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        llm_start = time.perf_counter()
        questions = llm_client.generate_mcq(
            item.topic, item.competency, evidence_text, candidate_count,
            extra_instructions=combined_instructions, language=item.language,
        )
        llm_ms = (time.perf_counter() - llm_start) * 1000.0

        verification_start = time.perf_counter()
        verification_results = verify_questions(
            questions, evidence_docs_for_prompt,
            reviewer=reviewer_client, cross_cove_reviewer=cross_cove_reviewer, run_reviewer=True,
        )
        verification_ms = (time.perf_counter() - verification_start) * 1000.0

        for result in verification_results:
            question = result.question
            question.meta.retrieval.setdefault("doc_ids", retrieval_result.doc_ids)
            question.meta.retrieval.setdefault("evidence_doc_ids", evidence_doc_ids)
            question.meta.retrieval.setdefault("retrieval_mode", retrieval_mode)
            question.meta.timings_ms.setdefault("retrieval", retrieval_ms)
            question.meta.timings_ms.setdefault("llm", llm_ms)
            question.meta.timings_ms.setdefault("verification", verification_ms)

        normalized_avoid = {_normalize_stem(stem) for stem in avoid_stems}
        candidate_infos = []
        for candidate_index, result in enumerate(verification_results):
            question = result.question
            normalized_stem = _normalize_stem(question.stem or "")
            is_duplicate = bool(normalized_stem and normalized_stem in normalized_avoid)
            candidate_failed_checks = list(result.report.failed_checks)
            if is_duplicate:
                candidate_failed_checks = sorted(set(candidate_failed_checks) | {"duplicate_question"})
            candidate_infos.append({
                "index": candidate_index,
                "question": question,
                "failed_checks": candidate_failed_checks,
                "is_duplicate": is_duplicate,
            })

        selected = next(
            (info for info in candidate_infos if info["question"].status == "OK" and not info["failed_checks"]),
            None,
        )
        if selected is None:
            selected = min(
                candidate_infos,
                key=lambda info: (
                    0 if info["question"].status == "OK" else 1,
                    len(info["failed_checks"]),
                    info["index"],
                ),
            )

        question_result = selected["question"]
        is_duplicate = selected["is_duplicate"]
        selected_failed_checks = selected["failed_checks"]
        llm_error = _get_llm_error_reason(question_result)

        status_counts, aggregate_failed_checks = _summarize_verification_results(verification_results)
        if is_duplicate:
            aggregate_failed_checks = sorted(set(aggregate_failed_checks) | {"duplicate_question"})

        LOGGER.info(
            "\nVerification summary: topic=%s competency=%s attempt=%s status_counts=%s failed_checks=%s selected_failed=%s",
            item.topic, item.competency, attempt, status_counts,
            aggregate_failed_checks, selected_failed_checks,
        )

        attempt_logs.append({
            "attempt": attempt, "reason": attempt_reason_used, "query": query_used,
            "evidence_top_k": evidence_top_k, "candidate_count": candidate_count,
            "selected_index": selected["index"] + 1, "prompt_hash": prompt_hash,
            "evidence_doc_ids": {
                "bm25": retrieval_result.bm25_doc_ids,
                "dense": retrieval_result.dense_doc_ids,
                "fused": retrieval_result.fused_doc_ids,
            },
            "runtime_ms": {"retrieval": retrieval_ms, "llm": llm_ms, "verification": verification_ms},
            "retrieval_mode": retrieval_mode,
            "status_counts": status_counts, "failed_checks": selected_failed_checks,
            "failed_checks_all": aggregate_failed_checks,
            "evidence_doc_ids_used": evidence_doc_ids, "evidence_reused": evidence_reused,
        })
        attempt_history.append({
            "attempt": attempt, "reason": attempt_reason_used, "query": query_used,
            "evidence_top_k": evidence_top_k, "candidate_count": candidate_count,
            "selected_index": selected["index"] + 1,
            "retrieval_ms": retrieval_ms, "llm_ms": llm_ms, "verification_ms": verification_ms,
            "extra_instructions": extra_instructions or "",
            "retrieval_mode": retrieval_mode,
            "status_counts": status_counts, "failed_checks": selected_failed_checks,
            "failed_checks_all": aggregate_failed_checks,
            "evidence_doc_ids_used": evidence_doc_ids, "evidence_reused": evidence_reused,
        })

        if question_result.status == "OK" and not selected_failed_checks:
            final_question = question_result
            final_evidence_doc_ids = evidence_doc_ids
            break

        if attempt < _MAX_ATTEMPTS:
            if question_result.status == "INSUFFICIENT_EVIDENCE" or "missing_evidence" in selected_failed_checks:
                evidence_top_k = expanded_top_k
                query_override = _rewrite_query(item.topic, item.competency)
                attempt_reason = "v3_insufficient"
                extra_instructions = None
                continue
            if "duplicate_question" in selected_failed_checks:
                extra_instructions = _merge_instructions(_DEDUPLICATE_INSTRUCTION, _EVIDENCE_FOCUS_INSTRUCTION)
                attempt_reason = "v7_deduplicate"
                continue
            if llm_error in ("invalid_json", "short", "empty_response") or "schema_validation" in selected_failed_checks:
                extra_instructions = _STRICT_JSON_INSTRUCTION
                attempt_reason = "v4_json_strict"
                continue
            if any(check in _V2_FAILED_CHECKS for check in selected_failed_checks):
                v2_requote_count += 1
                extra_instructions = _REQUOTE_INSTRUCTION
                if v2_requote_count >= 2:
                    query_override = build_query_varied(item.topic, item.competency, variation_index=v2_requote_count - 2)
                    attempt_reason = "v2_requote_varied"
                    LOGGER.info(
                        "\nQuery variation applied: topic=%s competency=%s v2_count=%s query=%s",
                        item.topic, item.competency, v2_requote_count, _truncate_log(query_override),
                    )
                else:
                    attempt_reason = "v2_requote"
                continue
            if any(check in ("reviewer_mismatch", "reviewer_insufficient") for check in selected_failed_checks):
                extra_instructions = _EVIDENCE_FOCUS_INSTRUCTION
                attempt_reason = "v5_reviewer"
                continue
            if question_result.status != "OK":
                extra_instructions = _EVIDENCE_FOCUS_INSTRUCTION
                attempt_reason = "v6_retry"
                continue

        final_question = question_result
        final_evidence_doc_ids = evidence_doc_ids
        break

    if final_question is None:
        final_question = _build_failure_question(item, status="FAILED_VERIFICATION", error_message="pipeline_error")

    if track_doc_ids and final_question.status == "OK" and final_evidence_doc_ids:
        doc_id_tracker.update(final_evidence_doc_ids)

    verification_meta = dict(final_question.meta.verification or {})
    verification_meta["attempt_history"] = attempt_history
    final_question.meta.verification = verification_meta

    return final_question, attempt_logs
