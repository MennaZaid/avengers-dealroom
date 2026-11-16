"""Convert the team's source_registry_seed.xlsx into YAML seed files under config/sources/.

Usage: python scripts/import_seed.py path/to/source_registry_seed.xlsx

The YAML files are only the *seed*: `db/seed.py` loads them into Postgres once, and after that
admins add or remove sources through the admin API. Re-running this script overwrites the YAML.
"""

import sys
from datetime import date
from pathlib import Path

import openpyxl
import yaml

OUT = Path(__file__).resolve().parents[1] / "config" / "sources"
TABS = {
    "registry": "registry_seed.yaml",
    "corpus": "corpus_seed.yaml",
    "discovery_rules": "discovery_rules.yaml",
    "tech_candidates": "tech_candidates.yaml",
}


def rows(ws):
    it = ws.iter_rows(values_only=True)
    header = [str(h).strip() for h in next(it) if h is not None]
    for r in it:
        if not any(c is not None for c in r):
            continue
        rec = {h: v for h, v in zip(header, r)}
        yield {k: (v.strip() if isinstance(v, str) else v) for k, v in rec.items()}


def main(xlsx: str) -> None:
    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    for tab, fname in TABS.items():
        data = list(rows(wb[tab]))
        header = (
            f"# Generated from {Path(xlsx).name} tab '{tab}' on {date.today()} by scripts/import_seed.py.\n"
            "# Seed list written from memory and NOT yet verified: every URL and license is a claim to check.\n"
        )
        (OUT / fname).write_text(
            header + yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=120), encoding="utf-8"
        )
        print(f"{tab}: {len(data)} rows -> {fname}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
