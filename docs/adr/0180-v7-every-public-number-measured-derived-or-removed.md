# ADR 0180: Every number on a public surface is measured, derived from the tree, or removed.

**Status:** Accepted

**Date:** 2026-10-31

**Relates to:** ADR 0015 (a rule nothing executes is not enforced: every
fix below that could regress has a guard or a test that was shown to fail
without it), ADR 0125 (a score that could only be zero: the dashboard now
words it as the CLI does), ADR 0128 and ADR 0151 (their mutation sets are
ported and re-run), ADR 0014 (Python support: the scipy pin is split by
interpreter), ADR 0020, 0169 and 0171 (each gains a dated note for the
epidemiology residue removed here), ADR 0177 (a release is a workflow: the
README now says why a pip install of a checkout is not the wheel).

## Context

The pages an evaluator reads first -- the landing app, `caterva-site`,
`landing/` and the mule page -- had drifted from the tree they describe.
Surveyed on 2026-10-31 against commit 2c8cae3:

- `GUARD_COUNT` was a typed-in 76; `scripts/` holds 79 guards.
- The landing row for the literature suite said 1,589 tests; the suite
  collected 1,622 in CI run 40724292047.
- The CLI `status` command in the landing app printed a fixed block of
  "healthy" lines without asking any server.
- Three sites still offered the domains archived on 2026-09-27
  (epidemiology, population genetics, Lennard-Jones molecular dynamics)
  as runnable; one boot line named a release that never existed.
- The dashboard showed the uncalibrated literature score as a percentage.
- `scripts/verify_citations_live.py` checked a BRENDA reference id
  (740253) as a PubMed id; PubMed answers it with a 1978 paper on
  jugular-vein cannulation.
- `pip install` of a checkout ships no literature layer, the wheel
  refuses Python 3.14 without the Quick start saying so, and one README
  command exits 2 because it omits the mechanism description.
- `scipy==1.15.3` does not import `scipy.sparse.linalg` on macOS 27.0.1
  (dlopen: `__DATA/__thread_bss` zero-fill section), which silently drops
  steady-state and influence analysis from every compose run there.

## Decision

A number on a public surface is one of three things: measured (and the
measurement named), derived from the tree at build time (and a guard fails
when the derivation is stale), or removed. Where an archived feature is
asked for, the answer says it is archived, when, and which release still
runs it, instead of running something else.

What this changed:

1. **Derived counts.** `caterva-landing/src/lib/generated/repoFacts.json`
   is written by `check_landing_test_counts.py --write` (and by
   `check_documented_counts.py --write`) from the guard scripts, the README
   suite sizes and `docs/data-sources.json`. The guard fails when the file
   is stale, when a row's `collected:` differs from the README suite size,
   or when a row claims more passes than were collected.
2. **The status command asks.** It calls `/api/healthz` and
   `/api/metrics/health` and prints what came back; the dot turns green
   only for a 2xx JSON body, because a static host's HTML fallback also
   answers 200.
3. **Live domains only.** `caterva-site`'s shell lists the five domains of
   `src/cli/domainCatalogue.ts`, computes Michaelis-Menten and Gillespie
   runs in the browser with the showcase constants (Km 6 mM, BRENDA ref
   641068; kcat 40.1 1/s, ref 739603), and answers every name the v0.4.0
   shell accepted with "archived 2026-09-27, v0.4.0". Its tests run in CI
   and in `make test-site`. The API server's epidemiology bridge,
   `diseases.ts` and `wright_fisher` entry are removed, since no live
   domain reaches them.
4. **The score is a heuristic.** The dashboard prints it on a 0-1 scale,
   labelled "heuristic, not a probability", and the average tile is
   computed from the rendered runs rather than left as `--`.
5. **Live checks have three outcomes.** Both live verifiers end every
   check matched, mismatched or unreachable (exit 0, 2, 1). DOIs go through
   the CrossRef API because doi.org gates bots. The CORE client's
   Retry-After handling and wait budget are tested offline.
6. **The install path is stated.** The README says the wheel needs Python
   3.10-3.13 and that a checkout is installed with `make setup`, not pip.
   scipy is pinned to 1.16.0 for Python 3.11-3.13 (the first release after
   1.15.3 that imports on macOS 27.0.1) and stays 1.15.3 for 3.10, which
   1.16 does not support.
7. **The root is a front door.** Probe scripts, a stray screenshot and a
   committed job log are gone; monitoring files live in
   `deploy/monitoring/`, bound to 127.0.0.1, with Grafana's admin password
   read from the environment and no default.

## Consequences

- Adding or removing a guard or a test now fails a build until the counts
  are regenerated. That is the intent.
- The literature and engine landing rows carry a local measurement taken
  on the merged tree with nothing else in flight; CI re-measures them.
- Python 3.10 on macOS 27 is untested: no 3.10 interpreter was available.
- Not done: the `key=value` override regex in `queryResolver.ts` still
  accepts archived parameter names, because four test files depend on it;
  `Tests/epidemiology_resolver.py` and `Tests/popgen_resolver.py` are still
  in the tree (see `archive/legacy_domains/README.md`).
