from __future__ import annotations

from typing import List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import TypeAdapter, ValidationError

from app.logging.logger import get_latest_run_record, get_latest_run_summary
from app.core.config import settings
from app.eval.rouge_eval import evaluate_question_bank
from app.schemas.request import GenerateRequestItem
from app.schemas.response import HealthResponse, QuestionItem
from app.services.pipeline import build_failure_batch, run_pipeline_batch, run_pipeline_stream

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok")


@router.post("/generate", response_model=List[QuestionItem])
def generate_questions(payload: List[GenerateRequestItem]) -> List[QuestionItem]:
    try:
        return run_pipeline_batch(payload)
    except Exception as exc:
        return build_failure_batch(payload, f"unhandled_error: {exc}")


@router.websocket("/ws/generate")
async def generate_questions_ws(websocket: WebSocket) -> None:
    await websocket.accept()

    try:
        data = await websocket.receive_json()
        adapter = TypeAdapter(List[GenerateRequestItem])
        payload = adapter.validate_python(data)
    except ValidationError as exc:
        await websocket.send_json(
            {"type": "error", "message": "validation_error", "details": exc.errors()}
        )
        await websocket.close(code=1003)
        return
    except Exception as exc:
        await websocket.send_json(
            {"type": "error", "message": f"invalid_payload: {exc}"}
        )
        await websocket.close(code=1003)
        return

    try:
        for event in run_pipeline_stream(payload, include_failed=False):
            await websocket.send_json(event)
    except WebSocketDisconnect:
        return
    except Exception as exc:
        await websocket.send_json({"type": "error", "message": f"pipeline_error: {exc}"})
    finally:
        try:
            await websocket.close()
        except RuntimeError:
            pass


@router.get("/runs/latest")
def latest_run() -> dict:
    summary = get_latest_run_summary()
    record = get_latest_run_record()
    if summary is None and record is None:
        return {"status": "empty"}
    return {"summary": summary, "record": record}


@router.get("/eval/rouge")
def rouge_eval(
    limit: int = 0,
    include_items: bool = False,
    category: str | None = None,
) -> dict:
    result = evaluate_question_bank(
        settings.QUESTION_BANK_PATH,
        limit=limit,
        include_items=include_items,
        filter_category=category,
    )
    return {
        "total_seen": result.total_seen,
        "scored": result.scored,
        "skipped_status": result.skipped_status,
        "skipped_no_evidence": result.skipped_no_evidence,
        "avg_rouge1_f1": result.avg_rouge1_f1,
        "avg_rougeL_f1": result.avg_rougeL_f1,
        "categories": result.categories,
        "items": result.items,
        "filter_category": category,
        "rubric": {
            "strong": "ROUGE-L >= 0.30",
            "moderate": "0.20 <= ROUGE-L < 0.30",
            "weak": "0.10 <= ROUGE-L < 0.20",
            "very_weak": "ROUGE-L < 0.10",
        },
        "notes": "ROUGE scores computed on stem + correct answer vs evidence span_text (F1 variant).",
    }
