# ADR 0063: Attribution travels with the model, not with the repository

**Status:** Accepted, implemented

**Date:** 2026-08-15

**Relates to:** the `NOTICE` / `LICENSE` work that answered Jeske's licence
question for the repository, ADR 0027 and ADR 0038 (computed and not
delivered), ADR 0024 (Jeske's cross-species opt-in), and Sauro's
annotated-model export

## Context

Dr Lisa Jeske (BRENDA / Leibniz Institute DSMZ) raised BRENDA's CC BY 4.0
obligations directly. `NOTICE` answers them thoroughly: creator, copyright,
licence URI, warranty disclaimer, an itemised list of the modifications
Caterva makes, and BRENDA's own citation request.

**`NOTICE` stays in the repository. The model does not.**

Measured on the real exporter before this change, a generated Antimony model
containing two BRENDA-derived values read:

```
Vmax = 5.0;  // CROSS-SPECIES -- brenda_cross_species; in Oryctolagus cuniculus; BRENDA ref 649716
Km = 2.5;  // brenda_exact; in Homo sapiens; BRENDA ref 740253
```

```
mentions BRENDA        : True
mentions CC BY / licence: False
mentions DSMZ / Leibniz : False
```

It names BRENDA as a reference id and says nothing about who licensed the
data or under what terms. That file is the artifact a student actually
shares — attached to a lab report, emailed to a demonstrator, committed
beside a paper — and it travels alone.

The attribution existed where a lawyer would look and not where the data
went. The same last-mile shape as ADR 0027 (score computed, discarded at the
boundary) and ADR 0038 (effectors compared, never reaching the response),
applied to a licence obligation instead of a computation.

## Decision

`caterva/core/data_sources.py` holds the attribution facts for each source
Caterva redistributes values from, and `annotate_antimony` writes a block
into every model naming the sources **that model actually used**.

### What the licence asks for, read rather than remembered

From the legal code at
`https://creativecommons.org/licenses/by/4.0/legalcode.en`:

| clause | requirement | where it lands |
|---|---|---|
| §3(a)(1)(A)(i) | identification of the creator | `creator` |
| §3(a)(1)(A)(iii)–(iv) | notice of the licence and of the warranty disclaimer | `licence`, pointer to NOTICE |
| §3(a)(1)(A)(v) | a URI to the Licensed Material | `source_uri` |
| §3(a)(1)(B) | indicate if you modified it | `modifications` |
| §3(a)(1)(C) | name the licence and link its text | `licence`, `licence_uri` |

§3(a)(2) is what sets the size of the block:

> You may satisfy the conditions […] in any reasonable manner based on the
> medium, means, and context […]. For example, it may be reasonable to
> satisfy the conditions by providing a URI or hyperlink to a resource that
> includes the required information.

So the block carries the creator, the licence, two URIs and a one-line
summary of the modifications, and points at `NOTICE` for the rest — rather
than inlining several pages of it into every model file.

### What this deliberately does not claim

**Not that the obligation certainly applies.** Whether a handful of numeric
values is "the Licensed Material" at all is genuinely unsettled: bare facts
are not copyrightable in the United States, and §4(c) conditions the sui
generis database-right obligation on Sharing "all or a substantial portion
of the contents". Four Km values are not a substantial portion of BRENDA.

This is therefore not compliance performed under legal certainty. It is the
cheap and correct thing to do while the answer is unclear, and it is also
the scientific courtesy Jeske was asking for independently of the licence.
Saying which of the two it is — rather than implying a legal conclusion
nobody here is qualified to reach — is the honest framing, and the module
says so in the same words.

**Not that the licensor endorses the model.** CC BY 4.0 §2(a)(6) forbids
implying that your use is "sponsored, endorsed, or granted official status
by, the Licensor". This is not boilerplate in this project: a researcher
already read a Caterva outreach email as claiming credit that was not ours,
and a block naming DSMZ beside Caterva's generated numbers is the same shape
misread. The block states the non-endorsement outright:

> None of these sources produced, reviewed or endorsed this model. Caterva
> selected and combined the values; any error in doing so is Caterva's, not
> theirs.

### Credited only when they contributed

`attribution_lines` emits a source's block only when a parameter in *that
model* came from it. A model built entirely from user-supplied values names
nobody, and a test pins that.

This is not tidiness. Naming BRENDA on a model BRENDA contributed nothing to
is a false statement about provenance — the defect class this project is
organised around — and under §2(a)(6) it is also precisely what the licence
forbids implying.

A source appearing in the provenance with no licence record produces a line
saying so, never silence. "We do not know the terms" and "there are no
terms" must not render alike.

The detection is deliberately narrow — a label naming a reference id or a
URL is a source, anything else is not — because `origin: user` triggering an
"unknown licence" warning on every hand-supplied value would train readers
to skip the block. That is ADR 0028's reasoning about buffer strings applied
to a different cry-wolf.

## Verification

`caterva/tests/test_data_sources.py` (13) asserts the licence *elements*
rather than the wording, so the block can be rephrased but not thinned.
`scripts/check_data_source_attribution.py` fails when the table and `NOTICE`
disagree — two statements of one licence, which drift the way ADR 0003's two
numeric bounds drifted.

Three mutations on the attribution, all caught by tests:

| Mutation | Caught by |
|---|---|
| the block never reaches a model | `test_the_block_reaches_a_real_annotated_model` |
| every source credited regardless of contribution | `test_user_and_structural_notes_are_not_mistaken_for_databases` |
| an undescribed source dropped silently | `test_an_undescribed_source_is_named_not_dropped` |

### The consistency guard caught two real errors in the table

On its first run, against my own transcription:

- the creator read "the BRENDA team, Leibniz Institute DSMZ" where `NOTICE`
  says "the BRENDA team **at the** Leibniz Institute DSMZ", with an em dash
  rather than a double hyphen;
- the table carried an NCBI Taxonomy URI that appears nowhere in `NOTICE` —
  a URI this project would have asserted in exported files and could not
  point at in its own records.

Both are small, and both are the reason the guard compares literally rather
than approximately.

### The guard I wrote to prevent the defect had the defect

Mutation M1 deletes the single line in `model_provenance.py` that puts the
block into a model. Tests caught it. **The guard exited 0.**

It called `attribution_lines` directly, so it verified that the text could
be *produced*, not that a model *receives* it — a copy of the thing instead
of the thing, while its own docstring claimed:

> The attribution block a model receives actually contains the licence and
> the creator — rendered, not merely stored. A table nobody renders is ADR
> 0027 again.

It now goes through `annotate_antimony`. Doing so immediately crashed on a
hand-rolled `_Entry` stub carrying only `source` and `citation`: enough for
the renderer, not enough for the annotator. The stub had been quietly
holding the guard to the shallower path. It is a real `ParameterProvenance`
now.

That is the sixth instance of this shape in the project's records and the
second this session. Every one was found by mutation or by a test failing —
none by reading, including this one, which sat inside a docstring
specifically disclaiming it.

### SBML had the same gap, in the format that travels furthest

Fixing the Antimony export did not fix the SBML one. `build_sbml` strips the
Antimony comments before converting — rightly, since the same facts in two
encodings inside one file rot apart — and that strips the attribution with
them. Measured through the real exporter, by disabling the fix and
re-running:

```
model notes never set:  SBML carries the licence: False | licensor: False
restored:               SBML carries the licence: True  | licensor: True
```

SBML is what a student opens in COPASI or Tellurium months later, and it was
the export carrying no credit at all.

The attribution now goes into the model's `<notes>` as XHTML. **Notes, not a
model-level CVTerm:** a `bqmodel:isDescribedBy` pointing at BRENDA would
assert that BRENDA describes *this model*, which is false and is the
endorsement §2(a)(6) forbids implying. The per-parameter CVTerms already
carry each value's machine-readable identity; this is the human-readable
credit for the file as a whole.

Both encodings render from one `attribution_fields`, so they cannot come to
say different things about the same licence, and
`test_both_encodings_state_the_same_licence` asserts field by field that
they do not.

### Measuring the wrong artifact, nearly

The claim "SBML has the same gap" was first produced by running
`export_annotated_model.py --format sbml` — which takes **no command-line
arguments at all**. The flag was ignored, the script emitted Antimony,
reported `"ok": true`, and the Antimony output was read as evidence about
SBML.

Caught only because the response body said `"format": "antimony"`. This is
the ADR 0035 error one step from being repeated: a claim measured off a
reconstruction presented as a claim about the real path.

The cause is fixed rather than the instance: the script now rejects any
argument instead of ignoring it. That is the same defect as `claim_adr.py
--help` writing `0044---help.md` — an argument nobody parses means whatever
the reader hoped it meant.

### A flattening helper that mangled the URLs it was checking

`text.replace("//", " ")`, used to strip Antimony comment markers before
substring assertions, also eats the `//` in `https://`. Every URI assertion
written against it was comparing against a corrupted string.

It surfaced as `test_both_encodings_state_the_same_licence` failing on a
licence URI that *was* present. The renderer was right and the test's helper
was wrong — the third time this session that a verification artifact, rather
than the code, was the thing at fault.

The guard had the same line. It had been passing by luck: its two URI checks
run against `NOTICE`, which is not flattened. With the flattening fixed, the
guard can now assert that §3(a)(1)(A)(v) and §3(a)(1)(C)'s URIs actually
reach the model, which it previously could not — mutation confirms it fails
when the licence URI is dropped.

## Consequences

- Every exported model containing resolved values gains an attribution
  block. Existing golden comparisons on exported *text* will change; golden
  comparisons on simulation *results* cannot, and the round-trip test
  asserts `strip_annotations` still recovers the original model exactly.
- `NOTICE` remains authoritative. The table transcribes it, the guard
  enforces the transcription, and a licence change is made in `NOTICE`
  first.
- Sources are added by adding a row, not by editing the renderer.
- This does not answer whether the obligation legally attaches to a handful
  of values. It makes the question moot by complying anyway.
