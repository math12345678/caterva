"""The enzyme mechanisms the motif library was missing -- and an honest
count of the ones it was not.

WHAT WAS ACTUALLY MISSING
-------------------------
This module was specified as ten mechanisms. Six of them were already in
`library.py`, with the right rate laws, the right parameter kinds and a
basis string apiece:

    uncompetitive_inhibition   mixed_inhibition   noncompetitive_inhibition
    product_inhibition         ordered_bi_bi      ping_pong_bi_bi

They are re-exported here, so that "the enzymology motifs" is one import,
and they are deliberately NOT redefined.

A second definition of a rate law is not a convenience. It is a second
answer to a question that already had one, and this repository has the
scars: four implementations of Michaelis-Menten, three of BRENDA lookup,
and no way for a reader to tell which one the product actually used. The
kcat labelled "mM" lived in the copy nobody was watching. Adding is
rewarded here and never being called is not punished, which is exactly how
a duplicate survives -- so `_refuse_duplicates` below fails at IMPORT time
if a name defined in this module collides with one in `library.py`, rather
than letting the two silently shadow each other in a merged dictionary.

What is genuinely new is three mechanisms and one alias:

    mwc_allostery         the Monod-Wyman-Changeux concerted two-state model
    substrate_channeling  an intermediate handed over rather than released
    futile_cycle          opposing modification that pays ATP for the privilege
    HILL_KINETICS         an alias for `library.COOPERATIVE_CATALYSIS`

WHY HILL IS AN ALIAS AND NOT A MOTIF
------------------------------------
`library.COOPERATIVE_CATALYSIS` is already the Hill rate law, symbol for
symbol. Shipping `hill_kinetics` beside it would put the same equation in
the registry twice under two names, which is the failure described above.
What that motif was missing was not algebra, it was a sentence: its basis
did not say that the Hill coefficient is a phenomenological fit rather than
a count of subunits. That sentence has been added to the motif itself, in
`library.py`, where the one copy lives. `HILL_KINETICS` here is a name
bound to that same object, for callers who look for the mechanism under the
name the literature uses.

WHY MWC AND HILL ARE A PAIR, AND WHY ONLY ONE OF THEM IS A MECHANISM
--------------------------------------------------------------------
They produce the same shape of curve and they are not the same claim.

The Hill equation is a fit. Its exponent `h` is whatever number makes the
sigmoid match, it is real-valued, it is routinely non-integer, and it is
bounded above by -- not equal to -- the number of binding sites.
Haemoglobin has four sites and a Hill coefficient near 2.8. Reporting `h`
as a subunit count is a specific, common, and load-bearing error: it turns
a curve-fitting parameter into a structural claim about the protein.

MWC is a mechanism. Its `n` IS the number of subunits, it is an integer,
and the caller states it from the structure rather than fitting it. The
sigmoid then falls out of the concerted R/T switch, and the apparent Hill
coefficient of an MWC curve is a DERIVED quantity -- a function of L, of
Kr/Kt and of n, always less than n, and different at every effector
concentration.

The kinds encode that difference and are not decoration. `n` is
KIND_EXPONENT, which is CHOSEN: no paper supplies the subunit count of the
protein in your model, you do. `L` is KIND_AFFINITY, which is RESOLVABLE,
with no BRENDA table -- it is a conformational equilibrium constant, so a
paper can supply it and a database lookup cannot, and `MotifParameter`
annotates it as such so a refusal can say "never searched" rather than
"searched and not found".

NO EFFICIENCY FACTORS
---------------------
`substrate_channeling` is the mechanism most often written with a fudge: a
dimensionless "channelling efficiency" multiplying an otherwise ordinary
two-step pathway. That parameter has no kind here that is not a lie. It is
not a rate constant and not an affinity, so it is not resolvable; it is not
a concentration and not an exponent, so the caller has no principled way to
choose it either. A quantity that fits no kind is a quantity nobody can
source, which is the same defect as a lumped Vmax wearing a different hat
(ADR 0013).

So the channel is written as a race instead: a first-order transfer to the
second active site against a first-order escape to bulk. Both are rate
constants a paper can report, and the channelled fraction

    k_transfer / (k_transfer + k_escape)

is DERIVED from them rather than declared. The same rule produced
`futile_cycle` with ATP as a species rather than folded into the kinase's
rate constant: a cycle whose energetic cost is invisible cannot be starved,
and being able to starve it is the only way to show that the cost is real.

EVERY DEFAULT HERE IS A PLACEHOLDER
-----------------------------------
Every numeric default below is illustrative and order-of-magnitude only.
None of them is a measurement, none is attributed to a paper, and the
pipeline treats every RESOLVABLE one as a quantity to go and find. A number
with a citation it does not deserve is worse than a number with none.
"""

from __future__ import annotations

from typing import Dict

try:
    from .motifs import (
        KIND_AFFINITY, KIND_EXPONENT, KIND_RATE_CONSTANT,
        Motif, MotifError, MotifParameter, Port, ReactionTemplate,
        ROLE_COMPLEX, ROLE_ENZYME, ROLE_PRODUCT, ROLE_SUBSTRATE,
    )
    from .library import (
        COOPERATIVE_CATALYSIS, LIBRARY, MIXED_INHIBITION,
        NONCOMPETITIVE_INHIBITION, ORDERED_BI_BI, PING_PONG_BI_BI,
        PRODUCT_INHIBITION, UNCOMPETITIVE_INHIBITION,
    )
except ImportError:  # pragma: no cover - flat import
    from motifs import (  # type: ignore[no-redef]
        KIND_AFFINITY, KIND_EXPONENT, KIND_RATE_CONSTANT,
        Motif, MotifError, MotifParameter, Port, ReactionTemplate,
        ROLE_COMPLEX, ROLE_ENZYME, ROLE_PRODUCT, ROLE_SUBSTRATE,
    )
    from library import (  # type: ignore[no-redef]
        COOPERATIVE_CATALYSIS, LIBRARY, MIXED_INHIBITION,
        NONCOMPETITIVE_INHIBITION, ORDERED_BI_BI, PING_PONG_BI_BI,
        PRODUCT_INHIBITION, UNCOMPETITIVE_INHIBITION,
    )


# ---------------------------------------------------------------------------
# Allostery
# ---------------------------------------------------------------------------

MWC_ALLOSTERY = Motif(
    name="mwc_allostery",
    summary=(
        "A concerted two-state allosteric enzyme: every subunit in the "
        "active R conformation or every subunit in the inactive T one."
    ),
    basis=(
        "Monod, Wyman and Changeux 1965. The oligomer switches as a unit "
        "between a high-affinity R state and a low-affinity T state; a "
        "partly-R, partly-T oligomer does not exist, which is what "
        "'concerted' means and what separates this from the sequential "
        "(Koshland-Nemethy-Filmer) scheme. Cooperativity is bought entirely "
        "by substrate pulling the R/T equilibrium, so the model CANNOT "
        "produce negative cooperativity: a measured Hill coefficient below "
        "one falsifies it outright, and that is the sharpest experimental "
        "discriminator there is between concerted and sequential schemes. "
        "The two further signatures are that the sigmoid disappears "
        "entirely -- to an exact rectangular hyperbola -- when a saturating "
        "activator drives L to zero, without the subunit count changing, "
        "and that with L equal in both directions of the effector the "
        "apparent Km is untouched while Vmax falls. It fails whenever the "
        "subunits are demonstrably non-identical, or when the ligand binds "
        "an oligomer caught mid-switch, both of which the concerted "
        "assumption denies can happen."
    ),
    ports=(
        Port("S", ROLE_SUBSTRATE, 1.0, description="substrate consumed"),
        Port("P", ROLE_PRODUCT, 0.0, description="product formed"),
        Port(
            "E", ROLE_ENZYME, 1e-3,
            description=(
                "catalyst, counted as ACTIVE SITES rather than as oligomers. "
                "Stated because the alternative convention needs a factor of "
                "n that nothing here could resolve: kcat is reported per "
                "site, so per-site enzyme is what multiplies it."
            ),
        ),
    ),
    parameters=(
        MotifParameter(
            "kcat", KIND_RATE_CONSTANT, 100.0, "1/s", table="kcat",
            description=(
                "turnover number of one active site in the R state; "
                "illustrative placeholder"
            ),
        ),
        MotifParameter(
            "Kr", KIND_AFFINITY, 0.1, "mM", table="km",
            description=(
                "substrate dissociation constant of the R (high-affinity) "
                "state; illustrative placeholder"
            ),
        ),
        MotifParameter(
            "Kt", KIND_AFFINITY, 5.0, "mM", table="km",
            description=(
                "substrate dissociation constant of the T (low-affinity) "
                "state. Kt > Kr is what makes the curve sigmoid at all; at "
                "Kt = Kr the model collapses to Michaelis-Menten with Vmax "
                "divided by (1 + L). Illustrative placeholder"
            ),
        ),
        MotifParameter(
            "L", KIND_AFFINITY, 1000.0, "dimensionless",
            description=(
                "allosteric constant, [T] / [R] with no substrate bound. A "
                "conformational equilibrium constant, so a paper can supply "
                "it. Illustrative placeholder"
            ),
        ),
        MotifParameter(
            "n", KIND_EXPONENT, 4.0, "dimensionless",
            description=(
                "number of subunits. A COUNT the caller states from the "
                "structure, not a fitted Hill coefficient -- see the module "
                "docstring; the apparent Hill coefficient of this curve is "
                "derived from L, Kr/Kt and n, and is always below n"
            ),
        ),
    ),
    reactions=(
        # The MWC velocity for a K-system in which only the R state turns
        # substrate over:
        #
        #     v = kcat * E * a * (1 + a)^(n-1)
        #                    / ((1 + a)^n + L * (1 + c*a)^n)
        #
        # with a = S/Kr and c = Kr/Kt. Written below as
        # a*(1+a)^n / ((1+a) * (...)), which is the same expression and
        # avoids raising anything to `n - 1`. That is not cosmetic: the
        # unit checker can carry a symbolic exponent only when it is a
        # BARE symbol, because `X^n` and `K^n` are commensurable exactly
        # when the same named n raises both. Given `^(n-1)` it reports that
        # it cannot decide, and a motif that ships with a standing unit
        # finding trains a reader to ignore unit findings.
        ReactionTemplate(
            "catalysis",
            reactants={"S": 1},
            products={"P": 1},
            rate_law=(
                "{kcat} * {E} * ({S} / {Kr}) * (1 + {S} / {Kr})^{n} / "
                "((1 + {S} / {Kr}) * "
                "((1 + {S} / {Kr})^{n} + {L} * (1 + {S} / {Kt})^{n}))"
            ),
            modifiers=("E",),
        ),
    ),
)


# ---------------------------------------------------------------------------
# Channelling
# ---------------------------------------------------------------------------

SUBSTRATE_CHANNELING = Motif(
    name="substrate_channeling",
    summary=(
        "Two consecutive active sites passing an intermediate between them "
        "without releasing it to the bulk."
    ),
    basis=(
        "Two active sites held close enough -- on one bifunctional chain or "
        "in one stable complex -- that the intermediate reaches the second "
        "before it can diffuse away; tryptophan synthase's intramolecular "
        "tunnel is the structurally proven case. The distinguishing "
        "experiment is isotope dilution: flood the bulk with unlabelled "
        "intermediate and the labelled flux to product is untouched if the "
        "intermediate is channelled, and diluted in proportion if it is "
        "not. A scavenging enzyme for the bulk intermediate is the same "
        "test run the other way, and a transient time before the second "
        "step reaches steady state that is far shorter than Km2 / (kcat2 * "
        "[E]) is the kinetic shadow of both. Written as a race between "
        "transfer and escape rather than as a channelling efficiency, "
        "because an efficiency is a dimensionless number of no kind: not a "
        "rate constant, not an affinity, so not resolvable, and not a "
        "concentration or an exponent, so not honestly choosable either. "
        "The channelled fraction k_transfer / (k_transfer + k_escape) is "
        "derived rather than declared. It fails when the bound intermediate "
        "stops being a small fraction of the complex -- the first step is "
        "in the quasi-steady-state form, which assumes exactly that, and a "
        "saturated second site breaks it."
    ),
    ports=(
        Port("S", ROLE_SUBSTRATE, 1.0, description="substrate of the first site"),
        Port(
            "EI", ROLE_COMPLEX, 0.0,
            description=(
                "intermediate still held between the two sites; never in "
                "solution, which is the entire claim of the motif"
            ),
        ),
        Port(
            "I", ROLE_PRODUCT, 0.0,
            description=(
                "intermediate that escaped to bulk. A scavenger or an "
                "isotope-dilution pool binds HERE, and nowhere else"
            ),
        ),
        Port("P", ROLE_PRODUCT, 0.0, description="final product"),
        Port(
            "C", ROLE_ENZYME, 1e-3,
            description="the bifunctional enzyme, or the E1-E2 complex",
        ),
    ),
    parameters=(
        MotifParameter(
            "kcat1", KIND_RATE_CONSTANT, 50.0, "1/s", table="kcat",
            description="turnover of the first active site; illustrative placeholder",
        ),
        MotifParameter(
            "Km1", KIND_AFFINITY, 0.1, "mM", table="km",
            description="first site's Michaelis constant; illustrative placeholder",
        ),
        MotifParameter(
            "k_transfer", KIND_RATE_CONSTANT, 200.0, "1/s",
            description=(
                "first-order hand-off of the bound intermediate to the "
                "second site and through turnover, without release; "
                "illustrative placeholder"
            ),
        ),
        MotifParameter(
            "k_escape", KIND_RATE_CONSTANT, 1.0, "1/s",
            description=(
                "first-order leak of the bound intermediate into bulk "
                "solution; illustrative placeholder"
            ),
        ),
        MotifParameter(
            "kcat2", KIND_RATE_CONSTANT, 50.0, "1/s", table="kcat", ligand="I",
            description=(
                "turnover of the second active site on intermediate "
                "recaptured from bulk; illustrative placeholder"
            ),
        ),
        MotifParameter(
            "Km2", KIND_AFFINITY, 0.1, "mM", table="km", ligand="I",
            description="second site's Michaelis constant; illustrative placeholder",
        ),
    ),
    reactions=(
        ReactionTemplate(
            "first_step",
            reactants={"S": 1},
            products={"EI": 1},
            rate_law="{kcat1} * {C} * {S} / ({Km1} + {S})",
            modifiers=("C",),
        ),
        ReactionTemplate(
            "channelled_transfer",
            reactants={"EI": 1},
            products={"P": 1},
            rate_law="{k_transfer} * {EI}",
        ),
        ReactionTemplate(
            "escape_to_bulk",
            reactants={"EI": 1},
            products={"I": 1},
            rate_law="{k_escape} * {EI}",
        ),
        ReactionTemplate(
            "recapture_from_bulk",
            reactants={"I": 1},
            products={"P": 1},
            rate_law="{kcat2} * {C} * {I} / ({Km2} + {I})",
            modifiers=("C",),
        ),
    ),
)


# ---------------------------------------------------------------------------
# Cycles that cost something
# ---------------------------------------------------------------------------

FUTILE_CYCLE = Motif(
    name="futile_cycle",
    summary=(
        "A kinase and a phosphatase opposing each other on one protein, "
        "with the kinase paying an ATP each pass."
    ),
    basis=(
        "The Goldbeter-Koshland cycle with its energetics written down. At "
        "steady state the protein pools do not move -- d[Xp]/dt is zero -- "
        "while ATP is hydrolysed at the cycling rate, and that separation "
        "is the whole point: the cycle buys sensitivity and response speed "
        "and pays for them in hydrolysis. The distinguishing measurement "
        "follows directly: an ATPase activity that persists once the "
        "modified and unmodified pools have stopped changing, so nothing is "
        "being made. A cycle drawn without the nucleotide shows none, which "
        "is why ATP is a species here rather than a factor absorbed into "
        "the kinase's rate constant -- a cost that cannot be starved cannot "
        "be shown to be real. It fails as written in a closed system: "
        "nothing regenerates ATP, so the cycle runs itself down and the "
        "steady state reported is exhaustion rather than balance. Compose "
        "`constant_inflow` onto the ATP port for a cell held at a fixed "
        "energy charge."
    ),
    ports=(
        Port("X", ROLE_SUBSTRATE, 1.0, description="unphosphorylated form"),
        Port("Xp", ROLE_PRODUCT, 0.0, description="phosphorylated form"),
        Port("kinase", ROLE_ENZYME, 1e-3),
        Port("phosphatase", ROLE_ENZYME, 1e-3),
        Port(
            "ATP", ROLE_SUBSTRATE, 3.0,
            description=(
                "nucleotide consumed once per pass. The default is an "
                "illustrative cellular-order amount and a scenario choice, "
                "not a measurement"
            ),
        ),
        Port("ADP", ROLE_PRODUCT, 0.0),
        Port(
            "Pi", ROLE_PRODUCT, 0.0,
            description=(
                "inorganic phosphate released by the phosphatase; tracked "
                "so the hydrolysis the cycle pays for is visible in the "
                "stoichiometry rather than only in the ATP that vanished"
            ),
        ),
    ),
    parameters=(
        MotifParameter(
            "kcat_kin", KIND_RATE_CONSTANT, 10.0, "1/s", table="kcat",
            description="kinase turnover number; illustrative placeholder",
        ),
        MotifParameter(
            "Km_kin", KIND_AFFINITY, 0.1, "mM", table="km",
            description=(
                "kinase affinity for the unphosphorylated protein; "
                "illustrative placeholder"
            ),
        ),
        MotifParameter(
            "Km_atp", KIND_AFFINITY, 0.1, "mM", table="km", ligand="ATP",
            description=(
                "kinase affinity for ATP. Separate from Km_kin because they "
                "are separate measurements on separate substrates, and one "
                "number standing for both would be unresolvable by "
                "construction. Illustrative placeholder"
            ),
        ),
        MotifParameter(
            "kcat_pptase", KIND_RATE_CONSTANT, 10.0, "1/s", table="kcat", ligand="Xp",
            description="phosphatase turnover number; illustrative placeholder",
        ),
        MotifParameter(
            "Km_pptase", KIND_AFFINITY, 0.1, "mM", table="km", ligand="Xp",
            description=(
                "phosphatase affinity for the phosphorylated form; "
                "illustrative placeholder"
            ),
        ),
    ),
    reactions=(
        ReactionTemplate(
            "phosphorylation",
            reactants={"X": 1, "ATP": 1},
            products={"Xp": 1, "ADP": 1},
            rate_law=(
                "{kcat_kin} * {kinase} * {X} / ({Km_kin} + {X}) "
                "* {ATP} / ({Km_atp} + {ATP})"
            ),
            modifiers=("kinase",),
        ),
        ReactionTemplate(
            "dephosphorylation",
            reactants={"Xp": 1},
            products={"X": 1, "Pi": 1},
            rate_law="{kcat_pptase} * {phosphatase} * {Xp} / ({Km_pptase} + {Xp})",
            modifiers=("phosphatase",),
        ),
    ),
)


# ---------------------------------------------------------------------------
# The alias, and the registry
# ---------------------------------------------------------------------------

#: The empirical sigmoid, under the name the literature uses for it.
#:
#: Bound to the SAME object as `library.COOPERATIVE_CATALYSIS`, not to a
#: copy: `HILL_KINETICS is COOPERATIVE_CATALYSIS` holds, and a test pins
#: that it does. See the module docstring for why a second definition would
#: be a defect rather than a convenience.
HILL_KINETICS = COOPERATIVE_CATALYSIS

#: Names callers reach for that are not the registry's own. Explicit,
#: because a lookup that silently guessed at near-misses would eventually
#: hand back the wrong mechanism for a typo.
ALIASES: Dict[str, str] = {"hill_kinetics": COOPERATIVE_CATALYSIS.name}

#: The motifs this module DEFINES. Deliberately three: see the module
#: docstring for the six it re-exports instead.
ENZYMOLOGY_LIBRARY: Dict[str, Motif] = {
    motif_.name: motif_
    for motif_ in (MWC_ALLOSTERY, SUBSTRATE_CHANNELING, FUTILE_CYCLE)
}


def _refuse_duplicates() -> None:
    """Fail at import if this module redefines something `library.py` has.

    A refusal rather than a merge policy. `{**LIBRARY, **ENZYMOLOGY}`
    resolves a collision by picking one, which is how two rate laws for one
    mechanism coexist for a year and the reader has no way to tell which
    one ran. There is no correct winner here, so there is no silent choice.
    """
    collisions = sorted(set(LIBRARY) & set(ENZYMOLOGY_LIBRARY))
    if collisions:
        raise MotifError(
            f"library_enzymology redefines {collisions}, which library.py "
            f"already defines. Two rate laws for one mechanism is two "
            f"answers to one question, and merging would pick one of them "
            f"without saying so. Re-export the existing motif, or change "
            f"the existing one in place -- do not add a second copy."
        )


_refuse_duplicates()

#: Every enzymology motif reachable by name: `library.py`'s and this
#: module's. Built once, after the duplicate check, so it cannot be the
#: thing that hides a collision.
FULL_LIBRARY: Dict[str, Motif] = {**LIBRARY, **ENZYMOLOGY_LIBRARY}


def enzymology_motif(name: str) -> Motif:
    """Look a motif up by name, following the alias table.

    Refuses with the available names rather than returning None, for the
    reason every refusal in this package is written out: a caller who
    mistyped `mwc_alostery` needs to see `mwc_allostery` in the message,
    and a caller who wanted a mechanism nobody has written needs to be told
    that rather than handed a plausible neighbour.
    """
    resolved = ALIASES.get(name, name)
    try:
        return FULL_LIBRARY[resolved]
    except KeyError:
        raise KeyError(
            f"no motif named {name!r}. Available: "
            f"{', '.join(sorted(FULL_LIBRARY))}"
            + (f". Aliases: {', '.join(sorted(ALIASES))}" if ALIASES else "")
        ) from None


__all__ = [
    # defined here
    "MWC_ALLOSTERY",
    "SUBSTRATE_CHANNELING",
    "FUTILE_CYCLE",
    # re-exported from library.py, not redefined
    "HILL_KINETICS",
    "MIXED_INHIBITION",
    "NONCOMPETITIVE_INHIBITION",
    "ORDERED_BI_BI",
    "PING_PONG_BI_BI",
    "PRODUCT_INHIBITION",
    "UNCOMPETITIVE_INHIBITION",
    # registry
    "ALIASES",
    "ENZYMOLOGY_LIBRARY",
    "FULL_LIBRARY",
    "enzymology_motif",
]
