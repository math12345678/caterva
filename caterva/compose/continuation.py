"""Following ONE steady-state branch, including around its turning points.

WHAT A PARAMETER SWEEP CANNOT DO, AND WHY IT IS NOT A RESOLUTION PROBLEM
------------------------------------------------------------------------
`bifurcation.py` sweeps a parameter and re-solves from scratch at each
value. That is what a researcher does by hand, and it works right up to the
point where the branch turns back on itself.

Take the saddle-node normal form, dx/dt = mu - x^2. Its steady states are
x = +/- sqrt(mu): a stable arm and an unstable one, meeting at mu = 0 and
existing nowhere below it. Sweep mu downwards and the solver finds states
until mu = 0 and then finds nothing, so the report says "the steady states
vanished between these two samples". That sentence is true and it is also
the most a sweep can say.

The branch did not vanish. It TURNED. And no finer sweep recovers it,
because the failure is not resolution:

  * above the fold there are TWO states at every mu, so "the state at
    mu = 0.3" does not name a point on the branch;
  * at the fold the branch is vertical in mu -- dx/dmu is infinite -- so mu
    is not a coordinate on it there at all;
  * below the fold there is nothing, and a sweep in mu has nowhere to step.

The fix is to stop using the parameter as the independent variable. This
module parameterises the branch by its own ARCLENGTH, which is a coordinate
everywhere on it including at the turn, and follows it with a
predictor-corrector: step along the tangent, then correct back onto the
branch with Newton on an AUGMENTED system -- the rate equations plus one
extra equation saying how far along the branch to land.

The augmented system is the whole trick. The rate equations alone are
singular at a fold (the Jacobian has a zero eigenvalue, which is what a fold
IS), so Newton on them fails there. Bordering them with the arclength
constraint produces a system that is non-singular at the fold, so the
corrector converges at exactly the place a sweep breaks down.

WHAT A FOLD IS HERE, AND WHY IT IS DETECTED THE WAY IT IS
---------------------------------------------------------
`bifurcation.py` infers a fold from "the number of states changed between
two samples". That is a symptom, and it has other causes: a root find that
converged at one sample and not the next produces the same evidence, which
is why that module hedges every label it attaches.

A fold has an actual definition, and continuation can test it directly. The
unit tangent to the branch is a vector (dx/ds, dp/ds). A fold is where the
parameter reaches an extremum along the branch, so it is where dp/ds passes
through zero and changes sign. That is a sign change in one number that is
computed at every step anyway, and it does not depend on any root find
succeeding or failing.

Located folds are then REFINED, by bisecting on that sign with the same
corrector, to a stated |dp/ds|. The parameter value at a fold is second
order in that quantity -- near a turning point p varies quadratically in
arclength -- so the reported fold parameter is much more accurate than the
bracket it came from, and the fold record carries both.

THE HONEST LIMIT: ONE BRANCH, ONE STARTING POINT
------------------------------------------------
Continuation follows the connected component of the solution set through
the point it was given. It does not, and cannot, find anything
disconnected from that point.

This matters most for the models this repository is usually pointed at. A
toggle switch has two stable states. Whether they lie on one branch that
folds twice, or on two branches that never meet, is a fact about that
model -- and following one of them says NOTHING about the other. A `Branch`
that never found a fold is not evidence that the model is monostable; it is
evidence about one curve.

So: `analysis.analyse` searches globally and reports what it converged to.
This module follows one curve exactly. They answer different questions and
neither substitutes for the other. `Branch.summary()` says so in the
report itself rather than only here, because the report is what gets read.

Two further limits, stated rather than discovered later:

  * A branch that CLOSES on itself is followed until `max_points` and the
    closure is not detected, so a closed loop reads as a long branch.
  * Continuation is not a proof of existence between its points. It solves
    at each accepted point, to the residual each point carries; the curve
    drawn between two points is an interpolation.

ARCLENGTH IN A MIXED SPACE HAS NO NATURAL UNIT
----------------------------------------------
The step is a distance in (state, parameter) space, and those coordinates
are in different units -- mM and 1/s, say. Adding them in quadrature is
what every continuation code does and it is dimensionally meaningless; the
consequence is that a step size means something only relative to the
model's own numbers.

Rather than pretend otherwise, the step bounds DEFAULT to fractions of the
starting point's own magnitude, and `Branch` reports the bounds that
actually applied. A fixed 0.05 would be a millimetre step for a kcat of
1e4 and a mile for a Km of 1e-6, and one of those runs would take a
hundred thousand steps while the other stepped clean over the fold.

CONSERVED TOTALS ARE HELD FIXED, BECAUSE THEY ARE NOT PARAMETERS
-----------------------------------------------------------------
A network with conservation laws does not have isolated steady states: it
has one per leaf of the foliation the laws define, and the rate equations
alone are rank-deficient by exactly the number of laws. So the residual
here is the rate equations WITH the conserved totals appended as
constraints, fixed at the totals of the starting state -- the same
construction `analysis.analyse` uses, for the same reason.

A conserved total is an initial condition, not a parameter. Letting it
drift would follow a different leaf at every step, which is a curve through
a family of different models rather than a branch of one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

try:
    from .analysis import (
        JACOBIAN_STEP, MARGINAL_EIGENVALUE, RESIDUAL_TOLERANCE,
        STATE_DISTINCT_TOLERANCE, classify, derivative_function, jacobian,
    )
except ImportError:  # pragma: no cover - flat import
    from analysis import (  # type: ignore[no-redef]
        JACOBIAN_STEP, MARGINAL_EIGENVALUE, RESIDUAL_TOLERANCE,
        STATE_DISTINCT_TOLERANCE, classify, derivative_function, jacobian,
    )

#: Initial arclength step, as a FRACTION of the starting point's magnitude.
#: See the module docstring on why this cannot be an absolute number.
DEFAULT_STEP_FRACTION = 0.05

#: Largest step the adaptive rule may grow to, as the same fraction. A cap
#: is needed at all because growth after easy steps is geometric and would
#: otherwise step straight over a fold and land on the far arm without ever
#: seeing dp/ds change sign -- the one event this module exists to catch.
MAX_STEP_FRACTION = 0.5

#: Smallest step before the run gives up. Also a fraction: an absolute floor
#: would be unreachable for a model whose numbers are 1e-6 and instant for
#: one whose numbers are 1e6.
MIN_STEP_FRACTION = 1e-8

#: What a failed step multiplies the step by, and what an easy one does.
#:
#: Halving on failure is the standard choice and needs no defence. Growing
#: by 1.6 rather than by 2 does: growth compounds, and a factor of two
#: reaches the cap in four easy steps, which is how a run steps over a fold
#: immediately after the flat, easy stretch that always precedes one.
STEP_SHRINK = 0.5
STEP_GROW = 1.6

#: A step is "easy" when the corrector converged within this many Newton
#: iterations, and only easy steps are allowed to grow the step size.
EASY_ITERATIONS = 3

#: Newton iterations the corrector is allowed before the step is rejected.
#: Rejection is cheap here -- the step shrinks and the same predictor runs
#: again -- so this is deliberately low. A corrector that needs twelve
#: iterations from a predictor a short step away is not converging; it is
#: wandering, and the answer it eventually reaches may be on another part
#: of the curve.
MAX_CORRECTOR_ITERATIONS = 12

#: The tangent may turn by at most this much (as a cosine) in one accepted
#: step: 0.5 is 60 degrees.
#:
#: This is what keeps a large step from cutting a corner. Without it, a step
#: taken along the tangent near a sharp turn can be corrected onto a point
#: further round the branch than intended -- or onto a different part of it
#: entirely -- and the intermediate stretch, which is where the fold lives,
#: is never visited. Failing the check shrinks the step and re-predicts,
#: which is exactly the right response: the same corner, taken slower.
MAX_TURN_COSINE = 0.5

#: Points before the run stops on its own. A budget, not a result.
DEFAULT_MAX_POINTS = 400

#: |dp/ds| below which a bisected point is accepted as the fold.
#:
#: The quantity that is actually driven to zero. The FOLD'S PARAMETER VALUE
#: is then accurate to second order in this, because p varies quadratically
#: in arclength at a turning point -- which is why this can be loose-looking
#: and still locate mu = 0 of the normal form to about 1e-9.
FOLD_TANGENT_TOLERANCE = 1e-9

#: Bisections allowed per fold. Each halves the arclength bracket, so 60 is
#: far more than the tolerance above ever needs and exists to bound the
#: pathological case rather than to be reached.
MAX_FOLD_BISECTIONS = 60

#: Relative singular-value threshold below which the augmented Jacobian is
#: called rank deficient and the tangent undefined.
#:
#: Not a numerical nicety. At a fold the state Jacobian IS singular and the
#: augmented matrix is not -- the parameter column fills the deficiency.
#: When it does not, the two are singular together, which is what a
#: transcritical or pitchfork bifurcation looks like: two branches crossing,
#: with no tangent that picks one of them out. Refusing there is correct;
#: guessing a direction would silently switch branches.
RANK_TOLERANCE = 1e-10

#: |dp/ds| at the STARTING point below which `direction` does not name a
#: direction, because the branch is already turning there.
INITIAL_DIRECTION_TOLERANCE = 1e-8

STOPPED_MAX_POINTS = "reached the maximum number of points"
STOPPED_OUT_OF_RANGE = "the parameter left the requested range"
STOPPED_CORRECTOR = "the corrector failed at the smallest permitted step"
STOPPED_TANGENT = "the branch has no unique tangent at the smallest permitted step"


class ContinuationError(RuntimeError):
    """A branch could not be started or could not be followed.

    Distinct from a short branch. A branch that stops after four points has
    been followed and has a `stopped_because`; this is raised when there is
    nothing to follow, and the message says which of the two happened.
    """


# ---------------------------------------------------------------------------
# What comes out
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BranchPoint:
    """One solved point on the branch, with the tangent through it."""

    #: The continuation parameter's value here.
    parameter: float
    #: species id -> concentration.
    state: Mapping[str, float]
    #: Arclength from the starting point, in the model's own mixed units.
    arclength: float
    #: The unit tangent's state part, species id -> dx/ds.
    tangent_state: Mapping[str, float]
    #: The unit tangent's parameter part, dp/ds. THE number fold detection
    #: reads: a fold is where this changes sign.
    tangent_parameter: float
    #: Largest absolute time derivative here. Carried rather than reduced to
    #: a boolean so a reader can see how converged each point is, exactly as
    #: `analysis.FixedPoint` does.
    residual: float
    eigenvalues: Tuple[complex, ...] = ()
    classification: str = ""
    #: False when a species is negative by more than rounding. KEPT, not
    #: filtered: continuing around a fold routinely runs the branch into
    #: negative concentrations, which the equations have and the system
    #: cannot reach. Dropping them would hide the turn that was the reason
    #: for continuing in the first place.
    physical: bool = True
    #: Newton iterations the corrector needed to land here.
    corrector_iterations: int = 0

    @property
    def stable(self) -> bool:
        from_analysis = ("stable", "stable spiral")
        return self.classification in from_analysis

    def describe(self) -> str:
        coordinates = ", ".join(
            f"{name}={value:.4g}" for name, value in sorted(self.state.items())
        )
        parts = [f"{self.parameter:.6g}: {coordinates}"]
        if self.classification:
            parts.append(self.classification)
        parts.append(f"dp/ds={self.tangent_parameter:+.3g}")
        if not self.physical:
            parts.append("NEGATIVE concentrations -- not physically reachable")
        return "; ".join(parts)


@dataclass(frozen=True)
class Fold:
    """A turning point: where dp/ds changed sign along the branch."""

    parameter: str
    #: The estimated parameter value at the turn.
    value: float
    #: species id -> concentration at the turn.
    state: Mapping[str, float]
    #: |dp/ds| achieved at the reported point. THE measure of how close to
    #: the turn this actually is. The error in `value` is second order in it.
    tangent_parameter: float
    #: Parameter values of the two continuation points whose tangents had
    #: opposite dp/ds. Both lie on the SAME side of the fold, so the width
    #: of this bracket is not the accuracy of `value` -- see `describe`.
    bracket: Tuple[float, float]
    arclength: float
    #: True when bisection drove |dp/ds| below `FOLD_TANGENT_TOLERANCE`.
    refined: bool = True
    #: Why refinement stopped early, when it did.
    detail: str = ""

    def describe(self) -> str:
        head = (
            f"fold at {self.parameter} = {self.value:.6g}: the branch turns "
            f"here, so two steady states meet and annihilate"
        )
        if self.refined:
            return (
                head
                + f", located by bisecting on the sign of dp/ds down to "
                f"|dp/ds| = {abs(self.tangent_parameter):.2g}. The error in "
                f"the value quoted is SECOND order in that, because the "
                f"parameter varies quadratically in arclength at a turning "
                f"point -- it is not the width of the bracket "
                f"[{self.bracket[0]:.6g}, {self.bracket[1]:.6g}], whose two "
                f"ends both sit on the same side of the turn."
            )
        return (
            head
            + f", bracketed between {self.parameter} = {self.bracket[0]:.6g} "
            f"and {self.bracket[1]:.6g} but NOT refined ({self.detail}). "
            f"|dp/ds| got down to {abs(self.tangent_parameter):.2g}; the "
            f"value quoted is the best point reached and is no better than "
            f"that."
        )


@dataclass(frozen=True)
class Branch:
    """One continued solution branch, and what was found along it."""

    parameter: str
    points: Tuple[BranchPoint, ...]
    folds: Tuple[Fold, ...] = ()
    #: Why the run ended. Always set: a branch that ends has a reason, and
    #: "it ended" is not one a reader can act on.
    stopped_because: str = ""
    #: The step bounds that actually applied, so the run is reproducible.
    #: Defaults are derived from the starting point's magnitude, so the
    #: constants at the top of this module are not enough to reproduce it.
    step_bounds: Tuple[float, float] = (0.0, 0.0)
    #: Predictor steps that were rejected and retried smaller. Reported
    #: because a branch with many of them was hard to follow, and a reader
    #: judging the result should know that.
    steps_rejected: int = 0

    @property
    def parameter_values(self) -> Tuple[float, ...]:
        return tuple(point.parameter for point in self.points)

    @property
    def arclength(self) -> float:
        return self.points[-1].arclength if self.points else 0.0

    @property
    def physical_points(self) -> Tuple[BranchPoint, ...]:
        return tuple(point for point in self.points if point.physical)

    @property
    def turned(self) -> bool:
        """Did the branch reach a turning point? Not "is the model bistable"."""
        return bool(self.folds)

    def parameter_range(self) -> Optional[Tuple[float, float]]:
        if not self.points:
            return None
        values = self.parameter_values
        return (min(values), max(values))

    def state_values(self, species: str) -> Tuple[float, ...]:
        """One species along the branch, in point order.

        Refuses an unknown species rather than returning an empty tuple: an
        empty plot of a real branch is a lie a typo can produce.
        """
        if not self.points:
            return ()
        if species not in self.points[0].state:
            raise KeyError(
                f"{species!r} is not a species of this branch. It has: "
                f"{', '.join(sorted(self.points[0].state))}."
            )
        return tuple(float(point.state[species]) for point in self.points)

    def summary(self) -> str:
        if not self.points:
            return (
                f"No points were continued for {self.parameter}. A branch "
                f"with no points is a run that did not start, not a model "
                f"with no steady states."
            )

        low, high = self.parameter_range()  # type: ignore[misc]
        lines = [
            f"Followed one steady-state branch through {len(self.points)} "
            f"point(s), over an arclength of {self.arclength:.4g}, with "
            f"{self.parameter} between {low:.6g} and {high:.6g}."
        ]

        if self.folds:
            lines.append(
                f"{len(self.folds)} turning point(s), where dp/ds changes "
                f"sign:"
            )
            for fold in self.folds:
                lines.append("  - " + fold.describe())
            lines.append(
                "A sweep in this parameter cannot follow the branch past "
                "any of those: above a fold two states share every "
                "parameter value and at the fold itself the branch is "
                "vertical, so the parameter is not a coordinate on it there."
            )
        else:
            lines.append(
                f"No turning point was crossed: dp/ds kept its sign over "
                f"the whole run, so {self.parameter} was a usable coordinate "
                f"on this stretch and a sweep would have found the same "
                f"states. That is a statement about the stretch followed, "
                f"not about the branch -- it stopped because "
                f"{self.stopped_because}."
            )

        unphysical = len(self.points) - len(self.physical_points)
        if unphysical:
            lines.append(
                f"{unphysical} point(s) are at negative concentrations. They "
                f"are kept rather than filtered: the equations have them, "
                f"the system cannot reach them, and continuing around a fold "
                f"is exactly how a branch gets there."
            )

        stable = sum(1 for point in self.points if point.stable)
        if stable and stable < len(self.points):
            lines.append(
                f"{stable} of the {len(self.points)} points are stable and "
                f"the rest are not, so this one branch carries both an "
                f"attracting arm and a repelling one -- which is what a "
                f"branch that folds looks like."
            )

        if self.steps_rejected:
            lines.append(
                f"{self.steps_rejected} predictor step(s) were rejected and "
                f"retried smaller."
            )

        lines.append(f"The run ended because {self.stopped_because}.")
        lines.append(
            "THIS IS ONE BRANCH, FROM ONE STARTING POINT. Continuation "
            "follows the connected curve through the point it was given and "
            "finds nothing disconnected from it. A toggle switch's two "
            "stable states may sit on branches that never meet, and "
            "following one of them says nothing whatever about the other. "
            "For the question 'what states does this model have', use "
            "analysis.analyse, which searches globally and reports what it "
            "converged to."
        )
        return " ".join(lines)


# ---------------------------------------------------------------------------
# The augmented system
# ---------------------------------------------------------------------------


def _conservation_rows(network: Any, species: Sequence[str]) -> List[List[float]]:
    """Conservation laws as float rows over the species order.

    `ReactionNetwork` derives these EXACTLY, over `Fraction`, from the
    stoichiometry. They become floats only here, at the boundary with a
    numerical solver, so the exact result stays the authority and this is
    visibly an approximation of it.
    """
    try:
        laws = network.conservation_laws()
    except Exception:  # noqa: BLE001 - a network that cannot report them
        return []
    return [[float(law.get(name, 0)) for name in species] for law in laws]


class _System:
    """`G(x, p) = 0`: the rate equations plus the conserved totals.

    The rate equations are rank-deficient by exactly the number of
    conservation laws, so on their own they do not define a curve in
    (state, parameter) space -- they define a sheet, and continuation on a
    sheet has no defined direction. Appending the totals cuts the sheet down
    to the leaf the starting state is on. See the module docstring.

    Rate laws are recompiled whenever the parameter moves, because
    `analysis.derivative_function` bakes parameter values into the closure
    it returns. The corrector evaluates at p and at p +/- h repeatedly, so a
    small cache keyed on the exact parameter value turns that from the
    dominant cost back into a negligible one.
    """

    #: Compiled right-hand sides kept at once. Three would do -- p, p+h,
    #: p-h -- and eight leaves room for a corrector that revisits a value.
    CACHE_LIMIT = 8

    def __init__(
        self,
        network: Any,
        parameter: str,
        species: Sequence[str],
        anchor_state: Sequence[float],
    ) -> None:
        self._network = network
        self._parameter = parameter
        self.species = tuple(species)
        self.dimension = len(self.species)
        self.laws = _conservation_rows(network, self.species)
        self.totals = [
            sum(row[i] * float(anchor_state[i]) for i in range(self.dimension))
            for row in self.laws
        ]
        self._cache: Dict[float, Callable[[Sequence[float]], List[float]]] = {}

    def rhs_at(self, value: float) -> Callable[[Sequence[float]], List[float]]:
        key = float(value)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        if len(self._cache) >= self.CACHE_LIMIT:
            self._cache.clear()
        altered = replace(
            self._network,
            parameters=tuple(
                replace(p, value=key) if p.id == self._parameter else p
                for p in self._network.parameters
            ),
        )
        rhs, _ = derivative_function(altered)
        self._cache[key] = rhs
        return rhs

    def rates(self, u: Sequence[float]) -> List[float]:
        """The rate equations alone, which is what a residual is measured on.

        The conserved totals are satisfied by construction and including
        them would flatter the residual -- the same reasoning
        `analysis.analyse` records where it measures its own.
        """
        return list(self.rhs_at(float(u[self.dimension]))(list(u[: self.dimension])))

    def residual(self, u: Sequence[float]) -> List[float]:
        values = self.rates(u)
        for row, total in zip(self.laws, self.totals):
            values.append(
                sum(row[i] * float(u[i]) for i in range(self.dimension)) - total
            )
        return values

    def matrix(self, u: Sequence[float], np: Any) -> Any:
        """dG/d(x, p): the state Jacobian, the parameter column, the laws.

        The parameter column is a central difference with the same step
        `analysis.jacobian` uses for the state columns, so both halves of
        the matrix carry the same approximation rather than one being
        quietly better than the other. Its accuracy affects only how fast
        Newton converges and which way the tangent points to about eight
        digits; it does not enter the solved point, because the residual
        `G` is evaluated exactly.
        """
        n = self.dimension
        state = [float(v) for v in u[:n]]
        value = float(u[n])

        state_block = np.array(jacobian(self.rhs_at(value), state), dtype=float)

        h = JACOBIAN_STEP * max(abs(value), 1.0)
        up = np.array(self.rhs_at(value + h)(state), dtype=float)
        down = np.array(self.rhs_at(value - h)(state), dtype=float)
        parameter_column = ((up - down) / (2.0 * h)).reshape(-1, 1)

        top = np.hstack([state_block, parameter_column])
        if not self.laws:
            return top
        law_block = np.array(self.laws, dtype=float)
        bottom = np.hstack([law_block, np.zeros((law_block.shape[0], 1))])
        return np.vstack([top, bottom])


# ---------------------------------------------------------------------------
# Predictor, corrector, tangent
# ---------------------------------------------------------------------------


def _tangent(
    system: _System,
    u: Any,
    np: Any,
    previous: Any = None,
    prefer: Optional[float] = None,
) -> Tuple[Any, bool, str]:
    """The unit tangent to the branch at `u`, oriented to keep going forwards.

    The tangent is the null direction of the augmented Jacobian, taken from
    an SVD rather than by solving a bordered system. The SVD costs more and
    buys the rank test: it says whether there IS a unique tangent, which a
    solve would answer by returning whatever the linear algebra produced.

    Orientation is by continuity -- the new tangent is flipped to agree with
    the previous one. This is the entire mechanism that lets the branch turn:
    nothing here asks the parameter to keep increasing, so when the branch
    reverses in the parameter the tangent simply follows it, and dp/ds
    changes sign.
    """
    matrix = system.matrix(u, np)
    try:
        _, singular, vt = np.linalg.svd(matrix)
    except np.linalg.LinAlgError:
        return None, False, "the augmented Jacobian has no SVD at this point"
    if singular.size == 0 or not np.all(np.isfinite(singular)):
        return None, False, "the augmented Jacobian is not finite at this point"

    # Rank must be exactly the number of state equations: one less than the
    # number of unknowns, which is what leaves a one-dimensional tangent.
    index = system.dimension - 1
    if singular[index] <= RANK_TOLERANCE * singular[0]:
        return (
            None,
            False,
            (
                "the augmented Jacobian is rank deficient here, so the "
                "solution set is not locally a curve and no tangent picks "
                "out a direction. This is what a transcritical or pitchfork "
                "bifurcation looks like -- two branches crossing -- and "
                "guessing a direction there would silently switch branches"
            ),
        )

    tangent = np.array(vt[-1], dtype=float)
    norm = float(np.linalg.norm(tangent))
    if norm == 0.0 or not math.isfinite(norm):
        return None, False, "the tangent came back as a zero vector"
    tangent = tangent / norm

    if previous is not None:
        if float(tangent @ previous) < 0.0:
            tangent = -tangent
    elif prefer is not None and tangent[-1] * prefer < 0.0:
        tangent = -tangent
    return tangent, True, ""


def _correct(
    system: _System,
    predicted: Any,
    tangent: Any,
    tolerance: float,
    np: Any,
    max_iterations: int = MAX_CORRECTOR_ITERATIONS,
) -> Tuple[Any, int]:
    """Newton onto `G(u) = 0` and `tangent . (u - predicted) = 0`.

    The second equation is what makes this work at a fold. It says "land on
    the plane through the predicted point perpendicular to the tangent",
    which is a condition on arclength rather than on the parameter, so it
    stays meaningful where the parameter stops being a coordinate.

    The step is a least-squares solve, not a square one. With conservation
    laws the system is overdetermined and consistent -- the appended rows
    are implied by the rate equations, not independent of them -- which
    `lstsq` handles and a square solve cannot even be handed.

    Returns `(None, iterations)` on failure. The caller shrinks the step and
    tries again; it does not fall back to anything, because a fallback that
    found a different point would return a plausible answer about the wrong
    branch.
    """
    u = np.array(predicted, dtype=float)
    # The conserved totals and the arclength row are LINEAR, so they reach
    # roundoff in one step -- but roundoff on a total of 1e6 is 1e-10, which
    # an absolute 1e-9 would judge as non-convergence for a reason that is
    # entirely floating point. They get a relative floor; the rate
    # equations, which are the physical claim, get `tolerance`.
    linear_floor = 1e-8 * max(1.0, float(np.max(np.abs(u))))

    for iteration in range(max_iterations + 1):
        rates = system.rates(u)
        if not all(math.isfinite(value) for value in rates):
            return None, iteration
        residual = system.residual(u)
        constraint = float(np.dot(tangent, u - predicted))

        physical = max(abs(value) for value in rates) if rates else 0.0
        linear = max(
            [abs(value) for value in residual[len(rates):]] + [abs(constraint)]
        )
        if physical <= tolerance and linear <= linear_floor:
            return u, iteration
        if iteration == max_iterations:
            break

        matrix = system.matrix(u, np)
        augmented = np.vstack([matrix, np.array(tangent, dtype=float).reshape(1, -1)])
        target = -np.concatenate([np.array(residual, dtype=float), [constraint]])
        try:
            delta, *_ = np.linalg.lstsq(augmented, target, rcond=None)
        except np.linalg.LinAlgError:
            return None, iteration
        if not np.all(np.isfinite(delta)):
            return None, iteration
        u = u + delta
        if not np.all(np.isfinite(u)):
            return None, iteration

    return None, max_iterations


def _locate_fold(
    system: _System,
    parameter: str,
    low_u: Any,
    low_t: Any,
    high_u: Any,
    high_t: Any,
    tolerance: float,
    np: Any,
    arclength: float,
) -> Fold:
    """Bisect between two points whose dp/ds have opposite signs.

    Bisection rather than a secant, and on the SIGN of dp/ds rather than on
    its value. The sign is exactly the definition of the turn and cannot be
    fooled; a secant on a quantity that is nearly linear through zero would
    be faster and would occasionally step outside the bracket, which here
    means leaving the piece of branch the bracket was evidence about.

    Each trial point is corrected onto the branch with the same corrector,
    on the plane perpendicular to the chord between the two ends. That plane
    is transverse to the branch at a fold -- the chord is nearly all state
    and nearly no parameter there -- which is why this converges at the one
    place a parameter-based method cannot.
    """
    bracket = (float(low_u[-1]), float(high_u[-1]))
    low_u, low_t = np.array(low_u, dtype=float), np.array(low_t, dtype=float)
    high_u, high_t = np.array(high_u, dtype=float), np.array(high_t, dtype=float)

    if abs(low_t[-1]) <= abs(high_t[-1]):
        best_u, best_t = low_u, low_t
    else:
        best_u, best_t = high_u, high_t
    detail = ""

    for _ in range(MAX_FOLD_BISECTIONS):
        if abs(best_t[-1]) <= FOLD_TANGENT_TOLERANCE:
            break
        chord = high_u - low_u
        length = float(np.linalg.norm(chord))
        if length == 0.0:
            detail = "the bracketing points collapsed onto each other"
            break
        predicted = 0.5 * (low_u + high_u)
        corrected, _iterations = _correct(
            system, predicted, chord / length, tolerance, np
        )
        if corrected is None:
            detail = "the corrector failed on a bisected point"
            break
        tangent, ok, why = _tangent(system, corrected, np, previous=low_t)
        if not ok:
            detail = why
            break
        if abs(tangent[-1]) < abs(best_t[-1]):
            best_u, best_t = corrected, tangent
        if (tangent[-1] > 0.0) == (low_t[-1] > 0.0):
            low_u, low_t = corrected, tangent
        else:
            high_u, high_t = corrected, tangent
    else:
        detail = (
            f"{MAX_FOLD_BISECTIONS} bisections did not bring |dp/ds| below "
            f"{FOLD_TANGENT_TOLERANCE:g}"
        )

    # `bool(...)` rather than the numpy scalar the comparison returns: a
    # `np.bool_` on a frozen dataclass prints as `np.True_` in every report
    # that shows the record, which reads as a leaked implementation detail.
    refined = bool(abs(best_t[-1]) <= FOLD_TANGENT_TOLERANCE)
    if refined:
        detail = ""
    return Fold(
        parameter=parameter,
        value=float(best_u[-1]),
        state={
            name: float(best_u[i]) for i, name in enumerate(system.species)
        },
        tangent_parameter=float(best_t[-1]),
        bracket=bracket,
        arclength=arclength,
        refined=refined,
        detail=detail,
    )


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


def continue_branch(
    network: Any,
    parameter: str,
    *,
    initial_state: Optional[Mapping[str, float]] = None,
    direction: float = 1.0,
    max_points: int = DEFAULT_MAX_POINTS,
    step: Optional[float] = None,
    min_step: Optional[float] = None,
    max_step: Optional[float] = None,
    parameter_range: Optional[Tuple[float, float]] = None,
    corrector_tolerance: float = RESIDUAL_TOLERANCE,
    locate_folds: bool = True,
) -> Branch:
    """Follow the steady-state branch through one point, by arclength.

    `initial_state` is where the branch is picked up: a species id ->
    concentration mapping, which is the shape `analysis.FixedPoint.state`
    already has. Omitting it starts from the network's declared initial
    condition, which is a guess at a steady state and usually not one -- so
    the first thing this does is solve, and refuse if that solve fails.

    `direction` is +1 to set off toward increasing parameter and -1 toward
    decreasing. It orients the FIRST tangent and nothing after it: once
    moving, the branch is followed by continuity of the tangent, which is
    what lets it turn and come back. Following the other way is a second
    call with the sign flipped, and the two halves are one branch.

    `parameter_range` stops the run when the parameter leaves it. The last
    point may lie just outside, because a step lands where arclength takes
    it and truncating it back would report a point nothing solved for.

    Refuses rather than returning a short branch when there is no steady
    state to start from. "No branch here" and "a branch that ended early"
    are different findings and a caller that cannot tell them apart will
    read the first as the second.
    """
    try:
        import numpy as np
        from scipy.optimize import least_squares
    except ImportError as exc:  # pragma: no cover - dependency is pinned
        raise ContinuationError(
            "continuation needs numpy and scipy, which are in "
            f"requirements.txt but not importable here: {exc}"
        ) from exc

    known = {p.id: float(p.value) for p in network.parameters}
    if parameter not in known:
        raise KeyError(
            f"{parameter!r} is not a parameter of this network. It has: "
            f"{', '.join(sorted(known))}."
        )
    if max_points < 2:
        raise ValueError(
            f"max_points={max_points} cannot produce a branch; a single "
            f"point is a steady state, which analysis.analyse already gives"
        )
    if direction == 0:
        raise ValueError(
            "direction must be +1 (toward increasing parameter) or -1 "
            "(toward decreasing); 0 names no direction to set off in"
        )

    if getattr(network, "rate_rules", ()):
        # NOT a limitation to discover at the end of a run.
        #
        # `analysis.derivative_function` compiles reactions only. A species
        # driven by a rate rule gets dx/dt = 0 from it, which is a different
        # model that happens to have steady states -- and continuation would
        # follow a branch of the wrong system, confidently and to a small
        # residual.
        targets = ", ".join(rule.target for rule in network.rate_rules)
        raise ContinuationError(
            f"this network drives {targets} by rate rule(s), and the "
            f"derivative function this module continues is compiled from "
            f"REACTIONS only -- a rate-rule species would be held at "
            f"dx/dt = 0. Continuing it would follow a branch of a different "
            f"model. Use compose/simulate.py, which does evaluate rate "
            f"rules, or express the mechanism as reactions."
        )

    _rhs_declared, species = derivative_function(network)
    if not species:
        raise ContinuationError(
            "a network with no species has no branch to continue"
        )

    start_state = _starting_state(network, species, initial_state)
    base_value = known[parameter]
    system = _System(network, parameter, species, start_state)

    # -- the starting point ------------------------------------------------
    #
    # Solved with least_squares rather than the Newton corrector: the
    # declared initial condition may be nowhere near a steady state, and
    # Newton from far away either diverges or lands somewhere arbitrary.
    # After this the corrector is always started a short step from a solved
    # point, which is where Newton belongs.
    def at_base(x: Any) -> List[float]:
        return system.residual(list(x) + [base_value])

    try:
        outcome = least_squares(
            at_base, list(start_state), xtol=1e-14, ftol=1e-14, gtol=1e-14
        )
        solved = [float(v) for v in outcome.x]
        rates = system.rates(solved + [base_value])
        residual = max(abs(value) for value in rates)
    except Exception as exc:  # noqa: BLE001
        raise ContinuationError(
            f"the solve for a starting point on the branch failed at "
            f"{parameter} = {base_value:g}: {exc}"
        ) from exc

    if not math.isfinite(residual) or residual > corrector_tolerance:
        raise ContinuationError(
            f"no steady state at {parameter} = {base_value:g} from the "
            f"starting state given: the best the solver reached leaves a "
            f"largest time derivative of {residual:.3g}, against a tolerance "
            f"of {corrector_tolerance:g}. Continuation FOLLOWS a branch; it "
            f"does not find one, so there is nothing here to follow. Run "
            f"analysis.analyse at this parameter value to see whether the "
            f"model has a steady state at all -- if it has none, the branch "
            f"you are after may exist at another parameter value, or may "
            f"lie past a fold and have to be picked up from the other side."
        )

    u = np.array(solved + [base_value], dtype=float)
    scale = max(float(np.linalg.norm(u)), 1.0)
    ds = float(step) if step is not None else DEFAULT_STEP_FRACTION * scale
    ds_max = float(max_step) if max_step is not None else MAX_STEP_FRACTION * scale
    ds_min = float(min_step) if min_step is not None else MIN_STEP_FRACTION * scale
    if not (0.0 < ds_min <= ds_max) or not (ds_min <= ds <= ds_max):
        raise ValueError(
            f"step bounds must satisfy 0 < min_step <= step <= max_step; got "
            f"min_step={ds_min:g}, step={ds:g}, max_step={ds_max:g}"
        )

    tangent, ok, why = _tangent(
        system, u, np, prefer=math.copysign(1.0, direction)
    )
    if not ok:
        raise ContinuationError(
            f"the branch has no tangent at {parameter} = {base_value:g}: {why}"
        )
    if abs(tangent[-1]) < INITIAL_DIRECTION_TOLERANCE:
        raise ContinuationError(
            f"dp/ds = {tangent[-1]:.3g} at the starting point, so the branch "
            f"is already turning there and 'increase the parameter' does not "
            f"name a direction to set off in. Start from a state further "
            f"from the turn -- the fold is what you would have found, and "
            f"you are on it."
        )

    points: List[BranchPoint] = [
        _point(system, u, tangent, 0.0, 0, np)
    ]
    folds: List[Fold] = []
    arclength = 0.0
    rejected = 0
    stopped = STOPPED_MAX_POINTS

    while len(points) < max_points:
        predicted = u + ds * tangent
        corrected, iterations = _correct(
            system, predicted, tangent, corrector_tolerance, np
        )

        failure = ""
        new_tangent = None
        if corrected is None:
            failure = STOPPED_CORRECTOR
        else:
            new_tangent, ok, why = _tangent(system, corrected, np, previous=tangent)
            if not ok:
                failure = STOPPED_TANGENT
            elif float(new_tangent @ tangent) < MAX_TURN_COSINE:
                # Not an error: the step was too long for how sharply the
                # branch turns here. Shrinking and re-predicting takes the
                # same corner slower, which is the whole point of an
                # adaptive step.
                failure = STOPPED_CORRECTOR

        if failure:
            if ds <= ds_min:
                stopped = failure
                break
            rejected += 1
            ds = max(ds_min, ds * STEP_SHRINK)
            continue

        arclength += ds
        previous_point = points[-1]
        point = _point(system, corrected, new_tangent, arclength, iterations, np)
        points.append(point)

        if locate_folds and (
            (previous_point.tangent_parameter > 0.0)
            != (point.tangent_parameter > 0.0)
        ):
            folds.append(
                _locate_fold(
                    system, parameter, u, tangent, corrected, new_tangent,
                    corrector_tolerance, np, arclength - 0.5 * ds,
                )
            )

        u, tangent = corrected, new_tangent
        if iterations <= EASY_ITERATIONS:
            ds = min(ds_max, ds * STEP_GROW)

        if parameter_range is not None:
            low, high = min(parameter_range), max(parameter_range)
            if not (low <= point.parameter <= high):
                stopped = STOPPED_OUT_OF_RANGE
                break

    return Branch(
        parameter=parameter,
        points=tuple(points),
        folds=tuple(folds),
        stopped_because=stopped,
        step_bounds=(ds_min, ds_max),
        steps_rejected=rejected,
    )


def _starting_state(
    network: Any,
    species: Sequence[str],
    initial_state: Optional[Mapping[str, float]],
) -> List[float]:
    """The state to start solving from, in the network's species order.

    Ordered by the network rather than by the mapping, because everything
    downstream reads state positionally and a dictionary that happened to
    iterate differently would put each concentration on the wrong species --
    a solve that converges to a confident wrong answer.
    """
    if initial_state is None:
        return [float(s.initial) for s in network.species]

    unknown = sorted(set(initial_state) - set(species))
    if unknown:
        raise ContinuationError(
            f"the starting state names {unknown}, which this network has no "
            f"species for. It has: {', '.join(species)}. A name that does "
            f"not exist is silently dropped by a dict lookup, and the solve "
            f"would then start from a different state than the one asked for."
        )
    missing = [name for name in species if name not in initial_state]
    if missing:
        raise ContinuationError(
            f"the starting state gives no value for {missing}. Every species "
            f"needs one: a missing coordinate defaulted to zero is a "
            f"different starting point, and the branch found from it is a "
            f"different branch."
        )
    return [float(initial_state[name]) for name in species]


def _point(
    system: _System,
    u: Any,
    tangent: Any,
    arclength: float,
    iterations: int,
    np: Any,
) -> BranchPoint:
    """Package a solved point, with the eigenvalues of the state Jacobian.

    Stability is computed here rather than left to the caller because the
    interesting fact about a folded branch is that ONE curve carries a
    stable arm and an unstable one, and a list of coordinates does not show
    it.

    As many near-zero eigenvalues as there are conservation laws are
    dropped, exactly as `analysis.analyse` drops them and for the same
    reason: each law contributes a structural zero, the dynamics do not move
    along a conserved direction, and leaving them in makes every conserved
    system read as `marginal` -- which says nothing about whether the state
    attracts ON its leaf.
    """
    n = system.dimension
    state = [float(v) for v in u[:n]]
    value = float(u[n])
    rhs = system.rhs_at(value)

    rates = rhs(state)
    residual = max(abs(v) for v in rates) if rates else 0.0

    eigenvalues: Tuple[complex, ...] = ()
    classification = ""
    try:
        matrix = np.array(jacobian(rhs, state), dtype=float)
        eigenvalues = tuple(complex(v) for v in np.linalg.eigvals(matrix))
    except Exception:  # noqa: BLE001 - a point without eigenvalues is still a point
        eigenvalues = ()

    if eigenvalues and system.laws:
        ordered = sorted(eigenvalues, key=lambda v: abs(v))
        for structural in [v for v in ordered[: len(system.laws)] if abs(v) <= 1e-6]:
            remaining = list(eigenvalues)
            remaining.remove(structural)
            eigenvalues = tuple(remaining)
    if eigenvalues:
        classification = classify(eigenvalues)

    return BranchPoint(
        parameter=value,
        state={name: state[i] for i, name in enumerate(system.species)},
        arclength=float(arclength),
        tangent_state={
            name: float(tangent[i]) for i, name in enumerate(system.species)
        },
        tangent_parameter=float(tangent[n]),
        residual=float(residual),
        eigenvalues=eigenvalues,
        classification=classification,
        physical=all(v > -STATE_DISTINCT_TOLERANCE for v in state),
        corrector_iterations=int(iterations),
    )


__all__ = [
    "Branch", "BranchPoint", "ContinuationError", "Fold",
    "continue_branch",
    "DEFAULT_STEP_FRACTION", "MAX_STEP_FRACTION", "MIN_STEP_FRACTION",
    "STEP_SHRINK", "STEP_GROW", "EASY_ITERATIONS",
    "MAX_CORRECTOR_ITERATIONS", "MAX_TURN_COSINE", "DEFAULT_MAX_POINTS",
    "FOLD_TANGENT_TOLERANCE", "MAX_FOLD_BISECTIONS", "RANK_TOLERANCE",
    "INITIAL_DIRECTION_TOLERANCE",
    "STOPPED_MAX_POINTS", "STOPPED_OUT_OF_RANGE", "STOPPED_CORRECTOR",
    "STOPPED_TANGENT",
]
