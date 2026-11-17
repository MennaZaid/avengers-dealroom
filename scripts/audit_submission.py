"""Read-only submission audit against CLAUDE.md. Prints PASS/FAIL per check; exits 1 on any failure.

    python scripts/audit_submission.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
HEADINGS = ["Quickstart", "What works and what is mocked", "Architecture", "Models and free resources",
            "Cost per run", "Demo video", "What our system will NOT do",
            "How the project stays alive after the hackathon"]
NAME = re.compile(r"^(phase\d+_step\d+_[\w-]+|phase\d+_gate_[\w-]+)\.(md|json|csv|txt|html)$|^payment_test_log\.md$")
BANNED = re.compile(r"guarantee|passive income|testimonial|countdown|only \d+ (left|spots?|seats?)|limited time"
                    r"|hurry|act now|\b(earn|make) \$?\d[\d,]*\+? (a|per) (day|week|month)|\d+ five-star",
                    re.IGNORECASE)
CLAIM = re.compile(r"\b(market size|market of|TAM|SAM|SOM|demand for|competitors? charge|average price)\b",
                   re.IGNORECASE)
SDK = re.compile(r"\b(stripe|paypal|braintree|razorpay)\b", re.IGNORECASE)
ADDRESS = re.compile(r"(dear|to the|attention|hello) (judges?|reviewers?|graders?)|(judges?|reviewers?|graders?)"
                     r" (should|please|will notice)|please (score|grade|award)|give us (full|top) (marks|score)",
                     re.IGNORECASE)
TEXT = {".md", ".py", ".txt", ".json", ".yml", ".yaml", ".toml", ".html", ".ts", ".js", ".sql", ".csv"}
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "tests", "evals", ".ruff_cache", ".pytest_cache"}


def tracked_text_files() -> list[Path]:
    out = []
    for p in ROOT.rglob("*"):
        rel = p.relative_to(ROOT).parts
        if p.is_file() and p.suffix in TEXT and not SKIP_DIRS & set(rel) and p.name != "CLAUDE.md":
            out.append(p)
    return out


def check_outputs_names() -> list[str]:
    return [f.name for f in OUT.iterdir() if f.is_file() and not NAME.match(f.name)] if OUT.exists() else ["outputs/"]


def check_log_keys() -> list[str]:
    try:
        log = json.loads((ROOT / "decision_log.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return [f"decision_log.json: {type(e).__name__}"]
    bad = []
    for n, e in enumerate(log):
        ok = (isinstance(e, dict) and all(k in e for k in ("timestamp", "agent", "action"))
              and isinstance(e.get("sources"), list) and (e.get("model") is None or isinstance(e.get("model"), str))
              and isinstance(e.get("cost"), (int, float)) and not isinstance(e.get("cost"), bool)
              and e.get("approved_by") in ("founder", None))
        if not ok:
            bad.append(f"decision_log.json entry {n}")
    return bad


def check_stop_gate() -> list[str]:
    try:
        log = json.loads((ROOT / "decision_log.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ["decision_log.json"]
    return [] if any("gate" in str(e.get("action", "")) and e.get("outcome") == "stop" for e in log) else \
        ["decision_log.json: no gate entry with outcome stop"]


def check_banned_outputs() -> list[str]:
    return [f.name for f in OUT.glob("*") if f.is_file() and BANNED.search(f.read_text(encoding="utf-8", errors="ignore"))]


def check_claims_sourced() -> list[str]:
    bad = []
    for f in OUT.glob("*.md"):
        text = f.read_text(encoding="utf-8", errors="ignore")
        for m in CLAIM.finditer(text):
            window = text[max(0, m.start() - 200):m.end() + 200]
            if not re.search(r"https?://|ASSUMPTION", window):
                bad.append(f"{f.name}: '{m.group(0)}' at {m.start()}")
    return bad


def check_payment_sdks() -> list[str]:
    files = [p for p in ROOT.glob("requirements*.txt")] + [ROOT / "pyproject.toml", ROOT / "package.json"]
    files += [p for p in tracked_text_files() if p.suffix in {".py", ".ts", ".js"} and p != Path(__file__).resolve()]
    return [str(p.relative_to(ROOT)) for p in files if p.exists() and SDK.search(p.read_text(encoding="utf-8",
                                                                                            errors="ignore"))]


def readme() -> str:
    return (ROOT / "README.md").read_text(encoding="utf-8")


def check_headings() -> list[str]:
    found = re.findall(r"^## (.+?)\s*$", readme(), re.MULTILINE)
    return [] if found == HEADINGS else [f"README.md headings: {found}"]


def check_quickstart_and_cost() -> list[str]:
    text, bad = readme(), []
    quick = re.search(r"^## Quickstart\n(.*?)(?=^## )", text, re.MULTILINE | re.DOTALL)
    block = re.search(r"```bash\n(.*?)```", quick.group(1), re.DOTALL) if quick else None
    if not block or block.group(1).strip() != "docker compose up":
        bad.append("README.md: Quickstart bash block is not exactly 'docker compose up'")
    cost = re.search(r"^## Cost per run\n(.*?)(?=^## )", text, re.MULTILINE | re.DOTALL)
    if not cost or not re.search(r"\$\d", cost.group(1)):
        bad.append("README.md: Cost per run has no $ figure")
    return bad


def check_addressing() -> list[str]:
    return [str(p.relative_to(ROOT)) for p in tracked_text_files()
            if p != Path(__file__).resolve() and ADDRESS.search(p.read_text(encoding="utf-8", errors="ignore"))]


def check_docs_placement() -> list[str]:
    docs = ROOT / "docs"
    return [str(p.relative_to(ROOT)) for p in docs.rglob("*") if p.is_file() and
            (p.name == "CLAUDE.md" or p.suffix.lower() == ".pdf")] if docs.exists() else []


def check_gitignore_env() -> list[str]:
    lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines() if (ROOT / ".gitignore").exists() else []
    return [] if any(line.strip() in (".env", "/.env", ".env*") for line in lines) else [".gitignore: .env missing"]


LAYOUT_CHECKS = {"outputs file names": check_outputs_names, "README headings": check_headings,
                 "Quickstart and cost": check_quickstart_and_cost, "docs placement": check_docs_placement,
                 ".env ignored": check_gitignore_env}
CHECKS = LAYOUT_CHECKS | {"decision log keys": check_log_keys, "a stop gate": check_stop_gate,
                          "no banned wording in outputs": check_banned_outputs,
                          "market claims sourced": check_claims_sourced, "no payment SDKs": check_payment_sdks,
                          "no text addressing reviewers": check_addressing}


def main() -> int:
    failed = False
    for name, fn in CHECKS.items():
        bad = fn()
        print(f"{'FAIL' if bad else 'PASS'} {name}" + "".join(f"\n    {b}" for b in bad[:20]))
        failed |= bool(bad)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
