"""The four reference distributions the reports use, in one place.

The chi-square tail and the normal quantile are `compose/fitting.py`'s own
(`chi_squared_tail`, `_z_for`), reused rather than written a second time.
fitting.py never needed Student's t or Fisher's F, because it refuses to
estimate the measurement error from its own residuals; this package does
estimate it, from replicates or (when asked) from the residuals, and then t
and F are the right references. They come from `scipy.special`, which the
fit's optimiser already requires, rather than from a second hand-written
continued fraction. Each is checked in the tests against an identity it must
satisfy: F(1, nu) is the square of t(nu), and chi-square(2)'s tail is
exp(-x/2).
"""
from __future__ import annotations

import math
from typing import Optional

from caterva.compose.fitting import _z_for, chi_squared_tail


def z_for(level: float) -> float:
    """Two-sided normal quantile for a confidence level (fitting.py's)."""
    return _z_for(level)


def t_for(level: float, dof: float) -> float:
    """Two-sided Student's t quantile for a confidence level."""
    from scipy.special import stdtrit

    return float(stdtrit(dof, 1.0 - (1.0 - level) / 2.0))


def chi2_tail(statistic: float, dof: int) -> Optional[float]:
    """P(chi-square(dof) >= statistic), fitting.py's."""
    if statistic <= 0:
        return 1.0
    return chi_squared_tail(statistic, dof)


def f_tail(statistic: float, dof_num: float, dof_den: float) -> Optional[float]:
    """P(F(dof_num, dof_den) >= statistic)."""
    from scipy.special import fdtrc

    if dof_num <= 0 or dof_den <= 0 or not math.isfinite(statistic):
        return None
    if statistic <= 0:
        return 1.0
    return float(fdtrc(dof_num, dof_den, statistic))


def boundary_tail(one_df_tail: Optional[float], statistic: float) -> Optional[float]:
    """The p-value of a one-constant restriction on the boundary of the
    parameter space: the 50:50 mixture of a point mass at zero and the
    one-degree-of-freedom reference (Self & Liang 1987, J. Am. Stat. Assoc.
    82:605). Half the ordinary tail when the statistic is positive, and 1
    when it is zero, because half of all datasets drawn under the restriction
    put the general model's optimum exactly on the boundary."""
    if one_df_tail is None:
        return None
    if statistic <= 0:
        return 1.0
    return 0.5 * one_df_tail


__all__ = ["z_for", "t_for", "chi2_tail", "f_tail", "boundary_tail"]
