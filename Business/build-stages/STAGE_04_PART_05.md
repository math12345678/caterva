# Stage 4, Part 5 — The Citation-Format Guard

## 0. What this part builds

Part 4 found that 3 of 7 literature references in the query resolver's
`DOMAIN_DEFAULTS` were wrong — a fabricated title, two truncated ones —
and carried a recommendation to Part 5: *"a citation-format guard, in the
same spirit as `check_rng_convention.py` — an executable check rather than
a review habit."*

This part builds that guard: `scripts/check_citation_format.py`. It is the
fourth executable guard in `scripts/`, alongside
`check_dependencies_declared.py` (Stage 1), `check_rng_convention.py`
(Stage 2), and the `verify_domain.sh` script.

## 1. Why a format guard is the honest scope of automation

The guard cannot verify that a paper exists. What it can do is refuse
citations whose shape is unverifiable: no authors, no year, no journal
volume, no pages, no publisher, no URL. A bare title like *"Physical
clusters of simple liquids."* — the exact failure shape Part 4 found
attributed to Hoare & Pal — fails on every field.

It converts "someone should look these up" into "an unlookuppable citation
cannot merge", which is the difference between a habit and a guard.

## 2. Scope decisions

- **Scanned file:** `Science-Agent-Pipeline/artifacts/api-server/src/lib/
  queryResolver.ts` — the only file in the codebase with static
  `modelCitations` entries. The `modelCitations` occurrence in
  `llmResolver.ts` lives inside the LLM system-prompt template literal,
  and LLM-provided citations are runtime data; neither is statically
  checkable. The script accepts an optional path argument so a future
  static array elsewhere is covered by the same check.
- **URL rule:** an entry containing a URL is accepted as-is. Database
  citations (BRENDA) legitimately carry no author or year; a URL is
  inherently lookuppable.
- **Publisher rule:** an entry naming a publisher ("Clarendon Press.")
  satisfies the "locator" requirement for book citations. Part 4's
  recommendation said "volume/page range or a URL"; a publisher
  identifies a book exactly as volume/pages identify an article, and
  Fisher (1930) is a book. Without this, the guard would reject a
  legitimate citation.
- **Deferred, deliberately:** whether a `resolved` (per-parameter)
  citation must satisfy a *stricter* format than a `modelCitations`
  entry. Part 4 §5 assigned that decision to Stage 5's provenance
  contract; this guard does not pre-empt it.

## 3. The rules

For every static `modelCitations` entry:

1. Non-empty.
2. If it contains `http://` or `https://` — pass.
3. Otherwise all three must hold:
   - a year in parentheses, e.g. `(1930)`;
   - at least two capitalized name tokens before the year
     ("Kermack W.O., McKendrick A.G." → four; "Fisher R.A." → two);
   - a volume/page range (`115(772), 700-721` or `51, 263-273`) or a
     publisher (`Press | University | Institute | Publications`).

Entry line numbers are reported so a violation points at the exact line.

## 4. Verification — positive run

```
$ python3 scripts/check_citation_format.py
OK: all modelCitations entries carry authors, a year, and volume/pages, a publisher, or a URL.
```

Exit 0. All 7 committed entries pass: BRENDA (URL rule), Kermack &
McKendrick ×2, Mullis et al., Metropolis & Ulam, Fisher (publisher rule) +
Wright, Lewontin, Hoare & Pal.

## 5. Verification — the guard fails on the shapes it must catch

Each failure shape was exercised against a mutated copy of
`queryResolver.ts` (single-entry substitution, then reverted — the working
tree is unchanged):

| Mutation | Guard output (exit 1) |
|---|---|
| Bare title: `Physical clusters of simple liquids.` | no volume/page range and no publisher |
| Truncated article: journal `20(84)` without pages | no volume/page range and no publisher |
| No year | missing a year in parentheses |
| No authors: `(1971) Physical cluster mechanics …` | fewer than two author-name tokens |
| Placeholder: `optional literature reference` | missing year + no locator |
| Empty entry `""` | empty modelCitations entry |

The pre-Part-4 Mullis shape (full journal/volume/pages, truncated title)
passes this guard, and that is correct and honest: it is *format*-
lookuppable. Content verification remains a human/LLM lookup — Part 4's
audit — and the guard's job is to guarantee a future regression is at
least formatted so someone can.

## 6. Guard set

All three executable guards run clean together:

```
$ python3 scripts/check_rng_convention.py
OK: all stochastic domains comply with ADR 0005 (numpy.random.default_rng(seed)).
$ python3 scripts/check_dependencies_declared.py
OK: every third-party import is declared in requirements.txt or requirements-dev.txt.
$ python3 scripts/check_citation_format.py
OK: all modelCitations entries carry authors, a year, and volume/pages, a publisher, or a URL.
```

## 7. Status

| Item | State |
|---|---|
| `scripts/check_citation_format.py` | built, verified positive + negative |
| 7 committed `modelCitations` entries | pass guard; all independently re-verified against primary sources (Part 4 + audit) |
| Working tree | citation guard added; no resolver changes (Part 4's corrections stand as committed in `edbbbc3`) |

## 8. Carried forward

- **Stage 5 provenance contract:** decide whether a `resolved` citation
  must satisfy a stricter format than a `modelCitations` entry (Part 4 §5;
  ADR 0008). This guard deliberately stops at `modelCitations`.

## 9. Audit amendment (2026-08-01) — the guard was enforced nowhere

Two corrections to this document, found by auditing it rather than re-reading
it.

### 9.1 The CI claim in §8 was false, and it had a consequence

The original §8 stated: *"the repo has no workflow files; guards run manually
in each stage's verification. If CI is ever added, this guard belongs in the
merge gate next to the other two."*

`.github/workflows/tests.yml` exists, is tracked in git, and runs two jobs
(`test` and `api-server`). It has been in the repository since before Stage 1
and was extended with the api-server job during Stage 4 Part 1.

This is not a trivia error. It produced a wrong conclusion — that CI
enforcement was hypothetical and deferred — which is precisely why the guard
shipped connected to nothing. A false premise about the environment led to
real work being left undone. The claim was checkable in one command.

### 9.2 The guard existed but nothing ran it

Verified at audit time: `check_citation_format.py` was referenced by **no**
pytest test, **no** CI step, and **no** step in `verify_domain.sh`. It ran
only when a human typed its name.

This is the same failure as `check_rng_convention.py` after Stage 2, which
sat unenforced until a test wrapped it. The lesson did not transfer, so it is
now recorded in the constitution with standing force rather than left as a
per-stage observation: **a guard is not delivered until something runs it
without being asked.**

Now wired in three places, deliberately overlapping:

| Where | Why this one too |
|---|---|
| `Tellurium/tests/test_citation_format.py` | fails the suite locally, before a push |
| `.github/workflows/tests.yml` (`test` job) | fails the merge gate, and fast — before the full suite |
| `scripts/verify_domain.sh` Step 2c | fails a stage's own verification run |

### 9.3 The guard was verified against the defect that motivated it

A guard that cannot catch its own founding case is decoration. Checked by
restoring the exact pre-correction string and running it:

```
MUTATED   "Hoare M.R., Pal P. (1971) Physical clusters of simple liquids."
          line 108: no volume/page range and no publisher; an entry with a
          bare title cannot be looked up
          exit code 1

REVERTED  OK: all modelCitations entries carry authors, a year, and
          volume/pages, a publisher, or a URL.
          exit code 0
```

The exit codes were checked directly rather than through a pipe — an earlier
attempt read `tail`'s status instead of the script's and appeared to show a
guard that reported violations while exiting 0, which would never fail CI.
It does exit 1. But the near-miss is worth recording: **when verifying that a
guard fails, verify the exit code, not the output.**

Six tests now cover it: the live check, rejection of the fabricated string,
acceptance of the corrected replacement, acceptance of a database URL,
rejection of a missing year, and rejection of an empty entry.

### 9.4 One more infrastructure fix folded in

`Tellurium/conftest.py` (added alongside the guard) makes the flat
`from tellurium_engine import ...` imports resolve regardless of pytest's
rootdir. `pytest.ini`'s `pythonpath = . ..` — added during the Part 3 audit —
only works when rootdir is `Tellurium/`; running pytest from the repo root
made those relative entries resolve elsewhere. Correct fix, and it closes a
gap the Part 3 audit left open.

## 10. Follow-up (2026-08-01) — plain `pytest` collects clean end to end

With the conftest in place, one collection error remained in bare runs
(`python3 -m pytest` from the repo root): `Tests/big_test.py`, a
straight-line scratch script (no functions) that matched pytest's
`*_test.py` pattern and instantiated `OpenAI()` at module level, failing
without `GROQ_API_KEY`. `scripts/check_dependencies_declared.py` already
treats `big_test*` as scratch via `EXCLUDE_NAME_PREFIXES`.

Renamed to `Tests/big_test_scratch.py` (git mv, no references anywhere).
Bare pytest now collects 846 tests with zero errors, and the full battery
is green:

| Check | Result |
|---|---|
| `python3 -m pytest` (bare, repo root) | 845 passed, 1 skipped |
| vitest (api-server) | 111 passed (6 files) |
| `npm run typecheck` | clean |
| `check_rng_convention.py` / `check_dependencies_declared.py` / `check_citation_format.py` / `check_engine_contract.py` | all pass |

The big_test collection quirk (present only when a Tellurium path joined
the pytest command line) was not fully root-caused — a pytest 8.4.2
multi-arg collection oddity; the rename removes the dependency on it,
which is the point.
