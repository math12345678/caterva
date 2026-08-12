"""Markov-chain probability machinery for the Wright-Fisher model."""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple

import numpy as np
def _wf_p_adj(
    p: np.ndarray,
    selection_coefficient: float,
    dominance: float | None,
) -> np.ndarray:
    """Post-selection allele frequency, mirroring simulate_wright_fisher's
    selection step exactly (haploid or diploid-with-dominance scheme)."""
    if selection_coefficient == 0.0:
        return p
    s = selection_coefficient
    if dominance is None:
        return p * (1.0 + s) / (1.0 + p * s)
    h = dominance
    p2 = p * p
    pq = p * (1.0 - p)
    q2 = (1.0 - p) * (1.0 - p)
    w_bar = (p2 * (1.0 + s) + 2.0 * pq * (1.0 + h * s) + q2)
    return (p2 * (1.0 + s) + pq * (1.0 + h * s)) / w_bar  # type: ignore[return-value]


def _binom_pmf_log(k: int, n: int, p: float) -> float:
    """Log of the Binomial(n, p) point mass at k, in lgamma space so it
    never overflows (handles n up to several thousand)."""
    if p == 0.0:
        return 0.0 if k == 0 else -math.inf
    if p == 1.0:
        return 0.0 if k == n else -math.inf
    return (math.lgamma(n + 1) - math.lgamma(k + 1)
            - math.lgamma(n - k + 1) + k * math.log(p)
            + (n - k) * math.log1p(-p))

def wright_fisher_transition_matrix(
    population_size: int,
    mutation_rate: float = 0.0,
    selection_coefficient: float = 0.0,
    dominance: float | None = None,
) -> np.ndarray:
    """The exact Wright-Fisher one-generation transition matrix.

    ``Q[i, j]`` is the probability that a panmictic population with
    ``i`` copies of allele A (out of ``2N``) has ``j`` copies one
    generation later, applying the same per-generation steps as
    ``simulate_wright_fisher``: selection (haploid, or diploid with
    dominance), binomial reproduction over ``2N`` copies, then
    per-copy symmetric mutation. The matrix has shape
    ``(2N+1) x (2N+1)`` and every row sums to 1.

    With ``mutation_rate=0`` states 0 and 2N are absorbing (the chain
    has no way to leave them); with ``mutation_rate > 0`` the chain is
    ergodic (the mutation step is folded in exactly via the
    convolution of the two mutation Binomials, matching the
    simulation's two-step mutation draw).

    Not applicable (as in the simulation) to structured populations:
    the matrix describes a single panmictic deme, so there are no
    ``n_demes``/``migration``/``population_size_series`` parameters.

    Args:
        population_size: diploid census size N per deme
        mutation_rate: per-copy symmetric mutation rate u, in [0, 1)
        selection_coefficient: selective advantage of A (s); > -1
        dominance: None = haploid selection; in [0, 2] for diploid

    Returns:
        the (2N+1) x (2N+1) transition matrix as a float64 ndarray

    Raises:
        ValueError: on invalid parameters
    """
    if isinstance(population_size, (bool, np.bool_)) or not isinstance(
            population_size, (int, np.integer)) or population_size < 1:
        raise ValueError("population_size must be an integer >= 1")
    if isinstance(mutation_rate, (bool, np.bool_)) or not isinstance(
            mutation_rate, (int, float, np.integer, np.floating)):
        raise ValueError("mutation_rate must be a number")
    if math.isnan(mutation_rate) or math.isinf(mutation_rate) \
            or not 0.0 <= mutation_rate < 1.0:
        raise ValueError("mutation_rate must be in [0, 1)")
    if isinstance(selection_coefficient, (bool, np.bool_)) or not isinstance(
            selection_coefficient, (int, float, np.integer, np.floating)):
        raise ValueError("selection_coefficient must be a number")
    if math.isnan(selection_coefficient) or math.isinf(
            selection_coefficient) or selection_coefficient <= -1.0:
        raise ValueError("selection_coefficient must be > -1")
    if dominance is not None:
        if isinstance(dominance, (bool, np.bool_)) or not isinstance(
                dominance, (int, float, np.integer, np.floating)):
            raise ValueError("dominance must be a number or None")
        if not 0.0 <= dominance <= 2.0:
            raise ValueError("dominance must be in [0, 2] or None")

    N = int(population_size)
    K = 2 * N + 1
    copies = np.arange(K, dtype=np.float64)
    p_adj = _wf_p_adj(copies / (2.0 * N),
                      selection_coefficient, dominance)

    Q = np.zeros((K, K), dtype=np.float64)
    log_row = np.empty(K)
    for i in range(K):
        pa = p_adj[i]
        if pa == 0.0:
            Q[i, 0] = 1.0
            continue
        if pa == 1.0:
            Q[i, K - 1] = 1.0
            continue
        for j in range(K):
            log_row[j] = _binom_pmf_log(j, 2 * N, pa)
        Q[i] = np.exp(log_row)
    # Renormalize: log-space exp can shed mass to rounding.
    row_sums = Q.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0.0] = 1.0
    Q /= row_sums

    if mutation_rate > 0.0:
        u = float(mutation_rate)
        M = np.zeros((K, K), dtype=np.float64)
        for k in range(K):
            n_a = 2 * N - k
            pm1 = np.array(
                [math.exp(_binom_pmf_log(m1, k, u)) for m1 in range(k + 1)])
            pm2 = np.array(
                [math.exp(_binom_pmf_log(m2, n_a, u))
                 for m2 in range(n_a + 1)])
            target = np.arange(n_a + 1)
            for m1 in range(k + 1):
                if pm1[m1] > 0.0:
                    M[k, k - m1 + target] += pm1[m1] * pm2
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            Q = Q @ M
    return Q

def _wf_chain_setup(
    starting_frequency: float,
    population_size: int,
    selection_coefficient: float,
    dominance: float | None,
) -> Tuple[np.ndarray, int]:
    """Shared validation + transition-matrix build for the exact-chain
    functions. Returns ``(Q, i0)`` where ``i0`` is the state closest
    to ``starting_frequency * 2N`` copies of A."""
    if isinstance(starting_frequency, (bool, np.bool_)) or not isinstance(
            starting_frequency, (int, float, np.integer, np.floating)):
        raise ValueError("starting_frequency must be a number")
    if not 0.0 <= starting_frequency <= 1.0:
        raise ValueError("starting_frequency must be in [0, 1]")
    Q = wright_fisher_transition_matrix(
        population_size, 0.0, selection_coefficient, dominance)
    K = Q.shape[0]
    i0 = int(round(starting_frequency * (K - 1)))
    return Q, i0


def _wf_fixation_vector(q: np.ndarray) -> np.ndarray:
    """Absorption probabilities of the all-A state from every interior
    state, for a transition matrix ``Q`` with absorbing states 0 and
    ``K-1``: ``f[j]`` = P(hit all-A before all-a | start with j+1
    copies of A). Solves ``(I - Q_t) f = p_top`` with boundaries
    ``f_0 = 0``, ``f_{K-1} = 1``."""
    K = q.shape[0]
    transient = slice(1, K - 1)
    q_t = q[transient, transient]
    p_top = q[transient, K - 1]
    return np.linalg.solve(np.eye(q_t.shape[0]) - q_t, p_top)

def wright_fisher_fixation_probability(
    starting_frequency: float,
    population_size: int,
    selection_coefficient: float = 0.0,
    dominance: float | None = None,
) -> float:
    """Probability that allele A fixes, exact for the discrete
    Wright-Fisher chain (no diffusion approximation).

    This is the exact value of which ``kimura_fixation_probability``
    (Kimura 1962) is the diffusion approximation: it solves the
    absorption system of ``wright_fisher_transition_matrix`` for
    P(hit the all-A state before the all-a state). For neutrality the
    martingale property makes it exactly ``starting_frequency``; for
    genic selection it matches Kimura's closed form within the
    diffusion error (~0.01-0.02); and — unlike the diffusion
    approximation — it stays reliable for ``dominance > 1``
    (over/underdominance), where Kimura's formula is documented as
    unreliable (error up to ~0.25).

    Requires ``mutation_rate = 0`` semantics: with mutation the chain
    has no absorbing all-A state and fixation never strictly occurs,
    so the function takes no mutation parameter.

    Args:
        starting_frequency: initial frequency of allele A, in [0, 1]
        population_size: diploid census size N
        selection_coefficient: selective advantage of A (s); > -1
        dominance: None = haploid selection; in [0, 2] for diploid

    Returns:
        the exact fixation probability in [0, 1] (0.0 at frequency 0,
        1.0 at frequency 1)

    Raises:
        ValueError: on invalid parameters
    """
    Q, i0 = _wf_chain_setup(
        starting_frequency, population_size,
        selection_coefficient, dominance)
    if i0 <= 0:
        return 0.0
    if i0 >= Q.shape[0] - 1:
        return 1.0
    f = _wf_fixation_vector(Q)
    return float(f[i0 - 1])

def wright_fisher_expected_fixation_time(
    starting_frequency: float,
    population_size: int,
    selection_coefficient: float = 0.0,
    dominance: float | None = None,
) -> float:
    """Expected time to fixation of allele A, exact for the discrete
    Wright-Fisher chain (no diffusion approximation).

    Solves the Markov chain whose transition matrix is
    ``wright_fisher_transition_matrix``: the expected number of
    generations to hit the all-A state (2N copies), conditional on
    fixation occurring, starting from ``starting_frequency``. This is
    the exact value of which ``expected_fixation_time`` (Kimura &
    Ohta's 1969 diffusion closed form) is the continuous
    approximation — the two agree to within ~1-2 % and converge as N
    grows. ``selection_coefficient``/``dominance`` enter through the
    exact transition probabilities, so the result is valid for
    selection of any strength in (0, 1].

    Requires ``mutation_rate = 0`` semantics: with mutation the chain
    has no absorbing all-A state and fixation never strictly occurs,
    so the function takes no mutation parameter.

    Args:
        starting_frequency: initial frequency of allele A, in (0, 1]
        population_size: diploid census size N
        selection_coefficient: selective advantage of A (s); > -1
        dominance: None = haploid selection; in [0, 2] for diploid

    Returns:
        the expected generations to fixation, given that fixation
        occurs (0.0 when the allele is already fixed)

    Raises:
        ValueError: on invalid parameters, or when the allele cannot
            fix from the starting frequency (``starting_frequency``
            of 0)
    """
    if isinstance(starting_frequency, (bool, np.bool_)) or not isinstance(
            starting_frequency, (int, float, np.integer, np.floating)):
        raise ValueError("starting_frequency must be a number")
    if not 0.0 <= starting_frequency <= 1.0:
        raise ValueError("starting_frequency must be in [0, 1]")
    if starting_frequency == 0.0:
        raise ValueError("an allele at frequency 0 never fixes")
    if starting_frequency == 1.0:
        return 0.0
    Q, i0 = _wf_chain_setup(
        starting_frequency, population_size,
        selection_coefficient, dominance)
    if i0 <= 0:
        raise ValueError("an allele at frequency 0 never fixes")
    if i0 >= Q.shape[0] - 1:
        return 0.0

    K = Q.shape[0]
    transient = slice(1, K - 1)
    Q_t = Q[transient, transient]
    p_top = Q[transient, K - 1]
    f = _wf_fixation_vector(Q)
    # w[j]: E[T * 1_{fixation}], solving (I - Q_t) w = Q_t f + p_top
    # with boundaries w_0 = w_top = 0; then E[T | fixation] = w / f.
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        rhs = Q_t @ f + p_top
    w = np.linalg.solve(np.eye(Q_t.shape[0]) - Q_t, rhs)
    f_val = f[i0 - 1]
    if f_val <= 1e-15:
        raise ValueError(
            "allele cannot fix from this starting frequency")
    return float(w[i0 - 1] / f_val)

def wright_fisher_expected_loss_time(
    starting_frequency: float,
    population_size: int,
    selection_coefficient: float = 0.0,
    dominance: float | None = None,
) -> float:
    """Expected time to loss of allele A, exact for the discrete
    Wright-Fisher chain (no diffusion approximation).

    The mirror image of ``wright_fisher_expected_fixation_time``:
    solves the same transition matrix for ``E[T | loss]``, the mean
    number of generations to hit the all-a state (0 copies of A),
    conditional on loss occurring. Under neutrality it equals
    ``wright_fisher_expected_fixation_time(1 - p)`` by symmetry, and
    both are approximated within ~1-2 % by the Kimura & Ohta 1969
    closed forms (``expected_loss_time`` /
    ``expected_fixation_time``). With selection, the loss time is
    exact for any strength in (0, 1].

    Note the boundary convention difference from the closed form:
    ``expected_loss_time`` returns the diffusion limit 4N at
    ``p0 = 1``, while the exact chain treats the fixed state as
    absorbing and raises (the allele cannot be lost).

    Requires ``mutation_rate = 0`` semantics: with mutation the chain
    has no absorbing all-a state and loss never strictly occurs, so
    the function takes no mutation parameter.

    Args:
        starting_frequency: initial frequency of allele A, in [0, 1)
        population_size: diploid census size N
        selection_coefficient: selective advantage of A (s); > -1
        dominance: None = haploid selection; in [0, 2] for diploid

    Returns:
        the expected generations to loss, given that loss occurs
        (0.0 when the allele is already lost)

    Raises:
        ValueError: on invalid parameters, or when the allele cannot
            be lost from the starting frequency (``starting_frequency``
            of 1)
    """
    Q, i0 = _wf_chain_setup(
        starting_frequency, population_size,
        selection_coefficient, dominance)
    K = Q.shape[0]
    if i0 <= 0:
        return 0.0
    if i0 >= K - 1:
        raise ValueError(
            "an allele fixed at frequency 1 cannot be lost")
    transient = slice(1, K - 1)
    Q_t = Q[transient, transient]
    p_bottom = Q[transient, 0]
    f = _wf_fixation_vector(Q)
    # v[j]: E[T * 1_{loss}], solving (I - Q_t) v = Q_t (1 - f) + p_bottom
    # with boundaries v_0 = v_top = 0; then E[T | loss] = v / (1 - f).
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        rhs = Q_t @ (1.0 - f) + p_bottom
    v = np.linalg.solve(np.eye(Q_t.shape[0]) - Q_t, rhs)
    f_val = f[i0 - 1]
    if 1.0 - f_val <= 1e-15:
        raise ValueError(
            "allele cannot be lost from this starting frequency")
    return float(v[i0 - 1] / (1.0 - f_val))


def wright_fisher_expected_absorption_time(
    starting_frequency: float,
    population_size: int,
    selection_coefficient: float = 0.0,
    dominance: float | None = None,
) -> float:
    """Expected time until allele A is either fixed or lost, exact for
    the discrete Wright-Fisher chain.

    The unconditional mean number of generations to hit either
    absorbing boundary (0 or 2N copies of A): solves
    ``h = (I - Q_t)^{-1} 1`` on the transient states. The diffusion
    closed form (Kimura & Ohta 1969) is::

        t_bar = -4N (p0 ln p0 + (1 - p0) ln (1 - p0))

    which the exact chain approximates within ~1-2 % (at p0 = 0.5 both
    give 4N ln(2) ~= 2.77N).

    Markov-property consistency with the conditional quantities:
    ``absorption_time = fixation_time * P_fix + loss_time * (1 - P_fix)``
    (checked in the test suite).

    Requires ``mutation_rate = 0`` semantics: with mutation the chain
    has no absorbing states and no strictly-defined absorption time,
    so the function takes no mutation parameter.

    Args:
        starting_frequency: initial frequency of allele A, in [0, 1]
        population_size: diploid census size N
        selection_coefficient: selective advantage of A (s); > -1
        dominance: None = haploid selection; in [0, 2] for diploid

    Returns:
        the expected generations to absorption at either boundary
        (0.0 when already fixed or lost)

    Raises:
        ValueError: on invalid parameters
    """
    Q, i0 = _wf_chain_setup(
        starting_frequency, population_size,
        selection_coefficient, dominance)
    K = Q.shape[0]
    if i0 <= 0 or i0 >= K - 1:
        return 0.0
    transient = slice(1, K - 1)
    Q_t = Q[transient, transient]
    h = np.linalg.solve(np.eye(Q_t.shape[0]) - Q_t,
                        np.ones(Q_t.shape[0]))
    return float(h[i0 - 1])

def _normalise_stationary_vector(v: np.ndarray) -> np.ndarray:
    """Orient and normalise a Perron-Frobenius probability vector.

    Eigenvectors are defined only up to sign.  This helper deliberately
    orients the vector before clamping so an all-negative eigenvector is not
    turned into all zeros and then divided by zero.
    """
    vector = np.asarray(v, dtype=np.float64)
    if not np.all(np.isfinite(vector)):
        raise ValueError("failed to compute the stationary distribution")
    if vector.sum() < 0.0:
        vector = -vector
    vector = np.maximum(vector, 0.0)
    total = vector.sum()
    if total == 0.0:
        raise ValueError("failed to compute the stationary distribution")
    return vector / total


def wright_fisher_stationary_vector(
    population_size: int,
    mutation_rate: float,
    selection_coefficient: float = 0.0,
    dominance: float | None = None,
) -> List[float]:
    """Stationary distribution over A-copy counts of the exact
    Wright-Fisher chain with mutation.

    Computes the Perron-Frobenius eigenvector of
    ``wright_fisher_transition_matrix`` (with ``mutation_rate > 0``
    the chain is ergodic, so the stationary distribution is the
    unique left eigenvector with eigenvalue 1, normalized to sum to
    1): ``pi Q = pi``.

    This is the exact finite-population counterpart of Wright's
    ``Beta(4Nu, 4Nu)`` diffusion density
    (``wright_stationary_distribution``): the two agree within the
    diffusion error, and both match the simulated allele-frequency
    spectrum. It is also the first behavioral check of the mutation
    convolution in the transition matrix -- the vector's shape is
    determined entirely by how the two mutation Binomials are folded
    in.

    Returns ``pi[i]`` = stationary probability of exactly ``i``
    copies of A (out of ``2N``), ``i = 0 .. 2N``.

    Args:
        population_size: diploid census size N
        mutation_rate: per-copy symmetric mutation rate u, in (0, 1)
        selection_coefficient: selective advantage of A (s); > -1
        dominance: None = haploid selection; in [0, 2] for diploid

    Returns:
        the stationary distribution as a list of length 2N+1

    Raises:
        ValueError: on invalid parameters (including
            ``mutation_rate`` of 0, which would make the chain
            absorbing with no unique stationary distribution)
    """
    if isinstance(mutation_rate, (bool, np.bool_)) or not isinstance(
            mutation_rate, (int, float, np.integer, np.floating)):
        raise ValueError("mutation_rate must be a number")
    if math.isnan(mutation_rate) or math.isinf(mutation_rate) \
            or not 0.0 < mutation_rate < 1.0:
        raise ValueError("mutation_rate must be in (0, 1)")
    Q = wright_fisher_transition_matrix(
        population_size, mutation_rate,
        selection_coefficient, dominance)
    from scipy.linalg import eig
    # Left eigenvectors are the right eigenvectors of Q^T; the
    # stationary distribution is the one for eigenvalue 1.
    eigvals, eigvecs = eig(Q.T)
    idx = int(np.argmin(np.abs(eigvals - 1.0)))
    v = _normalise_stationary_vector(np.real(eigvecs[:, idx]))
    return [float(x) for x in v]

def wright_stationary_distribution(
    points: Sequence[float],
    mutation_rate: float,
    population_size: int,
) -> List[float]:
    """Wright's (1931) stationary distribution of allele frequency under
    mutation-drift balance.

    For a diploid population of size N with per-copy symmetric mutation
    rate u, the equilibrium distribution of allele frequency is
    Beta(4Nu, 4Nu)::

        phi(p) = C * p^(4Nu-1) * (1-p)^(4Nu-1)

    where C normalizes the density. With 4Nu < 1 the density is
    unbounded at the edges (most populations fixed); with 4Nu > 1 it is
    a single central hump (polymorphism maintained).

    Args:
        points: frequencies at which to evaluate the density
        mutation_rate: per-copy symmetric mutation rate u
        population_size: diploid census size N

    Returns:
        the density evaluated at each point (0.0 outside (0, 1),
        math.inf at the boundaries when 4Nu < 1)

    Raises:
        ValueError: if mutation_rate or population_size is not positive
    """
    if mutation_rate <= 0.0:
        raise ValueError("mutation_rate must be > 0")
    if population_size <= 0:
        raise ValueError("population_size must be positive")

    a = 4.0 * mutation_rate * population_size
    from scipy.special import gammaln
    log_norm = gammaln(2.0 * a) - 2.0 * gammaln(a)

    out: List[float] = []
    for p in points:
        if p <= 0.0 or p >= 1.0:
            out.append(0.0 if a > 1.0 else math.inf)
        else:
            log_d = ((a - 1.0) * math.log(p)
                     + (a - 1.0) * math.log(1.0 - p) + log_norm)
            out.append(math.exp(log_d))
    return out
