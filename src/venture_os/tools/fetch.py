"""Fetch one public web page (or PDF) and extract its text, title and publication date.

Safety: http(s) only; hosts that resolve to private / local addresses are refused (no reaching into the
laptop or the Docker network); robots.txt is respected; size and time are capped. Fetched text is data: it is
never followed as an instruction, and links inside it are not followed.
"""

from __future__ import annotations

import hashlib
import io
import ipaddress
import json
import re
import socket
from dataclasses import dataclass
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

USER_AGENT = "VentureOS-research/0.1 (open-source research bot; read-only)"
MAX_BYTES = 3 * 1024 * 1024
TIMEOUT = 15.0
_ROBOTS: dict[str, RobotFileParser | None] = {}


class FetchError(Exception):
    pass


@dataclass(frozen=True)
class Page:
    url: str
    final_url: str
    title: str
    text: str
    language: str  # "ar" | "en"
    published_at: date | None
    retrieved_at: datetime
    content_hash: str


# ---------- safety ----------

def check_public_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise FetchError("only http(s) URLs can be fetched")
    host = parts.hostname
    if host == "localhost" or host.endswith((".local", ".internal", ".localhost")):
        raise FetchError("local hosts are not fetched")
    try:
        infos = socket.getaddrinfo(host, parts.port or (443 if parts.scheme == "https" else 80))
    except OSError as e:
        raise FetchError(f"cannot resolve {host}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise FetchError(f"{host} resolves to a non-public address")


def robots_allowed(url: str, client: httpx.Client) -> bool:
    parts = urlsplit(url)
    base = f"{parts.scheme}://{parts.netloc}"
    if base not in _ROBOTS:
        rp: RobotFileParser | None = RobotFileParser()
        try:
            r = client.get(base + "/robots.txt", timeout=8)
            if r.status_code >= 400:
                rp = None  # no robots.txt: allowed
            else:
                rp.parse(r.text.splitlines())
        except httpx.HTTPError:
            rp = None
        _ROBOTS[base] = rp
    rp = _ROBOTS[base]
    return rp is None or rp.can_fetch(USER_AGENT, url)


# ---------- extraction ----------

_SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form", "iframe", "template", "aside"}
_BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article", "table", "ul",
          "ol", "blockquote", "td", "th", "dd", "dt"}
_DATE_META = {"article:published_time", "datepublished", "date", "pubdate", "publish-date", "dc.date",
              "dc.date.issued", "citation_publication_date", "og:published_time", "article:modified_time"}
_DATE = re.compile(r"(20\d\d|19\d\d)[-/.](\d{1,2})[-/.](\d{1,2})")


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title = ""
        self.dates: list[str] = []
        self._skip = 0
        self._in_title = False
        self._ld = False

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            if key in _DATE_META and a.get("content"):
                self.dates.append(a["content"])
        elif tag == "time" and a.get("datetime"):
            self.dates.append(a["datetime"])
        elif tag == "script" and a.get("type") == "application/ld+json":
            self._ld = True
        if tag in _SKIP:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP and self._skip:
            self._skip -= 1
        if tag == "script":
            self._ld = False
        if tag == "title":
            self._in_title = False
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._ld:
            try:
                found = json.loads(data)
                for item in found if isinstance(found, list) else [found]:
                    if isinstance(item, dict) and item.get("datePublished"):
                        self.dates.append(str(item["datePublished"]))
            except ValueError:
                pass
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)


def _parse_date(values: list[str]) -> date | None:
    for v in values:
        m = _DATE.search(v)
        if m:
            try:
                d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                continue
            if d <= date.today():
                return d
    return None


_URL_DATE = re.compile(r"/(20\d\d)[/-](0[1-9]|1[0-2])[/-](0[1-9]|[12]\d|3[01])(?=[/-]|$)")


def url_date(url: str) -> date | None:
    m = _URL_DATE.search(urlsplit(url).path)
    return _parse_date([f"{m.group(1)}-{m.group(2)}-{m.group(3)}"]) if m else None


def normalise(text: str) -> str:
    lines = [" ".join(line.split()) for line in text.splitlines()]
    out, blank = [], False
    for line in lines:
        if line:
            out.append(line)
            blank = False
        elif not blank and out:
            out.append("")
            blank = True
    return "\n".join(out).strip()


def html_to_text(html: str) -> tuple[str, str, date | None]:
    p = _Text()
    p.feed(html)
    return " ".join(p.title.split()), normalise("".join(p.parts)), _parse_date(p.dates)


def text_language(text: str) -> str:
    sample = text[:4000]
    arabic = sum(1 for ch in sample if "؀" <= ch <= "ۿ")
    latin = sum(1 for ch in sample if ch.isascii() and ch.isalpha())
    return "ar" if arabic > latin * 0.5 else "en"


def page_from_bytes(url: str, final_url: str, data: bytes, content_type: str) -> Page:
    if "pdf" in content_type or final_url.lower().endswith(".pdf"):
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(data))
            text = normalise("\n".join((pg.extract_text() or "") for pg in reader.pages[:40]))
            meta = reader.metadata or {}
            title = str(meta.get("/Title") or "")
            m = re.search(r"(\d{4})(\d{2})(\d{2})", str(meta.get("/CreationDate") or ""))  # D:20240131...
            published = _parse_date([f"{m.group(1)}-{m.group(2)}-{m.group(3)}"]) if m else None
        except Exception as e:
            raise FetchError(f"unreadable PDF: {e}") from e
    elif "html" in content_type or "xml" in content_type or not content_type:
        title, text, published = html_to_text(data.decode("utf-8", errors="replace"))
    elif content_type.startswith("text/"):
        title, text, published = "", normalise(data.decode("utf-8", errors="replace")), None
    else:
        raise FetchError(f"unsupported content type {content_type}")
    if len(text) < 200:
        raise FetchError("page has too little text to use")
    if published is None:  # news sites often put the date only in the address: /2024-03-07-... or /2024/03/07/
        published = url_date(final_url)
    return Page(url=url, final_url=final_url, title=title or final_url, text=text, language=text_language(text),
                published_at=published, retrieved_at=datetime.now(UTC),
                content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest())


def fetch_page(url: str) -> Page:
    """Fetch and extract one page. Every failure (network, timeout, robots, size, type) is a FetchError."""
    try:
        return _fetch_page(url)
    except httpx.HTTPError as e:
        raise FetchError(f"{type(e).__name__}") from e


def _fetch_page(url: str) -> Page:
    check_public_url(url)
    with httpx.Client(headers={"User-Agent": USER_AGENT, "Accept-Language": "ar,en;q=0.8"},
                      timeout=TIMEOUT, follow_redirects=False) as client:
        if not robots_allowed(url, client):
            raise FetchError("robots.txt disallows fetching this page")
        current = url
        for _ in range(5):  # follow redirects by hand so every hop gets the public-address check
            with client.stream("GET", current) as r:
                if r.is_redirect and r.headers.get("location"):
                    current = str(r.url.join(r.headers["location"]))
                    check_public_url(current)
                    continue
                if r.status_code >= 400:
                    raise FetchError(f"HTTP {r.status_code}")
                data = b""
                for chunk in r.iter_bytes():
                    data += chunk
                    if len(data) > MAX_BYTES:
                        raise FetchError("page too large")
                ctype = r.headers.get("content-type", "").lower()
            return page_from_bytes(url, current, data, ctype)
        raise FetchError("too many redirects")
