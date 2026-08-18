"""
spread_consequence.py

The evidence ranked several literature values equal. What does choosing
between them do to the simulation?

WHY THIS EXISTS
---------------
Barbara Bakker (UMCG), asked whether "flag it, don't use it" is right for a
poorly-described measurement, rejected the premise:

    In practice, we chose the best option, but do not exclude anything a
    priori. [...] We gave each parameter a score based on its reliability
    and applicability [...] These scores were then used to give the
    parameter a weight in the sampling.

ADR 0024 Decision 3 adopted her scoring axes and **declined the ensemble**,
for a reason that still holds:

    Sampling needs a distribution per parameter and a flux dataset to
    validate the resulting models against. A teaching lab has neither.
    Without the validation step, ensemble sampling produces spread with no
    reason to trust any part of it -- which is worse than a single flagged
    value, because it *looks* like a rigorous uncertainty estimate.

ADR 0047 then narrowed selection to the non-dominated set, and ADR 0051
reported the tie among the survivors. Its own text says: *"This is not an
ensemble."*

So the reader is now told, correctly, that the evidence found several values
equally credible -- and has no way to see what turns on it. Through the real
resolution path, for LDH kcat:

    170.7 1/s   immobiized recombinant enzyme, pH 7.0, 25 C   (selected)
    276.5 1/s   soluble recombinant enzyme, pH 7.0, 25 C

Both from BRENDA reference 741355, a 1.62-fold spread. A student is handed
170.7 and a sentence saying 276.5 was equally well evidenced. Whether that
matters to *their* experiment is a question about the model, and nothing
answered it.

WHAT THIS IS, AND WHAT IT IS NOT
--------------------------------
This runs the model once per candidate the literature actually reports and
puts the outcomes side by side.

It is **not** an ensemble, and the distinction is not cosmetic:

* No distribution is sampled. The inputs are the observed values and only
  those. There is no prior, no weighting, no interpolation between them --
  running a model at a number nobody measured is precisely the fabrication
  this project exists to refuse.
* No uncertainty is estimated. Bakker's spread is bounded by rejection at
  the model level after flux validation. Terrium has no flux data, so
  nothing here may be read as "the answer is X +/- Y".
* Nothing is aggregated. There is no mean outcome. A mean over values whose
  weights are unknown is the invented total that `reliabilityScore.ts`
  refuses for the same reason (ADR 0024, `noAggregateReason`), and Bakker's
  own weighting question is still unanswered -- see the outstanding item in
  `docs/EXPERT_FEEDBACK.md`.

What it reports is narrower and fully grounded: *these are the values the
literature reports; here is the model under each; they differ by this much.*
That is a statement about disagreement in the sources, propagated through
arithmetic the reader can check -- not a claim about the true value.

It reports and does not block, for Bakker's reason: she excludes nothing a
priori.
"""
from __future__ import annotations

from typing import Callable, Sequence

from pydantic import BaseModel

#: The Michaelis-Menten parameters a candidate list can vary.
#:
#: `kcat` is NOT here. A kcat is not an input to the model -- `vmax = kcat *
#: [E]` needs an enzyme concentration, which BRENDA does not report and this
#: module will not assume. A kcat tie is answerable only when the caller
#: supplies that concentration, and `consequence_of` says so rather than
#: quietly treating a turnover number as a rate.
VARIABLE_PARAMETERS = ("km", "vmax")


class CandidateOutcome(BaseModel):
    """One literature value, and the model run at it."""

    #: The parameter value used, exactly as the source reported it.
    value: float
    #: True for the value the resolver actually returned.
    selected: bool
    #: What the source said about this row, so a reader can see WHY two
    #: numbers differ before deciding which to believe.
    conditions: str | None = None
    reference_id: str | None = None

    #: The observable, or None when this candidate could not be simulated.
    outcome: float | None = None

    #: Why this candidate produced no outcome. A candidate that failed is
    #: KEPT and named: dropping it would shrink the reported spread and
    #: make the remaining values look more agreed than they are.
    failure: str | None = None


class SpreadConsequence(BaseModel):
    """What the disagreement among equally-evidenced values does."""

    #: "assessed" | "not_assessed"
    #:
    #: Three states are unnecessary here and two are not enough on their
    #: own -- which is why `not_assessed` always carries `reason`. An empty
    #: `SpreadConsequence()` must never read as "the candidates agreed".
    status: str

    #: Which model parameter the candidates are values of.
    parameter: str = ""

    #: The observable compared across runs, named in the payload rather
    #: than left for a reader to infer from a bare number.
    observable: str = ""

    outcomes: list[CandidateOutcome] = []

    #: Range of the OUTCOME across candidates that ran. Observed, not
    #: modelled: these are the smallest and largest results, not a
    #: confidence interval.
    outcome_low: float | None = None
    outcome_high: float | None = None
    outcome_fold_range: float | None = None

    reason: str = ""

    @property
    def is_assessed(self) -> bool:
        """A POSITIVE test, counting candidates that actually RAN.

        `status != "not_assessed"` would call a default-constructed
        `SpreadConsequence()` assessed. Same reasoning as
        `SelectionTie.is_tied` and `VariantVerdict.is_wild_type`.

        And `len(self.outcomes) > 1` is not enough either -- found by
        running it: two candidates that both failed to simulate produced
        `status="assessed"`, two outcomes, and `is_assessed=True`, while
        the model had said precisely nothing. A comparison needs two
        results, not two attempts.
        """
        return (
            self.status == "assessed"
            and len([o for o in self.outcomes if o.outcome is not None]) > 1
        )


#: The substrate column, as the engine labels it. Not an index.
#:
#: `data[-1][1]` would read the second column of whatever the engine
#: happened to emit, and would keep returning a number after a column was
#: added or reordered -- silently answering with the product instead of the
#: substrate. The name is looked up and its absence is an error.
_SUBSTRATE_COLUMN = "[S]"


def substrate_remaining(result) -> float:
    """The observable: substrate left at the end of the simulated window.

    A direct model output, read off the final row of the trajectory. NOT a
    derived statistic -- no half-life, no fitted rate, no interpolation.

    Half-conversion time would be the more familiar teaching quantity and
    is deliberately not used: it requires interpolating between time points
    and a rule for trajectories that never reach half, and both are
    judgements this module would be making on the reader's behalf.
    """
    colnames = list(result.colnames)
    if _SUBSTRATE_COLUMN not in colnames:
        raise KeyError(
            f"no {_SUBSTRATE_COLUMN!r} column in {colnames}; the observable "
            "this compares is not present in the trajectory"
        )
    return float(result.data[-1][colnames.index(_SUBSTRATE_COLUMN)])


def consequence_of(
    candidates: Sequence,
    *,
    parameter: str,
    vmax: float | None = None,
    km: float | None = None,
    s0: float | None = None,
    end: float = 10.0,
    points: int = 51,
    simulate: Callable | None = None,
) -> SpreadConsequence:
    """Run the model at each candidate value and report the outcomes.

    `candidates` is `SelectionTie.candidates` -- every non-dominated row,
    including the selected one.

    THE REFUSALS
    ------------
    Varying one Michaelis-Menten parameter requires the others, and this
    module will not supply them. `reliabilityScore.ts` makes the same
    refusal for "physiological pH and T": 7.4 and 37 C describe a mammal
    and misdescribe *Thermus thermophilus*, so the reference is an
    experimental condition the caller provides. A `vmax` or `s0` invented
    here would be worse, because it does not merely mis-score a value -- it
    changes the trajectory the reader is being shown.

    So a missing input is `not_assessed` with the missing input NAMED, and
    that is a different fact from "there was nothing to report".
    """
    if parameter not in VARIABLE_PARAMETERS:
        return SpreadConsequence(
            status="not_assessed",
            parameter=parameter,
            reason=(
                f"{parameter!r} is not an input to the Michaelis-Menten model "
                f"(it takes {' and '.join(VARIABLE_PARAMETERS)}). A kcat is a "
                "turnover number: converting it to a vmax needs the enzyme "
                "concentration of the assay, which BRENDA does not report. "
                "Supply that concentration and pass the resulting vmax "
                "values, or nothing here would be a simulation of anything "
                "measured."
            ),
        )

    values = [float(c.value) for c in candidates if getattr(c, "value", None) is not None]
    if len(values) < 2:
        return SpreadConsequence(
            status="not_assessed",
            parameter=parameter,
            reason=(
                f"{len(values)} candidate value(s). Nothing turned on the "
                "choice, so there is no disagreement to propagate."
            ),
        )

    fixed = {"vmax": vmax, "km": km, "s0": s0}
    fixed.pop(parameter)
    missing = sorted(name for name, held in fixed.items() if held is None)
    if missing:
        return SpreadConsequence(
            status="not_assessed",
            parameter=parameter,
            reason=(
                f"cannot run the model: {', '.join(missing)} not supplied. "
                "These are experimental settings, not properties of the "
                "enzyme, and Terrium does not have them. Guessing one would "
                "change the trajectory shown to the reader while looking "
                "like a result."
            ),
        )

    if simulate is None:  # pragma: no cover - exercised via the real engine
        from Terium.continuous.simulations import simulate_michaelis_menten

        simulate = simulate_michaelis_menten

    outcomes: list[CandidateOutcome] = []
    for candidate in candidates:
        value = getattr(candidate, "value", None)
        if value is None:
            continue
        arguments = {"km": km, "vmax": vmax, "s0": s0}
        arguments[parameter] = float(value)

        outcome: float | None = None
        failure: str | None = None
        try:
            outcome = substrate_remaining(
                simulate(
                    km=arguments["km"],
                    vmax=arguments["vmax"],
                    s0=arguments["s0"],
                    end=end,
                    points=points,
                )
            )
        except Exception as exc:  # noqa: BLE001 - reported, never swallowed
            # Kept in the list with the reason. A candidate silently
            # dropped would narrow the reported spread, which is the one
            # direction this module must never move in.
            failure = f"{type(exc).__name__}: {exc}"

        outcomes.append(
            CandidateOutcome(
                value=float(value),
                selected=bool(getattr(candidate, "selected", False)),
                conditions=getattr(candidate, "conditions", None),
                reference_id=getattr(candidate, "reference_id", None),
                outcome=outcome,
                failure=failure,
            )
        )

    ran = [o.outcome for o in outcomes if o.outcome is not None]
    low = min(ran) if ran else None
    high = max(ran) if ran else None
    fold = (high / low) if (low is not None and high is not None and low > 0) else None

    failed = [o for o in outcomes if o.failure]
    note = (
        f" {len(failed)} candidate(s) could not be simulated and are listed "
        "with the reason rather than dropped."
        if failed
        else ""
    )

    # Assembled as STATEMENTS, not as one expression with a conditional in
    # the middle of it.
    #
    # The first version was `headline if ran else other + suffix`, which
    # Python parses as `headline if ran else (other + suffix)` -- so on the
    # branch that matters the failure note and the "NOT an uncertainty
    # estimate" disclaimer were both silently dropped. Computed and not
    # delivered, in the lines written to deliver them. Two tests caught it.
    ranked = (
        f"The evidence ranked {len(values)} values of {parameter} equal: "
        f"{min(values):.4g} to {max(values):.4g}."
    )
    if low is not None and high is not None:
        headline = (
            f"{ranked} Running the model at each -- and at no other value, "
            "since no other value was measured -- the substrate remaining at "
            f"t={end:.4g} ranges from {low:.4g} to {high:.4g}."
        )
        if fold:
            headline += f" A factor of {fold:.3g}."
    else:
        headline = (
            f"{ranked} NONE of them could be simulated, so the model says "
            "nothing about the disagreement."
        )

    disclaimer = (
        " This is the disagreement among the sources carried through the "
        "model. It is NOT an uncertainty estimate: the spread is bounded by "
        "which papers happen to be in BRENDA, not by any statement about the "
        "true value."
    )

    return SpreadConsequence(
        # Fewer than two RESULTS means there is nothing to compare, however
        # many candidates were tried. `status` and `is_assessed` are
        # derived from the same count so they cannot disagree.
        status="assessed" if len(ran) > 1 else "not_assessed",
        parameter=parameter,
        observable=f"substrate remaining at t={end}",
        outcomes=outcomes,
        outcome_low=low,
        outcome_high=high,
        outcome_fold_range=fold,
        # Rounded in the PROSE only. `outcome_low`/`outcome_high` and each
        # `CandidateOutcome.outcome` carry the full value, so a reader who
        # needs the digits has them and a reader who needs a sentence is
        # not handed 7.634925931393244.
        reason=headline + note + disclaimer,
    )
