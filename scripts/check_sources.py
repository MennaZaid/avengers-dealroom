"""Test which registry sources actually respond and record the result on each row.

Usage: python scripts/check_sources.py [--all] [--search-only]

Checks the digital-pack rows and the rows changed by registry_updates.yaml (or every active row with --all):
  api / polite_fetch / manual_upload / manual : GET test_url (or url) -> reachable | failed | needs_key
  search_only                                 : a SearXNG "site:" query -> reachable (via search) | failed
The result goes to url_status / http_status / tested_on through registry.update_source (the logged admin path,
reason "reachability check"). Never sends credentials: a source that wants a key is recorded as needs_key.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import yaml

from venture_os.api.db import connect
from venture_os.api.registry import update_source
from venture_os.config import Settings
from venture_os.tools.search import SearchError, searxng_search

ROOT = Path(__file__).resolve().parents[1]
UA = "VentureOS-research/0.1 (open-source research bot; source reachability check)"
KEY_HINTS = ("api key", "apikey", "token", "unauthorized", "authentication", "access_token")


def targets(all_rows: bool) -> list[dict]:
    with connect("vos_admin") as conn:
        rows = conn.execute("SELECT id, source_name, url, test_url, access_type FROM sources WHERE active "
                            "ORDER BY id").fetchall()
    if all_rows:
        return rows
    ids = {e["id"] for e in yaml.safe_load((ROOT / "config/sources/digital.yaml").read_text(encoding="utf-8"))}
    ids |= set(yaml.safe_load((ROOT / "config/sources/registry_updates.yaml").read_text(encoding="utf-8")))
    return [r for r in rows if r["id"] in ids]


def check_http(url: str) -> tuple[str, int | None, str]:
    try:
        r = httpx.get(url, headers={"User-Agent": UA}, timeout=20, follow_redirects=True)
    except httpx.HTTPError as e:
        return "failed", None, f"{type(e).__name__}: {str(e)[:120]}"
    body = r.text[:2000].lower() if "text" in r.headers.get("content-type", "") or "json" in \
        r.headers.get("content-type", "") else ""
    if r.status_code < 300:
        return "reachable", r.status_code, ""
    if r.status_code == 401 or (r.status_code in (403, 429) and any(h in body for h in KEY_HINTS)):
        return "needs_key", r.status_code, "asks for a key or token"
    if r.status_code == 429:
        return "failed", r.status_code, "rate limited (no key exists; retry later)"
    return "failed", r.status_code, f"HTTP {r.status_code}"


def engines_suspended() -> bool:
    """True when SearXNG's upstream engines refuse us (rate limits / CAPTCHA): then nothing can be judged."""
    try:
        d = httpx.get(Settings().searxng_url.rstrip("/") + "/search",
                      params={"q": "software", "format": "json"}, timeout=20).json()
    except (httpx.HTTPError, ValueError):
        return True
    return not d.get("results") and bool(d.get("unresponsive_engines"))


def check_search(url: str) -> tuple[str, int | None, str] | None:
    domain = (urlsplit(url).hostname or "").removeprefix("www.")
    try:
        hits = searxng_search(f"site:{domain} software", "en", limit=8)  # engines need a term with site:
    except SearchError as e:
        return "failed", None, str(e)[:120]
    if any(domain in (urlsplit(h.url).hostname or "") for h in hits):
        return "reachable", None, "via search (search_only)"
    if engines_suspended():
        return None  # the search engines refused us, not the source: record nothing
    return "failed", None, "no results from this site through search"


def main(all_rows: bool = False, only: set[str] | None = None) -> None:
    results = []
    for r in targets(all_rows):
        if only and r["access_type"] not in only:
            continue
        url = r["test_url"] or r["url"]
        if not url:
            continue
        result = check_search(url) if r["access_type"] == "search_only" else check_http(url)
        if result is None:
            print(f"skipped    {r['id']:7} search engines suspended (rate limit/CAPTCHA): not recorded")
            continue
        status, code, detail = result
        update_source(r["id"], {"url_status": status, "http_status": code, "tested_on": date.today()},
                      "seed", f"reachability check: {status}" + (f" ({detail})" if detail else ""))
        results.append((r["id"], r["source_name"], r["access_type"], status, code, detail))
        print(f"{status:10} {code or ''!s:4} {r['id']:7} {r['access_type'] or '':13} {r['source_name'][:45]}"
              f"  {detail}")
    counts: dict[str, int] = {}
    for *_, status, _code, _d in results:
        counts[status] = counts.get(status, 0) + 1
    print(counts)


if __name__ == "__main__":
    main(all_rows="--all" in sys.argv, only={"search_only"} if "--search-only" in sys.argv else None)
