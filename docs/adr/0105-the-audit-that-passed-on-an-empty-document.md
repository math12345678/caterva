# ADR 0105: The audit that passed on an empty document

**Status:** Accepted, implemented

**Date:** 2026-08-17

**Context:** `Terium/core/sbml_provenance.py`, `scripts/export_annotated_model.py`,
ADR 0063 (attribution travels with the model)

## How this was found

Installing ruff to lint my own change made `check_python_bug_lints.py`
runnable, and it reports what it does not yet enforce:

```
not yet wired (bug-class, not green): F401 x17, F841 x3
```

F841 is *local assigned and never used* — which is this project's house
defect in one line. Three instances. One of them:

```python
root = etree.fromstring(sbml_text.encode("utf-8"))
sbml_ns = etree.QName(root).namespace      # never read again
```

in `audit_annotations`, the independent RDF reader that exists because
libSBML cannot be trusted to check its own output.

## Two defects behind it

### An HTML error page audits clean

`sbml_ns` is the only value that could tell the audit what kind of document
it was handed. Measured:

```
not SBML at all      ok=True  triples=0  problems=0
an HTML page         ok=True  triples=0  problems=0
empty SBML, no annots ok=True triples=0  problems=0
```

The module already contains a test named
`test_an_unannotated_model_audits_clean_rather_than_erroring`, with the
right reasoning: *"A checker that cannot tell 'nothing to check' from
'something is wrong' is useless on the common case."*

That distinction is correct and it stopped one short. **A document that is
not SBML is not "nothing to check" — it is the wrong document**, and it was
collapsed into the same clean verdict. A fetch returning a 404 page reads as
a model with no annotations.

The namespace is matched by stem (`http://www.sbml.org/sbml/`) rather than
by a list of full URIs, because this repository handles level3/version2/core
from libSBML and level2/version3 and /version4 from BioModels. A check
written against one of those rejects the others, which is how a correctness
guard becomes a compatibility bug. Mutation confirms it: pinning the full
level-3 URI fails the BioModels case.

### The audit cannot see annotations that are simply absent

`annotate_sbml` writes CVTerms, counts them, then audits the serialised
document and refuses to return if the audit reports problems. But
`audit.ok` is **true when the reader finds nothing**. Measured, by deleting
every `<annotation>` block from a freshly annotated document:

```
cvterms_written=3   audit triples=0   ok=True   problems=[]
```

So the check written precisely because *"libSBML happily writes RDF that
libSBML then declines to read"* was blind to the RDF not being there at all.

And this is not hypothetical for this module. Its own comment above
`by_lower` records a pass where the lookup

> annotated NOTHING while still reporting success — two parameters listed
> as unannotated, two model-level CVTerms written, and a green run.

That defect was fixed at the lookup. **The detector that should have caught
it was left unable to**, and stayed that way.

## Decision

The audit stays a standalone reader — it has no way of knowing how many
annotations were intended, and an unannotated model is legitimate. It gains
only the one judgement its own parse supports: *this is not SBML*.

The reconciliation belongs to `annotate_sbml`, the one place that holds both
facts. Two numbers sat in the same function and were never compared:

```python
if len(audit.triples) < cvterms:
    raise ValueError(...)
```

`>=` rather than `==` deliberately: every CVTerm here carries exactly one
resource, so they are equal today, but a term with two resources would yield
more triples than terms and must not fail. Loss always shows up as fewer.

`triples_read_back` is now a field on `AnnotationOutcome`, in `summary()`,
and in the export report's JSON beside `cvterms`. Reporting only the
writer's own count would not mislead — the refusal above guarantees it — but
it leaves a reader trusting the producer's word for the producer's own
output, which is the arrangement the audit exists to replace.

## Consequences

- A total annotation loss is now a raised error rather than a successful
  return with a confident count.
- A non-SBML document is a named problem rather than a clean audit.
- `F841` is clear across `Tests`, `scripts` and `Terium`. It found a real
  defect on its first honest run, in a repository that has had the rule
  configured and unexecuted (ADR 0093) the whole time.
- Two guards were red in this environment for the right reason and were left
  alone: `check_python_bug_lints` refuses to report green without ruff, and
  `check_citation_cff` refuses to call "could not check" a pass. Installing
  each turned a refusal into a real check, and both then passed.
