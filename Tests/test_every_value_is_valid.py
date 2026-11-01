"""v7 value gate: every numeric and categorical value in the ground-truth data
is checked against an explicit domain, not just "is present".

Scope: Tests/golden_set.py and docs/data-sources.json. Offline and
deterministic; the live comparison against BRENDA stays in
scripts/verify_golden_against_live.py (network, deliberate).

A value outside its domain fails here, naming the tuple and the field.
"""
from __future__ import annotations

import datetime
import json
import math
import pathlib
import re

import pytest

from golden_set import GOLDEN

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"

UNITS = {"mM"}
SOURCES = {"brenda_exact", "brenda_cross_species"}
QUANTITIES = {"km", "ki", "kcat"}
EC_RE = re.compile(r"^\d+\.\d+\.\d+\.\d+$")
BINOMIAL_RE = re.compile(r"^[A-Z][a-z]+ [a-z]+$")
# Km/Ki physically plausible span in mM (sub-nM to molar).
KM_MIN, KM_MAX = 1e-9, 1e3

TOP_KEYS = {"id", "verified_on", "ec", "substrate", "organism", "fixture",
            "expected", "quantity", "allow_cross_species", "allow_variants"}
EXPECTED_KEYS = {"km", "unit", "organism", "source", "ref",
                 "cross_species_flag", "rejected_organisms"}


@pytest.mark.parametrize("t", GOLDEN, ids=lambda t: t["id"].split(":")[0])
class TestGoldenValues:
    def test_no_unknown_fields(self, t):
        assert set(t) <= TOP_KEYS, set(t) - TOP_KEYS
        assert set(t["expected"]) <= EXPECTED_KEYS, set(t["expected"]) - EXPECTED_KEYS

    def test_categorical_fields(self, t):
        e = t["expected"]
        assert EC_RE.match(t["ec"])
        assert t["substrate"].strip() and t["substrate"] == t["substrate"].lower()
        assert BINOMIAL_RE.match(t["organism"])
        assert BINOMIAL_RE.match(e["organism"])
        assert e["unit"] in UNITS
        assert e["source"] in SOURCES
        assert t.get("quantity", "km") in QUANTITIES
        assert (FIXTURES / t["fixture"]).is_file()
        for k in ("allow_cross_species", "allow_variants", "cross_species_flag"):
            assert isinstance(t.get(k, e.get(k, False)), bool)

    def test_numeric_fields(self, t):
        e = t["expected"]
        km = e["km"]
        assert isinstance(km, float) and not isinstance(km, bool)
        assert math.isfinite(km) and KM_MIN <= km <= KM_MAX
        assert e["ref"].isdigit()

    def test_date(self, t):
        d = datetime.date.fromisoformat(t["verified_on"])
        assert d <= datetime.date.today()

    def test_internal_consistency(self, t):
        e = t["expected"]
        cross = e["source"] == "brenda_cross_species"
        assert e["cross_species_flag"] is cross
        if cross:
            assert t.get("allow_cross_species") is True
        else:
            assert e["organism"] == t["organism"]
        for org in e.get("rejected_organisms", ()):
            assert BINOMIAL_RE.match(org) and org != e["organism"]


def test_golden_ids_unique_and_ordered():
    ids = [t["id"] for t in GOLDEN]
    assert len(set(ids)) == len(ids)
    assert [i.split(":")[0] for i in ids] == [f"G{n}" for n in range(1, len(ids) + 1)]


def test_expected_ref_present_in_fixture():
    for t in GOLDEN:
        html = (FIXTURES / t["fixture"]).read_text(errors="replace")
        assert t["expected"]["ref"] in html, t["id"]


def test_data_sources_fields():
    d = json.loads((ROOT / "docs" / "data-sources.json").read_text())
    required = {"tokens", "creator", "source_uri", "licence", "licence_uri",
                "modifications", "notice_uri", "citation_request"}
    seen = set()
    for s in d["sources"]:
        assert set(s) == required, s.get("tokens")
        assert s["tokens"] and all(t == t.lower() and t.strip() for t in s["tokens"])
        assert not (seen & set(s["tokens"])), "token claimed twice"
        seen |= set(s["tokens"])
        assert s["creator"].strip() and s["licence"].strip()
        for k in ("source_uri", "licence_uri"):
            assert s[k] in (None, "") or re.match(r"^https://\S+$", s[k]), k
