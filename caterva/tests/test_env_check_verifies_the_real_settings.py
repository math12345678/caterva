"""`make check` must certify the configuration the product actually runs.

The README leans this project's most load-bearing claim on that command:

    `make check` is not a version-string check. It builds a real
    Michaelis-Menten model, translates it to SBML, integrates it, and
    compares the result to the exact closed-form solution. **If it passes,
    the numerics are trustworthy.**

That claim is only true if the check integrates at the tolerances the
engine uses. It hardcoded `1e-10` and `1e-12` — identical to
`DEFAULT_RELATIVE_TOLERANCE` and `DEFAULT_ABSOLUTE_TOLERANCE`, and
therefore correct, and therefore a second statement of one fact.

Loosen the engine's defaults — ADR 0005 shows they have been tuned once
already — and `check_env.py` would go on certifying the old settings, for
a configuration nobody runs. The README's sentence would become false with
nothing turning red anywhere.

These tests read the source rather than run the command: `check_env.py`
needs a working roadrunner and prints to a terminal, and what is being
pinned is *where the numbers come from*, not the numerics themselves —
those are already covered by the check itself and by the engine suite.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
CHECK_ENV = REPO / "scripts" / "check_env.py"


def source() -> str:
    return CHECK_ENV.read_text(encoding="utf-8")


class TestTheToleranceComesFromTheEngine:
    def test_it_imports_the_constants(self):
        text = source()
        assert "DEFAULT_RELATIVE_TOLERANCE" in text
        assert "DEFAULT_ABSOLUTE_TOLERANCE" in text
        assert "from caterva.core.data_structures import" in text

    def test_it_assigns_the_constants_rather_than_literals(self):
        text = source()
        assert (
            "runner.integrator.relative_tolerance = DEFAULT_RELATIVE_TOLERANCE" in text
        )
        assert (
            "runner.integrator.absolute_tolerance = DEFAULT_ABSOLUTE_TOLERANCE" in text
        )

    def test_no_numeric_tolerance_literal_is_assigned_to_the_integrator(self):
        """The specific regression, in the shape it would come back.

        Matches an assignment of a float literal to either tolerance —
        `= 1e-10`, `= 1e-8`, `= 0.000001`. The comment above the import
        mentions the old values in prose, which must not trip this.
        """
        offending = re.findall(
            r"integrator\.(?:relative|absolute)_tolerance\s*=\s*[0-9.]+(?:e-?\d+)?",
            source(),
        )
        assert offending == [], offending

    def test_a_failed_import_is_reported_not_silently_defaulted(self):
        """Falling back to literals would rebuild the defect.

        "Could not read the engine's tolerances" and "the numerics are
        fine" are different facts, and only one of them means the stack is
        trustworthy.
        """
        text = source()
        assert "could not read the engine's integrator tolerances" in text
        # And it must stop, not carry on with whatever it has.
        block = text[text.index("could not read the engine's") :]
        assert "return" in block[:400]


class TestTheEngineStillDefinesThem:
    def test_the_constants_exist_and_are_numbers(self):
        from caterva.core.data_structures import (
            DEFAULT_ABSOLUTE_TOLERANCE,
            DEFAULT_RELATIVE_TOLERANCE,
        )

        assert isinstance(DEFAULT_RELATIVE_TOLERANCE, float)
        assert isinstance(DEFAULT_ABSOLUTE_TOLERANCE, float)
        # Not a value assertion — the point is that the check follows
        # whatever these become, not that they stay at any figure. Only
        # that they are tighter than roadrunner's own defaults (1e-6/1e-12),
        # which is the reason ADR 0005 set them at all.
        assert DEFAULT_RELATIVE_TOLERANCE < 1e-6

    def test_the_check_reports_which_tolerances_it_used(self):
        # A green line that does not say what it verified invites the
        # reader to assume it verified more than it did.
        assert "at the engine's own tolerances" in source()
