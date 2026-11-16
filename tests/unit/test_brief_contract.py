"""The saved brief fixtures load through the same typed contract the pipeline uses."""

from pathlib import Path

import pytest

from venture_os.onboarding.briefs import ConfirmedBrief

FIXTURES = sorted((Path(__file__).parents[1] / "fixtures" / "briefs").glob("*.json"))


@pytest.mark.parametrize("path", FIXTURES, ids=[p.stem for p in FIXTURES])
def test_fixture_loads_as_confirmed_brief(path):
    b = ConfirmedBrief.from_file(path)
    assert b.version >= 1 and b.known("idea") and b.tag("country_code") in ("EG", "KE")


def test_unknown_values_are_never_returned():
    b = ConfirmedBrief(brief_id="x", version=1, fields={"budget": {"value": None, "status": "unknown"}}, tags={})
    assert b.known("budget") is None and b.tag("industries") == "unknown" and b.allowed
