"""Gene expression, written out in two stages with the DNA as a species.

WHY THIS IS A SEPARATE FILE AND NOT FOUR MORE ENTRIES IN library.py
-------------------------------------------------------------------
`library.py` reaches gene expression through `synthesis_degradation`,
`hill_repression` and `hill_activation`. All three write production as a
zero-order term whose constant `ks` is in mM/s. That constant is the Vmax of
gene expression, and it is unresolvable for exactly the reason Vmax is
(ADR 0013):

    ks = k_tx * [gene]

`k_tx` is transcription initiations per promoter per second, a property of
the promoter and the polymerase that somebody can measure. `[gene]` is a
scenario choice -- one chromosomal copy, or a plasmid at fifty. The two are
multiplied together into `ks`, so no paper can supply it: a measured `ks`
is a measurement of somebody else's copy number.

Every motif here writes the gene out as a SPECIES, so transcription is

    k_tx * G

and the lumped quantity is gone rather than worked around. This is the
same move `catalytic_step` makes with `kcat * E * S / (Km + S)`, applied to
the one place in the library that had not had it made.

WHY TWO STAGES
--------------
DNA -> mRNA -> protein is not a longer way of writing DNA -> protein. The
one-step model is the limit in which the message equilibrates instantly,
and the message does not: a bacterial transcript turns over in minutes and
its protein in tens of minutes to hours. The one-step model therefore gets
the RESPONSE TIME wrong by that ratio, and response time is most of what
anyone builds a gene-circuit model to ask about. It also has nowhere to put
a knockdown -- an siRNA, an RNase -- because it has no mRNA to remove.

The cost of the second stage is one more state variable and two more rate
constants. The benefit is that both constants are things a paper reports.

NOTHING HERE HAS A DATABASE TABLE
----------------------------------
BRENDA holds enzyme constants. Transcription initiation rates, translation
rates, and mRNA and protein turnover rates are not enzyme constants, and
BRENDA does not hold them: they are per-promoter, per-transcript and
per-strain, and they come out of specific papers or out of nothing. Every
such parameter here passes `table=None`, which makes
`MotifParameter.__post_init__` append the note that it is resolvable only
from a paper. "Searched and not found" and "never searched" are different
sentences, and a reader of the gap list is entitled to which one applies.

The two protease constants are the exception and do carry tables: a
protease is an enzyme and its kcat and Km are enzyme constants.

WHAT A RESOLVER SHOULD KNOW ABOUT THESE UNITS
----------------------------------------------
Papers report mRNA and protein stability as HALF-LIVES, in minutes. The
motifs want first-order rate constants, in 1/s. The conversion is
`d = ln(2) / t_half`, and it is stated on each parameter's description
rather than left for whoever wires up the resolver, because reading a
half-life into a rate-constant slot is off by a factor of ln 2 -- 30%,
which is small enough to look like a plausible answer.

THESE MODELS RUN FOUR ORDERS BELOW THE REST OF THE LIBRARY
-----------------------------------------------------------
Enzymology happens at millimolar. Gene expression happens at nanomolar: a
single-copy gene is about 1e-6 mM and its message a few times that. The
motifs are still written in the library's mM, because a composition has ONE
concentration unit and mixing them is the error `unit_findings` exists to
catch -- but two of `analysis.py`'s tolerances are ABSOLUTE, and at this
scale that matters:

    RESIDUAL_TOLERANCE       1e-9    a single-copy gene's largest flux is
                                     about k_tx*G = 1e-8 mM/s, one order of
                                     magnitude above the floor
    STATE_DISTINCT_TOLERANCE 1e-6    two steady states of a message closer
                                     together than this are reported as one

Measured, on `autoregulated_gene` at these defaults, against the exact root
of the cubic the model reduces to:

    analytic root                    1.7055336431300678e-4 mM
    what `analyse` converges to      1.7053827003915816e-4 mM
    relative gap                     8.9e-5
    that point's residual            5.6e-13

The root find did not stop early by its own measure -- 5.6e-13 is three
orders inside the acceptance gate. The state is still wrong in its fifth
digit, because dM/dt changes by only 2.2e-5 per unit of P at this scale, so
a small absolute residual buys little relative accuracy. The linear
`two_stage_expression` agrees with its closed form to 1e-6; anything with
feedback in it should not be expected to.

Two consequences for a reader. A bistable gene circuit whose two message
levels differ by less than a nanomolar will be reported as having one state
rather than two. And `FixedPoint.residual` is the number to read, not the
classification alone -- it is carried for exactly this reason.
"""

from __future__ import annotations

from typing import Dict

try:
    from .motifs import (
        KIND_AFFINITY, KIND_EXPONENT, KIND_RATE_CONSTANT,
        Motif, MotifParameter, Port, ReactionTemplate,
        ROLE_ENZYME, ROLE_PRODUCT, ROLE_REGULATOR, ROLE_SUBSTRATE,
    )
except ImportError:  # pragma: no cover - flat import
    from motifs import (  # type: ignore[no-redef]
        KIND_AFFINITY, KIND_EXPONENT, KIND_RATE_CONSTANT,
        Motif, MotifParameter, Port, ReactionTemplate,
        ROLE_ENZYME, ROLE_PRODUCT, ROLE_REGULATOR, ROLE_SUBSTRATE,
    )


# ---------------------------------------------------------------------------
# Shared illustrative defaults
# ---------------------------------------------------------------------------
#
# Every number below is a PLACEHOLDER. It is order-of-magnitude plausible
# for a bacterium so that a composed model integrates and can be looked at
# before anything is resolved, and it is not a measurement of anything. The
# pipeline treats a resolvable parameter's default as a quantity to go and
# find; these are chosen to be obviously round rather than obviously
# precise, so that a number surviving into a report is visible as one that
# was never resolved.

#: One gene copy in roughly a bacterial cell volume: 1 molecule in 1e-15 L
#: is 1.7e-9 M, so ~1e-6 mM. Arithmetic, not a citation -- and a scenario
#: choice either way, which is why it is a port default and not a parameter.
SINGLE_COPY_GENE_MM = 1e-6

#: A ribosome pool, illustrative. Same arithmetic, several thousand copies.
RIBOSOME_POOL_MM = 1e-2

#: A protease pool, illustrative.
PROTEASE_POOL_MM = 1e-3


# ---------------------------------------------------------------------------
# Promoters
# ---------------------------------------------------------------------------

CONSTITUTIVE_PROMOTER = Motif(
    name="constitutive_promoter",
    summary="A promoter transcribing at a fixed rate per gene copy.",
    basis=(
        "Transcription initiation is the rate-limiting step and the promoter "
        "is never saturated, so the rate is first order in the gene and "
        "independent of everything else. The gene is a modifier, not a "
        "reactant: a template is read without being consumed, which is what "
        "makes the transcription rate constant in time rather than decaying "
        "as the template runs out. Fails when RNA polymerase is the limiting "
        "resource -- several strong promoters in one cell draw on one "
        "polymerase pool, and this motif, instantiated once per promoter, "
        "gives each of them the whole pool and so overpredicts the total."
    ),
    ports=(
        Port("G", ROLE_ENZYME, SINGLE_COPY_GENE_MM,
             description=(
                 "the gene, in copies per volume. Declared with the enzyme "
                 "role because that is its mechanical part: it sets the rate "
                 "and is neither consumed nor produced"
             )),
        Port("M", ROLE_PRODUCT, 0.0, description="the transcript"),
    ),
    parameters=(
        MotifParameter(
            "k_tx", KIND_RATE_CONSTANT, 0.01, "1/s", table=None,
            description=(
                "transcription initiations per gene copy per second; "
                "illustrative placeholder"
            ),
        ),
    ),
    reactions=(
        ReactionTemplate(
            "transcription", {}, {"M": 1}, "{k_tx} * {G}", modifiers=("G",),
        ),
    ),
)

REPRESSED_PROMOTER = Motif(
    name="repressed_promoter",
    summary="A promoter whose transcription a repressor shuts off.",
    basis=(
        "A Hill term multiplying the constitutive rate. It assumes the "
        "repressor equilibrates with its operator far faster than the "
        "promoter fires, so the fraction of time the operator is free is a "
        "function of the current repressor concentration alone. n > 1 "
        "encodes cooperativity -- several operators, or an oligomeric "
        "repressor -- and it is a modelling choice with a conventional "
        "value, not a measured constant. Fails in two places worth naming: "
        "the term goes to ZERO at high repressor, and no real promoter does "
        "(measured repression is hundreds of fold, not infinite), so a model "
        "of the OFF state built from this motif underestimates it and needs "
        "a basal term; and at one or two repressor molecules per cell the "
        "equilibrium occupancy this assumes is not what the promoter sees."
    ),
    ports=(
        Port("G", ROLE_ENZYME, SINGLE_COPY_GENE_MM, description="the gene"),
        Port("M", ROLE_PRODUCT, 0.0, description="the transcript"),
        Port("R", ROLE_REGULATOR, 0.0, description="the repressor"),
    ),
    parameters=(
        MotifParameter(
            "k_tx", KIND_RATE_CONSTANT, 0.01, "1/s", table=None,
            description=(
                "transcription initiations per gene copy per second with the "
                "operator free; illustrative placeholder"
            ),
        ),
        MotifParameter(
            "K", KIND_AFFINITY, 1e-4, "mM", table=None,
            description=(
                "repressor concentration at half repression; illustrative "
                "placeholder. Not a BRENDA quantity -- it is an operator "
                "occupancy constant, not an enzyme constant"
            ),
        ),
        MotifParameter(
            "n", KIND_EXPONENT, 2.0, "dimensionless",
            description="Hill coefficient; cooperativity, chosen not measured",
        ),
    ),
    reactions=(
        ReactionTemplate(
            "repressed_transcription", {}, {"M": 1},
            "{k_tx} * {G} * {K}^{n} / ({K}^{n} + {R}^{n})",
            modifiers=("G", "R"),
        ),
    ),
)

ACTIVATED_PROMOTER = Motif(
    name="activated_promoter",
    summary="A promoter an activator switches on.",
    basis=(
        "The complement of `repressed_promoter`: transcription rises with "
        "the activator instead of falling with a repressor, on the same "
        "fast-equilibrium assumption and with the same argument for n. "
        "Fails at the other end: the term is exactly zero with no activator, "
        "and a real activated promoter leaks. A circuit whose interest is "
        "its OFF state -- most of them -- needs a basal transcription term "
        "composed alongside this one, and `constitutive_promoter` bound to "
        "the same gene and transcript is that term."
    ),
    ports=(
        Port("G", ROLE_ENZYME, SINGLE_COPY_GENE_MM, description="the gene"),
        Port("M", ROLE_PRODUCT, 0.0, description="the transcript"),
        Port("A", ROLE_REGULATOR, 0.0, description="the activator"),
    ),
    parameters=(
        MotifParameter(
            "k_tx", KIND_RATE_CONSTANT, 0.01, "1/s", table=None,
            description=(
                "transcription initiations per gene copy per second at "
                "saturating activator; illustrative placeholder"
            ),
        ),
        MotifParameter(
            "K", KIND_AFFINITY, 1e-4, "mM", table=None,
            description=(
                "activator concentration at half maximal transcription; "
                "illustrative placeholder"
            ),
        ),
        MotifParameter(
            "n", KIND_EXPONENT, 2.0, "dimensionless",
            description="Hill coefficient; cooperativity, chosen not measured",
        ),
    ),
    reactions=(
        ReactionTemplate(
            "activated_transcription", {}, {"M": 1},
            "{k_tx} * {G} * {A}^{n} / ({K}^{n} + {A}^{n})",
            modifiers=("G", "A"),
        ),
    ),
)


# ---------------------------------------------------------------------------
# Translation and turnover
# ---------------------------------------------------------------------------

TRANSLATION = Motif(
    name="translation",
    summary="Protein made from a message by a finite pool of ribosomes.",
    basis=(
        "The ribosome is the enzyme and the message is its substrate -- one "
        "it reads without consuming, which is why the transcript is a "
        "modifier and the stoichiometry does not remove it. Saturation is in "
        "the message: below Km_tl the ribosome pool is idle and protein "
        "output is proportional to transcript, above it the pool is "
        "committed and more transcript buys nothing. That crossover is the "
        "whole reason to write translation this way rather than as k_tl * M, "
        "and it is where a strong overexpression construct actually sits. "
        "Fails when several different messages are composed against "
        "SEPARATE ribosome ports: each instance then assumes the entire pool "
        "for itself and the model produces more protein than the cell has "
        "ribosomes to make. Bind every instance's R port to one species -- "
        "see `compete` in builder.py -- and the competition falls out of the "
        "shared pool rather than being written into a rate law."
    ),
    ports=(
        Port("M", ROLE_SUBSTRATE, 0.0,
             description="the transcript; read, not consumed"),
        Port("P", ROLE_PRODUCT, 0.0, description="the protein"),
        Port("R", ROLE_ENZYME, RIBOSOME_POOL_MM,
             description="free ribosomes; a scenario choice, not a constant"),
    ),
    parameters=(
        MotifParameter(
            "kcat_tl", KIND_RATE_CONSTANT, 0.05, "1/s", table=None,
            description=(
                "completed proteins per ribosome per second on this "
                "message; illustrative placeholder. A property of the "
                "TRANSCRIPT as much as of the ribosome, since it falls with "
                "the length of the coding sequence -- which is why no "
                "enzyme table serves it"
            ),
        ),
        MotifParameter(
            "Km_tl", KIND_AFFINITY, 1e-3, "mM", table=None,
            description=(
                "transcript concentration at which the ribosome pool is "
                "half committed; illustrative placeholder"
            ),
        ),
    ),
    reactions=(
        ReactionTemplate(
            "translation", {}, {"P": 1},
            "{kcat_tl} * {R} * {M} / ({Km_tl} + {M})",
            modifiers=("R", "M"),
        ),
    ),
)

MRNA_DEGRADATION = Motif(
    name="mrna_degradation",
    summary="A transcript decaying first order.",
    basis=(
        "Exponential decay: a message's chance of being cut in the next "
        "second does not depend on how long it has already survived, which "
        "holds when the degradation machinery is in excess and attacks the "
        "message at random. It is what sets the response time of the whole "
        "gene -- the steady state is fixed by k_tx*G/d_m, but the time to "
        "reach it is 1/d_m and nothing else. Fails where decay is "
        "age-dependent: a eukaryotic message deadenylates before it is "
        "degraded, so its survival curve has a shoulder and a single "
        "exponential fitted to it is wrong at early times in the direction "
        "that matters, predicting protein sooner than it appears."
    ),
    ports=(
        Port("M", ROLE_SUBSTRATE, 0.0, description="the transcript"),
    ),
    parameters=(
        MotifParameter(
            "d_m", KIND_RATE_CONSTANT, 0.005, "1/s", table=None,
            description=(
                "first-order decay constant of the transcript; illustrative "
                "placeholder. Papers report a HALF-LIFE in minutes: "
                "d_m = ln(2) / t_half, and dropping the ln(2) is a 30% "
                "error that reads as a plausible answer"
            ),
        ),
    ),
    reactions=(
        ReactionTemplate("mrna_decay", {"M": 1}, {}, "{d_m} * {M}"),
    ),
)

PROTEIN_DEGRADATION_TAGGED = Motif(
    name="protein_degradation_tagged",
    summary="A degron-tagged protein removed by a protease, and by growth.",
    basis=(
        "Two removal routes that are not the same shape, which is the point "
        "of the motif. Proteolysis by a tagged-substrate protease "
        "(ClpXP on an ssrA tag, the proteasome on a ubiquitinated "
        "substrate) is Michaelis-Menten in the protein and SATURABLE: past "
        "Km the machinery is fully occupied and removal stops rising, so a "
        "system whose first-order model says it reaches a steady state can "
        "in fact accumulate without bound. Dilution by growth is first order "
        "and never saturates -- it is not degradation at all, it is the same "
        "protein spread through more cell -- and for a stable protein it is "
        "usually the larger of the two. A model with only the protease term "
        "makes a stable protein immortal; one with only a first-order term "
        "makes an overloaded protease look infinite. "
        "Fails when several different tagged proteins share one protease: "
        "each instance of this motif assumes the whole pool for itself, so "
        "the model clears more protein than the cell has protease to clear, "
        "and the queueing that makes inducing one substrate slow another's "
        "removal is absent entirely. Bind every instance's Prot port to one "
        "species and that competition falls out of the shared pool instead "
        "of being written into a rate law. "
        "Do not compose this onto a species that already carries the "
        "d_p term of `two_stage_expression`, or the protein is removed "
        "twice. This motif replaces that term; it does not supplement it."
    ),
    ports=(
        Port("P", ROLE_SUBSTRATE, 0.0, description="the tagged protein"),
        Port("Prot", ROLE_ENZYME, PROTEASE_POOL_MM,
             description="the protease; a finite pool, hence saturable"),
    ),
    parameters=(
        MotifParameter(
            "kcat_deg", KIND_RATE_CONSTANT, 1.0, "1/s", table="kcat",
            description=(
                "protease turnover number on the tagged substrate; "
                "illustrative placeholder. A protease IS an enzyme, so "
                "unlike the transcription constants here this one has a "
                "table to be asked"
            ),
        ),
        MotifParameter(
            "Km_deg", KIND_AFFINITY, 1e-3, "mM", table="km",
            description=(
                "tagged protein at half maximal degradation; illustrative "
                "placeholder"
            ),
        ),
        MotifParameter(
            "mu", KIND_RATE_CONSTANT, 3e-4, "1/s", table=None,
            description=(
                "specific growth rate, which dilutes the protein; "
                "illustrative placeholder. Set by the strain and the medium "
                "rather than by the molecule, so a value taken from a paper "
                "carries that paper's growth conditions with it and the "
                "model inherits them"
            ),
        ),
    ),
    reactions=(
        ReactionTemplate(
            "proteolysis", {"P": 1}, {},
            "{kcat_deg} * {Prot} * {P} / ({Km_deg} + {P})",
            modifiers=("Prot",),
        ),
        ReactionTemplate("dilution", {"P": 1}, {}, "{mu} * {P}"),
    ),
)


# ---------------------------------------------------------------------------
# The whole gene
# ---------------------------------------------------------------------------

TWO_STAGE_EXPRESSION = Motif(
    name="two_stage_expression",
    summary="DNA -> mRNA -> protein, with both stages' turnover separate.",
    basis=(
        "The standard two-stage model. Transcription is first order in the "
        "gene, translation first order in the message, and both products "
        "decay first order with constants of their own. Its content is that "
        "the two stages have DIFFERENT lifetimes: the steady state is "
        "(k_tx*G/d_m) for the message and (k_tl/d_p) times that for the "
        "protein, so the levels multiply while the response times do not -- "
        "the protein follows the slower of 1/d_m and 1/d_p, which for a "
        "stable protein in a growing cell is the division time regardless "
        "of how fast the message turns over. "
        "Translation is written k_tl * M, the unsaturated limit of "
        "`translation`. That is the assumption that fails first: it holds "
        "while the message is scarce enough that ribosomes are idle, and a "
        "strongly induced construct is not, so an overexpression model "
        "should compose `translation` instead and make the ribosome pool "
        "explicit. Transcription assumes the promoter is unregulated; "
        "`repressed_promoter` and `activated_promoter` are that term with a "
        "Hill factor on it."
    ),
    ports=(
        Port("G", ROLE_ENZYME, SINGLE_COPY_GENE_MM,
             description=(
                 "the gene, in copies per volume -- a scenario choice "
                 "(chromosomal single copy, or a plasmid at fifty), which is "
                 "exactly why it is here as a species rather than "
                 "multiplied into a lumped synthesis rate"
             )),
        Port("M", ROLE_PRODUCT, 0.0, description="the transcript"),
        Port("P", ROLE_PRODUCT, 0.0, description="the protein"),
    ),
    parameters=(
        MotifParameter(
            "k_tx", KIND_RATE_CONSTANT, 0.01, "1/s", table=None,
            description=(
                "transcription initiations per gene copy per second; "
                "illustrative placeholder"
            ),
        ),
        MotifParameter(
            "k_tl", KIND_RATE_CONSTANT, 0.1, "1/s", table=None,
            description=(
                "proteins per transcript per second, in the ribosome-rich "
                "limit; illustrative placeholder"
            ),
        ),
        MotifParameter(
            "d_m", KIND_RATE_CONSTANT, 0.005, "1/s", table=None,
            description=(
                "transcript decay constant; illustrative placeholder. "
                "d_m = ln(2) / t_half when a paper reports a half-life"
            ),
        ),
        MotifParameter(
            "d_p", KIND_RATE_CONSTANT, 3e-4, "1/s", table=None,
            description=(
                "protein removal constant, degradation and dilution "
                "together; illustrative placeholder. d_p = ln(2) / t_half"
            ),
        ),
    ),
    reactions=(
        ReactionTemplate(
            "transcription", {}, {"M": 1}, "{k_tx} * {G}", modifiers=("G",),
        ),
        ReactionTemplate(
            "translation", {}, {"P": 1}, "{k_tl} * {M}", modifiers=("M",),
        ),
        ReactionTemplate("mrna_decay", {"M": 1}, {}, "{d_m} * {M}"),
        ReactionTemplate("protein_decay", {"P": 1}, {}, "{d_p} * {P}"),
    ),
)

AUTOREGULATED_GENE = Motif(
    name="autoregulated_gene",
    summary="A two-stage gene whose own protein represses its promoter.",
    basis=(
        "Negative autoregulation: `two_stage_expression` with the Hill term "
        "of `repressed_promoter` on transcription, and the repressor bound "
        "to the gene's OWN protein. It is the commonest regulatory shape in "
        "a bacterial transcription network, and its interest is dynamic "
        "rather than static -- it reaches its steady state faster than an "
        "unregulated gene tuned to the same level, because the promoter "
        "fires unrepressed until the protein has accumulated and then backs "
        "off, instead of approaching the level exponentially from below. "
        "Measured in E. coli by Rosenfeld, Elowitz and Alon (J Mol Biol "
        "2002, doi:10.1016/s0022-2836(02)00994-4), who also report the shape "
        "in over 40% of that organism's known transcription factors. "
        "The steady state is the root of a polynomial, not a ratio, "
        "so `d_p` no longer sets the response time on its own and no closed "
        "form for the level survives. Fails where "
        "`repressed_promoter` fails -- zero transcription at high protein, "
        "no basal term -- and additionally where the delay between "
        "transcription and a folded, active repressor is not small compared "
        "with 1/d_m: this motif has no delay at all, and a feedback loop "
        "given a delay it does not have can oscillate in reality while the "
        "model sits still."
    ),
    ports=(
        Port("G", ROLE_ENZYME, SINGLE_COPY_GENE_MM, description="the gene"),
        Port("M", ROLE_PRODUCT, 0.0, description="the transcript"),
        Port("P", ROLE_PRODUCT, 0.0,
             description="the protein, which is also its own repressor"),
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
            "k_tl", KIND_RATE_CONSTANT, 0.1, "1/s", table=None,
            description=(
                "proteins per transcript per second; illustrative placeholder"
            ),
        ),
        MotifParameter(
            "d_m", KIND_RATE_CONSTANT, 0.005, "1/s", table=None,
            description=(
                "transcript decay constant; illustrative placeholder. "
                "d_m = ln(2) / t_half"
            ),
        ),
        MotifParameter(
            "d_p", KIND_RATE_CONSTANT, 3e-4, "1/s", table=None,
            description=(
                "protein removal constant; illustrative placeholder. "
                "d_p = ln(2) / t_half"
            ),
        ),
        MotifParameter(
            "K", KIND_AFFINITY, 1e-4, "mM", table=None,
            description=(
                "own-protein concentration at half repression; illustrative "
                "placeholder"
            ),
        ),
        MotifParameter(
            "n", KIND_EXPONENT, 2.0, "dimensionless",
            description="Hill coefficient; cooperativity, chosen not measured",
        ),
    ),
    reactions=(
        ReactionTemplate(
            "autorepressed_transcription", {}, {"M": 1},
            "{k_tx} * {G} * {K}^{n} / ({K}^{n} + {P}^{n})",
            modifiers=("G", "P"),
        ),
        ReactionTemplate(
            "translation", {}, {"P": 1}, "{k_tl} * {M}", modifiers=("M",),
        ),
        ReactionTemplate("mrna_decay", {"M": 1}, {}, "{d_m} * {M}"),
        ReactionTemplate("protein_decay", {"P": 1}, {}, "{d_p} * {P}"),
    ),
)


#: The expression motifs, by name.
#:
#: A separate mapping rather than an insertion into `library.LIBRARY`.
#: `grammar.py` reads that mapping to turn a phrase at the front door into a
#: composition, and a motif reachable by name but with no phrase that
#: reaches it is a promise the front door does not keep. Registering these
#: is a grammar change, and it belongs in the change that adds the phrases.
EXPRESSION_LIBRARY: Dict[str, Motif] = {
    motif.name: motif
    for motif in (
        CONSTITUTIVE_PROMOTER,
        REPRESSED_PROMOTER,
        ACTIVATED_PROMOTER,
        TRANSLATION,
        MRNA_DEGRADATION,
        PROTEIN_DEGRADATION_TAGGED,
        TWO_STAGE_EXPRESSION,
        AUTOREGULATED_GENE,
    )
}


def expression_motif(name: str) -> Motif:
    try:
        return EXPRESSION_LIBRARY[name]
    except KeyError:
        raise KeyError(
            f"no expression motif named {name!r}. Available: "
            f"{', '.join(sorted(EXPRESSION_LIBRARY))}"
        ) from None


__all__ = [
    "ACTIVATED_PROMOTER",
    "AUTOREGULATED_GENE",
    "CONSTITUTIVE_PROMOTER",
    "EXPRESSION_LIBRARY",
    "MRNA_DEGRADATION",
    "PROTEASE_POOL_MM",
    "PROTEIN_DEGRADATION_TAGGED",
    "REPRESSED_PROMOTER",
    "RIBOSOME_POOL_MM",
    "SINGLE_COPY_GENE_MM",
    "TRANSLATION",
    "TWO_STAGE_EXPRESSION",
    "expression_motif",
]
