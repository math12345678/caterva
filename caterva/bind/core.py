"""From a cited inhibition constant to a binding free energy a simulation can be held to.

ΔG°bind = RT ln(Ki / c°), c° = 1 M, at the temperature the Ki was measured
at. That line is textbook; what this module adds is everything the line
leaves out, because each omission is a way to validate a free-energy
calculation against the wrong number:

* **Which molecule.** A Ki belongs to the compound in the row, never to a
  molecule its commentary mentions ("competitive versus NADH" is what the
  inhibitor competes with). See brenda_client._compound_cell.
* **Which binding event.** Only some inhibition modes make Ki a
  dissociation constant of the state a simulation usually models. A
  competitive Ki is Kd for inhibitor + free enzyme. An uncompetitive Ki is
  Kd for inhibitor + enzyme-substrate complex, so it validates a ternary
  simulation and not an apo one. A mixed-type row gives one of two
  constants and does not say which. The mode is read from the row, and a
  row whose mode does not fit the simulated state is excluded, by name.
* **At what temperature.** ΔG scales with T. A row without one gets no ΔG
  at a guessed temperature; it gets the range over 4-37 °C, the span the
  corpus's assays cover, and says so.
* **How well the literature agrees with itself.** Two measurements of one
  constant typically differ several-fold. A computed ΔG inside that spread
  cannot be called right or wrong by it, and the report says how wide the
  band is in kcal/mol before it says anything about agreement.

Nothing here is estimated from a model; every number is a recorded row or
arithmetic on one.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

#: Gas constant, kJ mol^-1 K^-1 (CODATA 2018, exact).
R_KJ = 8.314462618e-3
KJ_PER_KCAL = 4.184
#: Temperatures used when a row reports none: the coldest and warmest assay
#: temperatures in the LDH Ki corpus (Gadus morhua at 4 °C, human at 37 °C).
#: A stated range, not a guess at the missing value.
UNSTATED_T_RANGE_C = (4.0, 37.0)

#: "isozyme H4", "isoform 2", "LDH-A": the protein a row measured, when the
#: commentary names one. BRENDA files isoforms of one EC under one organism.
_ISOFORM = re.compile(
    r"\b(?:isozyme|isoenzyme|isoform)\s+([A-Za-z0-9-]+)|\b([A-Z]{2,5}-[A-Z0-9]{1,2})\b"
)


def read_isoform(commentary: Optional[str]) -> Optional[str]:
    m = _ISOFORM.search(commentary or "")
    return (m.group(1) or m.group(2)) if m else None


_MODE = re.compile(
    r"\b(non-?competitive|uncompetitive|competitive|mixed(?:-type)?|partial(?:ly)?\s+\w+)\b"
    r"(?:\s+(?:inhibition\s+)?(?:versus|vs\.?|with respect to)\s+([^,;]+))?",
    re.I,
)

#: What each mode's Ki is the dissociation constant OF, and so which
#: simulated state it can validate.
MODE_MEANING = {
    "competitive": ("free", "Kd of inhibitor + free enzyme (the site the competing ligand uses)"),
    "noncompetitive": ("either", "Kd of inhibitor for free enzyme and enzyme-substrate complex alike"),
    "uncompetitive": ("ternary", "Kd of inhibitor + enzyme-substrate complex; the apo enzyme does not bind it"),
    "mixed": ("ambiguous", "one of two unequal constants (Ki or Ki'), and the row does not say which"),
    "partial": ("ambiguous", "a partial inhibitor: Ki is a fitted parameter, not cleanly a Kd"),
    "unstated": ("unknown", "inhibition mode not stated, so which binding event this is is unknown"),
}


def dg_kj(ki_mM: float, temperature_c: float) -> float:
    """Standard binding free energy (kJ/mol) for a Ki in mM at T (°C), c° = 1 M."""
    if ki_mM <= 0:
        raise ValueError(f"Ki must be positive, got {ki_mM}")
    return R_KJ * (temperature_c + 273.15) * math.log(ki_mM / 1000.0)


def kj_to_kcal(x: float) -> float:
    return x / KJ_PER_KCAL


def read_mode(commentary: Optional[str]) -> tuple[str, Optional[str]]:
    """(mode, versus) from a BRENDA commentary cell; ('unstated', None) if absent."""
    m = _MODE.search(commentary or "")
    if not m:
        return "unstated", None
    word = m.group(1).lower().replace("-", "")
    if word.startswith("mixed"):
        mode = "mixed"
    elif word.startswith("partial"):
        mode = "partial"
    else:
        mode = word
    versus = m.group(2).strip() if m.group(2) else None
    return mode, versus


@dataclass
class Measurement:
    ki_mM: float
    compound: str
    organism: str
    reference: Optional[str]
    commentary: Optional[str]
    ph: Optional[float]
    temperature_c: Optional[float]
    mode: str
    versus: Optional[str]
    preparation: Optional[str] = None  # "tagged", "immobilised", ... from enzyme_preparation
    isoform: Optional[str] = None
    #: ΔG in kcal/mol: a single value at the stated T, or (lo, hi) over
    #: UNSTATED_T_RANGE_C when the row gave none.
    dg_kcal: tuple = ()
    excluded: Optional[str] = None  # why this row cannot validate the simulated state

    @property
    def dg_lo(self) -> float:
        return min(self.dg_kcal)

    @property
    def dg_hi(self) -> float:
        return max(self.dg_kcal)


def measurement(ki_mM, compound, organism, reference, commentary, ph, temperature_c,
                preparation=None) -> Measurement:
    mode, versus = read_mode(commentary)
    if temperature_c is not None:
        dg = (kj_to_kcal(dg_kj(ki_mM, temperature_c)),)
    else:
        dg = tuple(kj_to_kcal(dg_kj(ki_mM, t)) for t in UNSTATED_T_RANGE_C)
    return Measurement(ki_mM, compound, organism, reference, commentary, ph,
                       temperature_c, mode, versus, preparation, read_isoform(commentary), dg)


def fits_state(m: Measurement, state: str) -> Optional[str]:
    """None when the row can validate a simulation of `state`
    ('free' = inhibitor with apo enzyme, 'ternary' = with enzyme-substrate
    complex), else the reason it cannot."""
    kind, meaning = MODE_MEANING[m.mode]
    if kind in ("either",) or kind == state:
        return None
    if kind == "unknown":
        return None  # kept, and flagged in the verdict: excluding it would hide it
    if kind == "ambiguous":
        return f"{m.mode} inhibition: {meaning}"
    return f"{m.mode} inhibition measures the {kind} state ({meaning}); the simulation is of the {state} state"


@dataclass
class Target:
    """The experimental band a computed ΔG is judged against."""
    compound: str
    organism: str
    state: str
    used: List[Measurement]
    excluded: List[Measurement]
    lo: Optional[float] = None
    hi: Optional[float] = None
    references: List[str] = field(default_factory=list)
    caveats: List[str] = field(default_factory=list)

    @property
    def width(self) -> Optional[float]:
        return None if self.lo is None else self.hi - self.lo


def target(rows: Sequence[Measurement], state: str = "free",
           isoform: Optional[str] = None) -> Target:
    if state not in ("free", "ternary"):
        raise ValueError("state is 'free' or 'ternary'")
    used, excluded = [], []
    for m in rows:
        why = fits_state(m, state)
        if not why and isoform and m.isoform and m.isoform.lower() != isoform.lower():
            why = f"measured on {m.isoform}; the simulation is of {isoform}"
        if why:
            m.excluded = why
            excluded.append(m)
        else:
            used.append(m)
    compound = rows[0].compound if rows else ""
    organism = rows[0].organism if rows else ""
    t = Target(compound, organism, state, used, excluded)
    if not used:
        return t
    t.lo = min(m.dg_lo for m in used)
    t.hi = max(m.dg_hi for m in used)
    t.references = sorted({m.reference for m in used if m.reference})
    if len(t.references) < 2:
        t.caveats.append(
            "one publication: how far this constant moves between laboratories is unknown, "
            "so agreement with it is consistency, not validation"
        )
    if any(m.temperature_c is None for m in used):
        t.caveats.append(
            f"a row reports no assay temperature; its ΔG is given over "
            f"{UNSTATED_T_RANGE_C[0]:g}-{UNSTATED_T_RANGE_C[1]:g} °C instead of at a guessed one"
        )
    isoforms = sorted({m.isoform for m in used if m.isoform})
    if len(isoforms) > 1:
        t.caveats.append(
            f"the band pools {len(isoforms)} isoforms ({', '.join(isoforms)}), which are different "
            f"proteins; pass the one simulated (--isoform) to compare like with like"
        )
    if any(m.mode == "unstated" for m in used):
        t.caveats.append("a row does not state its inhibition mode, so which binding event it measured is unknown")
    preps = sorted({m.preparation for m in used if m.preparation and m.preparation not in ("unstated", "native")})
    if preps:
        t.caveats.append(
            f"measured on a {', '.join(preps)} enzyme; a simulation of the unmodified protein "
            f"is compared with a construct"
        )
    versus = sorted({m.versus for m in used if m.versus})
    if versus:
        t.caveats.append(f"inhibition was measured against {', '.join(versus)}; a Ki is specific to that assay")
    return t


@dataclass
class Verdict:
    word: str  # "agrees" | "disagrees" | "no target"
    gap_kcal: float = 0.0  # distance from the band's edge, 0 inside it
    ki_fold: float = 1.0   # the same gap as a fold error in Ki
    detail: str = ""


def judge(t: Target, computed_kcal: float, error_kcal: float, temperature_c: float = 25.0) -> Verdict:
    """Is the computed ΔG ± 2σ consistent with the experimental band?"""
    if t.lo is None:
        return Verdict("no target", detail="no measurement fits the simulated state")
    lo, hi = computed_kcal - 2 * error_kcal, computed_kcal + 2 * error_kcal
    if hi < t.lo:
        gap = t.lo - hi
    elif lo > t.hi:
        gap = lo - t.hi
    else:
        gap = 0.0
    rt_kcal = kj_to_kcal(R_KJ * (temperature_c + 273.15))
    fold = math.exp(gap / rt_kcal)
    if gap == 0.0:
        return Verdict("agrees", 0.0, 1.0,
                       "the computed value ± 2σ overlaps the measured band")
    side = "binds too tightly" if computed_kcal < t.lo else "binds too weakly"
    return Verdict("disagrees", gap, fold,
                   f"the simulation {side}: {gap:.2f} kcal/mol beyond the band even at 2σ, "
                   f"a {fold:.3g}-fold error in Ki")


def parse_computed(text: str) -> tuple[float, float]:
    """'-8.1', '-8.1+-0.5', '-8.1±0.5', '-8.1 0.5' -> (value, error)."""
    parts = re.split(r"\s*(?:±|\+/-|\+-|\s)\s*", text.strip().replace("−", "-"))
    parts = [p for p in parts if p]
    if not 1 <= len(parts) <= 2:
        raise ValueError(f"expected 'ΔG' or 'ΔG±error', got {text!r}")
    value = float(parts[0])
    error = abs(float(parts[1])) if len(parts) == 2 else 0.0
    return value, error
