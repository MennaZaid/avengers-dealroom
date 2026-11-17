"""Evidence Extractor: claims with an exact quote from a stored chunk.

Rules mode (no model): a claim is a sentence copied verbatim from the page, chosen because it shares words with
the research query (and, for numeric topics, contains a number). Nothing is paraphrased.
Model mode: the model proposes claims, but a claim is kept only if its quote is found word for word in the
chunk. The fetched text is passed as data, never as instructions.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable

from venture_os.evidence.store import StoredChunk
from venture_os.prompts import load_prompt

ChatFn = Callable[[list[dict]], str]
NUMERIC_TOPICS = {"market_size", "pricing"}
_SENT = re.compile(r"(?<=[.!?؟])\s+|\n+")
_DIGIT = re.compile(r"[0-9٠-٩]")
_WORD = re.compile(r"[\w؀-ۿ]+")
_STOP = {"the", "and", "for", "with", "from", "that", "this", "are", "was", "how", "what", "many", "much",
         "في", "من", "على", "إلى", "الى", "عن", "مع", "هل", "ما", "كم", "التي", "الذي", "هي", "هو"}


def terms(text: str) -> set[str]:
    out = set()
    for w in _WORD.findall(text.lower()):
        if len(w) < 3 or w in _STOP:
            continue
        out.add(w[2:] if w.startswith("ال") and len(w) > 4 else w)  # Arabic: drop the article
    return out


def _norm(s: str) -> str:
    return " ".join(s.split())


def quote_in(quote: str, text: str) -> bool:
    return bool(quote.strip()) and _norm(quote) in _norm(text)


def rule_claims(chunk: StoredChunk, topic: str, query: str, limit: int = 2) -> list[dict]:
    want = terms(query)
    scored = []
    for sent in _SENT.split(chunk.text):
        s = sent.strip()
        if not (40 <= len(s) <= 400):
            continue
        overlap = len(want & terms(s))
        if topic in NUMERIC_TOPICS and not _DIGIT.search(s):
            continue
        if overlap >= min(2, len(want)):
            scored.append((overlap + (1 if _DIGIT.search(s) else 0), s))
    scored.sort(key=lambda x: -x[0])
    return [{"text": s, "quote": s, "type": "fact", "extracted_by": "rules"} for _, s in scored[:limit]]


_SYSTEM = load_prompt("evidence_extractor")


def model_claims(chunk: StoredChunk, topic: str, query: str, chat: ChatFn, limit: int = 3) -> list[dict]:
    msg = f"Research question: {query}\n<document>\n{chunk.text}\n</document>"
    try:
        data = json.loads(chat([{"role": "system", "content": _SYSTEM}, {"role": "user", "content": msg}]))
    except Exception:  # noqa: BLE001 - a bad model answer falls back to rules
        return rule_claims(chunk, topic, query)
    out = []
    for c in (data.get("claims") or [])[:limit] if isinstance(data, dict) else []:
        if not isinstance(c, dict):
            continue
        quote, text = str(c.get("quote") or ""), str(c.get("claim") or "")
        if text and quote_in(quote, chunk.text):  # grounded, or dropped
            out.append({"text": text, "quote": _norm(quote), "type": "fact", "extracted_by": "model"})
    return out
