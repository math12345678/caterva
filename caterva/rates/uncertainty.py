"""Where the error bar on each rate comes from, and what that decides.

THREE SOURCES, EXACTLY ONE, AND NEVER AN INVENTED ONE
-----------------------------------------------------
`compose/fitting.py` refuses to construct an observation without an error
bar, and its module docstring gives the reason: a weighted fit, its
chi-square and every interval are expressed in units of the stated errors,
so a sigma this code chose would appear in the answer as though it had been
measured. The same refusal holds here. There are three honest ways to supply
the error, and the caller names one:

  column      a per-row standard deviation in the file (`sigma (uM/min)`).
              The errors are the experiment's own and are taken as known:
              intervals use the normal quantile, model comparisons the
              chi-square, and the fit's chi-square is a test of the model
              and the error bars together.

  replicates  a pooled standard deviation from the replicate sets (rows
              with identical conditions), with its degrees of freedom
              stated: sum over sets of (n_i - 1). `--error-model constant`
              pools the variance; `proportional` pools the squared
              coefficient of variation and scales it by each condition's
              mean, the error structure of an assay whose noise grows with
              its signal. The error is ESTIMATED, so intervals use Student's
              t on those degrees of freedom and comparisons use F. The
              chi-square is then not separate evidence: most of it is the
              pure error the sigma was estimated from, and the lack-of-fit F
              test is what asks whether the model's shape is right.

  residuals   ordinary least squares, with sigma estimated from the fit's
              own scatter: s^2 = SS / (n - p). This is what R's `nls`
              reports, and it ASSUMES THE MODEL IS RIGHT: a model of the
              wrong shape inflates s and widens every interval, and the
              scatter cannot then test the model it was computed from. So
              no goodness-of-fit chi-square is printed for it; the report
              says why, and points to the lack-of-fit test, which needs
              replicates and does not use s.

With none of these the fit is refused, naming the three.

WHY THE PROPORTIONAL SCALE IS THE CONDITION'S MEAN
--------------------------------------------------
Proportional error means sigma_i = CV * (true rate at i). The true rate is
unknown; the choices are the observation itself, the mean of the
observations at that condition, or the model's prediction. The model's
prediction makes the weights move with the parameters, so the quantity
minimised is no longer a weighted sum of squares with fixed weights and the
chi-square loses its distribution. The single observation gives a low
reading a large weight because it is low. The condition's mean is fixed
before the fit, averages the replicates it was pooled from, and is what the
CV was computed against, so it is used, and the methods paragraph says so.
A condition measured once has only its one rate for a mean, so its scale IS
the single observation, with the bias described above; the methods paragraph
says that too. The alternative, a scale from a first fit, would make the
weights depend on a model chosen before the comparison of models.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from caterva.rates.table import Dataset

KNOWN = "column"
POOLED = "replicates"
RESIDUAL = "residuals"
SOURCES = (KNOWN, POOLED, RESIDUAL)
ERROR_MODELS = ("constant", "proportional")


class NoUncertainty(ValueError):
    """No error source was given, or two were: refused, exit code 3."""


@dataclass(frozen=True)
class Uncertainty:
    source: str
    #: Per row, in the rate's unit. Ones for RESIDUAL, whose scale is
    #: estimated after the fit.
    sigma: Tuple[float, ...]
    #: Degrees of freedom of a POOLED estimate.
    dof: Optional[int] = None
    error_model: Optional[str] = None
    #: The pooled standard deviation (constant) or coefficient of variation
    #: (proportional).
    pooled: Optional[float] = None
    #: Replicate sets that contributed to the pooling.
    sets: int = 0

    @property
    def estimated(self) -> bool:
        return self.source != KNOWN

    def describe(self, rate_unit: str) -> str:
        if self.source == KNOWN:
            return "per-row standard deviations from the file, taken as known"
        if self.source == POOLED:
            if self.error_model == "proportional":
                return (f"pooled from {self.sets} replicate set(s): coefficient of variation "
                        f"{self.pooled:.3g} ({self.dof} degrees of freedom), scaled by each "
                        f"condition's mean rate")
            return (f"pooled from {self.sets} replicate set(s): standard deviation "
                    f"{self.pooled:.4g} {rate_unit} ({self.dof} degrees of freedom)")
        return ("estimated from the fit's own residuals (ordinary least squares), which "
                "assumes the model is right")


def _replicate_sets(data: Dataset) -> Dict[Tuple[object, ...], List[int]]:
    sets: Dict[Tuple[object, ...], List[int]] = {}
    for row in range(len(data)):
        sets.setdefault(data.condition(row), []).append(row)
    return sets


def replicate_summary(data: Dataset) -> Tuple[int, int]:
    """(replicate sets, degrees of freedom they give): what `--sigma-from
    replicates` would pool, without pooling it."""
    sets = [rows for rows in _replicate_sets(data).values() if len(rows) >= 2]
    return len(sets), sum(len(rows) - 1 for rows in sets)


def condition_means(data: Dataset) -> np.ndarray:
    """Each row's condition mean, the scale a proportional error uses."""
    rate = np.asarray(data.rate, dtype=float)
    out = np.empty(len(data))
    for rows in _replicate_sets(data).values():
        out[rows] = rate[rows].mean()
    return out


def resolve(data: Dataset, source: Optional[str], error_model: Optional[str] = None) -> Uncertainty:
    """The error bars for this dataset, or a refusal that names the options."""
    has_column = data.sigma is not None
    if source is None:
        source = KNOWN if has_column else None
    if source is None:
        raise NoUncertainty(
            "no uncertainty was given for the rates, and this fit will not invent one: "
            "the weights, every interval and every test are expressed in units of the "
            "error bars, so a chosen sigma would appear in the answer as if measured. "
            "Give exactly one of: (1) a per-row standard deviation column in the file, "
            "e.g. 'sigma (uM/min)'; (2) --sigma-from replicates, which pools the spread "
            "of rows with identical conditions (add --error-model proportional if the "
            "noise grows with the rate); (3) --sigma-from residuals, ordinary least "
            "squares with sigma estimated from the fit's own scatter, which assumes the "
            "model is right."
        )
    if source not in SOURCES:
        raise NoUncertainty(f"--sigma-from must be one of {', '.join(SOURCES[1:])}, not {source!r}")
    if error_model is not None and source != POOLED:
        raise NoUncertainty(
            "--error-model says how replicate spreads are pooled, so it needs --sigma-from "
            "replicates; with a sigma column the errors are the file's, and with residuals "
            "they are the fit's"
        )
    if source != KNOWN and has_column:
        raise NoUncertainty(
            f"the file has a standard-deviation column and --sigma-from {source} was also "
            f"given. Exactly one source of uncertainty is used, and choosing between two "
            f"silently would hide which one the intervals mean. Remove the column, or drop "
            f"--sigma-from."
        )
    n = len(data)
    if source == KNOWN:
        if not has_column:
            raise NoUncertainty(
                "the uncertainty was to come from a standard-deviation column, and the file "
                "has none (looked for 'sigma'; name another with --sigma-column)")
        return Uncertainty(KNOWN, tuple(float(s) for s in data.sigma))
    if source == RESIDUAL:
        return Uncertainty(RESIDUAL, tuple(1.0 for _ in range(n)))

    model = error_model or "constant"
    if model not in ERROR_MODELS:
        raise NoUncertainty(f"--error-model must be constant or proportional, not {model!r}")
    rate = np.asarray(data.rate, dtype=float)
    sets = [rows for rows in _replicate_sets(data).values() if len(rows) >= 2]
    dof = sum(len(rows) - 1 for rows in sets)
    if dof < 1:
        raise NoUncertainty(
            "--sigma-from replicates needs at least one condition measured more than once "
            "(two rows with the same substrate, inhibitor and group), and every condition "
            "in this file was measured once. Give a sigma column or use --sigma-from "
            "residuals."
        )
    if model == "constant":
        ss = sum(float(((rate[rows] - rate[rows].mean()) ** 2).sum()) for rows in sets)
        pooled = math.sqrt(ss / dof)
        if pooled <= 0:
            raise NoUncertainty(
                "the replicates agree exactly, so their pooled standard deviation is zero; a "
                "zero error bar would give every row infinite weight. Give the instrument's "
                "precision as a sigma column instead.")
        sigma = np.full(n, pooled)
    else:
        means = condition_means(data)
        if np.any(means <= 0):
            raise NoUncertainty(
                "a proportional error model scales each row's error by its condition's mean "
                "rate, and at least one condition's mean is zero or negative, so it has no "
                "proportional error. Use --error-model constant.")
        ss = sum(float((((rate[rows] - rate[rows].mean()) / rate[rows].mean()) ** 2).sum())
                 for rows in sets)
        pooled = math.sqrt(ss / dof)
        if pooled <= 0:
            raise NoUncertainty(
                "the replicates agree exactly, so their pooled coefficient of variation is "
                "zero. Give the instrument's precision as a sigma column instead.")
        sigma = pooled * means
    return Uncertainty(POOLED, tuple(float(s) for s in sigma), dof=dof, error_model=model,
                       pooled=pooled, sets=len(sets))


def pure_error(rate: Sequence[float], sigma: Sequence[float],
               conditions: Sequence[object]) -> Tuple[float, int, int]:
    """(weighted pure-error sum of squares, its degrees of freedom, the number
    of distinct conditions) -- the replicate scatter that no model of the
    conditions can remove (Draper & Smith, Applied Regression Analysis).
    Rows with equal `conditions` keys are replicates. The lack-of-fit test
    (discriminate.lack_of_fit) calls this on the rows of one fit."""
    rate = np.asarray(rate, dtype=float)
    weight = 1.0 / np.asarray(sigma, dtype=float) ** 2
    sets: Dict[object, List[int]] = {}
    for row, key in enumerate(conditions):
        sets.setdefault(key, []).append(row)
    ss = 0.0
    for rows in sets.values():
        w = weight[rows]
        mean = float((w * rate[rows]).sum() / w.sum())
        ss += float((w * (rate[rows] - mean) ** 2).sum())
    return ss, len(rate) - len(sets), len(sets)


__all__ = [
    "KNOWN", "POOLED", "RESIDUAL", "SOURCES", "ERROR_MODELS", "NoUncertainty", "Uncertainty",
    "resolve", "pure_error", "condition_means", "replicate_summary",
]
