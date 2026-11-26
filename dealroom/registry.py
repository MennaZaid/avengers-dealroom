"""The team's source registry (from the hackathon), tiered A (official / peer-reviewed) > B (established) > C.
Used by the research agent to search trusted sources first, and to tag every cited URL with its tier."""
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse
import yaml

REG = Path(__file__).resolve().parent.parent / "data" / "registry"


def _domain(url: str) -> str:
    d = urlparse(url if "://" in url else "https://" + url).netloc.lower()
    return d[4:] if d.startswith("www.") else d


@lru_cache(maxsize=1)
def sources() -> list[dict]:
    out, seen = [], set()
    for f in sorted(REG.glob("*.yaml")):
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or []
        if isinstance(data, dict):
            data = next((v for v in data.values() if isinstance(v, list)), [])
        for r in data:
            if not isinstance(r, dict) or not r.get("url") or "web.archive.org" in r["url"]:
                continue
            d = _domain(r["url"])
            if d in seen:
                continue
            seen.add(d)
            out.append({"id": r.get("id"), "name": r.get("source_name"), "domain": d, "tier": r.get("tier") or "C",
                        "scope": r.get("scope"), "coverage": r.get("coverage"), "provides": r.get("provides") or "",
                        "use": "analogy" if "case stud" in str(r.get("provides", "")).lower() or r.get("use") == "analogy" else "fact"})
    return out


def tier_of(url: str) -> str | None:
    d = _domain(url)
    for s in sources():
        if d == s["domain"] or d.endswith("." + s["domain"]):
            return s["tier"]
    return None


def catalogue(use: str = "fact", tiers=("A", "B")) -> str:
    return "\n".join(f"- {s['domain']} [{s['tier']}, {s['coverage'] or s['scope']}]: {s['name']}: {s['provides']}"
                     for s in sources() if s["use"] == use and s["tier"] in tiers)
