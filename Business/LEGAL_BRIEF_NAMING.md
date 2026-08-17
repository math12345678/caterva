# Legal brief: the Terrium / Tellurium naming question

**Prepared for a lawyer. Not legal advice — nobody who wrote this is a lawyer.**

The purpose of this document is to let you bill thirty minutes against a
prepared record instead of several hours against a codebase. Every factual
claim below is checkable in this repository, and the check is named.

---

## 1. In one paragraph

Terrium is an open-source enzyme-kinetics simulation tool. It depends on
`libroadrunner` and `antimony`, two libraries produced by the Sauro lab at the
University of Washington. That same lab produces **Tellurium**, an established
systems-biology environment. "Terrium" and "Tellurium" are one letter apart in
the middle. Terrium does not use, fork, or bundle Tellurium, and says so on
every shipping surface — but the names are close, in the same field, and the
similarity was not deliberate. The question for you is whether the name is
defensible, needs changing, or needs permission.

## 2. What Terrium actually is

- An Apache-2.0 licensed tool that resolves enzyme kinetic parameters from the
  literature (BRENDA, PubMed) and simulates reaction models with them.
- Published as eighteen repositories under `github.com/Terrium-sim`.
- Not incorporated. No revenue. No trademark filed for "Terrium".
- Written by a single founder, a high-school student. See §7.

## 3. What Tellurium is, and the relationship

Tellurium is a Python environment for systems and synthetic biology, developed
in Herbert Sauro's laboratory at the University of Washington. It is
long-established, widely used in the field, and academically funded.

The relationship is real but indirect:

| | |
|---|---|
| Terrium **uses** | `libroadrunner` 2.8.0, `antimony` 2.14.0 — both from the Sauro lab |
| Terrium **does not use** | the `tellurium` package, in any form |
| Same field? | Yes. Both are systems-biology simulation tooling. |
| Same audience? | Overlapping. Tellurium serves researchers; Terrium targets students. |

**Prof. Sauro is aware of Terrium.** He replied to a cold email from the
founder and gave substantive technical feedback on the product, which is
recorded in `docs/EXPERT_FEEDBACK.md`. He has not, on the record, raised the
name. That is a fact, not a waiver, and it should not be read as one.

## 4. Why Tellurium is not a dependency — the decision predates the concern

ADR `docs/adr/0001-no-tellurium-umbrella-package.md` records the decision not
to depend on `tellurium`, made on **technical grounds** before the naming
question arose: `tellurium` pulls in `python-libcombine` and `python-libnuml`,
which lack prebuilt wheels on several platforms and fall back to a C++ source
build requiring `cmake` and `swig`. Terrium uses none of that functionality.

This matters to you because it means the separation is genuine and documented
contemporaneously, not constructed afterwards as a defence.

The prohibition is mechanically enforced. `scripts/check_forbidden_packages.py`
fails the build if `tellurium` appears in any dependency manifest or install
script. It currently checks 4 manifests, 2 install scripts, 225 documents, and
runs in CI on every push. There is no Tellurium code in this project, and the
repository cannot acquire any silently.

## 5. What is already in place

Every shipping surface carries a non-affiliation notice, enforced by
`scripts/check_non_affiliation_notice.py` (seven surfaces in the monorepo) and
`scripts/check_published_repo_readmes.py` (the seventeen published front
pages). The NOTICE wording is:

> Tellurium is a separate, established systems-biology environment from the
> same lab. Terrium is unaffiliated with it, is not a fork of it, and does not
> depend on the `tellurium` package. [...] Terrium is a consumer of
> libRoadRunner and Antimony, in the ordinary way those libraries are meant to
> be consumed. The similar name is a mistake and is addressed in README.md and
> docs/RENAME_PLAN.md.

Note the phrase **"the similar name is a mistake"** — that admission is
already public, in the repository, and has been for some time. You may have a
view on whether that helps or hurts.

## 6. The cost of renaming, if it comes to that

Measured, not estimated — see `docs/RENAME_PLAN.md`:

- **452 tracked files** contain the string, **2,651 occurrences**.
- Most of it is prose. Search-and-replace, then the guard suite.
- The importable Python package is `Terium` (one 'r'), distinct from the
  product name `Terrium` — an existing quirk with its own guard.
- The GitHub organisation `Terrium-sim` and eighteen repository names.
- No published package on PyPI or npm under the name, so **no downstream
  users would break**. This is the single most important cost fact: renaming
  now is cheap in a way it will not be after a release.

## 7. The founder is a minor — two separate questions

Recorded in `Business/INCORPORATION_CHECKLIST.md`:

1. **Incorporation.** Most US states require a parent or guardian to sign
   incorporation documents or hold shares in custodial form.
2. **Capacity to grant the licence.** A minor can unambiguously *own*
   copyright. But a licence grant is contract-like, and in most US states a
   minor's contract is voidable by that minor. Terrium's outbound Apache-2.0
   grant and its acceptance of inbound contributions under a DCO are both made
   by a minor.

Please address (2) in the same conversation. It is cheap to fix now — usually
a guardian countersignature or copyright held in trust until majority — and
expensive to discover during someone else's diligence.

## 8. The questions we actually need answered

1. **Is "Terrium" a trademark problem** given "Tellurium" in the same field,
   with an acknowledged dependency relationship on the same lab's libraries?
   Is Tellurium's name even protected as a mark, or only used descriptively?
2. **Does the existing non-affiliation notice do enough**, or does its
   "the similar name is a mistake" phrasing weaken the position?
3. **Should we ask Prof. Sauro / the University of Washington for written
   comfort** — and does asking create risk that not asking avoids?
4. **If we rename, when?** Before any PyPI/npm release is clearly cheapest.
   Is there a reason to move faster than that?
5. **Does the founder's age change the answer** to any of the above,
   particularly the capacity question in §7?
6. **Is "Terrium" registrable at all**, or too close to proceed with?

## 9. Where to verify anything here

| claim | check |
|---|---|
| No Tellurium code or dependency | `python scripts/check_forbidden_packages.py` |
| Non-affiliation notice on every surface | `python scripts/check_non_affiliation_notice.py` |
| Same, for the 17 published repos | `python scripts/check_published_repo_readmes.py` |
| Dependency licences | `python scripts/check_dependency_licenses.py` |
| Rename scale | `docs/RENAME_PLAN.md` |
| Why no `tellurium` dependency | `docs/adr/0001-no-tellurium-umbrella-package.md` |
| Sauro correspondence | `docs/EXPERT_FEEDBACK.md` |
| Minor / capacity | `Business/INCORPORATION_CHECKLIST.md` |
