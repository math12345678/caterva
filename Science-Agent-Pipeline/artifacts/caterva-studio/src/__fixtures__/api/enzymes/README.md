# Enzyme finder fixtures

Real answers of the studio server, for the enzyme finder's component tests
(`src/__tests__/enzymeFinder.test.tsx`, `src/screens/kinetics/enzymes.test.tsx`).
Nothing here is typed by hand, and none of it may be edited by hand.

## How they were produced

`caterva/tests/capture_studio_enzyme_fixtures.py`, run from the repository
root:

    PYTHONPATH=$PWD python caterva/tests/capture_studio_enzyme_fixtures.py

It builds `caterva.studio.dispatch.App` over the full adapter registry and an
empty workspace, and makes each request through `App.dispatch`, exactly as the
socket layer hands a request over (`GET /api/enzymes/find`,
`GET /api/enzymes/{ec}`, `GET /api/capabilities`, then `POST /api/runs`,
polling `GET /api/runs/{id}`, and the run's `result` and `events`). The
`find-*` and `detail-*` files hold `{request, status, body}`; the run files hold
the same `{captured, run, result_status, result | error, events}` as
`../kinetics/`. The only edit after capture is the scratch data directory's path
replaced by `<data dir>`.

The finder itself is the shipped nomenclature index (ExPASy ENZYME, the release
each `find-*` file names in `release`), read offline: no recording is involved.
Literature answers for the compose and constants runs are the repository's
committed recordings (`caterva/tests/studio_kinetics_offline.py`: the human
hexokinase page under `Tests/fixtures/recorded/`, the lactate dehydrogenase page
under `Tests/fixtures/ki_mode/`), so the numbers are BRENDA's as recorded.

Two answers come from a real request to UniProt, made once, on 2026-10-03:

- `capabilities-after-a-lookup.json`: `GET /api/capabilities` after the script
  asked UniProt's protein-name search for "hexokinase" (a real HTTPS request
  through `Tests/enzyme_lookup.fetch_ec_numbers_by_name`). The server noted that
  the host answered, so `network` is `{checked: true, reachable: true, source:
  "use", hosts: {"rest.uniprot.org": true, ...}}` with the time of that answer.
- `find-pyruvate-kinase-pkm-human.json`: the finder found nothing for "pyruvate
  kinase PKM", the network was then known to be reachable, and the server asked
  UniProt. The three EC numbers in `fallback` are UniProt's own answer,
  including two protein kinases that merely carry the words; the page lists
  them as UniProt's and chooses none.

Nothing was contacted for the other files. `capabilities-nothing-yet.json` is
the answer before anything had happened (`checked: false`, `source: null`).

## What each is

| file | request |
|---|---|
| `find-lactate-dehydrogenase.json`, `...-human.json` | the owner's complaint: a name that is several enzymes, without and with an organism (the human one carries the finder's recommendation) |
| `find-pyruvate-kinase.json`, `find-hexokinase-human.json`, `find-glucokinase.json` | names the finder resolves, with the organism's proteins and cautions where it has any |
| `find-ldha-human.json` | an abbreviation, with an organism |
| `find-hexokinse-human.json` | a typo: did-you-mean, not resolved |
| `find-1-1-1-27-human.json`, `find-1-1-1.json` | a complete EC number, and a class |
| `find-transferred-1.1.1.109.json`, `find-deleted-1.1.1.128.json` | the first transferred number with one successor, and the first deleted one without, in EC order |
| `find-zzqx-protein-of-no-enzyme.json`, `find-9-9-9-9.json` | nothing found, UniProt not asked because the network was not yet known; a well-formed number the nomenclature does not hold |
| `find-pyruvate-kinase-pkm-human.json` | nothing found, UniProt asked (see above) |
| `detail-2.7.1.1-human.json`, `detail-1.1.1.27-human.json`, `detail-5.3.1.1-human.json`, `detail-9.9.9.9.json` | one enzyme and its human isozymes: five, five, one (TPIS), and a 404 |
| `compose-ldh-human-pyruvate.json` | `caterva compose "Michaelis Menten" --subject 1.1.1.27 --organism human --substrate pyruvate`: the run the steady-state defect was seen on, 14 of its 15 solutions at negative amounts |
| `compose-hexokinase-human-glucose.json`, `...-hxk1.json` | EC 2.7.1.1 in human with and without `--isoform HXK1`: the isozyme notice, then its absence |
| `compose-name-several-enzymes.json`, `constants-name-several-enzymes.json` | `--subject "lactate dehydrogenase"` and `--enzyme "lactate dehydrogenase"`: refused, the outcome's `name_refusal` naming each candidate |
| `capabilities-nothing-yet.json`, `capabilities-after-a-lookup.json` | the network as the status bar reads it before and after a real lookup |

`../structure/structure-by-name-ldha.json` and
`../structure/structure-name-several-enzymes.json` were written again by the same
script, because the name policy changed what the engine answers to those two
requests (the second is now a refusal with no result and a `name_refusal`).

## Paths

A response that names a directory on the machine it was captured on carried a
throwaway scratch or worktree path. After capture, only that prefix was
rewritten, to `/tmp/caterva-enzyme-fixtures` (`caterva/tests/capture_studio_enzyme_fixtures.py` now does this itself when it writes a file), so that no file in the repository names a person's
home or scratch folder; every other byte is what the server answered.
