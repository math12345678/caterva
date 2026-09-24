"""The motifs themselves: the mechanisms teaching labs actually ask about.

Each entry carries the rate law it encodes and the assumption that licenses
it, because a composed model has to be able to explain its own shape. A
reader who disagrees with the quasi-steady-state assumption behind
Michaelis-Menten should be able to see that it was made, here, rather than
infer it from an equation.

WHY THE ENZYME IS A SPECIES AND NOT A Vmax
------------------------------------------
`catalytic_step` writes

    kcat * E * S / (Km + S)

rather than the textbook `Vmax * S / (Km + S)`. The two are the same
equation with Vmax = kcat * [E]0, and the difference matters entirely for
provenance. `Vmax` is a single parameter that no paper can supply for YOUR
assay, so Terrium has to refuse it (ADR 0013). `kcat` and `Km` are
properties of the enzyme that BRENDA holds, and `E` is a species whose
initial concentration is a scenario choice like any other starting amount.

Writing the mechanism out rather than lumping it does not merely avoid the
refusal -- it removes the quantity that had to be refused.
"""

from __future__ import annotations

from typing import Dict, Tuple

try:
    from .motifs import (
        KIND_AFFINITY, KIND_CONCENTRATION, KIND_EXPONENT, KIND_RATE_CONSTANT,
        Motif, MotifParameter, Port, ReactionTemplate,
        ROLE_COMPLEX, ROLE_ENZYME, ROLE_PARTNER, ROLE_PRODUCT,
        ROLE_REGULATOR, ROLE_SUBSTRATE,
    )
except ImportError:  # pragma: no cover - flat import
    from motifs import (  # type: ignore[no-redef]
        KIND_AFFINITY, KIND_CONCENTRATION, KIND_EXPONENT, KIND_RATE_CONSTANT,
        Motif, MotifParameter, Port, ReactionTemplate,
        ROLE_COMPLEX, ROLE_ENZYME, ROLE_PARTNER, ROLE_PRODUCT,
        ROLE_REGULATOR, ROLE_SUBSTRATE,
    )


# ---------------------------------------------------------------------------
# Enzyme catalysis
# ---------------------------------------------------------------------------

CATALYTIC_STEP = Motif(
    name="catalytic_step",
    summary="One enzyme turning one substrate into one product.",
    basis=(
        "Michaelis-Menten under the quasi-steady-state assumption (Briggs & "
        "Haldane 1925): the enzyme-substrate complex is short-lived relative "
        "to the reaction, so its concentration is treated as constant. Valid "
        "while [E]0 << [S]; it fails for a tightly-binding enzyme at low "
        "substrate, where the free-substrate approximation breaks down."
    ),
    ports=(
        Port("S", ROLE_SUBSTRATE, 1.0, description="substrate consumed"),
        Port("P", ROLE_PRODUCT, 0.0, description="product formed"),
        Port("E", ROLE_ENZYME, 1e-3,
             description="catalyst; neither consumed nor produced"),
    ),
    parameters=(
        MotifParameter("kcat", KIND_RATE_CONSTANT, 100.0, "1/s", table="kcat",
                       description="turnover number of the enzyme"),
        MotifParameter("Km", KIND_AFFINITY, 0.1, "mM", table="km",
                       description="substrate concentration at half maximal rate"),
    ),
    reactions=(
        ReactionTemplate(
            "catalysis",
            reactants={"S": 1},
            products={"P": 1},
            rate_law="{kcat} * {E} * {S} / ({Km} + {S})",
            modifiers=("E",),
        ),
    ),
)

COMPETITIVE_INHIBITION = Motif(
    name="competitive_inhibition",
    summary="Catalysis with an inhibitor competing for the active site.",
    basis=(
        "The inhibitor binds free enzyme only, so it raises the apparent Km "
        "by (1 + [I]/Ki) and leaves kcat untouched. That signature -- Vmax "
        "unchanged, Km inflated -- is what distinguishes competitive from "
        "uncompetitive inhibition on a Lineweaver-Burk plot."
    ),
    ports=(
        Port("S", ROLE_SUBSTRATE, 1.0),
        Port("P", ROLE_PRODUCT, 0.0),
        Port("E", ROLE_ENZYME, 1e-3),
        Port("I", ROLE_REGULATOR, 0.0, description="competitive inhibitor"),
    ),
    parameters=(
        MotifParameter("kcat", KIND_RATE_CONSTANT, 100.0, "1/s", table="kcat"),
        MotifParameter("Km", KIND_AFFINITY, 0.1, "mM", table="km"),
        MotifParameter("Ki", KIND_AFFINITY, 0.5, "mM", table="ki",
                       description="inhibitor dissociation constant"),
    ),
    reactions=(
        ReactionTemplate(
            "catalysis",
            reactants={"S": 1},
            products={"P": 1},
            rate_law="{kcat} * {E} * {S} / ({Km} * (1 + {I} / {Ki}) + {S})",
            modifiers=("E", "I"),
        ),
    ),
)

UNCOMPETITIVE_INHIBITION = Motif(
    name="uncompetitive_inhibition",
    summary="Catalysis with an inhibitor that binds only the ES complex.",
    basis=(
        "The inhibitor binds the enzyme-substrate complex rather than free "
        "enzyme, so it lowers apparent Vmax and apparent Km by the same "
        "factor -- the parallel lines on a Lineweaver-Burk plot that "
        "distinguish it from competitive inhibition."
    ),
    ports=(
        Port("S", ROLE_SUBSTRATE, 1.0),
        Port("P", ROLE_PRODUCT, 0.0),
        Port("E", ROLE_ENZYME, 1e-3),
        Port("I", ROLE_REGULATOR, 0.0),
    ),
    parameters=(
        MotifParameter("kcat", KIND_RATE_CONSTANT, 100.0, "1/s", table="kcat"),
        MotifParameter("Km", KIND_AFFINITY, 0.1, "mM", table="km"),
        MotifParameter("Ki", KIND_AFFINITY, 0.5, "mM", table="ki"),
    ),
    reactions=(
        ReactionTemplate(
            "catalysis",
            reactants={"S": 1},
            products={"P": 1},
            rate_law="{kcat} * {E} * {S} / ({Km} + {S} * (1 + {I} / {Ki}))",
            modifiers=("E", "I"),
        ),
    ),
)

SUBSTRATE_INHIBITION = Motif(
    name="substrate_inhibition",
    summary="Catalysis that slows down at high substrate.",
    basis=(
        "A second substrate molecule binds the ES complex non-productively, "
        "giving the characteristic rate curve that rises to a maximum and "
        "then falls. Ksi is the substrate concentration at which that "
        "second binding becomes significant; a large Ksi recovers ordinary "
        "Michaelis-Menten."
    ),
    ports=(
        Port("S", ROLE_SUBSTRATE, 1.0),
        Port("P", ROLE_PRODUCT, 0.0),
        Port("E", ROLE_ENZYME, 1e-3),
    ),
    parameters=(
        MotifParameter("kcat", KIND_RATE_CONSTANT, 100.0, "1/s", table="kcat"),
        MotifParameter("Km", KIND_AFFINITY, 0.1, "mM", table="km"),
        MotifParameter("Ksi", KIND_AFFINITY, 10.0, "mM", table="ki",
                       description="substrate-inhibition constant"),
    ),
    reactions=(
        ReactionTemplate(
            "catalysis",
            reactants={"S": 1},
            products={"P": 1},
            rate_law=(
                "{kcat} * {E} * {S} / ({Km} + {S} + {S} * {S} / {Ksi})"
            ),
            modifiers=("E",),
        ),
    ),
)


# ---------------------------------------------------------------------------
# Binding
# ---------------------------------------------------------------------------

REVERSIBLE_BINDING = Motif(
    name="reversible_binding",
    summary="Two molecules associating and dissociating.",
    basis=(
        "Mass action in both directions. Kd = koff / kon, so a measured Kd "
        "constrains the pair but not either rate alone -- which is why both "
        "are declared resolvable rather than one being derived from the "
        "other and a Kd."
    ),
    ports=(
        Port("A", ROLE_PARTNER, 1.0),
        Port("B", ROLE_PARTNER, 1.0),
        Port("AB", ROLE_COMPLEX, 0.0),
    ),
    parameters=(
        MotifParameter("kon", KIND_RATE_CONSTANT, 1.0, "1/(mM*s)",
                       description="association rate constant"),
        MotifParameter("koff", KIND_RATE_CONSTANT, 0.1, "1/s",
                       description="dissociation rate constant"),
    ),
    reactions=(
        ReactionTemplate("association", {"A": 1, "B": 1}, {"AB": 1},
                         "{kon} * {A} * {B}"),
        ReactionTemplate("dissociation", {"AB": 1}, {"A": 1, "B": 1},
                         "{koff} * {AB}"),
    ),
)

DIMERISATION = Motif(
    name="dimerisation",
    summary="A molecule binding a copy of itself.",
    basis=(
        "Two monomers to one dimer, so the forward rate is second order in "
        "the monomer. The stoichiometry is what makes the conservation law "
        "M + 2*D rather than M + D, which the network derives rather than "
        "being told."
    ),
    ports=(
        Port("M", ROLE_PARTNER, 1.0, description="monomer"),
        Port("D", ROLE_COMPLEX, 0.0, description="dimer"),
    ),
    parameters=(
        MotifParameter("kon", KIND_RATE_CONSTANT, 1.0, "1/(mM*s)"),
        MotifParameter("koff", KIND_RATE_CONSTANT, 0.1, "1/s"),
    ),
    reactions=(
        ReactionTemplate("dimerise", {"M": 2}, {"D": 1}, "{kon} * {M} * {M}"),
        ReactionTemplate("dissociate", {"D": 1}, {"M": 2}, "{koff} * {D}"),
    ),
)


# ---------------------------------------------------------------------------
# Covalent modification
# ---------------------------------------------------------------------------

PHOSPHORYLATION_CYCLE = Motif(
    name="phosphorylation_cycle",
    summary="A protein switched on by a kinase and off by a phosphatase.",
    basis=(
        "Two opposing Michaelis-Menten steps on the same protein -- the "
        "Goldbeter-Koshland cycle (1981). Its interest is that the "
        "steady-state fraction phosphorylated can be far more switch-like "
        "than either step alone when both enzymes are near saturation, which "
        "is the zero-order ultrasensitivity a cascade amplifies.\n\n"
        "        THE ZERO-ORDER CONDITION IS THE WHOLE OF IT, and it is "
        "checkable: BOTH converter enzymes must be saturated, with Km_kin "
        "and Km_pptase each far below the total protein X + Xp. Saturated, "
        "each arm runs at a rate that does not depend on its own substrate "
        "-- zero order in it, which is where the name comes from -- so a "
        "small change in the kinase-to-phosphatase ratio has nothing to "
        "push back against and the cycle swings from one end to the other. "
        "Outside that regime the switch is NOT SHARP AT ALL. With either Km "
        "above the total protein the response to the kinase/phosphatase "
        "ratio is hyperbolic, and a hyperbolic response needs an 81-fold "
        "change in that ratio to move the cycle from 10% to 90% "
        "phosphorylated -- the same 81 a non-cooperative binding curve "
        "needs, and no amplification whatsoever. Sharpness is therefore a "
        "joint property of the Km values AND the total protein, not of the "
        "mechanism, and a cycle drawn without checking them is not a switch."
        "\n\n"
        "        The zero-order limit is also where this motif's own "
        "derivation strains. Saturating both enzymes means a large fraction "
        "of the protein is sitting in enzyme-substrate complexes, and the "
        "quasi-steady-state form assumes exactly that fraction is "
        "negligible. The sharpness is real; the free-substrate bookkeeping "
        "is approximate, and a cycle pushed deep into zero order should be "
        "checked against a model with the complexes written out. "
        "`library_signaling.ULTRASENSITIVE_CYCLE` is a name bound to this "
        "same motif, not a second copy of it."
    ),
    ports=(
        Port("X", ROLE_SUBSTRATE, 1.0, description="unphosphorylated form"),
        Port("Xp", ROLE_PRODUCT, 0.0, description="phosphorylated form"),
        Port("kinase", ROLE_ENZYME, 1e-3),
        Port("phosphatase", ROLE_ENZYME, 1e-3),
    ),
    parameters=(
        MotifParameter("kcat_kin", KIND_RATE_CONSTANT, 10.0, "1/s", table="kcat",
                       description="kinase turnover number"),
        MotifParameter("Km_kin", KIND_AFFINITY, 0.1, "mM", table="km",
                       description="kinase affinity for the unphosphorylated form"),
        MotifParameter("kcat_pptase", KIND_RATE_CONSTANT, 10.0, "1/s", table="kcat",
                       description="phosphatase turnover number"),
        MotifParameter("Km_pptase", KIND_AFFINITY, 0.1, "mM", table="km",
                       description="phosphatase affinity for the phosphorylated form"),
    ),
    reactions=(
        ReactionTemplate(
            "phosphorylation", {"X": 1}, {"Xp": 1},
            "{kcat_kin} * {kinase} * {X} / ({Km_kin} + {X})",
            modifiers=("kinase",),
        ),
        ReactionTemplate(
            "dephosphorylation", {"Xp": 1}, {"X": 1},
            "{kcat_pptase} * {phosphatase} * {Xp} / ({Km_pptase} + {Xp})",
            modifiers=("phosphatase",),
        ),
    ),
)


# ---------------------------------------------------------------------------
# Gene expression
# ---------------------------------------------------------------------------

SYNTHESIS_DEGRADATION = Motif(
    name="synthesis_degradation",
    summary="A species made at a constant rate and removed first order.",
    basis=(
        "Constitutive expression with first-order turnover. Steady state is "
        "ks/kd and the approach to it has time constant 1/kd, so the "
        "degradation rate sets how fast the system can respond -- not the "
        "synthesis rate, which only sets where it lands."
    ),
    ports=(Port("X", ROLE_PRODUCT, 0.0),),
    parameters=(
        MotifParameter("ks", KIND_RATE_CONSTANT, 1.0, "mM/s",
                       description="zero-order synthesis rate"),
        MotifParameter("kd", KIND_RATE_CONSTANT, 0.1, "1/s",
                       description="first-order degradation rate constant"),
    ),
    reactions=(
        ReactionTemplate("synthesis", {}, {"X": 1}, "{ks}"),
        ReactionTemplate("degradation", {"X": 1}, {}, "{kd} * {X}"),
    ),
)

HILL_REPRESSION = Motif(
    name="hill_repression",
    summary="One species shutting off the synthesis of another.",
    basis=(
        "A Hill function with exponent n. n > 1 encodes cooperative binding "
        "of the repressor -- multiple operator sites, or an oligomeric "
        "repressor -- and is what makes the response sharp enough to build a "
        "switch or an oscillator out of. n is a modelling choice with a "
        "conventional value, not a measured constant, and is marked as such."
    ),
    ports=(
        Port("X", ROLE_PRODUCT, 0.0, description="the repressed species"),
        Port("R", ROLE_REGULATOR, 0.0, description="the repressor"),
    ),
    parameters=(
        #: ks and K are scaled TOGETHER (same factor) on purpose: the
        #: qualitative behaviour depends only on ks/kd/K in combination, so
        #: rescaling all three leaves the dynamics unchanged up to a scale
        #: factor. The unscaled pair (ks = 1 mM/s, K = 0.5 mM) gave an
        #: unrepressed steady state of ks/kd = 10 mM -- TWICE the ~5 mM of
        #: total protein in a cell, which `compose/predictions.py` correctly
        #: refused. These give a 2 mM steady state, inside the cell's
        #: capacity and still far above K for a sharp switch.
        MotifParameter("ks", KIND_RATE_CONSTANT, 0.2, "mM/s",
                       description="maximal synthesis rate, with no repressor"),
        MotifParameter("K", KIND_AFFINITY, 0.1, "mM",
                       description="repressor concentration for half repression"),
        MotifParameter("n", KIND_EXPONENT, 2.0, "dimensionless",
                       description="Hill coefficient; cooperativity"),
        MotifParameter("kd", KIND_RATE_CONSTANT, 0.1, "1/s"),
    ),
    reactions=(
        ReactionTemplate(
            "repressed_synthesis", {}, {"X": 1},
            "{ks} * {K}^{n} / ({K}^{n} + {R}^{n})",
            modifiers=("R",),
        ),
        ReactionTemplate("degradation", {"X": 1}, {}, "{kd} * {X}"),
    ),
)

HILL_ACTIVATION = Motif(
    name="hill_activation",
    summary="One species switching on the synthesis of another.",
    basis=(
        "The complement of Hill repression: synthesis rises with the "
        "activator rather than falling with a repressor. Same cooperativity "
        "argument for n."
    ),
    ports=(
        Port("X", ROLE_PRODUCT, 0.0),
        Port("A", ROLE_REGULATOR, 0.0, description="the activator"),
    ),
    parameters=(
        MotifParameter("ks", KIND_RATE_CONSTANT, 1.0, "mM/s"),
        MotifParameter("K", KIND_AFFINITY, 0.5, "mM"),
        MotifParameter("n", KIND_EXPONENT, 2.0, "dimensionless"),
        MotifParameter("kd", KIND_RATE_CONSTANT, 0.1, "1/s"),
    ),
    reactions=(
        ReactionTemplate(
            "activated_synthesis", {}, {"X": 1},
            "{ks} * {A}^{n} / ({K}^{n} + {A}^{n})",
            modifiers=("A",),
        ),
        ReactionTemplate("degradation", {"X": 1}, {}, "{kd} * {X}"),
    ),
)


# ---------------------------------------------------------------------------
# Open-system boundaries
# ---------------------------------------------------------------------------

CONSTANT_INFLOW = Motif(
    name="constant_inflow",
    summary="Something entering the system at a fixed rate.",
    basis=(
        "A zero-order source. This is what makes a system OPEN: with it, the "
        "network has no conservation law over the fed species, and a steady "
        "state can exist that is not equilibrium. Terrium derives that "
        "absence from the stoichiometry rather than being told."
    ),
    ports=(Port("S", ROLE_PRODUCT, 0.0),),
    parameters=(
        MotifParameter("v_in", KIND_RATE_CONSTANT, 1.0, "mM/s",
                       description="volumetric feed rate"),
    ),
    reactions=(ReactionTemplate("inflow", {}, {"S": 1}, "{v_in}"),),
)

FIRST_ORDER_OUTFLOW = Motif(
    name="first_order_outflow",
    summary="Something leaving at a rate proportional to its amount.",
    basis="Dilution or washout in a chemostat; first order in the species.",
    ports=(Port("S", ROLE_SUBSTRATE, 0.0),),
    parameters=(
        MotifParameter("k_out", KIND_RATE_CONSTANT, 0.1, "1/s"),
    ),
    reactions=(
        ReactionTemplate("outflow", {"S": 1}, {}, "{k_out} * {S}"),
    ),
)

MASS_ACTION_CONVERSION = Motif(
    name="mass_action_conversion",
    summary="A first-order conversion with no catalyst.",
    basis=(
        "Uncatalysed or pseudo-first-order conversion. Present so a "
        "composition can include a step nobody is claiming an enzyme for, "
        "rather than inventing an enzyme to satisfy a template."
    ),
    ports=(Port("A", ROLE_SUBSTRATE, 1.0), Port("B", ROLE_PRODUCT, 0.0)),
    parameters=(MotifParameter("k", KIND_RATE_CONSTANT, 1.0, "1/s"),),
    reactions=(
        ReactionTemplate("conversion", {"A": 1}, {"B": 1}, "{k} * {A}"),
    ),
)




# ---------------------------------------------------------------------------
# Multi-substrate enzymes
# ---------------------------------------------------------------------------
#
# Most enzymes take two substrates, and the two canonical mechanisms are
# distinguishable from steady-state kinetics alone -- which is why they are
# separate motifs rather than one with a switch. Their double-reciprocal
# plots differ in a way generations of biochemists have used to tell them
# apart, and a composition that picked the wrong one would fit data it
# should not.

ORDERED_BI_BI = Motif(
    name="ordered_bi_bi",
    summary="Two substrates binding in a fixed order before catalysis.",
    basis=(
        "Cleland's ordered sequential mechanism: A binds first, then B, and "
        "catalysis happens on the ternary complex. The KiA*Kmb term in the "
        "denominator is the signature -- it is the dissociation constant of "
        "the FIRST substrate, and it is why the double-reciprocal lines for "
        "an ordered mechanism intersect rather than run parallel. Typical of "
        "NAD-dependent dehydrogenases, where the cofactor binds first."
    ),
    ports=(
        Port("A", ROLE_SUBSTRATE, 1.0, description="first substrate to bind"),
        Port("B", ROLE_SUBSTRATE, 1.0, description="second substrate"),
        Port("P", ROLE_PRODUCT, 0.0),
        Port("E", ROLE_ENZYME, 1e-3),
    ),
    parameters=(
        MotifParameter("kcat", KIND_RATE_CONSTANT, 100.0, "1/s", table="kcat"),
        MotifParameter("Kma", KIND_AFFINITY, 0.1, "mM", table="km",
                       description="Michaelis constant for the first substrate"),
        MotifParameter("Kmb", KIND_AFFINITY, 0.1, "mM", table="km",
                       description="Michaelis constant for the second substrate"),
        MotifParameter("Kia", KIND_AFFINITY, 0.2, "mM", table="ki",
                       description="dissociation constant of the first substrate"),
    ),
    reactions=(
        ReactionTemplate(
            "catalysis", {"A": 1, "B": 1}, {"P": 1},
            "{kcat} * {E} * {A} * {B} / "
            "({Kia} * {Kmb} + {Kmb} * {A} + {Kma} * {B} + {A} * {B})",
            modifiers=("E",),
        ),
    ),
)

PING_PONG_BI_BI = Motif(
    name="ping_pong_bi_bi",
    summary="Two substrates, with the first product released before the second binds.",
    basis=(
        "Cleland's ping-pong mechanism: the enzyme is covalently modified by "
        "the first substrate, releases the first product, and only then binds "
        "the second. No ternary complex forms, so the KiA*Kmb term of the "
        "ordered mechanism is ABSENT -- which makes the double-reciprocal "
        "lines parallel rather than intersecting, and is how the two are "
        "told apart. Transaminases are the textbook case."
    ),
    ports=(
        Port("A", ROLE_SUBSTRATE, 1.0),
        Port("B", ROLE_SUBSTRATE, 1.0),
        Port("P", ROLE_PRODUCT, 0.0),
        Port("E", ROLE_ENZYME, 1e-3),
    ),
    parameters=(
        MotifParameter("kcat", KIND_RATE_CONSTANT, 100.0, "1/s", table="kcat"),
        MotifParameter("Kma", KIND_AFFINITY, 0.1, "mM", table="km"),
        MotifParameter("Kmb", KIND_AFFINITY, 0.1, "mM", table="km"),
    ),
    reactions=(
        ReactionTemplate(
            "catalysis", {"A": 1, "B": 1}, {"P": 1},
            "{kcat} * {E} * {A} * {B} / "
            "({Kmb} * {A} + {Kma} * {B} + {A} * {B})",
            modifiers=("E",),
        ),
    ),
)


# ---------------------------------------------------------------------------
# Reversibility and product effects
# ---------------------------------------------------------------------------

REVERSIBLE_CATALYSIS = Motif(
    name="reversible_catalysis",
    summary="An enzymatic step that runs both ways.",
    basis=(
        "The reversible Michaelis-Menten form. Every enzymatic reaction is "
        "reversible; the irreversible form is the approximation that holds "
        "while product is scarce, and it stops holding exactly when a "
        "pathway approaches equilibrium -- which is when a modeller most "
        "wants to know what happens. The Haldane relationship ties the four "
        "constants to the equilibrium constant, so they are not independent, "
        "and a set resolved separately should be checked against it. "
        "\n\n"
        "The relationship is stated here rather than merely named, because "
        "a reader told that a constraint exists still cannot check it. "
        "Setting the rate to zero and solving for P/S gives the ratio at "
        "equilibrium, which is by definition the equilibrium constant: "
        "\n\n"
        "    Keq = (kcat_f * Kmp) / (kcat_r * Kms)"
        "\n\n"
        "Keq is fixed by the reaction's standard free energy change, and a "
        "catalyst changes how fast equilibrium is reached and not where it "
        "is. So these four constants have three degrees of freedom and "
        "CANNOT BE RESOLVED INDEPENDENTLY: four values from four papers are "
        "three measurements and one accident, and a set that misses the "
        "relationship describes an enzyme moving its own equilibrium. "
        "`library_metabolic.check_haldane` is the check, and "
        "`library_metabolic.LINEAR_PATHWAY_SEGMENT` is the same rate law "
        "with the constraint substituted in, for chains where the error "
        "would compound step by step."
    ),
    ports=(
        Port("S", ROLE_SUBSTRATE, 1.0),
        Port("P", ROLE_PRODUCT, 0.0),
        Port("E", ROLE_ENZYME, 1e-3),
    ),
    parameters=(
        MotifParameter("kcat_f", KIND_RATE_CONSTANT, 100.0, "1/s", table="kcat",
                       description="forward turnover number"),
        MotifParameter("kcat_r", KIND_RATE_CONSTANT, 10.0, "1/s", table="kcat",
                       description="reverse turnover number"),
        MotifParameter("Kms", KIND_AFFINITY, 0.1, "mM", table="km"),
        MotifParameter("Kmp", KIND_AFFINITY, 0.5, "mM", table="km"),
    ),
    reactions=(
        ReactionTemplate(
            "net_catalysis", {"S": 1}, {"P": 1},
            "({kcat_f} * {E} * {S} / {Kms} - {kcat_r} * {E} * {P} / {Kmp}) / "
            "(1 + {S} / {Kms} + {P} / {Kmp})",
            modifiers=("E",),
        ),
    ),
)

PRODUCT_INHIBITION = Motif(
    name="product_inhibition",
    summary="A step slowed by its own product.",
    basis=(
        "The product competes with the substrate for the free enzyme, so it "
        "raises the apparent Km exactly as a competitive inhibitor does. "
        "Distinct from `reversible_catalysis`: here the reverse reaction is "
        "negligible and the product still binds, which is common when the "
        "product is structurally similar to the substrate."
    ),
    ports=(
        Port("S", ROLE_SUBSTRATE, 1.0),
        Port("P", ROLE_PRODUCT, 0.0),
        Port("E", ROLE_ENZYME, 1e-3),
    ),
    parameters=(
        MotifParameter("kcat", KIND_RATE_CONSTANT, 100.0, "1/s", table="kcat"),
        MotifParameter("Km", KIND_AFFINITY, 0.1, "mM", table="km"),
        MotifParameter("Kp", KIND_AFFINITY, 0.5, "mM", table="ki",
                       description="product dissociation constant"),
    ),
    reactions=(
        ReactionTemplate(
            "catalysis", {"S": 1}, {"P": 1},
            "{kcat} * {E} * {S} / ({Km} * (1 + {P} / {Kp}) + {S})",
            modifiers=("E",),
        ),
    ),
)


# ---------------------------------------------------------------------------
# More inhibition mechanisms
# ---------------------------------------------------------------------------

NONCOMPETITIVE_INHIBITION = Motif(
    name="noncompetitive_inhibition",
    summary="An inhibitor binding free enzyme and ES complex equally.",
    basis=(
        "The inhibitor binds a site other than the active site with the same "
        "affinity whether substrate is bound or not, so it lowers apparent "
        "Vmax and leaves apparent Km alone -- the mirror image of "
        "competitive inhibition, and the reason more substrate cannot "
        "rescue the rate."
    ),
    ports=(
        Port("S", ROLE_SUBSTRATE, 1.0),
        Port("P", ROLE_PRODUCT, 0.0),
        Port("E", ROLE_ENZYME, 1e-3),
        Port("I", ROLE_REGULATOR, 0.0),
    ),
    parameters=(
        MotifParameter("kcat", KIND_RATE_CONSTANT, 100.0, "1/s", table="kcat"),
        MotifParameter("Km", KIND_AFFINITY, 0.1, "mM", table="km"),
        MotifParameter("Ki", KIND_AFFINITY, 0.5, "mM", table="ki"),
    ),
    reactions=(
        ReactionTemplate(
            "catalysis", {"S": 1}, {"P": 1},
            "{kcat} * {E} * {S} / (({Km} + {S}) * (1 + {I} / {Ki}))",
            modifiers=("E", "I"),
        ),
    ),
)

MIXED_INHIBITION = Motif(
    name="mixed_inhibition",
    summary="An inhibitor with different affinities for enzyme and complex.",
    basis=(
        "The general case, of which competitive (Kiu -> infinity), "
        "uncompetitive (Kic -> infinity) and non-competitive (Kic = Kiu) are "
        "the limits. Two dissociation constants because there are two "
        "binding events, and reporting one would hide which limit the data "
        "actually supports."
    ),
    ports=(
        Port("S", ROLE_SUBSTRATE, 1.0),
        Port("P", ROLE_PRODUCT, 0.0),
        Port("E", ROLE_ENZYME, 1e-3),
        Port("I", ROLE_REGULATOR, 0.0),
    ),
    parameters=(
        MotifParameter("kcat", KIND_RATE_CONSTANT, 100.0, "1/s", table="kcat"),
        MotifParameter("Km", KIND_AFFINITY, 0.1, "mM", table="km"),
        MotifParameter("Kic", KIND_AFFINITY, 0.5, "mM", table="ki",
                       description="dissociation constant from free enzyme"),
        MotifParameter("Kiu", KIND_AFFINITY, 2.0, "mM", table="ki",
                       description="dissociation constant from the ES complex"),
    ),
    reactions=(
        ReactionTemplate(
            "catalysis", {"S": 1}, {"P": 1},
            "{kcat} * {E} * {S} / "
            "({Km} * (1 + {I} / {Kic}) + {S} * (1 + {I} / {Kiu}))",
            modifiers=("E", "I"),
        ),
    ),
)

COOPERATIVE_CATALYSIS = Motif(
    name="cooperative_catalysis",
    summary="An enzyme whose rate rises sigmoidally with substrate.",
    basis=(
        "The Hill form applied to catalysis rather than to binding. h > 1 "
        "means substrate binding at one site raises the affinity of the "
        "others, giving the sigmoid that makes an enzyme behave like a "
        "threshold detector. Phosphofructokinase is the canonical case, and "
        "the sigmoid is what lets glycolysis switch on sharply. h is a "
        "modelling choice, not a measured constant, and is marked as such. "
        "More precisely: h is a PHENOMENOLOGICAL fit and is NOT a subunit "
        "count. It is real-valued, routinely non-integer, bounded above by "
        "the number of binding sites and equal to that number only in the "
        "unreachable limit of all-or-none binding, and it moves with the "
        "effector concentration while the number of subunits does not. "
        "Haemoglobin has four sites and h near 2.8. Reading h as a site "
        "count turns a curve-fitting parameter into a structural claim "
        "about the protein, and is the commonest specific error made with "
        "this equation. That is also what separates this motif from a "
        "concerted two-state (Monod-Wyman-Changeux) model: this one has no "
        "mechanism to be wrong about, so it fits negative cooperativity "
        "(h < 1) as happily as positive, where a concerted model cannot "
        "produce h < 1 at all. It describes a curve, and it stops meaning "
        "anything wherever the curve is not sigmoid."
    ),
    ports=(
        Port("S", ROLE_SUBSTRATE, 1.0),
        Port("P", ROLE_PRODUCT, 0.0),
        Port("E", ROLE_ENZYME, 1e-3),
    ),
    parameters=(
        MotifParameter("kcat", KIND_RATE_CONSTANT, 100.0, "1/s", table="kcat"),
        MotifParameter("K", KIND_AFFINITY, 0.1, "mM", table="km",
                       description="substrate at half maximal rate"),
        MotifParameter("h", KIND_EXPONENT, 2.0, "dimensionless",
                       description="Hill coefficient"),
    ),
    reactions=(
        ReactionTemplate(
            "catalysis", {"S": 1}, {"P": 1},
            "{kcat} * {E} * {S}^{h} / ({K}^{h} + {S}^{h})",
            modifiers=("E",),
        ),
    ),
)


# ---------------------------------------------------------------------------
# Transport, turnover, autocatalysis
# ---------------------------------------------------------------------------

FACILITATED_TRANSPORT = Motif(
    name="facilitated_transport",
    summary="A carrier moving a solute across a boundary, saturably.",
    basis=(
        "A transporter is an enzyme whose product is the same molecule "
        "somewhere else, so it saturates the same way and is described by "
        "the same rate law. Modelled as two species -- outside and inside "
        "-- because that is what makes the gradient a state of the model "
        "rather than a parameter of it."
    ),
    ports=(
        Port("Out", ROLE_SUBSTRATE, 1.0, description="solute outside"),
        Port("In", ROLE_PRODUCT, 0.0, description="solute inside"),
        Port("T", ROLE_ENZYME, 1e-3, description="the transporter"),
    ),
    parameters=(
        MotifParameter("kcat", KIND_RATE_CONSTANT, 10.0, "1/s", table="kcat",
                       description="transport turnover number"),
        MotifParameter("Kt", KIND_AFFINITY, 0.5, "mM", table="km",
                       description="solute at half maximal transport"),
    ),
    reactions=(
        ReactionTemplate(
            "transport", {"Out": 1}, {"In": 1},
            "{kcat} * {T} * {Out} / ({Kt} + {Out})",
            modifiers=("T",),
        ),
    ),
)

SATURABLE_DEGRADATION = Motif(
    name="saturable_degradation",
    summary="Removal by machinery that can be swamped.",
    basis=(
        "First-order degradation assumes the protease is never saturated, "
        "which fails at high substrate -- and the failure matters, because a "
        "system whose removal saturates can accumulate without bound while "
        "the first-order model says it reaches a steady state. The "
        "Michaelis-Menten form is the honest one when the degrading "
        "machinery is finite."
    ),
    ports=(
        Port("X", ROLE_SUBSTRATE, 1.0),
        Port("D", ROLE_ENZYME, 1e-3, description="the degrading machinery"),
    ),
    parameters=(
        MotifParameter("kcat", KIND_RATE_CONSTANT, 10.0, "1/s", table="kcat"),
        MotifParameter("Kd_m", KIND_AFFINITY, 0.5, "mM", table="km"),
    ),
    reactions=(
        ReactionTemplate(
            "degradation", {"X": 1}, {},
            "{kcat} * {D} * {X} / ({Kd_m} + {X})",
            modifiers=("D",),
        ),
    ),
)

AUTOCATALYSIS = Motif(
    name="autocatalysis",
    summary="A product that catalyses its own formation.",
    basis=(
        "The simplest positive feedback there is: S + X -> 2X. It produces "
        "the sigmoid growth curve of an autocatalytic reaction, and it is "
        "the mechanism behind prion propagation and behind the "
        "trypsinogen-to-trypsin activation cascade. The stoichiometric 2 is "
        "load-bearing -- it is what makes the conservation law S + X rather "
        "than something that conserves nothing."
    ),
    ports=(
        Port("S", ROLE_SUBSTRATE, 1.0, description="precursor"),
        Port("X", ROLE_PRODUCT, 0.01, description="autocatalyst; needs a seed"),
    ),
    parameters=(
        MotifParameter("k", KIND_RATE_CONSTANT, 1.0, "1/(mM*s)"),
    ),
    reactions=(
        ReactionTemplate(
            "autocatalysis", {"S": 1, "X": 1}, {"X": 2}, "{k} * {S} * {X}",
        ),
    ),
)

COOPERATIVE_BINDING = Motif(
    name="cooperative_binding",
    summary="A ligand binding a multi-site receptor cooperatively.",
    basis=(
        "The Hill equation as Hill wrote it in 1910, for haemoglobin. h is "
        "not the number of sites -- it is a measure of cooperativity that "
        "cannot exceed the number of sites, and for haemoglobin's four sites "
        "it is about 2.8. Reporting h as a site count is a common and "
        "specific error."
    ),
    ports=(
        Port("L", ROLE_PARTNER, 1.0, description="free ligand"),
        Port("R", ROLE_PARTNER, 1.0, description="free receptor"),
        Port("LR", ROLE_COMPLEX, 0.0, description="occupied receptor"),
    ),
    parameters=(
        # `kon` is 1/s, not 1/(mM*s), because the Hill factor already
        # carries the ligand dependence. The first version of this law was
        # `kon * R * L * L^h / (Kh^h + L^h)` with kon in 1/(mM*s): it
        # BALANCED dimensionally, and it counted the ligand twice. A rate
        # law can be dimensionally perfect and biochemically wrong, and the
        # unit checker cannot tell the difference -- which is why the basis
        # of each motif is written out and not left to the equation.
        MotifParameter("kon", KIND_RATE_CONSTANT, 1.0, "1/s",
                       description="maximal binding rate, at saturating ligand"),
        MotifParameter("koff", KIND_RATE_CONSTANT, 0.1, "1/s"),
        MotifParameter("Kh", KIND_AFFINITY, 0.5, "mM",
                       description="ligand at half occupancy"),
        MotifParameter("h", KIND_EXPONENT, 2.8, "dimensionless",
                       description="Hill coefficient; not the site count"),
    ),
    reactions=(
        ReactionTemplate(
            "binding", {"L": 1, "R": 1}, {"LR": 1},
            "{kon} * {R} * {L}^{h} / ({Kh}^{h} + {L}^{h})",
            modifiers=(),
        ),
        ReactionTemplate(
            "release", {"LR": 1}, {"L": 1, "R": 1}, "{koff} * {LR}",
        ),
    ),
)

ZERO_ORDER_DEGRADATION = Motif(
    name="zero_order_degradation",
    summary="Removal at a constant rate, regardless of how much is there.",
    basis=(
        "The saturated limit of Michaelis-Menten removal. Included because "
        "it has a property first-order degradation does not: the "
        "concentration reaches zero in FINITE time and then the rate law is "
        "wrong, since it would drive the species negative. A model using it "
        "needs a floor, and saying so is more useful than omitting the motif."
    ),
    ports=(Port("X", ROLE_SUBSTRATE, 1.0),),
    parameters=(
        MotifParameter(
            "v_max", KIND_RATE_CONSTANT, 0.1, "mM/s",
            description=(
                "THE ONE LUMPED PARAMETER IN THIS LIBRARY, and it is lumped "
                "because the mechanism is. v_max is kcat times the enzyme "
                "concentration, and ADR 0013 is the rule that Terrium never "
                "resolves such a product: a paper reporting Vmax = 0.4 mM/s "
                "measured it at ITS enzyme concentration, and carrying that "
                "number into a model with a different one is wrong by "
                "whatever ratio separates them. Every other motif here "
                "writes kcat and the enzyme out separately for exactly that "
                "reason, which is what makes them resolvable. This one "
                "cannot: taking the saturated limit is what absorbed the "
                "enzyme, and a motif that named it again would not be "
                "zero-order removal. Resolvable from a paper only ALONGSIDE "
                "the enzyme concentration it was measured at; use "
                "catalytic_step if you have kcat"
            ),
        ),
    ),
    reactions=(
        ReactionTemplate("degradation", {"X": 1}, {}, "{v_max}"),
    ),
)


#: Every motif, by name. The single source the grammar and the builder read.
LIBRARY: Dict[str, Motif] = {
    motif.name: motif
    for motif in (
        CATALYTIC_STEP,
        COMPETITIVE_INHIBITION,
        UNCOMPETITIVE_INHIBITION,
        SUBSTRATE_INHIBITION,
        REVERSIBLE_BINDING,
        DIMERISATION,
        PHOSPHORYLATION_CYCLE,
        SYNTHESIS_DEGRADATION,
        HILL_REPRESSION,
        HILL_ACTIVATION,
        CONSTANT_INFLOW,
        FIRST_ORDER_OUTFLOW,
        MASS_ACTION_CONVERSION,
        ORDERED_BI_BI,
        PING_PONG_BI_BI,
        REVERSIBLE_CATALYSIS,
        PRODUCT_INHIBITION,
        NONCOMPETITIVE_INHIBITION,
        MIXED_INHIBITION,
        COOPERATIVE_CATALYSIS,
        FACILITATED_TRANSPORT,
        SATURABLE_DEGRADATION,
        AUTOCATALYSIS,
        COOPERATIVE_BINDING,
        ZERO_ORDER_DEGRADATION,
    )
}


def motif(name: str) -> Motif:
    try:
        return LIBRARY[name]
    except KeyError:
        raise KeyError(
            f"no motif named {name!r}. Available: {', '.join(sorted(LIBRARY))}"
        ) from None


__all__ = ["LIBRARY", "motif"] + [m.upper() for m in ()] + [
    "CATALYTIC_STEP", "COMPETITIVE_INHIBITION", "UNCOMPETITIVE_INHIBITION",
    "SUBSTRATE_INHIBITION", "REVERSIBLE_BINDING", "DIMERISATION",
    "PHOSPHORYLATION_CYCLE", "SYNTHESIS_DEGRADATION", "HILL_REPRESSION",
    "HILL_ACTIVATION", "CONSTANT_INFLOW", "FIRST_ORDER_OUTFLOW",
    "MASS_ACTION_CONVERSION", "ORDERED_BI_BI", "PING_PONG_BI_BI",
    "REVERSIBLE_CATALYSIS", "PRODUCT_INHIBITION",
    "NONCOMPETITIVE_INHIBITION", "MIXED_INHIBITION",
    "COOPERATIVE_CATALYSIS", "FACILITATED_TRANSPORT",
    "SATURABLE_DEGRADATION", "AUTOCATALYSIS", "COOPERATIVE_BINDING",
    "ZERO_ORDER_DEGRADATION",
]
