# ADR 0153 — Thirty seconds to the first document

**Date:** 2026-08-21
**Status:** Accepted

## Context

Terrium's front page describes a document. To see one, a stranger had to
clear six separate hurdles:

1. clone the repository — which is private (ADR 0143)
2. `make setup` — 120 MB, two to five minutes
3. install a Node toolchain, because the CLI is TypeScript
4. work out which of ten commands to run
5. discover that BRENDA calls lactate `(S)-lactate`, or get an empty result
6. have the network reach BRENDA, UniProt, NCBI and PubMed at that moment

Every one is defensible alone. Together they meant **nobody had ever seen
the output without being told how** — which is the difference between a
project that is good and a project somebody adopts.

Hurdle 6 only became removable on 2026-08-21, when `report` learned
`--fixture` (ADR 0149). Before that there was no offline path to demonstrate
at all.

## Decision

`make demo`. No network, no BRENDA account, no Node. It prints a real lab
report — a Km with its BRENDA reference, the chosen values marked as yours,
the published disagreement, and the refusals section — and writes it to
`demo-report.md`.

`make help` now opens with it, and *"First time here?"* is
`make setup && make demo` rather than `make setup && make check && make test`,
which asked a newcomer to wait eight minutes to be told the tests pass.

### It drives the real builder

It calls `report_lab.py` with the payload the CLI sends. It renders nothing.

**A demo with its own rendering path is the worst instance of the rule this
project is built on.** A check that cannot fail is worse than no check
because it is trusted — and a demo that cannot fail keeps looking impressive
for months after the product it advertises has rotted, with the discrepancy
surfacing in front of the first person who tries the real command.

### No Node, and the CLI command printed instead

`make setup` installs Python; requiring a Node toolchain to see one document
would reinstate a smaller copy of the barrier this removes. The equivalent
CLI invocation prints at the end, so the real path is a copy-paste rather
than a secret.

### It says what it did not prove

The saved page is committed under `Tests/fixtures/`, so the run demonstrates
the pipeline and not a live lookup. The document says so in its own *"What
Terrium would not do"* section, and the demo repeats it. A demo that quietly
read a fixture while looking like a live lookup would be more flattering and
dishonest.

## Verification

Six tests in `Tests/test_demo_shows_the_real_thing.py`, no `skipif` — a test
that skipped when offline would skip in exactly the environment the feature
exists for.

**Mutation:** teaching the demo to print its own `## Parameters` heading and
a fabricated `BRENDA ref 286469` row failed three of the six, including
`test_the_demo_renders_nothing_of_its_own`. Restore verified by `diff`.

`test_the_demo_writes_the_file_it_says_it_wrote` overwrites the output with
a sentinel rather than deleting it — `unlink` raised `PermissionError` in
the container this was written in, and a test that cannot run everywhere
gets marked skip and stops meaning anything. Proving the file was
**rewritten** is the stronger claim regardless: a demo leaving a stale
document in place would pass an existence check.

## A correction to the fifty-sixth pass

That pass reported *"fourteen root markdown files are reachable from no
front door and no `docs/*.md`"* and proposed moving twelve of them.

**Checked before acting, and the finding was wrong.** Every one is
referenced by between one and six tracked files elsewhere in the tree —
`git grep` says so. The scan had looked at five front doors and `docs/*.md`
and nothing else, then reported its own blind spot as an absence.

That is the ninth recorded instance of *a matcher narrower than the thing it
measures*, and the first where the matcher was written for a one-off
measurement rather than shipped as a guard — which is precisely why nothing
caught it. **No files were moved.** The move would have broken forty-odd
references across a tree several agents are committing into, on the strength
of a measurement that was wrong.

The underlying complaint stands: 43 top-level markdown files is what a
visitor sees, and they cannot tell which three matter. `make demo` on the
first screen is a partial answer. Reorganising the root is not, and is not
attempted here.

## Consequences

- One command, from a cold clone, to the thing the project is for.
- Test count +6.
- `demo-report.md` is generated and gitignored: a committed copy would be a
  second, unwatched version of the tool's output — the one-fact-two-copies
  defect, in the file most likely to be read.
- **Unchanged:** the repository is private, so hurdle 1 still stops
  everybody. This shortens the path for someone who is already through it.

## Related

- [ADR 0149](0149-using-the-tool-as-a-student.md) — `--fixture`, without
  which none of this was possible
- [ADR 0143](0143-the-first-command-a-stranger-runs.md) — the hurdle this
  does not remove
