"""Phase 3, step 6: user guide + "what is evidenced, what is assumed" (code only, no model).

Written from the plan, the requirements and the validator's findings, so the guide can only describe what was
actually built and the summary can only repeat labels code already set. Language follows the brief.

    docs_writer.run(inputs, reqs, plan, validation, tests)
"""

from __future__ import annotations

from venture_os.agents.build_inputs import BuildInputs
from venture_os.agents.mvp_planner import MvpPlan
from venture_os.agents.mvp_tester import TestReport
from venture_os.agents.mvp_validator import ValidationReport
from venture_os.agents.requirements_mapper import Requirements
from venture_os.decision_log import log_action
from venture_os.evidence import LABEL_TEXT
from venture_os.outputs import write_output

AGENT = "docs_writer"

# What a user does on each screen, per language (screen ids are fixed by the templates).
_SCREEN_HELP = {
    "en": {"home": "Start here: see what is available or how things stand.",
           "add": "Fill in the form and press Save.", "list": "See what you saved; remove anything you no longer need.",
           "providers": "Providers add themselves with their name, what they offer and their area.",
           "feedback": "Tell the team what to improve. It is saved on this device only."},
    "ar": {"home": "ابدأ من هنا: اطّلع على المتاح أو على الوضع الحالي.", "add": "املأ النموذج واضغط حفظ.",
           "list": "اطّلع على ما حفظته واحذف ما لم تعد تحتاجه.",
           "providers": "يضيف مقدمو الخدمة أنفسهم بالاسم وما يقدمونه والمنطقة.",
           "feedback": "أخبر الفريق بما يجب تحسينه. يُحفظ على هذا الجهاز فقط."},
}
_T = {
    "en": {"guide": "User guide", "open": "How to open it", "open_text":
           "Double-click `phase3_step5_mvp.html`. It works offline in any browser, on a computer, phone or tablet.",
           "screens": "Screens", "record": "What you fill in", "data": "Your data", "data_text":
           "Everything stays in this browser on this device. Nothing is sent anywhere, and there are no real payments "
           "(MOCKED). Clearing the browser's data removes it.", "limits": "Not in this MVP (on purpose)",
           "required": "required"},
    "ar": {"guide": "دليل المستخدم", "open": "كيف تفتحه", "open_text":
           "افتح الملف `phase3_step5_mvp.html` بنقرتين. يعمل دون إنترنت في أي متصفح على الكمبيوتر أو الهاتف أو الجهاز اللوحي.",
           "screens": "الشاشات", "record": "ما تملؤه", "data": "بياناتك", "data_text":
           "تبقى كل البيانات في هذا المتصفح على هذا الجهاز. لا يُرسل أي شيء ولا توجد مدفوعات حقيقية (MOCKED). "
           "مسح بيانات المتصفح يحذفها.", "limits": "غير موجود في هذا النموذج (عن قصد)", "required": "مطلوب"},
}


def user_guide(plan: MvpPlan) -> str:
    lang = "ar" if plan.lang == "ar" else "en"
    t = _T[lang]
    lines = [f"# {plan.title}: {t['guide']}", "", f"Brief id: `{plan.brief_id}`", "", plan.tagline, "",
             f"## {t['open']}", "", t["open_text"], "", f"## {t['screens']}", ""]
    lines += [f"- **{name}**: {_SCREEN_HELP[lang].get(sid, '')}" for sid, name in plan.screens.items()]
    lines += ["", f"## {t['record']}", ""]
    lines += [f"- {f.label}" + (f" ({t['required']})" if f.required else "") +
              (f": {', '.join(f.options)}" if f.options else "") for f in plan.fields]
    lines += ["", f"## {t['data']}", "", t["data_text"], "", f"## {t['limits']}", ""]
    lines += [f"- {x}" for x in plan.out_of_scope]
    return "\n".join(lines) + "\n"


def evidence_summary(inputs: BuildInputs, reqs: Requirements, plan: MvpPlan, validation: ValidationReport,
                     tests: TestReport) -> str:
    by = {k: [r for r in reqs.items if r.label == k] for k in LABEL_TEXT}
    lines = ["# What this MVP rests on", "", f"Brief id: `{inputs.brief_id}` (version {inputs.brief_version})", "",
             "For the founder's decision at the end of Phase 3. Labels are set by code from the cited inputs.", "",
             "| Rests on | Requirements |", "|---|---|"]
    lines += [f"| {LABEL_TEXT[k]} | {', '.join(r.id for r in v) or '-'} |" for k, v in by.items()]
    lines += ["", "## Evidenced (backed by a source)", ""]
    lines += [f"- {r.id}: {r.statement} (inputs {', '.join(r.evidence)})" for r in by["evidenced"]] or \
             ["- None yet: no Phase 1-2 findings were available."]
    lines += ["", "## To test with real users next (founder-stated, inferred or assumed)", ""]
    lines += [f"- {r.id} [{LABEL_TEXT[r.label]}]: {r.statement}" for k in ("founder_stated", "inferred", "assumption")
              for r in by[k]]
    if plan.assumptions:
        lines += [f"- [ASSUMPTION] {a}" for a in plan.assumptions]
    if inputs.missing:
        lines += ["", "## Missing when the stage started", ""] + [f"- {m}" for m in inputs.missing]
    if validation.warnings:
        lines += ["", "## Validator warnings", ""] + [f"- {w}" for w in validation.warnings]
    lines += ["", (f"**Plan validation:** {'passed' if validation.passed else 'failed'} (round {validation.round}). "
              f"**MVP tests:** {sum(c.passed for c in tests.checks)} of {len(tests.checks)} passed.")]
    return "\n".join(lines) + "\n"


def run(inputs: BuildInputs, reqs: Requirements, plan: MvpPlan, validation: ValidationReport,
        tests: TestReport) -> tuple[str, str]:
    guide = user_guide(plan)
    summary = evidence_summary(inputs, reqs, plan, validation, tests)
    write_output(3, 7, "user_guide", guide)
    write_output(3, 8, "evidence_summary", summary)
    log_action(AGENT, "write_mvp_docs", sources=[], model=None, cost=0, approved_by=None, outcome="written",
               brief_id=inputs.brief_id)
    return guide, summary
