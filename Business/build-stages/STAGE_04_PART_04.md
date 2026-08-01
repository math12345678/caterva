# Stage 4, Part 4 — Verification: the citations, checked against the literature

Stage 4 of 100. Part 4.

## 0. What this part verifies, and why it is the right target

Part 3 built per-parameter provenance and renamed `citations` to
`modelCitations` so a model reference could never again be mistaken for a
parameter reference. That work landed and its structural tests pass.

But structural correctness says nothing about whether the citations are
*true*. Target B asserts that no citation appears on a non-resolved
parameter. It does not assert that "Hoare M.R., Pal P. (1971) Physical
clusters of simple liquids" is a real paper.

For a product whose claim is *"every number traces back to a citation that
has been independently checked,"* an unchecked citation is the one defect
that attacks the thesis directly. So this part does the obvious thing that
had not been done: look every citation up.

Eight domains, seven distinct references. **Three were wrong.**

## 1. Method

Each reference was searched against primary sources and indexes, and the
title, authors, year, journal, volume and page range compared to what the
code claims. Nothing was accepted from memory — including the references
Terrium's own earlier stages had used correctly.

## 2. Findings

### 2.1 Molecular dynamics — WRONG TITLE

```
claimed  Hoare M.R., Pal P. (1971) Physical clusters of simple liquids.
actual   Hoare M.R., Pal P. (1971) Physical cluster mechanics: statics and
         energy surfaces for monatomic systems.
         Advances in Physics 20(84), 161-196.
```

The title in the code does not exist. The real paper is the one that
determined minimum-energy geometries for Lennard-Jones clusters — the source
of the `LJ13 = -44.326801` value Stage 3 verified against and the reason
Target E is literature-backed at all.

This is the sharpest finding in the audit. **Stage 3 cited this paper
correctly**, in `STAGE_03_PART_02.md` and in the test docstring, with the
right title and page range. The application layer then attached a fabricated
title to the same reference. The engine's citation discipline did not
propagate across the boundary — which is the same structural gap Part 1
found for domain dispatch, recurring in the provenance layer.

### 2.2 PCR — truncated title, no source detail

```
claimed  Mullis K. et al. (1986) Specific enzymatic amplification of DNA
         in vitro.
actual   Mullis K., Faloona F., Scharf S., Saiki R., Horn G., Erlich H.
         (1986) Specific enzymatic amplification of DNA in vitro: the
         polymerase chain reaction.
         Cold Spring Harbor Symposia on Quantitative Biology 51, 263-273.
```

The dropped subtitle is the half naming the technique. A reader searching
the truncated string finds the paper only by luck.

### 2.3 Two-locus Wright-Fisher — truncated title

```
claimed  Lewontin R.C. (1964) The interaction of selection and linkage.
actual   Lewontin R.C. (1964) The interaction of selection and linkage.
         I. General considerations; heterotic models.
         Genetics 49(1), 49-67.
```

The Roman numeral matters: this is part I of a series, and the citation as
written is ambiguous between them.

### 2.4 Wright-Fisher — correct, but attributing half the model

```
claimed  Fisher R.A. (1930) The Genetical Theory of Natural Selection.
```

Real book, correct year. But the domain is called **Wright-Fisher**, and
Wright is not cited. Added:

```
Wright S. (1931) Evolution in Mendelian populations. Genetics 16(2), 97-159.
```

Not an error so much as an incomplete attribution — and in a provenance
feature, incomplete attribution is the failure mode being guarded against.

### 2.5 Verified correct

```
Kermack W.O., McKendrick A.G. (1927) A contribution to the mathematical
theory of epidemics. Proceedings of the Royal Society A 115(772), 700-721.

Metropolis N., Ulam S. (1949) The Monte Carlo method.
Journal of the American Statistical Association 44(247), 335-341.
```

Both titles were right. Both were missing journal, volume and pages, so a
reader could not follow them without a search. Both expanded.

The BRENDA entry is a database, not a paper, and correctly carries a URL
rather than a page range.

## 3. What changed

All seven references in `DOMAIN_DEFAULTS` now carry full bibliographic
detail: authors, year, full title, journal, volume, pages. Verified balanced
and structurally intact after editing; the Python suite is unaffected, since
this is TypeScript-only.

## 4. The finding underneath the findings

Three of seven citations were wrong, in the feature built specifically to
make citations trustworthy, in a product whose entire pitch is citation
integrity.

None of Part 3's tests could have caught it. Target A checks key
correspondence. Target B checks that citations only appear on resolved
parameters. Both passed throughout — they verify the *shape* of the
provenance record, and a fabricated title is a perfectly well-shaped string.

This is the provenance-layer instance of a pattern this project keeps
rediscovering:

- Stage 2 — a mutation report claimed three failing tests; the rerun found two.
- Stage 3 — a comment cited `STAGE_04_PART_01 §6.3`; the section did not exist.
- Stage 4 Part 2 — an MD timing of "~11s" that had never been measured.
- Stage 4 Part 4 — a paper title that does not exist.

Each time: a plausible-looking claim, structurally valid, unchecked, and
wrong. Each time it was cheap to check and nobody had. Rule 1 exists for
numerical claims. **It applies equally to bibliographic ones**, and the
codebase had no mechanism enforcing that.

## 5. Recommendation carried to Part 5

A citation-format guard, in the same spirit as
`check_rng_convention.py` — an executable check rather than a review habit.
It cannot verify a paper exists, but it can require that every
`modelCitations` entry carries authors, a year in parentheses, and either a
volume/page range or a URL. A bare title like *"Physical clusters of simple
liquids."* would have failed that check immediately, because it has no
journal, no volume, no pages — the very fields whose absence made it
unverifiable.

That is the honest scope of what automation can do here. It converts
"someone should look these up" into "an unlookuppable citation cannot merge,"
which is the difference between a habit and a guard.

Stage 5's provenance contract should also decide whether a `resolved`
citation must satisfy a stricter format than a `modelCitations` entry, since
those are the ones actually attached to numbers.

## 6. Status

| Reference | Verdict |
|---|---|
| Hoare & Pal (1971) | **wrong title** — corrected |
| Mullis et al. (1986) | truncated — expanded |
| Lewontin (1964) | truncated — expanded |
| Fisher (1930) | correct; Wright (1931) added |
| Kermack & McKendrick (1927) | correct — detail added |
| Metropolis & Ulam (1949) | correct — detail added |
| BRENDA | correct (database, URL) |

## 7. References verified during this part

- Hoare, M. R. & Pal, P. (1971). *Physical cluster mechanics: statics and
  energy surfaces for monatomic systems.* Advances in Physics 20(84),
  161–196.
- Mullis, K., Faloona, F., Scharf, S., Saiki, R., Horn, G. & Erlich, H.
  (1986). *Specific enzymatic amplification of DNA in vitro: the polymerase
  chain reaction.* Cold Spring Harbor Symposia on Quantitative Biology 51,
  263–273. DOI 10.1101/SQB.1986.051.01.032
- Lewontin, R. C. (1964). *The interaction of selection and linkage.
  I. General considerations; heterotic models.* Genetics 49(1), 49–67.
  DOI 10.1093/genetics/49.1.49
- Metropolis, N. & Ulam, S. (1949). *The Monte Carlo method.* Journal of the
  American Statistical Association 44(247), 335–341.
  DOI 10.1080/01621459.1949.10483310
- Kermack, W. O. & McKendrick, A. G. (1927). *A contribution to the
  mathematical theory of epidemics.* Proceedings of the Royal Society A
  115(772), 700–721.
- Wright, S. (1931). *Evolution in Mendelian populations.* Genetics 16(2),
  97–159.
- Fisher, R. A. (1930). *The Genetical Theory of Natural Selection.* Oxford:
  Clarendon Press.
