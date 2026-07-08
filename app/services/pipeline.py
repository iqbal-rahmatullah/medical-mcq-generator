"""Pipeline orchestration: run_pipeline_stream and run_pipeline_batch."""
from __future__ import annotations

import json
import logging
import pickle
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, List, Optional

from app.core.config import settings
from app.corpus.loaders import load_pubmed_hf, load_textbooks_hf
from app.corpus.store import DocumentStore
from app.generation.llm_client import LLMClient
from app.retrieval.bm25 import BM25Index
from app.retrieval.medcpt_runtime import MedCPTRuntime
from app.retrieval.retriever import Retriever
from app.schemas.request import GenerateRequestItem
from app.schemas.response import QuestionItem, QuestionStatus
from app.logging.logger import log_run
from app.logging.latency_logger import LatencyTracker
from app.logging.question_bank import append_question_bank, load_question_bank
from app.services._pipeline_utils import (
    _build_failure_question,
    _exact_question_hash,
    _GENERIC_FAILURE_MESSAGE,
    _normalize_stem,
    _reattach_evidence_from_cache,
    _select_bank_question,
    _summarize_failure_reason,
    _truncate_log,
)
from app.services._question_generator import _generate_single_question
from app.services._reviewers import _get_cross_cove_reviewer, _get_reviewer_client
import hashlib  # noqa: E402 (used in _build_retriever_cache_fingerprint)

LOGGER = logging.getLogger(__name__)

_RETRIEVER: Optional[Retriever] = None
_RETRIEVER_ERROR: Optional[str] = None
_LLM_CLIENT: Optional[LLMClient] = None
_MAX_DEDUP_ATTEMPTS = max(settings.LLM_DEDUP_ATTEMPTS, 1)


def _get_llm_client() -> LLMClient:
    global _LLM_CLIENT
    if _LLM_CLIENT is None:
        _LLM_CLIENT = LLMClient()
    return _LLM_CLIENT


def _is_dev_environment() -> bool:
    return (settings.environment or "").strip().lower() in {"local", "development", "dev"}


def _get_retriever_cache_path() -> Optional[Path]:
    cache_path = (settings.RETRIEVER_CACHE_PATH or "").strip()
    return Path(cache_path).expanduser() if cache_path else None


def _build_retriever_cache_fingerprint() -> str:
    payload = {
        "corpus_schema_version": 2,
        "pubmed_dataset": settings.CORPUS_PUBMED_HF_DATASET,
        "textbooks_dataset": settings.CORPUS_TEXTBOOKS_HF_DATASET,
        "pubmed_max_docs": settings.CORPUS_PUBMED_MAX_DOCS,
        "textbooks_max_docs": settings.CORPUS_TEXTBOOKS_MAX_DOCS,
        "hf_local_only": settings.CORPUS_HF_LOCAL_ONLY,
        "hf_streaming": settings.CORPUS_HF_STREAMING,
        "bm25_k1": 1.5,
        "bm25_b": 0.75,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _load_cached_bm25_index() -> Optional[BM25Index]:
    if not _is_dev_environment():
        return None
    cache_path = _get_retriever_cache_path()
    if cache_path is None or not cache_path.exists():
        return None
    try:
        with cache_path.open("rb") as handle:
            payload = pickle.load(handle)
        if not isinstance(payload, dict):
            return None
        if payload.get("fingerprint") != _build_retriever_cache_fingerprint():
            return None
        index = payload.get("bm25_index")
        if isinstance(index, BM25Index):
            LOGGER.info("Loaded retriever cache from %s", cache_path)
            return index
    except Exception as exc:
        LOGGER.warning("Failed to load retriever cache: %s", exc)
    return None


def _write_cached_bm25_index(index: BM25Index) -> None:
    if not _is_dev_environment():
        return
    cache_path = _get_retriever_cache_path()
    if cache_path is None:
        return
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"fingerprint": _build_retriever_cache_fingerprint(), "bm25_index": index}
        with cache_path.open("wb") as handle:
            pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)
        LOGGER.info("Saved retriever cache to %s", cache_path)
    except Exception as exc:
        LOGGER.warning("Failed to write retriever cache: %s", exc)


def _load_corpus() -> DocumentStore:
    store = DocumentStore()
    pubmed_limit = max(settings.CORPUS_PUBMED_MAX_DOCS, 0)
    textbook_limit = max(settings.CORPUS_TEXTBOOKS_MAX_DOCS, 0)
    pubmed_count = 0
    textbook_count = 0

    try:
        for doc in load_pubmed_hf(
            settings.CORPUS_PUBMED_HF_DATASET,
            local_files_only=settings.CORPUS_HF_LOCAL_ONLY,
            streaming=settings.CORPUS_HF_STREAMING,
        ):
            if store.add(doc):
                pubmed_count += 1
            if pubmed_limit and pubmed_count >= pubmed_limit:
                break
    except Exception as exc:
        LOGGER.warning("Pubmed HF load failed: %s", exc)

    try:
        for doc in load_textbooks_hf(
            settings.CORPUS_TEXTBOOKS_HF_DATASET,
            local_files_only=settings.CORPUS_HF_LOCAL_ONLY,
            streaming=settings.CORPUS_HF_STREAMING,
        ):
            if store.add(doc):
                textbook_count += 1
            if textbook_limit and textbook_count >= textbook_limit:
                break
    except Exception as exc:
        LOGGER.warning("Textbooks HF load failed: %s", exc)

    return store


def _get_retriever() -> Optional[Retriever]:
    global _RETRIEVER, _RETRIEVER_ERROR
    if _RETRIEVER is not None or _RETRIEVER_ERROR:
        return _RETRIEVER

    try:
        index = _load_cached_bm25_index()
        if index is None:
            store = _load_corpus()
            if len(store) == 0:
                _RETRIEVER_ERROR = "corpus_empty"
                LOGGER.error("Corpus is empty; check HF dataset cache or config")
                return None
            index = BM25Index.build(store.iter_docs())
            _write_cached_bm25_index(index)

        medcpt_runtime = None
        if settings.RETRIEVAL_MODE == "hybrid_rerank":
            try:
                medcpt_runtime = MedCPTRuntime()
            except Exception as exc:
                LOGGER.exception("Failed to init MedCPT runtime: %s", exc)

        _RETRIEVER = Retriever(index, medcpt_runtime=medcpt_runtime)
        return _RETRIEVER
    except Exception as exc:
        _RETRIEVER_ERROR = f"retriever_init_failed: {exc}"
        LOGGER.exception("Failed to init retriever: %s", exc)
        return None


def build_failure_batch(
    payload: List[GenerateRequestItem],
    error_message: str,
    status: QuestionStatus = "FAILED_VERIFICATION",
) -> List[QuestionItem]:
    results: List[QuestionItem] = []
    for item in payload:
        for _ in range(max(item.n_questions, 1)):
            results.append(_build_failure_question(item, status, error_message))
    return results


def run_pipeline_stream(
    payload: List[GenerateRequestItem],
    include_failed: bool = True,
) -> Iterator[Dict[str, object]]:
    retriever = _get_retriever()
    llm_client = _get_llm_client()
    reviewer_client = _get_reviewer_client()
    cross_cove_reviewer = _get_cross_cove_reviewer()
    run_started = time.perf_counter()
    run_id = uuid.uuid4().hex
    run_timestamp = datetime.utcnow().isoformat() + "Z"
    run_log_items: List[Dict[str, object]] = []
    latency_tracker = LatencyTracker(run_id)
    input_batch = [item.model_dump() for item in payload]
    total_questions = sum(max(item.n_questions, 1) for item in payload)
    completed = 0
    run_used_stems: List[str] = []
    run_used_normalized: set[str] = set()
    run_used_hashes: set[str] = set()
    run_used_doc_ids: set[str] = set()
    ok_only_mode = settings.OK_ONLY_MODE
    ok_only_max_rounds = max(settings.OK_ONLY_MAX_ROUNDS, 1)
    ok_only_max_seconds = max(settings.OK_ONLY_MAX_SECONDS, 0.0)
    bank_questions: List[QuestionItem] = []
    bank_normalized: set[str] = set()
    if ok_only_mode and (settings.QUESTION_BANK_FALLBACK or settings.QUESTION_BANK_WRITE_OK):
        bank_questions = load_question_bank(settings.QUESTION_BANK_PATH)
        bank_normalized = {_normalize_stem(q.stem) for q in bank_questions if q.stem}

    yield {
        "type": "progress",
        "stage": "start",
        "run_id": run_id,
        "timestamp": run_timestamp,
        "total_questions": total_questions,
    }
    LOGGER.info(
        "\nRun start: run_id=%s items=%s total_questions=%s ok_only=%s retrieval_mode=%s",
        run_id, len(payload), total_questions, ok_only_mode, settings.RETRIEVAL_MODE,
    )

    def _build_question_event(
        question: QuestionItem, item_index: int, question_index: int
    ) -> Optional[Dict[str, object]]:
        if ok_only_mode:
            if question.status != "OK":
                return None
            return {"type": "question", "item_index": item_index, "question_index": question_index, "question": question.model_dump()}
        if include_failed or question.status == "OK":
            return {"type": "question", "item_index": item_index, "question_index": question_index, "question": question.model_dump()}
        return {
            "type": "question_failed",
            "item_index": item_index,
            "question_index": question_index,
            "status": question.status,
            "message": _summarize_failure_reason(question),
        }

    def _record_latency_for_logs(logs: List[Dict[str, object]]) -> None:
        for log in logs:
            rt = log.get("runtime_ms", {})
            latency_tracker.record_attempt(
                retrieval_ms=rt.get("retrieval", 0.0) if isinstance(rt, dict) else log.get("retrieval_ms", 0.0),
                llm_ms=rt.get("llm", 0.0) if isinstance(rt, dict) else log.get("llm_ms", 0.0),
                verification_ms=rt.get("verification", 0.0) if isinstance(rt, dict) else log.get("verification_ms", 0.0),
            )

    for item_index, item in enumerate(payload, start=1):
        item_attempts: List[Dict[str, object]] = []
        item_outputs: List[Dict[str, object]] = []
        item_reports: List[object] = []
        used_stems: List[str] = []

        try:
            LOGGER.info(
                "\nItem start: run_id=%s item_index=%s topic=%s competency=%s n_questions=%s",
                run_id, item_index, item.topic, item.competency, item.n_questions,
            )
            if item.n_questions < 1:
                raise ValueError("n_questions must be >= 1")

            item_started = time.perf_counter()
            ok_only_deadline = (item_started + ok_only_max_seconds) if ok_only_mode and ok_only_max_seconds > 0 else None

            if retriever is None:
                if ok_only_mode:
                    item_failed = False
                    pending_questions: List[QuestionItem] = []
                    pending_normalized: set[str] = set()

                    if not settings.QUESTION_BANK_FALLBACK:
                        LOGGER.error("generation_failed: retriever_unavailable and question bank fallback disabled")
                        item_failed = True
                        for _ in range(item.n_questions):
                            fq = _build_failure_question(item, "FAILED_VERIFICATION", _GENERIC_FAILURE_MESSAGE)
                            item_outputs.append(fq.model_dump())
                            item_reports.append(fq.meta.verification.get("gate"))
                        yield {"type": "error", "item_index": item_index, "message": _GENERIC_FAILURE_MESSAGE}
                    else:
                        for question_index in range(1, item.n_questions + 1):
                            avoid_normalized = set(run_used_normalized)
                            avoid_normalized.update(_normalize_stem(s) for s in used_stems if s)
                            avoid_normalized.update(pending_normalized)
                            fallback_question = _select_bank_question(
                                bank_questions, item.topic, item.competency,
                                avoid_normalized, settings.QUESTION_BANK_ALLOW_ANY_TOPIC,
                            )
                            if fallback_question is None:
                                LOGGER.error(
                                    "generation_failed: question bank fallback missing for topic=%s competency=%s",
                                    item.topic, item.competency,
                                )
                                item_failed = True
                                for _ in range(item.n_questions - question_index + 1):
                                    fq = _build_failure_question(item, "FAILED_VERIFICATION", _GENERIC_FAILURE_MESSAGE)
                                    item_outputs.append(fq.model_dump())
                                    item_reports.append(fq.meta.verification.get("gate"))
                                yield {"type": "error", "item_index": item_index, "message": _GENERIC_FAILURE_MESSAGE}
                                break
                            question = fallback_question
                            normalized_stem = _normalize_stem(question.stem or "")
                            item_outputs.append(question.model_dump())
                            item_reports.append(question.meta.verification.get("gate"))
                            pending_questions.append(question)
                            if question.stem and normalized_stem:
                                used_stems.append(question.stem)
                                pending_normalized.add(normalized_stem)

                    if item_failed:
                        continue
                    for question_index, question in enumerate(pending_questions, start=1):
                        normalized_stem = _normalize_stem(question.stem or "")
                        if question.stem and normalized_stem:
                            run_used_stems.append(question.stem)
                            run_used_normalized.add(normalized_stem)
                        completed += 1
                        event = _build_question_event(question, item_index, question_index)
                        if event is not None:
                            yield event
                        yield {"type": "progress", "completed": completed, "total_questions": total_questions}
                    continue

                for question_index, question in enumerate(
                    build_failure_batch([item], "retriever_unavailable"), start=1
                ):
                    item_outputs.append(question.model_dump())
                    item_reports.append(question.meta.verification.get("gate"))
                    completed += 1
                    event = _build_question_event(question, item_index, question_index)
                    if event is not None:
                        yield event
                    yield {"type": "progress", "completed": completed, "total_questions": total_questions}
                continue

            if ok_only_mode:
                item_doc_ids: set[str] = set()
                item_failed = False
                shared_retrieval_cache: Dict[str, tuple] = {}
                last_best_question: Optional[QuestionItem] = None

                for question_index in range(1, item.n_questions + 1):
                    latency_tracker.begin_question()
                    question: Optional[QuestionItem] = None
                    normalized_stem = ""
                    local_attempt_stems: List[str] = []
                    ok_round = 0

                    while True:
                        ok_round += 1
                        if ok_only_deadline is not None and time.perf_counter() > ok_only_deadline:
                            break
                        for dedup_attempt in range(1, _MAX_DEDUP_ATTEMPTS + 1):
                            avoid_stems = used_stems + run_used_stems + local_attempt_stems
                            question, attempt_logs = _generate_single_question(
                                item, retriever, llm_client, reviewer_client, cross_cove_reviewer,
                                avoid_stems, item_doc_ids, retrieval_cache=shared_retrieval_cache,
                            )
                            _record_latency_for_logs(attempt_logs)
                            for log in attempt_logs:
                                log["question_index"] = question_index
                                log["dedup_attempt"] = dedup_attempt
                                log["ok_round"] = ok_round
                                item_attempts.append(log)
                            if question.stem:
                                local_attempt_stems.append(question.stem)
                            normalized_stem = _normalize_stem(question.stem or "")
                            if normalized_stem and normalized_stem in run_used_normalized:
                                LOGGER.info(
                                    "\nDedup hit (ok_only): topic=%s competency=%s round=%s dedup_attempt=%s stem=%s",
                                    item.topic, item.competency, ok_round, dedup_attempt,
                                    _truncate_log(question.stem or ""),
                                )
                                vm = dict(question.meta.verification or {})
                                vm.setdefault("error", "duplicate_question")
                                vm["duplicate"] = True
                                vm["dedup_attempt"] = dedup_attempt
                                question.meta.verification = vm
                                question.status = "FAILED_VERIFICATION"
                                if dedup_attempt < _MAX_DEDUP_ATTEMPTS:
                                    continue
                            break
                        if question is None:
                            break
                        if question.stem:
                            last_best_question = question
                        if question.status == "OK":
                            break
                        time_exceeded = ok_only_deadline is not None and time.perf_counter() > ok_only_deadline
                        if ok_round < ok_only_max_rounds and not time_exceeded:
                            latency_tracker.record_retry(reason="Cross-CoVe verification")
                            continue
                        break

                    if question is None or question.status != "OK":
                        fallback_question = None
                        if settings.QUESTION_BANK_FALLBACK:
                            avoid_normalized = set(run_used_normalized)
                            avoid_normalized.update(_normalize_stem(s) for s in used_stems if s)
                            fallback_question = _select_bank_question(
                                bank_questions, item.topic, item.competency,
                                avoid_normalized, settings.QUESTION_BANK_ALLOW_ANY_TOPIC,
                            )
                        if fallback_question is not None:
                            question = fallback_question
                            normalized_stem = _normalize_stem(question.stem or "")
                        elif question is not None and question.stem:
                            LOGGER.warning(
                                "Graceful fallback: using best-effort question for topic=%s competency=%s (original status=%s)",
                                item.topic, item.competency, question.status,
                            )
                            vm = dict(question.meta.verification or {})
                            vm["graceful_fallback"] = True
                            vm["original_status"] = question.status
                            question.meta.verification = vm
                            question.status = "OK"
                            normalized_stem = _normalize_stem(question.stem or "")
                            _reattach_evidence_from_cache(question, shared_retrieval_cache)
                        elif last_best_question is not None and last_best_question.stem:
                            question = last_best_question
                            LOGGER.warning(
                                "Graceful fallback (from last_best): using best-effort question for topic=%s competency=%s (original status=%s)",
                                item.topic, item.competency, question.status,
                            )
                            vm = dict(question.meta.verification or {})
                            vm["graceful_fallback"] = True
                            vm["original_status"] = question.status
                            question.meta.verification = vm
                            question.status = "OK"
                            normalized_stem = _normalize_stem(question.stem or "")
                            _reattach_evidence_from_cache(question, shared_retrieval_cache)
                        else:
                            LOGGER.error(
                                "generation_failed: OK-only attempts exhausted for topic=%s competency=%s",
                                item.topic, item.competency,
                            )
                            item_failed = True
                            for _ in range(item.n_questions - question_index + 1):
                                fq = _build_failure_question(item, "FAILED_VERIFICATION", _GENERIC_FAILURE_MESSAGE)
                                item_outputs.append(fq.model_dump())
                                item_reports.append(fq.meta.verification.get("gate"))
                            yield {"type": "error", "item_index": item_index, "message": _GENERIC_FAILURE_MESSAGE}
                            break

                    q_hash = _exact_question_hash(question)
                    if q_hash in run_used_hashes:
                        LOGGER.warning(
                            "\nExact duplicate suppressed: topic=%s competency=%s stem=%s",
                            item.topic, item.competency, _truncate_log(question.stem or ""),
                        )
                        question.status = "FAILED_VERIFICATION"
                        vm = dict(question.meta.verification or {})
                        vm["error"] = "duplicate_exact"
                        vm["duplicate"] = True
                        question.meta.verification = vm
                    else:
                        run_used_hashes.add(q_hash)

                    item_outputs.append(question.model_dump())
                    item_reports.append(question.meta.verification.get("gate"))
                    if question.stem and normalized_stem:
                        used_stems.append(question.stem)
                        run_used_stems.append(question.stem)
                        run_used_normalized.add(normalized_stem)
                    if (
                        question.status == "OK"
                        and settings.QUESTION_BANK_WRITE_OK
                        and normalized_stem
                        and normalized_stem not in bank_normalized
                    ):
                        append_question_bank(settings.QUESTION_BANK_PATH, question)
                        bank_questions.append(question)
                        bank_normalized.add(normalized_stem)

                    latency_tracker.finish_question(
                        topic=item.topic, competency=item.competency, status=question.status,
                    )
                    completed += 1
                    event = _build_question_event(question, item_index, question_index)
                    if event is not None:
                        yield event
                    yield {"type": "progress", "completed": completed, "total_questions": total_questions}

                if item_failed:
                    continue
                if item_doc_ids:
                    run_used_doc_ids.update(item_doc_ids)
                continue

            for question_index in range(1, item.n_questions + 1):
                latency_tracker.begin_question()
                question = None
                normalized_stem = ""
                for dedup_attempt in range(1, _MAX_DEDUP_ATTEMPTS + 1):
                    avoid_stems = used_stems + run_used_stems
                    question, attempt_logs = _generate_single_question(
                        item, retriever, llm_client, reviewer_client, cross_cove_reviewer,
                        avoid_stems, run_used_doc_ids,
                    )
                    _record_latency_for_logs(attempt_logs)
                    for log in attempt_logs:
                        log["question_index"] = question_index
                        log["dedup_attempt"] = dedup_attempt
                        item_attempts.append(log)
                    normalized_stem = _normalize_stem(question.stem or "")
                    if normalized_stem and normalized_stem in run_used_normalized:
                        LOGGER.info(
                            "\nDedup hit: topic=%s competency=%s dedup_attempt=%s stem=%s",
                            item.topic, item.competency, dedup_attempt,
                            _truncate_log(question.stem or ""),
                        )
                        vm = dict(question.meta.verification or {})
                        vm.setdefault("error", "duplicate_question")
                        vm["duplicate"] = True
                        vm["dedup_attempt"] = dedup_attempt
                        question.meta.verification = vm
                        question.status = "FAILED_VERIFICATION"
                        if dedup_attempt < _MAX_DEDUP_ATTEMPTS:
                            continue
                    break

                if question is None:
                    question = _build_failure_question(item, "FAILED_VERIFICATION", "pipeline_error")
                    normalized_stem = ""

                item_outputs.append(question.model_dump())
                item_reports.append(question.meta.verification.get("gate"))
                if question.stem and normalized_stem not in run_used_normalized:
                    used_stems.append(question.stem)
                    run_used_stems.append(question.stem)
                    run_used_normalized.add(normalized_stem)
                latency_tracker.finish_question(
                    topic=item.topic, competency=item.competency, status=question.status,
                )
                completed += 1
                event = _build_question_event(question, item_index, question_index)
                if event is not None:
                    yield event
                yield {"type": "progress", "completed": completed, "total_questions": total_questions}
                if (
                    question.status == "OK"
                    and settings.QUESTION_BANK_WRITE_OK
                    and normalized_stem
                    and normalized_stem not in bank_normalized
                ):
                    append_question_bank(settings.QUESTION_BANK_PATH, question)
                    bank_questions.append(question)
                    bank_normalized.add(normalized_stem)

        except ValueError as exc:
            LOGGER.warning("pipeline validation error: %s", exc)
            msg = _GENERIC_FAILURE_MESSAGE if ok_only_mode else str(exc)
            yield {"type": "error", "item_index": item_index, "message": msg}
            for question_index, question in enumerate(
                build_failure_batch([item], str(exc), status="FAILED_VERIFICATION"), start=1
            ):
                item_outputs.append(question.model_dump())
                item_reports.append(question.meta.verification.get("gate"))
                if not ok_only_mode:
                    completed += 1
                    event = _build_question_event(question, item_index, question_index)
                    if event is not None:
                        yield event
                    yield {"type": "progress", "completed": completed, "total_questions": total_questions}
        except Exception as exc:
            LOGGER.exception("pipeline error: %s", exc)
            msg = _GENERIC_FAILURE_MESSAGE if ok_only_mode else f"pipeline_error: {exc}"
            yield {"type": "error", "item_index": item_index, "message": msg}
            for question_index, question in enumerate(
                build_failure_batch([item], f"pipeline_error: {exc}", status="FAILED_VERIFICATION"), start=1
            ):
                item_outputs.append(question.model_dump())
                item_reports.append(question.meta.verification.get("gate"))
                if not ok_only_mode:
                    completed += 1
                    event = _build_question_event(question, item_index, question_index)
                    if event is not None:
                        yield event
                    yield {"type": "progress", "completed": completed, "total_questions": total_questions}
        finally:
            run_log_items.append({
                "input": item.model_dump(),
                "attempts": item_attempts,
                "outputs": item_outputs,
                "verification_reports": item_reports,
            })

    try:
        latency_tracker.finalize()
    except Exception as exc:
        LOGGER.warning("Failed to finalize latency tracker: %s", exc)

    run_record = {
        "run_id": run_id,
        "timestamp": run_timestamp,
        "input_batch": input_batch,
        "items": run_log_items,
        "runtime_ms": (time.perf_counter() - run_started) * 1000.0,
    }
    summary: Optional[Dict[str, object]] = None
    try:
        summary = log_run(run_record)
    except Exception as exc:
        LOGGER.warning("Failed to log run: %s", exc)

    yield {
        "type": "done",
        "run_id": run_id,
        "completed": completed,
        "total_questions": total_questions,
        "summary": None if ok_only_mode else summary,
    }
    LOGGER.info(
        "\nRun done: run_id=%s completed=%s total=%s runtime_ms=%.1f",
        run_id, completed, total_questions,
        (time.perf_counter() - run_started) * 1000.0,
    )


def run_pipeline_batch(payload: List[GenerateRequestItem]) -> List[QuestionItem]:
    results: List[QuestionItem] = []
    saw_error = False
    for event in run_pipeline_stream(payload):
        if event.get("type") == "question":
            results.append(QuestionItem.model_validate(event["question"]))
        if event.get("type") == "error" and settings.OK_ONLY_MODE:
            saw_error = True
    if saw_error and settings.OK_ONLY_MODE:
        return []
    return results
