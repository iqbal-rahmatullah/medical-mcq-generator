from __future__ import annotations

from typing import Dict, Iterable, Iterator, Optional

from app.corpus.models import Document


class DocumentStore:
    def __init__(self, docs: Optional[Iterable[Document]] = None) -> None:
        self._docs: Dict[str, Document] = {}
        if docs is not None:
            for doc in docs:
                self.add(doc)

    def add(self, doc: Document) -> bool:
        if doc.doc_id in self._docs:
            return False
        self._docs[doc.doc_id] = doc
        return True

    def get(self, doc_id: str) -> Optional[Document]:
        return self._docs.get(doc_id)

    def iter_docs(self) -> Iterator[Document]:
        yield from self._docs.values()

    def __len__(self) -> int:
        return len(self._docs)
