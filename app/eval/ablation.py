from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path
from typing import Iterable, List, Tuple

from app.core.config import settings
from app.schemas.request import GenerateRequestItem
from app.schemas.response import QuestionItem
from app.services import pipeline


def _load_payload(path: Path) -> List[GenerateRequestItem]:
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    if raw.startswith("["):
        data = json.loads(raw)
    else:
        data = [json.loads(line) for line in raw.splitlines() if line.strip()]
    return [GenerateRequestItem.model_validate(item) for item in data]


def _reset_retriever_cache() -> None:
    pipeline._RETRIEVER = None
    pipeline._RETRIEVER_ERROR = None


def _is_json_valid(question: QuestionItem) -> bool:
    verification_error = (question.meta.verification or {}).get("error")
    if verification_error == "invalid_json":
        return False
    return question.explanation != "invalid_json"


def _evidence_supported(question: QuestionItem) -> bool:
    gate = (question.meta.verification or {}).get("gate") or {}
    return bool(gate.get("pass"))


def _reviewer_agreed(question: QuestionItem) -> bool:
    gate = (question.meta.verification or {}).get("gate") or {}
    failed_checks = gate.get("failed_checks", []) or []
    return not any(check.startswith("reviewer_") for check in failed_checks)


def _avg_runtime_ms(questions: Iterable[QuestionItem]) -> float:
    timings = []
    for question in questions:
        ms = 0.0
        timings_ms = question.meta.timings_ms or {}
        for key in ("retrieval", "llm", "verification"):
            ms += float(timings_ms.get(key, 0.0))
        timings.append(ms)
    if not timings:
        return 0.0
    return sum(timings) / len(timings)


def _run_mode(
    payload: List[GenerateRequestItem],
    retrieval_mode: str,
    fusion_enabled: bool,
) -> Tuple[List[QuestionItem], float]:
    settings.RETRIEVAL_MODE = retrieval_mode
    settings.FUSION_ENABLED = fusion_enabled
    _reset_retriever_cache()
    start = time.perf_counter()
    results = pipeline.run_pipeline_batch(payload)
    runtime_ms = (time.perf_counter() - start) * 1000.0
    return results, runtime_ms


def _compute_metrics(questions: List[QuestionItem], runtime_ms: float) -> dict:
    total = len(questions)
    if total == 0:
        return {
            "json_valid_rate": 0.0,
            "evidence_support_rate": 0.0,
            "reviewer_agreement_rate": 0.0,
            "avg_runtime_ms": 0.0,
            "runtime_ms": runtime_ms,
        }

    json_valid = sum(1 for q in questions if _is_json_valid(q))
    evidence_supported = sum(1 for q in questions if _evidence_supported(q))
    reviewer_agreed = sum(1 for q in questions if _reviewer_agreed(q))

    return {
        "json_valid_rate": json_valid / total,
        "evidence_support_rate": evidence_supported / total,
        "reviewer_agreement_rate": reviewer_agreed / total,
        "avg_runtime_ms": _avg_runtime_ms(questions),
        "runtime_ms": runtime_ms,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to JSON or JSONL test set.")
    parser.add_argument("--output", required=True, help="Output CSV path.")
    args = parser.parse_args()

    payload = _load_payload(Path(args.input))
    if not payload:
        raise SystemExit("Empty payload")

    bm25_questions, bm25_runtime_ms = _run_mode(payload, "bm25_only", False)
    hybrid_questions, hybrid_runtime_ms = _run_mode(payload, "hybrid_rerank", True)

    bm25_metrics = _compute_metrics(bm25_questions, bm25_runtime_ms)
    hybrid_metrics = _compute_metrics(hybrid_questions, hybrid_runtime_ms)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "mode",
                "json_valid_rate",
                "evidence_support_rate",
                "reviewer_agreement_rate",
                "avg_runtime_ms",
            ],
        )
        writer.writeheader()
        writer.writerow({"mode": "bm25_only", **{k: bm25_metrics[k] for k in writer.fieldnames[1:]}})
        writer.writerow(
            {"mode": "hybrid_bm25_medcpt_rrf", **{k: hybrid_metrics[k] for k in writer.fieldnames[1:]}}
        )


if __name__ == "__main__":
    main()
