# Stage 9, Part 5 — auditing the oscillator verification against actual literature

Stage: 9 · Part: 5 · 2026-08-09

## 0. What this part does

Part 4 flagged that `cell_cycle_oscillator` and `repressilator` had no
verification. Tests for both landed shortly after. This part audits those
tests against the primary sources rather than taking them at face value,
using the PubMed connector.

Finding: the tests are structurally sound (scipy cross-checks, positivity,
oscillation detection, determinism) but two of their strongest-sounding
claims were not verification at all, and one was weaker than it looked.

## 1. Primary sources confirmed (PubMed)

Both papers exist as cited, retrieved and confirmed via PubMed:

- **Elowitz, M.B. & Leibler, S. (2000)** "A synthetic oscillatory network
  of transcriptional regulators", *Nature* **403**(6767), 335-338.
  DOI [10.1038/35002125](https://doi.org/10.1038/35002125), PMID 10659856.
- **Tyson, J.J. (1991)** "Modeling the cell division cycle: cdc2 and cyclin
  interactions", *PNAS* **88**(16), 7328-7332.
  DOI [10.1073/pnas.88.16.7328](https://doi.org/10.1073/pnas.88.16.7328),
  PMID 1831270, PMC52288.

Two limits on what could be extracted, recorded because they bound what any
test can honestly assert:

- Tyson (1991) is a 1991 scan; **PMC returns empty full text**, so the
  paper's parameter table and reported period cannot be read from the
  source. The curated BioModels encodings are the practical primary source.
- The Elowitz abstract reports periods "of hours" and does **not** give a
  figure that pins a dimensionless period for the model as implemented. No
  period assertion was invented to fill that gap.

## 2. Two tests claimed verification they did not perform

`test_standard_parameter_set_matches_curated_biomodels_encoding` — the name
asserts a comparison against the curated BioModels encoding. The body:

```python
assert TYSON_KAPPA == 0.015
assert TYSON_K6 == 1.0
```

It never reads BioModels, or anything else. It compares the constants to
literal copies of themselves. The repressilator test had the same shape
under a `TestLiteratureParameterValues` class name.

This matters beyond pedantry: **a value mistranscribed on the day it was
typed in produces an assertion that is wrong in exactly the same way and
passes forever.** That is not hypothetical — Lotka-Volterra shipped in this
same batch with `gamma`/`delta` transposed (ADR 0023), and nothing caught it
until the values were checked against a property outside the code.

Both tests renamed to `..._is_pinned_against_accidental_edits` /
`..._is_pinned_against_edits`, with docstrings stating plainly that they are
drift-pins, not verification, and what real verification would require.
They are kept, because pinning does catch a later typo — it just is not
what the names promised.

## 3. The repressilator phase test was near-vacuous; now it is exact

The strongest available structural claim was only loosely asserted:

```python
assert period * 0.15 < offset < period * 0.85
```

satisfied by almost any non-degenerate waveform.

The repressilator is a symmetric three-gene ring, so the system is
equivariant under the cyclic permutation (1→2→3→1) combined with a time
shift. The only periodic solution consistent with that symmetry has the
three proteins **exactly one third of a period apart** — derivable without
integrating anything.

Measured: offsets of **0.3325** and **0.6663** of a period, against 1/3 and
2/3. Now asserted to within 0.01.

### What it actually catches, measured rather than assumed

The first draft of this test's docstring claimed it "fails if any single
gene's parameters drift away from the others'". **That was wrong**, and
mutation testing proved it:

| mutation | phase deviation from 1/3, 2/3 | caught by phase test? |
|---|---|---|
| gene 1 `alpha` x1.03 | 0.0001 | no |
| gene 1 `alpha` x1.15 | 0.0012 | no |
| gene 1 `alpha` x1.40 | 0.0017 | no |
| m1 repressed by p2 instead of p3 (ring miswired) | oscillation destroyed | **yes** |

The 1/3 spacing is a consequence of the ring's *topology*, which is far
more robust than its parameter symmetry. The docstring now records this
measurement so nobody re-derives the wrong expectation from the code.
Parameter asymmetry is caught instead by the scipy cross-check, which
compares the trajectory rather than its symmetry — the miswiring mutation
failed 4 tests including that one.

The Lotka-Volterra suite was mutation-tested the same way in Part 4
(`beta*P*V` → `beta*P*P*V` broke 7 of 17 across all four verification
routes).

## 4. What could not be done from here

`scripts/capture_biomodels_fixture.py` (new) downloads the three curated
SBML entries — BIOMD0000000005, BIOMD0000000006 (Tyson) and
BIOMD0000000012 (repressilator) — writes them as offline fixtures, and
prints every `<parameter>` for comparison against the engine's constants.

It could not be run from the review sandbox: `web_fetch` is rate-limited
and the sandbox proxy returns 403 on CONNECT for direct HTTPS, the same
block that prevents live BRENDA capture here. The script follows the
existing `Tests/brenda_kcat_capture.py` pattern — capture once on a
developer machine, commit the fixture, keep the suite offline.

**Until that fixture exists, the eight Tyson/repressilator constants rest
on transcription alone.** That is now stated in the tests themselves rather
than implied to be verified.

To close it:

```bash
python3 scripts/capture_biomodels_fixture.py
```

### First run failed, and the bug was in this script

The capture ran on a developer machine and downloaded all three models,
then failed to parse every one:

```
not well-formed (invalid token): line 1, column 2
```

That is an XML parser meeting the bytes `PK` — the ZIP magic number.
`/model/download/<id>` does not serve raw XML; it serves an **OMEX/ZIP
archive** containing the SBML plus the model's metadata.

The script compounded it by writing `response.text` rather than
`response.content`, decoding those binary bytes as UTF-8 before writing. A
170,698-byte download became a 326,911-byte file on disk — the size
discrepancy in the run output is the corruption, visible in plain sight.
The damage is lossy, so the three captured fixtures cannot be repaired and
must be re-downloaded.

Fixed: the script now reads `.content`, detects the ZIP magic, unpacks the
archive, skips `manifest.xml`, and extracts the SBML member — with the
plain-XML path retained in case the endpoint changes. Verified here against
a synthetic OMEX archive (correct member selected, manifest skipped,
parameters parsed) since the review sandbox cannot reach the network.

Re-run the command above to produce usable fixtures.

## 5. The capture succeeded, and found two real errors

With valid fixtures, `Tellurium/tests/test_biomodels_parameter_parity.py`
(new, 14 tests) compares the engine's constants against the curated SBML
instead of against themselves.

**Tyson (BIOMD0000000006): all four constants match exactly.**
kappa=0.015, k6=1.0, k4=180.0, k4prime=0.018. Now verified rather than
assumed — which matters most here, because Tyson (1991) is a scan with no
machine-readable text in PMC, so the curated encoding is the only
programmatically checkable source.

**Repressilator (BIOMD0000000012): `beta` was the reciprocal of the
correct value.** The engine had `beta = 5.0`; the curated encoding gives
`0.2`, and annotates the parameter in the model file itself:

```xml
<parameter id="beta" value="0.2">
  <notes>ratio of protein to mRNA decay rates</notes>
```

with `tau_prot = 10` and `tau_mRNA = 2` in the same file. The protein
decays five times *slower* than the mRNA, so the ratio is 0.2. In the
dimensionless form this engine integrates, `p' = -beta*(p - m)`, a beta of
5 would have the protein equilibrating five times *faster* than the mRNA —
contradicting those half-lives. 1/0.2 = 5 is the signature of a
convention inversion, not a rounding difference. `alpha` was also 216.0
against the curated 216.404.

The test suite now derives beta from the encoding's own `tau_mRNA/tau_prot`
rather than trusting the stored number, so the reciprocal is dimensionally
impossible to reintroduce.

### Where the wrong value came from

The test file's own header said it: the parameters were "transcribed from
a course exercise built directly around this paper (Cornell Physics 7682)"
— a secondary source. That is how a reciprocal survives: the exercise's
convention differed, and nothing downstream ever compared against a primary
source. The header now records this.

**A wrong DOI had propagated to five files**, including
`domain-literature.ts`, which serves citations to users:
`10.1038/35002131`. PubMed gives `10.1038/35002125` for PMID 10659856.
All five corrected.

The self-referential assertions in `test_repressilator_correctness.py` were
removed rather than updated — they had already gone stale against the
corrected constants, which is the predicted failure mode of pinning code
against itself. One source of truth now.

## 5. Carried forward

1. **Run the BioModels capture** (§4) and add a fixture-backed comparison.
   This is the single highest-value remaining item for these two domains.
2. **The `seed` parameter on both oscillators** is documented as "accepted
   for call-signature symmetry but unused". A student varying it sees
   identical output. Either remove it or have the domains reject a non-null
   seed explicitly rather than silently ignoring it.
3. **No period assertion for either oscillator.** Tyson's is unreadable in
   PMC and Elowitz's is dimensional; the BioModels fixtures may make a
   reference trajectory comparison possible instead.

## 6. References

- PubMed, via the bio-research connector, for both citations above.
- ADR 0022 — the three oscillator domains.
- ADR 0023 — the transposed Lotka-Volterra defaults; the concrete precedent
  for why self-referential constant assertions are not enough.
