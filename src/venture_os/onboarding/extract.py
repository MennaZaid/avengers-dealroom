"""Pull brief fields out of founder messages and documents.

NullExtractor needs no model (zero cost): the chat still works, it just fills one field per answer.
LLMExtractor uses the configured model, and keeps a value only if its quote really appears in the text,
so a document cannot make the model invent a field it does not contain. A value the text implies but does not
state (country from a city name) is kept but marked inferred, so the founder confirms it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Protocol

from venture_os.onboarding.brief import FIELDS
from venture_os.onboarding.tags import country_code, mentions_country
from venture_os.prompts import load_prompt

Extracted = dict[str, dict]  # field -> {"value": str, "quote": str, "inferred": bool}


class Extractor(Protocol):
    def extract(self, text: str, kind: str) -> Extracted: ...


class NullExtractor:
    def extract(self, text: str, kind: str) -> Extracted:
        return {}


def system_prompt() -> str:
    """prompts/brief_extractor.md with the field list filled in."""
    return load_prompt("brief_extractor", fields="\n".join(f"- {f.name}: {f.description}" for f in FIELDS))


class LLMExtractor:
    def __init__(self, chat_json: Callable[[list[dict]], str], model: str | None = "model"):
        self.chat_json = chat_json
        self.model = model  # recorded in decision_log.json

    def extract(self, text: str, kind: str) -> Extracted:
        messages = [
            {"role": "system", "content": system_prompt()},
            {"role": "user", "content": f"Source type: {kind}\n<untrusted>\n{text[:60000]}\n</untrusted>"},
        ]
        try:
            raw = json.loads(self.chat_json(messages))
        except Exception:  # noqa: BLE001 - bad JSON, timeout, rate limit: the chat goes on without the model
            return {}
        if not isinstance(raw, dict):
            return {}
        known = {f.name for f in FIELDS}
        out: Extracted = {}
        norm_text = " ".join(text.split())
        for name, item in raw.items():
            if isinstance(item, str) and item.strip():
                # Small local models sometimes answer {"city": "Cairo"} without a quote. Keep such a value only
                # if it is word for word in the text (it is then its own quote); anything else is dropped.
                item = {"value": item, "quote": item, "inferred": False}
            if name not in known or not isinstance(item, dict):
                continue
            value, quote = str(item.get("value") or "").strip(), str(item.get("quote") or "").strip()
            # Models sometimes copy our wrapper tag into the quote ("<untrusted>marketplace ..."). Drop the tag;
            # the rest of the quote must still appear in the text exactly.
            quote = re.sub(r"</?untrusted>", "", quote).strip()
            if not value or not quote:
                continue
            if " ".join(quote.split()).casefold() not in norm_text.casefold():  # grounding: the quote must be real
                continue
            out[name] = {"value": value[:500], "quote": quote[:500], "inferred": _inferred(name, value, quote, item)}
        return out


def _inferred(name: str, value: str, quote: str, item: dict) -> bool:
    """Trust the model when it says 'inferred'. For country, also check ourselves: if the quote does not name the
    country (e.g. it only says 'Cairo'), the value was deduced."""
    if item.get("inferred") is True or str(item.get("inferred")).lower() == "true":
        return True
    if name == "country":
        code = country_code(value)
        return not (code and mentions_country(quote, code))
    return False
