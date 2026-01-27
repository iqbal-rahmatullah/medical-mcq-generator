from __future__ import annotations

from app.corpus.models import Document
from app.retrieval.bm25 import BM25Index
from app.retrieval.retriever import Retriever


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
            title="Thyroid disorders",
            text=(
                "Hypothyroidism can cause fatigue, weight gain, and cold intolerance. "
                "Diagnosis is supported by elevated TSH and low free T4. "
                "Treatment is levothyroxine with TSH monitoring."
            ),
        ),
    ]


class _DummyRuntime:
    def __init__(self) -> None:
        self.called = False

    def rerank(self, query: str, docs: list[Document]) -> list[float]:
        self.called = True
        return [float(len(docs) - idx) for idx in range(len(docs))]


def test_bm25_only_does_not_call_medcpt() -> None:
    index = BM25Index.build(_make_docs())
    runtime = _DummyRuntime()

    retriever = Retriever(
        index,
        medcpt_runtime=runtime,
        retrieval_mode="bm25_only",
        bm25_candidates_top_n=5,
        rerank_top_n=3,
        evidence_top_k=2,
    )
    retriever.retrieve("diabetes", "diagnosis")

    assert runtime.called is False


def test_hybrid_mode_calls_medcpt() -> None:
    index = BM25Index.build(_make_docs())
    runtime = _DummyRuntime()

    retriever = Retriever(
        index,
        medcpt_runtime=runtime,
        retrieval_mode="hybrid_rerank",
        bm25_candidates_top_n=5,
        rerank_top_n=3,
        evidence_top_k=2,
    )
    retriever.retrieve("diabetes", "diagnosis")

    assert runtime.called is True
