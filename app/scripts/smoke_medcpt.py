from __future__ import annotations

from app.corpus.models import Document
from app.retrieval.medcpt_runtime import MedCPTRuntime


def main() -> None:
    runtime = MedCPTRuntime()

    query = "diabetes diagnosis"
    docs = [
        Document(
            doc_id="d1",
            source="dummy",
            title="Diabetes diagnosis",
            text="Symptoms include polyuria and polydipsia.",
        ),
        Document(
            doc_id="d2",
            source="dummy",
            title="Hypertension management",
            text="Lifestyle modification remains first-line therapy.",
        ),
        Document(
            doc_id="d3",
            source="dummy",
            title="Asthma exacerbation",
            text="Triggers include allergens and infections.",
        ),
        Document(
            doc_id="d4",
            source="dummy",
            title="Diabetes treatment",
            text="Metformin improves insulin sensitivity.",
        ),
        Document(
            doc_id="d5",
            source="dummy",
            title="Thyroid disorders",
            text="Hypothyroidism causes fatigue and weight gain.",
        ),
    ]

    query_vec = runtime.encode_query(query)
    doc_vecs = runtime.encode_docs([f"{doc.title} {doc.text}" for doc in docs])
    scores = runtime.rerank(query, docs)

    print(f"Query embedding shape: {query_vec.shape}")
    print(f"Doc embeddings shape: {doc_vecs.shape}")
    print("Scores:")
    for doc, score in zip(docs, scores):
        print(f"  {doc.doc_id}: {score:.4f}")


if __name__ == "__main__":
    main()
