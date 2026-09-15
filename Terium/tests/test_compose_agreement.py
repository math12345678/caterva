"""Every module's answer, against every other module's, on every model.

WHY THIS FILE EXISTS SEPARATELY FROM test_compose_validate.py
-------------------------------------------------------------
That file proves the cross-checks can FAIL: hand the fixed-point check a
state that is not one and it catches it, with an analytic residual. Those
are unit tests of the checker.

This one runs the checker over every model the composer can actually build.
The distinction matters because the two find different things. A checker can
be perfectly correct and still never have been pointed at the case that
breaks -- and every interesting defect found in this package during its
construction came from sweeping something across all eleven models rather
than from testing it on one:

  * the influence ranking called four models "saturated" when their steady
    state was pinned by a conservation law;
  * the dossier refused every binding model silently, because the target
    species was looked up by a name that chaining had rebound;
  * the verdict page returned an identical verdict for all eleven, which was
    true and useless;
  * the CRNT refusal printed its explanation eighteen times.

None of those were visible on one model. All of them were obvious across
eleven.

WHAT THIS ASSERTS
-----------------
That the package agrees with itself. `validate.py` runs five independent
cross-checks -- the root finder against the integrator, the derived
conservation laws against a simulated trajectory, the Jacobian's predicted
settling time against the observed curve, the finite-difference sensitivity
against a coarse re-solve, and the dimensions across the whole network --
and two independent routes to the same fact disagreeing is the most
informative thing this package can find about itself.

Today it finds nothing, on any of them. That is worth pinning, because the
value is entirely in the day it stops being true.

WHAT IT DOES NOT ASSERT
-----------------------
That the models are right. Every cross-check compares Terrium against
Terrium; a shared misconception would be invisible to all five. What it
establishes is internal consistency, which is a precondition for
correctness and not a substitute for it -- the analytic tests elsewhere in
the suite are what hold the package to the mathematics.
"""

from __future__ import annotations

import pytest

from Terium.compose.grammar import UnrecognisedShape
from Terium.compose.pipeline import compose
from Terium.compose.report import _default_target

#: Every query the composer builds, from test_compose_coverage.py's twenty.
#: Kept as its own list rather than imported so that a change there which
#: narrows coverage cannot silently narrow what this file checks.
BUILDABLE = (
    "enzyme kinetics with a competitive inhibitor",
    "repressilator oscillations",
    "three step phosphorylation cascade",
    "a MAP kinase cascade with negative feedback",
    "reversible binding of a ligand to a receptor",
    "substrate inhibition at high substrate concentration",
    "two enzymes competing for the same substrate",
    "a toggle switch between two repressors",
    "sequential feedback inhibition in amino acid synthesis",
    "an open system with constant substrate inflow",
    "allosteric activation of an enzyme by its product",
)

#: Severities that mean two modules disagreed, as opposed to a check that
#: could not run. The second is not a failure -- see the module docstring on
#: why "could not check" is kept apart from "checked and disagreed"
#: everywhere in this package.
DISAGREEMENT = ("error", "disagreement")


def disagreements_in(report) -> list:
    """The findings that mean two modules contradicted each other.

    EXTRACTED SO IT CAN BE TESTED ON SOMETHING THAT DISAGREES. The sweep
    below finds nothing today, which makes its assertion vacuously true --
    it would pass just as happily if this filter matched nothing at all.
    That is the defect `scripts/check_no_vacuous_tests.py` exists to find,
    and a sweep is the easiest place in a suite to hide one.

    So the filter is a function, and `TestTheFilterItselfCanFail` drives it
    with a constructed disagreement. The sweep proves the package agrees;
    that class proves the sweep would notice if it did not.
    """
    return [
        f for f in report.findings
        if getattr(f, "severity", "") in DISAGREEMENT
    ]


@pytest.fixture(scope="module")
def reports():
    """One validation report per buildable model.

    Module-scoped because each runs a steady-state search and a trajectory,
    and eleven of those is the bulk of this file's cost.
    """
    from Terium.compose.validate import validate

    built = {}
    for query in BUILDABLE:
        model = compose(query)          # a failure here is a coverage bug
        built[query] = validate(model, species=_default_target(model))
    return built


class TestThePackageAgreesWithItself:
    def test_every_buildable_model_validates(self, reports) -> None:
        # The premise. If the composer stops building one of these, this
        # file would otherwise quietly check ten.
        assert len(reports) == len(BUILDABLE)

    def test_no_two_modules_disagree_on_any_model(self, reports) -> None:
        """The assertion this file exists for.

        Two independent routes to the same fact disagreeing is the most
        informative thing this package can find about itself, and it is
        worth knowing on the day it starts rather than whenever someone
        next runs the sweep by hand.
        """
        offenders = {
            query: found
            for query, report in reports.items()
            if (found := disagreements_in(report))
        }
        assert not offenders, {
            q: [str(getattr(f, "detail", f))[:120] for f in fs]
            for q, fs in offenders.items()
        }

    def test_every_model_was_actually_checked(self, reports) -> None:
        """A sweep that checked nothing would pass the assertion above.

        This is the same defect the package's own guards exist to find, in
        the test that guards them -- a report with no findings has not
        agreed with itself, it has not looked.
        """
        for query, report in reports.items():
            assert report.findings, query

    def test_the_bigger_models_get_more_checks(self, reports) -> None:
        # A crude but load-bearing sanity check: the three-tier cascade has
        # more species, more conservation laws and more parameters than a
        # two-partner binding, so it must attract more cross-checks. If
        # every model produced the same number, the checks would not be
        # reading the model.
        cascade = len(reports["three step phosphorylation cascade"].findings)
        binding = len(reports["reversible binding of a ligand to a receptor"].findings)
        assert cascade > binding, (cascade, binding)


class TestWhatAgreementDoesNotMean:
    def test_the_docstring_says_this_is_not_correctness(self) -> None:
        """Every cross-check compares Terrium against Terrium.

        A shared misconception would be invisible to all five, and a file
        that claimed otherwise would be the most misleading thing in the
        suite -- it would read as validation to someone deciding whether to
        trust the package.
        """
        import Terium.tests.test_compose_agreement as module

        prose = " ".join((module.__doc__ or "").split())
        assert "does not assert" in prose.lower()
        assert "shared misconception would be invisible" in prose
        assert "not a substitute for it" in prose

    def test_could_not_check_is_not_counted_as_a_disagreement(self) -> None:
        # The distinction this package draws everywhere: a check that did
        # not run has not agreed, and has not disagreed either.
        assert "error" in DISAGREEMENT
        assert "unavailable" not in DISAGREEMENT
        assert "skipped" not in DISAGREEMENT


class TestTheFilterItselfCanFail:
    """The sweep above finds nothing, so its assertion is vacuously true.

    A filter that matched nothing would produce exactly the same green
    result, which is how a sweep hides a broken check. These drive the
    filter with findings that DO disagree.
    """

    class _Finding:
        def __init__(self, severity: str, detail: str = "constructed") -> None:
            self.severity = severity
            self.detail = detail

    class _Report:
        def __init__(self, findings) -> None:
            self.findings = tuple(findings)

    def test_an_error_finding_is_flagged(self) -> None:
        report = self._Report([
            self._Finding("info"),
            self._Finding("error", "the root finder and the integrator disagree"),
        ])
        found = disagreements_in(report)
        assert len(found) == 1
        assert "disagree" in found[0].detail

    def test_a_disagreement_finding_is_flagged(self) -> None:
        found = disagreements_in(self._Report([self._Finding("disagreement")]))
        assert len(found) == 1

    def test_a_benign_finding_is_not_flagged(self) -> None:
        # The filter has to cut both ways or it would flag every report.
        for severity in ("info", "note", "ok", "unavailable", "skipped"):
            report = self._Report([self._Finding(severity)])
            assert not disagreements_in(report), severity

    def test_a_finding_with_no_severity_is_not_flagged(self) -> None:
        # getattr's default must not accidentally match.
        class _Bare:
            detail = "no severity attribute at all"

        assert not disagreements_in(self._Report([_Bare()]))

    def test_the_sweep_assertion_would_fail_on_a_disagreeing_report(self) -> None:
        """The sweep's own logic, run against a report that disagrees.

        This is the test that makes `test_no_two_modules_disagree_on_any_model`
        meaningful: it shows the same filter, given a disagreement, produces
        the non-empty result that assertion is checking for.
        """
        reports = {
            "a sound model": self._Report([self._Finding("info")]),
            "a broken one": self._Report([self._Finding("error", "totals drift")]),
        }
        offenders = {
            query: found
            for query, report in reports.items()
            if (found := disagreements_in(report))
        }
        assert set(offenders) == {"a broken one"}
