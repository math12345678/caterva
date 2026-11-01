# Kinetics fixtures

Real API responses for the kinetics screens' component tests (Compose,
Constants, Sim, Bind). Nothing here is typed by hand, and no number in them
was written by a person: each file is what the studio server answered.

Produced 2026-10-01 in the `studio/sci-kinetics` worktree. Each request went
through `caterva.studio.dispatch.App.dispatch` (the core server's pure
dispatch layer, `studio/core` at e9f768f, copied beside this branch's
adapters in a scratch tree, since core is not merged here yet) exactly as
the socket layer hands a request over: `POST /api/runs`, then polling
`GET /api/runs/{id}` until the run finished, then `GET /api/runs/{id}`,
`GET /api/runs/{id}/result` and `GET /api/runs/{id}/events`. Each file
holds:

- `captured`: the kind and request posted;
- `run`: the RunRecord (`cli` is the command that reproduces the run);
- `result_status` and `result` (the kind's Result) or `error` (the 404 body
  for a run that finished without a result);
- `events`: every Server-Sent Event of the run, in order.

The only edit made after capture: the scratch data directory's path was
replaced by `<data dir>`.

Literature answers were the committed recordings, through
`caterva/tests/studio_kinetics_offline.py` (the same context managers the
parity tests use), so the numbers are BRENDA's as recorded:

| file | request | where its answers came from |
|---|---|---|
| `compose-ldh-gossypol.json` | `caterva compose "Michaelis-Menten with a competitive inhibitor" --subject 1.1.1.27 --organism human --substrate pyruvate --inhibitor gossypol` (the README example): Km 0.03 mM (BRENDA ref 286469), Ki 0.0014 mM (ref 711801), kcat a placeholder | `Tests/fixtures/ki_mode/brenda_1.1.1.27.html.gz`, `caterva/tests/fixtures/studio_kinetics/http/` |
| `compose-ldh-noncompetitive.json` | the same with a noncompetitive inhibitor and the quinoline sulfonamide of ref 739793: Ki 0.00252 mM, the row stating noncompetitive inhibition versus pyruvate | the same |
| `compose-binding-analyses.json` | `caterva compose "reversible binding of a ligand to a receptor" --crnt --scale --validate --reduction --robustness 5`: exit 3, timescale separation refused, the other sections answered | no search |
| `compose-unrecognised.json` | `caterva compose glycolysis`: refused, no result (404) | no search |
| `compose-shapes.json` | `GET /api/compose/shapes` | |
| `organisms-normalise-human.json` | `POST /api/organisms/normalise {"name": "human"}` | |
| `compose-malformed.json` | `POST /api/runs` with `--robustness 0`: 400 in the CLI's words | |
| `constants-hexokinase.json` | `python3 scripts/cite.py --ec 2.7.1.1 --organism human --substrate glucose`: Km 6.0 mM, BRENDA ref 641068 | `Tests/fixtures/recorded/` |
| `constants-refused.json` | the same without an organism: refused in report_lab's words | |
| `sim-decay.json` | `caterva sim ssa --a0=200 --k=0.3 --end=10.0 --seed=42` | the engine |
| `sim-association.json` | `caterva sim ssa --bimolecular --a0=120 --b0=80 --k=0.005 --end=5.0 --seed=7` | the engine |
| `bind-quinoline-disagrees.json` | `caterva bind --ec 1.1.1.27 --organism human --inhibitor <ref 739793's quinoline> --computed=-10.5±0.3`: exit 4, disagrees | `Tests/fixtures/brenda_ldh_ki_fixture.html` |
| `bind-gossypol.json` | `caterva bind ... --inhibitor gossypol` | the same |
| `bind-survey.json` | `caterva bind ... --survey` | the same |
| `bind-list.json` | `caterva bind ... --list` | the same |
| `bind-no-rows.json` | `caterva bind ... --inhibitor NADH`: refused, no result | the same |

To regenerate: build the same scratch tree (this branch's `caterva/`,
`Tests/` and `scripts/`, with core's `caterva/studio/{dispatch, jobs,
workspace, security, server, capabilities, static_files, __main__}.py` and
its contract amendment), create
`App(workspace=Workspace(<empty dir>), port=..., token=...)`, and make the
calls above inside the matching `studio_kinetics_offline` context manager.
Once core is merged this needs no scratch tree. The JSON must not be edited
by hand.

## Added on studio/kin (2026-10-01)

`compose-binding-charts.json` was captured on branch `studio/kin` (from
`studio/integrate` at f8c7cc9, core merged, so no scratch tree) through
`caterva.studio.dispatch.App(workspace=Workspace(<empty dir>), port=18720,
token=...)`, with the same calls as above (`POST /api/runs`, polling
`GET /api/runs/{id}`, then the record, `/result`, and `events.jsonl` as
written to the run's folder). Request, which needs no literature:

    caterva compose "reversible binding of a ligand to a receptor" \
      --sweep complex_kon --predictions --identifiability --design --screen \
      --robustness 30 --stochastic 1e-18 --stochastic-seed 11 --knockout complex_A

It is the one fixture whose sections carry a figure each (robustness draws,
the knockout screen, the measurement design, the identifiability spectrum,
a stochastic trajectory) and a sweep. Only the data directory's path was
replaced by `<data dir>`.

## Re-captured on 2026-10-17: the claims bundle

Every compose run in the studio now writes its claims bundle (ADR 0179;
docs/studio/CONTRACT.md 9, 11), so the six compose fixtures were written
again by `caterva/tests/capture_studio_kinetics_fixtures.py`, the recipe
above as a script (from the repository root, `PYTHONPATH=$PWD python
caterva/tests/capture_studio_kinetics_fixtures.py`; core is merged, so no
scratch tree), with the same requests through `App.dispatch`:
`compose-ldh-gossypol`, `compose-ldh-noncompetitive`,
`compose-binding-analyses`, `compose-binding-charts`, `compose-unrecognised`
and `compose-malformed` (which came out byte for byte as it was). The
constants, sim and bind fixtures were not touched. What changed in the
others:

- `run.artifacts` lists `claims.zip` and `claims.json` after the exports;
  `caterva_version` is 0.6.0; the stage events include `claims`.
- `result.claims` is the `ClaimsSummary` (root claim, counts, the `## Claims`
  section's text), and every parameter's and starting amount's
  `provenance.claim` is its `ClaimInfo`: for the LDH runs, `reaction_Km` is
  cited from the row of BRENDA ref 286469 (0.03 mM) and `reaction_Ki` from
  ref 711801 (0.0014 mM, gossypol) or 739793 (0.00252 mM, noncompetitive),
  each with its certificates in the pinned page; `reaction_kcat` is a
  placeholder claim; the binding runs' claims are placeholders and chosen
  starting amounts, with no row and no page.
- `claim.reference` is null in the LDH runs and `result.claims.notes` says
  why: BRENDA's literature pages for refs 286469, 711801 and 739793 are not
  among the recordings, so the run's attempt to capture them met the offline
  context's refusal ("no recording answers ..."), which the bundle records
  as a note and a refused claim rather than a paper. A fixture with a paper
  on a claim is the hexokinase run of
  `caterva/tests/test_studio_compose.py` (recordings under
  `caterva/tests/fixtures/compose_claims/http/`), not captured here.
- `report_markdown` ends with the `## Claims` section naming the bundle's
  directory under `<data dir>`.

Two replacements were made in what was written, and no other edit: the
scratch data directory is `<data dir>`, and the temporary folder the offline
context serves the LDH page from (a claim's `snapshot.served_from`) is
`<recorded pages>`.

## Added on 2026-10-17: the hexokinase run and its re-check

The same script, the same day, also writes the fixtures the page's
derivation block and its "Re-check this run" action are tested over
(`src/__tests__/derivation.test.tsx`, `recheck.test.tsx`):

| file | request | where its answers came from |
|---|---|---|
| `compose-hexokinase-claims.json` | `caterva compose "Michaelis Menten" --subject 2.7.1.1 --organism human --substrate glucose --no-analysis --no-simulate --no-ranking` (the run of `caterva/tests/test_studio_verify.py`): Km 6 mM from the row of BRENDA ref 641068, kcat 40.1 1/s from ref 739603, each a cited claim whose `reference` is the paper (title, journal, year, PMID and the PubMed link), because BRENDA's literature pages for both refs are recorded | `Tests/fixtures/recorded/` and `caterva/tests/fixtures/compose_claims/http/`, through `hexokinase_offline(literature=True)` |
| `verify-hexokinase.json` | `POST /api/runs/{id}/verify` with `{}` on that run, as written: 200, `ok` true, 24 checks | the run's own bundle, re-read by `caterva/check/verify.py` |
| `verify-hexokinase-changed-byte.json` | the same after the last digit of the certified reference id in the pinned page (`641068`, the span the Km claim's certificate names) was changed on disk, the gzip rewritten, and before it was put back: 200, `ok` false; the first failing check is the page's bytes and names the Km claim that rests on them | the same |
| `verify-no-bundle.json` | `POST /api/runs/{id}/verify` on the unrecognised-shape run, which built nothing and wrote no bundle: 409 with `contract.NO_CLAIMS_BUNDLE` | |

The verify fixtures are `{"status", "body"}`, as `compose-malformed.json`
is. One more replacement, and no other edit: the hexokinase page is served
from the repository's own recordings, so the Km claim's
`snapshot.served_from` names the checkout; that prefix is written as
`<repository>`.
