"""Sampling an ensemble from scored literature values — Bakker's method.

WHAT WAS ASKED FOR, VERBATIM
----------------------------
Prof. Barbara Bakker (UMC Groningen), 13 August 2026, asked whether "flag it,
don't use it" is the right response to a value with missing assay conditions:

    "In practice, we chose the best option, but do not exclude anything a
     priori. We are preparing a publication in which we generated an ensemble
     of models by sampling from a distribution of possible parameters. We gave
     each parameter a score based on its reliability and applicability, such
     as physiological pH and T, species [...] and completeness of assay
     description. **These scores were then used to give the parameter a weight
     in the sampling.**"

Prof. Herbert Sauro (UW, Director of the NIH Center for Model
Reproducibility), the same day, having been told about both options:

    "Barbara Bakker's approach is better. With Jessie's approach you don't get
     any simulation, with Barbara's you can sample and get an ensemble
     distribution. **That is the right way to do it.**"

Terrium shipped the scoring — `reliability.py` grades every value on exactly
the three axes Bakker names — and then used the scores to pick ONE number.
The sampling half was recorded as "declined". This module is that half.

WHAT THIS IS NOT, AND WHY THAT MATTERS MOST
--------------------------------------------
ADR 0024 declined sampling for a reason that is still correct and is not
being waved away:

    a teaching lab has no flux data to reject against, and spread without a
    validation step looks like a rigorous uncertainty estimate while being
    nothing of the kind.

Bakker's published ensemble has a rejection step — models are validated
against measured flux and the failures are discarded. Terrium has no such
data and does not pretend to. So what comes out of here is **not** an
uncertainty estimate, not a confidence interval, and not a posterior.

It is the spread of what the literature actually reports, weighted by how
well-evidenced each measurement is. That is a fact about the published
record, which is a genuinely useful thing to show a student and a genuinely
different thing from a calibrated uncertainty. Every surface that renders it
is required to say so, and `EnsembleResult.disclaimer` exists so the sentence
travels with the numbers rather than living in documentation.

RESAMPLING OBSERVED VALUES, NOT FITTING A DISTRIBUTION
-------------------------------------------------------
Bakker samples "from a distribution of possible parameters". With two to six
published measurements, fitting a parametric distribution would invent shape
information that the data does not contain — a lognormal through three points
is mostly an assumption. So this draws WITH REPLACEMENT from the observed
values themselves, weighted.

The consequence is stated rather than hidden: the ensemble can never produce
a value nobody measured. It interpolates nothing. For three candidates the
output takes at most three distinct values, and the histogram is a bar chart
of the literature rather than a smooth curve. That is the honest shape of the
evidence.

THE WEIGHTS ARE A POLICY, AND THE POLICY IS DECLARED
-----------------------------------------------------
`reliability.py` deliberately refuses to combine its three axes into a total,
because the trade-off between them is an empirical question nobody has
answered:

    "Combining the axes needs to know how a right-species value with a bad
     assay description trades off against a thorough assay in the wrong
     species. That trade-off is an empirical finding Terrium does not have."

Sampling needs a scalar. There is no way around that, so the numbers below
are **chosen, not measured**, and this module says so everywhere rather than
letting them read as derived. They are exposed as `DEFAULT_WEIGHT_POLICY`,
overridable per call, and echoed back in the result so a reader can disagree
with the arithmetic that produced their ensemble.

An axis on which every candidate scores the same cannot discriminate, and
does not: identical factors cancel under normalisation. So when nobody
supplied a physiological reference and every row is `not_assessed`, that axis
silently stops mattering instead of dragging every weight down together.
"""
from __future__ import annotations

import math
import random
import sys
from dataclasses import dataclass, field
from typing import Mapping, Sequence

try:  # pragma: no cover - import shape differs between callers
    from reliability import ReliabilityScore
except ImportError:  # pragma: no cover
    from Tests.reliability import ReliabilityScore  # type: ignore


#: Grade -> multiplicative factor, per axis.
#:
#: MULTIPLICATIVE, not additive. A value measured in the wrong organism, at
#: the wrong pH, with no assay description is not "one third as good" — the
#: defects compound, and a row that is poor on every axis should fall far
#: below one that is poor on a single axis. Addition lets a row launder one
#: fatal weakness behind two strengths.
#:
#: The numbers are a POLICY. They are not measured, they are not derived from
#: anything, and no experiment in this repository supports them. What can be
#: defended is the ORDERING within each axis, which is the same ordering
#: `evidence_rank.py` already uses for Pareto dominance and which nobody has
#: disputed:
#:
#:     complete > partial > absent
#:     near     > not_assessed > far
#:     exact    > related > unknown > distant
#:
#: `not_assessed` sits above `far` deliberately: "we could not check" is a
#: weaker signal than "we checked and it is wrong", and ranking a row below a
#: known-distant one for the crime of the CALLER not supplying a reference
#: would punish the value for the user's omission.
DEFAULT_WEIGHT_POLICY: Mapping[str, Mapping[str, float]] = {
    "assay_completeness": {"complete": 1.0, "partial": 0.5, "absent": 0.25},
    "condition_proximity": {"near": 1.0, "not_assessed": 0.6, "far": 0.3},
    "organism_match": {"exact": 1.0, "related": 0.5, "unknown": 0.35, "distant": 0.15},
}

#: A grade the policy does not name. Not silently dropped and not silently
#: given 1.0 — either would let a new grade change every ensemble in the
#: project without anyone noticing. Raised instead.
class UnknownGrade(ValueError):
    """A grade with no declared weight. The policy must be extended."""


@dataclass(frozen=True)
class Candidate:
    """One published measurement, with the score that decides its weight."""

    value: float
    score: ReliabilityScore
    unit: str | None = None
    organism: str | None = None
    reference_id: str | None = None
    conditions: str | None = None


@dataclass(frozen=True)
class WeightedCandidate:
    candidate: Candidate
    #: Raw product of the per-axis factors, before normalisation.
    raw_weight: float
    #: Share of the sampling probability, summing to 1 across the pool.
    probability: float
    #: (axis, grade, factor) for each axis, so the arithmetic is auditable.
    breakdown: tuple[tuple[str, str, float], ...]


@dataclass(frozen=True)
class EnsembleResult:
    """A drawn ensemble, and everything needed to argue with it."""

    draws: tuple[float, ...]
    weighted: tuple[WeightedCandidate, ...]
    seed: int
    policy: Mapping[str, Mapping[str, float]]
    disclaimer: str

    @property
    def distinct_values(self) -> int:
        """How many different numbers the ensemble can contain.

        Never more than the number of candidates: this resamples observed
        values and interpolates nothing. Surfaced as a property because a
        histogram with three bars is a fact about the literature, not a
        rendering bug.
        """
        return len({d for d in self.draws})

    def summary(self) -> dict[str, float | None]:
        """Order statistics of the draws.

        Percentiles, not mean and standard deviation. The draws come from a
        handful of discrete values and are usually neither symmetric nor
        unimodal, so a standard deviation would describe a bell that is not
        there. Percentiles are true of any shape.
        """
        if not self.draws:
            return {"n": 0, "low": None, "median": None, "high": None, "fold_range": None}
        ordered = sorted(self.draws)
        n = len(ordered)

        def pct(p: float) -> float:
            # Nearest-rank. With few distinct values, interpolating between
            # order statistics would report a number nobody measured, which
            # is exactly what resampling was chosen to avoid.
            index = min(n - 1, max(0, math.ceil(p * n) - 1))
            return ordered[index]

        low, high = ordered[0], ordered[-1]
        return {
            "n": float(n),
            "low": low,
            "p05": pct(0.05),
            "median": pct(0.50),
            "p95": pct(0.95),
            "high": high,
            "fold_range": (high / low) if low > 0 else None,
        }


#: Travels with the numbers. See the module docstring: Bakker's ensemble
#: rejects against measured flux, and Terrium has no such data.
DISCLAIMER = (
    "This is the spread of published measurements, weighted by how well "
    "evidenced each one is. It is NOT an uncertainty estimate: there is no "
    "validation step rejecting models that disagree with data, because a "
    "teaching lab has no such data. Read it as 'what the literature "
    "contains', not as 'how confident we are'."
)


def weight_of(
    score: ReliabilityScore,
    policy: Mapping[str, Mapping[str, float]] = DEFAULT_WEIGHT_POLICY,
) -> tuple[float, tuple[tuple[str, str, float], ...]]:
    """Scalar weight for one candidate, plus the arithmetic that produced it.

    Returns the breakdown alongside the number because a weight with no
    derivation is exactly the kind of unexplained figure this project exists
    to eliminate. Every surface that shows an ensemble can show why a row was
    sampled as often as it was.
    """
    axes = (
        ("assay_completeness", score.assay_completeness.grade),
        ("condition_proximity", score.condition_proximity.grade),
        ("organism_match", score.organism_match.grade),
    )
    product = 1.0
    breakdown: list[tuple[str, str, float]] = []
    for axis, grade in axes:
        table = policy.get(axis)
        if table is None or grade not in table:
            raise UnknownGrade(
                f"no weight declared for {axis}={grade!r}. Extend the policy "
                "rather than defaulting it: a silent 1.0 would let a new grade "
                "reweight every ensemble in the project unnoticed."
            )
        factor = table[grade]
        product *= factor
        breakdown.append((axis, grade, factor))
    return product, tuple(breakdown)


def weigh(
    candidates: Sequence[Candidate],
    policy: Mapping[str, Mapping[str, float]] = DEFAULT_WEIGHT_POLICY,
) -> list[WeightedCandidate]:
    """Normalised sampling probabilities for a pool of candidates."""
    raw = [weight_of(c.score, policy) for c in candidates]
    total = sum(w for w, _ in raw)
    if total <= 0:
        # Every candidate scored zero. Falling back to uniform would be a
        # silent policy change at the worst moment; refusing says the policy
        # cannot discriminate here and somebody should look.
        raise ValueError(
            "every candidate weighs zero under this policy, so there is no "
            "distribution to sample from. Check the policy rather than the data."
        )
    return [
        WeightedCandidate(
            candidate=candidate,
            raw_weight=weight,
            probability=weight / total,
            breakdown=breakdown,
        )
        for candidate, (weight, breakdown) in zip(candidates, raw)
    ]


def sample_ensemble(
    candidates: Sequence[Candidate],
    draws: int,
    seed: int,
    policy: Mapping[str, Mapping[str, float]] = DEFAULT_WEIGHT_POLICY,
) -> EnsembleResult:
    """Draw `draws` values, each candidate weighted by its reliability score.

    `seed` is REQUIRED, not optional with a default. An ensemble nobody can
    reproduce is not evidence, and this repository's whole claim is that its
    numbers can be re-derived. A caller who does not care which seed still
    has to write one down.
    """
    if draws < 1:
        raise ValueError(f"an ensemble needs at least one draw, got {draws}")
    if not candidates:
        raise ValueError(
            "no candidates to sample from. An empty ensemble is not a result: "
            "the caller should report that nothing was resolved."
        )

    weighted = weigh(candidates, policy)
    rng = random.Random(seed)
    population = [w.candidate.value for w in weighted]
    weights = [w.probability for w in weighted]
    drawn = tuple(rng.choices(population, weights=weights, k=draws))

    return EnsembleResult(
        draws=drawn,
        weighted=tuple(weighted),
        seed=seed,
        policy=policy,
        disclaimer=DISCLAIMER,
    )


def ensemble_from_entries(
    entries: Sequence[object],
    *,
    draws: int,
    seed: int,
    value_attr: str = "km_value",
    requested_organism: str | None = None,
    reference: object | None = None,
    relatedness_by_organism: Mapping[str, dict] | None = None,
    policy: Mapping[str, Mapping[str, float]] = DEFAULT_WEIGHT_POLICY,
) -> EnsembleResult:
    """Build an ensemble from resolver rows, scoring EACH one.

    WHY THIS FUNCTION IS THE WHOLE INTEGRATION
    -------------------------------------------
    `science_agent_runner.py` scores exactly one value: the winner. That is
    all a single-value answer needs, and it is why the scoring shipped while
    the sampling did not — there was never a per-candidate score to weight
    anything with.

    Bakker's method needs a score for every candidate, and the rows on the
    non-dominated frontier already carry what `score_reliability` wants:
    `assay_ph`, `assay_temperature_c`, `assay_unreported`, `organism`. So the
    scores are computed here rather than invented, from the same function the
    winner is graded by — one implementation, not two (ADR 0027).

    Rows with no usable value are dropped rather than defaulted. A row whose
    number could not be read is not a measurement, and giving it one would be
    the invention this whole project refuses.
    """
    try:
        from reliability import score_reliability
    except ImportError:  # pragma: no cover
        from Tests.reliability import score_reliability  # type: ignore

    candidates: list[Candidate] = []
    for entry in entries:
        value = getattr(entry, value_attr, None)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        if not math.isfinite(float(value)):
            continue
        measured_organism = getattr(entry, "organism", None)
        verdict = None
        if relatedness_by_organism and measured_organism:
            verdict = relatedness_by_organism.get(measured_organism)
        candidates.append(
            Candidate(
                value=float(value),
                score=score_reliability(
                    ph=getattr(entry, "assay_ph", None),
                    temperature_c=getattr(entry, "assay_temperature_c", None),
                    unreported=list(getattr(entry, "assay_unreported", []) or []),
                    reference=reference,
                    requested_organism=requested_organism,
                    measured_organism=measured_organism,
                    cross_species=bool(
                        requested_organism
                        and measured_organism
                        and requested_organism != measured_organism
                    ),
                    relatedness=verdict,
                ),
                unit=getattr(entry, "unit", None),
                organism=measured_organism,
                reference_id=getattr(entry, "reference_id", None),
                conditions=getattr(entry, "conditions", None),
            )
        )

    if not candidates:
        raise ValueError(
            "no row carried a usable value, so there is nothing to sample. "
            "This is a resolution failure to report, not an empty ensemble."
        )
    return sample_ensemble(candidates, draws=draws, seed=seed, policy=policy)


def _format_report(result: EnsembleResult, quantity: str = "value") -> str:
    """The ensemble as a person reads it.

    Kept in this module rather than in a caller so that every surface renders
    the same sentences. `queryResolver.ts` refuses to paraphrase a finding for
    exactly this reason: a client that rewords becomes a second place the
    wording can drift.
    """
    lines: list[str] = []
    summary = result.summary()
    n = int(summary["n"] or 0)

    lines.append("")
    lines.append(f"  The literature does not agree on this {quantity}.")
    lines.append("")
    lines.append(
        f"  {len(result.weighted)} published measurement(s), sampled {n} times with each"
    )
    lines.append("  weighted by how well evidenced it is:")
    lines.append("")
    for w in sorted(result.weighted, key=lambda x: -x.probability):
        c = w.candidate
        unit = f" {c.unit}" if c.unit else ""
        ref = f"  [ref {c.reference_id}]" if c.reference_id else ""
        grades = " / ".join(grade for _, grade, _ in w.breakdown)
        lines.append(f"    {c.value:>10g}{unit}   drawn {w.probability:6.1%} of the time{ref}")
        lines.append(f"    {'':>10}     {grades}")
        if c.conditions:
            lines.append(f"    {'':>10}     {c.conditions[:60]}")
    lines.append("")
    fold = summary["fold_range"]
    span = f"{summary['low']:g} to {summary['high']:g}"
    lines.append(
        f"  Spread: {span}"
        + (f", a {fold:.3g}-fold range" if fold else "")
        + f"   (median {summary['median']:g})"
    )
    lines.append("")
    # The disclaimer is not optional decoration. ADR 0024 declined sampling
    # precisely because a spread with no validation step reads as an
    # uncertainty estimate, and this sentence is the answer to that.
    for line in result.disclaimer.split(". "):
        text = line.strip().rstrip(".")
        if text:
            lines.append(f"  {text}.")
    lines.append("")
    lines.append(f"  Reproduce: seed {result.seed}, {n} draws, default weight policy.")
    return "\n".join(lines)


def candidates_from_scored(scored: Sequence[Mapping]) -> list[Candidate]:
    """Rebuild `Candidate` objects from the resolver's scored frontier.

    `KineticResult.ensemble_candidates` carries plain dicts on purpose: the
    literature layer must not import this module to produce its output, or
    the resolver would depend on the sampler when the real relationship runs
    the other way. This is the adapter on the sampler's side of that line.
    """
    try:
        from reliability import Axis, ReliabilityScore
    except ImportError:  # pragma: no cover
        from Tests.reliability import Axis, ReliabilityScore  # type: ignore

    out: list[Candidate] = []
    for row in scored:
        grades = row.get("grades") or {}
        out.append(
            Candidate(
                value=float(row["value"]),
                score=ReliabilityScore(
                    assay_completeness=Axis(grade=grades["assay_completeness"], reason=""),
                    condition_proximity=Axis(grade=grades["condition_proximity"], reason=""),
                    organism_match=Axis(grade=grades["organism_match"], reason=""),
                ),
                unit=row.get("unit"),
                organism=row.get("organism"),
                reference_id=row.get("reference_id"),
                conditions=row.get("conditions"),
            )
        )
    return out


def _format_band(band) -> str:
    """The trajectory envelope, as a person reads it.

    Beside the parameter spread rather than instead of it: the two answer
    different questions. The parameter spread says the literature disagrees;
    the band says how much that disagreement matters to the answer, which is
    the only one of the two a student can act on.
    """
    lines: list[str] = ["", "  What that disagreement does to the simulation:", ""]
    lines.append(f"  {band.support_note()}")
    lines.append("")
    for envelope in band.envelopes:
        # A column whose band is flat everywhere is not interesting and
        # crowds out the one that is. Reported as a single line instead of
        # a table of identical numbers.
        widths = [h - lo for lo, h in zip(envelope.low, envelope.high)]
        if max(widths) <= 0:
            lines.append(f"  {envelope.column}: identical across every run.")
            continue
        widest = max(range(len(widths)), key=lambda i: widths[i])
        lines.append(f"  {envelope.column}")
        lines.append(f"    {'t':>8}  {'low':>12}  {'median':>12}  {'high':>12}")
        for i, t in enumerate(envelope.times):
            mark = "  <-- widest" if i == widest else ""
            lines.append(
                f"    {t:>8.3g}  {envelope.low[i]:>12.5g}  "
                f"{envelope.median[i]:>12.5g}  {envelope.high[i]:>12.5g}{mark}"
            )
        lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """`python -m ensemble --fixture ... --substrate ...`

    Runs the whole method against a BRENDA table: parse, take the
    non-dominated frontier, score every surviving row, weight, sample, and
    report the spread.

    Offline by design -- it reads a fixture rather than the network, so the
    output is checkable and BRENDA is not hit by a demonstration.
    """
    import argparse
    import json
    import pathlib as _pathlib

    parser = argparse.ArgumentParser(
        prog="ensemble",
        description="Sample an ensemble from scored BRENDA values (Bakker's method).",
    )
    parser.add_argument(
        "--fixture",
        help="a saved BRENDA HTML table. Omit to resolve live, which is what "
             "a student without a saved table has to do.",
    )
    parser.add_argument("--enzyme", help="enzyme name, for a live lookup")
    parser.add_argument("--ec", default="1.1.1.27")
    parser.add_argument("--substrate", required=True)
    parser.add_argument("--organism", default="Homo sapiens")
    parser.add_argument("--quantity", default="km", choices=["km", "ki", "kcat"])
    parser.add_argument("--draws", type=int, default=2000)
    parser.add_argument(
        "--seed",
        type=int,
        required=True,
        help="required: an ensemble nobody can re-derive is not evidence",
    )
    parser.add_argument(
        "--simulate",
        help="engine domain to run per draw, e.g. michaelis_menten. Without "
             "this you get the parameter spread but no trajectory.",
    )
    parser.add_argument("--parameter", default="km", help="which parameter the draws vary")
    parser.add_argument("--vmax", type=float, default=5.0)
    parser.add_argument("--s0", type=float, default=10.0)
    parser.add_argument("--end", type=float, default=10.0)
    parser.add_argument("--points", type=int, default=11)
    parser.add_argument("--max-runs", dest="max_runs", type=int, default=200)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(list(argv) if argv is not None else None)

    # This module's own directory, so `brenda_client` and `evidence_rank`
    # import whatever the caller's working directory happens to be. The CLI
    # spawns it from the repository root; running it by hand happens from
    # Tests/. Depending on cwd made the first of those fail with a fixture
    # path resolved twice.
    _here = str(_pathlib.Path(__file__).resolve().parent)
    if _here not in sys.path:
        sys.path.insert(0, _here)

    import brenda_client
    import evidence_rank

    # TWO WAYS IN, AND THE LIVE ONE IS THE POINT.
    #
    # `--fixture` reads a saved BRENDA table: offline, checkable, and what
    # the tests use. It is also a file a student does not have, which made
    # this command effectively unrunnable for the person it is for.
    #
    # Without it, the ordinary resolver runs -- the same
    # `resolve_kinetic_value` behind `scientific resolve`, hitting BRENDA
    # exactly once. The ensemble then draws from the frontier that
    # resolution already scored, so the sampling costs no extra requests.
    # BRENDA asked that tools be gentle; a command that re-queried per draw
    # would not be.
    if args.fixture:
        html = _pathlib.Path(args.fixture).read_text(encoding="utf-8")
        rows = brenda_client.parse_brenda_km_html(
            html, args.ec, [args.substrate], args.organism
        )
        if not rows:
            print(json.dumps({"ok": False, "error":
                  f"No rows for {args.substrate!r} in {args.fixture}."})
                  if args.json else
                  f"No rows for {args.substrate!r} in {args.fixture}. "
                  "Nothing was resolved, so there is no ensemble to draw -- "
                  "which is a resolution failure to report, not an empty result.")
            return 2
        kept = evidence_rank.frontier(rows, args.organism, None)
        result = ensemble_from_entries(
            kept, draws=args.draws, seed=args.seed, requested_organism=args.organism
        )
        n_rows, n_frontier = len(rows), len(kept)
    else:
        if not args.enzyme and not args.ec:
            print("A live lookup needs --enzyme or --ec.")
            return 2
        import fallback_logic

        resolved = fallback_logic.resolve_kinetic_value(
            args.ec, args.organism, args.substrate,
            enzyme_name=args.enzyme, quantity=args.quantity,
        )
        scored = getattr(resolved, "ensemble_candidates", []) or []
        if not scored:
            message = (
                f"Nothing resolved for {args.substrate} / {args.organism}. "
                "There is no ensemble to draw -- a resolution failure to "
                "report, not an empty band."
            )
            print(json.dumps({"ok": False, "error": message}) if args.json else message)
            return 2
        result = sample_ensemble(
            candidates_from_scored(scored), draws=args.draws, seed=args.seed
        )
        n_rows = n_frontier = len(scored)

    # THE SIMULATION HALF. Without `--simulate` this reports the spread of the
    # PARAMETER, which is Bakker's weighting and is not yet what Sauro asked
    # for -- "with Barbara's you can sample and get an ensemble distribution".
    # With it, the model is run once per draw and the band is what comes back.
    band = None
    if args.simulate:
        try:
            from model_ensemble import ensemble_over
        except ImportError:  # pragma: no cover
            from Tests.model_ensemble import ensemble_over  # type: ignore
        # The engine lives at the repository root, one level above Tests/.
        # Added here rather than relying on the caller's PYTHONPATH so the
        # command works when run directly from Tests/, which is how the
        # docstring says to run it.
        _root = str(_pathlib.Path(__file__).resolve().parent.parent)
        if _root not in sys.path:
            sys.path.insert(0, _root)
        import Terium.terium_engine as _engine

        simulate_fn = getattr(_engine, f"simulate_{args.simulate}", None)
        if simulate_fn is None:
            print(f"No engine function for domain {args.simulate!r}.")
            return 2
        band = ensemble_over(
            simulate=simulate_fn,
            base_parameters=dict(
                vmax=args.vmax, s0=args.s0, end=args.end, points=args.points
            ),
            parameter=args.parameter,
            drawn=result,
            max_runs=args.max_runs,
        )

    if args.json:
        payload = {
            "ok": True,
            "substrate": args.substrate,
            "organism": args.organism,
            "rows": n_rows,
            "frontier": n_frontier,
            "seed": result.seed,
            "disclaimer": result.disclaimer,
            "candidates": [
                {
                    "value": w.candidate.value,
                    "unit": w.candidate.unit,
                    "probability": w.probability,
                    "referenceId": w.candidate.reference_id,
                    "conditions": w.candidate.conditions,
                    "grades": [grade for _, grade, _ in w.breakdown],
                }
                for w in sorted(result.weighted, key=lambda x: -x.probability)
            ],
            "summary": result.summary(),
        }
        if band is not None:
            payload["band"] = {
                "swept": list(band.swept),
                "succeeded": band.succeeded,
                "attempted": band.attempted,
                "supportNote": band.support_note(),
                "envelopes": [
                    {
                        "column": e.column,
                        "times": list(e.times),
                        "low": list(e.low),
                        "median": list(e.median),
                        "high": list(e.high),
                    }
                    for e in band.envelopes
                ],
            }
        print(json.dumps(payload, indent=2))
        return 0

    print(f"\n{args.substrate} / {args.organism}  --  {n_rows} row(s), "
          f"{n_frontier} on the non-dominated frontier")
    print(_format_report(result, quantity="Km"))
    if band is not None:
        print(_format_band(band))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
