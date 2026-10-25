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
  that span. A cited row's texts (its reference id, value text, commentary,
  substrate and organism) each get one when the row's bytes on the page
  hold them (`caterva/evidence/rows.py`, `certificates_for`). A text that
  is not found yields no certificate, never an invented span;
- a `Derivation`: a rule (`rule_id`, `version`, the ADR that decided it),
  the refs it consumed, its certificates and its settings, a read-only
  mapping of strings (so a claim cannot be changed in place and keep an
  id that no longer describes it);
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
Identity is order-independent and the tests say so with Hypothesis:
`caterva/tests/test_evidence_claims.py` permutes the keys of an object and
of a derivation's settings (`st.permutations`) and gets the same bytes and
the same id.

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
would not see its calls. After the search, and only with `--claims`, the
run also fetches BRENDA's literature page for each cited reference
(`literature.php?e=<EC>&r=<ref>`, one live request per reference, which
the search itself never makes) so that `caterva why` can name the paper; a
page that cannot be fetched is a note in the report's `## Claims` section
and a refused claim in the store, not a failure of the run, because no
derivation consumes it. Nothing reads a snapshot to answer a later search.
`Tests/fixtures/recorded/README.md`'s rule stands: a recorded page is
served to tests and to nothing else, and a snapshot's `retrieved_at` says
which day it is a record of. The one module of the package that reads
recorded pages, the showcase (`caterva/evidence/showcase.py`, below), reads
them directly to build an example bundle dated as the recordings are, and
nothing a person types calls it. Without `--claims` nothing changes and
nothing from `caterva/evidence/` is imported.

**5. The pick is recorded as a rule; conflict is kept, not resolved.** This
slice records what the resolver chose, under `select.resolver` v1, with the
chosen row's ordinals and the alternatives' in `settings["ordinals"]` when
the resolver carried them, so that the checker can confirm the chosen row
is not strictly dominated. When the ordinals were not carried the
derivation says `dominance = not certified` and the checker reports that
check as not run, never as passed (printed `n/a`, counted under "did not
run", JSON status `"not run"`). What this slice does **not** do is
enumerate readings: the plan's M3, where every row's interpretation
(isozyme, variant, condition) is a claim of its own and a selection is a
claim over readings, is not built, and the frontier's reasoning is still
recomputed live. The report's "where the evidence did not settle" section
(ADR 0178) remains the place the spread is shown.

**6. A separate checker that imports no producer code.** `caterva/check/`
imports only the standard library (on 2026-10-24: `argparse`, `bisect`,
`collections.abc` for type checking only, `dataclasses`, `decimal`,
`hashlib`, `json`, `pathlib`, `re`, `sys`, `typing` and `zlib`),
re-implements canonical JSON from its definition rather than importing it,
and re-finds a row in the pinned bytes by regular expression rather than by
the parser that produced it. The independence is a guard,
`scripts/check_checker_independence.py`, which walks every module under
`caterva/check/` with `ast` and fails on any import outside
`sys.stdlib_module_names` or naming `caterva`, `Tests`, `bs4`, `pydantic`
or `numpy`; its `--selftest` plants a bad import and expects the failure.
The guard is about the checker's own imports: `caterva verify`, like every
subcommand, starts the `caterva` package, whose `__init__` loads the
engine core, and it loads nothing of `caterva/evidence/` or
`caterva/compose/`.

`caterva verify DIR` holds a bundle to eight things: every blob inflates
to at most 64 MiB (`MAX_PAGE_BYTES`; it is read a piece at a time, so a
small file that inflates further is refused before it is held) and its
sha256 equals its snapshot id; every row and claim id recomputes from its
stored fields; every cited claim's row exists, its snapshot exists, its
reference id, value, substrate, organism and commentary are whole cells of
one table row of the decoded page (the checker documents what it takes a
table row to be), and the claim's value and unit are the row's; every
certificate's span lies inside its snapshot and reads as its text, and,
for a cited claim, every span lies inside the one table row that holds the
cited row, and the spans certify its reference, value and commentary;
dominance, when certified; unit arithmetic, when a factor is stated, in
`Decimal` within the claim's tolerance; every computed claim's inputs exist
and the manifest's root claim exists and is computed; and anything it
cannot check -- regenerating the Antimony, replaying the integration -- is
listed as "not checked" with the reason. A check has three states, each
printed as itself: `ok` (it held), `FAIL` (it did not), `n/a` (it did not
run, with the reason). A summary line counts them apart (`18 checks: 18
ok, 0 failed, 0 did not run; 2 not checked.` on the showcase) and gives
the verdict. Exit 0 when no check failed (an `n/a` does not fail the
bundle), 3 when one failed (stderr names the first failing check and
claim), 2 for a bundle it cannot read; `--json` prints the report, each
check with its `status` (`"ok"`, `"failed"` or `"not run"`).

**7. `caterva why` prints the derivation down to the bytes.** Its output
for the showcase's Km claim, as printed on 2026-10-24 with the digests
shortened to their first and last eight hex digits; the spans are the
real ones:

```
claim:sha256:cd8e3853…a0b717d1  cited  reaction_Km = Km(2.7.1.1, D-glucose, Homo sapiens)
  value        6 mM
  rule         select.resolver v1 (ADR 0047): the row the resolver carried: weight-free dominance, then the minimum
  ordinals     chosen row  assay_completeness=2  organism_match=1  variant_statement=2  (higher is better)
               alternative 6.3 mM ref 739603: assay_completeness=2  organism_match=1  variant_statement=2
  input        row:sha256:8dbc83ff…f966fb2f
    parser       parse.brenda_table v1 (ADR 0179): a row read from a BRENDA enzyme page by the literature layer's parser
    locator      brenda:2.7.1.1:km:Homo sapiens:D-glucose:641068:6:0
    value        6 mM   substrate D-glucose   organism Homo sapiens
    commentary   30°C, pH 7.5, wild-type
    reference    641068
  certificates 5, each a byte span of the snapshot that reads as its text
                 [1980757, 1980763)  '641068'
                 [1980265, 1980266)  '6'
                 [1980612, 1980636)  '30°C, pH 7.5, wild-type'
                 [1980376, 1980385)  'D-glucose'
                 [1980477, 1980489)  'Homo sapiens'
  snapshot     snapshot:sha256:3a69b492…5060ef91  brenda_enzyme
    locator      https://www.brenda-enzymes.org/enzyme.php?ecno=2.7.1.1
    retrieved    2026-09-28   licence CC BY 4.0   release none stated
    served from  Tests/fixtures/recorded/brenda_2.7.1.1.html.gz
  reference    641068  PMID 7730377
                 Xu, L.Z.; Harrison, R.W.; Weber, I.T.; Pilkis, S.J. (1995) J. Biol. Chem.
                 Human beta-cell glucokinase. Dual role of Ser-151 in catalysis and hexose affinity
                 read from snapshot:sha256:71fac47b…b62215fe, retrieved 2026-10-17
```

Five certificates: the producer issues one for each of the row's texts
that its table row on the page holds (the reference id, the value, the
commentary, the substrate and the organism), and
`caterva/tests/test_why.py` pins the first three. A claim whose ordinals
the resolver did not carry prints `settings     dominance = not certified:
chosen row's ordinals not carried` (the words `caterva compose --claims`
writes, `ORDINALS_NOT_CARRIED` in `caterva/evidence/compose_claims.py`)
where the two `ordinals` lines are. The journal line is the authors, year
and journal that `caterva/evidence/references.py` reads from BRENDA's
literature page; the page also gives the volume and pages (`270,
9939-9946` for 641068), which the parser does not read and `caterva why`
does not print. The reference block appears when a `brenda_reference`
snapshot for the row's reference is in the bundle; the title and PMID are
read from it by `caterva/evidence/references.py`, not typed in. A ref
that is not in the bundle exits 3 with `Refused:` and the ref; a bundle
whose records do not produce their own ids is not read at all (exit 2,
`Not a claims bundle:` and the line), and `caterva verify` is what names
the check that fails. `--store DIR` reads a store instead, opened
read-only so that it writes nothing: a directory that is not a store (no
`index.sqlite`, or one that is not an evidence store's index) exits 2,
and a store record that does not produce its own id exits 3 with
`Refused:` and why.

`Tests/citation.py`'s docstring said BRENDA has no per-reference deep
link; the form it tested (`literature.php?refid=`) was found broken in
2026-07 and again on 2026-10-24 (for references 641068 and 740541 it
returns BRENDA's generic page, titled "Reference for EC = " with nothing
after it), and the form `literature.php?e=<EC>&r=<ref>` returns the
reference (checked 2026-10-17, and for 641068 again on 2026-10-24); the
docstring now says which is which.

**8. Exports carry claim ids, and only when asked.** With `--export FORMAT
--claims DIR` the CSV gains a final `claim_id` column, each SBML
parameter's and species' notes gain one `CLAIM <ref>` line, the Antimony
gains `# claim: <ref>` after each assignment's existing comment, and the
methods paragraph gains a closing paragraph naming each quantity's claim
ref. Without `--claims` the writers
take no ids, and a test holds each writer's output without the keyword
equal to its output with `claim_ids=None` and free of any claim ref
(`caterva/tests/test_export_claim_ids.py`); the other tests there remove
the ids from the with-ids artefact and find the plain one. No test compares
an artefact with one 0.5.1 wrote. That was done by hand on 2026-10-24: the
four writers' output for the test's model (the CSV, the Antimony, the SBML
and the methods paragraph) is byte for byte what the `v0.5.1-rc.2` tree,
with its own literature layer, writes for the same model.

**9. A model may propose an EC number, never supply one.** ADR 0011's rule
for values, applied to identifiers, in the API server's path: the resolver
asks the language model for the enzyme *name as stated in the query* and
for an EC number only if the query text itself contains one; any EC number
the model returns that is not verbatim in the query is dropped, and the
resolved object records that it was dropped and why. The model supplies no
organism either: when the query names none, the API server's documented
default (Homo sapiens, applied by its query resolver; the runner applies
none, `Tests/test_no_default_organism.py`) is used and reported in the
response's flags as an assumption (`assumed: organism = Homo sapiens. The
query names no organism, ...`), as `caterva compose` reports the organism
its search chose when no `--organism` was given. When the runner receives both an EC number and a name, the
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
bytes gzipped under `snapshots/<hex>.gz`. The report's last section, before
the footer, is `## Claims`: the root claim, the counts per kind, the
directory and the line `Re-check offline: caterva verify DIR`. A
description that builds nothing ("Not built.", exit 3) writes nothing under
DIR; once a model is built, a valid bundle is written even if the search or
the export then refuses.

## What `caterva verify` is held to

`caterva/tests/test_verify_mutations.py` builds the showcase bundle
(`caterva/evidence/showcase.py`: the recorded hexokinase page, the 6 mM row
from reference 641068 with commentary "30°C, pH 7.5, wild-type", the kcat
row from reference 739603, a chosen starting amount and a computed model
claim whose `settings["ir"]` is a stand-in hash, which the docstring says)
once per test session with the network made impossible
(`caterva/tests/evidence_showcase_offline.py`), copies it, and applies one
change per test. Each test asserts that the failing check names the claim
it damaged. Where the change is a changed derivation rather than a lying
id, the id is recomputed with the producer's own `make_claim`, so that
identity is not the check that fires.

- Swapping the Km claim's row input for the kcat row fails the row locator
  and the certificate
  (`test_swapping_the_km_rows_input_for_the_kcat_row_fails_the_row_locator_and_the_certificate`):
  the value is not the row's, and the spans the claim kept lie in a table
  row that does not hold the row it now cites.
- A certificate is held to the cited row. Citing the 0.63 mM D-glucose row
  of reference 702314 with the spans of the 0.63 mM ATP row of reference
  641068 fails the certificate; before the row tie (found 2026-10-24) it
  passed every check, because the value matched and every span read. So
  does citing the D-glucose kcat row of reference 674800 (Mus musculus,
  53.2 1/s) with the spans of the ATP row that shares its reference, value
  and commentary, which is why the substrate and the organism are cells of
  the one row too. A claim whose only span is in the page's `<title>`, one
  whose spans lie in two table rows, one with no span for its value and a
  cited claim with no span at all each fail the certificate. Citing the
  D-glucose row of each pair with its own spans passes.
- Flipping the claim's unit to µM without a factor fails identity; stating
  a factor of 1000 with a wrong value fails unit arithmetic.
- Editing one byte inside the cited row's bytes fails the snapshot check,
  and, with the snapshot id rewritten to the new bytes' hash so that the
  snapshot check passes, fails the certificate or the row locator.
- Editing a byte in a row no claim cites, with the snapshot id and every id
  that depends on it recomputed, passes every check: the same derivation
  re-applies to the changed page. The ids do not survive (a row's snapshot
  is one of its fields, and a claim's inputs name the row); what the test
  shows is that the derivation does.
  `test_one_byte_in_an_uncited_part_of_the_page_with_the_id_rewritten_re_derives_and_every_check_passes`
  is run on two places: a neighbouring row (the 60.4 1/s row of reference
  703624, in the same table group as the cited kcat row) and the page's
  title.
- A blob that inflates past 64 MiB in place of the page fails the snapshot
  check, naming the claims that rest on it, and is read no further than the
  bound.
- Bumping `select.resolver`'s version in the stored JSON without
  recomputing the id fails identity, as does dropping a certificate or
  editing the tolerance.

The same file is the executable form of the sentence "the dataclass cannot
hold a lying id".

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
`verify_build.py` and under `caterva/tests/test_no_placeholder_dois.py`,
which also holds the allowances to the guard's rule that they only shrink:
a new entry fails until the test's own list is widened in review.
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
four exports (CSV, SBML, Antimony and the methods paragraph); the
EC-number rule in the API server's resolver and runner; the independence
guard and the placeholder-DOI guard; the labelled set.
Also in 0.6.0, as a separate change this ADR does not record: the Studio's
derivation view (claim to row to snapshot to reference, on the Compose
screen) and its "Re-check this run" action, which runs this checker over a
run's bundle (`docs/studio/CONTRACT.md`, sections 7, 9, 11, 13, 17 and 18).

Not built, and which milestone of the plan each is:

- **Readings** (M3): a row's interpretation as a claim, selection as a
  claim over readings, the isozyme rule the labelled set is for. The
  resolver's ranking is recorded as its pick, not re-derived.
- **Labels** (M3) and **defeats as data** (M4): the persistent engine in
  which a later claim can defeat an earlier one and the defeat is itself
  recorded. Audits, the ledger and synthesis are M4 and after.
- **Ordinals are certified only when carried.** When the chosen row's
  grades are not among the frontier the resolver returned, the derivation
  says so and the dominance check does not run (it prints `n/a`).
- **"One table row" is a delimiter heuristic, not an HTML parse.** The
  checker takes a row to run from one BRENDA row opening (a div whose id is
  `tab<N>r<N>` or `tab<N>r<N>sr<N>` and whose class starts with `row` or
  `hidden`; a table's header row, `tab<N>_head`, opens one too) to the
  next, and a text counts only as a whole cell of it. The row locator and
  the certificate both rest on that: a cited claim's spans must lie in a
  row that holds the cited row's reference, value, substrate, organism and
  commentary. Until 2026-10-24 the certificate proved presence only, and a
  claim could carry another row's spans and pass. What it still does not
  tell apart is two table rows that hold the same five texts: either one
  satisfies both checks, so the locator's index among duplicates is the
  producer's statement, not something re-checked (the checker's docstring,
  "What is not checked"). A page whose markup changes shape needs the
  heuristic changed with it, and the checker's docstring says what it
  looked at.
- **The value text is what the parser yielded** (a float, formatted with
  fifteen significant digits), not the page's own characters; the
  certificate is what matches the page, and the docstring says so.
- **A bundle can be re-checked for its own consistency**, not for who
  wrote it or when:
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
