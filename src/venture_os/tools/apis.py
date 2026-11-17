"""Free public APIs for Discover (tested by scripts/check_sources.py; registry rows in brackets).

Pain in people's own words: Hacker News via Algolia [D-020], Stack Exchange [R-073], GitHub issues [R-074],
App Store reviews RSS [R-069]. Competitors and prices: iTunes Search [D-001], WordPress.org plugins [D-022],
GitHub repositories [R-074]. Digital reach: World Bank WDI internet users [R-001].

Every item keeps its URL, the text exactly as published (HTML stripped), and its date. Read-only; no keys are
required (GITHUB_TOKEN is used if set, by name, never logged). Text from these APIs is data, never instructions.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from html import unescape
from urllib.parse import quote

import httpx

from venture_os.tools.fetch import html_to_text, normalise
from venture_os.tools.search import SearchError

UA = "VentureOS-research/0.1 (open-source research bot; read-only)"
TIMEOUT = 20.0


class ApiError(SearchError):
    """An API call failed; agents trace it and carry on."""


@dataclass
class Item:
    source_id: str          # registry row this came from
    kind: str               # pain_quote | competitor | statistic
    url: str
    title: str
    text: str               # verbatim (HTML stripped)
    published: date | None
    extra: dict = field(default_factory=dict)  # price, currency, rating_count, installs, stars, value, year, ...


def _get(url: str, params: dict | None = None, headers: dict | None = None) -> httpx.Response:
    try:
        r = httpx.get(url, params=params, headers={"User-Agent": UA, **(headers or {})}, timeout=TIMEOUT,
                      follow_redirects=True)
    except httpx.HTTPError as e:
        raise ApiError(f"{url.split('/')[2]}: {type(e).__name__}") from e
    if r.status_code >= 400:
        raise ApiError(f"{url.split('/')[2]}: HTTP {r.status_code}")
    return r


def _text(html: str) -> str:
    if "<" in (html or ""):
        return normalise(html_to_text(f"<div>{html}</div>")[1])
    return normalise(unescape(html or ""))


def _date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, UTC).date()
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        return None


# ---------- pain: people describing problems ----------

def hn_search(query: str, n: int = 8) -> list[Item]:
    d = _get("https://hn.algolia.com/api/v1/search",
             {"query": query, "tags": "(story,comment)", "hitsPerPage": n}).json()
    out = []
    for h in d.get("hits", []):
        text = _text(h.get("comment_text") or h.get("story_text") or "") or (h.get("title") or "")
        if len(text) < 40:
            continue
        out.append(Item("D-020", "pain_quote", f"https://news.ycombinator.com/item?id={h['objectID']}",
                        h.get("title") or h.get("story_title") or "Hacker News comment", text,
                        _date(h.get("created_at")), {"points": h.get("points")}))
    return out


def stackexchange_search(query: str, site: str = "webapps", n: int = 6) -> list[Item]:
    d = _get("https://api.stackexchange.com/2.3/search/advanced",
             {"q": query, "site": site, "order": "desc", "sort": "relevance", "pagesize": n,
              "filter": "withbody"}).json()
    return [Item("R-073", "pain_quote", q["link"], _text(q.get("title", "")), _text(q.get("body", "")),
                 _date(q.get("creation_date")), {"score": q.get("score"), "site": site,
                                                 "licence": "CC BY-SA 4.0 (attribution: Stack Exchange user)"})
            for q in d.get("items", []) if q.get("body")]


def _gh_headers() -> dict:
    tok = os.environ.get("GITHUB_TOKEN")
    return {"Authorization": f"Bearer {tok}"} if tok else {}


def github_issues(query: str, n: int = 6) -> list[Item]:
    d = _get("https://api.github.com/search/issues",
             {"q": f"{query} is:issue", "sort": "reactions", "order": "desc", "per_page": n},
             _gh_headers()).json()
    return [Item("R-074", "pain_quote", i["html_url"], i.get("title", ""),
                 normalise((i.get("body") or "")[:3000]) or i.get("title", ""), _date(i.get("created_at")),
                 {"reactions": (i.get("reactions") or {}).get("total_count")})
            for i in d.get("items", [])]


def appstore_reviews(app_id: int | str, country: str = "us", n: int = 10) -> list[Item]:
    url = f"https://itunes.apple.com/{country.lower()}/rss/customerreviews/id={app_id}/sortby=mostrecent/json"
    entries = (_get(url).json().get("feed") or {}).get("entry") or []
    if isinstance(entries, dict):
        entries = [entries]
    app_url = f"https://apps.apple.com/{country.lower()}/app/id{app_id}"
    out = []
    for e in entries[:n]:
        text = ((e.get("content") or {}).get("label") or "").strip()
        if len(text) < 30:
            continue
        out.append(Item("R-069", "pain_quote", app_url, ((e.get("title") or {}).get("label") or "App Store review"),
                        text, _date((e.get("updated") or {}).get("label")),
                        {"rating": (e.get("im:rating") or {}).get("label"), "review_feed": url}))
    return out


# ---------- competitors and prices ----------

def itunes_search(term: str, country: str = "us", n: int = 8) -> list[Item]:
    d = _get("https://itunes.apple.com/search",
             {"term": term, "entity": "software", "country": country.lower(), "limit": n}).json()
    out = []
    for a in d.get("results", []):
        out.append(Item("D-001", "competitor", a["trackViewUrl"].split("?")[0], a.get("trackName", ""),
                        normalise(a.get("description", ""))[:1500], _date(a.get("currentVersionReleaseDate")),
                        {"price": a.get("price"), "currency": a.get("currency"),
                         "formatted_price": a.get("formattedPrice"), "rating_count": a.get("userRatingCount"),
                         "rating": a.get("averageUserRating"), "genre": a.get("primaryGenreName"),
                         "app_id": a.get("trackId"), "in_app_purchases": bool(a.get("isGameCenterEnabled"))}))
    return out


def wordpress_plugins(search: str, n: int = 6) -> list[Item]:
    d = _get("https://api.wordpress.org/plugins/info/1.2/",
             {"action": "query_plugins", "request[search]": search, "request[per_page]": n}).json()
    return [Item("D-022", "competitor", f"https://wordpress.org/plugins/{p['slug']}/", unescape(p.get("name", "")),
                 _text(p.get("short_description", "")), _date((p.get("last_updated") or "")[:10]),
                 {"active_installs": p.get("active_installs"), "rating": p.get("rating"),
                  "num_ratings": p.get("num_ratings"), "price": 0, "currency": "USD",
                  "formatted_price": "free (plugin directory)"})
            for p in d.get("plugins", [])]


def github_repos(query: str, n: int = 5) -> list[Item]:
    d = _get("https://api.github.com/search/repositories",
             {"q": query, "sort": "stars", "order": "desc", "per_page": n}, _gh_headers()).json()
    return [Item("R-074", "competitor", r["html_url"], r["full_name"], r.get("description") or "",
                 _date(r.get("pushed_at")), {"stars": r.get("stargazers_count"), "price": 0, "currency": "USD",
                                            "formatted_price": "free (open source)", "licence":
                                                (r.get("license") or {}).get("spdx_id")})
            for r in d.get("items", [])]


# ---------- digital reach ----------

def wdi_indicator(country: str, indicator: str = "IT.NET.USER.ZS") -> Item | None:
    api = (f"https://api.worldbank.org/v2/country/{quote(country)}/indicator/{indicator}"
           f"?format=json&mrv=5")
    data = _get(api).json()
    rows = [r for r in (data[1] if isinstance(data, list) and len(data) > 1 and data[1] else []) if r["value"]]
    if not rows:
        return None
    r = rows[0]
    page = f"https://data.worldbank.org/indicator/{indicator}?locations={country}"
    return Item("R-001", "statistic", page, f"{r['indicator']['value']} - {r['country']['value']} {r['date']}",
                f"{r['indicator']['value']}, {r['country']['value']}, {r['date']}: {r['value']:.1f}",
                date(int(r["date"]), 12, 31), {"value": r["value"], "year": int(r["date"]), "api": api})
