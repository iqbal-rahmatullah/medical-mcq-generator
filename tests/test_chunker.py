from app.ingestion.chunker import chunk_text


def test_chunk_text_basic_paragraphs():
    text = "\n\n".join(["First paragraph." * 5, "Second paragraph." * 5, "Third paragraph." * 5])
    chunks = list(chunk_text(text, source="doc.txt", chunk_size=100, overlap=20))
    assert len(chunks) > 1
    assert all(c.text.strip() for c in chunks)
    assert all(c.source == "doc.txt" for c in chunks)
    assert all(c.doc_id.startswith("doc.txt#") for c in chunks)


def test_chunk_text_empty_input():
    assert list(chunk_text("   \n\n  ", source="empty.txt")) == []


def test_chunk_text_oversized_paragraph_hard_split():
    text = "x" * 500
    chunks = list(chunk_text(text, source="big.txt", chunk_size=100, overlap=10))
    assert len(chunks) >= 5
    assert all(len(c.text) <= 100 for c in chunks)


def test_chunk_text_doc_ids_unique():
    text = "\n\n".join(f"paragraph number {i} " * 10 for i in range(10))
    chunks = list(chunk_text(text, source="doc.txt", chunk_size=80, overlap=10))
    ids = [c.doc_id for c in chunks]
    assert len(ids) == len(set(ids))


if __name__ == "__main__":
    test_chunk_text_basic_paragraphs()
    test_chunk_text_empty_input()
    test_chunk_text_oversized_paragraph_hard_split()
    test_chunk_text_doc_ids_unique()
    print("ok")
