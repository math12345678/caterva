# Terrium Engineering Constitution

Status: canonical. Every future implementation prompt (OpenCode, FreeBuff,
or any other coding agent) is prefaced with the text in Section 3. Every
future spec follows the template in Section 4. Every diff is reviewed
against Section 5 before it's trusted. This file is the consolidation of
`Business/build-stages/STAGE_01_PART_01.md` through `PART_04.md` — read
those for the full reasoning and worked examples; read this file when you
need the operative rules fast, mid-work.

## 1. The nine non-negotiable rules

1. **Every numerical claim is checked against an independent source of
   truth** — an exact closed-form solution, a known-correct independent
   solver, or a physical invariant. "Looks like a reasonable curve" is not
   verification.
2. **Physical impossibility is rejected (`ok=False`); implausible-but-real
   is flagged (`ok=True, flagged=True, flag_reason=...`), never silently
   accepted or silently rejected.** Use exactly these field names, in
   every domain.
3. **Continuous vs. discrete is a decision, made explicitly, before
   implementation.** Continuous-time processes go through antimony →
   SBML → roadrunner. Discrete/stochastic processes (PCR, Monte Carlo) are
   direct Python, no solver. Never default to whichever pattern the
   previous domain used without checking it's actually correct here.
4. **Shared constraints across layers are enforced by a test, not a
   comment.** If two parts of the system encode the same rule
   independently, an executable test must fail if they drift apart.
5. **Undeclared dependencies are a category of bug with a permanent
   automated guard** (`scripts/check_dependencies_declared.py`), not a
   one-time fix. Every new import gets a matching `requirements.txt` /
   `package.json` line in the same diff.
6. **Mutation testing is how you verify the test suite, not just the
   code.** At least one documented mutation per domain: a specific bug
   deliberately introduced, the specific test that caught it named, the
   suite confirmed clean after reverting. A report claiming this happened
   is not sufficient — the reviewer reproduces at least one, independently
   (see Section 6, Step 4).
7. **Never `pip install tellurium`** (the umbrella package). Use
   `libroadrunner`, `antimony`, `python-libsbml` directly. See ADR 0001.
8. **Every architecturally significant decision gets an ADR**, not just a
   comment — Status/Context/Decision/Consequences, numbered sequentially.
9. **Conservative defaults over irreversible optimism**, wherever the two
   conflict. Easily-reversible choices optimize for velocity now;
   expensive-or-impossible-to-reverse choices (IP posture, unvetted
   dependencies, foundational data modeling) default conservative.

## 2. The five-tool pipeline, roles

- **Claude** — orchestrator. Writes specs, reviews diffs, runs
  verification personally, resolves divergence, writes ADRs and commit
  messages. Does not implement domain code in this pipeline.
- **OpenCode / FreeBuff** — implementers. Same spec goes to both,
  independently, when running both. Treated as interchangeable and
  parallel — divergence between them is signal, not noise (see Section 7).
- **Perplexity / Kimi** — research only, before spec-writing, when a
  genuine grounding gap exists. Output folds into the spec's Verification
  Target section; it does not go straight to an implementer, and it does
  not skip verification just because it came with citations.

Full reasoning: `Business/BUILD_PIPELINE.md`.

## 3. The permanent prompt preamble

Prepend this, verbatim, to every implementation prompt:

```
You are implementing a piece of Terrium, a scientific simulation engine
for teaching labs. Before you write any code, internalize these
non-negotiable standards — they exist because each one was learned from a
real bug in this exact codebase, not as generic best practice:

1. Every numerical claim you implement must be checked, in a test, against
   an exact closed-form solution, a known-correct independent solver, or a
   physical invariant. "The output looks like a reasonable curve" is not
   verification and will be rejected in review.

2. Distinguish physically-impossible parameters (reject with ok=False,
   raise ModelBuildError, never simulate) from physically-possible-but-
   implausible parameters (ok=True, flagged=True, flag_reason set,
   simulation still runs). Use exactly these field names. Do not collapse
   this distinction in either direction.

3. Before writing any simulation logic, explicitly state whether this
   domain is continuous-time (belongs in the antimony -> SBML -> roadrunner
   pipeline) or discrete (belongs as a direct Python recurrence, no ODE
   solver). Do not default to whichever pattern the last domain used
   without checking it's actually correct for this domain's physics.

4. If this domain shares any constraint (a bound, a unit, a name) with
   another part of the system, that sync must be enforced by an executable
   test that would fail if the two drifted apart — not just a comment.

5. Every new import needs a corresponding line added to requirements.txt
   (or package.json) in the same change. Do not leave this for CI to catch.

6. After writing your tests, perform at least one mutation test:
   deliberately break your own implementation in a specific, realistic way,
   confirm the relevant test fails, then revert and confirm the suite is
   clean again. Document exactly what you broke and which test caught it.

7. Never `pip install tellurium` (the umbrella package) or suggest it.
   Use libroadrunner, antimony, and python-libsbml directly.

8. If antimony model generation is involved, check every new
   variable/parameter name against antimony's reserved words before using
   it directly — `gamma` is one known collision, there may be others.

9. If you're making a decision that a different, equally-reasonable
   engineer might have made differently (not just a variable name, but a
   real architectural choice), flag it explicitly in your final report
   rather than silently picking one.

10. Report back explicitly: what you implemented, what closed-form/
    invariant/solver you verified against, what mutation test you ran and
    what it caught, and any judgment call you made that wasn't fully
    specified in the task. A bare "tests pass" is not sufficient.

[DOMAIN-SPEC GOES HERE]
```

## 4. The domain spec template

10 fixed fields, filled every time before any implementation starts:
one-sentence definition, governing model, continuous-or-discrete (and why),
public function signature(s), validation contract, verification target,
relevant ADRs, shared-constraint check, out-of-scope statement, deliverables
checklist. Full template and a fully-worked Monte Carlo example:
`Business/build-stages/STAGE_01_PART_02.md`, Sections 2-3.

## 5. The mechanical review checklist (10 items)

Applied to every diff, in order, stop at first failure:

1. Verification target actually implemented as a real assertion, not
   described in a docstring.
2. `ok`/`flagged` contract present, exact field names, correct direction.
3. Continuous-vs-discrete choice matches what was declared; no antimony
   path introduced for a domain that shouldn't have one.
4. Shared constraints have an enforcing test.
5. New imports declared in the same diff; version pins checked against
   actually-available wheels for the Python/Node version in use.
6. Mutation test documented AND independently reproduced by the reviewer
   (Section 6 below) — not taken on the implementer's word.
7. Judgment calls were flagged, not silently made.
8. Full suite run directly by the reviewer, zero unexplained skips.
9. Diff scope matches the spec's stated out-of-scope boundaries.
10. If two independent implementations exist, they've been diffed against
    each other for substantive (not cosmetic) divergence.

## 6. The verification procedure (mechanical steps)

1. Run the full suite — both `Tellurium/` and `Tests/`, not just the new
   domain's tests.
2. Run `python3 scripts/check_dependencies_declared.py`.
3. Check any new dependency's version pin against what's actually
   installable for the Python/Node version in use.
4. **Independently reproduce at least one claimed mutation test.** Back up
   the file, apply the exact mutation described, run the specific test(s)
   claimed to catch it, confirm the failure matches the claimed cause,
   revert, confirm the suite is clean again.
   **Never chain the mutation-run step and the revert step with `&&`** —
   the mutated test is *supposed* to fail (nonzero exit), which would
   short-circuit an `&&` chain and skip the revert. Use `;` between steps,
   or a `trap ... EXIT` that fires the revert unconditionally. (Found by
   FreeBuff independently reproducing this exact procedure — see
   `Business/build-stages/STAGE_01_PART_04.md`, Section 0.)
5. For antimony-touching domains: confirm no new reserved-word collision
   by an actual build, not by inspection.
6. Confirm the diff's file list matches the spec's out-of-scope section.

Steps 1-3 are automated by `scripts/verify_domain.sh <domain>` (run from
the repo root). Step 4 remains manual — the script prints the procedure
and a reminder about the `&&`-chaining trap, then exits without
performing the mutation. Run the script first, then do Step 4 by hand.

Full procedure with commands and the `&&`-chaining incident:
`Business/build-stages/STAGE_01_PART_03.md`.

## 7. Divergence resolution

Cosmetic divergence (naming, ordering, different-but-equivalent sample
sizes in independent reproductions) — note it, move on, no escalation.

Substantive divergence (different validation bounds, non-equivalent
verification strategies, a factual disagreement about what a mutation test
result means, or one reviewer surfacing something the other's process
never had a chance to catch) — state the discrepancy precisely citing both
sources, reproduce it a third time yourself rather than picking a side by
inference, update the permanent record (not just the conversation), and
ask whether it reveals a process gap worth fixing generally (not just this
one instance). Full procedure and prompt template, plus the real worked
example (OpenCode's mutation-count correction, FreeBuff's `&&`-chaining
catch): `Business/build-stages/STAGE_01_PART_04.md`.

## 8. Amendment history

This constitution is not frozen. When a future stage surfaces a new class
of mistake the way the PCR/gamma/dependency incidents did in the original
build, or the way the `&&`-chaining bug did during Stage 1's own review
process, the fix belongs here, permanently, with the reasoning — not just
patched in the instance where it was found. Record amendments below as
they happen:

- 2026-07 — Stage 1: initial version, consolidating the nine rules, the
  five-tool pipeline roles, the spec template, the review checklist, the
  verification procedure, and divergence resolution.
- 2026-07 — Stage 1, Part 4: added the `&&`-chaining safety amendment to
  Section 6, Step 4, found by FreeBuff during independent verification of
  the Monte Carlo domain.
- 2026-07 — Stage 1 improvements (post-close): created
  `scripts/verify_domain.sh` from the Part 3 draft, automated Steps 1-3
  of the verification procedure; updated `Business/BUILD_PIPELINE.md` to
  reflect the actual 5-part stage structure established during Stage 1;
  added the script reference to Section 6.
- 2026-07 — Stage 2 (Wright-Fisher population genetics): confirmed the
  existing divergence-resolution procedure (Section 7) needs no amendment
  after catching two more mutation-test blast-radius overclaims/
  underclaims in one domain (see `Business/build-stages/
  STAGE_02_PART_04.md`) — the procedure already requires independent
  reproduction precisely because self-reported blast radius is
  unreliable; this is the procedure working, not a gap. Fixed a real bug
  in `scripts/verify_domain.sh`: Step 3's test-file lookup assumed a
  `test_<domain>_correctness.py` naming convention, which false-failed for
  Wright-Fisher's `test_popgen_correctness.py` (named after the domain
  category, not the specific model). The script now accepts an optional
  second argument for the actual filename. Briefly added, then removed, a
  third implementer (Claude Code running qwen3-coder:30b locally) after
  it proved too resource-intensive on the user's machine — the pipeline
  reverts to two implementers (OpenCode, FreeBuff); no permanent change
  to Section 2's roles was needed since the addition was reverted before
  producing any real output to build a lasting process around.
