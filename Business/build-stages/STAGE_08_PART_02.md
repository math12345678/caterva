# Stage 8, Part 2 — full audit of Stages 1–7

Stage: 8 · Part: 2 (audit) · 2026-08-02

## 0. Method

Every carried-forward item from Stages 1–7 checked **against the code**, not
against the report that claimed it. Every guard mutation-tested: deliberately
break the thing it protects, confirm it fails, restore, confirm it passes.

That method found two real defects in the guards themselves. A guard nobody
tries to break is a guard nobody knows works.

## 1. Two guard defects found and fixed

### 1.1 The plausibility guard never looked at the literature layer

**ADR 0003** makes the Km plausibility bounds a contract *between* the
literature layer and the simulation layer. The guard enforcing it scanned
`Tellurium/` only, so `Tests/brenda_client.py` — the other half of that
contract — was outside its search path entirely.

Demonstrated before fixing:

```
brenda_client.KM_PLAUSIBLE_MAX_MM = 9999    (engine still 1000)
check_plausibility_constants.py             -> PASSED, exit 0
```

That is precisely the bug ADR 0003 exists for, and one that **actually
happened**: engine `1e4` vs BRENDA `1e3`, so a Km of 5000 mM was flagged
upstream and silently accepted downstream.

Fixed by scanning both layers. The wider scan immediately produced a **false
positive** — `1e3`, `1000` and `1000.0` are the same bound spelled three ways
and legitimately appear as all three, but the comparison was `str(v)`. So a
second fix: compare by value. A guard that cries wolf is worse than useless;
it trains people to ignore the output, and the next real drift rides along
with it.

Verified in four states: clean → 0; literature-side drift → 1; engine-side
drift (the historical bug) → 1; restored → 0.

### 1.2 Self-skipping tests

`make test` reported "857 passed, **1 skipped**" for months. The 1 was
`test_flagged_brenda_entries_do_not_become_confident_numbers`, which had
**never executed a single assertion** — every fixture parses to zero flagged
entries, so its `if not flagged: pytest.skip(...)` fired every run while the
test was counted in the total.

A sweep found five more of the same shape in the same file. All are now
assertions. The two fixture-level ones mattered most: a parser regression
returning `[]` would have made *every test in that file* skip while the suite
stayed green. Verified by mutating `parse_brenda_km_html` to return `[]` — the
file now produces 4 ERRORs where it would previously have vanished silently.

**New guard: `scripts/check_no_silent_skips.py`.** Runs both suites, fails
when the skip count exceeds zero, and names the file, line and reason of
anything that skipped. Verified both directions by injecting a temporary
skipping test (exit 1, reason reported) and removing it (exit 0). Wired into
CI after the two test steps.

## 2. Carried items, each checked against the code

| Item | Status |
|---|---|
| S3P4·1 mutation-6 energy `−20.836780` | recorded |
| S3P4·2 qualitative frustration assertion | present (`test_molecular_dynamics_correctness.py:751`) |
| S3P4·3 `frustation` typo | gone |
| S3P4·4 eigenvector sign regression test | present (`test_popgen_correctness.py:3384`) |
| S4P5 resolved-citation format | settled by ADR 0008 / 0010 |
| S4P6·Q1 provenance travels with the value | **materially closed** — see below |
| S4P6·Q2 LLM-generated value tier | closed by ADR 0011 |
| S4P6·Q3 Rule 1 for provenance | closed by the golden tuple (S7P3) |
| S4P6·Q4 resolver mutation test | present (`provenance.test.ts:319`) |
| S5P7·1 extract pH/temperature | closed 2026-08-02 |
| S5P7·2 golden tuple with real conditions | closed 2026-08-02 (AChE) |
| S5P7·3 / S7P3·1 `vmax`/`kcat` lookup | **open** — blocked, see §4 |
| S7P3·2 Stage 6 candidates | B closed (ADR 0011); A blocked |

### On Q1 — provenance in a parallel channel

Stage 4 recommended provenance travel *with* the parameter through the Python
engine. It does not: `tellurium_runner.py` has no provenance at all, and the
two are rejoined in TypeScript afterwards.

The design is nonetheless sound, because the concern behind the question —
"a citation and the number it supports should not be separable by a refactor…
nothing checks they still correspond" — **is** now checked, at runtime rather
than in tests. `validateParameterProvenance` rejects drift in both directions,
verified against the compiled module:

```
{km, vmax} + provenance for km only   -> "vmax has a parameter value but no provenance"
{km} + provenance for km and vmax     -> violation
exact correspondence                  -> []
```

`resolveQuery` throws on any violation, so a refactor that separated them
would 500 rather than silently ship a mismatched pair. Recorded as closed on
the substance, with the structural recommendation deliberately not adopted.

## 3. Guards mutation-tested

| Guard | Mutation | Caught |
|---|---|---|
| plausibility constants | literature-side drift | ✅ (after §1.1 fix) |
| plausibility constants | engine-side drift | ✅ |
| RNG convention | `default_rng` → legacy `np.random` | ✅ |
| documented counts | wrong total / conflicting domain counts | ✅ |
| shim shadowing | implementation appended to `tellurium_engine.py` | ✅ by `test_shim_defines_no_implementations` |
| silent skips | injected skipping test | ✅ |

One clarification worth recording: **`check_engine_contract.py` does not
catch shim shadowing.** Appending an implementation to the shim leaves it
green. That regression is caught by `test_shim_defines_no_implementations`
(Stage 4's `__module__` test), which runs in the same CI job. Coverage
exists; it is simply not where the script's name implies. Left as-is rather
than duplicated — but named here so nobody assumes the script covers it.

## 4. What remains open, and exactly what is needed

### 4.1 ~~`kcat`/`vmax` literature resolution — blocked on a fixture~~ CLOSED

**Closed 2026-08-02.** You captured the fixture; the extraction is built,
tested and mutation-checked. See §7 below for what was found on the way, and
**ADR 0012** for why kcat is resolved but deliberately *not* wired into
`RESOLVABLE_FIELDS`.

The original blocker, for the record:

Already in `STRENDA_GOVERNED_FIELDS`, so the reporting requirement applies
automatically the moment a lookup exists. Blocked because:

- No fixture contains a **Turnover Numbers** table. The only `kcat` strings in
  `brenda_ache_fixture.html` are prose about rows **removed** for being
  unverifiable.
- BRENDA reuses identical `div.row`/`div.cell` markup for every table, so
  `_find_table_container` needs the real HTML structure.
- `web_fetch` returns extracted text, not that structure.

**What I need you to run** (network access required):

```bash
cd ~/Desktop/Coding/Terrium/Tests
python3 - <<'PY'
from brenda_client import fetch_brenda_html, _find_table_container
from bs4 import BeautifulSoup
html = fetch_brenda_html("3.1.1.7")          # AChE has real kcat data
soup = BeautifulSoup(html, "html.parser")
node = _find_table_container(soup, "Turnover Numbers")
print("FOUND" if node else "NOT FOUND")
if node:
    open("fixtures/brenda_ache_kcat_fixture.html", "w").write(str(node))
PY
```

Paste the result. If `FOUND`, the remaining work is mechanical and specified
in Stage 8 Part 1 §2.

### 4.2 Python 3.13+/NumPy 2.x upgrade

`libroadrunner` 2.7.0 and `numpy` 1.26.4 stop at cp312 (verified against
PyPI). Reaching 3.14 needs `libroadrunner` 2.9.3 + `numpy` 2.5.x — a NumPy
2.x major upgrade with breaking API changes, not a version-gate edit. Its own
stage, if wanted.

### 4.3 Things I cannot verify here

- **The full 1,040-test suite in one pass.** Closed once by your `make test`
  run (857+1 skipped, 182). The engine suite exceeds this sandbox's process
  lifetime, so I verify subsets and say which.
- **vitest.** rollup's native binary is macOS-only in my sandbox.

## 5. Note on working-tree state

At audit time the tree carried **33 uncommitted files** that are not mine —
including a `PARAMETER_PATTERN` change adding `seed` in `queryResolver.ts`.
Left untouched. Every commit in this session touched only files listed
explicitly in its `git add`.

One process note for myself: a `cp`-based backup restored a **stale** copy of
`tellurium_engine.py` mid-audit, silently reverting unrelated changes. Caught
by `git diff`, restored with `git checkout`. Backups during mutation testing
should come from git, not `cp`.

## 7. Addendum (2026-08-02) — kcat built, three bugs found

The fixture capture succeeded (`FOUND label='Turnover Numbers'`, 15 data
rows), which unblocked the last open item. Building against **real** data
immediately exposed three defects that a hand-written fixture would have
hidden — two of them pre-existing in code that had been green for months.

### 7.1 Duplicate rows (pre-existing, shared with the Km path)

`rows + subrows` concatenated two selector results without deduplicating. A
sub-row that also carries `class="row"` was therefore parsed **twice**, and
the same measurement returned as two entries.

The Km fixtures never tripped it — their sub-rows are not `class="row"`. The
AChE Turnover Numbers capture has **11 such rows**, so every heavily-studied
substrate came back duplicated. Fixed by identity dedup preserving document
order.

This is the value of testing against captured rather than constructed data:
the bug was in shared code, reachable from the Km path, and no existing
fixture could reach it.

### 7.2 An inverted heuristic

The Km parser flags any row whose commentary mentions "Kcat", on the theory
that a turnover number has landed in the KM Values table by mistake. Correct
there — and **nonsense** in the Turnover Numbers table, where such commentary
is exactly what belongs.

Applied unconditionally, it flagged the real captured human row
(6500 s⁻¹, *"…does not alter the Kcat value"*) as suspect **for being
precisely what it claims to be**. Now scoped to the Km table, with a test
asserting it still fires there — the fix must not disable the check where it
was right.

### 7.3 An unscoped fixture (my capture script's fault)

`_find_table_container` locates a table by its **navigation link**, so a
fixture holding only the container has nothing to match: the parser falls
back to a whole-page scan and flags every row as unconfirmed. The existing Km
fixtures include the anchor for exactly this reason; my script saved only the
container. Fixed in `brenda_kcat_capture.py`, which now stores both.

### 7.4 Bounds, anchored to literature

kcat needs its own plausibility range — the Km bounds are meaningless for a
turnover number. A kcat of 6500 s⁻¹ is an ordinary fast enzyme; a Km of
6500 mM is a unit error.

| | value | source |
|---|---|---|
| median kcat | ~10 s⁻¹ | Bar-Even *et al.* 2011, *Biochemistry* **50**(21), 4402–4410 |
| fastest known (catalase) | ~4 × 10⁷ s⁻¹ | |
| `KCAT_PLAUSIBLE_MAX_PER_S` | 10⁹ s⁻¹ | diffusion limit — above this it cannot be a kcat |
| `KCAT_PLAUSIBLE_MIN_PER_S` | 10⁻⁶ s⁻¹ | admits the real captured 8.83 × 10⁻⁶ *Schizaphis* row |

The ceiling sits at the diffusion limit rather than at catalase deliberately:
faster than catalase is *remarkable*, faster than diffusion is *impossible*.

### 7.5 Result

7 unique entries, 3.72–6500 s⁻¹, every one STRENDA-complete. Golden tuple:
**118 s⁻¹, 6-monoacetylmorphine, *Homo sapiens*, pH 7.4, 37 °C, ref 750291.**

Nine tests, four mutations, each caught:

```
revert the row dedup                    -> FAIL
use Km bounds for kcat                  -> FAIL
un-scope the kcat-commentary heuristic  -> FAIL
point the wrapper at the KM table       -> FAIL
```

### 7.6 And it stopped short, on purpose

kcat is **not** in `RESOLVABLE_FIELDS`. The MM engine takes `vmax`, and
`Vmax = kcat · [E]₀` needs an enzyme concentration Terrium does not have.
Defaulting it would produce a smooth plausible curve whose `Vmax` came from a
number nobody measured — invisible to every test. **ADR 0012.**

### 7.7 The counts guard earned itself

Adding 9 tests broke `check_documented_counts.py` on its first real outing:

```
FAIL: make_test: README says 1,040, actual is 1,049
      literature: README says 182, actual is 191
```

That is precisely the drift that went unnoticed for several stages before the
guard existed.

## 6. References

- **ADR 0003** — shared Km plausibility bounds across layers.
- **ADR 0005** — RNG convention. Guard scope (engine-only) verified correct:
  no RNG usage exists outside `Tellurium/`.
- **ADR 0008 / 0010 / 0011** — provenance, STRENDA, the `llm` origin.
- `docs/CONSTITUTION.md` — Rule 4 (shared constraints enforced by executable
  test), Rule 6 (mutation testing with independent reproduction), and the
  Stage 4 amendment on guard delivery.
