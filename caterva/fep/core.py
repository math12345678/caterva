"""The physics of an absolute binding free energy, kept small enough to check by hand.

Double decoupling (Gilson et al. 1997): the ligand's interactions are
switched off twice, once bound and once in water, and the binding free
energy is the difference, corrected to the 1 M standard state the Ki is
quoted at. While it is decoupled in the complex the ligand is held in its
pose by six Boresch restraints (one distance, two angles, three
dihedrals), whose cost at standard state has a closed form (Boresch et al.
2003, eq. 32). The legs are integrated with BAR (Bennett 1976).

The cycle, with every ΔG a decoupling (coupled -> decoupled):

    ΔG°bind = ΔG_solvent + ΔG_restraints_on - ΔG_complex

ΔG_complex includes switching the restraints on while the ligand is still
coupled; ΔG_restraints_on is the analytic cost of those restraints on a
ligand that feels nothing, at c° = 1 M. A ligand that binds tightly is
expensive to decouple in the complex, so ΔG_complex is large and ΔG°bind
negative.

Units: nm, radians, kJ/mol throughout, as GROMACS writes them. GROMACS's
restraint potentials are 1/2 K (x - x0)^2 for bond type 6, angle type 1
and dihedral type 2, which is the convention eq. 32 assumes.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from itertools import permutations
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

R_KJ = 8.314462618e-3
#: Volume per molecule at 1 M, nm^3: 1 / (N_A * 1 mol/L) = 1.66054 nm^3.
V_STANDARD_NM3 = 1.0 / (6.02214076e23 * 1e-24)
#: Restraint force constants: 10 kcal/mol/A^2 and 10 kcal/mol/rad^2, the
#: values in common use since Boresch et al. and in the benchmarks built on
#: it. Stiff enough to hold the pose, soft enough not to strain it.
K_DISTANCE = 4184.0   # kJ/mol/nm^2
K_ANGLE = 41.84       # kJ/mol/rad^2

AMINO_ACIDS = {
    "ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY", "HIS", "ILE", "LEU", "LYS",
    "MET", "PHE", "PRO", "SER", "THR", "TRP", "TYR", "VAL", "HID", "HIE", "HIP", "HSD",
    "HSE", "HSP", "CYX", "ASH", "GLH", "LYN", "NALA", "CALA",
}


# -- structure -------------------------------------------------------------

@dataclass(frozen=True)
class Atom:
    index: int      # 1-based, the position in the .gro: GROMACS's global index
    resnr: int
    resname: str
    name: str
    xyz: Tuple[float, float, float]


def read_gro(path: Path) -> List[Atom]:
    lines = Path(path).read_text().splitlines()
    n = int(lines[1].split()[0])
    atoms = []
    for i, line in enumerate(lines[2:2 + n], start=1):
        atoms.append(Atom(i, int(line[0:5]), line[5:10].strip(), line[10:15].strip(),
                          (float(line[20:28]), float(line[28:36]), float(line[36:44]))))
    if len(atoms) != n:
        raise ValueError(f"{path}: header says {n} atoms, found {len(atoms)}")
    return atoms


def ligand_atoms(atoms: Sequence[Atom], resname: str) -> List[Atom]:
    lig = [a for a in atoms if a.resname == resname]
    if not lig:
        names = sorted({a.resname for a in atoms if a.resname not in AMINO_ACIDS
                        and a.resname not in ("SOL", "NA", "CL", "HOH", "WAT")})
        raise ValueError(f"no residue named {resname!r}; non-protein residues present: {', '.join(names) or 'none'}")
    if len({a.resnr for a in lig}) > 1:
        raise ValueError(f"{resname!r} names more than one residue; the ligand must be one copy")
    return lig


def _heavy(a: Atom) -> bool:
    return not a.name.upper().startswith("H")


# -- geometry ----------------------------------------------------------------

def _v(a: Atom) -> np.ndarray:
    return np.asarray(a.xyz, dtype=float)


def distance(a, b) -> float:
    return float(np.linalg.norm(_v(a) - _v(b)))


def angle(a, b, c) -> float:
    """Angle at b, radians."""
    u, w = _v(a) - _v(b), _v(c) - _v(b)
    cos = float(np.dot(u, w) / (np.linalg.norm(u) * np.linalg.norm(w)))
    return math.acos(max(-1.0, min(1.0, cos)))


def dihedral(a, b, c, d) -> float:
    """IUPAC dihedral a-b-c-d, radians, in (-pi, pi]."""
    b0, b1, b2 = _v(a) - _v(b), _v(c) - _v(b), _v(d) - _v(c)
    b1 = b1 / np.linalg.norm(b1)
    v = b0 - np.dot(b0, b1) * b1
    w = b2 - np.dot(b2, b1) * b1
    x = np.dot(v, w)
    y = np.dot(np.cross(b1, v), w)
    return float(math.atan2(y, x))


@dataclass
class Restraint:
    """Boresch's six degrees of freedom: protein P3-P2-P1, ligand L1-L2-L3.

    r = |P1 L1|; thetaA = P2-P1-L1; thetaB = P1-L1-L2; phiA = P3-P2-P1-L1;
    phiB = P2-P1-L1-L2; phiC = P1-L1-L2-L3. Reference values are measured
    on the input structure: the restraint holds the pose you gave it.
    """
    protein: Tuple[Atom, Atom, Atom]   # P1, P2, P3
    ligand: Tuple[Atom, Atom, Atom]    # L1, L2, L3
    r: float
    theta_a: float
    theta_b: float
    phi_a: float
    phi_b: float
    phi_c: float
    quality: float  # smallest sine among the angles that keep it well defined

    def gromacs(self) -> str:
        """The [ intermolecular_interactions ] block: off in state A, on in B."""
        (p1, p2, p3), (l1, l2, l3) = self.protein, self.ligand
        deg = math.degrees
        kd, ka = K_DISTANCE, K_ANGLE
        return (
            "\n[ intermolecular_interactions ]\n"
            "; Boresch restraints, Boresch et al. (2003) J. Phys. Chem. B 107:9535.\n"
            "; State A (restraint-lambda 0): off. State B (restraint-lambda 1): on.\n"
            f"; Protein P1-P2-P3 = {_label(p1)}, {_label(p2)}, {_label(p3)}\n"
            f"; Ligand  L1-L2-L3 = {_label(l1)}, {_label(l2)}, {_label(l3)}\n"
            "[ bonds ]\n"
            f"{p1.index:>7} {l1.index:>7}  6  {self.r:.4f} 0.0  {self.r:.4f} {kd:.2f}\n"
            "[ angles ]\n"
            f"{p2.index:>7} {p1.index:>7} {l1.index:>7}  1  {deg(self.theta_a):.3f} 0.0  {deg(self.theta_a):.3f} {ka:.3f}\n"
            f"{p1.index:>7} {l1.index:>7} {l2.index:>7}  1  {deg(self.theta_b):.3f} 0.0  {deg(self.theta_b):.3f} {ka:.3f}\n"
            "[ dihedrals ]\n"
            f"{p3.index:>7} {p2.index:>7} {p1.index:>7} {l1.index:>7}  2  {deg(self.phi_a):.3f} 0.0  {deg(self.phi_a):.3f} {ka:.3f}\n"
            f"{p2.index:>7} {p1.index:>7} {l1.index:>7} {l2.index:>7}  2  {deg(self.phi_b):.3f} 0.0  {deg(self.phi_b):.3f} {ka:.3f}\n"
            f"{p1.index:>7} {l1.index:>7} {l2.index:>7} {l3.index:>7}  2  {deg(self.phi_c):.3f} 0.0  {deg(self.phi_c):.3f} {ka:.3f}\n"
        )


def _label(a: Atom) -> str:
    return f"{a.resname}{a.resnr}:{a.name} (atom {a.index})"


def choose_restraint(atoms: Sequence[Atom], ligand_resname: str) -> Restraint:
    """Pick restraint atoms so every angle stays well away from 0 and 180 degrees.

    A Boresch angle near collinear makes its dihedral undefined and the
    correction's sin(theta) blow up; the standard failure of hand-picked
    anchors. Ligand: L1 is the heavy atom nearest the ligand's centroid, L2
    and L3 the pair of nearby heavy atoms making L1-L2-L3 closest to a right
    angle. Protein: C-alpha atoms (backbone moves least) within 1.5 nm of
    the ligand, choosing the triple that maximises the smallest sine among
    thetaA, thetaB and the P3-P2-P1 and L1-L2-L3 angles, with |P1 L1|
    preferred between 0.4 and 0.8 nm.
    """
    lig = [a for a in ligand_atoms(atoms, ligand_resname) if _heavy(a)]
    if len(lig) < 3:
        raise ValueError(f"{ligand_resname!r} has {len(lig)} heavy atom(s); Boresch restraints need 3")
    centroid = np.mean([_v(a) for a in lig], axis=0)
    by_centre = sorted(lig, key=lambda a: float(np.linalg.norm(_v(a) - centroid)))
    l1 = by_centre[0]
    near = by_centre[1:8]
    best_lig = None
    for l2, l3 in permutations(near, 2):
        if distance(l1, l2) < 0.12 or distance(l2, l3) < 0.12 or distance(l1, l3) < 0.12:
            continue
        s = math.sin(angle(l1, l2, l3))
        if best_lig is None or s > best_lig[0]:
            best_lig = (s, l2, l3)
    if best_lig is None:
        raise ValueError(f"{ligand_resname!r}: no three heavy atoms form a usable triangle")
    _, l2, l3 = best_lig

    ca = [a for a in atoms if a.name == "CA" and a.resname in AMINO_ACIDS]
    pocket = sorted((a for a in ca if float(np.linalg.norm(_v(a) - centroid)) < 1.5),
                    key=lambda a: float(np.linalg.norm(_v(a) - centroid)))[:16]
    if len(pocket) < 3:
        raise ValueError("fewer than 3 C-alpha atoms within 1.5 nm of the ligand: is it in the pocket?")
    best = None
    for p1 in pocket[:10]:
        r = distance(p1, l1)
        if not 0.3 <= r <= 1.2:
            continue
        for p2, p3 in permutations([p for p in pocket if p is not p1], 2):
            if distance(p1, p2) < 0.3 or distance(p2, p3) < 0.3:
                continue
            ta, tb = angle(p2, p1, l1), angle(p1, l1, l2)
            q = min(math.sin(ta), math.sin(tb), math.sin(angle(p3, p2, p1)), best_lig[0])
            score = q - 0.1 * max(0.0, abs(r - 0.6) - 0.2)
            if best is None or score > best[0]:
                best = (score, q, p1, p2, p3, r, ta, tb)
    if best is None:
        raise ValueError("no C-alpha within 0.3-1.2 nm of the ligand's central atom")
    _, q, p1, p2, p3, r, ta, tb = best
    return Restraint((p1, p2, p3), (l1, l2, l3), r, ta, tb,
                     dihedral(p3, p2, p1, l1), dihedral(p2, p1, l1, l2), dihedral(p1, l1, l2, l3), q)


def restraint_cost_kj(rst: Restraint, temperature_k: float) -> float:
    """ΔG of switching the restraints ON for a non-interacting ligand at 1 M.

    Boresch et al. (2003) eq. 32 gives the free energy of releasing them,
    -kT ln[8 pi^2 V° sqrt(K_r K_thA K_thB K_phA K_phB K_phC) /
    (r0^2 sin thA sin thB (2 pi kT)^3)]; switching them on costs its negative,
    and is positive.
    """
    kt = R_KJ * temperature_k
    ks = K_DISTANCE * K_ANGLE ** 5
    arg = (8 * math.pi ** 2 * V_STANDARD_NM3 * math.sqrt(ks)
           / (rst.r ** 2 * math.sin(rst.theta_a) * math.sin(rst.theta_b) * (2 * math.pi * kt) ** 3))
    return kt * math.log(arg)


# -- lambda schedule ----------------------------------------------------------

RESTRAINT_STEPS = (0.0, 0.01, 0.025, 0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0)
COUL_STEPS = (0.0, 0.25, 0.5, 0.75, 1.0)
VDW_STEPS = tuple(round(x * 0.05, 2) for x in range(21))


@dataclass
class Schedule:
    restraint: List[float]
    coul: List[float]
    vdw: List[float]

    def __len__(self) -> int:
        return len(self.coul)

    def mdp(self) -> str:
        f = lambda xs: " ".join(f"{x:g}" for x in xs)
        text = (f"coul-lambdas            = {f(self.coul)}\n"
                f"vdw-lambdas             = {f(self.vdw)}\n")
        if any(self.restraint):
            text += f"restraint-lambdas       = {f(self.restraint)}\n"
        return text


def schedule(leg: str) -> Schedule:
    """Restraints on first (complex only), then charges off, then van der Waals.

    Charges go before van der Waals so no bare charge is ever left without
    the repulsion that keeps it off its neighbours; the van der Waals steps
    are the finest because soft-core curvature concentrates there.
    """
    rs, cs, vs = [], [], []
    if leg == "complex":
        for x in RESTRAINT_STEPS:
            rs.append(x); cs.append(0.0); vs.append(0.0)
    elif leg != "solvent":
        raise ValueError("leg is 'complex' or 'solvent'")
    tail_r = 1.0 if leg == "complex" else 0.0
    for x in COUL_STEPS[1:]:
        rs.append(tail_r); cs.append(x); vs.append(0.0)
    for x in VDW_STEPS[1:]:
        rs.append(tail_r); cs.append(1.0); vs.append(x)
    if leg == "solvent":
        rs, cs, vs = [0.0] + rs, [0.0] + cs, [0.0] + vs
    return Schedule(rs, cs, vs)


# -- reading results ----------------------------------------------------------

_BAR_TOTAL = re.compile(r"^\s*total\s+\d+\s*-\s*\d+,\s*DG\s+(-?[\d.]+)\s+\+/-\s+([\d.]+)", re.M)


def read_bar(text: str) -> Tuple[float, float]:
    """(ΔG, σ) in kJ/mol from `gmx bar` output (the 'total' line after
    'Final results in kJ/mol')."""
    tail = text.split("Final results in kJ/mol", 1)
    m = _BAR_TOTAL.search(tail[1] if len(tail) == 2 else text)
    if not m:
        raise ValueError("no 'total ... DG x +/- y' line in gmx bar output")
    return float(m.group(1)), float(m.group(2))


__all__ = ["Atom", "Restraint", "Schedule", "read_gro", "ligand_atoms", "choose_restraint",
           "restraint_cost_kj", "schedule", "read_bar", "V_STANDARD_NM3", "K_DISTANCE", "K_ANGLE"]
