# Stage 1, Part 5 — Consolidation, the Stage-Closing Commit, and the Report Format

## 0. What this part closes out

Parts 1 through 4 built the constitution in pieces, each part adding a
layer: the nine rules and their reasoning, the spec template and prompts,
the mechanical verification procedure, and divergence resolution — the
last of these validated against a real disagreement between OpenCode and
FreeBuff rather than a hypothetical one. This part does three things: puts
all of it into the single canonical file every future stage actually
points to (`docs/CONSTITUTION.md`, written alongside this part), defines
the exact procedure for closing out any stage once its parts are done, and
writes the actual commit that lands Stage 1 — including the Monte Carlo
domain that was reviewed and cleared during this stage's own process, since
it would be strange to publish an elaborate review procedure without
landing the one real diff it was exercised against.

## 1. Why the consolidation lives in `docs/`, not `Business/`

`Business/build-stages/STAGE_01_PART_01.md` through `PART_04.md` are the
narrative record — the reasoning, the worked examples, the false starts
(like the `&&`-chaining bug) preserved in place rather than edited away.
They're valuable exactly because they show the work, including the parts
that needed fixing.

`docs/CONSTITUTION.md` is different: it's the fast-reference operative
document, the one that actually gets read (or pasted into a prompt) under
time pressure, at stage 47, when nobody wants to re-read four narrative
parts to remember the exact field names for the validation contract. This
mirrors the existing split in the repo between `docs/adr/` (the reasoning,
preserved) and `docs/API.md` (the fast reference, current). Putting the
constitution in `docs/` alongside the ADRs and the API reference keeps it
in the same "operative documentation" bucket a contributor or future coding
agent would actually look in, rather than buried in a `Business/` folder
that's really about company operations, not engineering process.

## 2. The stage-closing procedure, defined once, used for every future stage

At the end of every stage (not just Stage 1), before starting the next
one:

1. **Confirm every part of the stage actually shipped something real**,
   not just documentation about what would be built. Stage 1 is unusual in
   that most of its parts are process/documentation — that's correct for a
   foundation stage, but it should be the exception, not the pattern.
   Starting with Stage 2, most stages should close with actual domain code
   landed, reviewed via this exact process, not just more process
   documents about process.

2. **Run the full verification procedure (Section 6 of the constitution)
   one final time**, on the complete state of the repo, not just the most
   recent diff. This catches interaction effects between changes made at
   different points in the stage that a per-diff review wouldn't surface.

3. **Write the stage-closing commit.** One commit (or a small number,
   logically grouped), with a message that states what shipped, what was
   verified, and what's explicitly still open — following the same
   pattern already used for `ba60bdc`, `5fb9118`, and the rest of this
   repo's commit history, not a generic "stage 1 complete" one-liner.

4. **Write the stage-closing report** — see the format below — as the
   artifact that actually gets read back to you (the person driving this),
   distinct from the commit message, which is for future readers of `git
   log`.

## 3. The stage-closing report format

A fixed shape, so every future stage's closing report is scannable the
same way, rather than each one inventing its own structure:

```
STAGE [N] CLOSING REPORT

Shipped:
- [bulleted list of what actually landed — code, docs, decisions —
  each with a one-line "why it matters," not just a filename]

Verified:
- [full suite pass/fail counts, run directly, not reported by an
  implementer]
- [dependency guard status]
- [any mutation tests independently reproduced, and by whom/which tool]

Divergence encountered and resolved (if any):
- [per Part 4's procedure — what diverged, how it was resolved, whether
  it revealed a process gap that got fixed]

Explicitly still open:
- [anything deferred, with why it was deferred rather than silently
  dropped]

Constitution amendments this stage (if any):
- [anything added to docs/CONSTITUTION.md's amendment history]

Ready for Stage [N+1]: yes/no, and why
```

## 4. Stage 1's actual closing report

Applying the format above to what actually happened in this stage:

```
STAGE 1 CLOSING REPORT

Shipped:
- docs/CONSTITUTION.md — the canonical, fast-reference engineering
  standard: nine non-negotiable rules, the five-tool pipeline roles, the
  permanent prompt preamble, the domain spec template, the ten-item review
  checklist, the verification procedure, and divergence resolution.
- Business/build-stages/STAGE_01_PART_01.md through PART_05.md — the full
  narrative reasoning behind every rule in the constitution, each traced
  to a real, specific incident in this codebase's history, plus a real
  worked example of the whole pipeline running end-to-end.
- Business/build-stages/RESEARCH_antithetic_variates.md — grounding
  research from Kimi and Perplexity, cross-checked against each other,
  banked for a future stage rather than acted on now, since it was
  explicitly out of scope for this stage's actual domain work.
- Tellurium/tellurium_engine.py — simulate_monte_carlo_pi() and
  validate_monte_carlo_params(), the first domain built and reviewed
  under this stage's own process while that process was still being
  written.
- Tellurium/tests/test_monte_carlo_correctness.py — 22 tests, Hypothesis-
  free (deliberately: this domain's correctness claims are about
  convergence rates and distributional properties across many
  repeated runs, which needed direct repeated-trial tests rather than
  property-based generation — worth noting as a real, reasoned deviation
  from the "match test_pcr_correctness.py's Hypothesis style" instruction
  in the original spec, not an oversight).

Verified:
- Tellurium/: 326 passed, 1 skipped (pre-existing, unrelated skip in
  test_brenda_integration.py). Tests/: 124 passed. Confirmed directly, in
  this environment, not taken from any tool's self-report.
- Dependency-declaration guard: clean. No new dependency was added; numpy
  was already declared.
- Numpy version pin checked against actual availability: no discrepancy
  blocking this stage (a pre-existing, unrelated delta was noted by
  FreeBuff between the pinned version and what's installed under Python
  3.13 in one environment — flagged as a pre-existing condition, not
  something this stage's work caused, and not yet independently confirmed
  by Claude directly — see "Explicitly still open" below).
- Mutation tests: three documented in the test file's own mutation-test
  record. Mutation 3 (seed ignored) was independently reproduced by
  Claude, separately by OpenCode, and separately by FreeBuff, with
  matching qualitative failures across all three reproductions. Mutation 2
  (missing factor of 4 in the SE formula) was independently reproduced by
  OpenCode, which corrected the original report's overclaim (3 tests
  claimed to catch it; actually 2 do).

Divergence encountered and resolved:
- OpenCode's independent reproduction corrected an overclaim in the
  original mutation-test report (Mutation 2's actual test coverage).
  Resolved by updating this stage's understanding of the domain's test
  coverage — the underlying implementation was never in question, only
  the documentation of what its tests actually prove.
- FreeBuff's independent reproduction surfaced a real bug in the
  verification procedure itself (the `&&`-chaining hazard in the mutation-
  test steps), not in the Monte Carlo implementation. Resolved by amending
  Business/build-stages/STAGE_01_PART_03.md and docs/CONSTITUTION.md
  directly, with the `trap`-based fix, and by using this exact incident as
  Part 4's worked example rather than inventing a hypothetical one.

Explicitly still open:
- The numpy version-pin discrepancy FreeBuff noted has been independently
  checked and closed, not left open: CI's actual test matrix
  (.github/workflows/tests.yml) runs Python 3.10 and 3.12 only. numpy==
  1.26.4 has published wheels for both, confirmed here by directly
  querying PyPI's available versions and confirming the installed version
  in this Python-3.10 environment matches the pin exactly. The 2.4.6-vs-
  1.26.4 mismatch FreeBuff saw was a local Python 3.13 environment, which
  is not part of CI's matrix at all — real, but not a CI risk. This is
  the exact "check the pin against actual availability" step the
  constitution requires, applied to a real flagged concern rather than
  left as a vague note for later.
- Antithetic variates and other Monte Carlo variance-reduction techniques
  remain explicitly out of scope, grounded but not started, per the
  original spec's Section 9 and Business/ROADMAP.md's scope-discipline
  note.
- The `scripts/verify_domain.sh` script drafted in Part 3 is still a
  first draft with Step 4 deliberately left manual — it has not yet been
  used, as written, end-to-end for a full future domain review. Treat it
  as unproven until it has been.

Constitution amendments this stage:
- Initial version written (this stage).
- Section 6, Step 4 amended with the `&&`-chaining / trap-based revert
  safety fix, sourced from FreeBuff's independent finding.

Ready for Stage 2: yes. The numpy version-pin item was checked and closed
during this stage, not carried forward as unfinished business.
```

## 5. The stage-closing commit

Given everything above, the actual commit for this stage bundles: the
Monte Carlo domain (implementation + tests, already independently
reviewed and cleared through this exact process), the constitution and its
five supporting narrative parts, and the research grounding file. One
commit, because all of it represents a single coherent unit of work — the
foundation stage plus the first domain built and verified under it — not
several unrelated changes that happen to land at the same time.

## 6. What Stage 2 is, and the one open item it inherits

Stage 1 was foundation: process, not new product surface area beyond the
one domain (Monte Carlo) that got built specifically to exercise the
process while it was being written. Stage 2, following `Business/
ROADMAP.md`'s own Phase 2 sequencing, would be the next real domain —
population genetics or molecular dynamics setup, whichever is picked next
— run through the exact same five parts this stage just demonstrated: a
Part 1 (constitution/spec, referencing `docs/CONSTITUTION.md` directly
rather than re-deriving it), a Part 2 (the domain-specific spec and
prompts), a Part 3 (verification, now with the corrected `&&`/trap fix
already in place from the start rather than discovered mid-stage), a Part
4 (divergence resolution, if any arises — and if none does, saying so
explicitly rather than omitting the section), and a Part 5 (closing
consolidation and commit).

Stage 2 inherits no unresolved items from Stage 1 — the one open question
(the numpy version-pin discrepancy) was checked against CI's actual test
matrix and closed within this stage, using the constitution's own Step 3
verification procedure, rather than carried forward the way the original
`libroadrunner==2.9.0` incident was allowed to sit before it broke CI.
