from __future__ import annotations

from typing import Dict, List


_COMPETENCY_EXPANSIONS: Dict[str, List[str]] = {
    "diagnosis": [
        "diagnosis",
        "differential diagnosis",
        "signs",
        "symptoms",
        "screening",
    ],
    "treatment": [
        "treatment",
        "therapy",
        "management",
        "drug",
        "dosage",
    ],
    "therapy": [
        "therapy",
        "treatment",
        "management",
        "drug",
        "dosage",
    ],
    "etiology": [
        "etiology",
        "cause",
        "risk factors",
        "pathogenesis",
    ],
    "prevention": [
        "prevention",
        "prophylaxis",
        "risk reduction",
        "screening",
    ],
    "prognosis": [
        "prognosis",
        "outcomes",
        "mortality",
        "survival",
    ],
}


def build_query(topic: str, competency: str) -> str:
    topic = topic.strip()
    competency = competency.strip()

    terms: List[str] = []
    if topic:
        terms.append(topic)
    if competency:
        terms.append(competency)

    expansions = _COMPETENCY_EXPANSIONS.get(competency.lower(), [])
    for term in expansions:
        if term not in terms:
            terms.append(term)

    return " ".join(terms)
