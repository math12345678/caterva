"""Transport across a membrane, in an IR that has no membranes.

WHY ONE TRANSPORT MOTIF IS NOT ENOUGH
-------------------------------------
`library.facilitated_transport` is a Michaelis-Menten step whose product is
the same molecule under another name. It answers one question -- how fast
does the solute get in, before any of it has accumulated -- and it cannot
answer the question a transport experiment is usually asking, which is
where the solute STOPS. Its rate law does not mention the inside
concentration at all, so it carries a solute up an arbitrary gradient for
ever with nothing paying for the work. That is not a small approximation
error. It is the second law, and a reader watching the trajectory has no
way to see it happen.

The motifs here differ from each other in the way transport mechanisms
actually differ: in which free energy pays for the movement, and therefore
in where the movement stops.

    facilitated_diffusion     nothing pays; stops at Out = In
    passive_leak              nothing pays; stops at Out = In
    symport                   the driver's gradient pays; stops at
                              A_out*S_out = A_in*S_in
    antiport                  the driver's gradient pays; stops at
                              A_out*B_in = A_in*B_out
    primary_active_transport  ATP pays; stops when ATP runs out
    receptor_ligand_          vesicle traffic pays; the ligand does not
      internalisation         come back at all

Every one of those stopping points falls OUT of its rate law rather than
being imposed on it. That is the property worth having six motifs for: a
composed model that concentrates a solute tenfold must have been given
something to pay with, and if it was not, the rate law stalls on its own.

THE COMPARTMENT PROBLEM, AND WHAT IT COSTS
------------------------------------------
A `ReactionNetwork` has species, parameters and rate laws. It has no
compartments and no volumes. Every species is a concentration in one
declared unit (`Composition.concentration_unit`), and a reaction changes
each of its species by a stoichiometric coefficient times one rate.

Transport does not fit that. Moving one mole out of a compartment of volume
V_out into one of volume V_in changes the two concentrations by J/V_out and
J/V_in, and those are the same number only when the volumes are. A single
reaction `Out -> In` therefore conserves CONCENTRATION, and what physics
conserves is moles. For a cell in a dish -- the usual case, where the
outside is thousands of times the inside -- writing it as one reaction
overstates the depletion of the bath by that same factor.

Silently assuming the volumes equal was not acceptable, and inventing a
compartment system for one module was not either. So each translocation
here is written as a PAIR of half-reactions sharing one driving expression:

    the inside-facing half     rate  v
    the outside-facing half    rate  v / volume_ratio

with `v` written per unit INSIDE volume and

    volume_ratio = V_outside / V_inside

declared as a CHOSEN parameter on every motif that moves something across.
It is dimensionless, it is a fact about the scenario's geometry rather than
about any molecule, and no paper supplies it -- a cell in a dish and the
same cell in a droplet have different ones. Left at its default of 1.0 the
two halves are identical and the pair behaves exactly like the single
reaction it replaces, which is the only case the single reaction was ever
right for.

The cost is real and worth stating plainly. Split into two reactions, the
stoichiometry no longer says that the solute leaving the outside is the
solute arriving inside, so `ReactionNetwork` cannot DERIVE a conservation
law for it: the left null space of the pair is empty. The moles are still
conserved -- V_out*[Out] + V_in*[In] is exactly constant, and the tests
integrate the emitted network and check it -- but they are conserved
because the two rate laws agree, not because the stoichiometry says so, and
`simulate.check_invariants` therefore has nothing to check. A composition
that needs the structural law more than it needs unequal volumes should use
`library.FACILITATED_TRANSPORT`, which is the equal-volume single-reaction
form.

Because the two halves have to agree, they are not written twice by hand.
`_membrane_pair` builds both from one string, and a test asserts for every
motif here that the outside half is the inside half over `volume_ratio`.
Two hand-maintained copies of a driving expression are one edit away from a
model that creates or destroys molecules at a rate nothing reports.

WHY facilitated_diffusion IS NOT A SECOND COPY OF facilitated_transport
-----------------------------------------------------------------------
`library_enzymology` refuses at import time to redefine a mechanism
`library.py` already has, for reasons this module agrees with. This is not
that. `facilitated_transport` is the ZERO-TRANS INITIAL RATE limit -- the
rate law you get when the inside concentration is negligible, which is the
condition an uptake assay is run under and the condition its Kt is measured
under. `facilitated_diffusion` is the same carrier without that
restriction: it has the inside concentration in it, it runs backwards when
the gradient does, and it equilibrates. Different claims, different rate
laws, different ranges of validity. The existing motif's basis does not yet
say that it cannot equilibrate, and it should.

WRITTEN IN THE CONSTANTS SOMEBODY MEASURED
------------------------------------------
Solving an alternating-access carrier gives its flux in terms of
MICROSCOPIC constants: the rate at which the carrier reorients, and the
dissociation constant of the solute from one face of it. Neither is what a
transport paper reports. A paper reports the maximal net flux per carrier
and the solute concentration at half of it, both measured with nothing on
the far side, and in these schemes those operational numbers differ from
the microscopic ones by factors of two -- the carrier waits on both faces,
so half of it is in the wrong place at any moment.

Every law here is therefore written in the OPERATIONAL constants. `kcat` is
the measured maximal turnover and `Kt`/`Ka`/`Ks`/`Kb` are measured
half-saturations, and the factors of two have been absorbed into them
algebraically rather than left in the rate law. A law written in the
microscopic constants and then fed a measured kcat would be wrong by two
with nothing to show for it: dimensionally perfect, plotted smoothly, half
the flux the same measurement implies.

There is a second reason it had to be done that way, and it is a fact about
this IR that the next author will want to know. `units.py` reads a bare
numeric coefficient in a rate law as a SCALE, so `2 * kcat * ...` is
reported as a law whose scale is off by a factor of two -- the same finding
it would raise for a model that mixed mM with 2 mM. Numeric coefficients
other than 1 are effectively not writable here. The constraint and the
resolvability argument happen to point the same way.

EVERY DEFAULT HERE IS A PLACEHOLDER
-----------------------------------
Every numeric default below is illustrative and order-of-magnitude only.
None is a measurement, none carries a citation, and the pipeline treats
every RESOLVABLE one as a quantity to go and find. A number wearing a
citation it has not earned is worse than a number wearing none.

WHAT IS DELIBERATELY NOT HERE
-----------------------------
The two electrical motifs -- an ohmic channel and a voltage-gated one --
are named in `WITHHELD` with the reason, and `transport_motif()` raises
that reason rather than a KeyError when they are asked for. The short
version is that `units.py` has two base dimensions, concentration and time;
it cannot parse mV, nS, pA or a litre, and `parse_unit("mV")` RAISES rather
than returning a unit -- so a motif declaring one would not produce a unit
FINDING, it would make `unit_findings()` itself raise, and nothing in the
composition could be checked at all. The long version, including what
shipping one anyway would cost and what would have to change first, is in
`WITHHELD`.
"""

from __future__ import annotations

import re
from typing import Dict, Mapping, Optional, Sequence, Tuple

try:
    from .motifs import (
        KIND_AFFINITY, KIND_EXPONENT, KIND_RATE_CONSTANT,
        Motif, MotifError, MotifParameter, Port, ReactionTemplate,
        ROLE_COMPLEX, ROLE_ENZYME, ROLE_PARTNER, ROLE_PRODUCT,
        ROLE_SUBSTRATE,
    )
    from .library import FACILITATED_TRANSPORT, LIBRARY
except ImportError:  # pragma: no cover - flat import
    from motifs import (  # type: ignore[no-redef]
        KIND_AFFINITY, KIND_EXPONENT, KIND_RATE_CONSTANT,
        Motif, MotifError, MotifParameter, Port, ReactionTemplate,
        ROLE_COMPLEX, ROLE_ENZYME, ROLE_PARTNER, ROLE_PRODUCT,
        ROLE_SUBSTRATE,
    )
    from library import FACILITATED_TRANSPORT, LIBRARY  # type: ignore[no-redef]


class TransportMotifWithheld(NotImplementedError):
    """A transport mechanism this IR cannot express without lying.

    Raised by name, from `transport_motif`, carrying what the mechanism
    needs and what would have to change to get it. Deliberately distinct
    from the `KeyError` for a mechanism nobody has written: "this cannot be
    done here and here is why" and "there is no such thing" are different
    sentences, and a caller who typed `ion_channel_ohmic` deserves the
    first one rather than being sent to hunt for a spelling.
    """


# ---------------------------------------------------------------------------
# The compartment convention
# ---------------------------------------------------------------------------

#: The volume ratio, shared by every motif that moves something across.
#:
#: ONE object, referenced by each motif, so the declaration cannot drift
#: between them -- a `volume_ratio` meaning V_in/V_out in one motif and
#: V_out/V_in in the next would invert a flux with nothing to show for it.
#:
#: KIND_EXPONENT deserves a word, because this is not an exponent. The kind
#: vocabulary has exactly two CHOSEN kinds and a volume ratio is neither a
#: concentration nor a Hill coefficient. KIND_CONCENTRATION would be worse
#: than inexact: it would put a dimensionless geometric ratio in the same
#: bucket as species amounts, and `chosen_quantities` would present it as
#: an amount somebody has to measure out. KIND_EXPONENT is the
#: CHOSEN-and-dimensionless bucket, which is what this is. The real fix is
#: a KIND_GEOMETRY in `motifs.py`; that is a change to the shared
#: vocabulary and belongs in a change of its own rather than smuggled in
#: behind a transport module.
VOLUME_RATIO = MotifParameter(
    "volume_ratio",
    KIND_EXPONENT,
    1.0,
    "dimensionless",
    description=(
        "V_outside / V_inside: the volume the outside species are measured "
        "in, over the volume the inside species are measured in. A property "
        "of the scenario's geometry and not of any molecule, so no "
        "literature supplies it and the caller must. At the default of 1.0 "
        "the two compartments are treated as equal, which is the only case "
        "in which one unit of concentration leaving the outside is one unit "
        "arriving inside. For a cell in a dish it is in the thousands"
    ),
)

#: How the outside-facing half of a translocation is written, given the
#: inside-facing one. Parenthesised because the driving expressions are
#: differences, and `a - b / r` is not `(a - b) / r` -- the wrong one of
#: those integrates perfectly well and reports nothing.
_OUTSIDE_TEMPLATE = "({law}) / {{volume_ratio}}"

_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _membrane_pair(
    *,
    ports: Sequence[str],
    law: str,
    inside_name: str,
    outside_name: str,
    inside_reactants: Optional[Mapping[str, int]] = None,
    inside_products: Optional[Mapping[str, int]] = None,
    outside_reactants: Optional[Mapping[str, int]] = None,
    outside_products: Optional[Mapping[str, int]] = None,
) -> Tuple[ReactionTemplate, ReactionTemplate]:
    """The two half-reactions of one translocation, from one rate law.

    `law` is the flux per unit INSIDE volume. The outside-facing half gets
    the same expression over `volume_ratio`, because the same molar flux
    spread through a different volume is a different concentration change.

    Built rather than written twice on purpose: the two halves must agree
    exactly or the pair creates and destroys molecules, and a divergence
    between two long hand-copied expressions is invisible in review and
    invisible on a plot.

    Modifiers are derived here too. A species that appears in the driving
    expression but not in this half's stoichiometry -- the outside
    concentration, in the half that only touches the inside -- is a
    modifier of that half, and deriving it removes the chance of declaring
    one list for one half and a different list for the other.
    """
    named = set(_PLACEHOLDER.findall(law))

    def half(
        name: str,
        reactants: Optional[Mapping[str, int]],
        products: Optional[Mapping[str, int]],
        rate_law: str,
    ) -> ReactionTemplate:
        stoichiometry = set(reactants or {}) | set(products or {})
        return ReactionTemplate(
            name,
            dict(reactants or {}),
            dict(products or {}),
            rate_law,
            modifiers=tuple(
                port for port in ports
                if port in named and port not in stoichiometry
            ),
        )

    return (
        half(inside_name, inside_reactants, inside_products, law),
        half(
            outside_name,
            outside_reactants,
            outside_products,
            _OUTSIDE_TEMPLATE.format(law=law),
        ),
    )


# ---------------------------------------------------------------------------
# Passive movement: nothing pays
# ---------------------------------------------------------------------------

PASSIVE_LEAK = Motif(
    name="passive_leak",
    summary="A solute equilibrating across a membrane, first order and unsaturably.",
    basis=(
        "Fick's law across a thin membrane the solute partitions into: the "
        "flux is proportional to the concentration DIFFERENCE, with no "
        "carrier and therefore no saturation and no ceiling. Right for a "
        "small uncharged molecule crossing the lipid itself -- water, "
        "oxygen, a weak-acid drug in its neutral form. It fails for "
        "anything that crosses through a protein, which saturates (use "
        "`facilitated_diffusion`), and for anything charged, whose flux "
        "depends on a membrane potential this IR cannot carry (see "
        "WITHHELD). Because nothing pays for the movement it stops exactly "
        "at equal concentrations, whatever the volumes are, and it can "
        "never concentrate the solute anywhere. Written as two "
        "half-reactions with an explicit volume_ratio, which is 1.0 -- "
        "equal volumes -- unless the caller sets it; the module docstring "
        "says what that buys and what it costs."
    ),
    ports=(
        Port("Out", ROLE_SUBSTRATE, 1.0, description="solute outside"),
        Port("In", ROLE_PRODUCT, 0.0, description="solute inside"),
    ),
    parameters=(
        MotifParameter(
            "k_leak", KIND_RATE_CONSTANT, 0.01, "1/s",
            description=(
                "first-order rate constant for equilibration, referred to "
                "the inside volume. Measurable directly, as the rate "
                "constant of a washout or uptake time course. It is NOT a "
                "permeability: P is reported in cm/s and this is P*(A/V), "
                "so a permeability from a paper cannot be used here without "
                "the caller's own surface-to-volume ratio -- and that "
                "product cannot be written out and dimensionally checked "
                "here either, because units.py carries no length. "
                "Illustrative default"
            ),
        ),
        VOLUME_RATIO,
    ),
    reactions=_membrane_pair(
        ports=("Out", "In"),
        law="{k_leak} * ({Out} - {In})",
        inside_name="leak_in",
        inside_products={"In": 1},
        outside_name="leak_out",
        outside_reactants={"Out": 1},
    ),
)

FACILITATED_DIFFUSION = Motif(
    name="facilitated_diffusion",
    summary="A symmetric carrier moving a solute either way, saturably, for free.",
    basis=(
        "The simple-carrier scheme solved at steady state: one binding "
        "site, alternating access between an outward-facing and an "
        "inward-facing state, the SAME affinity at both faces, the loaded "
        "reorientation rate limiting, and an empty carrier that returns "
        "fast enough not to pile up on either face. Both concentrations "
        "appear in the denominator, which is the model's own "
        "trans-inhibition: raising the inside concentration slows the flux "
        "by more than the loss of driving force alone, because it holds "
        "carrier on the inside face. That is the observable difference "
        "between a carrier and a pore. Symmetric, so it stalls exactly at "
        "Out = In and can never concentrate the solute -- nothing is "
        "paying. It fails for an ASYMMETRIC carrier -- GLUT1's two faces "
        "do not have the same affinity -- which moves the whole rate curve "
        "while leaving the stalling point exactly where it was, and "
        "it fails when the empty carrier's return is itself rate limiting, "
        "which adds an Out*In term to the denominator and makes the "
        "trans-inhibition stronger than this law says. Two half-reactions "
        "and an explicit volume_ratio; see the module docstring."
    ),
    ports=(
        Port("Out", ROLE_SUBSTRATE, 1.0, description="solute outside"),
        Port("In", ROLE_PRODUCT, 0.0, description="solute inside"),
        Port("T", ROLE_ENZYME, 1e-3,
             description=(
                 "the carrier, in concentration referred to the INSIDE "
                 "volume; neither consumed nor produced"
             )),
    ),
    parameters=(
        MotifParameter(
            "kcat", KIND_RATE_CONSTANT, 100.0, "1/s", table="kcat",
            description=(
                "maximal NET turnover per carrier, with saturating solute "
                "on one side and none on the other -- the number an uptake "
                "assay reports. Operational, not microscopic; see the "
                "module docstring. Illustrative default"
            ),
        ),
        MotifParameter(
            "Kt", KIND_AFFINITY, 1.0, "mM", table="km",
            description=(
                "solute concentration at half the maximal flux under "
                "zero-trans conditions, taken to be the same at both faces. "
                "Illustrative default"
            ),
        ),
        VOLUME_RATIO,
    ),
    reactions=_membrane_pair(
        ports=("Out", "In", "T"),
        law="{kcat} * {T} * ({Out} - {In}) / ({Kt} + {Out} + {In})",
        inside_name="uptake",
        inside_products={"In": 1},
        outside_name="removal_from_the_outside",
        outside_reactants={"Out": 1},
    ),
)


# ---------------------------------------------------------------------------
# Secondary active transport: another solute's gradient pays
# ---------------------------------------------------------------------------

SYMPORT = Motif(
    name="symport",
    summary="A carrier moving two solutes the same way, one of them downhill.",
    basis=(
        "An alternating-access carrier in which only the FULLY loaded form "
        "reorients, the two sites bind independently and with the same "
        "affinities at both faces, and the empty carrier returns fast. "
        "Solving that gives a flux proportional to "
        "A_out*S_out - A_in*S_in, so the carrier stalls when the PRODUCTS "
        "of the coupled concentrations match rather than when either "
        "concentration does. That is the whole point: a tenfold driver "
        "gradient holds a tenfold cargo gradient uphill, and the model does "
        "it without being told to. The singly-loaded states are in the "
        "denominator but cannot cross, which is what couples the two "
        "solutes; a carrier that could carry the driver alone would be a "
        "uniporter with extra steps and would not stall there. The "
        "equal-affinity assumption is what makes the stalling point "
        "thermodynamically right for 1:1 coupling -- unequal affinities "
        "would let the carrier run in a circle and produce free energy. Two "
        "failures to name. First, this is the ELECTRONEUTRAL case: a "
        "Na+-coupled symporter moves charge, the membrane potential does "
        "work on it, and that term is absent because this IR cannot carry a "
        "volt (see WITHHELD), so the stalling point is right only at zero "
        "membrane potential and a real cell at -60 mV drives the cargo "
        "further uphill than this says. Second, the 1:1 stoichiometry is "
        "written into the reactions: a 2:1 symporter such as SGLT1 stalls "
        "at A_out^2*S_out = A_in^2*S_in and is a different motif, not a "
        "different parameter."
    ),
    ports=(
        Port("A_out", ROLE_SUBSTRATE, 100.0,
             description="driver ion outside, the one running downhill"),
        Port("A_in", ROLE_PRODUCT, 10.0, description="driver ion inside"),
        Port("S_out", ROLE_SUBSTRATE, 0.1,
             description="cargo outside, the one that may run uphill"),
        Port("S_in", ROLE_PRODUCT, 0.1, description="cargo inside"),
        Port("T", ROLE_ENZYME, 1e-3,
             description=(
                 "the carrier, referred to the INSIDE volume; neither "
                 "consumed nor produced"
             )),
    ),
    parameters=(
        MotifParameter(
            "kcat", KIND_RATE_CONSTANT, 50.0, "1/s", table="kcat",
            description=(
                "maximal net turnover per carrier, with both solutes "
                "saturating on one side and neither on the other. "
                "Operational, not microscopic; see the module docstring. "
                "Illustrative default"
            ),
        ),
        MotifParameter(
            "Ka", KIND_AFFINITY, 10.0, "mM", table="km",
            description=(
                "driver concentration at half the maximal flux, measured "
                "with cargo saturating and nothing on the far side. Taken "
                "to be the same at both faces. Illustrative default"
            ),
        ),
        MotifParameter(
            "Ks", KIND_AFFINITY, 0.1, "mM", table="km",
            description=(
                "cargo concentration at half the maximal flux, measured "
                "with driver saturating and nothing on the far side. Taken "
                "to be the same at both faces. Illustrative default"
            ),
        ),
        VOLUME_RATIO,
    ),
    reactions=_membrane_pair(
        ports=("A_out", "A_in", "S_out", "S_in", "T"),
        # The denominator is the carrier spread over the empty, singly
        # loaded and fully loaded states of both faces. It is never below
        # 2, so this law has no state at which it divides by zero --
        # unlike `antiport`, which does, and says so.
        law=(
            "{kcat} * {T} * "
            "({A_out} * {S_out} - {A_in} * {S_in}) / ({Ka} * {Ks}) / "
            "((1 + {A_out} / {Ka}) * (1 + {S_out} / {Ks}) + "
            "(1 + {A_in} / {Ka}) * (1 + {S_in} / {Ks}))"
        ),
        inside_name="release_at_the_inner_face",
        inside_products={"A_in": 1, "S_in": 1},
        outside_name="loading_at_the_outer_face",
        outside_reactants={"A_out": 1, "S_out": 1},
    ),
)

ANTIPORT = Motif(
    name="antiport",
    summary="A carrier exchanging two solutes in opposite directions, one for one.",
    basis=(
        "An obligatory exchanger: alternating access in which only a LOADED "
        "carrier reorients, so nothing can leave a face unless something "
        "else arrives at it. Solving that gives a flux proportional to "
        "A_out*B_in - A_in*B_out, so it stalls when the two gradients match "
        "ratio for ratio -- the Na+/Ca2+ exchanger reversing during "
        "depolarisation is that stalling point being crossed. Same "
        "equal-affinity assumption as `symport` and for the same "
        "thermodynamic reason, and the same two limits: it is the "
        "electroneutral 1:1 case, so it omits the potential's work on a "
        "charged exchange, and the real Na+/Ca2+ exchanger is 3:1 and "
        "electrogenic and is therefore a different motif rather than a "
        "different parameter. One thing to know about this law "
        "specifically: with all four concentrations at zero its denominator "
        "is zero as well as its numerator, because a carrier with nothing "
        "bound cannot reorient and the model has no turnover to report. "
        "Give at least one face something to carry."
    ),
    ports=(
        Port("A_out", ROLE_SUBSTRATE, 100.0,
             description="the inward-moving solute, outside"),
        Port("A_in", ROLE_PRODUCT, 10.0,
             description="the inward-moving solute, inside"),
        Port("B_in", ROLE_SUBSTRATE, 1.0,
             description="the outward-moving solute, inside"),
        Port("B_out", ROLE_PRODUCT, 0.1,
             description="the outward-moving solute, outside"),
        Port("T", ROLE_ENZYME, 1e-3,
             description=(
                 "the exchanger, referred to the INSIDE volume; neither "
                 "consumed nor produced"
             )),
    ),
    parameters=(
        MotifParameter(
            "kcat", KIND_RATE_CONSTANT, 50.0, "1/s", table="kcat",
            description=(
                "maximal net exchange turnover per carrier, with each "
                "solute saturating on the side it enters from. "
                "Operational, not microscopic; see the module docstring. "
                "Illustrative default"
            ),
        ),
        MotifParameter(
            "Ka", KIND_AFFINITY, 10.0, "mM", table="km",
            description=(
                "concentration of the inward-moving solute at half the "
                "maximal exchange, with the other solute saturating. Taken "
                "to be the same at both faces. Illustrative default"
            ),
        ),
        MotifParameter(
            "Kb", KIND_AFFINITY, 1.0, "mM", table="km",
            description=(
                "concentration of the outward-moving solute at half the "
                "maximal exchange, with the other solute saturating. Taken "
                "to be the same at both faces. Illustrative default"
            ),
        ),
        VOLUME_RATIO,
    ),
    reactions=_membrane_pair(
        ports=("A_out", "A_in", "B_in", "B_out", "T"),
        # Occupancy of the outer face plus occupancy of the inner face plus
        # their product. No constant term: an exchanger holding nothing
        # does nothing, which is also why this denominator can be zero.
        law=(
            "{kcat} * {T} * "
            "({A_out} * {B_in} - {A_in} * {B_out}) / ({Ka} * {Kb}) / "
            "(({A_out} / {Ka} + {B_out} / {Kb}) + "
            "({A_in} / {Ka} + {B_in} / {Kb}) + "
            "({A_out} / {Ka} + {B_out} / {Kb}) * "
            "({A_in} / {Ka} + {B_in} / {Kb}))"
        ),
        inside_name="exchange_at_the_inner_face",
        inside_reactants={"B_in": 1},
        inside_products={"A_in": 1},
        outside_name="exchange_at_the_outer_face",
        outside_reactants={"A_out": 1},
        outside_products={"B_out": 1},
    ),
)


# ---------------------------------------------------------------------------
# Primary active transport: ATP pays
# ---------------------------------------------------------------------------

PRIMARY_ACTIVE_TRANSPORT = Motif(
    name="primary_active_transport",
    summary="A pump spending ATP to move a solute out against its gradient.",
    basis=(
        "A P-type pump written as an enzyme with two substrates -- the "
        "solute on the cis face and ATP -- saturating independently, which "
        "is the rapid-equilibrium random form and is what a pump's reported "
        "Km for solute and Km for ATP are measured against. ATP is a "
        "SPECIES and not a rate constant, deliberately: a pump whose "
        "energetic cost is folded into its kcat cannot be starved, and "
        "starving it is the only way to show in a trajectory that the cost "
        "is real. Where it fails is the direction it cannot go. The law is "
        "irreversible, so it has no back-pressure term: it keeps pumping at "
        "the same rate against a gradient of any steepness and stops only "
        "when the cis solute or the ATP runs out. Real pumps stall at a "
        "gradient set by the free energy available, and can be driven "
        "backwards to make ATP. Writing that honestly needs the free energy "
        "of hydrolysis and of the gradient -- kJ/mol, and a charge for an "
        "electrogenic pump -- and this IR carries neither (see WITHHELD), "
        "so the limitation is stated here rather than papered over with a "
        "factor. Phosphate is not tracked: the pump makes ADP and the model "
        "does not follow the Pi, which matters only to a composition that "
        "wanted a phosphate pool. Two half-reactions and an explicit "
        "volume_ratio; see the module docstring."
    ),
    ports=(
        Port("In", ROLE_SUBSTRATE, 1.0,
             description="solute inside, the side it is pumped FROM"),
        Port("Out", ROLE_PRODUCT, 1.0,
             description="solute outside, the side it is pumped TO"),
        Port("Pump", ROLE_ENZYME, 1e-3,
             description=(
                 "the pump, referred to the INSIDE volume; neither consumed "
                 "nor produced"
             )),
        Port("ATP", ROLE_SUBSTRATE, 3.0,
             description="cytosolic ATP; one consumed per solute moved"),
        Port("ADP", ROLE_PRODUCT, 0.1, description="cytosolic ADP"),
    ),
    parameters=(
        MotifParameter(
            "kcat", KIND_RATE_CONSTANT, 100.0, "1/s", table="kcat",
            description=(
                "turnover number of the pump at saturating solute and "
                "saturating ATP. Illustrative default"
            ),
        ),
        MotifParameter(
            "Km_s", KIND_AFFINITY, 0.1, "mM", table="km",
            description=(
                "solute concentration at half maximal pumping, on the cis "
                "face. Illustrative default"
            ),
        ),
        MotifParameter(
            "Km_atp", KIND_AFFINITY, 0.5, "mM", table="km",
            description=(
                "ATP concentration at half maximal pumping. Illustrative "
                "default"
            ),
        ),
        VOLUME_RATIO,
    ),
    reactions=_membrane_pair(
        ports=("In", "Out", "Pump", "ATP", "ADP"),
        law=(
            "{kcat} * {Pump} * {In} / ({Km_s} + {In}) * "
            "{ATP} / ({Km_atp} + {ATP})"
        ),
        inside_name="hydrolysis_and_extrusion",
        inside_reactants={"In": 1, "ATP": 1},
        inside_products={"ADP": 1},
        outside_name="arrival_outside",
        outside_products={"Out": 1},
    ),
)


# ---------------------------------------------------------------------------
# Traffic rather than transport
# ---------------------------------------------------------------------------

RECEPTOR_LIGAND_INTERNALIZATION = Motif(
    name="receptor_ligand_internalisation",
    summary="A ligand bound, taken inside, and then degraded or sorted back out.",
    basis=(
        "The receptor-trafficking scheme: reversible binding at the "
        "surface, first-order internalisation of the OCCUPIED receptor, and "
        "a first-order race in the endosome between recycling the receptor "
        "to the surface and delivering it to the lysosome. The recycled "
        "fraction is k_rec/(k_rec + k_deg) and is DERIVED from two rate "
        "constants a paper can report, rather than declared as a sorting "
        "efficiency nobody could source. The ligand does not come back in "
        "either branch, which is the choice to argue with: a "
        "transferrin-like receptor releases its ligand and returns it, and "
        "that is a different motif rather than a different parameter. "
        "Constitutive internalisation of the EMPTY receptor is absent too, "
        "so the model understates receptor turnover in an unstimulated "
        "cell. On volumes: every species here is counted per unit of ONE "
        "reference volume, the medium the ligand is dissolved in, which is "
        "the convention receptor-trafficking models are written in "
        "(receptors per cell times cells per volume). That is why this "
        "motif has no volume_ratio -- nothing here crosses between two "
        "volumes. The cost is that the internalised complex is a "
        "concentration referred to the MEDIUM and not a cytosolic "
        "concentration, so wiring it to a cytosolic species from another "
        "motif is wrong unless the two volumes are equal."
    ),
    ports=(
        Port("L", ROLE_PARTNER, 0.01, description="free ligand in the medium"),
        Port("R", ROLE_PARTNER, 1e-3, description="free surface receptor"),
        Port("LR", ROLE_COMPLEX, 0.0, description="occupied surface receptor"),
        Port("LRi", ROLE_COMPLEX, 0.0,
             description="internalised complex, in the endosome"),
    ),
    parameters=(
        MotifParameter(
            "kon", KIND_RATE_CONSTANT, 10.0, "1/(mM*s)",
            description="association rate constant. Illustrative default",
        ),
        MotifParameter(
            "koff", KIND_RATE_CONSTANT, 0.01, "1/s",
            description="dissociation rate constant. Illustrative default",
        ),
        MotifParameter(
            "k_int", KIND_RATE_CONSTANT, 5e-3, "1/s",
            description=(
                "internalisation rate constant of the occupied receptor. "
                "Illustrative default"
            ),
        ),
        MotifParameter(
            "k_rec", KIND_RATE_CONSTANT, 2e-3, "1/s",
            description=(
                "rate constant for sorting the receptor back to the "
                "surface. Illustrative default"
            ),
        ),
        MotifParameter(
            "k_deg", KIND_RATE_CONSTANT, 1e-3, "1/s",
            description=(
                "rate constant for delivery to the lysosome, which destroys "
                "receptor and ligand together. Illustrative default"
            ),
        ),
    ),
    reactions=(
        ReactionTemplate(
            "binding", {"L": 1, "R": 1}, {"LR": 1}, "{kon} * {L} * {R}",
        ),
        ReactionTemplate(
            "unbinding", {"LR": 1}, {"L": 1, "R": 1}, "{koff} * {LR}",
        ),
        ReactionTemplate(
            "internalisation", {"LR": 1}, {"LRi": 1}, "{k_int} * {LR}",
        ),
        # Receptor only. The ligand is not a product of either fate, which
        # is the modelling choice the basis names and argues for.
        ReactionTemplate(
            "recycling", {"LRi": 1}, {"R": 1}, "{k_rec} * {LRi}",
        ),
        ReactionTemplate(
            "lysosomal_degradation", {"LRi": 1}, {}, "{k_deg} * {LRi}",
        ),
    ),
)


# ---------------------------------------------------------------------------
# What is not here, and why
# ---------------------------------------------------------------------------

#: Mechanisms this module was asked for and did not ship, with the reason.
#:
#: Data rather than a comment, because `transport_motif` reads it: asking
#: for one of these by name gets the reason, not a KeyError that reads like
#: a typo. A motif that passed the unit checker by hiding a volt inside a
#: lumped constant would be worse than no motif at all, because nothing
#: downstream could tell that it had.
WITHHELD: Dict[str, str] = {
    "ion_channel_ohmic": (
        "An ohmic channel current is g*(V - E_rev): a conductance in "
        "siemens times a potential in volts, which is an ampere. Turning "
        "that into the only thing a reaction network can carry -- an amount "
        "per volume per time -- takes I/(z*F*V_compartment), so it needs a "
        "charge number, the Faraday constant in coulombs per mole, and a "
        "compartment volume in litres.\n\n"
        "Terium/compose/units.py has exactly two base dimensions, "
        "concentration and time (its BASES). It cannot parse mV, nS, pA or "
        "L, and parse_unit('mV') RAISES rather than returning a unit -- so "
        "a motif declaring one would not produce a unit finding, it would "
        "make Composition.unit_findings() itself raise, and the whole "
        "composition would become uncheckable rather than be reported as "
        "wrong.\n\n"
        "The version that would fit is the same law with the volts hidden: "
        "one parameter with the dimensions of an amount per volume per "
        "time, multiplying a dimensionless driving force. That parameter is "
        "g/(z*F*V) with the potentials folded into it -- the conductance "
        "belongs to the channel and the volume belongs to the scenario, and "
        "no paper reports their product. It is a lumped quantity of exactly "
        "the kind ADR 0013 blocks, and it would PASS the unit checker, "
        "which is the worst combination available: dimensionally clean and "
        "permanently unresolvable.\n\n"
        "What would have to change first, in order: a charge base and a "
        "volume base in units.py; physical constants such as F as "
        "declarable quantities; and a decision about whether a membrane "
        "potential is a species, a parameter, or a state variable with a "
        "capacitive current equation of its own. The last is a change to "
        "the IR and not to this module."
    ),
    "voltage_gated_channel": (
        "Everything that blocks ion_channel_ohmic blocks this, and one "
        "thing more. A Boltzmann open probability is "
        "1/(1 + exp(-(V - V_half)/k)), and the rate-law parser in units.py "
        "has no function calls at all: check_rate_law('exp(x)', ...) raises "
        "UnitError -- no unit declared for 'exp' -- even though "
        "Terium/core/network.py allows exp in a rate law and "
        "analysis.derivative_function evaluates it happily. So the gate "
        "would be unverifiable even in a unit system that knew what a volt "
        "was: the checker cannot see through the exponential to the "
        "potentials inside it.\n\n"
        "Both halves are fixable and neither is fixable here. Until they "
        "are, a voltage-gated conductance in Terrium would be a shape "
        "somebody drew rather than a mechanism anybody could check."
    ),
}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

#: The motifs defined in this module, by name.
TRANSPORT_LIBRARY: Dict[str, Motif] = {
    motif.name: motif
    for motif in (
        PASSIVE_LEAK,
        FACILITATED_DIFFUSION,
        SYMPORT,
        ANTIPORT,
        PRIMARY_ACTIVE_TRANSPORT,
        RECEPTOR_LIGAND_INTERNALIZATION,
    )
}

#: The one spelling difference worth carrying. `library.py` spells
#: `dimerisation` with an s, so the motif follows it; the z is what most
#: callers will type.
ALIASES: Dict[str, str] = {
    "receptor_ligand_internalization": "receptor_ligand_internalisation",
}


def _refuse_duplicates() -> None:
    """Fail at import if this module redefines a mechanism library.py has.

    The guard `library_enzymology` carries, for the same reason: two rate
    laws for one mechanism is two answers to one question, and a merged
    dictionary picks one of them without saying so. `facilitated_diffusion`
    is not a redefinition of `facilitated_transport` -- the module
    docstring makes that argument -- and it does not collide by name
    either, which is what this checks.
    """
    collisions = sorted(set(LIBRARY) & set(TRANSPORT_LIBRARY))
    if collisions:
        raise MotifError(
            f"library_transport redefines {collisions}, which library.py "
            f"already defines. Re-export the existing motif or change it in "
            f"place; do not ship a second copy of a rate law under a name "
            f"that already means something."
        )


_refuse_duplicates()

#: Every motif reachable by name from here: library.py's and this module's.
#: Built after the duplicate check, so it cannot be the thing that hides a
#: collision.
FULL_LIBRARY: Dict[str, Motif] = {**LIBRARY, **TRANSPORT_LIBRARY}


def transport_motif(name: str) -> Motif:
    """Look a motif up by name, refusing the withheld ones with the reason.

    Three outcomes rather than two, because there are three situations and
    they need different sentences:

      * the motif exists -- return it;
      * the mechanism is real and this IR cannot express it honestly --
        raise `TransportMotifWithheld` with what it needs and what would
        have to change first;
      * nobody has written it -- raise `KeyError` listing what is
        available, because that one usually is a typo.

    Collapsing the middle case into the last would tell a caller asking for
    an ion channel that there is no such thing, which is false, and would
    send them hunting for a spelling instead of reading the reason.
    """
    resolved = ALIASES.get(name, name)
    if resolved in WITHHELD:
        raise TransportMotifWithheld(
            f"{resolved!r} is not in this library, and the reason is not "
            f"that nobody got around to it.\n\n{WITHHELD[resolved]}"
        )
    try:
        return FULL_LIBRARY[resolved]
    except KeyError:
        raise KeyError(
            f"no motif named {name!r}. Available: "
            f"{', '.join(sorted(FULL_LIBRARY))}. Withheld with a reason "
            f"(ask for one by name to read it): "
            f"{', '.join(sorted(WITHHELD))}."
        ) from None


__all__ = [
    # defined here
    "PASSIVE_LEAK",
    "FACILITATED_DIFFUSION",
    "SYMPORT",
    "ANTIPORT",
    "PRIMARY_ACTIVE_TRANSPORT",
    "RECEPTOR_LIGAND_INTERNALIZATION",
    # re-exported from library.py, not redefined: the zero-trans limit of
    # FACILITATED_DIFFUSION, kept reachable under the name it already has.
    "FACILITATED_TRANSPORT",
    # the compartment convention
    "VOLUME_RATIO",
    # refusals
    "TransportMotifWithheld",
    "WITHHELD",
    # registry
    "ALIASES",
    "TRANSPORT_LIBRARY",
    "FULL_LIBRARY",
    "transport_motif",
]
