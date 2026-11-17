"""Evidence items: what each phase found, in one format later phases can read.

Phase 1 (Discover) and Phase 2 (Validate) write items; Phase 3 (Build) reads them.

    from venture_os import evidence
    evidence.add(brief_id, [evidence.Item(phase=1, kind="pain", text="Families can't find reliable cleaners",
                                          label="evidenced", sources=["https://..."], date="2026-11-17",
                                          quote="...")])
    items = evidence.load(brief_id)

Labels: evidenced (needs at least one source URL), founder_stated (the founder said it), inferred (deduced from
something stated), assumption (nobody has checked it yet). Stored per brief in RUNS_DIR/<brief_id>/evidence.json
(default runs/, git-ignored; tests use a temporary folder).
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, model_validator

Label = Literal["evidenced", "founder_stated", "inferred", "assumption"]
Kind = Literal["idea", "pain", "customer", "supply", "demand", "competitor", "price", "market", "revenue",
               "constraint", "claim", "other"]
LABEL_TEXT = {"evidenced": "EVIDENCED", "founder_stated": "FOUNDER-STATED", "inferred": "INFERRED",
              "assumption": "ASSUMPTION"}
_lock = threading.Lock()


class Item(BaseModel):
    id: str = ""  # assigned on add(): E1, E2, ...
    phase: int  # 0 = founder brief, 1 = Discover, 2 = Validate
    kind: Kind = "claim"
    text: str
    label: Label
    sources: list[str] = []
    date: str | None = None  # publication or retrieval date of the source
    quote: str | None = None  # exact words from the source or the founder

    @model_validator(mode="after")
    def _evidenced_needs_a_source(self):
        if self.label == "evidenced" and not any(u.startswith(("http://", "https://")) for u in self.sources):
            raise ValueError("an 'evidenced' item needs at least one source URL; otherwise label it assumption")
        return self

    def tag(self) -> str:
        return f"[{self.id}, {LABEL_TEXT[self.label]}]" if self.id else f"[{LABEL_TEXT[self.label]}]"


def runs_dir() -> Path:
    return Path(os.environ.get("RUNS_DIR", "runs"))


def _path(brief_id: str) -> Path:
    return runs_dir() / str(brief_id) / "evidence.json"


def load(brief_id: str) -> list[Item]:
    p = _path(brief_id)
    if not p.exists():
        return []
    return [Item.model_validate(d) for d in json.loads(p.read_text(encoding="utf-8"))]


def add(brief_id: str, items: list[Item]) -> list[Item]:
    """Append items for a brief; ids continue from the existing ones. Returns the stored items."""
    with _lock:
        existing = load(brief_id)
        n = len(existing)
        added = [it.model_copy(update={"id": f"E{n + i + 1}"}) for i, it in enumerate(items)]
        p = _path(brief_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps([i.model_dump() for i in existing + added], ensure_ascii=False, indent=2),
                     encoding="utf-8")
    return added
