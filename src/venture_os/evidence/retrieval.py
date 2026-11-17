"""Embeddings and hybrid search over the RAG indexes (documents + chunks in Postgres/pgvector).

Embeddings: bge-m3 (open weights, multilingual AR/EN, 1024 dimensions = the chunks.embedding column) served
locally by Ollama (EMBED_URL, default http://localhost:11434; EMBED_MODEL, default bge-m3). Free, no key.
Hybrid search: keyword rank (Postgres full-text, 'simple' config so Arabic works) and vector similarity
(cosine), fused with reciprocal rank fusion. Either half alone still works if the other finds nothing.
"""

from __future__ import annotations

import os
import re

import httpx

from venture_os.api.db import connect

DIM = 1024
RRF_K = 60


def embed_url() -> str:
    return os.environ.get("EMBED_URL", "http://localhost:11434").rstrip("/")


def embed_model() -> str:
    return os.environ.get("EMBED_MODEL", "bge-m3")


def embed(texts: list[str], timeout: float = 120.0) -> list[list[float]]:
    r = httpx.post(f"{embed_url()}/api/embed", json={"model": embed_model(), "input": texts}, timeout=timeout)
    r.raise_for_status()
    vecs = r.json()["embeddings"]
    if any(len(v) != DIM for v in vecs):
        raise ValueError(f"embedding size is not {DIM}: use a {DIM}-d model such as bge-m3")
    return vecs


def _vec(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def embed_missing(index_name: str = "corpus", batch: int = 16) -> int:
    """Embed every current chunk of the index that has no embedding yet. Returns how many were embedded."""
    with connect("vos_agent") as conn:
        rows = conn.execute("SELECT c.id, c.text FROM chunks c JOIN documents d ON d.id = c.document_id "
                            "WHERE d.index_name = %s AND d.valid_to IS NULL AND c.embedding IS NULL", (index_name,)
                            ).fetchall()
    done = 0
    for i in range(0, len(rows), batch):
        part = rows[i:i + batch]
        vecs = embed([r["text"] for r in part])
        with connect("vos_agent") as conn:
            for r, v in zip(part, vecs, strict=True):
                conn.execute("UPDATE chunks SET embedding = %s::vector WHERE id = %s", (_vec(v), r["id"]))
        done += len(part)
    return done


def hybrid_search(query: str, index_name: str = "corpus", k: int = 5, use_vectors: bool = True) -> list[dict]:
    words = [w for w in re.findall(r"[\w؀-ۿ]+", query.lower()) if len(w) > 1][:12]
    ranked: dict[str, dict] = {}
    with connect("vos_agent") as conn:
        if words:
            kw = conn.execute(
                "SELECT c.id, c.text, d.url, d.title, d.corpus_id, ts_rank(c.tsv, to_tsquery('simple', %(q)s)) AS r "
                "FROM chunks c JOIN current_documents d ON d.id = c.document_id WHERE d.index_name = %(ix)s "
                "AND c.tsv @@ to_tsquery('simple', %(q)s) ORDER BY r DESC LIMIT 20",
                {"q": " | ".join(words), "ix": index_name}).fetchall()
            for pos, row in enumerate(kw, 1):
                e = ranked.setdefault(str(row["id"]), {**row, "score": 0.0, "matched": []})
                e["score"] += 1 / (RRF_K + pos)
                e["matched"].append(f"keyword #{pos}")
        if use_vectors:
            try:
                qv = _vec(embed([query])[0])
            except (httpx.HTTPError, ValueError, KeyError):
                qv = None
            if qv:
                vec = conn.execute(
                    "SELECT c.id, c.text, d.url, d.title, d.corpus_id, 1 - (c.embedding <=> %(v)s::vector) AS sim "
                    "FROM chunks c JOIN current_documents d ON d.id = c.document_id WHERE d.index_name = %(ix)s "
                    "AND c.embedding IS NOT NULL ORDER BY c.embedding <=> %(v)s::vector LIMIT 20",
                    {"v": qv, "ix": index_name}).fetchall()
                for pos, row in enumerate(vec, 1):
                    e = ranked.setdefault(str(row["id"]), {**row, "score": 0.0, "matched": []})
                    e["score"] += 1 / (RRF_K + pos)
                    e["matched"].append(f"vector #{pos} (cos {row['sim']:.2f})")
    out = sorted(ranked.values(), key=lambda e: -e["score"])[:k]
    for e in out:
        e.pop("r", None)
        e.pop("sim", None)
        e["id"] = str(e["id"])
    return out
