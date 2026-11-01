"""The plausibility-constants guard must run without being asked.

Same standing rule as test_engine_contract.py: a guard is not delivered
until something runs it without being asked. check_plausibility_constants.py
verifies that the plausibility constants used by validation (KM bounds,
R0 thresholds, PCR/MC/WF/MD limits, tolerances) hold identical values
across every module that uses them -- a divergence would mean two modules
validating the same parameter against different limits.

The exit code is asserted rather than the output, per the audit's
near-miss lesson (Business/build-stages/STAGE_04_PART_05.md §9.3).
"""

import pathlib
import subprocess
import sys

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_GUARD = _REPO_ROOT / "scripts" / "check_plausibility_constants.py"


def test_plausibility_constants_guard_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(_GUARD)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        "check_plausibility_constants.py failed:\n"
        f"{result.stdout}\n{result.stderr}"
    )
