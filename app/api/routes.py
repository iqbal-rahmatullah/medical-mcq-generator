from __future__ import annotations

from typing import List

from fastapi import APIRouter

from app.schemas.request import GenerateRequestItem
from app.schemas.response import HealthResponse, QuestionItem
from app.services.pipeline import build_failure_batch, run_pipeline_batch

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok")


@router.post("/generate", response_model=List[QuestionItem])
def generate_questions(payload: List[GenerateRequestItem]) -> List[QuestionItem]:
    # Contoh curl:
    # curl -X POST http://localhost:8000/generate \
    #   -H "Content-Type: application/json" \
    #   -d '[{"topic":"Diabetes","competency":"Diagnosis","n_questions":2}]'
    try:
        return run_pipeline_batch(payload)
    except Exception as exc:
        return build_failure_batch(payload, f"unhandled_error: {exc}")
