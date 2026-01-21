from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import List

from app.schemas.response import QuestionItem

_BANK_LOCK = threading.Lock()


def load_question_bank(path: str) -> List[QuestionItem]:
    bank_path = Path(path)
    if not bank_path.exists():
        return []

    questions: List[QuestionItem] = []
    with bank_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                question = QuestionItem.model_validate(data)
            except Exception:
                continue
            if question.status != "OK":
                continue
            questions.append(question)
    return questions


def append_question_bank(path: str, question: QuestionItem) -> None:
    if question.status != "OK":
        return

    bank_path = Path(path)
    bank_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(question.model_dump(), ensure_ascii=True)
    with _BANK_LOCK:
        with bank_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
