"""Load agent prompts from prompts/<name>.md (one file per agent prompt, as the hackathon layout asks).

Each file has a short header and a '## System prompt' section; only that section is sent to the model.
Placeholders use $name (string.Template), so JSON braces in a prompt need no escaping.
PROMPTS_DIR overrides the folder (e.g. inside Docker).
"""

from __future__ import annotations

import os
from functools import cache
from pathlib import Path
from string import Template

_DEFAULT_DIR = Path(__file__).resolve().parents[2] / "prompts"
_MARKER = "## System prompt"


def prompts_dir() -> Path:
    return Path(os.environ.get("PROMPTS_DIR", _DEFAULT_DIR))


@cache
def _read(path: str) -> str:
    text = Path(path).read_text(encoding="utf-8")
    if _MARKER not in text:
        raise ValueError(f"{path} has no '{_MARKER}' section")
    return text.split(_MARKER, 1)[1].strip()


def load_prompt(name: str, **values: str) -> str:
    """The system prompt from prompts/<name>.md with $placeholders filled. Missing values raise KeyError."""
    return Template(_read(str(prompts_dir() / f"{name}.md"))).substitute(**values)
