"""Build QA: the MVP must carry the product name, the first customer action and the top requirements' key terms.
A generic app fails. Replay mode: no model."""

from types import SimpleNamespace as NS

from venture_os.agents.mvp_tester import requirement_checks
from venture_os.agents.requirements_mapper import Requirement, Requirements

REQS = Requirements(brief_id="b", source="rules", items=[
    Requirement(id="R1", statement="Parents book a cleaner for a home visit", priority="must"),
    Requirement(id="R2", statement="Parents see the cleaner's verified rating", priority="must"),
    Requirement(id="R3", statement="Cleaners confirm or decline the visit", priority="must"),
    Requirement(id="R4", statement="No card data is stored", type="constraint", priority="must")])

SPECIFIC = {"title": "Nadafa Home Cleaning", "tagline": "Book a vetted cleaner for your home",
            "screens": {"product": "Book a visit"}, "fields": [{"label": "Visit date"}, {"label": "Home area"}],
            "texts": {"banner": "MVP · MOCKED", "cta": "Book a cleaner", "help": {"rating": "Verified rating"}},
            "spec": {"core": {"verb": "book", "object": "cleaner visit"}, "offers": [{"name": "Single visit"}]}}
GENERIC = {"title": "My App", "tagline": "Welcome to the app", "screens": {"product": "Home"},
           "fields": [{"label": "Name"}, {"label": "Email"}],
           "texts": {"banner": "MVP · MOCKED", "cta": "Submit"}, "spec": {"core": {}, "offers": []}}


def by_name(checks):
    return {c.name: c.passed for c in checks}


def test_the_real_product_passes_all_three():
    r = by_name(requirement_checks(REQS, NS(title="Nadafa Home Cleaning"), SPECIFIC))
    assert all(r.values()), r


def test_a_generic_app_fails_all_three():
    r = by_name(requirement_checks(REQS, NS(title="My App"), GENERIC))
    assert r == {"product name on the page": False,
                 "first customer action from the requirements is on the page": False,
                 "key terms of the top requirements on the page": False}


def test_requirement_text_hidden_in_data_does_not_count():
    hidden = {**GENERIC, "screen_requirements": {"product": ["R1", "R2"]},
              "notes": "Parents book a cleaner for a home visit"}
    assert not by_name(requirement_checks(REQS, NS(title="My App"), hidden))[
        "first customer action from the requirements is on the page"]
