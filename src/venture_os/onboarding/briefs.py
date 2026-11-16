"""The hand-off from onboarding to the pipeline: a confirmed, versioned founder brief.

    from venture_os.onboarding.briefs import load_brief, is_stale
    brief = load_brief(brief_id)            # latest confirmed version (or version=N)
    brief.known("budget")                   # the founder's words, or None if unknown (never fill it in)
    brief.budget                            # {"min", "max", "currency", "currency_source"} or None
    brief.tag("country_code")               # "EG", "KE", ... or "unknown"
    brief.allowed                           # False for excluded products: the pipeline must stop
    is_stale(brief_id, version_used)        # True when the founder saved a newer version

The same data is served over HTTP by GET /onboarding/briefs/{id}.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel


class ConfirmedBrief(BaseModel):
    brief_id: str
    version: int
    fields: dict[str, dict]  # name -> {value, status, source, quote}; status "unknown" = unknown
    tags: dict[str, dict]  # name -> {value, basis}
    followups: list[dict] = []  # [{question, answer, source}]
    open_questions: list[str] = []  # research questions for Discover
    product_check: dict = {}  # {status: allowed|review|excluded, categories, matched}
    budget: dict | None = None  # parsed budget or None

    def known(self, name: str) -> str | None:
        """The value if the founder gave it (or confirmed it), else None. Never invent unknown values."""
        f = self.fields.get(name) or {}
        return f.get("value") if f.get("status") != "unknown" and f.get("value") else None

    def tag(self, name: str):
        return (self.tags.get(name) or {}).get("value", "unknown")

    @property
    def allowed(self) -> bool:
        return self.product_check.get("status") != "excluded"

    @property
    def unknown_fields(self) -> list[str]:
        return [n for n in self.fields if self.known(n) is None]

    @classmethod
    def from_file(cls, path: str | Path) -> ConfirmedBrief:
        """Load a saved brief (e.g. tests/fixtures/briefs/*.json) without a database."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.model_validate({k: v for k, v in data.items() if k in cls.model_fields})


_COLUMNS = "version, fields, tags, followups, open_questions, product_check, budget"


def load_brief(brief_id: UUID | str, version: int | None = None) -> ConfirmedBrief:
    """Read a confirmed brief from Postgres (latest version unless `version` is given). KeyError if missing."""
    from venture_os.api.db import connect

    with connect("vos_app") as conn:
        if version is None:
            row = conn.execute(f"SELECT {_COLUMNS} FROM brief_versions WHERE brief_id = %s "
                               "ORDER BY version DESC LIMIT 1", (str(brief_id),)).fetchone()
        else:
            row = conn.execute(f"SELECT {_COLUMNS} FROM brief_versions WHERE brief_id = %s AND version = %s",
                               (str(brief_id), version)).fetchone()
    if not row:
        raise KeyError(f"brief {brief_id} version {version or 'latest'} not found")
    return ConfirmedBrief(brief_id=str(brief_id), **row)


def latest_version(brief_id: UUID | str) -> int | None:
    from venture_os.api.db import connect

    with connect("vos_app") as conn:
        row = conn.execute("SELECT max(version) AS v FROM brief_versions WHERE brief_id = %s",
                           (str(brief_id),)).fetchone()
    return row["v"] if row else None


def is_stale(brief_id: UUID | str, version_used: int) -> bool:
    """A stage run that used `version_used` is stale once the founder saved a newer version."""
    latest = latest_version(brief_id)
    return latest is not None and latest > version_used
