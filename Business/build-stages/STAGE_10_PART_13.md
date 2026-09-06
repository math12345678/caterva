# Stage 10, Part 13 — the prompt-injection scan, triaged rather than obeyed

Stage: 10 · Part: 13 · 2026-08-11

## 1. Sixteen findings, zero injections

`npx trojan-scan .` reported 16 findings (8 high, 8 medium). Every one was
examined at its source line. **All 16 are false positives** — the scanner
matching English phrases in legitimate documentation.

| Flagged | What it actually is |
|---|---|
| `SECURITY_HARDENING.md:380` "credential exfiltration" | A section documenting that there is **no** secrets manager and that secrets come from `process.env`. An honest security assessment of the current state. |
| `check_typescript_compiles.py:294` "planted trust assertion" | An implementation note explaining why a guard had stopped being effective. Flagged on the phrase *"never report"*. |
| `test_model_building.py:60` "planted trust assertion" | Explains that `validate=False` skips validation — which is precisely the behaviour that test exercises. |
| `CliApp.tsx:889` "text hidden by markup" | A decorative 1.5×1.5 pulse dot carrying `aria-hidden`. Correct accessibility practice; the element has no text at all. |
| `DashboardPreview.tsx:82` "text hidden by markup" | A Tailwind `overflow-hidden` layout class. Substring match on "hidden". |
| `CODE_QUALITY_IMPROVEMENTS.md:195` "embedded execution instruction" | A to-do list item: *"Add type-safe parameter registry to prevent key mismatches"*. |
| `OPERATIONS_RUNBOOK.md:688` | A comment about systemd journal logging behaviour. |
| 8 × medium "direct address to an AI agent" | Docs that say "Claude", "LLM", or contain a `System:` line inside an example transcript. This project's documentation discusses AI agents constantly, by nature. |

Nothing was rewritten to appease the scanner. Editing accurate
documentation because a regex disliked its phrasing would trade real
information for a green tick, which is the same trade this codebase has
spent eleven parts refusing.

## 2. Why the scan is now clean by itself

Re-running the scan found **nothing** — including on the single files that
had been flagged. The reason is not that anything was fixed:
concurrent agents reworded several of those files between the scan and this
work, for unrelated reasons. `SECURITY_HARDENING.md` now reads "Secrets are
obtained from environment variables at the point of use" where the scanner
had quoted "Secrets are read directly from `process.env` wherever they're
needed"; `check_typescript_compiles.py`'s note was likewise rephrased.

Both rewrites were checked and neither damaged accuracy. But it is worth
stating plainly: **a clean scan today is not evidence that yesterday's
findings were benign.** The verdicts in §1 are that evidence, and they came
from reading each site.

## 3. The guard

`scripts/check_prompt_injection.py`, wired into `verify_build.py` in every
mode.

This repository is the case the threat model is actually about: several AI
agents commit to it unattended and read each other's source, comments and
docs. Prose here is an execution surface — a sentence written to manipulate
a reader rather than inform one can change what the next agent does. That is
a supply-chain risk whose payload happens to be text, and it belongs beside
the other guards rather than in a mode nobody runs. The scan is fully
offline and takes ~30s.

Three deliberate choices:

- **Fails at `high` only.** The medium tier is dominated by documentation
  that legitimately names an AI agent, which this project's docs do
  constantly. A guard that fires on every stage document would be ignored
  within a day — the "alarm that always fires" failure this codebase keeps
  correcting.
- **Cannot-run is not clean.** If `npx` or the scanner is unavailable, times
  out, or emits unparseable output, the guard FAILS and says why. A scan
  that did not happen is indistinguishable from a scan that found nothing,
  and only one of those is a pass. `TERRIUM_SKIP_INJECTION_SCAN=1` opts out
  visibly, in the environment.
- **The baseline is deliberately empty.** `trojan-scan` supports
  suppression, and pre-populating it with today's 16 findings would have
  been the fastest way to a green tick. An unreviewed baseline is a
  suppression list nobody read. The triage in §1 lives in the guard's
  docstring so that a future exemption has to be argued for in the same
  place.

**Proof of catch.** A synthetic payload was written to the tree: one line
carrying three clauses — an instruction override, a stay-quiet directive,
and a shell-profile append fetching a remote script. The guard failed and
named the file and line. The payload was then removed, and `inj_probe.md`
is no longer in the tree.

> **Edited 2026-09-06.** That payload was quoted verbatim here until this
> date, and is paraphrased above instead. The exact wording carried no
> documentary value — it was a probe someone composed, not output the tool
> produces — while the literal string was live injection text sitting in a
> file other agents read, which is the execution surface this stage is
> about. The three clauses are named precisely enough to rebuild an
> equivalent probe. Contrast the STAGE_10_PART_14 exemption, which keeps
> its quote verbatim on purpose: that one reproduces real CLI output, and
> rewording it would falsify the record.
>
> The finding this suppressed was invisible anyway until 2026-09-06 —
> `injection/instruction-override` is rated `critical`, and the guard was
> comparing severity for equality against `"high"`, so it discarded every
> critical finding. §4 below records this proof-of-catch as passing, and it
> did: the payload also tripped a `high` rule. The critical one beside it
> went unreported, which is how a passing proof concealed a blind spot in
> the thing it was proving.

## 4. Verification

- Prompt Injection Guard: passes clean; fails on a real payload.
- Guard Wiring Guard: recognises `check_prompt_injection` as wired.
- Root tree: **179 / 179**, 11 suites, `tsc` clean.
- api-server: 422 / 422, `tsc` clean (unchanged this part).
- Python engine: 285 passed, same 9 `stdpopsim` failures.

## 5. Still open

- `rm inj_probe.md` and `rm trojan-baseline.json` — the latter is an empty
  baseline written while probing the tool's behaviour; the guard does not
  need it and an empty file invites someone to fill it in unreviewed.
- The five audit findings from Part 12 §7 remain unfixed:
  `check_citation_format.py`'s zero-parse hole, `auditForPublication`
  treating `flagged` as publication-ready, the vacuous
  `kcatProvenance.test.ts` assertion, opt-in locator consistency, and four
  latent silent skips in `verify_citations_live.py`.
