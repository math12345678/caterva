"""Signalling motifs: the shapes a network is built out of, not the pathways.

WHAT A SIGNALLING MOTIF IS FOR
------------------------------
`library.py` holds mechanisms -- Michaelis-Menten, mass action, a Hill term.
`library_expression.py` holds the machinery of a gene. Neither holds the
WIRING PATTERNS that decide what a signalling network computes, and the
wiring is where the interesting behaviour lives. A feed-forward loop is not
a new rate law; it is three ordinary rate laws connected in a particular
way, and the connection is what makes it adapt, or delay, or do neither.

That is also why they belong in a composition library rather than in a
catalogue. There is no "incoherent feed-forward loop" experiment to look up
constants for. There is a shape, and the shape has consequences that follow
from its structure regardless of whose numbers are in it -- which is
precisely the kind of claim Caterva can make honestly with placeholder
constants, and the kind it cannot make by inventing them.

WHAT WAS ACTUALLY MISSING, AND WHAT WAS NOT
-------------------------------------------
Seven motifs here are new. The eighth, `ULTRASENSITIVE_CYCLE`, is an ALIAS
for `library.PHOSPHORYLATION_CYCLE` and is deliberately not a second
definition.

The Goldbeter-Koshland zero-order ultrasensitive cycle IS the
phosphorylation cycle: two opposing Michaelis-Menten arms on one protein,
symbol for symbol the rate laws `library.py` already ships. Writing them
out again under a second name would put one mechanism in the registry
twice, which is the defect `library_enzymology.py` refuses at import time
and which this repository has paid for before -- four implementations of
Michaelis-Menten, and no way for a reader to tell which one ran.

What that motif was missing was not algebra. It was the CONDITION: the
sharp response appears only when both converter enzymes are saturated, and
outside that regime the cycle is not a switch at all. That sentence has
been added to the motif itself, in `library.py`, where the one copy lives.
`ULTRASENSITIVE_CYCLE` here is a name bound to that same object, for
callers who look for the mechanism under the name the literature uses, and
a test pins that it is the same object and not a copy.

NO LUMPED SYNTHESIS RATE
------------------------
Every production term here is written `k * G`, with `k` in 1/s and `G` a
SPECIES, never as a single `ks` in mM/s. `library_expression.py` made this
argument in full and it applies unchanged: `ks = k_tx * [gene]`, the gene
copy number is a scenario choice, and so a measured `ks` is a measurement
of somebody else's copy number. It is the lumped Vmax of ADR 0013 wearing
a promoter.

`library.HILL_ACTIVATION` and `library.HILL_REPRESSION` predate that
argument and still carry an mM/s `ks`. These motifs do not, and a test in
`test_compose_library_signaling.py` asserts that no parameter defined here
has the units of a lumped synthesis rate -- so the rule is enforced rather
than merely stated.

The `G` port is written as a gene because the feed-forward loops were
catalogued in transcription networks. For a post-translational loop it is
the amount of the enzyme that makes the output instead; the port has the
same shape and the same argument either way, and its description says so.

WHAT EVERY BASIS HERE HAS TO CARRY
----------------------------------
Three things, because a motif whose basis says only what it assumes is a
half-written motif:

  * the assumption that licenses the rate law;
  * the regime in which it FAILS, stated concretely enough to check;
  * the experimental signature that distinguishes this mechanism from the
    one a reader might have meant instead, where such a signature exists.

The third is the one that earns its keep. An incoherent feed-forward loop
and a plain repression both make the output fall; only the feed-forward
loop makes it rise first and come back. A bistable switch and a very steep
graded response give the same dose-response curve measured upward; only
bistability gives a different one measured downward. A model that cannot
tell a reader which experiment separates the two has told them less than
they needed.

EVERY DEFAULT HERE IS A PLACEHOLDER
-----------------------------------
Every numeric default below is illustrative and order-of-magnitude only.
None is a measurement, none is attributed to a paper, and the pipeline
treats every RESOLVABLE one as a quantity to go and find. Where a default
was chosen so the motif exhibits the behaviour it is named for -- the Hill
exponent of the oscillator is the clear case -- the description says so and
says that this is a property of the placeholder, not a claim about any
protein. A number with a citation it does not deserve is worse than a
number with none.

NOT REGISTERED IN THE GRAMMAR
-----------------------------
`SIGNALING_LIBRARY` is its own mapping and is not merged into
`library.LIBRARY`. `grammar.py` turns a phrase at the front door into a
composition, and a motif reachable by name with no phrase that reaches it
is a promise the front door does not keep. Adding the phrases is a grammar
change, and it belongs in the change that adds them -- alongside the
keyword-collision check that file's docstring asks for, since "coherent"
contains no trap but "feedback" and "feed-forward" both contain "feed".
"""

from __future__ import annotations

from typing import Dict, Tuple

try:
    from .motifs import (
        KIND_AFFINITY, KIND_EXPONENT, KIND_RATE_CONSTANT,
        Motif, MotifError, MotifParameter, Port, ReactionTemplate,
        ROLE_COMPLEX, ROLE_ENZYME, ROLE_PARTNER, ROLE_PRODUCT,
        ROLE_REGULATOR, ROLE_SUBSTRATE,
    )
    from .library import LIBRARY, PHOSPHORYLATION_CYCLE
except ImportError:  # pragma: no cover - flat import
    from motifs import (  # type: ignore[no-redef]
        KIND_AFFINITY, KIND_EXPONENT, KIND_RATE_CONSTANT,
        Motif, MotifError, MotifParameter, Port, ReactionTemplate,
        ROLE_COMPLEX, ROLE_ENZYME, ROLE_PARTNER, ROLE_PRODUCT,
        ROLE_REGULATOR, ROLE_SUBSTRATE,
    )
    from library import LIBRARY, PHOSPHORYLATION_CYCLE  # type: ignore[no-redef]


# ---------------------------------------------------------------------------
# Shared illustrative amounts
# ---------------------------------------------------------------------------

#: One gene copy in roughly a bacterial cell volume: 1 molecule in 1e-15 L
#: is 1.7e-9 M, so ~1e-6 mM. Arithmetic, not a citation -- and a scenario
#: choice either way, which is why it is a port default and not a parameter.
#:
#: Spelled out here rather than imported so this module stands on its own
#: with only `motifs` and `library` present, the way `grammar.py` assumes an
#: expansion library can be missing. The copy is kept honest by
#: `test_the_gene_copy_default_agrees_with_the_expression_library`, which
#: fails if the two ever drift.
SINGLE_COPY_GENE_MM = 1e-6

#: An illustrative signalling-protein pool, roughly a micromolar.
SIGNALLING_POOL_MM = 1e-3


# ---------------------------------------------------------------------------
# Feed-forward loops
# ---------------------------------------------------------------------------

INCOHERENT_FEEDFORWARD = Motif(
    name="incoherent_feedforward",
    summary=(
        "X activates Y and Z, and Y represses Z: the output pulses and "
        "returns toward its baseline."
    ),
    basis=(
        "The type-1 incoherent feed-forward loop, and the canonical "
        "adaptation motif. The two arms from X reach Z with opposite signs "
        "and at different speeds: the direct arm acts at once, the arm "
        "through Y only after Y has accumulated, so a step up in X drives Z "
        "up and then Y catches up and pushes it back down.\n\n"
        "        ADAPTATION IS EXACT ONLY IN A NAMED REGIME, and the regime "
        "is checkable. Write the steady states: Y settles at "
        "(k_y*Gy/d_y) * X/(Kxy + X) and Z at "
        "(k_z*Gz/d_z) * X/(Kxz + X) * Kyz^n/(Kyz^n + Y^n). For Z's "
        "dependence on X to cancel, three things must hold at once -- the "
        "activation arms unsaturated (X << Kxy and X << Kxz, so both are "
        "proportional to X), the repression arm saturated (Y >> Kyz, so it "
        "is proportional to 1/Y^n), and n = 1. Then Z settles at "
        "(k_z*Gz*Kyz*d_y*Kxy) / (d_z*Kxz*k_y*Gy), with no X in it at all: "
        "perfect adaptation, and a structural property of the wiring rather "
        "than of any constant's value. Away from that regime adaptation is "
        "PARTIAL -- the adapted level drifts with X roughly as X^(1-n) in "
        "the saturated-repression limit -- and a model that reports "
        "adaptation without saying which regime it is in has not said "
        "anything falsifiable.\n\n"
        "        The distinguishing signature is FOLD-CHANGE DETECTION. In "
        "that same regime the pulse height depends on the RATIO by which X "
        "stepped, not on the absolute step: going from x to 2x and from 2x "
        "to 4x give the same pulse. A plain repression, or a saturating "
        "activation, cannot do that, and stepping the input twice by the "
        "same factor from different starting levels is the experiment that "
        "separates them.\n\n"
        "        Two failures worth naming. The pulse needs the output to "
        "be FASTER than the repressor -- d_z well above d_y -- or Z tracks "
        "Y down as it rises and the pulse is a shoulder rather than a peak; "
        "the wiring is identical and the dynamics are not, so a diagram is "
        "not enough to predict a pulse. And the Hill term reaches exactly "
        "zero at large Y, which no real promoter does: a model of the "
        "adapted state built from this motif puts it lower than measurement "
        "will, and needs a basal production term composed alongside."
    ),
    ports=(
        Port(
            "X", ROLE_REGULATOR, 0.1,
            description=(
                "the input signal. Held constant by this motif -- nothing "
                "here consumes or produces it -- so a step input is a "
                "change to its initial amount, which is a scenario choice"
            ),
        ),
        Port(
            "Gy", ROLE_ENZYME, SINGLE_COPY_GENE_MM,
            description=(
                "the gene for Y, in copies per volume. Declared with the "
                "enzyme role because that is its mechanical part: it sets a "
                "rate and is neither consumed nor produced. For a "
                "post-translational loop this is the enzyme that makes Y "
                "instead, and the argument for it being a species is the same"
            ),
        ),
        Port("Y", ROLE_PRODUCT, 0.0, description="the repressor arm"),
        Port("Gz", ROLE_ENZYME, SINGLE_COPY_GENE_MM,
             description="the gene for Z"),
        Port("Z", ROLE_PRODUCT, 0.0, description="the output that adapts"),
    ),
    parameters=(
        MotifParameter(
            "k_y", KIND_RATE_CONSTANT, 1.0, "1/s", table=None,
            description=(
                "maximal production of Y per gene copy per second; "
                "illustrative placeholder"
            ),
        ),
        MotifParameter(
            "Kxy", KIND_AFFINITY, 1.0, "mM", table=None,
            description=(
                "input at which Y's production is half maximal. The "
                "adaptation regime is X << Kxy; illustrative placeholder"
            ),
        ),
        MotifParameter(
            "d_y", KIND_RATE_CONSTANT, 1e-3, "1/s", table=None,
            description=(
                "first-order removal of Y; illustrative placeholder. It "
                "sets how long the pulse lasts, since the pulse ends when Y "
                "arrives. Papers report a half-life: d = ln(2)/t_half"
            ),
        ),
        MotifParameter(
            "k_z", KIND_RATE_CONSTANT, 1.0, "1/s", table=None,
            description=(
                "maximal production of Z per gene copy per second; "
                "illustrative placeholder"
            ),
        ),
        MotifParameter(
            "Kxz", KIND_AFFINITY, 1.0, "mM", table=None,
            description=(
                "input at which Z's direct activation is half maximal. The "
                "adaptation regime is X << Kxz; illustrative placeholder"
            ),
        ),
        MotifParameter(
            "Kyz", KIND_AFFINITY, 1e-6, "mM", table=None,
            description=(
                "repressor concentration at half repression of Z. The "
                "adaptation regime is Y >> Kyz; illustrative placeholder. "
                "An operator occupancy constant, not an enzyme constant, so "
                "no enzyme table serves it"
            ),
        ),
        MotifParameter(
            "n", KIND_EXPONENT, 1.0, "dimensionless",
            description=(
                "Hill coefficient of the repression, chosen not measured. "
                "n = 1 is the value at which adaptation is EXACT rather "
                "than approximate, which is why the default is 1 here and 2 "
                "elsewhere in the libraries"
            ),
        ),
        MotifParameter(
            "d_z", KIND_RATE_CONSTANT, 0.05, "1/s", table=None,
            description=(
                "first-order removal of Z; illustrative placeholder. It "
                "sets how fast the pulse rises, and a pulse is only visible "
                "while d_z is well above d_y -- the default is fifty times "
                "d_y for exactly that reason"
            ),
        ),
    ),
    reactions=(
        ReactionTemplate(
            "y_synthesis", {}, {"Y": 1},
            "{k_y} * {Gy} * {X} / ({Kxy} + {X})",
            modifiers=("Gy", "X"),
        ),
        ReactionTemplate("y_removal", {"Y": 1}, {}, "{d_y} * {Y}"),
        ReactionTemplate(
            "z_synthesis", {}, {"Z": 1},
            "{k_z} * {Gz} * {X} / ({Kxz} + {X}) "
            "* {Kyz}^{n} / ({Kyz}^{n} + {Y}^{n})",
            modifiers=("Gz", "X", "Y"),
        ),
        ReactionTemplate("z_removal", {"Z": 1}, {}, "{d_z} * {Z}"),
    ),
)

COHERENT_FEEDFORWARD = Motif(
    name="coherent_feedforward",
    summary=(
        "X activates Y, and X and Y together activate Z: the output is "
        "delayed on the way up and immediate on the way down."
    ),
    basis=(
        "The type-1 coherent feed-forward loop with an AND gate at Z -- the "
        "sign-consistent counterpart of `incoherent_feedforward`, and the "
        "commonest feed-forward wiring in the transcription networks where "
        "these were catalogued (Mangan and Alon, PNAS 2003). Both arms from "
        "X are activating, so nothing pulls Z back down and it does not "
        "adapt; what the second arm buys is TIME.\n\n"
        "        It is a persistence detector. When X switches on, Z waits "
        "for Y to climb past Kyz -- a delay of about "
        "-ln(1 - Kyz/Y_ss)/d_y -- so a pulse of X shorter than that "
        "produces essentially no Z. Noise in the input is filtered out and "
        "a sustained signal is passed. When X switches off, the AND gate "
        "loses its X arm at once and Z stops immediately, with no wait at "
        "all.\n\n"
        "        That asymmetry IS the experimental signature, and it is "
        "what separates this motif from a plain cascade. A cascade delays "
        "both edges by the same amount; the coherent loop delays one. "
        "Measure the response time after switching the input on and after "
        "switching it off: equal means a chain, unequal means a "
        "feed-forward loop -- and which edge is delayed says which logic "
        "the promoter implements, because an OR gate at Z reverses it "
        "exactly (immediate on, delayed off). The wiring diagram is the "
        "same for AND and OR, so the gate cannot be read off the arrows and "
        "must come from the dynamics or from the promoter.\n\n"
        "        Where it fails: the filtering is bought with the delay, so "
        "a circuit that needs both a fast response and rejection of short "
        "inputs cannot get them here -- the two are the same number. And "
        "the AND gate is written as a product of two independent Hill "
        "terms, which assumes the two activators bind their sites without "
        "affecting each other. A promoter where one activator recruits the "
        "other is more switch-like than this product, and a promoter where "
        "they compete for overlapping sites is less."
    ),
    ports=(
        Port(
            "X", ROLE_REGULATOR, 0.1,
            description=(
                "the input signal, held constant by this motif; a step is a "
                "change to its initial amount"
            ),
        ),
        Port("Gy", ROLE_ENZYME, SINGLE_COPY_GENE_MM,
             description="the gene for Y (or the enzyme that makes it)"),
        Port("Y", ROLE_PRODUCT, 0.0, description="the slow arm"),
        Port("Gz", ROLE_ENZYME, SINGLE_COPY_GENE_MM,
             description="the gene for Z"),
        Port("Z", ROLE_PRODUCT, 0.0,
             description="the output, which lags rather than pulsing"),
    ),
    parameters=(
        MotifParameter(
            "k_y", KIND_RATE_CONSTANT, 1.0, "1/s", table=None,
            description=(
                "maximal production of Y per gene copy per second; "
                "illustrative placeholder"
            ),
        ),
        MotifParameter(
            "Kxy", KIND_AFFINITY, 0.05, "mM", table=None,
            description="input at half maximal Y production; illustrative placeholder",
        ),
        MotifParameter(
            "d_y", KIND_RATE_CONSTANT, 1e-3, "1/s", table=None,
            description=(
                "first-order removal of Y; illustrative placeholder. With "
                "Kxy and Kyz it sets the length of the delay, which is the "
                "quantity this motif exists to produce"
            ),
        ),
        MotifParameter(
            "k_z", KIND_RATE_CONSTANT, 1.0, "1/s", table=None,
            description="maximal production of Z per gene copy per second; illustrative placeholder",
        ),
        MotifParameter(
            "Kxz", KIND_AFFINITY, 0.05, "mM", table=None,
            description="input at half maximal activation of Z; illustrative placeholder",
        ),
        MotifParameter(
            "Kyz", KIND_AFFINITY, 4e-4, "mM", table=None,
            description=(
                "Y concentration at half maximal activation of Z. The "
                "threshold the slow arm has to climb past, so it is what "
                "makes the delay long or short; illustrative placeholder"
            ),
        ),
        MotifParameter(
            "n", KIND_EXPONENT, 2.0, "dimensionless",
            description=(
                "Hill coefficient shared by both arms of the AND gate; "
                "cooperativity, chosen not measured. A larger n makes the "
                "gate closer to a logical AND and the delay sharper-edged"
            ),
        ),
        MotifParameter(
            "d_z", KIND_RATE_CONSTANT, 1e-3, "1/s", table=None,
            description="first-order removal of Z; illustrative placeholder",
        ),
    ),
    reactions=(
        ReactionTemplate(
            "y_synthesis", {}, {"Y": 1},
            "{k_y} * {Gy} * {X}^{n} / ({Kxy}^{n} + {X}^{n})",
            modifiers=("Gy", "X"),
        ),
        ReactionTemplate("y_removal", {"Y": 1}, {}, "{d_y} * {Y}"),
        ReactionTemplate(
            "z_and_gate", {}, {"Z": 1},
            "{k_z} * {Gz} * {X}^{n} / ({Kxz}^{n} + {X}^{n}) "
            "* {Y}^{n} / ({Kyz}^{n} + {Y}^{n})",
            modifiers=("Gz", "X", "Y"),
        ),
        ReactionTemplate("z_removal", {"Z": 1}, {}, "{d_z} * {Z}"),
    ),
)


# ---------------------------------------------------------------------------
# Receptors and their transducers
# ---------------------------------------------------------------------------

TWO_COMPONENT_SYSTEM = Motif(
    name="two_component_system",
    summary=(
        "A sensor histidine kinase autophosphorylating and passing the "
        "phosphoryl group to a response regulator."
    ),
    basis=(
        "The bacterial workhorse. The sensor autophosphorylates on a "
        "histidine at a rate set by the stimulus, and the phosphoryl group "
        "is then transferred to an aspartate on the response regulator; "
        "phosphorylated regulator is the output. Phosphotransfer is written "
        "as a bimolecular mass-action step because that is what it is -- a "
        "collision between two proteins -- rather than as a "
        "Michaelis-Menten step, which would need a Km nobody measured for a "
        "complex that is not an enzyme-substrate pair.\n\n"
        "        ATP is a species, not a factor folded into k_auto, for the "
        "reason `library_enzymology.FUTILE_CYCLE` gives: a cost that cannot "
        "be starved cannot be shown to be real, and the whole point of this "
        "architecture is that it spends nucleotide to hold an output steady "
        "against a stimulus.\n\n"
        "        BIFUNCTIONALITY IS THE DESIGN, and it is why k_ph is here. "
        "Many sensors are also phosphatases for their own regulator, and "
        "the consequence is exact rather than qualitative. Set k_off to "
        "zero for a moment and write the two balances: the sensor's, "
        "k_auto*HK*f(S)*g(ATP) = k_tr*HKp*RR, and the regulator's, "
        "k_tr*HKp*RR = k_ph*HK*RRp. The phosphotransfer flux appears in "
        "both, so it cancels, and\n\n"
        "            RRp = k_auto * f(S) * g(ATP) / k_ph\n\n"
        "        which contains NEITHER total. The output is set by the "
        "stimulus and by a ratio of two activities on one molecule, and it "
        "does not move when the cell makes more sensor or more regulator. "
        "That is the robustness, and it is structural: it survives any "
        "value of k_tr and any expression level. A non-zero k_off is the "
        "leak that spoils it, replacing k_ph with (k_ph + k_off/HK) and "
        "reintroducing a dependence on the sensor -- which is small while "
        "k_off << k_ph*HK, and is the honest reason the default k_off here "
        "is well under k_ph times the default sensor amount.\n\n"
        "        Setting k_ph to zero recovers a monofunctional sensor, "
        "which is a perfectly real architecture and is NOT robust: the "
        "cancellation above needs a phosphatase term proportional to HK, "
        "and with only k_off left the output tracks how much regulator the "
        "cell happens to contain.\n\n"
        "        The signature follows directly, and it is a single "
        "experiment: overexpress the response regulator and measure "
        "phosphorylated regulator. If it rises in proportion, the sensor is "
        "monofunctional; if it barely moves, the sensor is bifunctional.\n\n"
        "        Two failures. Phosphotransfer is written irreversible and "
        "in one step, and it is neither: it goes through a sensor-regulator "
        "complex and it runs backwards when phosphorylated regulator is "
        "abundant, so this motif overstates the output at high stimulus. "
        "And there is exactly ONE pair here. A real cell has dozens sharing "
        "a nucleotide pool and, in principle, each other's phosphoryl "
        "groups; cross-talk between pairs -- and the phosphatase activity "
        "that is thought to suppress it -- cannot be expressed by a motif "
        "with one sensor in it, and needs two instances wired together."
    ),
    ports=(
        Port("S", ROLE_REGULATOR, 0.1,
             description="the stimulus the sensor responds to"),
        Port("HK", ROLE_SUBSTRATE, SIGNALLING_POOL_MM,
             description="the sensor histidine kinase, unphosphorylated"),
        Port("HKp", ROLE_PRODUCT, 0.0,
             description="the sensor, phosphorylated on its histidine"),
        Port("RR", ROLE_SUBSTRATE, 5 * SIGNALLING_POOL_MM,
             description="the response regulator, unphosphorylated"),
        Port("RRp", ROLE_PRODUCT, 0.0,
             description="the response regulator, phosphorylated; the output"),
        Port(
            "ATP", ROLE_SUBSTRATE, 3.0,
            description=(
                "nucleotide consumed once per autophosphorylation. An "
                "illustrative cellular-order amount and a scenario choice, "
                "not a measurement. Nothing here regenerates it, so a long "
                "run in a closed system reports exhaustion rather than "
                "balance -- compose `constant_inflow` onto this port for a "
                "cell held at a fixed energy charge"
            ),
        ),
        Port("ADP", ROLE_PRODUCT, 0.0),
        Port(
            "Pi", ROLE_PRODUCT, 0.0,
            description=(
                "inorganic phosphate released when the regulator is "
                "dephosphorylated; tracked so the hydrolysis the cycle pays "
                "for is visible in the stoichiometry rather than only in "
                "the ATP that vanished"
            ),
        ),
    ),
    parameters=(
        MotifParameter(
            "k_auto", KIND_RATE_CONSTANT, 0.05, "1/s", table=None,
            description=(
                "autophosphorylation turnover of the sensor at saturating "
                "stimulus and ATP; illustrative placeholder. With k_ph it "
                "fixes the output outright -- RRp settles at "
                "k_auto*f(S)*g(ATP)/k_ph -- so the default is chosen to put "
                "that below the default regulator pool. Above it the "
                "regulator is simply all phosphorylated and the motif has "
                "no dynamic range left to show"
            ),
        ),
        MotifParameter(
            "Ks", KIND_AFFINITY, 0.1, "mM", table=None,
            description=(
                "stimulus concentration at half maximal autophosphorylation. "
                "A property of the sensing domain, not an enzyme constant, "
                "so no enzyme table serves it; illustrative placeholder"
            ),
        ),
        MotifParameter(
            "Km_atp", KIND_AFFINITY, 0.1, "mM", table="km",
            description=(
                "sensor affinity for ATP. Separate from Ks because they are "
                "separate measurements on separate ligands, and one number "
                "standing for both would be unresolvable by construction; "
                "illustrative placeholder"
            ),
        ),
        MotifParameter(
            "k_tr", KIND_RATE_CONSTANT, 100.0, "1/(mM*s)", table=None,
            description=(
                "second-order phosphotransfer rate constant from "
                "phosphorylated sensor to regulator; illustrative "
                "placeholder. Second order because it is a collision, so "
                "the unit is 1/(mM*s) and not 1/s -- declaring it 1/s is "
                "the commonest single error in a hand-written kinetic model "
                "and is what the unit checker exists to catch"
            ),
        ),
        MotifParameter(
            "k_ph", KIND_RATE_CONSTANT, 10.0, "1/(mM*s)", table=None,
            description=(
                "second-order phosphatase rate constant of the "
                "UNphosphorylated sensor acting on phosphorylated "
                "regulator. Zero recovers a monofunctional sensor; "
                "illustrative placeholder"
            ),
        ),
        MotifParameter(
            "k_off", KIND_RATE_CONSTANT, 1e-3, "1/s", table=None,
            description=(
                "intrinsic autodephosphorylation of the phosphorylated "
                "regulator. An aspartyl-phosphate hydrolyses on its own, "
                "with lifetimes running from seconds to hours across "
                "regulators; illustrative placeholder"
            ),
        ),
    ),
    reactions=(
        ReactionTemplate(
            "autophosphorylation",
            {"HK": 1, "ATP": 1}, {"HKp": 1, "ADP": 1},
            "{k_auto} * {HK} * {S} / ({Ks} + {S}) "
            "* {ATP} / ({Km_atp} + {ATP})",
            modifiers=("S",),
        ),
        ReactionTemplate(
            "phosphotransfer",
            {"HKp": 1, "RR": 1}, {"HK": 1, "RRp": 1},
            "{k_tr} * {HKp} * {RR}",
        ),
        ReactionTemplate(
            "sensor_phosphatase",
            {"RRp": 1}, {"RR": 1, "Pi": 1},
            "{k_ph} * {HK} * {RRp}",
            modifiers=("HK",),
        ),
        ReactionTemplate(
            "autodephosphorylation",
            {"RRp": 1}, {"RR": 1, "Pi": 1},
            "{k_off} * {RRp}",
        ),
    ),
)

GPCR_ACTIVATION = Motif(
    name="gpcr_activation",
    summary=(
        "An agonist-occupied receptor catalysing the G protein's "
        "GDP-to-GTP exchange, with GTP hydrolysis returning it."
    ),
    basis=(
        "Ligand binds receptor by mass action; the occupied receptor is a "
        "nucleotide exchange factor for the heterotrimeric G protein, and "
        "the GTP-bound form is the active species. Deactivation is the "
        "intrinsic GTPase of the alpha subunit, accelerated by an RGS "
        "protein acting as a GTPase-activating protein.\n\n"
        "        The amplification is in the CATALYTIC step, not the "
        "binding step: one occupied receptor turns over many G proteins "
        "before the agonist leaves, so occupancy and response are different "
        "curves and the response saturates at an occupancy well below one. "
        "That is the whole content of 'spare receptors', and a model that "
        "wrote activation as proportional to occupancy would lose it.\n\n"
        "        k_basal is not decoration. Without it an empty receptor is "
        "silent, and constitutive activity -- and therefore inverse agonism "
        "-- becomes inexpressible: every inverse agonist would be reported "
        "as having no effect, which is not a small error but the loss of an "
        "entire pharmacological class. Setting it to zero is a modelling "
        "decision that should be made deliberately.\n\n"
        "        Three failures, each one a phenomenon this motif cannot "
        "produce. The heterotrimer is a single species, so the beta-gamma "
        "dimer -- itself a signalling molecule with its own effectors -- "
        "has nowhere to act. There is no receptor phosphorylation, arrestin "
        "recruitment or internalisation, so the decline in response under "
        "sustained agonist that every real GPCR shows will not appear, and "
        "a fitted decline would be attributed to the wrong step. And "
        "ligand binding is written independently of G-protein coupling, so "
        "there is no ternary complex and no GTP SHIFT: in a real "
        "radioligand experiment, adding GTP breaks the receptor-G protein "
        "complex and agonist affinity drops, which is the classic "
        "signature of precoupling. This motif denies that shift exists, so "
        "it cannot be fitted to a binding experiment that shows one."
    ),
    ports=(
        Port("L", ROLE_PARTNER, SIGNALLING_POOL_MM, description="the agonist"),
        Port("R", ROLE_PARTNER, 0.1 * SIGNALLING_POOL_MM,
             description="free receptor"),
        Port("LR", ROLE_COMPLEX, 0.0,
             description="agonist-occupied receptor; the exchange factor"),
        Port("G", ROLE_SUBSTRATE, SIGNALLING_POOL_MM,
             description="inactive heterotrimeric G protein, GDP-bound"),
        Port("Ga", ROLE_PRODUCT, 0.0,
             description="active alpha subunit, GTP-bound; the output"),
        Port(
            "RGS", ROLE_ENZYME, 0.0,
            description=(
                "GTPase-activating protein. Defaults to none present, so "
                "the motif starts with the intrinsic hydrolysis alone and a "
                "caller adds RGS deliberately rather than inheriting it"
            ),
        ),
    ),
    parameters=(
        MotifParameter(
            "kon", KIND_RATE_CONSTANT, 100.0, "1/(mM*s)", table=None,
            description="agonist association rate constant; illustrative placeholder",
        ),
        MotifParameter(
            "koff", KIND_RATE_CONSTANT, 0.1, "1/s", table=None,
            description=(
                "agonist dissociation rate constant; illustrative "
                "placeholder. Kd = koff/kon, so a measured Kd constrains "
                "the pair and neither rate alone -- which is why both are "
                "declared resolvable rather than one derived from a Kd"
            ),
        ),
        MotifParameter(
            "k_ex", KIND_RATE_CONSTANT, 1.0, "1/s", table=None,
            description=(
                "nucleotide exchange turnover of one occupied receptor at "
                "saturating G protein; illustrative placeholder"
            ),
        ),
        MotifParameter(
            "Km_g", KIND_AFFINITY, 1e-3, "mM", table=None,
            description=(
                "G protein concentration at which exchange is half maximal; "
                "illustrative placeholder"
            ),
        ),
        MotifParameter(
            "k_basal", KIND_RATE_CONSTANT, 1e-4, "1/s", table=None,
            description=(
                "agonist-independent exchange. Sets the constitutive "
                "activity, which is what an inverse agonist reduces; "
                "illustrative placeholder"
            ),
        ),
        MotifParameter(
            "k_hyd", KIND_RATE_CONSTANT, 0.02, "1/s", table=None,
            description=(
                "intrinsic GTP hydrolysis by the alpha subunit; "
                "illustrative placeholder. With k_ex it sets how much "
                "active G protein one occupied receptor sustains"
            ),
        ),
        MotifParameter(
            "k_gap", KIND_RATE_CONSTANT, 1000.0, "1/(mM*s)", table=None,
            description=(
                "second-order acceleration of hydrolysis by RGS; "
                "illustrative placeholder"
            ),
        ),
    ),
    reactions=(
        ReactionTemplate(
            "agonist_binding", {"L": 1, "R": 1}, {"LR": 1},
            "{kon} * {L} * {R}",
        ),
        ReactionTemplate(
            "agonist_release", {"LR": 1}, {"L": 1, "R": 1},
            "{koff} * {LR}",
        ),
        ReactionTemplate(
            "nucleotide_exchange", {"G": 1}, {"Ga": 1},
            "{k_ex} * {LR} * {G} / ({Km_g} + {G})",
            modifiers=("LR",),
        ),
        ReactionTemplate(
            "basal_exchange", {"G": 1}, {"Ga": 1},
            "{k_basal} * {G}",
        ),
        ReactionTemplate(
            "intrinsic_hydrolysis", {"Ga": 1}, {"G": 1},
            "{k_hyd} * {Ga}",
        ),
        ReactionTemplate(
            "rgs_accelerated_hydrolysis", {"Ga": 1}, {"G": 1},
            "{k_gap} * {RGS} * {Ga}",
            modifiers=("RGS",),
        ),
    ),
)


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

SCAFFOLD_ASSEMBLY = Motif(
    name="scaffold_assembly",
    summary=(
        "A scaffold binding two partners, whose ternary complex is the "
        "active species -- and which too much scaffold pulls apart."
    ),
    basis=(
        "Two INDEPENDENT binding sites on one scaffold. Independent is a "
        "real assumption and it does two things: it means each site's kon "
        "and koff are the same whether the other site is occupied, and it "
        "means the four-step cycle (free scaffold to singly loaded to "
        "ternary and back the other way) satisfies detailed balance "
        "automatically. Allosteric coupling between the sites would need a "
        "fifth constant, and that constant would have to be measured rather "
        "than assumed -- which is why it is not here.\n\n"
        "        THE SCAFFOLD EFFECT IS NOT MONOTONIC, and a model that "
        "misses that gives the wrong advice. Signal comes from the TERNARY "
        "complex. With the partners limiting, adding scaffold beyond the "
        "optimum spreads them onto SEPARATE scaffolds, and a scaffold "
        "carrying one partner is inert -- it has sequestered that partner "
        "and delivered nothing. In the large-scaffold limit the ternary "
        "complex falls roughly as one over total scaffold. This is the "
        "prozone or hook effect, familiar from precipitin curves and from "
        "sandwich immunoassays at high antibody, and here it is called "
        "combinatorial inhibition. Its practical consequence: "
        "'overexpress the scaffold to boost the pathway' can silently "
        "reduce signalling, and a scaffold KNOCKDOWN can raise it in a cell "
        "that was already past the optimum. Neither result is a "
        "contradiction and both have been read as one.\n\n"
        "        The optimum is not a property of the scaffold alone. It "
        "sits near the partner concentrations and moves when they move, so "
        "a scaffold amount tuned in one cell type is not the right amount "
        "in another, and the only way to find it is a titration -- which "
        "makes the biphasic curve itself the experimental signature. A "
        "monotonic titration means the partners were not limiting, and the "
        "measurement has not yet reached the regime the motif is about.\n\n"
        "        Where it fails: this models PROXIMITY and nothing else. "
        "kcat here is the same kcat the free kinase has, so a scaffold that "
        "allosterically activates its client is not described, and adding "
        "that needs a second kcat with a measurement behind it. Binding is "
        "also assumed fast relative to catalysis; a scaffold that is "
        "assembled and disassembled as part of the signal breaks that, and "
        "then the transient matters more than the equilibrium this motif "
        "settles into."
    ),
    ports=(
        Port("Sc", ROLE_PARTNER, SIGNALLING_POOL_MM,
             description="free scaffold"),
        Port("A", ROLE_PARTNER, SIGNALLING_POOL_MM,
             description="free first partner, e.g. the upstream kinase"),
        Port("B", ROLE_PARTNER, SIGNALLING_POOL_MM,
             description="free second partner, e.g. its substrate kinase"),
        Port("ScA", ROLE_COMPLEX, 0.0,
             description="scaffold carrying A alone; inert, and a sink for A"),
        Port("ScB", ROLE_COMPLEX, 0.0,
             description="scaffold carrying B alone; inert, and a sink for B"),
        Port("ScAB", ROLE_COMPLEX, 0.0,
             description="the ternary complex; the only active species"),
        Port("X", ROLE_SUBSTRATE, 1.0,
             description="the downstream substrate the assembled pair acts on"),
        Port("Xp", ROLE_PRODUCT, 0.0, description="modified substrate; the output"),
    ),
    parameters=(
        MotifParameter(
            "kon_a", KIND_RATE_CONSTANT, 100.0, "1/(mM*s)", table=None,
            description="association of A with a scaffold site; illustrative placeholder",
        ),
        MotifParameter(
            "koff_a", KIND_RATE_CONSTANT, 0.01, "1/s", table=None,
            description=(
                "dissociation of A from a scaffold site; illustrative "
                "placeholder. Kd_a = koff_a/kon_a, and the prozone appears "
                "only once the partners are above that Kd"
            ),
        ),
        MotifParameter(
            "kon_b", KIND_RATE_CONSTANT, 100.0, "1/(mM*s)", table=None,
            description="association of B with a scaffold site; illustrative placeholder",
        ),
        MotifParameter(
            "koff_b", KIND_RATE_CONSTANT, 0.01, "1/s", table=None,
            description="dissociation of B from a scaffold site; illustrative placeholder",
        ),
        MotifParameter(
            "kcat", KIND_RATE_CONSTANT, 10.0, "1/s", table="kcat",
            description=(
                "turnover of the assembled pair on the downstream "
                "substrate; illustrative placeholder. The same turnover the "
                "unscaffolded enzyme has -- see the basis"
            ),
        ),
        MotifParameter(
            "Km", KIND_AFFINITY, 0.1, "mM", table="km",
            description=(
                "downstream substrate at half maximal turnover; "
                "illustrative placeholder"
            ),
        ),
    ),
    reactions=(
        ReactionTemplate("bind_a_to_free", {"Sc": 1, "A": 1}, {"ScA": 1},
                         "{kon_a} * {Sc} * {A}"),
        ReactionTemplate("release_a_from_free", {"ScA": 1}, {"Sc": 1, "A": 1},
                         "{koff_a} * {ScA}"),
        ReactionTemplate("bind_b_to_free", {"Sc": 1, "B": 1}, {"ScB": 1},
                         "{kon_b} * {Sc} * {B}"),
        ReactionTemplate("release_b_from_free", {"ScB": 1}, {"Sc": 1, "B": 1},
                         "{koff_b} * {ScB}"),
        # The same two constants again on the loaded scaffold. Reusing them
        # is what "independent sites" MEANS, and it is also what makes the
        # cycle thermodynamically consistent: the product of equilibrium
        # constants around it is exactly one, with no fifth parameter to
        # resolve and no way for a typo to open a perpetual-motion loop.
        ReactionTemplate("bind_b_to_loaded", {"ScA": 1, "B": 1}, {"ScAB": 1},
                         "{kon_b} * {ScA} * {B}"),
        ReactionTemplate("release_b_from_loaded", {"ScAB": 1}, {"ScA": 1, "B": 1},
                         "{koff_b} * {ScAB}"),
        ReactionTemplate("bind_a_to_loaded", {"ScB": 1, "A": 1}, {"ScAB": 1},
                         "{kon_a} * {ScB} * {A}"),
        ReactionTemplate("release_a_from_loaded", {"ScAB": 1}, {"ScB": 1, "A": 1},
                         "{koff_a} * {ScAB}"),
        ReactionTemplate(
            "scaffolded_catalysis", {"X": 1}, {"Xp": 1},
            "{kcat} * {ScAB} * {X} / ({Km} + {X})",
            modifiers=("ScAB",),
        ),
    ),
)


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------

NEGATIVE_FEEDBACK_OSCILLATOR = Motif(
    name="negative_feedback_oscillator",
    summary=(
        "A three-stage chain whose last product represses the first step: "
        "the general form behind many biological clocks."
    ),
    basis=(
        "Goodwin's oscillator. A message is made, translated into a "
        "cytoplasmic protein, converted into an active repressor -- by "
        "nuclear import, or by a modification that has to be completed -- "
        "and the repressor shuts off the message. Negative feedback alone "
        "does not oscillate; it needs DELAY, and here the delay is bought "
        "by the two intermediate stages.\n\n"
        "        THE THRESHOLD IS DERIVABLE AND IT IS SEVERE. Each "
        "first-order stage contributes at most 90 degrees of phase lag, so "
        "three stages reach 180 degrees only asymptotically -- with equal "
        "decay constants d they reach it at frequency sqrt(3)*d, and at "
        "that frequency each stage has attenuated the signal to one half. "
        "The loop therefore returns one eighth of what it sent, and a limit "
        "cycle needs it to return more than all of it. So the repression's "
        "logarithmic gain must exceed 8; the logarithmic gain of a Hill "
        "term with exponent n is at most n; hence n > 8 for three equal "
        "stages. Two stages cannot oscillate at any n whatsoever. More "
        "stages, or unequal ones, lower the requirement.\n\n"
        "        That threshold is why this motif is honest about what it "
        "is. A Hill coefficient above 8 for a single repressor is not "
        "plausible, so a real clock is not running on cooperativity: it "
        "buys phase lag from explicit delay -- ordered multi-site "
        "phosphorylation, nuclear import and export, transcript processing "
        "-- and from degradation that saturates, which steepens the "
        "feedback without any cooperativity at all. The default n here is "
        "set above the threshold so that the motif does what its name says; "
        "that is a property of a chosen placeholder, and it is not a claim "
        "about any repressor. Lower it to 2 and this model does not "
        "oscillate -- it settles -- and that is the correct behaviour, not "
        "a defect.\n\n"
        "        The signature is the PHASE ORDERING: message peaks first, "
        "cytoplasmic protein next, active repressor last, with the lags set "
        "by the stage time constants. A system merely following an external "
        "rhythm shows no such internal ordering, and a relaxation "
        "oscillator built on positive feedback shows a fast rise and a slow "
        "fall rather than a roughly symmetric one. The period of a "
        "delayed-negative-feedback clock is set mainly by the total delay, "
        "so it is far less sensitive to the synthesis constants than the "
        "amplitude is -- and a model whose period moves strongly with a "
        "synthesis rate is telling you the delay is not where you thought."
    ),
    ports=(
        Port("G", ROLE_ENZYME, SINGLE_COPY_GENE_MM,
             description="the clock gene, in copies per volume"),
        Port("M", ROLE_PRODUCT, 0.0, description="the transcript"),
        Port("Pc", ROLE_PRODUCT, 0.0,
             description="the protein as made, not yet able to repress"),
        Port("Pn", ROLE_PRODUCT, 0.0,
             description="the active repressor; the last stage of the delay"),
    ),
    parameters=(
        MotifParameter(
            "k_tx", KIND_RATE_CONSTANT, 0.01, "1/s", table=None,
            description=(
                "transcription initiations per gene copy per second with "
                "the operator free; illustrative placeholder"
            ),
        ),
        MotifParameter(
            "K", KIND_AFFINITY, 1e-4, "mM", table=None,
            description=(
                "active repressor at half repression; illustrative "
                "placeholder. An operator occupancy constant, not an enzyme "
                "constant"
            ),
        ),
        MotifParameter(
            "n", KIND_EXPONENT, 9.0, "dimensionless",
            description=(
                "Hill coefficient of the repression, chosen not measured. "
                "Set above the Goodwin threshold of 8 so this three-stage "
                "loop oscillates rather than damping -- see the basis. A "
                "cooperativity of 9 is not plausible for a single "
                "repressor, and treating this default as anything but a "
                "placeholder that makes the motif demonstrate itself would "
                "be a claim nobody measured"
            ),
        ),
        MotifParameter(
            "d_m", KIND_RATE_CONSTANT, 5e-3, "1/s", table=None,
            description=(
                "transcript decay constant; illustrative placeholder. "
                "d = ln(2)/t_half when a paper reports a half-life, and "
                "dropping the ln(2) is a 30% error that reads as a "
                "plausible answer"
            ),
        ),
        MotifParameter(
            "k_tl", KIND_RATE_CONSTANT, 0.1, "1/s", table=None,
            description="proteins per transcript per second; illustrative placeholder",
        ),
        MotifParameter(
            "d_c", KIND_RATE_CONSTANT, 5e-3, "1/s", table=None,
            description=(
                "removal of the cytoplasmic protein; illustrative placeholder"
            ),
        ),
        MotifParameter(
            "k_in", KIND_RATE_CONSTANT, 5e-3, "1/s", table=None,
            description=(
                "conversion of the cytoplasmic protein into the active "
                "repressor -- import, or the last step of a required "
                "modification. This is the stage that supplies the delay; "
                "illustrative placeholder"
            ),
        ),
        MotifParameter(
            "d_n", KIND_RATE_CONSTANT, 5e-3, "1/s", table=None,
            description="removal of the active repressor; illustrative placeholder",
        ),
    ),
    reactions=(
        ReactionTemplate(
            "repressed_transcription", {}, {"M": 1},
            "{k_tx} * {G} * {K}^{n} / ({K}^{n} + {Pn}^{n})",
            modifiers=("G", "Pn"),
        ),
        ReactionTemplate("mrna_decay", {"M": 1}, {}, "{d_m} * {M}"),
        ReactionTemplate(
            "translation", {}, {"Pc": 1}, "{k_tl} * {M}", modifiers=("M",),
        ),
        ReactionTemplate("cytoplasmic_turnover", {"Pc": 1}, {}, "{d_c} * {Pc}"),
        ReactionTemplate("activation", {"Pc": 1}, {"Pn": 1}, "{k_in} * {Pc}"),
        ReactionTemplate("repressor_turnover", {"Pn": 1}, {}, "{d_n} * {Pn}"),
    ),
)

BISTABLE_POSITIVE_FEEDBACK = Motif(
    name="bistable_positive_feedback",
    summary=(
        "A protein that cooperatively drives its own production, with a "
        "basal leak and first-order removal: two stable levels."
    ),
    basis=(
        "Positive feedback with cooperativity. Production is a sigmoid in "
        "the protein and removal is a straight line through the origin, and "
        "bistability is exactly the statement that the two curves cross "
        "three times -- low stable, middle unstable, high stable.\n\n"
        "        n > 1 IS NECESSARY AND NOT SUFFICIENT. A sigmoid can still "
        "sit entirely above or entirely below the removal line: the "
        "threshold K has to lie inside the range the protein can actually "
        "reach (below k_tx*G/d_x, the fully-induced level), and the basal "
        "term has to be small enough that the low crossing falls well below "
        "K. Miss either and the model is monostable at n = 4 as readily as "
        "at n = 1, so 'it has cooperative positive feedback' is not a "
        "demonstration of bistability -- finding three crossings is.\n\n"
        "        THE BASAL TERM IS LOAD-BEARING. With k_basal at zero, X = "
        "0 is an exact fixed point and the OFF state is an absorbing state "
        "rather than a low steady level: the system can never switch on by "
        "itself, and the model reports zero for something every real "
        "promoter leaks. Setting k_basal to zero changes what kind of "
        "object the OFF state is, which is a bigger change than it looks.\n\n"
        "        THE SIGNATURE IS HYSTERESIS, and only a two-directional "
        "experiment finds it. Ramp the input up and the system switches at "
        "one level; ramp it back down and it falls off at a LOWER one, and "
        "the width of that gap is the observable. A merely ultrasensitive "
        "response -- steep, but single-valued -- has no gap at all, and a "
        "dose-response measured in one direction cannot tell the two apart. "
        "It must also be measured in SINGLE CELLS: a population of cells "
        "that each switch abruptly at a slightly different input averages "
        "into a smooth graded curve, and reading that average as a graded "
        "response is the specific way this has been got wrong.\n\n"
        "        Where it fails: one species and no delay, so this can be "
        "bistable and cannot oscillate. Couple a real switch to slow "
        "negative feedback and it becomes a relaxation oscillator -- the "
        "shape behind the cell cycle -- and this motif has nowhere to put "
        "the slow arm. Compose it with `negative_feedback_oscillator` "
        "rather than expecting it here."
    ),
    ports=(
        Port("G", ROLE_ENZYME, SINGLE_COPY_GENE_MM,
             description="the gene, in copies per volume"),
        Port(
            "X", ROLE_PRODUCT, 0.0,
            description=(
                "the protein, which is also its own activator. Its STARTING "
                "amount decides which stable state a run lands in, so it is "
                "not an inert default -- it is the initial condition the "
                "bistability is about"
            ),
        ),
    ),
    parameters=(
        MotifParameter(
            "k_basal", KIND_RATE_CONSTANT, 1e-4, "1/s", table=None,
            description=(
                "leaky production per gene copy per second with no "
                "activator bound; illustrative placeholder. Not optional -- "
                "see the basis"
            ),
        ),
        MotifParameter(
            "k_tx", KIND_RATE_CONSTANT, 0.02, "1/s", table=None,
            description=(
                "additional production per gene copy per second at "
                "saturating activator; illustrative placeholder"
            ),
        ),
        MotifParameter(
            "K", KIND_AFFINITY, 5e-6, "mM", table=None,
            description=(
                "own-protein concentration at half maximal autoactivation; "
                "illustrative placeholder. It must lie below k_tx*G/d_x for "
                "bistability to be possible at all"
            ),
        ),
        MotifParameter(
            "n", KIND_EXPONENT, 2.0, "dimensionless",
            description=(
                "Hill coefficient of the autoactivation; cooperativity, "
                "chosen not measured. n > 1 is required and is not "
                "sufficient"
            ),
        ),
        MotifParameter(
            "d_x", KIND_RATE_CONSTANT, 1e-3, "1/s", table=None,
            description=(
                "first-order removal, degradation and dilution together; "
                "illustrative placeholder. It is the SLOPE of the straight "
                "line the sigmoid has to cross three times, so it is as "
                "much a bistability parameter as n is"
            ),
        ),
    ),
    reactions=(
        ReactionTemplate(
            "basal_synthesis", {}, {"X": 1}, "{k_basal} * {G}",
            modifiers=("G",),
        ),
        ReactionTemplate(
            "autoactivated_synthesis", {}, {"X": 1},
            "{k_tx} * {G} * {X}^{n} / ({K}^{n} + {X}^{n})",
            modifiers=("G", "X"),
        ),
        ReactionTemplate("removal", {"X": 1}, {}, "{d_x} * {X}"),
    ),
)


# ---------------------------------------------------------------------------
# The alias, and the registry
# ---------------------------------------------------------------------------

#: The Goldbeter-Koshland zero-order ultrasensitive cycle.
#:
#: Bound to the SAME object as `library.PHOSPHORYLATION_CYCLE`, not to a
#: copy: `ULTRASENSITIVE_CYCLE is PHOSPHORYLATION_CYCLE` holds, and a test
#: pins that it does. The rate laws are identical symbol for symbol, so a
#: second definition would be a second answer to a question that already
#: had one -- see the module docstring. What the motif was missing was the
#: zero-order CONDITION, and that sentence has been added to the motif
#: itself in `library.py`, where the one copy lives.
ULTRASENSITIVE_CYCLE = PHOSPHORYLATION_CYCLE

#: Names callers reach for that are not the registry's own. Explicit,
#: because a lookup that silently guessed at near-misses would eventually
#: hand back the wrong mechanism for a typo.
ALIASES: Dict[str, str] = {
    "ultrasensitive_cycle": PHOSPHORYLATION_CYCLE.name,
    "goldbeter_koshland": PHOSPHORYLATION_CYCLE.name,
}

#: The motifs this module DEFINES. Seven, not eight: see the module
#: docstring for why the ultrasensitive cycle is an alias.
SIGNALING_LIBRARY: Dict[str, Motif] = {
    motif_.name: motif_
    for motif_ in (
        INCOHERENT_FEEDFORWARD,
        COHERENT_FEEDFORWARD,
        TWO_COMPONENT_SYSTEM,
        GPCR_ACTIVATION,
        SCAFFOLD_ASSEMBLY,
        NEGATIVE_FEEDBACK_OSCILLATOR,
        BISTABLE_POSITIVE_FEEDBACK,
    )
}


def _refuse_duplicates() -> None:
    """Fail at import if this module redefines something already defined.

    A refusal rather than a merge policy, copied deliberately from
    `library_enzymology.py`. `{**LIBRARY, **SIGNALING_LIBRARY}` resolves a
    collision by picking one, which is how two rate laws for one mechanism
    coexist for a year with no way for a reader to tell which one ran.
    There is no correct winner here, so there is no silent choice.

    The sibling expansion libraries are checked too, when they are present.
    `grammar.py` treats every expansion library as possibly absent from a
    checkout, so their absence must not break this import -- but when they
    ARE here, a name colliding with one of them is exactly as bad as a name
    colliding with the core, and checking only the core would have found
    half the problem.
    """
    known: Dict[str, str] = {name: "library.py" for name in LIBRARY}

    for module_name, attribute in (
        ("library_expression", "EXPRESSION_LIBRARY"),
        ("library_enzymology", "ENZYMOLOGY_LIBRARY"),
    ):
        registry = None
        for spelling in (f"caterva.compose.{module_name}", module_name):
            try:
                module = __import__(spelling, fromlist=["*"])
            except ImportError:
                continue
            registry = getattr(module, attribute, None)
            break
        for name in registry or {}:
            known.setdefault(name, f"{module_name}.py")

    collisions = sorted(set(known) & set(SIGNALING_LIBRARY))
    if collisions:
        raise MotifError(
            "library_signaling redefines "
            + ", ".join(f"{name!r} (already in {known[name]})" for name in collisions)
            + ". Two rate laws for one mechanism is two answers to one "
            "question, and merging would pick one of them without saying "
            "so. Re-export the existing motif, or change the existing one "
            "in place -- do not add a second copy."
        )


_refuse_duplicates()


def signaling_motif(name: str) -> Motif:
    """Look a signalling motif up by name, following the alias table.

    Refuses with the available names rather than returning None, for the
    reason every refusal in this package is written out: a caller who
    mistyped `coherant_feedforward` needs to see `coherent_feedforward` in
    the message, and a caller who wanted a mechanism nobody has written
    needs to be told that rather than handed a plausible neighbour. An
    incoherent loop returned for a coherent one would simulate perfectly
    and answer the opposite question.
    """
    resolved = ALIASES.get(name, name)
    if resolved in SIGNALING_LIBRARY:
        return SIGNALING_LIBRARY[resolved]
    if resolved in LIBRARY:
        # Reached only through an alias -- `ultrasensitive_cycle` resolves
        # to a motif that lives in `library.py`. Returning it is the point
        # of the alias; silently failing here would make the alias a name
        # that resolves to nothing.
        return LIBRARY[resolved]
    raise KeyError(
        f"no signalling motif named {name!r}. Available: "
        f"{', '.join(sorted(SIGNALING_LIBRARY))}"
        + (f". Aliases: {', '.join(sorted(ALIASES))}" if ALIASES else "")
    )


__all__ = [
    # defined here
    "INCOHERENT_FEEDFORWARD",
    "COHERENT_FEEDFORWARD",
    "TWO_COMPONENT_SYSTEM",
    "GPCR_ACTIVATION",
    "SCAFFOLD_ASSEMBLY",
    "NEGATIVE_FEEDBACK_OSCILLATOR",
    "BISTABLE_POSITIVE_FEEDBACK",
    # re-exported from library.py, not redefined
    "ULTRASENSITIVE_CYCLE",
    # registry
    "ALIASES",
    "SIGNALING_LIBRARY",
    "signaling_motif",
    # illustrative amounts
    "SINGLE_COPY_GENE_MM",
    "SIGNALLING_POOL_MM",
]
