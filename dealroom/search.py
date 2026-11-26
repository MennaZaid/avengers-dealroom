"""Web search through the self-hosted SearXNG (free, decision D6). Returns result links only; nothing is
fetched here."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass

import httpx

from dealroom.settings import Settings


class SearchError(Exception):
    pass


@dataclass(frozen=True)
class SearchHit:
    url: str
    title: str
    snippet: str
    rank: int  # 1 = first result
    engines: tuple[str, ...] = ()


_LOCK = threading.Lock()
_LAST = [0.0]


def _throttle() -> None:
    """Space queries: SearXNG's upstream engines (Brave, DuckDuckGo, Google) suspend us after ~10 fast queries."""
    gap = float(os.environ.get("SEARXNG_MIN_INTERVAL", "2.5"))
    with _LOCK:
        wait = _LAST[0] + gap - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _LAST[0] = time.monotonic()


def searxng_search(query: str, language: str = "en", limit: int = 8, timeout: float = 20.0) -> list[SearchHit]:
    _throttle()
    try:
        r = httpx.get(Settings().searxng_url.rstrip("/") + "/search",
                      params={"q": query, "format": "json", "language": language, "safesearch": 1},
                      timeout=timeout)
        r.raise_for_status()
        results = r.json().get("results", [])
    except (httpx.HTTPError, ValueError) as e:
        raise SearchError(f"search failed: {e}") from e
    hits, seen = [], set()
    for item in results:
        url = item.get("url") or ""
        if not url.startswith(("https://", "http://")) or url in seen:
            continue
        seen.add(url)
        hits.append(SearchHit(url=url, title=(item.get("title") or "").strip(),
                              snippet=(item.get("content") or "").strip(), rank=len(hits) + 1,
                              engines=tuple(item.get("engines") or ())))
        if len(hits) >= limit:
            break
    return hits
