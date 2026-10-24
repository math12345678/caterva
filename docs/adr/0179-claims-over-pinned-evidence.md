# ADR 0179: A claim is a derivation over pinned evidence, and a program that shares no code with the composer can re-check it.

**Status:** Accepted

**Date:** 2026-10-17

**Relates to:** ADR 0011 (a model-supplied value is its own origin and,
since the 2026-08-06 amendment, never reaches the engine; this extends the
rule to identifiers: a model may propose an EC number, never supply one),
ADR 0015 (a rule nothing executes is not enforced: the checker's
independence and the placeholder-DOI rule each get a guard), ADR 0016
(provenance computed and dropped at a boundary; here the boundary is time,
and what was dropped is the page itself), ADR 0029 (a mutant's constant is
not the enzyme's: twelve of the twenty-five human D-glucose Km rows on the
hexokinase page this ADR's examples come from are variants by their own
commentary, and a cited number of the wrong protein is worse than none),
ADR 0047 (selection by evidence, not magnitude: the frontier whose ordinals
a derivation now carries, and whose pick is recorded as a rule rather than
re-derived), ADR 0170 (a model is a value; the annotation-free Antimony
source is what a computed claim's identity hashes), ADR 0171 (a search over
a parameter set whose trace is an audit only because declared reads are
enforced; a claims bundle is the same idea at rest), ADR 0172 (an assay
window re-selects a measured row and never adjusts a number; a unit factor
is the one arithmetic a derivation may state, and the checker redoes it),
ADR 0173 (a grammar of mechanisms: the composed model this slice makes
claims about), ADR 0177 (a release is a workflow; the bundle format carries
a version so a later release can read an earlier one), ADR 0178 ("the
resolver knew, and a conversion dropped it": the defect this ADR closes one
layer further out, where the conversion is the report and the thing dropped
is the evidence).

## Context

Since ADR 0178 a composed report prints, beside a constant, the organism it
was measured in and the BRENDA reference that measured it:

    | `reaction_Km` | 6.0 mM | literature (Homo sapiens) | BRENDA ref 641068 |

(the run `docs/OWNER_CHECKLIST.md` records for EC 2.7.1.1, D-glucose,
human). That line is true the moment it is printed and unverifiable the
moment after.

- **The page is gone.** BRENDA serves `enzyme.php?ecno=2.7.1.1` live; the
  report keeps a reference id, not the bytes it read. Re-checking the line
  means asking BRENDA again, which compares today's page with today's
  answer and says nothing about the run that was made.
- **The row is identified by a number.** The recorded hexokinase page
  (`Tests/fixtures/recorded/brenda_2.7.1.1.html.gz`, fetched 2026-09-28)
  holds twenty-five human D-glucose Km rows, four of them from reference
  641068: 6, 0.15, 0.34 and 2.1 mM, a wild-type and three Ser-151 mutants
  of beta-cell glucokinase. Which of the four the report means is carried
  by the value alone.
- **The reason for the pick is not kept.** ADR 0047 narrows to a Pareto
  frontier on ordinal evidence axes and takes the minimum inside it; the
  report says which row won and, since ADR 0178, which rows tied. The
  ordinals that made the frontier are recomputed on every run and written
  nowhere.
- **Nothing re-checks the report but the code that wrote it.** ADR 0178's
  note on its own tests applies: a test that constructs the state it means
  to verify can only confirm the code's mistakes back to it. A reader has
  no second program to run.

So the provenance ADR 0178 made reachable is a **label**: a true sentence
about a derivation that no longer exists. ADR 0016 found the same shape at
the cache boundary. This is the shape at the boundary of time.

The owner's architecture plan of 2026-09-30 names the fix. This ADR records
its first slice, the plan's M0 to M2, and says which parts are later
milestones and not built.

## Decision

**1. A warrant is a derivation, not a label.** `caterva/evidence/claims.py`
defines the data a number carries:

- a `Snapshot`: the raw bytes of a page the resolver read, identified by
  the sha256 of those bytes, with the URL, the date it was retrieved (ISO
  8601, UTC, stored *beside* the id and never inside it), the licence, the
  release the source states (BRENDA states none) and, when a test replayed
  it, the recording it was served from;
- a `Row`: one table row as the literature layer's parser read it,
  identified by the hash of its parser rule, its locator and its fields.
  The locator names the EC number, the table, the organism, the substrate,
  the reference id, the value text and the index among duplicates in parse
  order, so that two rows with the same value and reference are two rows;
- a `Certificate`: a byte span `[start, end)` of a snapshot and the text at
  that span, for the reference id, the value text and the commentary. A
  text that is not found yields no certificate, never an invented span;
- a `Derivation`: a rule (`rule_id`, `version`, the ADR that decided it),
  the refs it consumed, its certificates and its settings, which are
  strings;
- a `Claim`: a kind, a subject (`reaction_Km = Km(2.7.1.1, D-glucose, Homo
  sapiens)`), a value text and unit, a tolerance for recomputed values, a
  derivation and, for a refusal, the refusal.

The rules this slice uses, each versioned and each naming its ADR:

| rule_id | version | decided by | what it warrants |
|---|---|---|---|
| `parse.brenda_table` | 1 | this ADR | a row read from a BRENDA enzyme page by the literature layer's parser |
| `parse.brenda_reference` | 1 | this ADR | authors, title, journal, year and PMID read from BRENDA's literature page for a reference |
| `select.resolver` | 1 | ADR 0047 | the row the resolver carried for a constant: weight-free dominance, then the minimum |
| `placeholder.motif_library` | 1 | ADR 0013 | an illustrative value from the motif library, labelled as such |
| `chosen.starting_amount` | 1 | ADR 0044 | a starting amount or exponent somebody chose |
| `compile.model` | 1 | this ADR | the composed model: every parameter claim plus the hash of the annotation-free Antimony source |

A rule's version is part of every identity that uses it, so changing what a
rule means without bumping its version is caught by the checker as a claim
whose id no longer matches its contents.

**2. Identity follows the derivation.** Every id is the sha256 of canonical
JSON (`caterva/evidence/canonical.py`: keys sorted, no whitespace, UTF-8,
NaN refused), and canonical JSON refuses floats: every number that enters
an identity is a decimal string. For a cited, chosen or placeholder claim
the value text is part of the identity, because the number *is* what was
cited or chosen. For a computed claim the value is excluded and a tolerance
is carried instead, because a re-integration that lands within the stated
tolerance is the same claim and one that does not is a different fact. The
dataclasses recompute their own id on construction and refuse one that
does not match, so no object can hold a lying id; the construction
invariants (a cited claim has exactly one row input and at least one
certificate; a placeholder has no row input and names the table that would
have supplied it; a refusal carries no value) raise `EvidenceRefused`.
Identity is order-independent and the tests say so with Hypothesis.

**3. A refusal is a claim.** When no row on the pinned page matches the
measurement the resolver reported, the model carries a claim of kind
`refused` naming what was requested, why, and every candidate row with the
same reference id and the reason each was not it. A number with no row
behind it is never given a citation.

**4. A snapshot is a dated record, never a cache.** The product fetches
live, exactly as before. `--claims DIR` on `caterva compose` opens an
`EvidenceStore` and a `Recorder` that pins every BRENDA page the resolver
reads, through one hook: `PAGE_OBSERVERS` in `Tests/brenda_client.py`,
called after every `fetch_brenda_html`, live or recorded, because
`fallback_logic` binds that function as a default argument and a wrapper
would not see its calls. Nothing reads a snapshot to answer a later
search. `Tests/fixtures/recorded/README.md`'s rule stands: a recorded page
is served to tests and to nothing else, and a snapshot's `retrieved_at`
says which day it is a record of. Without `--claims` nothing changes and
nothing from `caterva/evidence/` is imported.

**5. The pick is recorded as a rule; conflict is kept, not resolved.** This
slice records what the resolver chose, under `select.resolver` v1, with the
chosen row's ordinals and the alternatives' in `settings["ordinals"]` when
the resolver carried them, so that the checker can confirm the chosen row
is not strictly dominated. When the ordinals were not carried the
derivation says `dominance = not certified` and the checker reports that
check as not run, never as passed. What this slice does **not** do is
enumerate readings: the plan's M3, where every row's interpretation
(isozyme, variant, condition) is a claim of its own and a selection is a
claim over readings, is not built, and the frontier's reasoning is still
recomputed live. The report's "where the evidence did not settle" section
(ADR 0178) remains the place the spread is shown.

**6. A separate checker that imports no producer code.** `caterva/check/`
imports only the standard library (`json`, `gzip`, `hashlib`, `re`,
`pathlib`, `dataclasses`, `typing`), re-implements canonical JSON from its
definition rather than importing it, and re-finds a row in the pinned bytes
by regular expression rather than by the parser that produced it. The
independence is a guard, `scripts/check_checker_independence.py`, which
walks every module under `caterva/check/` with `ast` and fails on any
import outside `sys.stdlib_module_names` or naming `caterva`, `Tests`,
`bs4`, `pydantic` or `numpy`; its `--selftest` plants a bad import and
expects the failure. `caterva verify DIR` holds a bundle to eight things:
every blob's sha256 equals its snapshot id; every row and claim id
recomputes from its stored fields; every cited claim's row exists, its
snapshot exists, and the reference id and value text occur within one table
row of the decoded page (the checker documents the delimiter it chose);
every certificate's span lies inside its snapshot and reads as its text;
dominance, when certified; unit arithmetic, when a factor is stated, in
`Decimal` within the claim's tolerance; every computed claim's inputs exist
and the manifest's root claim exists and is computed; and anything it
cannot check -- regenerating the Antimony, replaying the integration -- is
listed as "not checked" with the reason. One line per check, a summary,
exit 0 when every check passed, 3 when one failed (stderr names the first
failing claim), 2 for a bundle it cannot read; `--json` prints the report.

**7. `caterva why` prints the derivation down to the bytes.** The layout,
with digests elided and spans written as `[start, end)` because the real
numbers are what the test pins:

```
claim:sha256:…  cited  reaction_Km = Km(2.7.1.1, D-glucose, Homo sapiens)
  value        6 mM
  rule         select.resolver v1 (ADR 0047): the row the resolver carried
  settings     dominance = not certified: ordinals unavailable
  input        row:sha256:…
    parser     parse.brenda_table v1 (ADR 0179)
    locator    brenda:2.7.1.1:km:Homo sapiens:D-glucose:641068:6:0
    value      6 mM   substrate D-glucose   organism Homo sapiens
    commentary 30°C, pH 7.5, wild-type
    reference  641068
  certificates 3, each a byte span of the snapshot that reads as its text
    [start, end)  "641068"
    [start, end)  "6"
    [start, end)  "30°C, pH 7.5, wild-type"
  snapshot     snapshot:sha256:3a69b492…5060ef91  brenda_enzyme
    locator    https://www.brenda-enzymes.org/enzyme.php?ecno=2.7.1.1
    retrieved  …T…Z   licence CC BY 4.0   release none stated
    served from  Tests/fixtures/recorded/brenda_2.7.1.1.html.gz
  reference    641068  PMID 7730377
    Xu, L.Z.; Harrison, R.W.; Weber, I.T.; Pilkis, S.J. (1995) J. Biol. Chem. 270, 9939-9946
    Human beta-cell glucokinase. Dual role of Ser-151 in catalysis and hexose affinity
```

The reference block appears when a `brenda_reference` snapshot for the
row's reference is in the bundle; the title and PMID are read from it by
`caterva/evidence/references.py`, not typed in. A ref that is not in the
bundle exits 3 with `Refused:` and the ref. `Tests/citation.py`'s docstring
said BRENDA has no per-reference deep link; the form it tested
(`literature.php?refid=`) is still broken, and the form
`literature.php?e=<EC>&r=<ref>` returns the reference (checked
2026-10-17); the docstring now says which is which.

**8. Exports carry claim ids, and only when asked.** With `--export FORMAT
--claims DIR` the CSV gains a final `claim_id` column, each SBML parameter's
notes gain one `CLAIM <ref>` line, and the Antimony gains `# claim: <ref>`
after each parameter's existing comment. Without `--claims` the writers
take no ids and their bytes are identical to 0.5.1's, which a test holds
them to.

**9. A model may propose an EC number, never supply one.** ADR 0011's rule
for values, applied to identifiers, in the API server's path: the resolver
asks the language model for the enzyme *name as stated in the query* and
for an EC number only if the query text itself contains one; any EC number
the model returns that is not verbatim in the query is dropped, and the
resolved object records that it was dropped and why. The model supplies no
organism either: when the query names none, the runner's own default
applies and is reported as a chosen assumption, as `caterva compose` already
reports it. When the runner receives both an EC number and a name, the
number is used only if the one name policy (`resolve_enzyme`, the finder
behind `resolve_ec_number`) resolves the name to that number, or to a set
of enzymes it is one of (the number is then the disambiguation an
`ec_ambiguous` refusal asks for); otherwise the run is refused with source
`ec_mismatch`, naming both. A name the finder has no answer for leaves the
number standing, and the log says it was not checked: a network failure
is not evidence that a number is wrong. A wrong EC number is a citation
for the wrong protein, which ADR 0178 already called worse than a wrong
value.

**10. The bundle is a directory, and the format is versioned.**
`manifest.json` (`{"format": "caterva-claims/1", "root": "claim:sha256:…",
"written_at": …, "caterva": "0.6.0"}`), one JSON line per claim, row and
snapshot in `claims.jsonl`, `rows.jsonl` and `snapshots.jsonl`, and the raw
bytes gzipped under `snapshots/<hex>.gz`. The report ends with a `## Claims`
section naming the root claim, the counts per kind, the directory and the
line `Re-check offline: caterva verify DIR`.

## What `caterva verify` is held to

`caterva/tests/test_verify_mutations.py` builds the showcase bundle
(`caterva/evidence/showcase.py`: the recorded hexokinase page, the 6 mM row
from reference 641068 with commentary "30°C, pH 7.5, wild-type", the kcat
row from reference 739603, a chosen starting amount and a computed model
claim whose `settings["ir"]` is a stand-in hash, which the docstring says),
copies it, and applies one change per test. Each test asserts that the
failing check names the claim it damaged. Swapping the Km claim's row input
for the kcat row fails the row locator. Flipping the claim's unit to µM
without a factor fails identity; stating a factor of 1000 with a wrong value
fails unit arithmetic. Editing one byte inside the cited row's bytes fails
the snapshot check, and, with the snapshot id rewritten to the new bytes'
hash so that the snapshot check passes, fails the certificate or the row
locator. Editing a byte *outside* every cited row with the id rewritten
passes every check, which is the plan's point: a page may change elsewhere
and the claim stands. Bumping `select.resolver`'s version in the stored
JSON without recomputing the id fails identity, as does dropping a
certificate or editing the tolerance. The same file is the executable form
of the sentence "the dataclass cannot hold a lying id".

## Three smaller things, done on the way

**`docs/ARCHITECTURE_RIGOR.md` is deleted and `docs/ARCHITECTURE.md`
replaces it.** The old document described a language-model "last resort"
tier that ADR 0011's amendment removed, a five-stage pipeline with an
epidemiology bridge that was archived (CHANGELOG, 0.4.0), eleven guards
where there were seventy-seven, and ended "Ready for: Scientific publication,
teaching lab deployment, peer review". Its provenance example cited two
DOIs under the example prefix 10.1234, in a document whose last line said
"Every citation has DOI/PMID". It was classified historical and reached
from a present-tense table row, which is the worst of both: never checked,
always linked. The replacement is one page, present tense, states no
counts, and names the ADR behind each layer. Its description at
`docs/ARCHIVE_TRIAGE.md:30` stays as written, being a record.

**A placeholder-DOI guard.** `scripts/check_no_placeholder_dois.py` reads
every tracked Markdown file for the example prefixes and the `doi:` template
and fails on a hit; `docs/archive/` is not read, as a record, and two root
documents that quote test inputs are allowed with the reason written beside
each, and an allowance that stops being needed fails. It runs in
`verify_build.py` and under `caterva/tests/test_no_placeholder_dois.py`.
Before it was wired it was run: the deleted document and `docs/archive/`
were the offenders, plus the two quoted test inputs, plus one invented
citation ("Smith et al. (2020)" with a template DOI) in each of two root
design documents, which now say in the line itself that no paper is cited.

**A labelled set.** `Tests/fixtures/labelled/` holds the twenty-five human
D-glucose Km rows of the recorded hexokinase page, each labelled by hand
with the isozyme it belongs to (five hexokinase I, one hexokinase II, two
hexokinase III, fifteen glucokinase, two not checked) and with how the label
was read: the row's own commentary, the paper's title, or the UniProt
accession the row carries. `Tests/test_labelled_hexokinase_isozymes.py`
holds the table to the page through the literature layer's parser, in both
directions. It exists so that the isozyme reading of M3 can be scored for
precision and recall against something that is not itself.

## What is built in this slice and what is not

Built, in 0.6.0: the data model, canonical JSON, the store, the bundle
format, the capture hook, the reference-page parser and the showcase
(`caterva/evidence/`); the checker and `caterva verify` (`caterva/check/`);
`caterva why`; `caterva compose --claims DIR` and the claim ids in the
three exports; the EC-number rule in the API server's resolver and runner;
the independence guard and the placeholder-DOI guard; the labelled set.

Not built, and which milestone of the plan each is:

- **Readings** (M3): a row's interpretation as a claim, selection as a
  claim over readings, the isozyme rule the labelled set is for. The
  resolver's ranking is recorded as its pick, not re-derived.
- **Labels** (M3) and **defeats as data** (M4): the persistent engine in
  which a later claim can defeat an earlier one and the defeat is itself
  recorded. Audits, the ledger and synthesis are M4 and after.
- **The Studio's derivation view** (claim to row to snapshot to reference,
  with a re-check action) is a separate change and is not part of what
  this ADR records.
- **Ordinals are certified only when carried.** When the chosen row's
  grades are not among the frontier the resolver returned, the derivation
  says so and the dominance check does not run.
- **A certificate proves presence, not position.** Spans are found with
  `bytes.find`, first occurrence; the checker's row-locator check, which
  requires the reference id and the value within one table row, is what
  ties a number to its row, and "one table row" there is a delimiter
  heuristic the checker documents, not an HTML parse.
- **The value text is what the parser yielded** (a float, formatted with
  fifteen significant digits), not the page's own characters; the
  certificate is what matches the page, and the docstring says so.
- **A bundle proves its own consistency**, not who wrote it or when:
  `retrieved_at` and `written_at` are the writer's statements, and there is
  no signature.
- **Only `brenda_enzyme`, `brenda_reference` and `paper_table` sources.**
  NCBI, UniProt and PubChem answers the search reads are not pinned.
- **The unit factor is the only arithmetic** a derivation may state. Nothing
  interpolates, averages or corrects.

## Consequences

- One command re-checks a model's numbers against the bytes they came
  from, offline, with a program that cannot share the producer's mistakes:
  `caterva compose "Michaelis Menten" --subject 2.7.1.1 --organism human
  --substrate glucose --claims ./claims`, then `caterva verify ./claims`.
- The words are **re-checkable** and **within stated tolerances**. Never
  "verified", never "correct": the checker checks derivations and stated
  reasons against pinned bytes, not the biology.
- The product's behaviour without `--claims` is unchanged, byte for byte in
  the exports, and the exit codes are as before.
- A snapshot in a bundle is dated and is never served as a current answer;
  the rule in `Tests/fixtures/recorded/README.md` is now also the evidence
  layer's.
- `docs/ARCHITECTURE_RIGOR.md` is gone; `docs/README.md` points at
  `docs/ARCHITECTURE.md`.
- Guard count 77 → 79 (`scripts/check_no_placeholder_dois.py`,
  `scripts/check_checker_independence.py`). ADR count 176 → 177.
