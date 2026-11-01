"""Metabolic pathway building blocks, written so they cannot describe a
reaction that creates free energy from nothing.

WHY THERMODYNAMICS IS THE THEME AND NOT AN AFTERTHOUGHT
-------------------------------------------------------
Every other library in this package can be wrong only by getting a rate
wrong. A metabolic pathway can be wrong in a way that is worse than that:
it can run. A chain of reversible steps whose kinetic constants were each
resolved from a different paper will, in general, carry a net flux around a
cycle at equilibrium, or push a metabolite uphill for free. The trajectory
is smooth, the solver is happy, the plot looks like biochemistry, and the
model has quietly built a perpetual motion machine.

Nothing in `units.py` can catch that -- the law balances dimensionally. No
steady-state check catches it either, because the wrong model HAS a steady
state; it is just not the one the second law permits. The only place it can
be caught is here, in the shape of the motifs and in the constraints
written beside them.

THE HALDANE RELATIONSHIP, AND WHY THE RESOLVER MUST BE TOLD ABOUT IT
---------------------------------------------------------------------
For a one-substrate, one-product reversible enzymatic step written in the
reversible Michaelis-Menten form

    v = (kcat_f * E * S / Kms - kcat_r * E * P / Kmp)
        / (1 + S / Kms + P / Kmp)

setting v = 0 and solving gives the ratio of product to substrate at
equilibrium, which is by definition the equilibrium constant:

    Keq = (kcat_f * Kmp) / (kcat_r * Kms)

That is the Haldane relationship. It is not a modelling convention and not
an approximation. It is thermodynamics: Keq is fixed by the standard free
energy change of the reaction, which is a property of the chemistry and has
nothing to do with which enzyme catalyses it. A catalyst changes how fast
equilibrium is reached and cannot change where it is.

THE CONSEQUENCE FOR THIS CODEBASE, STATED LOUDLY

    kcat_f, kcat_r, Kms and Kmp CANNOT BE RESOLVED INDEPENDENTLY.

They are four numbers with three degrees of freedom. A resolver that sends
four scouts to four papers and collects four values has not resolved four
quantities -- it has resolved three and made a claim about the fourth,
and the claim will be wrong by whatever the papers' assay conditions
differed by. The resulting model does not merely have imprecise kinetics;
if the implied Keq disagrees with the thermodynamic one, the step is
running in a direction the free energy does not permit.

`check_haldane` below is the check. It is a function rather than a
`Motif.__post_init__` assertion because the values are not known at motif
definition time -- the defaults are placeholders and the real numbers
arrive from the pipeline -- so the builder, or the report, is the layer
that can call it. It is exported so that layer has something to call.

WHY linear_pathway_segment IS PARAMETERISED BY Keq AND NOT BY kcat_r
---------------------------------------------------------------------
Substituting the Haldane relationship into the reversible form removes
kcat_r entirely:

    kcat_r = kcat_f * Kmp / (Kms * Keq)

    v = kcat_f * E * (S - P / Keq) / (Kms * (1 + S / Kms + P / Kmp))

The two expressions are the same function. The difference is what a caller
can express. The first can be given four constants that imply an impossible
Keq. The second cannot: `v` carries the sign of `(S - P / Keq)` and nothing
else, so flux runs downhill for every value of every parameter. The
constraint is enforced by the ALGEBRA rather than by a check somebody has
to remember to run.

That is why the segment motif -- the piece meant to be chained into a
pathway, where the error compounds step by step -- is written this way, and
why `reversible_michaelis_menten` (which is `library.REVERSIBLE_CATALYSIS`)
is still offered in the four-constant form. The four-constant form is what
papers report and what a reader recognises. The Keq form is what a chain of
twelve steps should be built from.

WHY reversible_michaelis_menten IS AN ALIAS AND NOT A NEW MOTIF
----------------------------------------------------------------
`library.REVERSIBLE_CATALYSIS` is already the full two-directional rate
law, symbol for symbol. Defining it again here under the name the
literature uses would put one equation in the registry twice, which is the
defect `library_enzymology._refuse_duplicates` exists to prevent and which
this repository has produced before. So `REVERSIBLE_MICHAELIS_MENTEN` is
bound to that same object, exactly as `library_enzymology.HILL_KINETICS` is
bound to `library.COOPERATIVE_CATALYSIS`, and `ALIASES` records the name.

What that motif was missing was not algebra. It said the Haldane
relationship exists and did not say what it is, which is the half a reader
needs in order to check anything. The equation has been added to the motif
itself, in `library.py`, where the one copy lives.

SAME ALGEBRA, DIFFERENT MECHANISM: WHEN THAT IS NOT A DUPLICATE
----------------------------------------------------------------
`moiety_conserved_cycle` is two opposing Michaelis-Menten steps, and so is
`library.PHOSPHORYLATION_CYCLE`. `branch_point` is two Michaelis-Menten
steps sharing a substrate, which is also what `builder.compete` builds from
two `catalytic_step`s. These are not duplications, and the library already
settled the rule: `saturable_degradation` and `facilitated_transport` are
both `kcat * E * X / (Km + X)` and both exist, because a duplicate is two
answers to ONE question, and "how fast does this protease clear its
substrate" is not the question "how fast does this carrier move a solute".

The line drawn here is: a motif earns its place by its STOICHIOMETRY and
its BASIS, not by its algebra. `cofactor_coupled_step` earns it outright --
it returns a spent cofactor, which `ordered_bi_bi` cannot express at all.
`branch_point` earns less: it is the network `compete` already builds, and
what it adds is one object, two named product ports, and a basis about flux
partitioning. That is a weaker claim and it is written down here rather
than left for a reader to discover.

THE TOTAL OF A CONSERVED POOL IS A SCENARIO CHOICE
---------------------------------------------------
An adenine nucleotide pool, or a pyridine nucleotide pool, is conserved
because of the stoichiometry: every reaction that spends ATP makes an ADP.
`ReactionNetwork.conservation_laws` derives `C_active + C_spent` from the
stoichiometric matrix without being told, and that is the right place for
it -- a structural fact should come from the structure.

What follows is that the pool TOTAL is not a parameter of any motif here,
and must not become one. The total is the sum of two initial
concentrations, both of them KIND_CONCENTRATION and therefore CHOSEN: no
paper reports how much NAD your model has. A `C_total` parameter would be
a lumped scenario quantity of exactly the kind ADR 0013 blocks, and it
would additionally be redundant with the initials, so a model could state a
total that contradicted its own initial conditions and nothing would
notice.

The quantity that actually controls a coupled step is the RATIO -- the
energy charge, or the NAD+/NADH ratio -- and the ratio is set by the
balance of the two arms of the cycle, not by the total. Doubling the pool
at fixed ratio does not double the flux through a step that is saturated in
its cofactor.

NO LUMPED PARAMETERS ANYWHERE
------------------------------
Every rate law here writes `kcat * E * ...` with the enzyme as a species.
There is no Vmax and no `ks`. The reason is ADR 0013 and it is the same
reason as everywhere else in this package: Vmax = kcat * [E]0, [E]0 is the
caller's, and a parameter that mixes a measurement with a scenario choice
can never be resolved from literature. A transporter's Vmax and a
promoter's `ks` are the same mistake in different clothes.

EVERY DEFAULT BELOW IS A PLACEHOLDER
-------------------------------------
Not one number in this file is a measurement, and not one carries a
citation. They are round, order-of-magnitude-plausible values so that a
composed model integrates and can be looked at before anything is resolved.
The pipeline treats every RESOLVABLE default as a quantity to go and find.

The placeholder Keq is 1.0, deliberately. Any other value would encode a
claim about which direction the reaction runs, and 1.0 is the only number
that asserts nothing.

WHAT THIS MODULE DOES NOT CLAIM
--------------------------------
It does not claim to make a model thermodynamically valid. It removes one
specific way of being invalid -- a reversible step running uphill -- and
provides checks for two more. It says nothing about:

  * whether the pathway's overall drop in free energy is enough to carry
    the flux the caller wants (`check_segment_drive` computes the ceiling;
    it cannot know the caller's concentrations unless told);
  * membrane potential, which is most of the proton-motive force for a
    charge-carrying transporter and which nothing here can compute;
  * ionic strength, pH and temperature, which move every Keq and which the
    motifs have no slot for;
  * whether the mechanism is right at all. A rate law can be
    thermodynamically impeccable and describe the wrong enzyme.
"""

from __future__ import annotations

import math
from typing import Dict, Sequence, Tuple

try:
    from .motifs import (
        KIND_AFFINITY, KIND_EXPONENT, KIND_RATE_CONSTANT,
        Motif, MotifError, MotifParameter, Port, ReactionTemplate,
        ROLE_ENZYME, ROLE_PARTNER, ROLE_PRODUCT, ROLE_REGULATOR,
        ROLE_SUBSTRATE,
    )
    from .library import LIBRARY, REVERSIBLE_CATALYSIS
except ImportError:  # pragma: no cover - flat import
    from motifs import (  # type: ignore[no-redef]
        KIND_AFFINITY, KIND_EXPONENT, KIND_RATE_CONSTANT,
        Motif, MotifError, MotifParameter, Port, ReactionTemplate,
        ROLE_ENZYME, ROLE_PARTNER, ROLE_PRODUCT, ROLE_REGULATOR,
        ROLE_SUBSTRATE,
    )
    from library import LIBRARY, REVERSIBLE_CATALYSIS  # type: ignore[no-redef]


class ThermodynamicError(ValueError):
    """A set of constants describes a reaction the second law forbids.

    Separate from `MotifError` because it is a different failure. A
    malformed motif is a programming mistake and is found at import; a
    thermodynamically impossible parameter set is a RESOLUTION result -- the
    numbers arrived from the literature and do not fit together -- and the
    reader who has to act on it is the person reading the gap report, not
    the person who wrote the motif.
    """


# ---------------------------------------------------------------------------
# Reversible steps and pathway segments
# ---------------------------------------------------------------------------

LINEAR_PATHWAY_SEGMENT = Motif(
    name="linear_pathway_segment",
    summary=(
        "One reversible enzymatic step, parameterised by its equilibrium "
        "constant so that a chain of them cannot run uphill."
    ),
    basis=(
        "The reversible Michaelis-Menten form with the Haldane relationship "
        "already substituted in. Start from the four-constant law "
        "(library.REVERSIBLE_CATALYSIS): "
        "v = (kcat_f*E*S/Kms - kcat_r*E*P/Kmp) / (1 + S/Kms + P/Kmp). "
        "Setting v = 0 gives P/S at equilibrium, which is the equilibrium "
        "constant, so "
        "\n\n"
        "    Keq = (kcat_f * Kmp) / (kcat_r * Kms)"
        "\n\n"
        "-- the Haldane relationship. It is thermodynamics, not convention: "
        "Keq is fixed by the reaction's standard free energy change and a "
        "catalyst cannot move it. So the four kinetic constants have three "
        "degrees of freedom and CANNOT BE RESOLVED INDEPENDENTLY. Four "
        "values from four papers are three measurements and one accident, "
        "and if the accident disagrees with the thermodynamic Keq the step "
        "runs in a direction the free energy forbids. "
        "\n\n"
        "This motif substitutes kcat_r = kcat_f*Kmp/(Kms*Keq), which "
        "collapses the numerator to kcat_f*E*(S - P/Keq)/Kms. The rate then "
        "carries the sign of (S - P/Keq) for every value of every "
        "parameter: flux runs downhill by construction rather than by a "
        "check somebody has to remember. Chain n copies with "
        "`builder.chain` (or `linear_pathway` below) and the segment's "
        "overall equilibrium constant is the product of the steps' Keq. "
        "\n\n"
        "What it does not claim: the substituted kcat_r is only as good as "
        "Keq. It also assumes one substrate and one product -- a step that "
        "consumes a cofactor has a Keq that depends on the cofactor ratio, "
        "and belongs with `cofactor_coupled_step` instead."
    ),
    ports=(
        Port("S", ROLE_SUBSTRATE, 1.0, description="substrate of this step"),
        Port("P", ROLE_PRODUCT, 0.0, description="product of this step"),
        Port("E", ROLE_ENZYME, 1e-3,
             description="the enzyme; neither consumed nor produced"),
    ),
    parameters=(
        MotifParameter(
            "kcat_f", KIND_RATE_CONSTANT, 100.0, "1/s", table="kcat",
            description=(
                "forward turnover number; illustrative placeholder"
            ),
        ),
        MotifParameter(
            "Kms", KIND_AFFINITY, 0.1, "mM", table="km",
            description=(
                "Michaelis constant for the substrate; illustrative "
                "placeholder"
            ),
        ),
        MotifParameter(
            "Kmp", KIND_AFFINITY, 0.5, "mM", table="km", ligand="P",
            description=(
                "Michaelis constant for the product, i.e. for the reverse "
                "direction; illustrative placeholder"
            ),
        ),
        MotifParameter(
            "Keq", KIND_AFFINITY, 1.0, "dimensionless", table=None,
            description=(
                "equilibrium constant [P]/[S] at equilibrium, from the "
                "reaction's standard free energy change rather than from a "
                "kinetics database. Illustrative placeholder, and "
                "deliberately 1.0: any other value would assert which way "
                "this reaction runs"
            ),
        ),
    ),
    reactions=(
        ReactionTemplate(
            "net_step",
            reactants={"S": 1},
            products={"P": 1},
            rate_law=(
                "{kcat_f} * {E} * ({S} - {P} / {Keq}) / "
                "({Kms} * (1 + {S} / {Kms} + {P} / {Kmp}))"
            ),
            modifiers=("E",),
        ),
    ),
)


# ---------------------------------------------------------------------------
# Branching
# ---------------------------------------------------------------------------

BRANCH_POINT = Motif(
    name="branch_point",
    summary="One metabolite drawn on by two enzymes with different kinetics.",
    basis=(
        "Two irreversible Michaelis-Menten steps consuming the same "
        "metabolite. The competition is not written into either rate law -- "
        "it is the shared pool, and it emerges from the stoichiometry. "
        "\n\n"
        "The interesting quantity is the flux split: "
        "\n\n"
        "    v1/v2 = (kcat1*E1 / (Km1 + S)) / (kcat2*E2 / (Km2 + S))"
        "\n\n"
        "which is NOT a constant. Well below both Michaelis constants it "
        "tends to the ratio of specificity constants times enzyme amounts, "
        "(kcat1*E1/Km1) / (kcat2*E2/Km2). Well above both, the Michaelis "
        "constants cancel out entirely and it tends to kcat1*E1/kcat2*E2. "
        "A branch whose enzyme is slow but tight can therefore take most of "
        "the flux at low substrate and lose it at high substrate. That "
        "reversal is why a branch point is a control point rather than a "
        "fixed splitter, and it is why the split cannot be reported as a "
        "single ratio. "
        "\n\n"
        "Honest about what this adds: `builder.compete` already builds this "
        "same network from two `catalytic_step`s. What the motif adds is "
        "one object with named product ports and this basis -- not new "
        "algebra. It does not model allosteric coupling between the two "
        "branches, and it assumes both steps are far from equilibrium; a "
        "branch that is reversible should be built from "
        "`linear_pathway_segment` instead."
    ),
    ports=(
        Port("S", ROLE_SUBSTRATE, 1.0,
             description="the metabolite both branches draw on"),
        Port("P1", ROLE_PRODUCT, 0.0, description="product of the first branch"),
        Port("P2", ROLE_PRODUCT, 0.0, description="product of the second branch"),
        Port("E1", ROLE_ENZYME, 1e-3, description="enzyme of the first branch"),
        Port("E2", ROLE_ENZYME, 1e-3, description="enzyme of the second branch"),
    ),
    parameters=(
        MotifParameter(
            "kcat_1", KIND_RATE_CONSTANT, 100.0, "1/s", table="kcat",
            description="turnover number of the first branch; illustrative placeholder",
        ),
        MotifParameter(
            "Km_1", KIND_AFFINITY, 0.1, "mM", table="km",
            description="Michaelis constant of the first branch; illustrative placeholder",
        ),
        MotifParameter(
            "kcat_2", KIND_RATE_CONSTANT, 10.0, "1/s", table="kcat",
            description="turnover number of the second branch; illustrative placeholder",
        ),
        MotifParameter(
            "Km_2", KIND_AFFINITY, 0.01, "mM", table="km",
            description="Michaelis constant of the second branch; illustrative placeholder",
        ),
    ),
    reactions=(
        ReactionTemplate(
            "branch_one",
            reactants={"S": 1},
            products={"P1": 1},
            rate_law="{kcat_1} * {E1} * {S} / ({Km_1} + {S})",
            modifiers=("E1",),
        ),
        ReactionTemplate(
            "branch_two",
            reactants={"S": 1},
            products={"P2": 1},
            rate_law="{kcat_2} * {E2} * {S} / ({Km_2} + {S})",
            modifiers=("E2",),
        ),
    ),
)


# ---------------------------------------------------------------------------
# Cofactor pools
# ---------------------------------------------------------------------------

MOIETY_CONSERVED_CYCLE = Motif(
    name="moiety_conserved_cycle",
    summary=(
        "A cofactor pool -- ATP/ADP, NAD+/NADH -- cycling between an active "
        "and a spent form."
    ),
    basis=(
        "Two opposing saturable steps on the same moiety: something spends "
        "the active form and something regenerates it. The conservation law "
        "C_active + C_spent is STRUCTURAL -- it follows from the "
        "stoichiometry, and `ReactionNetwork.conservation_laws` derives it "
        "from the stoichiometric matrix rather than being told. "
        "\n\n"
        "THE POOL TOTAL IS A SCENARIO CHOICE, NOT A MEASUREMENT. It is the "
        "sum of two initial concentrations, both KIND_CONCENTRATION and "
        "therefore chosen by the caller; no paper reports how much adenine "
        "nucleotide is in your model. It is deliberately not a parameter of "
        "this motif. A `C_total` parameter would lump a scenario choice "
        "into something the resolver would then go looking for (ADR 0013), "
        "and it would be redundant with the initials, so a model could "
        "state a total contradicting its own initial conditions with "
        "nothing to notice. "
        "\n\n"
        "What a coupled step actually responds to is the RATIO -- the "
        "energy charge, the NAD+/NADH ratio -- and the ratio is set by the "
        "balance of the two arms, not by the total. Doubling the pool at "
        "fixed ratio does not double the flux through a step that is "
        "saturated in its cofactor. "
        "\n\n"
        "Shares its algebra with `library.PHOSPHORYLATION_CYCLE` and is not "
        "a duplicate of it: that motif's moiety is a protein being modified "
        "by a dedicated kinase and phosphatase, this one's is a small "
        "molecule shared by every reaction in the model. The stoichiometry "
        "and the questions differ; the equations happen to agree. "
        "\n\n"
        "What it does not claim: both arms are written irreversibly, so "
        "this cycle dissipates free energy and cannot be run backwards. "
        "That is correct for a real ATP cycle and wrong for any moiety "
        "whose interconversion is near equilibrium."
    ),
    ports=(
        Port("C_active", ROLE_PARTNER, 1.0,
             description="the usable form -- ATP, NADH, reduced glutathione"),
        Port("C_spent", ROLE_PARTNER, 0.0,
             description="the spent form -- ADP, NAD+, oxidised glutathione"),
        Port("E_regen", ROLE_ENZYME, 1e-3,
             description="the enzyme that regenerates the active form"),
        Port("E_demand", ROLE_ENZYME, 1e-3,
             description="the enzyme representing bulk demand on the pool"),
    ),
    parameters=(
        MotifParameter(
            "kcat_regen", KIND_RATE_CONSTANT, 10.0, "1/s", table="kcat", ligand="C_spent",
            description=(
                "turnover number of the regenerating enzyme; illustrative "
                "placeholder"
            ),
        ),
        MotifParameter(
            "Km_regen", KIND_AFFINITY, 0.1, "mM", table="km", ligand="C_spent",
            description=(
                "affinity of the regenerating enzyme for the spent form; "
                "illustrative placeholder"
            ),
        ),
        MotifParameter(
            "kcat_demand", KIND_RATE_CONSTANT, 10.0, "1/s", table="kcat", ligand="C_active",
            description=(
                "turnover number of the demand step; illustrative placeholder"
            ),
        ),
        MotifParameter(
            "Km_demand", KIND_AFFINITY, 0.1, "mM", table="km", ligand="C_active",
            description=(
                "affinity of the demand step for the active form; "
                "illustrative placeholder"
            ),
        ),
    ),
    reactions=(
        ReactionTemplate(
            "regeneration",
            reactants={"C_spent": 1},
            products={"C_active": 1},
            rate_law=(
                "{kcat_regen} * {E_regen} * {C_spent} / "
                "({Km_regen} + {C_spent})"
            ),
            modifiers=("E_regen",),
        ),
        ReactionTemplate(
            "demand",
            reactants={"C_active": 1},
            products={"C_spent": 1},
            rate_law=(
                "{kcat_demand} * {E_demand} * {C_active} / "
                "({Km_demand} + {C_active})"
            ),
            modifiers=("E_demand",),
        ),
    ),
)

COFACTOR_COUPLED_STEP = Motif(
    name="cofactor_coupled_step",
    summary=(
        "A reaction that can only proceed by spending a cofactor from a "
        "conserved pool."
    ),
    basis=(
        "S + C_active -> P + C_spent, catalysed by one enzyme, saturable in "
        "both the substrate and the cofactor: "
        "\n\n"
        "    v = kcat*E * S/(Km_s + S) * C_active/(Km_c + C_active)"
        "\n\n"
        "THE COFACTOR IS A REACTANT, NOT A MODIFIER. That is the entire "
        "point of the motif. Written as a modifier -- which is what a rate "
        "law with a cofactor term but no cofactor stoichiometry does -- the "
        "step would consume nothing, the pool could never run down, and the "
        "model could not show the one thing cofactor coupling exists to "
        "show. Composed with `moiety_conserved_cycle` the pool total is "
        "conserved and the step competes with everything else for it. "
        "\n\n"
        "Distinct from `ordered_bi_bi` and `ping_pong_bi_bi` in "
        "STOICHIOMETRY rather than in algebra: those consume two substrates "
        "and release one product, and neither can express returning the "
        "spent cofactor. "
        "\n\n"
        "The multiplicative denominator is the rapid-equilibrium "
        "random-order form -- substrate and cofactor bind independently, so "
        "the apparent Km for the substrate does not depend on the cofactor "
        "level. For many dehydrogenases that is false and the mechanism is "
        "ordered with the cofactor binding first, in which case "
        "`library.ORDERED_BI_BI` is the right motif and this one is wrong "
        "by the Kia*Kmb term. The assumption is stated because the two rate "
        "laws are distinguishable from steady-state data and choosing "
        "silently would fit data this model should not fit. "
        "\n\n"
        "What it does not claim: written irreversibly. A real "
        "NAD-dependent step is reversible and its equilibrium constant "
        "depends on the NAD+/NADH ratio, so at a ratio near equilibrium "
        "this form overstates the flux and cannot reverse at all."
    ),
    ports=(
        Port("S", ROLE_SUBSTRATE, 1.0, description="substrate consumed"),
        Port("P", ROLE_PRODUCT, 0.0, description="product formed"),
        Port("C_active", ROLE_PARTNER, 1.0,
             description="usable cofactor, consumed by this step"),
        Port("C_spent", ROLE_PARTNER, 0.0,
             description="spent cofactor, returned to the pool by this step"),
        Port("E", ROLE_ENZYME, 1e-3, description="the enzyme"),
    ),
    parameters=(
        MotifParameter(
            "kcat", KIND_RATE_CONSTANT, 100.0, "1/s", table="kcat",
            description="turnover number; illustrative placeholder",
        ),
        MotifParameter(
            "Km_s", KIND_AFFINITY, 0.1, "mM", table="km",
            description=(
                "Michaelis constant for the substrate; illustrative "
                "placeholder"
            ),
        ),
        MotifParameter(
            "Km_c", KIND_AFFINITY, 0.05, "mM", table="km", ligand="C_active",
            description=(
                "Michaelis constant for the cofactor; illustrative "
                "placeholder"
            ),
        ),
    ),
    reactions=(
        ReactionTemplate(
            "coupled_catalysis",
            reactants={"S": 1, "C_active": 1},
            products={"P": 1, "C_spent": 1},
            rate_law=(
                "{kcat} * {E} * {S} / ({Km_s} + {S}) * "
                "{C_active} / ({Km_c} + {C_active})"
            ),
            modifiers=("E",),
        ),
    ),
)


# ---------------------------------------------------------------------------
# Regulation and entry
# ---------------------------------------------------------------------------

ALLOSTERIC_FEEDBACK = Motif(
    name="allosteric_feedback",
    summary=(
        "The first committed step of a pathway, inhibited by the pathway's "
        "own end product."
    ),
    basis=(
        "End-product inhibition of the first committed step -- the "
        "canonical metabolic control motif, reported by Umbarger in 1956 "
        "for isoleucine shutting off threonine deaminase. The rate is "
        "Michaelis-Menten in the substrate, multiplied by a Hill inhibition "
        "term in the end product: "
        "\n\n"
        "    v = kcat*E * S/(Km + S) * Ki^n/(Ki^n + F^n)"
        "\n\n"
        "Two things about the placement. It is the FIRST step because "
        "inhibiting a later one would back up every intermediate ahead of "
        "it; stopping the commitment costs nothing to store. It is the "
        "COMMITTED step -- the first one whose product has no other fate -- "
        "because inhibiting a shared step would starve the branches that "
        "share it. "
        "\n\n"
        "n > 1 is what makes the response sharp enough to hold the end "
        "product near a setpoint; n = 1 gives a hyperbolic response that "
        "sags under load. n is KIND_EXPONENT and therefore CHOSEN: it is a "
        "phenomenological exponent fitted to a curve, not a count of "
        "subunits, and not something a database supplies. "
        "\n\n"
        "What it does not claim: this is a phenomenological inhibition "
        "term, not a mechanism. It does not say the inhibitor binds a "
        "regulatory site, does not distinguish K-systems from V-systems, "
        "and its n is not a structural quantity. If the enzyme's "
        "cooperativity is itself the subject, "
        "`library_enzymology.MWC_ALLOSTERY` states a mechanism and its n IS "
        "the subunit count. Being irreversible, this step also cannot "
        "describe feedback near equilibrium."
    ),
    ports=(
        Port("S", ROLE_SUBSTRATE, 1.0,
             description="substrate of the committed step"),
        Port("P", ROLE_PRODUCT, 0.0,
             description="product of the committed step"),
        Port("E", ROLE_ENZYME, 1e-3,
             description="the regulated enzyme"),
        Port("F", ROLE_REGULATOR, 0.0,
             description=(
                 "the end product feeding back; wire it to the last step's "
                 "product with `builder.couple`"
             )),
    ),
    parameters=(
        MotifParameter(
            "kcat", KIND_RATE_CONSTANT, 100.0, "1/s", table="kcat",
            description=(
                "turnover number of the uninhibited enzyme; illustrative "
                "placeholder"
            ),
        ),
        MotifParameter(
            "Km", KIND_AFFINITY, 0.1, "mM", table="km",
            description=(
                "Michaelis constant for the substrate; illustrative "
                "placeholder"
            ),
        ),
        MotifParameter(
            "Ki", KIND_AFFINITY, 0.1, "mM", table="ki", ligand="F",
            description=(
                "end-product concentration giving half inhibition; "
                "illustrative placeholder"
            ),
        ),
        MotifParameter(
            "n", KIND_EXPONENT, 2.0, "dimensionless",
            description=(
                "Hill coefficient of the feedback; a chosen modelling "
                "exponent, not a subunit count and not a measurement"
            ),
        ),
    ),
    reactions=(
        ReactionTemplate(
            "committed_step",
            reactants={"S": 1},
            products={"P": 1},
            rate_law=(
                "{kcat} * {E} * {S} / ({Km} + {S}) * "
                "{Ki}^{n} / ({Ki}^{n} + {F}^{n})"
            ),
            modifiers=("E", "F"),
        ),
    ),
)

TRANSPORTER_LIMITED_UPTAKE = Motif(
    name="transporter_limited_uptake",
    summary=(
        "Ion-coupled uptake of a nutrient across the membrane, as a "
        "pathway's entry point."
    ),
    basis=(
        "A 1:1 symport: one driving ion crosses with each solute molecule, "
        "and the carrier saturates in both. "
        "\n\n"
        "    v = kcat*T * S_out/(Kt + S_out) * H_out/(Kh + H_out)"
        "\n\n"
        "Uptake is written with the driving ion explicit for the same "
        "reason `library_enzymology.FUTILE_CYCLE` writes ATP explicitly: "
        "accumulating a solute ABOVE its external concentration costs free "
        "energy, and a transporter whose payment is folded into its rate "
        "constant describes a pump running on nothing. With the ion as a "
        "species the gradient can be run down, and a model that "
        "concentrates a nutrient has to show what paid for it. "
        "\n\n"
        "The ion gradient is a SCENARIO CHOICE. Both ion concentrations are "
        "initial values the caller sets; the placeholders are equal, which "
        "asserts no gradient at all, because a placeholder gradient would "
        "be a claim about the cell. "
        "\n\n"
        "THE HONEST LIMITATION, STATED RATHER THAN HIDDEN: this rate law is "
        "irreversible, so it does not enforce its own thermodynamic "
        "ceiling. For a 1:1 symport that ceiling is "
        "\n\n"
        "    S_in/S_out <= H_out/H_in"
        "\n\n"
        "at equilibrium, and this law will happily drive S_in past it. Use "
        "it while the internal concentration is well below the ceiling, and "
        "call `check_symport_gradient` to find out whether it is. A 2:1 "
        "symporter squares the ceiling and is a different motif. "
        "\n\n"
        "If the solute runs DOWNHILL, none of this applies and "
        "`library.FACILITATED_TRANSPORT` is the simpler and correct motif. "
        "The chemical gradient is also only part of the driving force: a "
        "charge-carrying symport is driven by the membrane potential too, "
        "which nothing in this package can compute and which this motif "
        "does not pretend to include."
    ),
    ports=(
        Port("S_out", ROLE_SUBSTRATE, 1.0,
             description="solute in the medium"),
        Port("S_in", ROLE_PRODUCT, 0.0,
             description="solute inside, the pathway's first metabolite"),
        Port("H_out", ROLE_PARTNER, 1e-4,
             description="driving ion outside; a scenario choice"),
        Port("H_in", ROLE_PARTNER, 1e-4,
             description=(
                 "driving ion inside; deliberately equal to the outside "
                 "placeholder, so the default asserts no gradient"
             )),
        Port("T", ROLE_ENZYME, 1e-3, description="the transporter"),
    ),
    parameters=(
        MotifParameter(
            "kcat", KIND_RATE_CONSTANT, 10.0, "1/s", table="kcat",
            description=(
                "transport turnover number; illustrative placeholder"
            ),
        ),
        MotifParameter(
            "Kt", KIND_AFFINITY, 0.01, "mM", table="km",
            description=(
                "external solute concentration at half maximal transport; "
                "illustrative placeholder"
            ),
        ),
        MotifParameter(
            "Kh", KIND_AFFINITY, 1e-4, "mM", table="km", ligand="H_out",
            description=(
                "driving-ion concentration at half maximal transport; "
                "illustrative placeholder"
            ),
        ),
    ),
    reactions=(
        ReactionTemplate(
            "symport",
            reactants={"S_out": 1, "H_out": 1},
            products={"S_in": 1, "H_in": 1},
            rate_law=(
                "{kcat} * {T} * {S_out} / ({Kt} + {S_out}) * "
                "{H_out} / ({Kh} + {H_out})"
            ),
            modifiers=("T",),
        ),
    ),
)


# ---------------------------------------------------------------------------
# The alias, and the registry
# ---------------------------------------------------------------------------

#: The full two-directional rate law, under the name the literature uses.
#:
#: Bound to the SAME object as `library.REVERSIBLE_CATALYSIS`, not to a
#: copy: `REVERSIBLE_MICHAELIS_MENTEN is REVERSIBLE_CATALYSIS` holds and a
#: test pins that it does. See the module docstring for why a second
#: definition of one equation would be a defect rather than a convenience.
REVERSIBLE_MICHAELIS_MENTEN = REVERSIBLE_CATALYSIS

#: Names a caller reaches for that are not the registry's own. Explicit,
#: because a lookup that guessed at near-misses would eventually hand back
#: the wrong mechanism for a typo.
ALIASES: Dict[str, str] = {
    "reversible_michaelis_menten": REVERSIBLE_CATALYSIS.name,
}

#: The motifs this module DEFINES.
#:
#: A separate mapping rather than an insertion into `library.LIBRARY`, for
#: the reason `library_expression` gives: `grammar.py` turns a phrase at the
#: front door into a composition, and a motif reachable by name with no
#: phrase that reaches it is a promise the front door does not keep.
#: Registering these is a grammar change and belongs in the change that
#: adds the phrases.
METABOLIC_LIBRARY: Dict[str, Motif] = {
    motif_.name: motif_
    for motif_ in (
        LINEAR_PATHWAY_SEGMENT,
        BRANCH_POINT,
        MOIETY_CONSERVED_CYCLE,
        COFACTOR_COUPLED_STEP,
        ALLOSTERIC_FEEDBACK,
        TRANSPORTER_LIMITED_UPTAKE,
    )
}


def _refuse_duplicates() -> None:
    """Fail at import if this module redefines something `library.py` has.

    The same guard `library_enzymology` carries, and for the same reason:
    `{**LIBRARY, **METABOLIC_LIBRARY}` resolves a collision by picking one,
    which is how two rate laws for one mechanism coexist for a year with no
    way for a reader to tell which one ran. There is no correct winner, so
    there is no silent choice.
    """
    collisions = sorted(set(LIBRARY) & set(METABOLIC_LIBRARY))
    if collisions:
        raise MotifError(
            f"library_metabolic redefines {collisions}, which library.py "
            f"already defines. Two rate laws for one mechanism is two "
            f"answers to one question, and merging would pick one of them "
            f"without saying so. Re-export the existing motif, or change "
            f"the existing one in place -- do not add a second copy."
        )


_refuse_duplicates()

#: Every motif a metabolic composition can reach by name: `library.py`'s and
#: this module's. Built once, after the duplicate check, so it cannot be the
#: thing that hides a collision.
FULL_LIBRARY: Dict[str, Motif] = {**LIBRARY, **METABOLIC_LIBRARY}


def metabolic_motif(name: str) -> Motif:
    """Look a motif up by name, following the alias table.

    Refuses with the available names rather than returning None. A caller
    who typed `reversible_michaelis_menton` needs to see the spelling in
    the message, and a caller who wanted a mechanism nobody has written
    needs to be told that rather than handed a plausible neighbour.
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


# ---------------------------------------------------------------------------
# Thermodynamic checks the builder can call
# ---------------------------------------------------------------------------
#
# None of these is called automatically. They take VALUES, and a motif
# definition has only placeholders -- the real numbers arrive from the
# resolver, so the layer that has them is the layer that must check them.
# Exported so that layer has something to call rather than a paragraph to
# re-derive.

#: How far the Haldane relationship may be missed before it is a finding.
#:
#: A CONVENTION this module chose, not a measurement. It is a factor, not a
#: percentage, because kinetic constants from different papers differ by
#: factors. Two is loose enough that ordinary between-paper scatter does not
#: fire it and tight enough that an order-of-magnitude inconsistency does.
#: A caller who knows the uncertainties on their own four numbers should
#: pass their own tolerance instead of inheriting this one.
HALDANE_TOLERANCE = 2.0


def _require_positive(name: str, value: float) -> float:
    numeric = float(value)
    if not math.isfinite(numeric) or numeric <= 0.0:
        raise ThermodynamicError(
            f"{name} is {value!r}. Every constant in a Haldane relationship "
            f"is a strictly positive finite number -- a zero or negative "
            f"kcat, Km or Keq is not a slow reaction, it is not a reaction. "
            f"Fix the resolved value or report it as unresolved; do not "
            f"pass a placeholder through this check."
        )
    return numeric


def haldane_keq(
    kcat_f: float, kcat_r: float, Kms: float, Kmp: float
) -> float:
    """The equilibrium constant a set of four kinetic constants implies.

        Keq = (kcat_f * Kmp) / (kcat_r * Kms)

    This is what the kinetics SAY the equilibrium is. Compare it against
    what thermodynamics says it is; they are two independent statements
    about one number and they have to agree.
    """
    kcat_f = _require_positive("kcat_f", kcat_f)
    kcat_r = _require_positive("kcat_r", kcat_r)
    Kms = _require_positive("Kms", Kms)
    Kmp = _require_positive("Kmp", Kmp)
    return (kcat_f * Kmp) / (kcat_r * Kms)


def haldane_kcat_r(kcat_f: float, Kms: float, Kmp: float, keq: float) -> float:
    """The reverse turnover number the other three constants and Keq force.

        kcat_r = kcat_f * Kmp / (Kms * Keq)

    Useful to a resolver: three kinetic constants plus a thermodynamic Keq
    determine the fourth, so the fourth should be DERIVED rather than
    searched for. A search that finds it anyway is a consistency check, not
    an extra measurement.
    """
    kcat_f = _require_positive("kcat_f", kcat_f)
    Kms = _require_positive("Kms", Kms)
    Kmp = _require_positive("Kmp", Kmp)
    keq = _require_positive("Keq", keq)
    return kcat_f * Kmp / (Kms * keq)


def haldane_residual(
    kcat_f: float, kcat_r: float, Kms: float, Kmp: float, keq: float
) -> float:
    """How badly a set of constants misses its equilibrium constant.

    Returns the FACTOR by which the kinetically implied Keq differs from
    the thermodynamic one, always >= 1 whichever way the discrepancy runs.
    A factor rather than a difference because these quantities span orders
    of magnitude and an absolute residual would mean nothing.
    """
    implied = haldane_keq(kcat_f, kcat_r, Kms, Kmp)
    stated = _require_positive("Keq", keq)
    ratio = implied / stated
    return ratio if ratio >= 1.0 else 1.0 / ratio


def check_haldane(
    kcat_f: float,
    kcat_r: float,
    Kms: float,
    Kmp: float,
    keq: float,
    *,
    tolerance: float = HALDANE_TOLERANCE,
    label: str = "this reversible step",
) -> None:
    """Refuse a parameter set that describes a reaction creating free energy.

    Raises `ThermodynamicError` naming the factor, the two equilibrium
    constants, and the value of kcat_r that WOULD satisfy the relationship
    -- because "these four numbers are inconsistent" is not actionable and
    "kcat_r must be 3.2 1/s for this Keq" is.
    """
    if tolerance < 1.0:
        raise ThermodynamicError(
            f"tolerance is {tolerance!r}, and it is a FACTOR, so anything "
            f"below 1.0 cannot be satisfied by any parameter set -- not "
            f"even an exact one. Pass 1.0 to demand exactness, or a factor "
            f"above it."
        )
    factor = haldane_residual(kcat_f, kcat_r, Kms, Kmp, keq)
    if factor <= tolerance:
        return
    implied = haldane_keq(kcat_f, kcat_r, Kms, Kmp)
    should_be = haldane_kcat_r(kcat_f, Kms, Kmp, keq)
    raise ThermodynamicError(
        f"{label}: its kinetic constants imply Keq = {implied:.6g}, and the "
        f"equilibrium constant given is {keq:.6g} -- a factor of "
        f"{factor:.3g}, past the tolerance of {tolerance:.3g}. The Haldane "
        f"relationship Keq = kcat_f*Kmp/(kcat_r*Kms) is thermodynamics, not "
        f"a fitting convention, so a set that misses it describes a "
        f"reaction whose enzyme moves its own equilibrium. With "
        f"kcat_f = {float(kcat_f):.6g}, Kms = {float(Kms):.6g} and "
        f"Kmp = {float(Kmp):.6g}, the only kcat_r consistent with this Keq "
        f"is {should_be:.6g}. Either take that value and drop the searched "
        f"one, or report the four constants as mutually inconsistent -- do "
        f"not average them."
    )


def segment_equilibrium_constant(keqs: Sequence[float]) -> float:
    """The overall Keq of steps in series: the product of the steps' Keq.

    Free energies add along a pathway, so equilibrium constants multiply.
    Refuses an empty sequence: the equilibrium constant of no reactions is
    not 1, it is undefined, and returning 1 would let a caller conclude
    that a pathway they forgot to build is at equilibrium.
    """
    if not keqs:
        raise ThermodynamicError(
            "no equilibrium constants given. A segment of zero steps has no "
            "equilibrium constant -- returning 1.0 would report an empty "
            "pathway as poised at equilibrium. Pass the steps' Keq."
        )
    total = 1.0
    for index, value in enumerate(keqs):
        total *= _require_positive(f"Keq of step {index + 1}", value)
    return total


def check_segment_drive(
    keqs: Sequence[float],
    first_substrate: float,
    last_product: float,
    *,
    label: str = "this pathway segment",
) -> None:
    """Refuse end concentrations a segment cannot carry net flux between.

    A segment of steps in series runs forward only while

        last_product / first_substrate < product of the steps' Keq

    and at equality it is at equilibrium. Beyond it the net flux is
    backwards, whatever the enzymes are: no amount of enzyme reverses a
    sign set by free energy.
    """
    ceiling = segment_equilibrium_constant(keqs)
    substrate = _require_positive("the first substrate concentration", first_substrate)
    product = _require_positive("the last product concentration", last_product)
    ratio = product / substrate
    if ratio < ceiling:
        return
    raise ThermodynamicError(
        f"{label}: the end concentrations give a product-to-substrate ratio "
        f"of {ratio:.6g}, and the segment's overall equilibrium constant is "
        f"{ceiling:.6g} (the product of {len(keqs)} step(s)). Net flux "
        f"forward requires the ratio to be BELOW the equilibrium constant; "
        f"at {'equality' if math.isclose(ratio, ceiling) else 'a ratio above it'} "
        f"the segment runs backwards or not at all, and no choice of enzyme "
        f"changes that. Either lower the product, raise the substrate, or "
        f"accept that this segment is a sink rather than a source in this "
        f"scenario."
    )


def symport_ceiling(
    ion_out: float,
    ion_in: float,
    *,
    ions_per_solute: int = 1,
    potential_factor: float = 1.0,
) -> float:
    """The largest S_in/S_out a symport can reach on the ion gradient alone.

    For an m:1 symport at equilibrium the accumulation ratio is
    `(ion_out/ion_in)**m`, times whatever the membrane potential
    contributes.

    `potential_factor` is that contribution and defaults to 1.0, meaning
    NONE. It is an argument rather than a computation because the membrane
    potential is not derivable from anything this package holds, and for a
    charge-carrying symport it is usually the larger term -- so the default
    ceiling is a LOWER bound on what a real cell reaches. A caller with a
    measured potential can pass exp(m*F*dPsi/RT); a caller without one
    should read this ceiling as conservative rather than as the answer.
    """
    ion_out = _require_positive("the outside ion concentration", ion_out)
    ion_in = _require_positive("the inside ion concentration", ion_in)
    potential_factor = _require_positive("potential_factor", potential_factor)
    if ions_per_solute < 1:
        raise ThermodynamicError(
            f"ions_per_solute is {ions_per_solute!r}. A symport moves at "
            f"least one ion per solute; zero ions is facilitated diffusion, "
            f"which is `library.FACILITATED_TRANSPORT` and has no ceiling "
            f"above 1."
        )
    return (ion_out / ion_in) ** ions_per_solute * potential_factor


def check_symport_gradient(
    solute_in: float,
    solute_out: float,
    ion_out: float,
    ion_in: float,
    *,
    ions_per_solute: int = 1,
    potential_factor: float = 1.0,
    label: str = "this uptake step",
) -> None:
    """Refuse an accumulation the ion gradient cannot pay for.

    `transporter_limited_uptake` is written irreversibly and will drive the
    solute past its thermodynamic ceiling without complaint. This is the
    check that says so, and it is separate from the motif because the
    concentrations it needs are a scenario, not a definition.
    """
    ceiling = symport_ceiling(
        ion_out, ion_in,
        ions_per_solute=ions_per_solute,
        potential_factor=potential_factor,
    )
    inside = _require_positive("the internal solute concentration", solute_in)
    outside = _require_positive("the external solute concentration", solute_out)
    achieved = inside / outside
    if achieved <= ceiling:
        return
    raise ThermodynamicError(
        f"{label}: the model holds the solute {achieved:.6g}-fold above the "
        f"medium, and a {ions_per_solute}:1 symport on this ion gradient "
        f"({ion_out:.6g} outside, {ion_in:.6g} inside) can reach at most "
        f"{ceiling:.6g}. The rate law is irreversible and so will keep "
        f"pumping past the ceiling; the trajectory is smooth and describes "
        f"a carrier concentrating a nutrient on free energy nobody "
        f"supplied. Either steepen the ion gradient, lower the internal "
        f"concentration, or -- if the real transporter is driven by the "
        f"membrane potential -- pass `potential_factor`, which this "
        f"package cannot compute and will not invent."
    )


# ---------------------------------------------------------------------------
# Composition helper
# ---------------------------------------------------------------------------


def linear_pathway(
    composition,
    steps: int,
    *,
    prefix: str = "step",
    head_initial: float = 1.0,
    shared_enzyme: bool = False,
):
    """Place `steps` reversible segments head to tail and return them.

    "n reversible steps in series" is a COMPOSITION and not a motif: a
    motif has a fixed set of ports, and n does not. `builder.chain` already
    does the wiring, including the rule that the upstream port creates the
    shared intermediate so it starts at a product's default rather than a
    substrate's. This is that call with the ports named, so a caller does
    not have to know which port of this motif is which.

    `shared_enzyme` is False by default and that is the biologically
    ordinary case: consecutive steps of a pathway are catalysed by
    different enzymes. Sharing one is a deliberate and unusual claim, so it
    has to be asked for.
    """
    try:
        from .builder import CompositionError, chain
    except ImportError:  # pragma: no cover - flat import
        from builder import CompositionError, chain  # type: ignore[no-redef]

    if steps < 1:
        raise CompositionError(
            f"a pathway segment of {steps} steps is not a shorter segment, "
            f"it is not a segment. Say how many steps the pathway has."
        )
    return chain(
        composition,
        LINEAR_PATHWAY_SEGMENT,
        steps,
        prefix=prefix,
        upstream_port="P",
        downstream_port="S",
        shared=("E",) if shared_enzyme else (),
        head_initial=head_initial,
    )


__all__ = [
    # defined here
    "ALLOSTERIC_FEEDBACK",
    "BRANCH_POINT",
    "COFACTOR_COUPLED_STEP",
    "LINEAR_PATHWAY_SEGMENT",
    "MOIETY_CONSERVED_CYCLE",
    "TRANSPORTER_LIMITED_UPTAKE",
    # re-exported from library.py, not redefined
    "REVERSIBLE_MICHAELIS_MENTEN",
    # registry
    "ALIASES",
    "METABOLIC_LIBRARY",
    "FULL_LIBRARY",
    "metabolic_motif",
    # thermodynamic checks
    "HALDANE_TOLERANCE",
    "ThermodynamicError",
    "check_haldane",
    "check_segment_drive",
    "check_symport_gradient",
    "haldane_kcat_r",
    "haldane_keq",
    "haldane_residual",
    "segment_equilibrium_constant",
    "symport_ceiling",
    # composition helper
    "linear_pathway",
]
