"""Folder-based CRUD for knowledge bases. No database: everything lives under
settings.KNOWLEDGE_DIR/<kb_id>/ as manifest.json + raw/ + chunks.jsonl +
bm25.pkl + embeddings.npy.
"""
from __future__ import annotations

import json
import pickle
import re
import shutil
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from app.core.config import settings

_WORD_RE = re.compile(r"[a-z0-9]+")

# EN + ID stopwords (knowledge can be either language). Keep inline — no nltk dep.
_STOPWORDS = {
    # English
    "the", "and", "for", "are", "but", "not", "you", "all", "any", "can", "had",
    "her", "was", "one", "our", "out", "has", "his", "how", "its", "may", "new",
    "now", "old", "see", "two", "who", "did", "get", "him", "let", "put", "say",
    "she", "too", "use", "that", "this", "with", "from", "have", "been", "were",
    "would", "could", "should", "their", "there", "which", "these", "those",
    "when", "what", "where", "while", "about", "after", "before", "between",
    "into", "through", "during", "also", "such", "very", "than", "then", "them",
    "they", "more", "some", "other", "only", "most", "both", "each", "many",
    "much", "same", "over", "under", "will", "your", "just", "like", "make",
    "made", "using", "used", "within", "upon", "does", "here", "because",
    # Indonesian
    "yang", "dan", "untuk", "dengan", "pada", "dari", "ini", "itu", "atau",
    "adalah", "akan", "tidak", "juga", "dalam", "oleh", "sebagai", "karena",
    "dapat", "ada", "kita", "kami", "mereka", "saya", "anda", "dia", "kalau",
    "agar", "sudah", "belum", "harus", "bisa", "lebih", "sangat", "saat",
    "ketika", "setelah", "sebelum", "antara", "namun", "tetapi", "serta",
    "maka", "yaitu", "yakni", "seperti", "hanya", "masih", "para", "suatu",
    "sebuah", "tersebut", "hal", "cara", "secara", "bahwa", "jika", "agar",
    "supaya", "sehingga", "bila", "atas", "bawah", "dua", "satu",
}


def keyword_stats(kb_id: str, limit: int = 20, min_length: int = 3) -> List[dict]:
    """Most-frequent words across a KB's chunks, excluding stopwords/short/numeric tokens."""
    chunks_path = kb_paths(kb_id)["chunks"]
    if not chunks_path.exists():
        return []

    counter: Counter = Counter()
    with chunks_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            text = json.loads(line).get("text", "")
            for word in _WORD_RE.findall(text.lower()):
                if (
                    len(word) >= min_length
                    and word not in _STOPWORDS
                    and not word.isdigit()
                ):
                    counter[word] += 1

    return [{"word": word, "count": count} for word, count in counter.most_common(limit)]


def _kb_root() -> Path:
    root = Path(settings.KNOWLEDGE_DIR)
    root.mkdir(parents=True, exist_ok=True)
    return root


_KB_ID_RE = re.compile(r"^[0-9a-f]{12}$")


def is_valid_kb_id(kb_id: str) -> bool:
    return bool(_KB_ID_RE.match(kb_id))


def safe_filename(name: str) -> Optional[str]:
    safe = Path(name).name
    return safe if safe and safe not in (".", "..") else None


def _kb_dir(kb_id: str) -> Path:
    if not is_valid_kb_id(kb_id):
        raise ValueError(f"invalid kb_id: {kb_id}")
    return _kb_root() / kb_id


def _manifest_path(kb_id: str) -> Path:
    return _kb_dir(kb_id) / "manifest.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def kb_paths(kb_id: str) -> Dict[str, Path]:
    d = _kb_dir(kb_id)
    return {
        "dir": d,
        "raw": d / "raw",
        "chunks": d / "chunks.jsonl",
        "bm25": d / "bm25.pkl",
        "embeddings": d / "embeddings.npy",
    }


def raw_dir(kb_id: str) -> Path:
    d = kb_paths(kb_id)["raw"]
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_raw_files(kb_id: str) -> List[str]:
    d = raw_dir(kb_id)
    return sorted(p.name for p in d.iterdir() if p.is_file())


def list_kbs() -> List[dict]:
    manifests = []
    for manifest_file in _kb_root().glob("*/manifest.json"):
        try:
            manifests.append(json.loads(manifest_file.read_text(encoding="utf-8")))
        except Exception:
            continue
    manifests.sort(key=lambda m: m.get("created_at", ""), reverse=True)
    return manifests


def get_kb(kb_id: str) -> Optional[dict]:
    if not is_valid_kb_id(kb_id):
        return None
    path = _manifest_path(kb_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_manifest(kb_id: str, manifest: dict) -> dict:
    manifest["updated_at"] = _now()
    _manifest_path(kb_id).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def title_exists(title: str, exclude_kb_id: Optional[str] = None) -> bool:
    norm = title.strip().lower()
    return any(
        m.get("id") != exclude_kb_id and m.get("title", "").strip().lower() == norm
        for m in list_kbs()
    )


def create_kb(title: str, filenames: List[str]) -> dict:
    kb_id = uuid.uuid4().hex[:12]
    raw_dir(kb_id)
    manifest = {
        "id": kb_id,
        "title": title.strip(),
        "files": filenames,
        "n_chunks": 0,
        "embed_model": settings.EMBED_MODEL,
        "status": "processing",
        "progress": 0.0,
        "error": None,
        "created_at": _now(),
    }
    return _write_manifest(kb_id, manifest)


def _mark_processing(manifest: dict) -> None:
    manifest["status"] = "processing"
    manifest["progress"] = 0.0
    manifest["error"] = None


def add_files(kb_id: str) -> dict:
    manifest = get_kb(kb_id)
    if manifest is None:
        raise FileNotFoundError(kb_id)
    manifest["files"] = list_raw_files(kb_id)
    _mark_processing(manifest)
    return _write_manifest(kb_id, manifest)


def remove_file(kb_id: str, filename: str) -> dict:
    manifest = get_kb(kb_id)
    if manifest is None:
        raise FileNotFoundError(kb_id)
    safe_name = safe_filename(filename)
    if safe_name:
        target = raw_dir(kb_id) / safe_name
        if target.is_file():
            target.unlink()
    manifest["files"] = list_raw_files(kb_id)
    _mark_processing(manifest)
    return _write_manifest(kb_id, manifest)


def rename_kb(kb_id: str, title: str) -> dict:
    manifest = get_kb(kb_id)
    if manifest is None:
        raise FileNotFoundError(kb_id)
    manifest["title"] = title.strip()
    return _write_manifest(kb_id, manifest)


def delete_kb(kb_id: str) -> None:
    shutil.rmtree(_kb_dir(kb_id), ignore_errors=True)


def set_status(
    kb_id: str,
    status: str,
    progress: float = 0.0,
    error: Optional[str] = None,
    n_chunks: Optional[int] = None,
) -> Optional[dict]:
    manifest = get_kb(kb_id)
    if manifest is None:
        return None
    manifest["status"] = status
    manifest["progress"] = progress
    manifest["error"] = error
    if n_chunks is not None:
        manifest["n_chunks"] = n_chunks
    return _write_manifest(kb_id, manifest)


def load_kb_index(kb_id: str):
    """Return (bm25_index, doc_embeddings) for a ready KB.

    doc_embeddings maps doc_id -> np.ndarray, built by zipping chunks.jsonl
    (write order) against embeddings.npy (same order, written at ingest time).
    """
    paths = kb_paths(kb_id)
    with paths["bm25"].open("rb") as handle:
        bm25_index = pickle.load(handle)

    doc_embeddings: Dict[str, np.ndarray] = {}
    if paths["embeddings"].exists() and paths["chunks"].exists():
        vectors = np.load(paths["embeddings"])
        doc_ids: List[str] = []
        with paths["chunks"].open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    doc_ids.append(json.loads(line)["doc_id"])
        if len(doc_ids) == len(vectors):
            doc_embeddings = {doc_id: vectors[i] for i, doc_id in enumerate(doc_ids)}

    return bm25_index, doc_embeddings
