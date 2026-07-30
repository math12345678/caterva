# Stage 1, Part 3 — The Verification Harness, Made Mechanical

## 0. Why this part exists separately from Part 2

Part 2's review prompt says, at item 5, "confirm the suite is clean after
reverting" and at item 7, "run `make test` directly." Those two sentences
are correct but underspecified in a way that matters: "run the tests" and
"do a mutation test" are not single commands, they're small procedures with
steps that are easy to skip under time pressure, especially across 100
stages where the temptation to treat step 4 of a 6-step procedure as
optional grows every time nobody's checking. The Monte Carlo review that
just happened in this conversation is a good worked example of what
"actually done properly" looked like — this part turns that into a fixed,
repeatable procedure instead of something that depended on this session
happening to be thorough that one time.

The concrete gap this closes: in the Monte Carlo review, the mutation-test
verification wasn't just "the implementer says three mutations were tried."
It was Claude independently reproducing one of the three mutations from
scratch, in the actual environment, confirming the specific test failed
with the specific error the report claimed, then reverting and confirming
the full suite was clean again. That's the standard. This part writes down
exactly how to do that every time, for any domain, without having to
rederive the steps.

## 1. The full verification procedure, step by step

### Step 1 — Run the full suite, not just the new domain's tests

```bash
cd Tellurium
python3 -m pytest tests/ -q
```

Then, separately:

```bash
cd Tests
python3 -m pytest -q
```

Both. Not one. A change scoped to `Tellurium/tellurium_engine.py` can still
break something in the literature layer if, for example, a shared bounds
constant got touched (Rule 4 from Part 1 — the sync between layers is
enforced by a test specifically because this class of breakage is
possible and has to be caught). Read the actual pass/fail counts, not just
whether the exit code was zero — a suite that silently collected zero
tests because of an import error still exits with a misleading status in
some configurations. Confirm the number of tests collected matches
expectations (e.g., "22 new tests" should show up as 22, not 0 or 15).

### Step 2 — Run the dependency-declaration guard

```bash
python3 scripts/check_dependencies_declared.py
```

This exists specifically because of the httpx/pydantic incident (Part 1,
Section 0). It is cheap to run and catches an entire category of bug
mechanically. Run it every time, not just when a new import "feels" like
it might be missing — the entire point of an automated guard is that it
doesn't rely on a human's intuition about when to check.

### Step 3 — Check any new dependency's version pin against actual availability

If Step 1 or Step 2 surfaced a new dependency, don't just trust that the
version pin in `requirements.txt` will install cleanly in CI. Check:

```bash
pip index versions <package-name> 2>&1 | head -5
python3 -c "import <package>; print(<package>.__version__)"
python3 --version
```

Confirm the installed version matches the pin, and confirm the Python
version in use is one the package actually publishes wheels for at that
version. This is the exact check that would have caught the
`libroadrunner==2.9.0` problem before it reached CI — a five-second check
against the reality of what's actually installable, rather than assuming a
version number that looks reasonable is actually available.

### Step 4 — Reproduce at least one claimed mutation test yourself, independently

This is the step most likely to get skipped, and the one that matters
most. An implementer's mutation-test report is a *claim*, not evidence, until
someone who isn't the implementer reproduces it. The procedure:

```bash
# 1. Back up the file being mutated
cp Tellurium/tellurium_engine.py /tmp/tellurium_engine.py.bak

# 2. Apply the exact mutation the implementer's report describes —
#    not a different mutation, the SAME one, so you're actually checking
#    their specific claim rather than substituting your own test.
#    Do this with a small inline script or a manual edit, whichever is
#    faster to get exactly right:

python3 - << 'EOF'
src = open("Tellurium/tellurium_engine.py").read()
mutated = src.replace(
    "<the exact original line from the report>",
    "<the exact mutated line from the report>",
)
assert mutated != src, "mutation did not apply — check the replace target"
open("Tellurium/tellurium_engine.py", "w").write(mutated)
EOF

# 3. Run exactly the test(s) the report claims should fail
cd Tellurium
python3 -m pytest tests/test_<domain>_correctness.py -k <specific_test_name> -v

# 4. Confirm it actually failed, and read the failure message —
#    does it fail for the REASON the report claims, or does it fail for
#    some unrelated reason (which would mean the report's causal story is
#    wrong even if the test does fail)?

# 5. Revert
cp /tmp/tellurium_engine.py.bak Tellurium/tellurium_engine.py

# 6. Confirm the full suite is clean again
python3 -m pytest tests/ -q
```

If there are multiple claimed mutations in the report, reproducing one is
the minimum bar — reproducing all of them is better when the domain is
high-stakes or the report's claims seem unusual. The bar is never zero:
"the implementer says they did this" is not, by itself, verification,
regardless of how detailed or plausible the report reads. This is exactly
what happened in the actual Monte Carlo review in this conversation —
Mutation 3 (ignoring the seed parameter) was reproduced independently, the
exact failure (`rows diverge: [...] vs [...]`) was read and confirmed to
match the claimed cause, then reverted and the suite reconfirmed clean.

**Amendment, found by FreeBuff independently running this exact
procedure:** never chain steps 3 and 5 with `&&`. The whole point of step 3
is that the test is *supposed* to fail (nonzero exit code) — if the
commands are chained as `pytest ... && cp backup ...`, the nonzero exit
from the expected test failure short-circuits the chain and the revert in
step 5 never runs, leaving the codebase mutated. Use `;` between steps, or
put the revert in a shell `trap` so it fires regardless of what step 3's
exit code is:

```bash
cp Tellurium/tellurium_engine.py /tmp/tellurium_engine.py.bak
trap 'cp /tmp/tellurium_engine.py.bak Tellurium/tellurium_engine.py' EXIT
# ... apply mutation, run the targeted test (expected to fail, that's fine) ...
# trap fires on exit no matter what happened above, guaranteeing revert
```

This is worth calling out explicitly rather than trusting `;` to be
obviously safer in every future re-derivation of this procedure — a
review harness whose own safety step can silently fail to run is worse
than not having the harness, because it looks safe while it isn't. This is
also a good example of exactly what Part 4 covers next: two independent
tools (OpenCode and FreeBuff) ran the same verification procedure against
the same diff and converged on the same pass/fail conclusions, but one of
them caught a real process bug the other didn't surface — which is the
entire justification for running more than one implementer/reviewer
against the same task in the first place.

### Step 5 — For domains touching antimony model generation specifically, check reserved words

If the domain being reviewed generates antimony source (most continuous-
time ODE domains do; discrete/stochastic domains like Monte Carlo and PCR
generally don't, since they bypass antimony entirely per ADR 0002), grep
the generated antimony strings for every new variable/parameter name
against antimony's actual reserved word list. There is no single
authoritative published list, so the practical procedure is: build the
model in a real antimony call, and confirm no error indicating a keyword
collision — don't assume based on the name looking "safe." This is
precisely how the `gamma` collision was originally discovered — not by
inspection, but by an actual build failing at antimony compilation.

### Step 6 — Confirm the diff's scope matches the spec's "out of scope" section

Read the actual file list touched by the diff (`git diff --stat` or
equivalent) against Section 9 of the domain spec (Part 2, Section 2, item
9). A diff that touches files the spec explicitly excluded is a scope
violation regardless of whether the extra changes are individually good —
scope creep in an agent-implemented change is a real risk specifically
because an implementer with initiative might "improve" something adjacent
without it being reviewed as its own decision. Flag it, don't silently
accept it just because the additional change happens to look reasonable.

## 2. Turning this into an actual script, not just a procedure

The steps above are written as commands specifically so they can be
assembled into a single verification script, run identically for every
future domain rather than re-typed from memory each time. A first draft of
that script, to be refined as more domains are verified against it:

```bash
#!/usr/bin/env bash
# scripts/verify_domain.sh
# Usage: scripts/verify_domain.sh <domain_name>
set -euo pipefail

DOMAIN="$1"

echo "=== Step 1: full test suite ==="
cd Tellurium && python3 -m pytest tests/ -q
cd ../Tests && python3 -m pytest -q
cd ..

echo "=== Step 2: dependency guard ==="
python3 scripts/check_dependencies_declared.py

echo "=== Step 3: new-domain test file exists and collects ==="
python3 -m pytest "Tellurium/tests/test_${DOMAIN}_correctness.py" --collect-only -q

echo "=== Step 4: manual mutation-test reproduction required ==="
echo "This step is NOT automated — it requires reading the implementer's"
echo "mutation-test report and manually reproducing at least one claimed"
echo "mutation per the procedure in STAGE_01_PART_03.md, Section 1, Step 4."
echo "Do not skip this because the other steps passed."

echo "=== Verification steps 1-3 complete. Step 4 (mutation reproduction) ==="
echo "must be done by hand before this domain is considered reviewed. ==="
```

Deliberately, Step 4 is not automated in this script — automating "confirm
a human actually read and understood the failure message" would defeat the
purpose. The script exists to make the mechanical parts fast and
consistent, not to make the judgment part disappear.

## 3. How this fits alongside CI's automated guards, not instead of them

CI runs the test suite and the dependency-declaration guard on every push,
automatically, regardless of whether anyone remembers to run
`verify_domain.sh` locally first. That's valuable and should stay exactly
as it is — it's the safety net that catches anything a manual review missed.
But CI passing is not the same claim as "this diff has been reviewed."
CI cannot run a mutation test that hasn't been written yet as an actual
assertion in the suite (mutation testing is a verification *method* applied
during review, not a permanent CI step — you don't want CI deliberately
breaking the codebase on every run). CI cannot judge whether a diff's scope
matches what the spec said was in-scope. CI cannot read a mutation-test
report and judge whether the claimed cause matches the actual failure
message.

So the relationship is: CI is the automated, permanent, zero-effort floor.
The manual verification procedure in this part is the review step that
happens once per diff, by a human or by Claude acting as reviewer, before
that diff is trusted — and it exists specifically to catch the things CI
structurally cannot check. Both layers matter, and treating CI passing as
sufficient by itself would be exactly the failure mode this document is
trying to prevent: mistaking "the mechanical checks passed" for "this was
actually reviewed."

## 4. What Part 4 will cover

Part 4 covers what happens when OpenCode and FreeBuff are run against the
identical spec and produce genuinely different implementations — not
cosmetic differences, but different validation bounds, different
verification strategies, or a different judgment call on something the
spec left open. It works through what "meaningful divergence" actually
looks like with concrete examples, and gives the exact prompt used to
present both implementations back to whichever tool (or to Claude
directly) is resolving the disagreement, so that resolution is a
structured comparison against the spec's stated requirements, not a coin
flip or a preference for whichever version happens to read more
confidently.
