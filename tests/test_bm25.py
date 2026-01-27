from __future__ import annotations

from app.corpus.models import Document
from app.retrieval.bm25 import BM25Index


def _make_docs() -> list[Document]:
    return [
        Document(
            doc_id="d1",
            source="test",
            title="Diabetes diagnosis",
            text=(
                "Background: Type 2 diabetes mellitus is often asymptomatic early. "
                "Symptoms include polyuria, polydipsia, and weight loss. "
                "Diagnosis is confirmed by fasting plasma glucose, HbA1c, or oral glucose tolerance test. "
                "Key findings can include elevated HbA1c and random glucose >200 mg/dL with symptoms."
            ),
        ),
        Document(
            doc_id="d2",
            source="test",
            title="Hypertension management",
            text=(
                "Guidelines recommend lifestyle modification and pharmacotherapy. "
                "First-line agents include thiazide diuretics, ACE inhibitors, ARBs, and calcium channel blockers. "
                "Monitor blood pressure, renal function, and electrolytes."
            ),
        ),
        Document(
            doc_id="d3",
            source="test",
            title="Asthma exacerbation",
            text=(
                "Acute exacerbations are triggered by viral infections, allergens, and irritants. "
                "Symptoms include wheeze, dyspnea, and cough with reduced peak flow. "
                "Management includes SABA, systemic corticosteroids, and oxygen if needed."
            ),
        ),
        Document(
            doc_id="d4",
            source="test",
            title="Diabetes treatment",
            text=(
                "Metformin is first-line pharmacotherapy for type 2 diabetes and improves insulin sensitivity. "
                "Consider GLP-1 receptor agonists or SGLT2 inhibitors for cardiovascular benefit. "
                "Monitor HbA1c every 3-6 months."
            ),
        ),
        Document(
            doc_id="d5",
            source="test",
            title="Chronic kidney disease",
            text=(
                "Chronic kidney disease staging is based on eGFR and albuminuria. "
                "Complications include anemia, bone mineral disorder, and cardiovascular disease. "
                "Management includes blood pressure control and avoidance of nephrotoxins."
            ),
        ),
        Document(
            doc_id="d6",
            source="test",
            title="Myocardial infarction",
            text=(
                "Presentation includes chest pain, diaphoresis, and nausea. "
                "ECG changes and elevated troponin support diagnosis. "
                "Acute management includes antiplatelets, anticoagulation, and reperfusion therapy."
            ),
        ),
        Document(
            doc_id="d7",
            source="test",
            title="Anemia workup",
            text=(
                "Workup includes CBC, reticulocyte count, iron studies, and peripheral smear. "
                "Microcytic anemia suggests iron deficiency or thalassemia. "
                "Assess for sources of blood loss."
            ),
        ),
        Document(
            doc_id="d8",
            source="test",
            title="Thyroid disorders",
            text=(
                "Hypothyroidism can cause fatigue, weight gain, and cold intolerance. "
                "Diagnosis is supported by elevated TSH and low free T4. "
                "Treatment is levothyroxine with TSH monitoring."
            ),
        ),
        Document(
            doc_id="d9",
            source="test",
            title="Pneumonia",
            text=(
                "Community-acquired pneumonia often presents with cough, fever, and sputum production. "
                "Common pathogens include Streptococcus pneumoniae and atypicals. "
                "Diagnosis may include chest imaging and sputum studies."
            ),
        ),
        Document(
            doc_id="d10",
            source="test",
            title="Sepsis",
            text=(
                "Sepsis is life-threatening organ dysfunction caused by infection. "
                "Early recognition and prompt antibiotics improve outcomes. "
                "Management includes fluid resuscitation and source control."
            ),
        ),
    ]


def test_bm25_ranks_relevant_doc_first() -> None:
    docs = _make_docs()
    index = BM25Index.build(docs)

    results = index.search("diabetes diagnosis", top_k=3)

    assert len(results) == 3
    assert results[0][0].doc_id == "d1"
    assert results[0][1] >= results[1][1]
