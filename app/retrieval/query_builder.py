from __future__ import annotations

from typing import List


def build_query(topic: str, competency: str) -> str:
    topic = topic.strip()
    competency = competency.strip()
    terms = [term for term in (topic, competency) if term]
    return " ".join(terms)


_QUERY_VARIATIONS = [
    ["detail", "specific", "overview", "context"],
    ["example", "evidence", "source", "reference"],
    ["definition", "explanation", "summary", "background"],
    ["process", "method", "approach", "technique"],
    ["comparison", "analysis", "cause", "effect"],
]


def build_query_varied(topic: str, competency: str, variation_index: int = 0) -> str:
    base_query = build_query(topic, competency)
    
    idx = variation_index % len(_QUERY_VARIATIONS)
    variation_terms = _QUERY_VARIATIONS[idx]
    
    base_lower = base_query.lower()
    new_terms = [t for t in variation_terms if t.lower() not in base_lower]
    
    if not new_terms:
        return base_query
    
    selected = new_terms[:2]
    return f"{base_query} {' '.join(selected)}"

