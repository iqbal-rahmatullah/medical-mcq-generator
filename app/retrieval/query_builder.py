from __future__ import annotations

from typing import Dict, List


_COMPETENCY_EXPANSIONS: Dict[str, List[str]] = {
    "diagnosis": [
        "diagnosis",
        "differential diagnosis",
        "signs",
        "symptoms",
        "screening",
        "clinical features",
        "presentation",
        "diagnostic criteria",
        "workup",
        "evaluation",
        "diagnostic test",
        "laboratory findings",
        "imaging",
    ],
    "treatment": [
        "treatment",
        "therapy",
        "management",
        "drug",
        "dosage",
        "medication",
        "pharmacotherapy",
        "first-line",
        "second-line",
        "guideline",
        "intervention",
        "acute management",
        "long-term management",
    ],
    "therapy": [
        "therapy",
        "treatment",
        "management",
        "drug",
        "dosage",
        "medication",
        "pharmacotherapy",
        "first-line",
        "second-line",
        "guideline",
        "intervention",
        "acute management",
        "long-term management",
    ],
    "etiology": [
        "etiology",
        "cause",
        "risk factors",
        "pathogenesis",
        "mechanism",
        "underlying cause",
        "genetic factors",
        "environmental factors",
        "predisposing factors",
        "associated conditions",
        "epidemiology",
        "incidence",
    ],
    "prevention": [
        "prevention",
        "prophylaxis",
        "risk reduction",
        "screening",
        "vaccination",
        "primary prevention",
        "secondary prevention",
        "lifestyle modification",
        "counseling",
        "public health",
        "early detection",
        "follow-up",
    ],
    "prognosis": [
        "prognosis",
        "outcomes",
        "mortality",
        "survival",
        "complications",
        "disease course",
        "recurrence",
        "risk stratification",
        "severity",
        "long-term outcomes",
        "quality of life",
        "predictors",
    ],
    "screening": [
        "screening",
        "early detection",
        "risk assessment",
        "screening test",
        "sensitivity",
        "specificity",
        "guideline",
        "population screening",
        "high-risk",
        "preventive care",
        "follow-up",
        "diagnostic threshold",
    ],
    "complications": [
        "complications",
        "adverse outcomes",
        "sequelae",
        "comorbidity",
        "disease progression",
        "risk factors",
        "mortality",
        "morbidity",
        "hospitalization",
        "long-term effects",
        "severity",
        "clinical deterioration",
    ],
    "pathophysiology": [
        "pathophysiology",
        "pathogenesis",
        "mechanism",
        "molecular pathway",
        "cellular response",
        "inflammation",
        "hemodynamics",
        "neurohormonal",
        "physiology",
        "biomarkers",
        "dysfunction",
        "disease process",
    ],
    "pharmacology": [
        "pharmacology",
        "drug mechanism",
        "indication",
        "contraindication",
        "adverse effects",
        "drug interaction",
        "dosage",
        "pharmacokinetics",
        "pharmacodynamics",
        "monitoring",
        "toxicity",
        "therapeutic target",
    ],
    "monitoring": [
        "monitoring",
        "follow-up",
        "treatment response",
        "labs",
        "imaging",
        "vital signs",
        "disease control",
        "therapeutic monitoring",
        "adverse effects",
        "dose adjustment",
        "clinical assessment",
        "outcome tracking",
    ],
    "investigation": [
        "investigation",
        "diagnostic test",
        "laboratory findings",
        "imaging",
        "workup",
        "evaluation",
        "differential diagnosis",
        "clinical criteria",
        "biomarkers",
        "screening",
        "confirmatory test",
        "diagnostic accuracy",
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


def build_query_minimal(topic: str, competency: str) -> str:
    topic = topic.strip()
    competency = competency.strip()
    terms = [term for term in (topic, competency) if term]
    return " ".join(terms)
