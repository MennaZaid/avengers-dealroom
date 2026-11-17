"""The evidence store in Postgres: the live RAG index (documents + chunks) and Discover claims.

Runs under the vos_agent role: agents may write documents, chunks and claims, and read the registry, but can
never change the registry (Postgres refuses it).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from psycopg.types.json import Jsonb

from venture_os.api.db import connect
from venture_os.tools.fetch import Page

CHUNK_CHARS = 1200


@dataclass(frozen=True)
class RegistryMatch:
    source_id: str
    tier: str
    max_age_months: int | None
    source_name: str


@dataclass
class StoredChunk:
    chunk_id: str
    document_id: str
    text: str
    url: str
    title: str
    language: str
    published_at: date | None
    retrieved_at: datetime
    source_id: str | None = None
    tier: str | None = None
    max_age_months: int | None = None
    from_db: bool = False  # found in the store from an earlier run, not fetched now


def chunk_text(text: str, size: int = CHUNK_CHARS) -> list[str]:
    """Paragraph-aligned chunks of about `size` characters."""
    chunks, cur = [], ""
    for para in [p for p in text.split("\n") if p.strip()]:
        while len(para) > size:  # a very long paragraph: cut at a sentence end if possible
            cut = max(para.rfind(". ", 0, size), para.rfind("، ", 0, size), para.rfind("。", 0, size))
            cut = cut + 1 if cut > size // 2 else size
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(para[:cut].strip())
            para = para[cut:].strip()
        if cur and len(cur) + len(para) + 1 > size:
            chunks.append(cur)
            cur = para
        else:
            cur = f"{cur}\n{para}" if cur else para
    if cur:
        chunks.append(cur)
    return chunks


def _domain(url: str) -> str:
    m = re.match(r"^https?://([^/:]+)", url)
    host = (m.group(1) if m else "").lower()
    return host.removeprefix("www.")


class EvidenceStore:
    def __init__(self):
        self._registry: dict[str, RegistryMatch] | None = None

    # ---- registry lookups (read-only) ----
    def registry_match(self, url: str) -> RegistryMatch | None:
        if self._registry is None:
            with connect("vos_agent") as conn:
                rows = conn.execute("SELECT id, domain, tier, max_age_months, source_name FROM sources "
                                    "WHERE active AND domain IS NOT NULL").fetchall()
            self._registry = {}
            for r in rows:
                d = r["domain"].lower()
                d = d.removeprefix("www.")
                self._registry.setdefault(d, RegistryMatch(r["id"], r["tier"], r["max_age_months"],
                                                           r["source_name"]))
        host = _domain(url)
        while host:
            if host in self._registry:
                return self._registry[host]
            host = host.split(".", 1)[1] if "." in host else ""
        return None

    # ---- documents and chunks ----
    def save_page(self, page: Page, index_name: str = "live", corpus_id: str | None = None,
                  license: str | None = None) -> list[StoredChunk]:
        """Store a page in the live index (market evidence) or the corpus index (methods, with its corpus id)."""
        match = self.registry_match(page.final_url) if index_name == "live" else None
        with connect("vos_agent") as conn:
            row = conn.execute(
                "INSERT INTO documents (index_name, source_id, corpus_id, url, title, language, published_at, "
                "retrieved_at, content_hash, license) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (url, content_hash) DO NOTHING RETURNING id",
                (index_name, match.source_id if match else None, corpus_id, page.final_url, page.title[:500],
                 page.language,
                 page.published_at, page.retrieved_at, page.content_hash, license),
            ).fetchone()
            if row:  # new document: store its chunks
                doc_id = row["id"]
                for i, text in enumerate(chunk_text(page.text)):
                    conn.execute("INSERT INTO chunks (document_id, ordinal, text) VALUES (%s, %s, %s)",
                                 (doc_id, i, text))
            else:  # the same page, unchanged, was stored before; fill in a publication date found only now
                doc_id = conn.execute(
                    "UPDATE documents SET published_at = COALESCE(published_at, %s) WHERE url = %s AND "
                    "content_hash = %s RETURNING id", (page.published_at, page.final_url, page.content_hash),
                ).fetchone()["id"]
            rows = conn.execute(
                "SELECT c.id, c.text, d.retrieved_at, d.published_at FROM chunks c JOIN documents d "
                "ON d.id = c.document_id WHERE c.document_id = %s ORDER BY c.ordinal", (doc_id,)).fetchall()
        return [StoredChunk(chunk_id=str(r["id"]), document_id=str(doc_id), text=r["text"], url=page.final_url,
                            title=page.title, language=page.language, published_at=r["published_at"],
                            retrieved_at=r["retrieved_at"],
                            source_id=match.source_id if match else None, tier=match.tier if match else None,
                            max_age_months=match.max_age_months if match else None)
                for r in rows]

    def search_corpus(self, query: str, limit: int = 5) -> list[dict]:
        """Keyword search over the methods corpus (Mom Test, user research, WCAG, OWASP, ...)."""
        words = [w for w in re.findall(r"[\w؀-ۿ]+", query.lower()) if len(w) > 2][:12]
        if not words:
            return []
        with connect("vos_agent") as conn:
            return conn.execute(
                "SELECT c.text, d.url, d.title, d.corpus_id, ts_rank(c.tsv, to_tsquery('simple', %(q)s)) AS rank "
                "FROM chunks c JOIN current_documents d ON d.id = c.document_id WHERE d.index_name = 'corpus' "
                "AND c.tsv @@ to_tsquery('simple', %(q)s) ORDER BY rank DESC LIMIT %(n)s",
                {"q": " | ".join(words), "n": limit}).fetchall()

    def search_chunks(self, query: str, limit: int = 5, max_age_days: int = 30) -> list[StoredChunk]:
        """Keyword search over current documents fetched in the last `max_age_days` (reuse, don't refetch)."""
        words = [w for w in re.findall(r"[\w؀-ۿ]+", query.lower()) if len(w) > 2][:12]
        if not words:
            return []
        tsq = " | ".join(words)
        with connect("vos_agent") as conn:
            rows = conn.execute(
                "SELECT c.id, c.text, c.document_id, d.url, d.title, d.language, d.published_at, d.retrieved_at, "
                "d.source_id, d.tier, d.max_age_months, ts_rank(c.tsv, to_tsquery('simple', %(q)s)) AS rank "
                "FROM chunks c JOIN current_documents d ON d.id = c.document_id "
                "WHERE d.index_name = 'live' AND d.retrieved_at > now() - make_interval(days => %(age)s) "
                "AND c.tsv @@ to_tsquery('simple', %(q)s) ORDER BY rank DESC LIMIT 40",
                {"q": tsq, "age": max_age_days}).fetchall()
        need = max(2, round(len(words) * 0.6))  # most of the query's words must appear
        out = []
        for r in rows:
            text = r["text"].lower()
            if sum(w in text for w in words) >= need:
                out.append(StoredChunk(chunk_id=str(r["id"]), document_id=str(r["document_id"]), text=r["text"],
                                       url=r["url"], title=r["title"] or r["url"], language=r["language"] or "",
                                       published_at=r["published_at"], retrieved_at=r["retrieved_at"],
                                       source_id=r["source_id"], tier=r["tier"],
                                       max_age_months=r["max_age_months"], from_db=True))
            if len(out) >= limit:
                break
        return out

    # ---- founder-entered interviews (read only for agents) ----
    def interviews(self, brief_id: str) -> list[dict]:
        with connect("vos_agent") as conn:
            return conn.execute("SELECT person, held_on, tagged, describes_problem FROM discover_interviews "
                                "WHERE brief_id = %s ORDER BY created_at", (brief_id,)).fetchall()

    # ---- claims and run progress ----
    def save_claims(self, run_id: str | UUID, claims: list[dict]) -> list[str]:
        ids = []
        with connect("vos_agent") as conn:
            for c in claims:
                ids.append(str(conn.execute(
                    "INSERT INTO claims (stage_run_id, topic, agent, text, type, document_id, chunk_id, quote, "
                    "language, flags, extracted_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                    (run_id, c["topic"], c["agent"], c["text"], c["type"], c.get("document_id"),
                     c.get("chunk_id"), c.get("quote"), c.get("language"), c.get("flags", []),
                     c["extracted_by"]),
                ).fetchone()["id"]))
        return ids

    def update_run(self, run_id: str | UUID, output: dict, status: str | None = None) -> None:
        with connect("vos_agent") as conn:
            if status:
                conn.execute("UPDATE stage_runs SET output = %s, status = %s, updated_at = now() WHERE id = %s",
                             (Jsonb(output), status, run_id))
            else:
                conn.execute("UPDATE stage_runs SET output = %s, updated_at = now() WHERE id = %s",
                             (Jsonb(output), run_id))
