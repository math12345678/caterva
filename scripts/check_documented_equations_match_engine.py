#!/usr/bin/env python3
"""The equations Terrium documents must be the equations Terrium solves.

WHAT THIS COMES FROM
--------------------
`LITERATURE_BACKING_DATABASE.md` is the document that says every number in
this product is traceable to literature. Audited on 2026-09-05 against the
engine it describes, four of its model sections described something the
engine does not compute:

  PCR        Documented `N(n) = N0 x E^n` with E in [0.85, 1.0] -- a DECAY
             formula. At 30 cycles with E = 0.9 that is 0.042*N0: a PCR
             reaction that destroys 96% of its template. `pcr.py` computes
             `n0 * (1.0 + efficiency) ** cycle` = 5.2e8*N0. The documented
             and implemented formulas differed by a factor of 1.2e10.

  PCR        Documented the plateau as "after ~30 cycles, reagent depletion
  plateau    limits amplification". The engine's plateau is opt-in and
             logistic, `N + E*N*(1 - N/K)`; where a curve flattens depends
             on K, N0 and E, not on the number 30.

  SIR/SEIR   Documented `dS/dt = -beta*S*I` (density-dependent).
             `model_building.py` emits `beta * S * I / N`
             (frequency-dependent). Not a notational variant: R0 = beta/gamma
             under the engine's form but beta*N/gamma under the documented
             one. A reader recomputing R0 for the shipped COVID-19 numbers
             and N = 1000 would have got 3140 instead of 3.14.

  Gillespie  Documented "Method: Tau-leaping algorithm", and claimed
             "Implementation: Adaptive tau-selection". `gillespie_ssa.py`
             implements the EXACT Direct Method and says so in its own
             docstring; there is no tau-leaping anywhere in the tree.
             (Tau-leaping is also 25 years younger than the paper it was
             attributed to.)

Every one of these was wrong in the document and right in the code. Prose
drifts away from code silently because nothing reads both. This does.

WHAT THIS CHECKS
----------------
For each model: a string the document MUST contain, a set of strings the
ENGINE source must contain, and -- where a specific wrong form is known to
have shipped -- a pattern the document must NOT contain.

Both halves matter. Requiring only the document text lets someone change
the engine and leave the page describing the old maths. Requiring only the
engine text lets the page rot on its own. Requiring both means the pair has
to be edited together or this fails.

Correction blockquotes are exempt from the forbidden-pattern check. Lines
beginning with `>` are *discussing* an old formula, not asserting it -- the
same rule `verify_citations_live.py` applies to DOIs named in comments. A
check that fired on its own correction note would force the evidence to be
deleted to make the check pass, which is precisely backwards.

Usage:
    python scripts/check_documented_equations_match_engine.py
    python scripts/check_documented_equations_match_engine.py --selftest
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
DOC = REPO_ROOT / "LITERATURE_BACKING_DATABASE.md"

PCR_PY = REPO_ROOT / "Terium" / "discrete" / "pcr.py"
MODEL_BUILDING_PY = REPO_ROOT / "Terium" / "continuous" / "model_building.py"
GILLESPIE_PY = REPO_ROOT / "Terium" / "discrete" / "gillespie_ssa.py"
MD_PY = REPO_ROOT / "Terium" / "discrete" / "molecular_dynamics.py"

#: Not documentation in the filing sense -- this is a LIVE SURFACE. Its
#: `description` strings are served to users through
#: /api/pipeline/literature and the domain citation endpoints, so a wrong
#: equation here is read by more people than a wrong equation in the
#: markdown. Both carried the same PCR decay formula and the same
#: density-dependent SIR until 2026-09-05; the markdown was audited first
#: and this file was found only because the fix was checked for
#: propagation. Corrections that land in one place and not the other are
#: this repository's oldest recurring shape.
DOMAIN_LITERATURE_TS = (
    REPO_ROOT
    / "Science-Agent-Pipeline"
    / "artifacts"
    / "api-server"
    / "src"
    / "lib"
    / "domain-literature.ts"
)


@dataclass
class Check:
    """One model, documented in one place and implemented in another."""

    name: str
    #: Text the document must contain verbatim.
    doc_required: List[str]
    #: (engine file, strings that file must contain verbatim).
    engine_required: List[Tuple[Path, List[str]]]
    #: (regex, human description) the document must NOT assert. Checked
    #: against the document with correction blockquotes removed.
    doc_forbidden: List[Tuple[str, str]] = field(default_factory=list)
    #: Strings the user-facing surface must contain verbatim.
    surface_required: List[str] = field(default_factory=list)
    #: (regex, description) the user-facing surface must NOT assert.
    #: Checked with `//` and `*` comment lines removed, for the same
    #: reason blockquotes are stripped from the markdown: a comment
    #: recording what a description USED to say is discussing it.
    surface_forbidden: List[Tuple[str, str]] = field(default_factory=list)


CHECKS: List[Check] = [
    Check(
        name="PCR amplification",
        doc_required=["N(n) = N₀ × (1 + E)ⁿ"],
        engine_required=[(PCR_PY, ["(1.0 + efficiency) ** cycle"])],
        doc_forbidden=[
            # The shipped defect. `N₀ × E^n` with E <= 1 is decay.
            (r"N₀\s*[×x]\s*E\s*\^?\s*n\b", "the decay form `N₀ × E^n`"),
        ],
        surface_required=["N(n) = N0 × (1 + E)^n"],
        surface_forbidden=[
            (r"N0\s*[×x]\s*E\s*\^\s*n\b", "the decay form `N0 × E^n`"),
        ],
    ),
    Check(
        name="PCR plateau",
        doc_required=["N(c+1) = N(c) + E·N(c)·(1 - N(c)/K)"],
        engine_required=[
            (PCR_PY, ["copies + efficiency * copies * (1.0 - copies / plateau_capacity)"])
        ],
        doc_forbidden=[
            (
                r"After\s*~?30\s*cycles,\s*reagent depletion",
                "a plateau tied to a fixed cycle count",
            ),
        ],
    ),
    Check(
        name="SIR",
        doc_required=[
            "Equations Terrium actually integrates",
            "dS/dt = -β·S·I/N",
            "dI/dt = β·S·I/N - γ·I",
            # The consequence a reader would otherwise get wrong by N.
            "**R₀ = β/γ**",
        ],
        engine_required=[
            (MODEL_BUILDING_PY, ["J0: S -> I; beta * S * I / N;"]),
        ],
        surface_required=["dS/dt = -β·S·I/N", "dI/dt = β·S·I/N - γ·I"],
        surface_forbidden=[
            (r"dS/dt = -β·S·I(?!/N)", "the density-dependent form `dS/dt = -β·S·I`"),
        ],
    ),
    Check(
        name="SEIR",
        doc_required=["dS/dt = -β·S·I/N\n  - dE/dt = β·S·I/N - σ·E"],
        engine_required=[
            (MODEL_BUILDING_PY, ["J0: S -> E; beta * S * I / N;"]),
        ],
        surface_required=["dE/dt = β·S·I/N - σ·E"],
        surface_forbidden=[
            (r"dE/dt = β·S·I(?!/N)",
             "the density-dependent form `dE/dt = β·S·I`"),
        ],
    ),
    Check(
        name="Gillespie SSA",
        doc_required=["exact SSA (Gillespie's Direct Method)"],
        engine_required=[
            (GILLESPIE_PY, ["Gillespie's Direct Method", "tau = -math.log("]),
        ],
        doc_forbidden=[
            (
                r"\*\*Method\*\*:\s*Tau-leaping",
                "tau-leaping named as the implemented method",
            ),
            (
                r"\*\*Implementation\*\*:\s*Adaptive tau-selection",
                "an adaptive tau-selection implementation that does not exist",
            ),
        ],
    ),
    Check(
        name="Molecular dynamics",
        doc_required=["V(r) = 4ε[(σ/r)¹² - (σ/r)⁶]"],
        engine_required=[
            (MD_PY, ["4.0 * (r12_inv - r6_inv)", "velocity Verlet"]),
        ],
    ),
]


def strip_correction_blockquotes(doc: str) -> str:
    """Drop blockquote lines, which discuss old text rather than assert it.

    Mirrors `verify_citations_live.py`'s rule for DOIs in comments. Without
    this, a correction note quoting the formula it corrects would keep the
    guard red until the evidence was deleted.
    """
    return "\n".join(
        line for line in doc.splitlines() if not line.lstrip().startswith(">")
    )


def strip_code_comments(source: str) -> str:
    """Drop `//` and `*` comment lines from a TypeScript source.

    Same rule as `strip_correction_blockquotes`, for the same reason: a
    comment recording what a description used to say is discussing the old
    text, and a guard that fired on it would force the explanation to be
    deleted to go green.
    """
    return "\n".join(
        line
        for line in source.splitlines()
        if not line.lstrip().startswith(("//", "*", "/*"))
    )


def audit(doc: str, engine: Dict[Path, str]) -> List[str]:
    """Return one failure line per mismatch. Empty list means clean.

    Pure: takes the file contents rather than reading them, so --selftest
    can feed it mutated copies without touching the working tree.
    """
    failures: List[str] = []
    asserted = strip_correction_blockquotes(doc)

    for check in CHECKS:
        for needle in check.doc_required:
            if needle not in doc:
                failures.append(
                    f"{check.name}: {DOC.name} no longer contains "
                    f"{needle!r} -- the page and the engine have diverged."
                )
        for path, needles in check.engine_required:
            source = engine.get(path)
            if source is None:
                failures.append(
                    f"{check.name}: engine source {path} is missing; the "
                    f"documented equation is backed by nothing."
                )
                continue
            for needle in needles:
                if needle not in source:
                    failures.append(
                        f"{check.name}: {path.name} no longer contains "
                        f"{needle!r} -- the engine changed and "
                        f"{DOC.name} still describes the old behaviour."
                    )
        for pattern, description in check.doc_forbidden:
            if re.search(pattern, asserted):
                failures.append(
                    f"{check.name}: {DOC.name} asserts {description}, which "
                    f"the engine does not implement."
                )

        if not (check.surface_required or check.surface_forbidden):
            continue
        surface = engine.get(DOMAIN_LITERATURE_TS)
        if surface is None:
            failures.append(
                f"{check.name}: {DOMAIN_LITERATURE_TS} is missing, so the "
                f"description served to users was not checked."
            )
            continue
        surface_asserted = strip_code_comments(surface)
        for needle in check.surface_required:
            if needle not in surface:
                failures.append(
                    f"{check.name}: {DOMAIN_LITERATURE_TS.name} no longer "
                    f"contains {needle!r} -- the equation SERVED TO USERS "
                    f"has drifted from the engine."
                )
        for pattern, description in check.surface_forbidden:
            if re.search(pattern, surface_asserted):
                failures.append(
                    f"{check.name}: {DOMAIN_LITERATURE_TS.name} serves users "
                    f"{description}, which the engine does not implement."
                )

    return failures


def read_engine() -> Dict[Path, str]:
    sources: Dict[Path, str] = {}
    for check in CHECKS:
        for path, _ in check.engine_required:
            if path not in sources and path.is_file():
                sources[path] = path.read_text(encoding="utf-8")
    if DOMAIN_LITERATURE_TS.is_file():
        sources[DOMAIN_LITERATURE_TS] = DOMAIN_LITERATURE_TS.read_text(
            encoding="utf-8"
        )
    return sources


def selftest() -> int:
    """Prove each check can fail, by breaking it and confirming detection.

    A guard nobody has watched fail is a guard nobody knows works. Each
    mutation below is a plausible regression, not a nonsense edit.
    """
    doc = DOC.read_text(encoding="utf-8")
    engine = read_engine()

    baseline = audit(doc, engine)
    if baseline:
        print("SELFTEST FAIL: the tree is already failing, so mutations "
              "prove nothing. Fix these first:", file=sys.stderr)
        for f in baseline:
            print(f"  - {f}", file=sys.stderr)
        return 1

    mutations: List[Tuple[str, str, Dict[Path, str], str]] = [
        # (label, mutated doc, mutated engine, substring expected in failure)
        (
            "PCR equation reverted to the decay form",
            doc.replace("N(n) = N₀ × (1 + E)ⁿ", "N(n) = N₀ × E^n"),
            engine,
            "decay form",
        ),
        (
            "SIR doc reverted to density-dependent",
            # Both lines, not just dS/dt. A one-line replace left
            # `dI/dt = β·S·I/N - γ·I` intact and so exercised only the
            # first assertion -- the mutation has to be the regression
            # that would actually happen, or it measures less than it
            # appears to.
            doc.replace("dS/dt = -β·S·I/N", "dS/dt = -β·S·I")
               .replace("dI/dt = β·S·I/N - γ·I", "dI/dt = β·S·I - γ·I"),
            engine,
            # The exact needle, not the check name: "SIR" alone would also
            # be satisfied by the SEIR check's failure and prove less.
            "'dI/dt = β·S·I/N - γ·I'",
        ),
        (
            "tau-leaping re-asserted as the method",
            doc.replace(
                "- **Method**: the **exact SSA (Gillespie's Direct Method)**",
                "- **Method**: Tau-leaping algorithm",
            ),
            engine,
            "tau-leaping named as the implemented method",
        ),
        (
            "engine switched to frequency-independent transmission",
            doc,
            {
                **engine,
                MODEL_BUILDING_PY: engine[MODEL_BUILDING_PY].replace(
                    "J0: S -> I; beta * S * I / N;", "J0: S -> I; beta * S * I;"
                ),
            },
            "model_building.py",
        ),
        (
            "the PCR description SERVED TO USERS reverted to decay",
            doc,
            {
                **engine,
                DOMAIN_LITERATURE_TS: engine[DOMAIN_LITERATURE_TS].replace(
                    "N(n) = N0 × (1 + E)^n", "N(n) = N0 × E^n"
                ),
            },
            "serves users the decay form",
        ),
        (
            "the SIR description SERVED TO USERS reverted to "
            "density-dependent",
            doc,
            {
                **engine,
                DOMAIN_LITERATURE_TS: engine[DOMAIN_LITERATURE_TS].replace(
                    "dS/dt = -β·S·I/N", "dS/dt = -β·S·I"
                ),
            },
            "serves users the density-dependent form",
        ),
        (
            "engine PCR switched to a different recurrence",
            doc,
            {
                **engine,
                PCR_PY: engine[PCR_PY].replace(
                    "(1.0 + efficiency) ** cycle", "(2.0 * efficiency) ** cycle"
                ),
            },
            "pcr.py",
        ),
    ]

    ok = True

    # The blockquote exemption must be doing real work. Every forbidden
    # pattern above is quoted verbatim inside the correction note that
    # records it, so WITHOUT the exemption this document fails its own
    # guard -- and the only way to go green would be to delete the
    # evidence. Asserted rather than assumed: if a future edit rewords the
    # notes so they no longer quote the old formulae, this stops being a
    # real exemption and someone should find out here.
    total_forbidden = sum(len(c.doc_forbidden) for c in CHECKS)
    needs_exemption = [
        d
        for c in CHECKS
        for pattern, d in c.doc_forbidden
        if re.search(pattern, doc)
        and not re.search(pattern, strip_correction_blockquotes(doc))
    ]
    if not needs_exemption:
        # Every pattern would pass with the exemption removed, so the
        # exemption is dead code dressed as diligence -- and nobody would
        # learn that until a correction note quoted a formula and the guard
        # went red on its own evidence.
        print("  MISSED  blockquote exemption is dead code: no forbidden "
              "pattern is quoted in any correction note", file=sys.stderr)
        ok = False
    else:
        # Not all of them need it, and that is correct rather than a gap:
        # patterns anchored on the asserted markdown form (`- **Method**:`)
        # do not match the prose of a correction note quoting the same
        # words, so they are already safe without the exemption.
        print(f"  caught  blockquote exemption is load-bearing "
              f"({len(needs_exemption)} of {total_forbidden} forbidden "
              f"patterns are quoted in a correction note and would "
              f"otherwise fail on their own evidence)")

    for label, mutated_doc, mutated_engine, expected in mutations:
        if mutated_doc == doc and mutated_engine == engine:
            print(f"  NO-OP  {label}: the mutation changed nothing, so this "
                  f"proves nothing", file=sys.stderr)
            ok = False
            continue
        found = audit(mutated_doc, mutated_engine)
        caught = any(expected in f for f in found)
        print(f"  {'caught' if caught else 'MISSED'}  {label}")
        if not caught:
            print(f"           expected a failure mentioning {expected!r}; "
                  f"got: {found or 'nothing'}", file=sys.stderr)
            ok = False

    if ok:
        print(f"selftest OK: {len(mutations)} mutations, all caught")
        return 0
    print("SELFTEST FAILED", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="break each check and confirm it fails",
    )
    args = parser.parse_args()

    if not DOC.is_file():
        print(f"FAIL: {DOC} not found", file=sys.stderr)
        return 1

    if args.selftest:
        return selftest()

    failures = audit(DOC.read_text(encoding="utf-8"), read_engine())
    if failures:
        print("FAIL: documented equations do not match the engine\n",
              file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    checked = sum(
        len(c.doc_required) + sum(len(n) for _, n in c.engine_required)
        + len(c.doc_forbidden) + len(c.surface_required)
        + len(c.surface_forbidden)
        for c in CHECKS
    )
    surfaces = sum(
        len(c.surface_required) + len(c.surface_forbidden) for c in CHECKS
    )
    print(f"OK: {len(CHECKS)} models, {checked} assertions "
          f"({surfaces} against the description served to users), "
          f"documentation matches the engine")
    return 0


if __name__ == "__main__":
    sys.exit(main())
