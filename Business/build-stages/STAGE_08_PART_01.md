# Stage 8, Part 1 — closing Stage 6's candidates

Stage: 8 · Part: 1 · 2026-08-02

## 0. What this part does

Stage 6's close named three candidates and committed to none. Stage 7 took
the first (bimolecular SSA). This part takes the other two:

- **Candidate B — "resolved value through the LLM path."** Closed. ADR 0011.
- **Candidate A — widen literature resolution to a second field.** Blocked on
  a fixture that cannot be captured from the review sandbox. The blocker is
  documented precisely below, with the exact command to unblock it.

It also carries the Stages 1–2 audit and the `make test` interpreter fix.

## 1. Candidate B — the `llm` origin (closed)

Stage 4 Part 6 left this as open question 2 and called it *"the one that
matters."* It stayed open through three stages.

`ParameterOrigin` had three values; the resolver has four paths. A value the
LLM produced was labelled `origin: "default"` — false at the API surface. A
default is a value this project chose and documented; an LLM value is one a
language model generated from a prompt.

Two things made it more than a naming quibble:

1. **Nothing tested the LLM path.** No test asserted the note, so the only
   thing distinguishing an LLM value from a default could have been deleted
   with a green suite.
2. **The distinction lived in free text.** `note` is prose. Nothing
   structural marked the value unverified, so nothing could filter, count, or
   enforce on it.

Full reasoning in **ADR 0011**. Three enforced rules: an `llm` entry must
carry a note; must never carry a citation or citation status; and `default`
is unchanged and still needs none.

Deliberately **not** `rejected` as Stage 4 proposed — that predates Stage 5's
`citationStatus` and conflates two axes. `origin` says where a value came
from; `citationStatus` grades a citation. An LLM value has no citation, so
there is nothing to grade.

**Verified:** 8 assertions against the compiled module, a new
`llmOrigin.test.ts` covering the validator rules and the end-to-end resolver
path, `tsc --strict` clean, six guards green.

One hazard worth recording: `orval` regenerated the zod client, then failed on
esbuild's platform binary **and deleted the react-query client on its way
out**. That deletion was caught in `git status` and reverted. A codegen tool
that partially fails can leave the tree worse than before it ran.

## 2. Candidate A — a second resolvable field (blocked, honestly)

The natural target is `kcat`/`vmax`. It is already in
`STRENDA_GOVERNED_FIELDS` with no lookup path (ADR 0010 carried item 3), so
the STRENDA requirement would apply to it automatically the moment one exists.

**Why it is not built here.** BRENDA reuses identical `div.row`/`div.cell`
markup for every table on an enzyme page — Km Values, Turnover Numbers, Ki
Values, IC50, Inhibitors. `_find_table_container` therefore resolves a table
*structurally, by its navigation label*, and needs the real HTML to do it.
Three facts follow:

1. **No fixture in this repo contains a Turnover Numbers table.** The only
   `kcat` strings in `brenda_ache_fixture.html` are prose describing two rows
   that were **removed** for being unverifiable against a live re-capture.
2. **Every fixture here is live-captured**, by the `*_realrows_debug.py`
   scripts that call `fetch_brenda_html`.
3. **The sandbox cannot produce one.** `web_fetch` returns extracted text,
   not the row/cell structure the parser matches on, and fetching by other
   means is not permitted.

Hand-writing a fixture and calling it BRENDA data would put fabricated
evidence into the golden set — the exact failure this project has caught
twice (Stage 4's fabricated citation, Stage 7's rejected synthetic oxamate
row). **Not built is the correct outcome; not built while claiming otherwise
is not.**

### To unblock it, on a machine with network access

```bash
cd ~/Desktop/Coding/Terrium/Tests
python3 - <<'PY'
from brenda_client import fetch_brenda_html, _find_table_container
from bs4 import BeautifulSoup
html = fetch_brenda_html("3.1.1.7")          # AChE: has real kcat data
soup = BeautifulSoup(html, "html.parser")
node = _find_table_container(soup, "Turnover Numbers")
print("FOUND" if node else "NOT FOUND")
open("fixtures/brenda_ache_kcat_fixture.html", "w").write(str(node) if node else "")
PY
```

Then the work is mechanical and already specified:

1. `parse_brenda_turnover_html()` alongside `parse_brenda_km_html`, reusing
   `_find_table_container("Turnover Numbers")` and the same
   `parse_assay_conditions` call — kcat carries pH and temperature exactly as
   Km does.
2. `RESOLVABLE_FIELDS.mm = ["km", "kcat"]`. The narrowness note updates
   itself; the STRENDA rule already governs `kcat`.
3. A golden tuple with **real** assay conditions, following the AChE Km
   precedent (Stage 7 Part 3: `Km 0.0714 mM`, `pH 7.4, 37 °C`, ref 713996).
4. A mutation test: swap the resolved kcat for a plausible wrong-organism
   value and require an end-to-end failure (Stage 4 Part 6, question 4).

## 3. Stages 1–2 audit

Both stages predate the constitution and had never been re-derived. Both
scientific claims hold under independent checking:

| Claim | Method | Result |
|---|---|---|
| Wright-Fisher: `H_t = H_0(1−1/2N)^t` | 800 replicates, N=50 | worst rel. err **1.31 %** |
| Kimura 1962: `P(fix) = p₀` | 1500 replicates × 3 starting frequencies | all within **2 SE** |
| Monte Carlo π: error ~ `1/√N` | 40 seeds × 4 values of N | `RMSE·√N` ≈ 1.7–1.9; ratios 0.52 / 0.54 / 0.46 vs theory 0.50 |

**Kimura (1962)** re-verified against the published record: *Genetics*
**47**(6), 713–719 — matches how the repo cites it.

One referenced file, `test_wright_fisher_correctness.py`, does not exist. It
is **not** a defect: Stage 2 Part 4 already recorded that
`verify_domain.sh`'s naming heuristic looked for it while the real file is
`test_popgen_correctness.py`, classified it as cosmetic, and the script now
takes an explicit basename with that exact case in its usage text. The
carried item was genuinely closed.

`test_popgen_correctness.py`: **282 passed.**

## 4. `make test` was broken on a clean checkout

Reported: `make test` died with `No module named pytest`.

The repository `.venv` is corrupt — `python` and `python3` point at a
`python3.15` that does not exist, `pyvenv.cfg` records it was built from
Homebrew **3.14.6**, and it contains no packages. A dangling symlink is
invisible to `[ -x ]`, so the resolver skipped the venv in silence, fell
through to a bare system `python3.12`, checked only its **version**, and
selected it. The recipe then needed pytest, which nothing had checked for.

The message was accurate and named the wrong problem.

Fixed by making selection reflect what the recipe needs: among supported
interpreters, prefer one that can `import pytest`; detect a `.venv` that
exists but cannot execute and print what it was built from plus
`rm -rf .venv && make setup`.

Support stays **3.10–3.12**, and the error now says *why* instead of
asserting a rule: `libroadrunner` 2.7.0 and `numpy` 1.26.4 publish cp39–cp312
only (verified against PyPI, 2026-08-02). Reaching 3.14 needs
`libroadrunner` 2.9.3 + `numpy` 2.5.x — a NumPy 2.x major upgrade, not a gate
change, and therefore its own stage.

Verified with four isolated PATH scenarios: no venv → selected; supported but
no pytest → actionable message, exit 2; 3.12 lacks pytest but 3.11 has it →
picks 3.11; only unsupported 3.14 with pytest → still rejected. Real exit
codes checked directly, not read off a piped `head` (which returns 141 on
SIGPIPE and hides them).

## 5. Carried forward

1. **Candidate A**, per §2, once the Turnover Numbers fixture is captured.
2. **The NumPy 2.x / roadrunner 2.9.3 upgrade**, if Python 3.13+ support is
   wanted. Scope it as a stage; it is not a version-gate edit.
3. **The full 1,040-test suite has not been run in one pass** by me — the
   engine suite exceeds the sandbox's process lifetime. `make test` on a
   working venv closes this.

## 6. References

- **Kimura, M. (1962).** On the probability of fixation of mutant genes in a
  population. *Genetics* **47**(6), 713–719. Verified against the published
  record.
- **ADR 0011** — the `llm` parameter origin.
- **ADR 0010** — STRENDA assay conditions; governs `kcat` already.
- **Stage 4 Part 6** — open questions 2 and 4.
