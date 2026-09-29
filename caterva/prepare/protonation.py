"""Which titratable residues near the active site have an uncertain charge at the assay pH.

This is not a pKa predictor. It does not know the environment of any
residue, and a residue buried next to a charge can have a pKa several units
from its average. What it knows is how far real proteins move each group:
Grimsley, Scholtz & Pace (2009) tabulated 541 measured pKa values from 78
folded proteins and give each group's mean and standard deviation.

From that, Henderson-Hasselbalch gives the fraction protonated at the assay
pH for a residue with the average pKa, and at one standard deviation either
side. If that whole band is below 10% or above 90%, typical behaviour
settles the charge state. If not, the state is genuinely uncertain for a
residue of that type at that pH, and the report says so: that residue needs
a structure-based estimate (PROPKA) or constant-pH simulation before the
charge GROMACS assigns can be trusted. It also says when pdb2gmx's default
state contradicts even the typical behaviour, which is an error to fix
before simulating, not a subtlety.

Arginine is not in the survey (its pKa in proteins is high enough that it
is taken as always charged below pH 12); it is reported as not assessed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

#: Grimsley, Scholtz & Pace (2009) Protein Sci. 18:247, doi:10.1002/pro.19:
#: mean pKa, standard deviation, number of measurements, in folded proteins.
PKA: Dict[str, Tuple[float, float, int]] = {
    "ASP": (3.5, 1.2, 139),
    "GLU": (4.2, 0.9, 153),
    "HIS": (6.6, 1.0, 131),
    "CYS": (6.8, 2.7, 25),
    "TYR": (10.3, 1.2, 20),
    "LYS": (10.5, 1.1, 35),
    "CTERM": (3.3, 0.8, 22),
    "NTERM": (7.7, 0.5, 16),
}
SOURCE = "Grimsley, Scholtz & Pace (2009) Protein Sci. 18:247, doi:10.1002/pro.19"

#: The state pdb2gmx gives each group unless told otherwise, from its own
#: help text (GROMACS 2026.1): Asp and Glu unprotonated, Lys protonated,
#: termini ionised (NH3+, COO-); Cys and Tyr neutral. True = protonated.
#: His is None: pdb2gmx places its proton(s) "based on an optimal hydrogen
#: bonding" network, on ND1, NE2 or both, so its state follows the
#: structure's hydrogen bonds, not the pH.
PDB2GMX_DEFAULT_PROTONATED: Dict[str, Optional[bool]] = {
    "ASP": False, "GLU": False, "HIS": None, "CYS": True, "TYR": True,
    "LYS": True, "CTERM": False, "NTERM": True,
}

#: The band must lie wholly outside (SETTLED, 1 - SETTLED) to count as settled.
SETTLED = 0.10


def fraction_protonated(ph: float, pka: float) -> float:
    """Henderson-Hasselbalch: 1 / (1 + 10^(pH - pKa))."""
    return 1.0 / (1.0 + 10.0 ** (ph - pka))


@dataclass
class Titration:
    group: str
    ph: float
    pka: float
    sd: float
    n: int
    protonated: float        # fraction at the mean pKa
    band: Tuple[float, float]  # fractions at pKa - sd and pKa + sd
    default_protonated: Optional[bool]

    @property
    def settled(self) -> Optional[bool]:
        """True = protonated, False = deprotonated, None = uncertain."""
        lo, hi = self.band
        if hi <= SETTLED:
            return False
        if lo >= 1 - SETTLED:
            return True
        return None

    @property
    def default_contradicted(self) -> bool:
        return (self.settled is not None and self.default_protonated is not None
                and self.settled != self.default_protonated)

    def describe(self) -> str:
        lo, hi = self.band
        state = {True: "protonated", False: "deprotonated", None: "uncertain"}[self.settled]
        text = (f"typical pKa {self.pka:.1f} +/- {self.sd:.1f}: {self.protonated:.0%} protonated at pH {self.ph:g} "
                f"({lo:.0%}-{hi:.0%} across one SD); {state}")
        if self.default_protonated is None:
            text += "; pdb2gmx sets it from the hydrogen-bond network, not the pH"
        elif self.default_contradicted:
            default = "protonated" if self.default_protonated else "deprotonated"
            text += f"; pdb2gmx would make it {default}, which contradicts this"
        elif self.settled is None:
            default = "protonated" if self.default_protonated else "deprotonated"
            text += f"; pdb2gmx would make it {default} without checking"
        return text


def assess(group: str, ph: float) -> Optional[Titration]:
    """The titration of one group type at a pH, or None if it is not in the survey."""
    key = group.upper()
    if key not in PKA:
        return None
    pka, sd, n = PKA[key]
    return Titration(key, ph, pka, sd, n, fraction_protonated(ph, pka),
                     (fraction_protonated(ph, pka - sd), fraction_protonated(ph, pka + sd)),
                     PDB2GMX_DEFAULT_PROTONATED[key])


TITRATABLE = set(PKA) - {"CTERM", "NTERM"} | {"ARG"}

__all__ = ["PKA", "SOURCE", "Titration", "assess", "fraction_protonated", "PDB2GMX_DEFAULT_PROTONATED",
           "SETTLED", "TITRATABLE"]
