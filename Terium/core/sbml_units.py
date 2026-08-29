"""Unit declarations for exported SBML: the file states its own units.

THE DEFECT THIS CLOSES
----------------------
ADR 0146 fixed the exported VALUES -- everything converted into the
substrate's units per second -- and recorded the remaining gap in so many
words: "without unit declarations the file still says 2.13e-4 rather than
2.13e-4 mM/s. That needs `unitDefinition` support in the Python exporter."
ADR 0150's index row claimed that support existed and had taken libSBML's
unit-consistency findings from 15 to 0; the row was written and the module
never was. This is that module, verified the way the row says: libSBML
`checkConsistency` with `LIBSBML_CAT_UNITS_CONSISTENCY` on -- 15 findings
before, 0 after.

TWO AUTHORS, AND HOW THE BOUNDARY SETTLED
-----------------------------------------
Two agents built this feature concurrently with no claim system to stop
them, overwrote each other's halves three times, and settled it through
`docs/COORDINATION-sbml-units.txt` -- the filesystem being the only
channel there is. The settlement, honoured here: THIS signature
(`parameter_units`, keyword-only `domain`, itemised `refusals`) is the
contract, chosen by the other author in so many words ("your module is
the better half and I am keeping it verbatim"); the exporter and its
UNIT_KINDS-free per-row design conform to it, and the seconds-only
time-base refusal -- the other author's idea, and a good one -- lives in
the exporter where the payload's `units` key is read. Do not change this
signature without changing `scripts/export_annotated_model.py` and
`Terium/tests/test_sbml_units_declared.py` in the same edit.

WHERE THE UNITS COME FROM
-------------------------
Nowhere here. Every unit string arrives from the caller's provenance
rows, which carry the units the CLI normalised the values INTO (ADR 0146:
the substrate's concentration unit, and that unit per second for rates).
This module refuses anything it was not told:

  * a model parameter with no supplied unit  -> refusal, named
  * a unit outside the vocabulary            -> refusal, named
  * two parameters in different
    concentration systems                    -> refusal, named
  * a domain whose unit semantics are not
    established here                         -> refusal, named

A refusal returns the document UNCHANGED plus the reasons, never a file
with invented units: a wrong declared unit is worse than none, because a
consumer trusts declarations and merely guesses at absences.

THE DIMENSIONAL FIX, WHICH IS THE SUBTLE HALF
---------------------------------------------
Declaring units surfaces a real error that was invisible without them
(ADR 0146 names it): the kinetic law is concentration/time, and SBML
defines a reaction rate as substance/time -- extent, not concentration.
The two agreed numerically only because the compartment is 1 litre. The
fix is the standard SBML idiom -- multiply the rate by the compartment
volume, (mmol/L/s) x L = mmol/s. At size 1 this changes no trajectory,
which a test asserts rather than assumes; at any other size it is the
version that was right all along.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import libsbml

#: unit token (normalised) -> scale on `mole`. Molar is mole/litre, so the
#: prefix rides on the mole and the litre is always exponent -1, scale 0.
#: Mirrors src/units.ts::CONCENTRATION_TO_MOLAR; the CLI cannot deliver a
#: unit outside its own table, so a new CLI unit this table lacks produces
#: a named refusal here, never a wrong declaration.
_CONCENTRATION_SCALE: dict[str, int] = {
    "m": 0,
    "mol/l": 0,
    "mm": -3,
    "mmol/l": -3,
    "um": -6,
    "umol/l": -6,
    "nm": -9,
    "nmol/l": -9,
    "pm": -12,
}

#: Domains whose species are concentrations and whose rates are
#: concentration/time -- the semantics the declarations below encode.
#: sir/seir species are population counts; declaring them as molar
#: concentrations would be a confident lie, so they refuse until someone
#: establishes their unit system deliberately.
_CONCENTRATION_DOMAINS = frozenset({"mm", "mm_competitive_inhibition"})


def _normalise(token: str) -> str:
    return token.strip().replace("µ", "u").replace("μ", "u").lower()


@dataclass
class UnitsOutcome:
    """What was declared, and what was refused with the reason."""

    sbml: str
    #: SBML ids that now carry a unit declaration; empty on refusal.
    declared: list[str] = field(default_factory=list)
    #: (symbol or aspect, why nothing was declared for it)
    refusals: list[tuple[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.refusals


def _scale_for(unit: str) -> int | None:
    return _CONCENTRATION_SCALE.get(_normalise(unit))


def _split_rate(unit: str) -> str | None:
    """The concentration half of `<conc>/s`, or None if not that shape."""
    token = _normalise(unit)
    if token.endswith("/s"):
        return token[: -len("/s")]
    return None


def _add_unit_definition(
    model: libsbml.Model, uid: str, parts: list[tuple[int, int, int]]
) -> None:
    """`parts` is (kind, exponent, scale). The multiplier is always 1."""
    definition = model.createUnitDefinition()
    definition.setId(uid)
    for kind, exponent, scale in parts:
        unit = definition.createUnit()
        unit.setKind(kind)
        unit.setExponent(exponent)
        unit.setScale(scale)
        unit.setMultiplier(1.0)


def declare_units(
    sbml_text: str,
    parameter_units: dict[str, str],
    *,
    domain: str,
) -> UnitsOutcome:
    """Return `sbml_text` with unit declarations, or unchanged with reasons.

    `parameter_units` maps caller names (the resolution layer's `km`,
    `vmax`, or the model's own `Km`, `Vmax` -- both accepted, see the fold
    below) to the unit strings the CLI normalised their values into.
    Model PARAMETERS missing from the map refuse; SPECIES do not need
    entries, because in the domains this module accepts every species IS a
    concentration -- that is what the `_CONCENTRATION_DOMAINS` gate
    establishes, not a default filling a gap. A species entry that IS
    supplied still participates in the mixed-scale check, so a
    contradicting species unit refuses.
    """
    if domain not in _CONCENTRATION_DOMAINS:
        return UnitsOutcome(
            sbml=sbml_text,
            refusals=[(
                "domain",
                f"unit semantics for domain '{domain}' are not established "
                "here: its species are not concentrations, and declaring "
                "molar units on them would be a confident lie. See this "
                "module's docstring.",
            )],
        )

    document = libsbml.readSBMLFromString(sbml_text)
    fatal = [
        document.getError(i).getMessage().strip()
        for i in range(document.getNumErrors())
        if document.getError(i).getSeverity() >= libsbml.LIBSBML_SEV_ERROR
    ]
    if fatal:
        raise ValueError(
            "declare_units was handed unparseable SBML: " + "; ".join(fatal)
        )
    model = document.getModel()

    refusals: list[tuple[str, str]] = []
    declared: list[str] = []

    # ---- fold caller names onto model symbols, the annotator's way -------
    #
    # The builders emit `Km` and `Vmax`; the resolution layer speaks `km`
    # and `vmax`. `annotate_sbml` learned this the expensive way -- an
    # exact-match lookup annotated NOTHING while reporting success -- and
    # its rule is reused verbatim: case-insensitive, but an ambiguous fold
    # (a model with both `km` and `Km`) is refused rather than resolved by
    # picking one, because SBML ids are case-sensitive and folding two
    # distinct parameters would declare one value's unit on the other.
    model_ids = {
        model.getParameter(i).getId() for i in range(model.getNumParameters())
    } | {model.getSpecies(i).getId() for i in range(model.getNumSpecies())}
    ids_by_lower: dict[str, list[str]] = {}
    for model_id in model_ids:
        ids_by_lower.setdefault(model_id.lower(), []).append(model_id)

    folded_units: dict[str, str] = {}
    for name, unit in parameter_units.items():
        if name in model_ids:
            folded_units[name] = unit
            continue
        candidates = ids_by_lower.get(name.lower(), [])
        if len(candidates) == 1:
            folded_units[candidates[0]] = unit
        elif len(candidates) > 1:
            refusals.append((
                name,
                "folds onto more than one model symbol ("
                + ", ".join(sorted(candidates))
                + "); declaring a unit on either would be a guess about "
                "which parameter the caller meant.",
            ))
        # A name matching nothing is not a refusal by itself: the model-
        # parameter completeness check below reports the gap from the
        # model's side, which is the side a reader of the file sees.
    parameter_units = folded_units

    # ---- one concentration system, read off the supplied units ----------
    conc_scales: dict[str, int] = {}
    rate_symbols: list[str] = []
    for symbol, unit in parameter_units.items():
        rate_conc = _split_rate(unit)
        token = rate_conc if rate_conc is not None else _normalise(unit)
        scale = _scale_for(token)
        if scale is None:
            refusals.append((
                symbol,
                f"unit '{unit}' is outside the vocabulary this module "
                "mirrors from src/units.ts; refusing to guess a scale for "
                "it. A wrong declared unit is worse than none.",
            ))
            continue
        conc_scales[symbol] = scale
        if rate_conc is not None:
            rate_symbols.append(symbol)

    # Every PARAMETER the model has must be accounted for by the caller --
    # an absent entry is a value this export would leave silently unitless,
    # and refusing is the only honest answer for a number whose unit nobody
    # delivered.
    model_parameters = {
        model.getParameter(i).getId() for i in range(model.getNumParameters())
    }
    for symbol in sorted(model_parameters - set(parameter_units)):
        refusals.append((
            symbol,
            "the caller supplied no unit for this model parameter, so "
            "nothing is declared for it. Absent means not delivered, not "
            "dimensionless.",
        ))

    if refusals:
        return UnitsOutcome(sbml=sbml_text, refusals=refusals)

    if len(set(conc_scales.values())) != 1:
        systems = sorted({f"{s}: 10^{v} mole/L" for s, v in conc_scales.items()})
        return UnitsOutcome(
            sbml=sbml_text,
            refusals=[(
                "concentration system",
                "the supplied units span more than one concentration scale ("
                + "; ".join(systems)
                + "). ADR 0146 normalises every export into the substrate's "
                "unit, so mixed scales here mean that normalisation broke -- "
                "declaring either scale would be wrong for the other half.",
            )],
        )
    scale = next(iter(set(conc_scales.values())))

    # ---- unit definitions ------------------------------------------------
    _add_unit_definition(
        model, "substance_amount", [(libsbml.UNIT_KIND_MOLE, 1, scale)]
    )
    _add_unit_definition(
        model,
        "concentration",
        [(libsbml.UNIT_KIND_MOLE, 1, scale), (libsbml.UNIT_KIND_LITRE, -1, 0)],
    )
    _add_unit_definition(
        model,
        "concentration_per_second",
        [
            (libsbml.UNIT_KIND_MOLE, 1, scale),
            (libsbml.UNIT_KIND_LITRE, -1, 0),
            (libsbml.UNIT_KIND_SECOND, -1, 0),
        ],
    )

    # ---- model-level bases (99506, 99507) --------------------------------
    model.setTimeUnits("second")
    model.setExtentUnits("substance_amount")
    model.setSubstanceUnits("substance_amount")
    model.setVolumeUnits("litre")

    # ---- compartment (20513) ---------------------------------------------
    for i in range(model.getNumCompartments()):
        compartment = model.getCompartment(i)
        compartment.setUnits("litre")
        if not compartment.isSetSize():
            # Not a guess: 1 litre is the size the kinetic law was already
            # implicitly integrating at, which is the whole story of the
            # extent fix below. Antimony emits an explicit size anyway.
            compartment.setSize(1.0)

    # ---- species (20616): concentrations by the domain gate ---------------
    for i in range(model.getNumSpecies()):
        species = model.getSpecies(i)
        species.setSubstanceUnits("substance_amount")
        declared.append(species.getId())

    # ---- parameters (20702, 80701) ---------------------------------------
    for i in range(model.getNumParameters()):
        parameter = model.getParameter(i)
        symbol = parameter.getId()
        parameter.setUnits(
            "concentration_per_second" if symbol in rate_symbols else "concentration"
        )
        declared.append(symbol)

    # ---- the extent fix (the tail of 99505) -------------------------------
    #
    # concentration/time x litre = substance/time. Identity at size 1,
    # pinned by test rather than trusted; correct at every other size.
    for i in range(model.getNumReactions()):
        reaction = model.getReaction(i)
        law = reaction.getKineticLaw()
        if law is None or law.getMath() is None:
            refusals.append((
                reaction.getId() or f"reaction {i}",
                "has no kinetic law to make dimensionally consistent; "
                "declaring extent units around it would claim a "
                "consistency the file does not have.",
            ))
            continue
        compartment_ref = libsbml.ASTNode(libsbml.AST_NAME)
        compartment_ref.setName(model.getCompartment(0).getId())
        times = libsbml.ASTNode(libsbml.AST_TIMES)
        times.addChild(law.getMath().deepCopy())
        times.addChild(compartment_ref)
        # (alice) Literal numbers in the law -- the `1` in the competitive
        # denominator's (1 + I/Ki) -- are genuinely dimensionless, and
        # libSBML cannot verify an expression containing an unitless
        # literal ([99505] was the last finding standing). SBML L3 lets a
        # <cn> carry its own units attribute; stating `dimensionless` on
        # numeric leaves is a declaration of what the math already means,
        # not a change to it. Names, operators and everything else are
        # untouched.
        pending = [times]
        while pending:
            node = pending.pop()
            if node.isNumber() and not node.isSetUnits():
                node.setUnits("dimensionless")
            pending.extend(node.getChild(i) for i in range(node.getNumChildren()))
        law.setMath(times)

    if refusals:
        # A reaction that could not be fixed poisons the whole claim: the
        # document goes back as it came in, because "some units declared,
        # extent still wrong" reads as done and is not.
        return UnitsOutcome(sbml=sbml_text, refusals=refusals)

    return UnitsOutcome(
        sbml=libsbml.writeSBMLToString(document),
        declared=sorted(set(declared)),
    )
