"""Phase 3, step 5: QA and safety tests on the built MVP (the "passing tests" gate input).

Static checks on the HTML file (always) and, when Edge or Chrome is installed, a headless-browser check that
the page really builds its screens and banner. Failures make build_stage rebuild the MVP with fixed copy (the
only part a model wrote), then test again.

    report = mvp_tester.run(inputs, reqs, plan, page)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from pydantic import BaseModel

from venture_os.agents.build_inputs import BuildInputs
from venture_os.agents.mvp_planner import _FORBIDDEN_FIELD, MvpPlan
from venture_os.agents.product_spec import brief_values, key_terms, relevance
from venture_os.agents.requirements_mapper import Requirements
from venture_os.decision_log import log_action
from venture_os.guardrails import check_output
from venture_os.outputs import write_output

AGENT = "mvp_tester"
MAX_BYTES = 1_000_000
_EXTERNAL = re.compile(r'(src|href|action)\s*=\s*["\']?\s*(https?:|//)', re.IGNORECASE)
_DANGEROUS = ("fetch(", "XMLHttpRequest", "innerHTML", "outerHTML", "eval(", "new Function", "document.write",
              "<iframe", "WebSocket", "sendBeacon", "navigator.credentials")
_BROWSERS = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
             r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
             r"C:\Program Files\Google\Chrome\Application\chrome.exe", "msedge", "google-chrome", "chromium",
             "chromium-browser", "chrome"]


class Check(BaseModel):
    name: str
    passed: bool
    detail: str = ""


class TestReport(BaseModel):
    brief_id: str
    passed: bool
    checks: list[Check]
    browser: str | None = None  # browser used for the render check, or None if not run
    attempt: int = 1


def _config(page: str) -> dict | None:
    m = re.search(r'<script type="application/json" id="config">(.*?)</script>', page, re.DOTALL)
    try:
        return json.loads(m.group(1)) if m else None
    except json.JSONDecodeError:
        return None


def _browser() -> str | None:
    for b in _BROWSERS:
        if Path(b).exists() or shutil.which(b):
            return b if Path(b).exists() else shutil.which(b)
    return None


def browser_check(page: str, cfg: dict) -> Check | None:
    """Open the page in a headless browser and read the DOM it builds. None if no browser is installed."""
    exe = _browser()
    if not exe:
        return None
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "mvp.html"
        f.write_text(page, encoding="utf-8")
        try:
            r = subprocess.run([exe, "--headless=new", "--disable-gpu", "--no-sandbox", "--dump-dom", f.as_uri()],
                               check=False, capture_output=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as e:
            return Check(name="opens in a browser", passed=False, detail=f"browser did not run: {e}")
    dom = r.stdout.decode("utf-8", errors="replace")
    tabs = len(re.findall(r"<button[^>]*data-screen=", dom))
    shown = re.search(r'<section class="on" id="screen-(\w+)"', dom)
    ok = tabs == len(cfg["screens"]) and shown is not None and "MOCKED" in dom
    return Check(name="opens in a browser", passed=ok,
                 detail=f"{tabs} of {len(cfg['screens'])} screens as tabs; first screen "
                        f"{'shown' if shown else 'NOT shown'}; banner {'shown' if 'MOCKED' in dom else 'missing'}")


def check(inputs: BuildInputs, reqs: Requirements, plan: MvpPlan, page: str, use_browser: bool = True
          ) -> tuple[list[Check], str | None]:
    checks: list[Check] = []

    def add(name, ok, detail=""):
        checks.append(Check(name=name, passed=bool(ok), detail=detail))

    cfg = _config(page)
    add("page data readable", cfg is not None)
    if cfg is None:
        return checks, None
    add("brief id and version on the page", cfg.get("brief_id") == inputs.brief_id and inputs.brief_id in page)
    add("template matches the plan", cfg.get("template") == plan.template, cfg.get("template", ""))
    missing_screens = [s for s in plan.screens if s not in cfg.get("screens", {})]
    add("every planned screen is present", not missing_screens, ", ".join(missing_screens))
    labels = [f["label"] for f in cfg.get("fields", [])]
    missing_fields = [f.label for f in plan.fields if f.label not in labels]
    add("every planned field is present", not missing_fields, ", ".join(missing_fields))
    covered = {r for v in cfg.get("screen_requirements", {}).values() for r in v} | \
              {f.get("requirement") for f in cfg.get("fields", [])}
    uncovered = [r.id for r in reqs.items if r.priority == "must" and r.type == "feature" and r.id not in covered]
    add("every 'must' feature is in the product", not uncovered, ", ".join(uncovered))

    ext = _EXTERNAL.findall(page)
    add("nothing loaded from outside", not ext, f"{len(ext)} external reference(s)" if ext else "")
    bad = [d for d in _DANGEROUS if d in page]
    add("no network calls or code injection points", not bad, ", ".join(bad))
    forbidden = [lab for lab in labels if _FORBIDDEN_FIELD.search(lab)]
    add("no password, card or medical fields", not forbidden, ", ".join(forbidden))
    unlabelled = [f["label"] for f in cfg.get("fields", []) if re.search(r"\b(pay|price|fee)\b|دفع|سعر|رسوم",
                                                                         f["label"], re.IGNORECASE) and not f.get("mocked")]
    add("payment fields marked MOCKED", not unlabelled, ", ".join(unlabelled))
    add("MVP / MOCKED banner present", "MOCKED" in cfg.get("texts", {}).get("banner", ""))
    texts = [cfg.get("title", ""), cfg.get("tagline", "")] + labels + \
            [v for v in cfg.get("texts", {}).values() if isinstance(v, str)] + \
            list(cfg.get("texts", {}).get("help", {}).values())
    broken = [(t[:40], r) for t in texts for r in check_output(t)]
    add("no must-never text (income promises, fake reviews, urgency)", not broken,
        "; ".join(f"{t} ({r})" for t, r in broken))
    size = len(page.encode("utf-8"))
    add("file size is reasonable", size < MAX_BYTES, f"{size:,} bytes")
    add("right-to-left for an Arabic brief", inputs.lang != "ar" or 'dir="rtl"' in page)

    checks.extend(product_checks(inputs, cfg, page))
    used = None
    if use_browser:
        bc = browser_check(page, cfg)
        if bc is not None:
            checks.append(bc)
            used = _browser()
    return checks, used


_BUTTON = re.compile(r'el\("button", \{[^\n]*')


def product_checks(inputs: BuildInputs, cfg: dict, page: str, terms: list[str] | None = None) -> list[Check]:
    """Checks computed from THIS brief at run time: is the page about the founder's product, and does it work."""
    out = []
    spec = cfg.get("spec") or {}
    core = spec.get("core") or {}
    visible = " ".join([cfg.get("title", ""), core.get("object", "")] +
                       [o.get("name", "") for o in spec.get("offers", [])])  # title, offer names, core action
    terms = terms if terms is not None else key_terms(brief_values(inputs))
    ok, hits = relevance(terms, visible)
    out.append(Check(name="about this brief (key terms in title, offers and core action)", passed=ok,
                     detail=f"{len(hits)} of {len(terms)} key terms: {', '.join(hits) or '-'}"))
    wired = bool(core.get("fields")) and "data-core-output" in page and 'addEventListener("input", draw)' in page \
        and "product" in cfg.get("screens", {})
    out.append(Check(name="core action is wired (input changes the page)", passed=wired,
                     detail=f"{len(core.get('fields', []))} input(s) -> live preview" if wired else "no core action"))
    buttons = _BUTTON.findall(page)
    loose = [b[:50] for b in buttons if "on: {" not in b and 'type: "submit"' not in b]
    out.append(Check(name="every button has a handler", passed=bool(buttons) and not loose,
                     detail=f"{len(buttons)} button(s)" + (f"; no handler: {loose}" if loose else "")))
    t = cfg.get("texts", {})
    unlabelled = [k for k in ("buy", "deliver", "waitlist", "bought", "joined") if "MOCKED" not in t.get(k, "")]
    out.append(Check(name="buy, delivery and waitlist labelled MOCKED", passed=not unlabelled,
                     detail=", ".join(unlabelled)))
    node = shutil.which("node")
    if node:
        m = re.search(r"<script>(.*?)</script>", page, re.DOTALL)
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "page.js"
            f.write_text(m.group(1) if m else "", encoding="utf-8")
            r = subprocess.run([node, "--check", str(f)], check=False, capture_output=True, timeout=30)
        out.append(Check(name="no JavaScript syntax error", passed=r.returncode == 0,
                         detail=r.stderr.decode("utf-8", "replace")[:120]))
    return out


def to_markdown(rep: TestReport) -> str:
    lines = ["# Phase 3, step 6: MVP test report", "", f"Brief id: `{rep.brief_id}`", "",
             (f"**Result:** {'ALL PASSED' if rep.passed else 'FAILED'} (attempt {rep.attempt}). Browser check: "
             f"{'run with ' + Path(rep.browser).name if rep.browser else 'not run (no Edge or Chrome found)'}."), "",
             "| Check | Result | Detail |", "|---|---|---|"]
    lines += [f"| {c.name} | {'pass' if c.passed else '**FAIL**'} | {c.detail.replace('|', '/')} |" for c in rep.checks]
    return "\n".join(lines) + "\n"


def run(inputs: BuildInputs, reqs: Requirements, plan: MvpPlan, page: str, attempt: int = 1,
        use_browser: bool | None = None, require_model: bool = False) -> TestReport:
    if use_browser is None:
        use_browser = os.environ.get("MVP_BROWSER_CHECK", "1") != "0"
    checks, used = check(inputs, reqs, plan, page, use_browser)
    if require_model:  # a model is configured: a page built from the brief's words alone is not the product
        spec = (_config(page) or {}).get("spec") or {}
        by_model = spec.get("source") == "model"
        checks.append(Check(name="product written by the model from the Discover and Validate data", passed=by_model,
                            detail=f"{spec.get('facts', 0)} facts given to the model" if by_model
                            else "the model's spec was unusable or off-brief; only the brief's own words were used"))
    rep = TestReport(brief_id=inputs.brief_id, passed=all(c.passed for c in checks), checks=checks, browser=used,
                     attempt=attempt)
    write_output(3, 6, "test_report", to_markdown(rep))
    log_action(AGENT, "test_mvp", sources=[], model=None, cost=0, approved_by=None,
               outcome="pass" if rep.passed else "fail", brief_id=inputs.brief_id, attempt=attempt,
               failed=[c.name for c in checks if not c.passed], browser=bool(used))
    return rep
