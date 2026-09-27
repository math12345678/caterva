"""Which of the constants a given set of observations could ever recover.

THE QUESTION THIS ANSWERS
-------------------------
`sensitivity.py` answers which constants MOVE an answer. That is the right
input to "what should I measure first". It is the wrong input to "what will
my assay hand back to me".

A steady state moves with kcat and it moves with Km, so a sensitivity
ranking lists both. It does not follow that fitting that steady state to
data returns kcat and Km: below saturation the rate depends on them only
through kcat/Km, and no quantity of data splits a ratio into a numerator and
a denominator. The ranking is not wrong. It is answering a different
question, and read as advice it sends somebody to the bench for a number
their experiment cannot contain.

The failure has a recognisable shape at the other end. The fit converges,
the residual is excellent, and the two constants wander together along a
valley with confidence intervals a decade wide. Nothing went wrong in the
lab. The experiment as specified never carried the information, and that was
knowable before it ran, from the model alone.

WHAT IS COMPUTED, AND IN WHICH SPACE
------------------------------------
One matrix, rows the observations and columns the parameters:

    S[i][j] = d ln y_i / d ln p_j

the same relative sensitivity `sensitivity.py` computes, for the same
reason. Absolute derivatives are in incomparable units, so a rank read off
them would depend on whether Km was written in mM or in uM -- rescaling a
column changes which singular values fall below any fixed cutoff. In the
logarithmic form every entry is dimensionless and the rank is a property of
the model rather than of the unit sheet.

A null direction of that matrix -- a vector v with S v = 0 -- is a way of
moving every parameter at once that no observation sees:

    p_j  ->  p_j * t^{v_j}

to first order in ln t. Two constants that enter only as a product or only
as a ratio produce exactly such a direction, and it is the direction that
names them: v = (1, 1) on (ks, kd) says scaling both by the same factor
changes nothing, so what the data fix is ks/kd and neither constant alone.
The complement is what IS determined -- the monomials prod p_j^{u_j} whose
exponent vector u is orthogonal to every null direction.

LOCAL AND PRACTICAL. NOT STRUCTURAL.
------------------------------------
This is the claim to be careful about, so it is stated before the machinery.

What is computed here is LOCAL, PRACTICAL identifiability: the rank of one
finite-difference sensitivity matrix, at ONE point in parameter space, for
ONE stated set of observations. It is not structural identifiability, which
asks whether the equations themselves admit two parameter sets with
identical output for every input and every value, and which is answered with
symbolic algebra -- differential elimination, a power-series or Lie-symmetry
argument -- not with a decimal SVD.

The two results license different sentences:

    rank deficiency here      Real evidence. A direction was found along
                              which the model's own equations say these
                              observations do not change, at these values.
                              For the analytic cases it is exact: a steady
                              state of ks - kd*X is ks/kd for every ks and
                              kd, and the deficiency is the whole truth about
                              that experiment.

    full rank here            NOT proof of identifiability. It says the
                              observations respond independently AT THIS
                              POINT, to first order, with no noise in the
                              data. It does not rule out a rank deficiency
                              elsewhere in parameter space, a global
                              ambiguity -- two distant parameter sets fitting
                              equally well -- which no local method can see,
                              or a direction so weakly determined that real
                              measurement error swallows it. Full rank is
                              the absence of one specific proof of failure.

A rank deficiency can also belong to the point rather than to the model: a
symmetric operating point can hide a dependence that an asymmetric one
exposes. That is why the report carries the parameter values it was
evaluated at, and why nothing here is phrased as a property of the mechanism
in general.

THE RANK THRESHOLD IS DERIVED, NOT PICKED
-----------------------------------------
"Rank" is a statement about exact arithmetic and there is none here. A
singular value is called zero when it cannot be told from zero, and that
comparison needs a number. Choosing one -- 1e-10, or numpy's default
`max(M, N) * eps * sigma_max` -- would make the answer to a scientific
question depend on a constant nobody argued for. So it is derived from what
the quantities themselves declare.

`sensitivity.resolution_for(precision)` is already the smallest |S| a
quantity of that accuracy can be told apart from its own rounding, which is
the same thing as a bound on the error in any single entry of that row.
Write the computed matrix as S = S_true + E with |E[i][j]| <= rho_i, where
rho_i is row i's resolution. Weyl's inequality for singular values says
every singular value moves by at most the spectral norm of the perturbation,
and the Frobenius norm bounds that:

    |sigma_k(S) - sigma_k(S_true)| <= ||E||_2 <= ||E||_F <= sqrt(n * sum rho_i^2)

with n the number of columns. So any computed singular value at or below

    tau = sqrt(n * sum_i rho_i^2)

is consistent with a true singular value of exactly zero: the matrix that
has it zero lies inside the error ball, and counting it towards the rank
would be reading the method's own rounding as information. That is the
threshold. The only judgement inside it is the factor of ten that
`sensitivity.SAFETY` already argues for.

It moves with the observations, which is the point. A steady state is exact
to machine precision and a settling time is not -- it comes off an
eigenvalue of a finite-difference Jacobian, five orders of magnitude coarser
-- so a matrix containing a settling-time row gets a coarser threshold, and
a fixed cutoff would have had to be wrong for one of them.

Note which way it errs. tau bounds the error from above, so the rank it
reports is a LOWER bound on the true rank and the unidentifiable set an
upper bound on the true one. That is the right direction for this question:
telling a researcher a parameter is unrecoverable when a heroic experiment
could recover it costs a conversation, and telling them it is recoverable
when it is not costs a month.

A NULL SPACE HAS NO CANONICAL BASIS, AND ONE FACT SURVIVES THAT
---------------------------------------------------------------
When the null space is one-dimensional its direction is unique up to sign,
so "only the ratio ks/kd is determined" is a statement about the model.
When it has two or more dimensions the SVD returns one orthonormal basis of
many, and the individual directions printed are not the only way to describe
the same set. The report says so rather than dressing an arbitrary rotation
up as a finding.

What survives is per-parameter: p_j can be recovered on its own exactly when
e_j has no component in the null space, and the norm of that component is
basis-independent. So `identifiable_subset` is a fact about the model where
the printed directions are a fact about the arithmetic, and the summary
leans on the first.

WHY A MISSING ROW OR A MISSING COLUMN IS A REFUSAL
--------------------------------------------------
`sensitivity.analyse` skips a parameter it cannot differentiate and reports
what it skipped, which is right there: a ranking of eleven constants is
still a ranking. Here it would be a lie by omission in a specific direction.

Dropping an observation can only lower the rank, so a report built from the
rows that happened to evaluate would call parameters unrecoverable that the
missing observation separates -- telling a researcher their experiment
cannot answer their question, on the evidence of an experiment that was not
in the matrix. Dropping a column silently removes a parameter from the
question that was asked. Both are refused, naming the observation or the
parameter and the reason, because there is no version of either answer that
is worth more than the refusal.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence, Tuple

try:
    from .sensitivity import MACHINE_PRECISION, SensitivityUnavailable
    from .sensitivity import analyse as _sensitivity_of
except ImportError:  # pragma: no cover - flat import
    from sensitivity import (  # type: ignore[no-redef]
        MACHINE_PRECISION, SensitivityUnavailable,
    )
    from sensitivity import analyse as _sensitivity_of  # type: ignore[no-redef]


class IdentifiabilityUnavailable(RuntimeError):
    """The matrix could not be built, so no rank can be reported.

    Separate from `SensitivityUnavailable` because the two failures license
    different next steps: a sensitivity that cannot be computed leaves the
    ranking short a row, and an identifiability matrix that cannot be built
    leaves the ANSWER wrong in a known direction -- see the module docstring
    on why a missing row is not a skip.
    """


def singular_value_threshold(
    resolutions: Sequence[float], columns: int
) -> float:
    """The largest singular value that could still be a true zero.

    Derived in the module docstring: each entry of row i is uncertain by at
    most that row's `resolution_for(precision)`, the Frobenius norm bounds
    the spectral norm of the resulting perturbation, and Weyl's inequality
    turns that into a bound on how far any singular value can have moved.

    Not a tuning knob. Every number in it comes from a quantity's declared
    accuracy and from the shape of the matrix.
    """
    if columns < 1:
        raise ValueError(
            "a sensitivity matrix with no columns has no parameters in it, "
            "so there is no threshold to compute and no rank to report"
        )
    if not resolutions:
        raise ValueError(
            "a sensitivity matrix with no rows has no observations in it. "
            "With nothing observed nothing is identifiable, which is a "
            "tautology rather than a finding."
        )
    total = 0.0
    for resolution in resolutions:
        value = float(resolution)
        if not (math.isfinite(value) and value > 0.0):
            raise ValueError(
                f"a row resolution of {resolution!r} is not a positive "
                f"finite number. It is the error bound on that row's "
                f"entries, and a threshold derived from a non-positive one "
                f"would claim the arithmetic is exact."
            )
        total += value * value
    return math.sqrt(columns * total)


def rank_of(singular_values: Sequence[float], threshold: float) -> int:
    """How many singular values are clear of the threshold.

    Strictly greater, not greater-or-equal: a singular value sitting exactly
    on the threshold is by construction the one that cannot be told from
    zero, so counting it would contradict the derivation.
    """
    return sum(1 for value in singular_values if float(value) > threshold)


@dataclass(frozen=True)
class SensitivityMatrix:
    """Relative sensitivities of several observations to several parameters.

    Rows are observations and columns are parameters, both in the order they
    were asked for. `resolutions` carries each ROW's noise floor rather than
    one number for the matrix, because the rows can come from quantities of
    very different accuracy and the threshold is built from all of them.

    `base_values` and `parameter_values` record WHERE this was evaluated.
    They are not used in the arithmetic; they are here because every claim
    this module makes is local to a point, and a local claim that does not
    say which point is not checkable.
    """

    quantities: Tuple[str, ...]
    parameters: Tuple[str, ...]
    rows: Tuple[Tuple[float, ...], ...]
    resolutions: Tuple[float, ...]
    base_values: Tuple[float, ...] = ()
    parameter_values: Tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if len(self.rows) != len(self.quantities):
            raise ValueError(
                f"{len(self.rows)} row(s) for {len(self.quantities)} "
                f"observation(s); a row and its label must be the same thing"
            )
        if len(self.resolutions) != len(self.rows):
            raise ValueError(
                f"{len(self.resolutions)} resolution(s) for "
                f"{len(self.rows)} row(s). Each row carries its own noise "
                f"floor, because the quantities need not be equally accurate."
            )
        width = len(self.parameters)
        for label, row in zip(self.quantities, self.rows):
            if len(row) != width:
                raise ValueError(
                    f"row {label!r} has {len(row)} entries for {width} "
                    f"parameter(s)"
                )

    @property
    def threshold(self) -> float:
        return singular_value_threshold(self.resolutions, len(self.parameters))

    def entry(self, quantity: str, parameter: str) -> float:
        return self.rows[self.quantities.index(quantity)][
            self.parameters.index(parameter)
        ]

    def uninformative(self) -> Tuple[str, ...]:
        """Observations whose whole row is below their own noise floor.

        Not an error and not dropped -- an observation that responds to
        nothing is a real finding about that observation, and it is a
        different finding from a parameter nothing responds to.
        """
        return tuple(
            label
            for label, row, floor in zip(
                self.quantities, self.rows, self.resolutions
            )
            if all(abs(value) <= floor for value in row)
        )


@dataclass(frozen=True)
class Combination:
    """One direction in parameter space that no observation responds to.

    `exponents` is the null direction, normalised so its largest component
    is +1, over ALL the parameters in matrix order. A parameter whose
    component is below `tolerance` does not take part: the null space is
    only located to within that angle, so a smaller component could be zero.
    """

    parameters: Tuple[str, ...]
    exponents: Tuple[float, ...]
    tolerance: float

    @property
    def involved(self) -> Tuple[str, ...]:
        return tuple(
            name
            for name, weight in zip(self.parameters, self.exponents)
            if abs(weight) > self.tolerance
        )

    def determined(self) -> Optional[Tuple[Tuple[str, float], ...]]:
        """The monomial these two parameters DO fix, when there are two.

        For a null direction v over parameters (a, b), the exponent vector
        orthogonal to it is u = (v_b, -v_a), so a^{u_a} b^{u_b} is what the
        observations pin down. Normalised so a's exponent is +1, which makes
        v = (1, 1) read as a/b and v = (1, -1) as a*b.

        `None` for any other number of parameters: with one there is nothing
        to combine, and with three or more the orthogonal complement is a
        plane rather than a direction, so no single monomial describes it.
        """
        names = self.involved
        if len(names) != 2:
            return None
        weights = [
            weight
            for name, weight in zip(self.parameters, self.exponents)
            if name in names
        ]
        first, second = weights
        # u = (second, -first), scaled so the first exponent is +1. `second`
        # cannot be zero: both parameters are involved, which is what makes
        # its magnitude exceed the tolerance.
        return ((names[0], 1.0), (names[1], -first / second))

    def describe(self) -> str:
        names = self.involved
        if not names:
            # Every component under the tolerance. Possible when the null
            # space is barely separated from the rest of the matrix, and
            # saying nothing would be better than naming a parameter on the
            # strength of a component that could be zero.
            return (
                "a direction no parameter is clearly part of: the null space "
                f"is located only to within {self.tolerance:.2g}, and every "
                "component of this direction is smaller than that. Treat it "
                "as a warning that the matrix is close to losing another "
                "rank rather than as a finding about any one constant."
            )
        if len(names) == 1:
            return (
                f"no observation here responds to {names[0]} on its own -- "
                f"its column of the matrix cannot be told from zero at this "
                f"run's threshold -- so it cannot be recovered from these "
                f"observations at any precision, however good the data are"
            )
        determined = self.determined()
        if determined is not None:
            (first, _), (second, exponent) = determined
            if abs(exponent + 1.0) <= self.tolerance:
                what = f"only the ratio {first}/{second} is determined"
            elif abs(exponent - 1.0) <= self.tolerance:
                what = f"only the product {first}*{second} is determined"
            else:
                what = (
                    f"only the combination {first} * {second}^{exponent:.3g} "
                    f"is determined"
                )
            return (
                f"{what}; {first} and {second} are not separately "
                f"identifiable from these observations"
            )
        moves = ", ".join(
            f"{name} by t^{weight:.3g}"
            for name, weight in zip(self.parameters, self.exponents)
            if name in names
        )
        return (
            f"{', '.join(names)} are not separately identifiable: multiplying "
            f"{moves} leaves every observation unchanged, so only the "
            f"combinations orthogonal to that direction are determined"
        )


@dataclass(frozen=True)
class IdentifiabilityReport:
    """What a fit to these observations could and could not return."""

    matrix: SensitivityMatrix
    singular_values: Tuple[float, ...]
    threshold: float
    rank: int
    #: An orthonormal basis of the null space, one direction per row, over
    #: the parameters in matrix order. One basis of many when there is more
    #: than one row -- see `basis_is_canonical`.
    null_space: Tuple[Tuple[float, ...], ...]
    #: How far a parameter's own axis leans into the null space: 0 means the
    #: observations fix it on its own, 1 means they say nothing about it
    #: except through others. Basis-independent, which is why the
    #: per-parameter verdict rests on this and not on the printed directions.
    leverage: Tuple[float, ...]
    #: The angle the null space itself is uncertain by, from Wedin's bound.
    #: A component smaller than this could be zero.
    tolerance: float

    @property
    def parameters(self) -> Tuple[str, ...]:
        return self.matrix.parameters

    @property
    def deficiency(self) -> int:
        """How many independent combinations the observations do not fix."""
        return len(self.parameters) - self.rank

    @property
    def basis_is_canonical(self) -> bool:
        """Whether the printed directions are the only way to say this.

        True for a one-dimensional null space, whose direction is unique up
        to sign. False above that: the SVD returns one orthonormal basis of
        infinitely many, all describing the same subspace.
        """
        return len(self.null_space) == 1

    def combinations(self) -> Tuple[Combination, ...]:
        return tuple(
            Combination(
                parameters=self.parameters,
                exponents=_normalised(direction),
                tolerance=self.tolerance,
            )
            for direction in self.null_space
        )

    def identifiable(self) -> Tuple[str, ...]:
        return tuple(
            name
            for name, lean in zip(self.parameters, self.leverage)
            if lean <= self.tolerance
        )

    def unidentifiable(self) -> Tuple[str, ...]:
        identifiable = set(self.identifiable())
        return tuple(n for n in self.parameters if n not in identifiable)

    def summary(self) -> str:
        lines = [
            f"{len(self.matrix.quantities)} observation(s) of "
            f"{len(self.parameters)} parameter(s): rank {self.rank}, so "
            f"{self.rank} independent combination(s) of the parameters are "
            f"determined and {self.deficiency} are not."
        ]

        if self.deficiency == 0:
            lines.append(
                "Every parameter is separately identifiable from these "
                "observations at this point: "
                + ", ".join(self.parameters)
                + ". That is the absence of one specific failure, not a "
                "proof -- see the closing note."
            )
        else:
            identifiable = self.identifiable()
            if identifiable:
                lines.append(
                    "Separately identifiable: " + ", ".join(identifiable) + "."
                )
            elif self.rank == 0:
                # A DIFFERENT FINDING FROM THE ONE BELOW, and the branch
                # below would state it wrongly. At rank zero nothing is
                # traded off against anything: no observation responds to
                # any parameter at all, so the sentence about trades would
                # describe a structure that is not there.
                lines.append(
                    "No observation responds to any parameter above its own "
                    "noise floor, so nothing here is identifiable. That is a "
                    "finding about the observations rather than about the "
                    "constants -- a quantity fixed by a conservation law, or "
                    "a mechanism switched off by a starting amount, does this."
                )
            else:
                lines.append(
                    "Not one parameter is separately identifiable: every one "
                    "of them can be traded against another without moving "
                    "any observation."
                )
            lines.append("What the observations cannot separate:")
            for combination in self.combinations():
                lines.append("  - " + combination.describe())
            if not self.basis_is_canonical:
                lines.append(
                    f"Those {len(self.null_space)} directions are one "
                    f"orthonormal basis of the unrecoverable subspace and not "
                    f"the only one; any rotation of them describes the same "
                    f"set. The per-parameter verdict above does not depend on "
                    f"the choice, so read that as the finding and these as an "
                    f"illustration of it."
                )

        uninformative = self.matrix.uninformative()
        if uninformative:
            lines.append(
                f"{len(uninformative)} observation(s) respond to nothing at "
                f"all above their own noise floor: "
                + ", ".join(uninformative)
                + ". They contribute no rank, so removing them from the "
                "experiment would cost nothing."
            )

        lines.append(
            f"Singular values {_format_values(self.singular_values)} against "
            f"a threshold of {self.threshold:.2g}, which is the radius of the "
            f"error ball the rows' own declared accuracies put around this "
            f"matrix -- below it a singular value cannot be told from zero."
        )

        if self.matrix.parameter_values:
            where = ", ".join(
                f"{name}={value:.4g}"
                for name, value in zip(
                    self.parameters, self.matrix.parameter_values
                )
            )
            lines.append(f"Evaluated at {where}.")

        lines.append(
            "Local and practical, not structural: this is the rank of one "
            "finite-difference matrix at one point, for these observations. "
            "A rank deficiency found here is real evidence that these "
            "observations do not separate the parameters it names. Full rank "
            "is not proof of identifiability -- it rules out neither a "
            "deficiency elsewhere in parameter space, nor a global ambiguity "
            "no local method can see, nor a direction that real measurement "
            "error would swallow."
        )
        return " ".join(lines)


def sensitivity_matrix(
    network: Any,
    quantities: Sequence[Any],
    parameters: Optional[Sequence[str]] = None,
    *,
    quantity_names: Optional[Sequence[str]] = None,
) -> SensitivityMatrix:
    """Relative sensitivities of every observation to every parameter.

    `quantities` are `sensitivity.Quantity` objects or plain callables, the
    same vocabulary `sensitivity.analyse` takes, so an observation can be
    anything the caller can read off a network -- a steady state, a settling
    time, an amplitude.

    Refuses rather than dropping anything. See the module docstring: a
    missing row lowers the rank and a missing column removes a parameter
    from the question, so either one turns this into a confident answer to
    something nobody asked.
    """
    names = _parameter_names(network, parameters)
    known = {p.id: float(p.value) for p in network.parameters}

    zeroed = [name for name in names if known[name] == 0.0]
    if zeroed:
        # A relative sensitivity around zero is undefined, so this column
        # cannot exist. Refused here rather than skipped: a parameter absent
        # from the matrix is a parameter absent from the verdict, and the
        # report would then be silent about exactly the constant the caller
        # asked after.
        raise IdentifiabilityUnavailable(
            f"{', '.join(zeroed)} have the value zero, so a fractional "
            f"change in them is undefined and their column of the matrix "
            f"cannot be built. Identifiability is asked in log space -- see "
            f"the module docstring on why -- and zero has no logarithm. "
            f"Either give them the value the model is meant to run at, or "
            f"leave them out of `parameters` and read the answer as being "
            f"about the rest."
        )

    labels = _quantity_names(quantities, quantity_names)
    rows: List[Tuple[float, ...]] = []
    resolutions: List[float] = []
    base_values: List[float] = []

    for label, quantity in zip(labels, quantities):
        try:
            report = _sensitivity_of(
                network, quantity, quantity_name=label, parameters=names
            )
        except SensitivityUnavailable as exc:
            # WRAPPED, WHERE sensitivity.analyse DELIBERATELY DOES NOT.
            #
            # There the reason is already complete and re-explaining it
            # buries it. Here there are several observations and the reason
            # alone does not say which one failed, so naming the row is new
            # information. The original text is carried through intact.
            raise IdentifiabilityUnavailable(
                f"observation {label!r} could not be evaluated, so its row "
                f"is missing. A rank computed without it would be a lower "
                f"bound reported as an answer -- it would call parameters "
                f"unrecoverable that this observation may well separate. "
                f"The reason it could not be evaluated: {exc}"
            ) from exc

        if report.skipped:
            raise IdentifiabilityUnavailable(
                f"observation {label!r} could not be differentiated with "
                f"respect to "
                + "; ".join(f"{k} ({v})" for k, v in report.skipped.items())
                + ". Those columns would be missing from this row only, "
                "which is not a matrix -- and filling them with zero would "
                "assert the observation does not respond to them, which is "
                "the very thing that could not be measured."
            )

        by_name = {s.parameter: s.relative for s in report.sensitivities}
        rows.append(tuple(by_name[name] for name in names))
        resolutions.append(report.resolution)
        base_values.append(report.base_value)

    return SensitivityMatrix(
        quantities=tuple(labels),
        parameters=tuple(names),
        rows=tuple(rows),
        resolutions=tuple(resolutions),
        base_values=tuple(base_values),
        parameter_values=tuple(known[name] for name in names),
    )


def decompose(matrix: SensitivityMatrix) -> IdentifiabilityReport:
    """Rank, null space and per-parameter verdict, by SVD.

    Split from `sensitivity_matrix` so the linear algebra can be driven with
    a matrix written down by hand. The cases where the right answer is known
    in closed form -- a row of (1, -1), a row of (1, 1) -- are the ones worth
    testing hardest, and they should not require a model that happens to
    produce them.
    """
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - dependency is pinned
        raise IdentifiabilityUnavailable(
            "identifiability needs numpy for the SVD, which is in "
            f"requirements.txt but not importable here: {exc}"
        ) from exc

    if not matrix.parameters:
        raise IdentifiabilityUnavailable(
            "no parameters were asked about, so there is nothing whose "
            "identifiability could be reported"
        )

    array = np.array(matrix.rows, dtype=float)
    if not np.all(np.isfinite(array)):
        raise IdentifiabilityUnavailable(
            "the sensitivity matrix contains a non-finite entry, so its "
            "singular values are undefined. A relative sensitivity is "
            "infinite when the observation is zero at this point, which "
            "usually means a starting amount leaves the mechanism switched "
            "off rather than that the parameter has unbounded influence."
        )

    _, singular_values, right = np.linalg.svd(array, full_matrices=True)
    threshold = matrix.threshold
    rank = rank_of(singular_values, threshold)

    # Rows of V^T past the rank span the null space. `full_matrices=True` is
    # what makes that true when there are fewer observations than parameters
    # -- which is the interesting case, and the one where a reduced SVD
    # would return no null space at all for a matrix that is nothing but.
    null_space = tuple(tuple(float(x) for x in row) for row in right[rank:])

    leverage = tuple(
        float(math.sqrt(sum(direction[j] ** 2 for direction in null_space)))
        for j in range(len(matrix.parameters))
    )

    return IdentifiabilityReport(
        matrix=matrix,
        singular_values=tuple(float(s) for s in singular_values),
        threshold=threshold,
        rank=rank,
        null_space=null_space,
        leverage=leverage,
        tolerance=_null_space_tolerance(singular_values, rank, threshold),
    )


def analyse(
    network: Any,
    quantities: Sequence[Any],
    *,
    parameters: Optional[Sequence[str]] = None,
    quantity_names: Optional[Sequence[str]] = None,
) -> IdentifiabilityReport:
    """What these observations of this model could recover.

    The whole question in one call: build the matrix at the model's current
    values, take its rank against the threshold its own accuracy implies,
    and report which parameters that leaves recoverable.
    """
    return decompose(
        sensitivity_matrix(
            network, quantities, parameters, quantity_names=quantity_names
        )
    )


def identifiable_subset(report: IdentifiabilityReport) -> Tuple[str, ...]:
    """The parameters a fit to these observations could return on its own.

    A parameter is in this set exactly when its own axis has no component in
    the null space -- when no trade against another parameter leaves the
    observations unchanged. Basis-independent, so it is a statement about
    the model rather than about which orthonormal basis the SVD happened to
    return.
    """
    return report.identifiable()


def unidentifiable_combinations(
    report: IdentifiabilityReport,
) -> Tuple[Combination, ...]:
    """The directions the observations do not see, in readable form.

    One per dimension of the null space. Unique up to sign when there is one
    of them; one basis of many when there are more, which
    `IdentifiabilityReport.basis_is_canonical` reports and the summary says
    out loud.
    """
    return report.combinations()


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _parameter_names(
    network: Any, parameters: Optional[Sequence[str]]
) -> List[str]:
    known = {p.id: float(p.value) for p in network.parameters}
    names = list(parameters) if parameters is not None else list(known)

    if not names:
        raise IdentifiabilityUnavailable(
            "no parameters were asked about. Identifiability is a question "
            "about a set of constants, and the empty set has no answer worth "
            "printing."
        )
    unknown = [name for name in names if name not in known]
    if unknown:
        raise KeyError(
            f"{unknown} are not parameters of this network. It has: "
            f"{', '.join(sorted(known))}."
        )
    repeated = sorted({n for n in names if names.count(n) > 1})
    if repeated:
        # Two identical columns are linearly dependent by construction, so
        # the rank would come back short and the report would blame the
        # model for a duplicate in the caller's list.
        raise IdentifiabilityUnavailable(
            f"{repeated} appear more than once in the parameter list. A "
            f"repeated column makes the matrix rank-deficient whatever the "
            f"model does, and the report would read as a finding about the "
            f"biology."
        )
    return names


def _quantity_names(
    quantities: Sequence[Any], quantity_names: Optional[Sequence[str]]
) -> List[str]:
    if not quantities:
        raise IdentifiabilityUnavailable(
            "no observations were given. With nothing observed nothing is "
            "identifiable, which is a tautology rather than a finding about "
            "this model -- name the measurements the experiment would "
            "actually make."
        )
    if quantity_names is not None:
        if len(quantity_names) != len(quantities):
            raise IdentifiabilityUnavailable(
                f"{len(quantity_names)} name(s) for {len(quantities)} "
                f"observation(s); a row and its label must be the same thing"
            )
        return list(quantity_names)
    return [
        getattr(quantity, "name", None) or f"observation {index + 1}"
        for index, quantity in enumerate(quantities)
    ]


def _null_space_tolerance(
    singular_values: Sequence[float], rank: int, threshold: float
) -> float:
    """How far the computed null space could be rotated from the true one.

    Wedin's theorem bounds the sine of the largest principal angle between
    the computed and the true null space by the perturbation over the gap
    that separates the null space from the rest of the spectrum. The
    perturbation is the same error ball the threshold came from, plus what
    the SVD itself costs, which is machine epsilon times the largest
    singular value.

    A component of a null direction smaller than this could be zero, so this
    is what decides whether a parameter takes part in a direction -- and, for
    the same reason, whether two exponents in the rendering are equal.

    At rank zero there is no gap: nothing was separated from anything, every
    direction is null, and the honest tolerance is zero, which makes every
    parameter take part in whatever the SVD returns.
    """
    if rank < 1:
        return 0.0
    largest = float(singular_values[0]) if len(singular_values) else 0.0
    gap = float(singular_values[rank - 1])
    return min(1.0, (threshold + MACHINE_PRECISION * largest) / gap)


def _normalised(direction: Sequence[float]) -> Tuple[float, ...]:
    """A null direction scaled so its largest component is +1.

    The SVD returns unit vectors with an arbitrary sign, and (0.707, 0.707)
    does not read as "scale both by the same factor" the way (1, 1) does.
    Scaling changes nothing: a null direction is only defined up to a
    non-zero multiple.
    """
    largest = 0.0
    for value in direction:
        if abs(value) > abs(largest):
            largest = value
    if largest == 0.0:
        return tuple(float(v) + 0.0 for v in direction)
    # The `+ 0.0` turns a negative zero back into a zero. A component that
    # is not there should not print with a sign.
    return tuple(float(v) / largest + 0.0 for v in direction)


def _format_values(values: Sequence[float]) -> str:
    return "[" + ", ".join(f"{v:.3g}" for v in values) + "]"


__all__ = [
    "Combination", "IdentifiabilityReport", "IdentifiabilityUnavailable",
    "SensitivityMatrix",
    "analyse", "decompose", "identifiable_subset", "rank_of",
    "sensitivity_matrix", "singular_value_threshold",
    "unidentifiable_combinations",
]
