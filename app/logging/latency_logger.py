"""Latency & throughput logger for question generation pipeline.

Produces two outputs per run:
  1. app/logging/latency_log.jsonl  – append-only machine-readable log
  2. app/logging/latency_<run_id>.csv – per-run CSV ready for Tabel 4.11 / 4.12

Each question record includes:
  - question_number (global within the run)
  - topic, competency
  - retrieval_ms, llm_ms, verification_ms, total_ms
  - attempts (how many pipeline attempts were needed)
  - retry_triggered (bool – True if Cross-CoVe verification caused a retry)
  - status (OK / FAILED_VERIFICATION / INSUFFICIENT_EVIDENCE)
"""

from __future__ import annotations

import csv
import json
import logging
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

LOGGER = logging.getLogger(__name__)

_LATENCY_JSONL_PATH = Path("app/logging/latency_log.jsonl")
_LATENCY_CSV_DIR = Path("app/logging")
_LOCK = threading.Lock()


@dataclass
class QuestionLatency:
    """Latency record for a single question."""
    question_number: int
    topic: str
    competency: str
    retrieval_ms: float = 0.0
    llm_ms: float = 0.0
    verification_ms: float = 0.0
    total_ms: float = 0.0
    attempts: int = 1
    retry_triggered: bool = False
    retry_reason: str = ""
    status: str = "OK"


@dataclass
class BatchLatency:
    """Latency record for an entire batch run."""
    run_id: str
    timestamp: str
    total_questions: int = 0
    successful_questions: int = 0
    failed_questions: int = 0
    total_runtime_ms: float = 0.0
    avg_question_ms: float = 0.0
    throughput_qps: float = 0.0  # questions per second
    avg_retrieval_ms: float = 0.0
    avg_llm_ms: float = 0.0
    avg_verification_ms: float = 0.0
    retrieval_pct: float = 0.0   # percentage of total time
    llm_pct: float = 0.0
    verification_pct: float = 0.0
    questions: List[QuestionLatency] = field(default_factory=list)


class LatencyTracker:
    """Accumulates per-question latency data during a pipeline run."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.timestamp = datetime.utcnow().isoformat() + "Z"
        self._records: List[QuestionLatency] = []
        self._run_start: float = time.perf_counter()
        self._question_counter = 0
        self._current_question_start: Optional[float] = None
        self._current_retrieval_ms: float = 0.0
        self._current_llm_ms: float = 0.0
        self._current_verification_ms: float = 0.0
        self._current_attempts: int = 0
        self._current_retry_triggered: bool = False
        self._current_retry_reason: str = ""

    def begin_question(self) -> None:
        """Call when starting generation of a new question."""
        self._current_question_start = time.perf_counter()
        self._current_retrieval_ms = 0.0
        self._current_llm_ms = 0.0
        self._current_verification_ms = 0.0
        self._current_attempts = 0
        self._current_retry_triggered = False
        self._current_retry_reason = ""

    def record_attempt(
        self,
        retrieval_ms: float,
        llm_ms: float,
        verification_ms: float,
    ) -> None:
        """Call after each attempt (including retries)."""
        self._current_attempts += 1
        self._current_retrieval_ms += retrieval_ms
        self._current_llm_ms += llm_ms
        self._current_verification_ms += verification_ms

    def record_retry(self, reason: str = "Cross-CoVe verification") -> None:
        """Call when a retry is triggered by verification failure."""
        self._current_retry_triggered = True
        self._current_retry_reason = reason

    def finish_question(
        self,
        topic: str,
        competency: str,
        status: str,
    ) -> QuestionLatency:
        """Call when a question is finalized. Returns the latency record."""
        self._question_counter += 1
        total_ms = (
            (time.perf_counter() - self._current_question_start) * 1000.0
            if self._current_question_start is not None
            else self._current_retrieval_ms + self._current_llm_ms + self._current_verification_ms
        )

        record = QuestionLatency(
            question_number=self._question_counter,
            topic=topic,
            competency=competency,
            retrieval_ms=round(self._current_retrieval_ms, 1),
            llm_ms=round(self._current_llm_ms, 1),
            verification_ms=round(self._current_verification_ms, 1),
            total_ms=round(total_ms, 1),
            attempts=self._current_attempts,
            retry_triggered=self._current_retry_triggered,
            retry_reason=self._current_retry_reason,
            status=status,
        )
        self._records.append(record)

        total_sec = total_ms / 1000.0
        if self._current_retry_triggered:
            LOGGER.info(
                "Question %d retry triggered by %s",
                self._question_counter,
                self._current_retry_reason or "Cross-CoVe verification",
            )
        LOGGER.info(
            "Question %d generated in %.1fs (retrieval=%.1fs, llm=%.1fs, verification=%.1fs) [%s]",
            self._question_counter,
            total_sec,
            self._current_retrieval_ms / 1000.0,
            self._current_llm_ms / 1000.0,
            self._current_verification_ms / 1000.0,
            status,
        )

        return record

    def finalize(self) -> BatchLatency:
        """Call at end of run. Computes summary stats and writes to disk."""
        total_runtime_ms = (time.perf_counter() - self._run_start) * 1000.0
        total_q = len(self._records)
        ok_count = sum(1 for r in self._records if r.status == "OK")
        failed_count = total_q - ok_count

        sum_retrieval = sum(r.retrieval_ms for r in self._records)
        sum_llm = sum(r.llm_ms for r in self._records)
        sum_verification = sum(r.verification_ms for r in self._records)
        sum_phases = sum_retrieval + sum_llm + sum_verification

        batch = BatchLatency(
            run_id=self.run_id,
            timestamp=self.timestamp,
            total_questions=total_q,
            successful_questions=ok_count,
            failed_questions=failed_count,
            total_runtime_ms=round(total_runtime_ms, 1),
            avg_question_ms=round(total_runtime_ms / max(total_q, 1), 1),
            throughput_qps=round(total_q / max(total_runtime_ms / 1000.0, 0.001), 3),
            avg_retrieval_ms=round(sum_retrieval / max(total_q, 1), 1),
            avg_llm_ms=round(sum_llm / max(total_q, 1), 1),
            avg_verification_ms=round(sum_verification / max(total_q, 1), 1),
            retrieval_pct=round(sum_retrieval / max(sum_phases, 1) * 100, 1),
            llm_pct=round(sum_llm / max(sum_phases, 1) * 100, 1),
            verification_pct=round(sum_verification / max(sum_phases, 1) * 100, 1),
            questions=list(self._records),
        )

        # Console summary
        LOGGER.info(
            "Batch completed: %d questions generated successfully, %d failed (%.1fs total, %.3f q/s)",
            ok_count,
            failed_count,
            total_runtime_ms / 1000.0,
            batch.throughput_qps,
        )
        LOGGER.info(
            "Avg per question: retrieval=%.1fms (%.1f%%), llm=%.1fms (%.1f%%), verification=%.1fms (%.1f%%)",
            batch.avg_retrieval_ms,
            batch.retrieval_pct,
            batch.avg_llm_ms,
            batch.llm_pct,
            batch.avg_verification_ms,
            batch.verification_pct,
        )

        # Write to disk
        _write_jsonl(batch)
        _write_csv(batch)

        return batch


def _write_jsonl(batch: BatchLatency) -> None:
    """Append batch record to latency_log.jsonl."""
    try:
        _LATENCY_JSONL_PATH.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "run_id": batch.run_id,
            "timestamp": batch.timestamp,
            "total_questions": batch.total_questions,
            "successful_questions": batch.successful_questions,
            "failed_questions": batch.failed_questions,
            "total_runtime_ms": batch.total_runtime_ms,
            "avg_question_ms": batch.avg_question_ms,
            "throughput_qps": batch.throughput_qps,
            "phase_averages": {
                "retrieval_ms": batch.avg_retrieval_ms,
                "llm_ms": batch.avg_llm_ms,
                "verification_ms": batch.avg_verification_ms,
            },
            "phase_percentages": {
                "retrieval_pct": batch.retrieval_pct,
                "llm_pct": batch.llm_pct,
                "verification_pct": batch.verification_pct,
            },
            "questions": [asdict(q) for q in batch.questions],
        }
        with _LOCK:
            with _LATENCY_JSONL_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        LOGGER.info("Latency log written to %s", _LATENCY_JSONL_PATH)
    except Exception as exc:
        LOGGER.warning("Failed to write latency JSONL: %s", exc)


def _write_csv(batch: BatchLatency) -> None:
    """Write per-run CSV file for direct use in thesis tables."""
    try:
        _LATENCY_CSV_DIR.mkdir(parents=True, exist_ok=True)
        csv_path = _LATENCY_CSV_DIR / f"latency_{batch.run_id}.csv"

        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)

            writer.writerow(["=== Per-Question Latency (Tabel 4.12) ==="])
            writer.writerow([
                "Soal ke-",
                "Waktu (s)",
                "Retrieval (s)",
                "LLM (s)",
                "Verification (s)",
                "Attempts",
                "Retry Triggered",
                "Retry Reason",
                "Status",
            ])
            for q in batch.questions:
                writer.writerow([
                    q.question_number,
                    f"{q.total_ms / 1000.0:.1f}",
                    f"{q.retrieval_ms / 1000.0:.1f}",
                    f"{q.llm_ms / 1000.0:.1f}",
                    f"{q.verification_ms / 1000.0:.1f}",
                    q.attempts,
                    "Yes" if q.retry_triggered else "No",
                    q.retry_reason,
                    q.status,
                ])

            writer.writerow([])

            writer.writerow(["=== Phase Distribution Summary (Tabel 4.11) ==="])
            writer.writerow([
                "No",
                "Fase / Modul Pipeline",
                "Rata-rata Waktu Eksekusi (s)",
                "Persentase Beban Waktu (%)",
            ])
            writer.writerow([
                1,
                "Prapemrosesan kueri dan hybrid retrieval",
                f"{batch.avg_retrieval_ms / 1000.0:.1f}",
                f"{batch.retrieval_pct:.1f}",
            ])
            writer.writerow([
                2,
                "Generasi draf soal menggunakan LLM",
                f"{batch.avg_llm_ms / 1000.0:.1f}",
                f"{batch.llm_pct:.1f}",
            ])
            writer.writerow([
                3,
                "Verifikasi Cross-CoVe menggunakan 3 model reviewer",
                f"{batch.avg_verification_ms / 1000.0:.1f}",
                f"{batch.verification_pct:.1f}",
            ])

            writer.writerow([])
            writer.writerow(["=== Batch Summary ==="])
            writer.writerow(["Run ID", batch.run_id])
            writer.writerow(["Timestamp", batch.timestamp])
            writer.writerow(["Total Questions", batch.total_questions])
            writer.writerow(["Successful", batch.successful_questions])
            writer.writerow(["Failed", batch.failed_questions])
            writer.writerow(["Total Runtime (s)", f"{batch.total_runtime_ms / 1000.0:.1f}"])
            writer.writerow(["Avg per Question (s)", f"{batch.avg_question_ms / 1000.0:.1f}"])
            writer.writerow(["Throughput (q/s)", f"{batch.throughput_qps:.3f}"])

        LOGGER.info("Latency CSV written to %s", csv_path)
    except Exception as exc:
        LOGGER.warning("Failed to write latency CSV: %s", exc)
