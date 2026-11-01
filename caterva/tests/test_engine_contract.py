"""The engine-contract guard must run without being asked.

Stage 4 Part 5's audit recorded the rule with standing force: a guard is
not delivered until something runs it without being asked
(docs/CONSTITUTION.md; Business/build-stages/STAGE_04_PART_05.md §9.2).
check_engine_contract.py verifies the modular engine split (Stage 4
Part 3) kept the public API intact -- dual try/except imports, module
structure, package and flat import compatibility, __all__ resolution,
and the Rule 2 contract.

It is wired into CI and verify_domain.sh as well; this test exists for
the same reason the citation guard got one: a regression surfaces in a
local pytest run, before a push. The exit code is asserted rather than
the output, per the audit's near-miss lesson (§9.3).
"""

import pathlib
import subprocess
import sys

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_GUARD = _REPO_ROOT / "scripts" / "check_engine_contract.py"


def test_engine_contract_guard_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(_GUARD)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        "check_engine_contract.py failed:\n"
        f"{result.stdout}\n{result.stderr}"
    )
