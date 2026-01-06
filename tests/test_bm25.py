from __future__ import annotations

from app.corpus.models import Document
from app.retrieval.bm25 import BM25Index


def _make_docs() -> list[Document]:
    return [
        Document(
            doc_id="d1",
            source="test",
            title="Diabetes diagnosis",
            text="Symptoms include polyuria and polydipsia.",
        ),
        Document(
            doc_id="d2",
            source="test",
            title="Hypertension management",
            text="First-line therapy includes lifestyle modification.",
        ),
        Document(
            doc_id="d3",
            source="test",
            title="Asthma exacerbation",
            text="Triggers include allergens and viral infections.",
        ),
        Document(
            doc_id="d4",
            source="test",
            title="Diabetes treatment",
            text="Metformin improves insulin sensitivity.",
        ),
        Document(
            doc_id="d5",
            source="test",
            title="Chronic kidney disease",
            text="Stages are based on eGFR.",
        ),
        Document(
            doc_id="d6",
            source="test",
            title="Myocardial infarction",
            text="Chest pain and ECG changes are key findings.",
        ),
        Document(
            doc_id="d7",
            source="test",
            title="Anemia workup",
            text="Microcytic anemia suggests iron deficiency.",
        ),
        Document(
            doc_id="d8",
            source="test",
            title="Thyroid disorders",
            text="Hypothyroidism causes fatigue and weight gain.",
        ),
        Document(
            doc_id="d9",
            source="test",
            title="Pneumonia",
            text="Common pathogens include Streptococcus pneumoniae.",
        ),
        Document(
            doc_id="d10",
            source="test",
            title="Sepsis",
            text="Early recognition improves outcomes.",
        ),
    ]


def test_bm25_ranks_relevant_doc_first() -> None:
    docs = _make_docs()
    index = BM25Index.build(docs)

    results = index.search("diabetes diagnosis", top_k=3)

    assert len(results) == 3
    assert results[0][0].doc_id == "d1"
    assert results[0][1] >= results[1][1]
