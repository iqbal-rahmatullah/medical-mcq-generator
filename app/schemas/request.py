from __future__ import annotations

from pydantic import BaseModel, Field


class GenerateRequestItem(BaseModel):
    topic: str = Field(..., min_length=1)
    competency: str = Field(..., min_length=1)
    n_questions: int = Field(3, ge=1, le=100)
