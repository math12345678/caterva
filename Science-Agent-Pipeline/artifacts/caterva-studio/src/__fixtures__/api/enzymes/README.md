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

Two answers come from a real request to a database, made at capture time:

- `capabilities-after-a-lookup.json`: `GET /api/capabilities` after the script
  asked PubChem's compound-name search for "gossypol" (a real HTTPS request through
  the literature layer's `http_retry.retry_get`, captured 2026-10-03). The server
  noted that the host answered, for that host alone, so `network` is
  `{checked: true, reachable: true, source: "use", hosts: {"pubchem.ncbi.nlm.nih.gov":
  true, ...: null}, host_status: ...}` with the time of that answer. It is the answer
  the earlier capture made after a UniProt request; UniProt's backend was answering
  503 on 2026-10-03, so a UniProt-based file could not be made again.
- `find-pyruvate-kinase-pkm-human.json`: the finder found nothing for "pyruvate
  kinase PKM", the network was then known to be reachable, and the server asked
  UniProt. The three EC numbers in `fallback` are UniProt's own answer, including
  two protein kinases that merely carry the words; the page lists them as UniProt's
  and chooses none. THIS FILE WAS NOT CAPTURED AGAIN with the finder of 2026-10-03
  (it is the answer of the finder before it, whose candidates lack `matched_by`);
  `capture_studio_enzyme_fixtures.py` rewrites it whenever UniProt answers.

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
| `find-hk1-human.json`, `find-sdh-human.json`, `find-glycogen-synthase-human.json`, `find-adh-human.json`, `find-gapdh-human.json`, `find-idh1-yeast.json`, `find-ache-human.json`, `find-hiv-protease.json`, `find-cox-e-coli.json`, `find-ribonuclease-a-human.json` | what the review of 2026-10-03 found it resolving or recommending wrongly, and what the finder answers now: an abbreviation (`confirm_only`), a confirmed one (GAPDH, resolved), a symbol per organism (IDH1 in yeast) and a recommendation across the whole list |
| `detail-2.7.1.1-human.json`, `detail-1.1.1.27-human.json`, `detail-5.3.1.1-human.json`, `detail-9.9.9.9.json` | one enzyme and its human isozymes: five, five, one (TPIS), and a 404 |
| `detail-1.1.1.1-human.json`, `detail-1.1.1.1-e-coli.json`, `detail-2.7.11.1-human.json` | the isozymes of EC 1.1.1.1 (and the family the nomenclature files under EC 1.1.1.105), the same for E. coli K-12, and the 245-protein broad class |
| `detail-transferred-*.json`, `detail-deleted-*.json` | a transferred number carrying its replacement's name, and a deleted one saying it keeps none |
| `compose-ldh-human-pyruvate.json` | `caterva compose "Michaelis Menten" --subject 1.1.1.27 --organism human --substrate pyruvate`: the run the steady-state defect was seen on, 14 of its 15 solutions at negative amounts |
| `compose-hexokinase-human-glucose.json`, `...-hxk1.json`, `...-hk2.json`, `...-gck.json` | EC 2.7.1.1 in human with no `--isoform`, and with HXK1, HK2 and GCK: the isozyme notice, the Km taken from the row that states the isozyme, and the notice staying, naming the constant whose row says nothing |
| `compose-michaelis-menten-unused-inhibitor.json` | `--inhibitor gossypol` on "Michaelis Menten": `search.unused_compounds`, not searched |
| `compose-two-enzymes-competing.json` | a line of equilibria: `stability.count_caveat` |
| `constants-hexokinase-human-glucose.json` | `cite.py` for human hexokinase's glucose Km: the tie explanation, the spread, the scope concern and the isozyme notice |
| `compose-name-several-enzymes.json`, `constants-name-several-enzymes.json` | `--subject "lactate dehydrogenase"` and `--enzyme "lactate dehydrogenase"`: refused, the outcome's `name_refusal` naming each candidate |
| `capabilities-nothing-yet.json`, `capabilities-after-a-lookup.json` | the network as the status bar reads it before and after a real lookup |

`../structure/structure-by-name-ldha.json` and
`../structure/structure-name-several-enzymes.json` were written again by the same
script, because the name policy changed what the engine answers to those two
requests (the second is now a refusal with no result and a `name_refusal`).
