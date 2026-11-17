"""Load the methods corpus into the RAG database (documents + chunks, index 'corpus') and embed it.

Usage: python scripts/ingest_corpus.py [--dry-run] [--no-pages]

1. Team-written method summaries (config/corpus/summaries/M-*.md): our own words plus the link, never book text.
   Each becomes a corpus document tied to its corpus item id, with retrieved_at = now and a content hash.
2. Openly licensed corpus items (CC BY / CC BY-SA / CC0, Open Government Licence, W3C document licence, public
   domain), fetched from their URL with robots.txt respected. Everything else stays link-only.
3. Every corpus chunk without an embedding gets one (bge-m3 via Ollama, 1024-d).
Re-running is safe: an unchanged document is not stored twice; only missing embeddings are added.
"""

from __future__ import annotations

import hashlib
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from venture_os.api.db import connect
from venture_os.evidence.retrieval import embed_missing
from venture_os.evidence.store import EvidenceStore
from venture_os.tools.fetch import FetchError, Page, fetch_page, text_language

ROOT = Path(__file__).resolve().parents[1]
SUMMARIES = ROOT / "config" / "corpus" / "summaries"
OPEN = re.compile(r"\b(cc[ -]?by|cc0|creative commons|open government licence|w3c document license|public domain)",
                  re.IGNORECASE)


def summary_pages(items: dict[str, dict]) -> list[tuple[str, Page]]:
    out = []
    for f in sorted(SUMMARIES.glob("M-*.md")):
        item = items.get(f.stem)
        if not item:
            print(f"skip {f.name}: no corpus item {f.stem}")
            continue
        text = f.read_text(encoding="utf-8").strip()
        out.append((f.stem, Page(url=item["url"], final_url=item["url"], title=f"Team summary: {item['title']}",
                                 text=text, language=text_language(text), published_at=None,
                                 retrieved_at=datetime.now(UTC),
                                 content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest())))
    return out


def main(dry_run: bool = False, pages: bool = True) -> None:
    with connect("vos_agent") as conn:
        rows = conn.execute("SELECT id, title, url, license, status FROM corpus_items ORDER BY id").fetchall()
    items = {r["id"]: r for r in rows}
    store = EvidenceStore()
    n_sum = 0
    for cid, page in summary_pages(items):
        if dry_run:
            print(f"would ingest summary {cid} ({len(page.text)} chars)")
            continue
        chunks = store.save_page(page, index_name="corpus", corpus_id=cid,
                                 license="team-written summary (this repository's licence); source linked")
        n_sum += 1
        print(f"ok   {cid} team summary: {len(chunks)} chunks")
    n_pages, link_only = 0, 0
    if pages:
        for it in rows:
            if it["status"] != "keep" or not it["url"]:
                continue
            if not OPEN.search(it["license"] or ""):
                link_only += 1
                continue
            if dry_run:
                print(f"would fetch {it['id']} {it['title']} ({it['license']})")
                continue
            try:
                chunks = store.save_page(fetch_page(it["url"]), index_name="corpus", corpus_id=it["id"],
                                         license=it["license"])
                n_pages += 1
                print(f"ok   {it['id']} {it['title'][:60]}: {len(chunks)} chunks")
            except FetchError as e:
                print(f"skip {it['id']} {it['title'][:60]}: {e}")
    embedded = 0 if dry_run else embed_missing("corpus")
    print(f"summaries {n_sum}; open-licence pages {n_pages}; link-only {link_only}; chunks embedded now {embedded}")


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv, pages="--no-pages" not in sys.argv)
