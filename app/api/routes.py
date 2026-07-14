import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, TypeAdapter, ValidationError

from app.logging.logger import get_latest_run_record, get_latest_run_summary
from app.core.config import settings
from app.eval.nli_eval import evaluate_question_bank_nli
from app.eval.rouge_eval import evaluate_question_bank
from app.eval.semantic_eval import evaluate_question_bank_semantic
from app.ingestion import knowledge_store as kb_store
from app.ingestion.ingest_worker import ingest_kb
from app.schemas.request import GenerateRequestItem
from app.schemas.response import HealthResponse, QuestionItem
from app.services.pipeline import build_failure_batch, run_pipeline_batch, run_pipeline_stream

router = APIRouter()
LOGGER = logging.getLogger(__name__)

_QUEUE_SENTINEL = object()
_UPLOAD_CHUNK_SIZE = 1024 * 1024


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok")


async def _save_upload(dest_dir, upload: UploadFile) -> None:
    dest = dest_dir / upload.filename
    with dest.open("wb") as out:
        while chunk := await upload.read(_UPLOAD_CHUNK_SIZE):
            out.write(chunk)


@router.post("/knowledge")
async def create_knowledge(
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    files: List[UploadFile] = File(...),
) -> dict:
    title = title.strip()
    if not title:
        raise HTTPException(400, "title_required")
    files = [f for f in files if f.filename]
    if not files:
        raise HTTPException(400, "files_required")
    if kb_store.title_exists(title):
        raise HTTPException(409, "title_already_exists")

    manifest = kb_store.create_kb(title, [f.filename for f in files])
    kb_id = manifest["id"]
    raw_dir = kb_store.raw_dir(kb_id)
    for upload in files:
        await _save_upload(raw_dir, upload)

    background_tasks.add_task(ingest_kb, kb_id)
    return manifest


@router.get("/knowledge")
def list_knowledge() -> List[dict]:
    return kb_store.list_kbs()


@router.get("/knowledge/{kb_id}")
def get_knowledge(kb_id: str) -> dict:
    manifest = kb_store.get_kb(kb_id)
    if manifest is None:
        raise HTTPException(404, "not_found")
    return manifest


@router.get("/knowledge/{kb_id}/keywords")
def knowledge_keywords(kb_id: str, limit: int = 20) -> dict:
    if kb_store.get_kb(kb_id) is None:
        raise HTTPException(404, "not_found")
    return {"keywords": kb_store.keyword_stats(kb_id, limit=max(1, min(limit, 100)))}


class RenameKnowledgeRequest(BaseModel):
    title: str


@router.patch("/knowledge/{kb_id}")
def rename_knowledge(kb_id: str, payload: RenameKnowledgeRequest) -> dict:
    title = payload.title.strip()
    if not title:
        raise HTTPException(400, "title_required")
    if kb_store.get_kb(kb_id) is None:
        raise HTTPException(404, "not_found")
    if kb_store.title_exists(title, exclude_kb_id=kb_id):
        raise HTTPException(409, "title_already_exists")
    return kb_store.rename_kb(kb_id, title)


@router.post("/knowledge/{kb_id}/files")
async def add_knowledge_files(
    kb_id: str,
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
) -> dict:
    if kb_store.get_kb(kb_id) is None:
        raise HTTPException(404, "not_found")
    files = [f for f in files if f.filename]
    if not files:
        raise HTTPException(400, "files_required")

    raw_dir = kb_store.raw_dir(kb_id)
    for upload in files:
        await _save_upload(raw_dir, upload)

    manifest = kb_store.add_files(kb_id)
    background_tasks.add_task(ingest_kb, kb_id)
    return manifest


@router.delete("/knowledge/{kb_id}/files/{filename}")
def remove_knowledge_file(kb_id: str, filename: str, background_tasks: BackgroundTasks) -> dict:
    if kb_store.get_kb(kb_id) is None:
        raise HTTPException(404, "not_found")
    manifest = kb_store.remove_file(kb_id, filename)
    background_tasks.add_task(ingest_kb, kb_id)
    return manifest


@router.delete("/knowledge/{kb_id}")
def delete_knowledge(kb_id: str) -> dict:
    kb_store.delete_kb(kb_id)
    return {"status": "deleted"}


def _kb_not_ready_message(payload: List[GenerateRequestItem]) -> Optional[str]:
    for kb_id in {item.kb_id for item in payload}:
        manifest = kb_store.get_kb(kb_id)
        if manifest is None:
            return f"knowledge_not_found: {kb_id}"
        if manifest.get("status") != "ready":
            return f"knowledge_not_ready: {kb_id} (status={manifest.get('status')})"
    return None


@router.post("/generate", response_model=List[QuestionItem])
def generate_questions(payload: List[GenerateRequestItem]) -> List[QuestionItem]:
    not_ready = _kb_not_ready_message(payload)
    if not_ready:
        raise HTTPException(409, not_ready)
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

    not_ready = _kb_not_ready_message(payload)
    if not_ready:
        await websocket.send_json({"type": "error", "message": not_ready})
        await websocket.close(code=1008)
        return

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()
    start_time = time.perf_counter()
    start_dt = datetime.now(timezone.utc)
    total_requested = sum(item.n_questions for item in payload)
    LOGGER.info(
        "WS generate START: topics=%d questions=%d start=%s",
        len(payload),
        total_requested,
        start_dt.strftime("%Y-%m-%dT%H:%M:%S UTC"),
    )

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
        elapsed = time.perf_counter() - start_time
        end_dt = datetime.now(timezone.utc)
        LOGGER.info(
            "WS generate END: topics=%d questions=%d start=%s end=%s elapsed=%.2fs",
            len(payload),
            total_requested,
            start_dt.strftime("%Y-%m-%dT%H:%M:%S UTC"),
            end_dt.strftime("%Y-%m-%dT%H:%M:%S UTC"),
            elapsed,
        )
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
