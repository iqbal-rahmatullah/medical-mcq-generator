import asyncio
import logging
from typing import List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import TypeAdapter, ValidationError

from app.logging.logger import get_latest_run_record, get_latest_run_summary
from app.core.config import settings
from app.eval.nli_eval import evaluate_question_bank_nli
from app.eval.rouge_eval import evaluate_question_bank
from app.eval.semantic_eval import evaluate_question_bank_semantic
from app.schemas.request import GenerateRequestItem
from app.schemas.response import HealthResponse, QuestionItem
from app.services.pipeline import build_failure_batch, run_pipeline_batch, run_pipeline_stream

router = APIRouter()
LOGGER = logging.getLogger(__name__)

_QUEUE_SENTINEL = object() 


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

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def _run_generator() -> None:
        try:
            for event in run_pipeline_stream(payload, include_failed=False):
                loop.call_soon_threadsafe(queue.put_nowait, event)
        except Exception as exc:
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {"type": "error", "message": f"pipeline_error: {exc}"},
            )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _QUEUE_SENTINEL)

    try:
        future = loop.run_in_executor(None, _run_generator)
        while True:
            event = await queue.get()
            if event is _QUEUE_SENTINEL:
                break
            try:
                await websocket.send_json(event)
            except WebSocketDisconnect:
                future.cancel()
                return
        await future  # propagate any unexpected executor exception
    except WebSocketDisconnect:
        return
    except Exception as exc:
        LOGGER.exception("WebSocket pipeline error: %s", exc)
        try:
            await websocket.send_json({"type": "error", "message": f"pipeline_error: {exc}"})
        except Exception:
            pass
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
        "avg_rouge_f1": (result.avg_rouge1_f1 + result.avg_rougeL_f1) / 2,
        "categories": result.categories,
        "items": result.items,
        "filter_category": category,
        "rubric": {
            "strong": "ROUGE-L >= 0.30",
            "moderate": "0.20 <= ROUGE-L < 0.30",
            "weak": "0.10 <= ROUGE-L < 0.20",
            "very_weak": "ROUGE-L < 0.10",
        },
        "notes": "ROUGE scores computed on stem + correct answer vs evidence span_text.",
    }


@router.get("/eval/nli")
def nli_eval(limit: int = 0, include_items: bool = False) -> dict:
    result = evaluate_question_bank_nli(
        settings.QUESTION_BANK_PATH,
        model_name=settings.NLI_MODEL,
        limit=limit,
        include_items=include_items,
    )
    return {
        "model": settings.NLI_MODEL,
        "total_seen": result.total_seen,
        "scored": result.scored,
        "skipped_status": result.skipped_status,
        "skipped_no_evidence": result.skipped_no_evidence,
        "avg_entailment": result.avg_entailment,
        "label_counts": result.label_counts,
        "items": result.items,
        "notes": "NLI scores computed with evidence as premise and stem+answer as hypothesis.",
    }


@router.get("/eval/semantic")
def semantic_eval(
    limit: int = 0,
    include_items: bool = False,
    category: str | None = None,
) -> dict:
    result = evaluate_question_bank_semantic(
        settings.QUESTION_BANK_PATH,
        model_name=settings.SEMANTIC_MODEL,
        limit=limit,
        include_items=include_items,
        filter_category=category,
    )
    return {
        "model": settings.SEMANTIC_MODEL,
        "total_seen": result.total_seen,
        "scored": result.scored,
        "skipped_status": result.skipped_status,
        "skipped_no_evidence": result.skipped_no_evidence,
        "avg_cosine_similarity": result.avg_cosine,
        "categories": result.categories,
        "items": result.items,
        "filter_category": category,
        "rubric": {
            "strong": "cosine >= 0.70",
            "moderate": "0.50 <= cosine < 0.70",
            "weak": "0.30 <= cosine < 0.50",
            "very_weak": "cosine < 0.30",
        },
        "notes": "Semantic similarity computed on stem + correct answer vs evidence span_text.",
    }
