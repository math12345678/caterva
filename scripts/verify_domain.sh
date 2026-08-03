#!/usr/bin/env bash
# scripts/verify_domain.sh
# Usage: scripts/verify_domain.sh <domain_name> [test_file_basename]
#
# Runs the mechanical verification steps from the Terrium Engineering
# Constitution (docs/CONSTITUTION.md, Section 6) for a newly implemented
# domain. Step 4 (mutation-test reproduction) is deliberately not
# automated — it requires a human (or Claude-as-reviewer) to read the
# implementer's mutation report, independently reproduce at least one
# claimed mutation, read the actual failure message, revert, and confirm
# the suite is clean.
#
# This script exists because the procedure in Part 3 was described as
# commands that could be assembled into a script — this is that script,
# refined against the Monte Carlo verification that exercised it.
#
# See also:
#   docs/CONSTITUTION.md Section 6
#   Business/build-stages/STAGE_01_PART_03.md

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <domain_name> [test_file_basename]"
    echo "Example: $0 monte_carlo"
    echo "         $0 wright_fisher test_popgen_correctness.py"
    exit 1
fi

DOMAIN="$1"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Use the same supported interpreter for every audit step. A stale repository
# venv must not shadow a supported interpreter merely because its directory
# exists; missing dependencies should fail transparently under Python 3.10–3.13.
is_supported_python() {
    "$1" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] in ((3, 10), (3, 11), (3, 12), (3, 13)) else 1)' >/dev/null 2>&1
}

if [ -n "${TERRIUM_PYTHON:-}" ]; then
    TERRIUM_PYTHON_PATH="$TERRIUM_PYTHON"
    case "$TERRIUM_PYTHON_PATH" in
        /*) ;;
        *) TERRIUM_PYTHON_PATH="$REPO_DIR/$TERRIUM_PYTHON_PATH" ;;
    esac
    if [ ! -x "$TERRIUM_PYTHON_PATH" ] || ! is_supported_python "$TERRIUM_PYTHON_PATH"; then
        echo "TERRIUM_PYTHON must point to a supported Python 3.10–3.13 interpreter: $TERRIUM_PYTHON"
        exit 2
    fi
    PYTHON="$TERRIUM_PYTHON_PATH"
elif [ -n "${VIRTUAL_ENV:-}" ]; then
    if [ ! -x "$VIRTUAL_ENV/bin/python" ] || ! is_supported_python "$VIRTUAL_ENV/bin/python"; then
        echo "Active VIRTUAL_ENV must use supported Python 3.10–3.13: $VIRTUAL_ENV/bin/python"
        exit 2
    fi
    PYTHON="$VIRTUAL_ENV/bin/python"
elif [ -x "$REPO_DIR/.venv/bin/python" ] \
        && is_supported_python "$REPO_DIR/.venv/bin/python"; then
    PYTHON="$REPO_DIR/.venv/bin/python"
else
    PYTHON=""
    for candidate in python3.13 python3.12 python3.11 python3.10; do
        if command -v "$candidate" >/dev/null 2>&1 \
                && is_supported_python "$(command -v "$candidate")"; then
            PYTHON="$(command -v "$candidate")"
            break
        fi
    done
fi

if [ -z "$PYTHON" ]; then
    echo "No supported Python 3.10–3.13 interpreter was found."
    echo "Install Python 3.13 and requirements-dev.txt, or set TERRIUM_PYTHON."
    exit 2
fi

PASS=0
FAIL=0

check() {
    local label="$1"
    local result="$2"
    if [ "$result" -eq 0 ]; then
        echo "  [PASS] $label"
        PASS=$((PASS + 1))
    else
        echo "  [FAIL] $label"
        FAIL=$((FAIL + 1))
    fi
}

echo "=========================================="
echo " Verification: $DOMAIN domain"
echo " Repo: $REPO_DIR"
echo "=========================================="
echo ""

# ------------------------------------------------------------------
# Step 1: Full test suites (both Tellurium/ and Tests/)
# ------------------------------------------------------------------
echo "=== Step 1: full test suite ==="

cd "$REPO_DIR/Tellurium"
TELLURIUM_OUT=$("$PYTHON" -m pytest tests/ -q 2>&1) && TELLURIUM_OK=0 || TELLURIUM_OK=1
check "Tellurium/ tests pass" "$TELLURIUM_OK"
if [ "$TELLURIUM_OK" -ne 0 ]; then
    echo "$TELLURIUM_OUT" | tail -10
fi

cd "$REPO_DIR/Tests"
TESTS_OUT=$("$PYTHON" -m pytest -q 2>&1) && TESTS_OK=0 || TESTS_OK=1
check "Tests/ pass" "$TESTS_OK"
if [ "$TESTS_OK" -ne 0 ]; then
    echo "$TESTS_OUT" | tail -10
fi

cd "$REPO_DIR"

# ------------------------------------------------------------------
# Step 2: Dependency-declaration guard
# ------------------------------------------------------------------
echo ""
echo "=== Step 2: dependency guard ==="

DEP_OUT=$("$PYTHON" "$REPO_DIR/scripts/check_dependencies_declared.py" 2>&1) && DEP_OK=0 || DEP_OK=1
check "dependencies declared" "$DEP_OK"
if [ "$DEP_OK" -ne 0 ]; then
    echo "$DEP_OUT"
fi

# ------------------------------------------------------------------
# Step 2b: RNG convention guard (ADR 0005 compliance)
# ------------------------------------------------------------------
echo ""
echo "=== Step 2b: RNG convention guard ==="

RNG_OUT=$("$PYTHON" "$REPO_DIR/scripts/check_rng_convention.py" 2>&1) && RNG_OK=0 || RNG_OK=1
check "RNG convention (ADR 0005)" "$RNG_OK"
if [ "$RNG_OK" -ne 0 ]; then
    echo "$RNG_OUT"
fi

# ------------------------------------------------------------------
# Step 2c: Citation-format guard
#
# Stage 4 Part 4 found three of seven modelCitations wrong, including a
# molecular-dynamics title that does not exist. No structural test caught
# it -- a fabricated title is a well-shaped string. This guard requires the
# fields that make a citation checkable by hand.
# ------------------------------------------------------------------
echo ""
echo "=== Step 2c: citation-format guard ==="

CIT_OUT=$("$PYTHON" "$REPO_DIR/scripts/check_citation_format.py" 2>&1) && CIT_OK=0 || CIT_OK=1
check "citation format" "$CIT_OK"
if [ "$CIT_OK" -ne 0 ]; then
    echo "$CIT_OUT"
fi

# ------------------------------------------------------------------
# Step 2c-2: Documented-counts guard
#
# The Stage 7 audit found three stale test counts in README.md (524 vs
# 1,040; 833 vs 858; 124 vs 182) and a domain count stated twice with two
# different values. No executable check covered any of them, so nothing
# objected as they went stale -- the same failure mode as the citation
# guard above.
# ------------------------------------------------------------------
echo ""
echo "=== Step 2c-2: documented-counts guard ==="

CNT_OUT=$("$PYTHON" "$REPO_DIR/scripts/check_documented_counts.py" 2>&1) && CNT_OK=0 || CNT_OK=1
check "documented counts" "$CNT_OK"
if [ "$CNT_OK" -ne 0 ]; then
    echo "$CNT_OUT"
fi

# ------------------------------------------------------------------
# Step 2d: Engine-contract guard
#
# The engine was split from a 4,283-line monolith into 14 modules behind a
# dual-mode shim (Stage 4 Part 3). This guard verifies the split kept the
# public API intact: dual try/except imports, module structure, package and
# flat import compatibility, __all__ resolution, and the Rule 2 contract.
# ------------------------------------------------------------------
echo ""
echo "=== Step 2d: engine-contract guard ==="

ENG_OUT=$("$PYTHON" "$REPO_DIR/scripts/check_engine_contract.py" 2>&1) && ENG_OK=0 || ENG_OK=1
check "engine contract" "$ENG_OK"
if [ "$ENG_OK" -ne 0 ]; then
    echo "$ENG_OUT"
fi

# ------------------------------------------------------------------
# Step 2e: Plausibility-constants guard
#
# Verifies the plausibility constants used by validation (KM bounds,
# R0 thresholds, PCR/MC/WF/MD limits, tolerances) hold identical values
# across every module that uses them.
# ------------------------------------------------------------------
echo ""
echo "=== Step 2e: plausibility-constants guard ==="

PLA_OUT=$("$PYTHON" "$REPO_DIR/scripts/check_plausibility_constants.py" 2>&1) && PLA_OK=0 || PLA_OK=1
check "plausibility constants" "$PLA_OK"
if [ "$PLA_OK" -ne 0 ]; then
    echo "$PLA_OUT"
fi

# ------------------------------------------------------------------
# Step 3: New-domain test file exists and collects
# ------------------------------------------------------------------
echo ""
echo "=== Step 3: new-domain test file collects ==="

# Auto-detect: if a test file wasn't given as 2nd arg, search for one
# that matches the domain. Tries test_<domain>_correctness.py first,
# then falls back to scanning for any test file whose path mentions
# the domain name (handling cases like wright_fisher ->
# test_popgen_correctness.py).
if [ $# -ge 2 ]; then
    TEST_BASENAME="$2"
else
    TEST_BASENAME="test_${DOMAIN}_correctness.py"
    TEST_FILE="$REPO_DIR/Tellurium/tests/$TEST_BASENAME"
    if [ ! -f "$TEST_FILE" ]; then
        # Fall back: search for test files that import simulate_<domain>.
        # This handles naming mismatches like wright_fisher ->
        # test_popgen_correctness.py (named after the domain category).
        CANDIDATE=$(grep -rl "simulate_${DOMAIN}" "$REPO_DIR/Tellurium/tests/" \
            --include='*.py' 2>/dev/null | head -1)
        if [ -n "$CANDIDATE" ]; then
            TEST_BASENAME=$(basename "$CANDIDATE")
        fi
    fi
fi

TEST_FILE="$REPO_DIR/Tellurium/tests/$TEST_BASENAME"
if [ ! -f "$TEST_FILE" ]; then
    echo "  [FAIL] test file not found: $TEST_FILE"
    echo "         (pass the actual filename as a 2nd arg if auto-detect fails)"
    FAIL=$((FAIL + 1))
else
    echo "  test file: $TEST_BASENAME"
    COLLECT_OUT=$(cd "$REPO_DIR/Tellurium" && "$PYTHON" -m pytest "tests/$TEST_BASENAME" --collect-only -q 2>&1) && COLLECT_OK=0 || COLLECT_OK=1
    check "test file collects" "$COLLECT_OK"
    if [ "$COLLECT_OK" -ne 0 ]; then
        echo "$COLLECT_OUT" | tail -10
    fi
fi

# ------------------------------------------------------------------
# Step 4: Mutation-test reproduction (manual)
# ------------------------------------------------------------------
echo ""
echo "=== Step 4: manual mutation-test reproduction required ==="
echo ""
echo "  This step is NOT automated — it requires reading the"
echo "  implementer's mutation-test report and manually reproducing"
echo "  at least one claimed mutation per the procedure in"
echo "  docs/CONSTITUTION.md Section 6 Step 4."
echo ""
echo "  Procedure (run all from repo root):"
echo "    1. Backup: cp Tellurium/tellurium_engine.py /tmp/tellurium_engine.py.bak"
echo "    2. Apply the exact mutation described in the report"
echo "    3. Run the specific test(s): cd Tellurium && $PYTHON -m pytest \\"
echo "       tests/test_popgen_correctness.py::<test_name> -q"
echo "    4. Confirm failure matches the claimed cause"
echo "    5. Revert: cp /tmp/tellurium_engine.py.bak Tellurium/tellurium_engine.py"
echo "    6. Confirm suite clean: cd Tellurium && $PYTHON -m pytest tests/ -q"
echo ""
echo "  IMPORTANT: Do NOT chain steps 3-5 with && — the mutated test"
echo "  is *supposed* to fail (nonzero exit), which would short-circuit"
echo "  && and skip the revert. Use ; or a trap ... EXIT."
echo "  (This was found by FreeBuff during Stage 1's own review — see"
echo "  Business/build-stages/STAGE_01_PART_04.md Section 0.)"
echo ""

# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------
echo "=========================================="
echo " Results: $PASS passed, $FAIL failed"
echo "=========================================="

if [ "$FAIL" -gt 0 ]; then
    echo ""
    echo "  Step 4 (mutation reproduction) must still be done by hand"
    echo "  before this domain is considered reviewed."
    exit 1
fi

echo ""
echo "  Mechanical checks passed. Step 4 (mutation reproduction)"
echo "  must be done by hand before this domain is reviewed."
exit 0
