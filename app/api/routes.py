from __future__ import annotations

from typing import List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import TypeAdapter, ValidationError

from app.logging.logger import get_latest_run_record, get_latest_run_summary
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
        for event in run_pipeline_stream(payload):
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
