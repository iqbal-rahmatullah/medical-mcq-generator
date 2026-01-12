from __future__ import annotations

import copy
import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

_LOG_PATH = Path("app/logging/runs.jsonl")
_LOCK = threading.Lock()
_LATEST_RUN_SUMMARY: Optional[Dict[str, Any]] = None
_LATEST_RUN_RECORD: Optional[Dict[str, Any]] = None


def _build_summary(record: Dict[str, Any]) -> Dict[str, Any]:
    status_counts = {
        "OK": 0,
        "INSUFFICIENT_EVIDENCE": 0,
        "FAILED_VERIFICATION": 0,
    }
    total_questions = 0
    for item in record.get("items", []):
        for output in item.get("outputs", []):
            status = output.get("status")
            if status in status_counts:
                status_counts[status] += 1
            total_questions += 1

    return {
        "run_id": record.get("run_id"),
        "timestamp": record.get("timestamp"),
        "total_items": len(record.get("items", [])),
        "total_questions": total_questions,
        "status_counts": status_counts,
        "runtime_ms": record.get("runtime_ms", 0.0),
    }


def log_run(record: Dict[str, Any]) -> Dict[str, Any]:
    if "timestamp" not in record:
        record = dict(record)
        record["timestamp"] = time.time()

    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")

    summary = _build_summary(record)
    with _LOCK:
        global _LATEST_RUN_SUMMARY, _LATEST_RUN_RECORD
        _LATEST_RUN_SUMMARY = summary
        _LATEST_RUN_RECORD = copy.deepcopy(record)

    return summary


def get_latest_run_summary() -> Optional[Dict[str, Any]]:
    with _LOCK:
        if _LATEST_RUN_SUMMARY is None:
            return None
        return dict(_LATEST_RUN_SUMMARY)


def get_latest_run_record() -> Optional[Dict[str, Any]]:
    with _LOCK:
        if _LATEST_RUN_RECORD is None:
            return None
        return copy.deepcopy(_LATEST_RUN_RECORD)
