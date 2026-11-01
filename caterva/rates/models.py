"""The rate laws an initial-rate experiment is fitted to, each written once.

SEVEN LAWS, AND WHERE EACH COMES FROM
-------------------------------------
Without an inhibitor:

    michaelis-menten       v = Vmax [S] / (Km + [S])
    substrate-inhibition   v = Vmax [S] / (Km + [S] + [S]^2 / Ksi)
    hill                   v = Vmax [S]^n / (K0.5^n + [S]^n)

With an inhibitor, the four classical reversible mechanisms of a
one-substrate enzyme:

    competitive      v = Vmax [S] / (Km (1 + [I]/Ki) + [S])
    uncompetitive    v = Vmax [S] / (Km + [S] (1 + [I]/Ki'))
    noncompetitive   v = Vmax [S] / ((Km + [S]) (1 + [I]/Ki))
    mixed            v = Vmax [S] / (Km (1 + [I]/Ki) + [S] (1 + [I]/Ki'))

Textbook sources: A. Cornish-Bowden, Fundamentals of Enzyme Kinetics, 4th ed.
(Wiley-Blackwell, 2012), and I. H. Segel, Enzyme Kinetics (Wiley, 1975), for
every law here; the originals are Michaelis & Menten (1913) Biochem. Z.
49:333 with Briggs & Haldane (1925) Biochem. J. 19:338 for the steady state,
Haldane, Enzymes (Longmans, 1930) for substrate inhibition, and Hill (1910)
J. Physiol. 40:iv for the Hill equation. They are the laws of
`compose/library.py`'s motifs (competitive_inhibition, uncompetitive_inhibition,
noncompetitive_inhibition, mixed_inhibition, substrate_inhibition and
cooperative_catalysis), with that library's kcat [E] written as the one
constant an initial-rate experiment can see, Vmax. Two constants are named
differently, and mean the same: the library's mixed Kic and Kiu are Ki and
Ki' here, and its uncompetitive motif's "Ki", which binds the ES complex, is
Ki' here, so that one symbol has one meaning across the four laws below.

WHICH Ki EACH CONSTANT IS
-------------------------
Two dissociation constants are possible, and the whole literature comparison
rests on comparing like with like:

    Ki   dissociation constant of EI, inhibitor from FREE enzyme.
         Cornish-Bowden's Kic (competitive inhibition constant); Segel's Ki.
    Ki'  dissociation constant of ESI, inhibitor from the enzyme-SUBSTRATE
         complex. Cornish-Bowden's Kiu; Segel's alpha*Ki.

A competitive inhibitor has only Ki (Ki' is infinite); an uncompetitive one
only Ki'; a noncompetitive (pure) one has both, equal, and the one number is
both; a mixed one has both, unequal. These are the meanings
`compose/row_scope.MODE_OF_MOTIF` gives the motifs' constants and
`bind/core.MODE_MEANING` gives BRENDA's commentary: a row BRENDA marks
"competitive" is a Ki, "uncompetitive" a Ki', "noncompetitive" the shared
constant, and "mixed" one of two unequal constants without saying which. So
the literature comparison looks up a competitive fit's Ki under
"competitive", an uncompetitive fit's Ki' under "uncompetitive", a
noncompetitive fit's constant under "noncompetitive", and does not look up a
mixed fit's constants at all (`compose/library.MIXED_KI_REFUSAL` says why).

K0.5 in the Hill law is the substrate concentration at half Vmax, not a
dissociation constant, and n is a phenomenological exponent, not a count of
binding sites (`compose/library.COOPERATIVE_CATALYSIS` says this at length).
Neither is compared with the literature.

WRITTEN TO BE DIFFERENTIATED EXACTLY
------------------------------------
Every law uses only arithmetic and powers, so it accepts complex parameter
values and the fit differentiates it by the complex step (fit.py), which is
exact to rounding error. A law written with `abs`, `max` or a comparison on a
parameter would break that silently; none may be.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Tuple

import numpy as np

#: The role a constant's value plays, which decides its unit and where the
#: fit's starting values come from.
ROLE_RATE = "rate"            # in the rate's unit; enters linearly
ROLE_SUBSTRATE = "substrate"  # in the substrate's unit
ROLE_INHIBITOR = "inhibitor"  # in the inhibitor's unit
ROLE_EXPONENT = "exponent"    # dimensionless


@dataclass(frozen=True)
class Constant:
    #: Identifier in JSON and CSV output.
    name: str
    #: As printed in a report.
    label: str
    role: str
    meaning: str


@dataclass(frozen=True)
class RateLaw:
    name: str
    title: str
    equation: str
    constants: Tuple[Constant, ...]
    needs_inhibitor: bool
    law: Callable[[Mapping[str, Any], np.ndarray, np.ndarray], np.ndarray]
    #: The inhibition mode BRENDA and compose name this law's constant by;
    #: None for a law with no inhibitor, and for mixed (see module docstring).
    mode: Optional[str] = None
    #: compose's motif of the same law, for `row_scope.read_scope`.
    motif: Optional[str] = None
    #: Which of this law's constants is the one a literature Ki of `mode` is.
    literature_ki: Optional[str] = None

    @property
    def names(self) -> Tuple[str, ...]:
        return tuple(c.name for c in self.constants)

    def constant(self, name: str) -> Constant:
        for c in self.constants:
            if c.name == name:
                return c
        raise KeyError(name)

    def rate(self, values: Mapping[str, Any], substrate: Any, inhibitor: Any = None) -> np.ndarray:
        s = np.asarray(substrate, dtype=float)
        i = np.zeros_like(s) if inhibitor is None else np.asarray(inhibitor, dtype=float)
        return self.law(values, s, i)


VMAX = Constant("Vmax", "Vmax", ROLE_RATE, "the limiting rate at saturating substrate")
KM = Constant("Km", "Km", ROLE_SUBSTRATE, "the substrate concentration at half Vmax")
KSI = Constant("Ksi", "Ksi", ROLE_SUBSTRATE,
               "dissociation constant of a second, non-productive substrate from ES")
KHALF = Constant("K_half", "K0.5", ROLE_SUBSTRATE, "the substrate concentration at half Vmax")
HILL = Constant("n", "n", ROLE_EXPONENT, "the Hill coefficient, a fitted exponent and not a site count")
KI = Constant("Ki", "Ki", ROLE_INHIBITOR,
              "dissociation constant of EI, inhibitor from free enzyme (Kic)")
KI_PRIME = Constant("Ki_prime", "Ki'", ROLE_INHIBITOR,
                    "dissociation constant of ESI, inhibitor from the enzyme-substrate complex (Kiu)")
KI_SHARED = Constant("Ki", "Ki", ROLE_INHIBITOR,
                     "dissociation constant of EI and of ESI, equal (Kic = Kiu)")


def _power(base: np.ndarray, exponent: Any) -> np.ndarray:
    """base**exponent for base >= 0 and a possibly complex exponent: 0 at a
    zero base, so a blank at [S] = 0 is a rate of 0 and not a NaN."""
    positive = base > 0
    safe = np.where(positive, base, 1.0)
    return np.where(positive, np.exp(exponent * np.log(safe)), 0.0)


def _mm(p, s, i):
    return p["Vmax"] * s / (p["Km"] + s)


def _substrate_inhibition(p, s, i):
    return p["Vmax"] * s / (p["Km"] + s + s * s / p["Ksi"])


def _hill(p, s, i):
    sn = _power(s, p["n"])
    return p["Vmax"] * sn / (p["K_half"] ** p["n"] + sn)


def _competitive(p, s, i):
    return p["Vmax"] * s / (p["Km"] * (1.0 + i / p["Ki"]) + s)


def _uncompetitive(p, s, i):
    return p["Vmax"] * s / (p["Km"] + s * (1.0 + i / p["Ki_prime"]))


def _noncompetitive(p, s, i):
    return p["Vmax"] * s / ((p["Km"] + s) * (1.0 + i / p["Ki"]))


def _mixed(p, s, i):
    return p["Vmax"] * s / (p["Km"] * (1.0 + i / p["Ki"]) + s * (1.0 + i / p["Ki_prime"]))


MICHAELIS_MENTEN = RateLaw(
    "michaelis-menten", "Michaelis-Menten", "v = Vmax [S] / (Km + [S])",
    (VMAX, KM), False, _mm)
SUBSTRATE_INHIBITION = RateLaw(
    "substrate-inhibition", "substrate inhibition (Haldane)",
    "v = Vmax [S] / (Km + [S] + [S]^2 / Ksi)", (VMAX, KM, KSI), False, _substrate_inhibition)
HILL_LAW = RateLaw(
    "hill", "Hill", "v = Vmax [S]^n / (K0.5^n + [S]^n)", (VMAX, KHALF, HILL), False, _hill)
COMPETITIVE = RateLaw(
    "competitive", "competitive inhibition", "v = Vmax [S] / (Km (1 + [I]/Ki) + [S])",
    (VMAX, KM, KI), True, _competitive, "competitive", "competitive_inhibition", "Ki")
UNCOMPETITIVE = RateLaw(
    "uncompetitive", "uncompetitive inhibition", "v = Vmax [S] / (Km + [S] (1 + [I]/Ki'))",
    (VMAX, KM, KI_PRIME), True, _uncompetitive, "uncompetitive", "uncompetitive_inhibition",
    "Ki_prime")
NONCOMPETITIVE = RateLaw(
    "noncompetitive", "noncompetitive (pure) inhibition",
    "v = Vmax [S] / ((Km + [S]) (1 + [I]/Ki))",
    (VMAX, KM, KI_SHARED), True, _noncompetitive, "noncompetitive", "noncompetitive_inhibition",
    "Ki")
MIXED = RateLaw(
    "mixed", "mixed inhibition", "v = Vmax [S] / (Km (1 + [I]/Ki) + [S] (1 + [I]/Ki'))",
    (VMAX, KM, KI, KI_PRIME), True, _mixed)

LAWS: Dict[str, RateLaw] = {law.name: law for law in (
    MICHAELIS_MENTEN, SUBSTRATE_INHIBITION, HILL_LAW,
    COMPETITIVE, UNCOMPETITIVE, NONCOMPETITIVE, MIXED,
)}
WITHOUT_INHIBITOR = ("michaelis-menten", "substrate-inhibition", "hill")
WITH_INHIBITOR = ("competitive", "uncompetitive", "noncompetitive", "mixed")


@dataclass(frozen=True)
class Nesting:
    """`special` is `general` with one constraint on its constants.

    `boundary` is True when the constraint puts a constant at the edge of
    its range (a dissociation constant at infinity), where the usual
    chi-square(1) reference for the likelihood ratio is wrong; False for an
    interior equality (Ki = Ki', n = 1). discriminate.py says what each
    means for the test.
    """

    general: str
    special: str
    boundary: bool
    constraint: str
    #: For a boundary nesting, the general law's constant that goes to
    #: infinity; for an interior one, None.
    to_infinity: Optional[str] = None


NESTINGS: Tuple[Nesting, ...] = (
    Nesting("mixed", "competitive", True, "Ki' -> infinity", "Ki_prime"),
    Nesting("mixed", "uncompetitive", True, "Ki -> infinity", "Ki"),
    Nesting("mixed", "noncompetitive", False, "Ki = Ki'"),
    Nesting("substrate-inhibition", "michaelis-menten", True, "Ksi -> infinity", "Ksi"),
    Nesting("hill", "michaelis-menten", False, "n = 1"),
)


def nestings_under(general: str) -> Tuple[Nesting, ...]:
    return tuple(n for n in NESTINGS if n.general == general)


def law_for(name: str) -> RateLaw:
    try:
        return LAWS[name]
    except KeyError:
        raise KeyError(f"no rate law called {name!r}; the laws are {', '.join(LAWS)}") from None


def as_values(law: RateLaw, theta: Sequence[Any]) -> Dict[str, Any]:
    """Log-parameters -> {constant: value}, complex-safe."""
    return {c.name: np.exp(t) for c, t in zip(law.constants, theta)}


__all__ = [
    "Constant", "RateLaw", "Nesting", "LAWS", "NESTINGS", "WITHOUT_INHIBITOR", "WITH_INHIBITOR",
    "MICHAELIS_MENTEN", "SUBSTRATE_INHIBITION", "HILL_LAW", "COMPETITIVE", "UNCOMPETITIVE",
    "NONCOMPETITIVE", "MIXED", "ROLE_RATE", "ROLE_SUBSTRATE", "ROLE_INHIBITOR", "ROLE_EXPONENT",
    "law_for", "nestings_under", "as_values",
]
