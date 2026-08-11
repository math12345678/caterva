# Stage 10, Part 14 — the CLI becomes a tool

Stage: 10 · Part: 14 · 2026-08-11

## 1. What a tool has to do

Terrium's value is not that it simulates — plenty of things simulate. It is
that it will tell you **where a number came from, and refuse to invent one**.
Until now that lived in a pipeline nobody could reach without writing
TypeScript. The CLI existed, ran, and exposed none of it.

Three things were in the way.

## 2. `resolve` — the command the tool exists for

New: `scientific resolve <enzyme> --substrate S --organism O`.

It answers the question a student or bench scientist actually starts with —
*what is the Km of this enzyme for this substrate, and who measured it?* —
through the real literature layer: BRENDA exact, then BRENDA cross-species,
then PubMed candidates, via the same `science_agent_runner.py` the API
server uses.

It reports **three outcomes with three exit codes**, because they are three
different facts:

| | meaning | exit |
|---|---|---|
| found | a real measurement, with unit, organism and citation | 0 |
| not found | BRENDA and PubMed were searched and have nothing | 2 |
| unavailable | the lookup could not be performed at all | 1 |

Most tools collapse the last two. A tool that reports "no result" when it
actually could not reach the registry teaches its user to read an absence of
evidence as evidence of absence. The distinct exit codes matter for
scripting too: `--json` output may be piped into something else, and the
exit code is the only channel that survives that.

Cross-species matches are called out unmissably:

```
⚠ Cross-species match. This was measured in Oryctolagus cuniculus, not Homo sapiens.
  Real and citable, but do not report it as a Homo sapiens measurement.
```

And `resolve` refuses to guess the system from the query text. Inferring an
enzyme or organism from prose would attach a real citation to a system the
user never named — provenance for the wrong measurement, which is worse
than none.

## 3. Units come off the number, not a table keyed on its name

`--km 5.2 --vmax 12.8` assigned units from a name table: km→mM,
vmax→μM/min. The label therefore always agreed with the assumption and
never with what the user meant. Someone working in mM/s had their Vmax
reinterpreted as μM/min — **a factor of 60,000** — and the run continued,
producing a trajectory and a provenance record for a quantity nobody
supplied.

Same defect as the hardcoded `vmax / 1000` removed twice in Parts 8–9, and
as `getDefaultUnit`. Same fix: read the unit from the data.

```
--km 5.2mM --vmax 12.8uM/min --s0 10mM     units declared
--km 5.2                                    accepted, and reported as ASSUMED
--km 5.2mMM                                 rejected at the command line
```

A bare number is still accepted — requiring units everywhere would make the
tool tedious — but it is marked `unitDeclared: false` and named in the
output, so the user can see which of their numbers the tool interpreted
rather than read. A typo now fails at the command line with the list of
known units, instead of three layers in with a misleading message.

`parseArgs` also fixes a real bug: the old loop stepped `i += 2`
unconditionally, so `--verbose --km 5` consumed `--km` as `--verbose`'s
value and **silently dropped km entirely**.

## 4. Quiet by default

The pipeline logs a dozen structured JSON lines per run. On a terminal they
buried the answer, which is the one thing a CLI exists to show. Logs now go
to stderr at `fatal` unless `--verbose`, and `LOG_LEVEL` still wins when set
explicitly.

## 5. Tests, on the surface users actually touch

`src/cli/__tests__/` — 20 tests, none of which existed. The end-to-end set
**spawns the real binary** and reads its real stdout, stderr and exit code,
because the things that break a CLI (argument parsing, exit codes, which
stream output lands on) are invisible to a unit test of the functions
underneath. The literature runner is stubbed through
`TERRIUM_LITERATURE_RUNNER`, so they are offline and deterministic.

Covered: all three resolve outcomes and their exit codes; the cross-species
warning; the refusal to guess a system from prose; `--json` being parseable;
unknown units rejected; assumed units reported; and that stdout carries no
JSON log lines by default.

Two bugs in my own test code were caught while writing them, both worth
recording: a `toMatchObject` assertion that hid stdout/stderr and made the
failure uninformative (now the failure prints both streams), and a
`writeStub` helper that wrote each stub file twice, so the runner emitted
trailing content and the JSON parse failed at position 121.

## 6. Verification

- Root tree: **199 / 199** passing, 13 suites (was 179 in Part 13).
- `tsc --noEmit -p .`: 0 errors.
- Python engine: 285 passed, same 9 `stdpopsim` failures.
- Every resolve path exercised against a stub runner; the live path still
  returns `403 Forbidden` from the review sandbox, correctly reported as
  *unavailable* rather than *not found*.

## 7. Next for the tool

- `resolve --quantity kcat --enzyme-conc 0.001mM` bridges to a simulable
  Vmax, but nothing yet feeds that straight into `simulate`. The obvious
  next step is `simulate --resolve`, which looks up what it needs and shows
  the provenance of every number it used.
- A `--cite` flag emitting BibTeX for everything a run touched.
- `check-integrity` and `verify` operate on in-memory job IDs that do not
  survive the process, so they are currently unusable from the CLI.
