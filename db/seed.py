"""Load the YAML seed files into Postgres.

Usage: python db/seed.py            (uses DATABASE_URL from .env / environment)

Run once on a fresh database, connected as the database owner (bootstrap). Re-running is safe:
existing ids are skipped, so an admin's later edits are never overwritten. Every inserted row is
logged in source_changes with admin_id='seed'.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import psycopg
import yaml

from venture_os.config import Settings

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "config" / "sources"
SCHEMA = ROOT / "db" / "schema.sql"
CATALOG = ROOT / "config" / "catalog"
SOURCE_FILES = ["registry_seed.yaml", "case_studies.yaml", "egypt.yaml", "digital.yaml"]
CORPUS_FILES = ["corpus_seed.yaml", "corpus_digital.yaml"]
# Changes to rows already in the database (product_scope, access, limitations, ...): applied through the logged
# admin path registry.update_source, never by direct UPDATE. Rows an admin edited by hand are left alone.
UPDATES_FILE = "registry_updates.yaml"
SYNC_FIELDS = ("product_scope", "access_type", "limitations", "license", "test_url", "industries")
RULE_FILES = ["discovery_rules.yaml", "discovery_rules_digital.yaml"]

COUNTRY_BY_COVERAGE = {"egypt": ["EG"], "kenya": ["KE"], "us": ["US"], "uk": ["GB"], "us-listed companies": ["US"]}
LEGAL_HINTS = re.compile(r"\b(laws?|legal|tax|vat|privacy)\b")  # whole words: "innovation" contains "vat"


def _crawl(e: dict) -> str:
    if e.get("crawl"):
        return e["crawl"]
    return "metadata" if (e.get("access_type") or "").lower() == "manual" else "full"


def _use(e: dict) -> str:
    if e.get("use"):
        return e["use"]
    text = str(e.get("provides") or "").lower()  # not notes: "high legal risk" is not legal content
    return "legal" if LEGAL_HINTS.search(text) else "market"


def source_row(e: dict) -> dict:
    cov = str(e.get("coverage") or "").strip().lower()
    return {
        "id": e["id"],
        "scope": e["scope"],
        "source_name": e["source_name"],
        "url": e.get("url"),
        "provides": e.get("provides"),
        "access_type": e.get("access_type"),
        "auth_needed": e.get("auth_needed"),
        "license": e.get("license"),
        "coverage": e.get("coverage"),
        "country_codes": COUNTRY_BY_COVERAGE.get(cov, []),
        "industries": list(e.get("industries") or []),
        "product_scope": e.get("product_scope") or "any",
        "limitations": e.get("limitations"),
        "test_url": e.get("test_url"),
        "update_frequency": e.get("update_frequency"),
        "max_age_months": e.get("max_age_months"),
        "tier": e["tier"],
        "crawl": _crawl(e),
        "use": _use(e),
        "verified": False,
        "url_status": e.get("url_status"),
        "http_status": e.get("http_status"),
        "tested_on": e.get("tested_on"),
        "notes": e.get("notes"),
        "created_by": "seed",
    }


def corpus_row(e: dict) -> dict:
    keys = ["id", "title", "author_publisher", "url", "year", "type", "topic", "license", "tier", "how_we_use_it", "status"]
    row = {k: e.get(k) for k in keys}
    row["created_by"] = "seed"
    return row


def _insert(cur, table: str, row: dict) -> bool:
    cols = ", ".join(row)
    vals = ", ".join(f"%({k})s" for k in row)
    cur.execute(f"INSERT INTO {table} ({cols}) VALUES ({vals}) ON CONFLICT (id) DO NOTHING", row)
    return cur.rowcount == 1


def load(conn: psycopg.Connection) -> dict[str, int]:
    counts = {"sources": 0, "corpus_items": 0, "skipped": 0}
    with conn.cursor() as cur:
        for fname in SOURCE_FILES:
            for e in yaml.safe_load((SRC / fname).read_text(encoding="utf-8")):
                row = source_row(e)
                if _insert(cur, "sources", row):
                    counts["sources"] += 1
                    cur.execute(
                        "INSERT INTO source_changes (source_id, action, admin_id, reason, after)"
                        " VALUES (%s, 'add', 'seed', %s, %s)",
                        (row["id"], f"initial seed from {fname}", json.dumps(row, default=str)),
                    )
                else:
                    counts["skipped"] += 1
        for fname in CORPUS_FILES:
            for e in yaml.safe_load((SRC / fname).read_text(encoding="utf-8")):
                if _insert(cur, "corpus_items", corpus_row(e)):
                    counts["corpus_items"] += 1
                else:
                    counts["skipped"] += 1
        counts["discovery_rules"] = 0
        for fname in RULE_FILES:
            for r in yaml.safe_load((SRC / fname).read_text(encoding="utf-8")):
                cur.execute(
                    "INSERT INTO discovery_rules (step, name, action, verification, output, product_scope, created_by)"
                    " VALUES (%s, %s, %s, %s, %s, %s, 'seed') ON CONFLICT (step) DO NOTHING",
                    (int(r["step"]), r["name"], r["what the agent does"], r.get("how it verifies"), r.get("output"),
                     r.get("product_scope", "any")))
                counts["discovery_rules"] += cur.rowcount
        counts["components"] = counts["model_endpoints"] = 0
        comps = yaml.safe_load((SRC / "tech_candidates.yaml").read_text(encoding="utf-8"))
        comps += yaml.safe_load((CATALOG / "components_extra.yaml").read_text(encoding="utf-8"))
        comps += yaml.safe_load((CATALOG / "models_reviewed.yaml").read_text(encoding="utf-8"))
        for e in comps:
            if _insert(cur, "components", component_row(e)):
                counts["components"] += 1
                _log_catalog(cur, "components", e["id"])
            else:
                counts["skipped"] += 1
        for e in yaml.safe_load((CATALOG / "model_endpoints.yaml").read_text(encoding="utf-8")):
            row = {**e, "created_by": "seed"}
            if _insert(cur, "model_endpoints", row):
                counts["model_endpoints"] += 1
                _log_catalog(cur, "model_endpoints", e["id"])
            else:
                counts["skipped"] += 1
    conn.commit()
    counts["sources_updated"] = sync_sources(conn)
    return counts


def sync_sources(conn: psycopg.Connection) -> int:
    """Bring rows already in the database in line with the YAML, through the logged admin path."""
    from venture_os.api.registry import update_source  # same function the admin route uses

    wanted: dict[str, tuple[dict, str]] = {}
    for fname in SOURCE_FILES:
        for e in yaml.safe_load((SRC / fname).read_text(encoding="utf-8")):
            fields = {k: e[k] for k in SYNC_FIELDS if k in e}
            if fields:
                wanted[e["id"]] = (fields, f"sync with config/sources/{fname}")
    for sid, e in (yaml.safe_load((SRC / UPDATES_FILE).read_text(encoding="utf-8")) or {}).items():
        reason = e.pop("reason")
        prev = wanted.get(sid, ({}, ""))[0]
        wanted[sid] = ({**prev, **{k: v for k, v in e.items() if k in SYNC_FIELDS}}, reason)
    changed = 0
    for sid, (fields, reason) in wanted.items():
        row = conn.execute("SELECT * FROM sources WHERE id = %s", (sid,)).fetchone()
        if row is None:
            continue
        cols = [d.name for d in conn.execute("SELECT * FROM sources LIMIT 0").description]
        current = dict(zip(cols, row, strict=True))
        diff = {k: v for k, v in fields.items() if (current.get(k) or ([] if k == "industries" else None)) != v}
        if not diff:
            continue
        hand_edited = conn.execute("SELECT 1 FROM source_changes WHERE source_id = %s AND admin_id <> 'seed'",
                                   (sid,)).fetchone()
        if hand_edited:
            print(f"skip {sid}: edited by an admin, not overwritten by the seed")
            continue
        update_source(sid, diff, "seed", reason)
        changed += 1
    return changed


def _log_catalog(cur, table: str, row_id: str) -> None:
    cur.execute(
        "INSERT INTO catalog_changes (table_name, row_id, action, admin_id, reason) VALUES (%s, %s, 'add', 'seed', %s)",
        (table, row_id, "initial seed"),
    )


OSI_PREFIXES = ("apache", "mit", "bsd", "postgresql", "lgpl", "agpl", "gpl", "mpl")
SELECTED = {"T-006", "T-007", "T-012", "T-014", "T-018", "T-101", "T-102", "T-103", "T-104", "T-105", "T-106"}
MODEL_KINDS = {"model", "embedding", "reranker", "classifier"}


def component_row(e: dict) -> dict:
    lic = str(e.get("license") or "").lower()
    if lic.startswith("custom"):
        osi = False
    elif lic.startswith(OSI_PREFIXES):
        osi = True
    else:
        osi = None
    return {
        "id": e["id"],
        "kind": e["kind"],
        "name": e["name"],
        "url": e.get("url"),
        "license": e.get("license"),
        "open_weight": e.get("open_weight", True if e["kind"] in MODEL_KINDS else None),
        "osi_open": e.get("osi_open", osi),
        "use": e.get("use"),
        "status": e.get("status") or ("selected" if e["id"] in SELECTED else "candidate"),
        "verified_on": e.get("verified_on"),
        "notes": e.get("notes"),
        "created_by": "seed",
    }


def main() -> None:
    with psycopg.connect(Settings().database_url) as conn:
        conn.execute(SCHEMA.read_text(encoding="utf-8"))
        conn.commit()
        print(load(conn))


if __name__ == "__main__":
    main()
