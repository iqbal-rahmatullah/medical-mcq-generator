from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class GenerateRequestItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    kb_id: str = Field(..., min_length=1)
    topic: str = Field(..., min_length=1, alias="keyword")
    competency: str = ""
    n_questions: int = Field(3, ge=1, le=100)
    language: str = Field("both", pattern="^(en|id|both)$")
