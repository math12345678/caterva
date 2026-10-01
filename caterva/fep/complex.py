"""`caterva complex`: a PDB entry and your ligand topology in, an equilibrated complex out.

    caterva complex --pdb 181L --ligand BNZ --ligand-itp bnz.itp --ligand-coords bnz.gro --out t4l
    bash t4l/build.sh
    caterva fep ... --complex t4l/npt.gro --topology t4l/topol.top --ligand BNZ --ligand-itp t4l/bnz.itp

The ligand goes where the crystal put it. Your parameterised ligand (the
coordinates your tool wrote alongside the .itp: ACPYPE's _GMX.gro, CGenFF's
.pdb) is superposed onto the entry's own copy by the atom names they share
(Kabsch 1976), carrying its hydrogens with it, and the fit is reported. If
fewer than three heavy atoms share a name, or the fit is worse than 1 A
RMSD (a different conformer, which a rigid superposition cannot fix), it
refuses and says which; it never places a ligand by guesswork.

build.sh then does what `caterva md` does for a protein, with the ligand
in: pdb2gmx, solvation, ions, minimisation, and NVT then NPT with the
protein restrained, at the temperature you name (by default the one
`caterva fep` will run at, if you pass the same Ki). Crystal waters and
every other HETATM are dropped, and listed.

    caterva complex --check t4l --ligand BNZ      (after build.sh)

Exit codes: 0 written (or: the ligand kept its pose), 4 it left its pose,
3 refused and said why, 2 malformed question, 1 a crash.
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from caterva.fep.setup import moleculetype_name
from caterva.md.setup import Conditions, MdSetup
from caterva.methods import METHODS

EXIT_OK, EXIT_CRASH, EXIT_USAGE, EXIT_REFUSED = 0, 1, 2, 3
#: Largest heavy-atom RMSD, after superposition, at which your ligand is
#: taken to be the crystal's conformer. 1 A: a chosen threshold, stated.
MAX_RMSD_NM = 0.10


@dataclass
class LigandAtom:
    name: str
    element: str
    xyz: np.ndarray  # nm


def _element(name: str, given: str = "") -> str:
    if given.strip():
        return given.strip().upper()
    letters = "".join(c for c in name if c.isalpha())
    return letters[:1].upper() if letters else "?"


def crystal_ligand(pdb_text: str, resname: str, chain: Optional[str] = None) -> Tuple[List[LigandAtom], str]:
    """The first copy of `resname` in the entry (on `chain` if given)."""
    first_key = None
    atoms: List[LigandAtom] = []
    for line in pdb_text.splitlines():
        if not line.startswith(("HETATM", "ATOM")) or line[17:20].strip() != resname:
            continue
        if chain and line[21] != chain:
            continue
        key = (line[21], line[22:27])
        if first_key is None:
            first_key = key
        if key != first_key:
            continue
        name = line[12:16].strip()
        atoms.append(LigandAtom(name, _element(name, line[76:78]),
                                np.array([float(line[30:38]), float(line[38:46]), float(line[46:54])]) / 10.0))
    if not atoms:
        present = sorted({l[17:20].strip() for l in pdb_text.splitlines() if l.startswith("HETATM")} - {"HOH"})
        raise ValueError(f"no {resname!r} in the entry" + (f" on chain {chain}" if chain else "")
                         + f"; its ligands and additives: {', '.join(present) or 'none'}")
    return atoms, f"chain {first_key[0]} residue {first_key[1].strip()}"


def read_coords(path: Path) -> List[LigandAtom]:
    """Your ligand's coordinates, from a .gro (nm) or .pdb/.mol2-free PDB (A)."""
    text = Path(path).read_text().splitlines()
    atoms = []
    if path.suffix.lower() == ".gro":
        n = int(text[1].split()[0])
        for line in text[2:2 + n]:
            name = line[10:15].strip()
            atoms.append(LigandAtom(name, _element(name),
                                    np.array([float(line[20:28]), float(line[28:36]), float(line[36:44])])))
    else:
        for line in text:
            if line.startswith(("ATOM", "HETATM")):
                name = line[12:16].strip()
                atoms.append(LigandAtom(name, _element(name, line[76:78]),
                                        np.array([float(line[30:38]), float(line[38:46]), float(line[46:54])]) / 10.0))
    if not atoms:
        raise ValueError(f"{path}: no atoms read")
    return atoms


def kabsch(P: np.ndarray, Q: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Rotation R and translation t minimising |(P R + t) - Q| (Kabsch 1976)."""
    pc, qc = P.mean(axis=0), Q.mean(axis=0)
    with np.errstate(all="ignore"):  # Accelerate BLAS flags finite products; checked below
        H = (P - pc).T @ (Q - qc)
        U, _, Vt = np.linalg.svd(H)
        d = np.sign(np.linalg.det(Vt.T @ U.T))
        D = np.diag([1.0, 1.0, d])  # a rotation, never a reflection
        R = U @ D @ Vt
    if not np.all(np.isfinite(R)):
        raise FloatingPointError("superposition produced a non-finite rotation")
    return R, qc - pc @ R


#: A group of four heavy atoms is chiral enough to check when its signed
#: volume exceeds this in both molecules (a bonded tetrahedral centre is
#: about 5e-4 nm^3), and compact enough when every pair is within 0.3 nm.
MIN_CHIRAL_VOLUME_NM3 = 2e-4
LOCAL_NM = 0.3


def inverted_centres(P: np.ndarray, Q: np.ndarray, names: Sequence[str]) -> List[str]:
    """Groups of four nearby heavy atoms whose signed volume changes sign
    between your ligand (P) and the crystal's (Q): an inverted stereocentre
    or a mirror image, which no rotation can produce and RMSD can hide."""
    from itertools import combinations
    out = []
    n = len(names)
    for quad in combinations(range(n), 4):
        if any(np.linalg.norm(Q[i] - Q[j]) > LOCAL_NM for i, j in combinations(quad, 2)):
            continue
        a, b, c, d = quad
        vp = np.dot(P[b] - P[a], np.cross(P[c] - P[a], P[d] - P[a])) / 6
        vq = np.dot(Q[b] - Q[a], np.cross(Q[c] - Q[a], Q[d] - Q[a])) / 6
        if min(abs(vp), abs(vq)) > MIN_CHIRAL_VOLUME_NM3 and np.sign(vp) != np.sign(vq):
            out.append("-".join(names[i] for i in quad))
    return out


@dataclass
class Pose:
    atoms: List[LigandAtom]
    rmsd_nm: float
    matched: List[str]
    unmatched_crystal: List[str]
    unmatched_yours: List[str]


def pose_onto_crystal(yours: Sequence[LigandAtom], crystal: Sequence[LigandAtom]) -> Pose:
    heavy = lambda a: a.element != "H"
    by_name = {a.name.upper(): a for a in crystal if heavy(a)}
    pairs = [(a, by_name[a.name.upper()]) for a in yours if heavy(a) and a.name.upper() in by_name]
    matched = [a.name for a, _ in pairs]
    unmatched_crystal = sorted(set(by_name) - {n.upper() for n in matched})
    unmatched_yours = sorted(a.name for a in yours if heavy(a) and a.name.upper() not in by_name)
    if len(pairs) < 3:
        raise ValueError(
            f"only {len(pairs)} heavy atom name(s) shared between your ligand and the crystal's; "
            f"superposition needs 3. Crystal: {', '.join(sorted(by_name))}. "
            f"Yours: {', '.join(sorted(a.name for a in yours if heavy(a)))}. "
            "Regenerate your topology from the entry's own ligand (its CCD atom names) or rename to match.")
    P = np.array([a.xyz for a, _ in pairs])
    Q = np.array([b.xyz for _, b in pairs])
    R, t = kabsch(P, Q)
    rmsd = float(np.sqrt(((P @ R + t - Q) ** 2).sum(axis=1).mean()))
    if rmsd > MAX_RMSD_NM:
        raise ValueError(
            f"your ligand fits the crystal's with heavy-atom RMSD {rmsd * 10:.2f} A (over {len(pairs)} atoms); "
            f"above {MAX_RMSD_NM * 10:.1f} A it is a different conformer, and a rigid superposition would "
            "put strained geometry in the pocket. Start your parameterisation from the crystal conformer.")
    flipped = inverted_centres(P, Q, [a.name for a, _ in pairs])
    if flipped:
        raise ValueError(
            f"your ligand is not the crystal's stereoisomer: the handedness around "
            f"{'; '.join(flipped[:4])} is inverted. RMSD cannot see this for a small ligand (a mirror "
            f"image can fit within {MAX_RMSD_NM * 10:.0f} A), and a Ki belongs to one stereoisomer. "
            "Parameterise the entry's own stereoisomer.")
    placed = [LigandAtom(a.name, a.element, a.xyz @ R + t) for a in yours]
    return Pose(placed, rmsd, matched, unmatched_crystal, unmatched_yours)


def protein_pdb(pdb_text: str, chain: Optional[str]) -> Tuple[str, Dict[str, int]]:
    """ATOM/TER records (one chain if asked), and every HETATM residue dropped."""
    keep, dropped = [], {}
    for line in pdb_text.splitlines():
        if line.startswith(("ATOM", "TER")) and (not chain or line[21:22] == chain):
            keep.append(line)
        elif line.startswith("HETATM") and (not chain or line[21:22] == chain):
            dropped[line[17:20].strip()] = dropped.get(line[17:20].strip(), 0) + 1
    return "\n".join(keep + ["END"]) + "\n", dropped


def ligand_gro(atoms: Sequence[LigandAtom], resname: str) -> str:
    lines = [f"{resname} posed on the crystal", f"{len(atoms):5d}"]
    for i, a in enumerate(atoms, start=1):
        x, y, z = a.xyz
        lines.append(f"{1:5d}{resname:<5}{a.name:>5}{i:5d}{x:8.3f}{y:8.3f}{z:8.3f}")
    lines.append("   0.00000   0.00000   0.00000")
    return "\n".join(lines) + "\n"


def build_script(pdb_id: str, moltype: str, itp_name: str, setup: MdSetup, resname: str = "") -> str:
    ff, water, seed = setup.force_field, setup.water, setup.seed
    return f"""#!/usr/bin/env bash
# Caterva complex: PDB {pdb_id.upper()} with {moltype} in its crystal pose. Read BUILD.md.
# Needs GROMACS (gmx). Stops at the first error. Output: npt.gro + topol.top.
set -euo pipefail
GMX="${{GMX:-gmx}}"
MDRUN_FLAGS="${{MDRUN_FLAGS:--ntmpi 1}}"
cd "$(dirname "$0")"

"$GMX" pdb2gmx -f protein.pdb -o protein.gro -p topol.top -ff {ff} -water {water} -ignh

# Protein + ligand in one coordinate file: the protein's atoms, then the
# ligand's, under the protein's box line.
awk 'FNR==NR {{ p[FNR]=$0; np=FNR; next }} {{ l[FNR]=$0; nl=FNR }}
     END {{ print "{pdb_id.upper()} with {moltype}"; print p[2]+l[2];
           for (i=3;i<np;i++) print p[i]; for (i=3;i<nl;i++) print l[i]; print p[np] }}' \\
    protein.gro ligand.gro > complex_vacuum.gro

# The ligand's topology goes straight after the force field, where its own
# [ atomtypes ] (if it has them) must be; its molecule after the protein's.
if ! grep -q '#include "{itp_name}"' topol.top; then
  awk '{{ print }} /#include ".*forcefield.itp"/ && !done {{ print "#include \\"{itp_name}\\""; done=1 }}' topol.top > topol.tmp
  mv topol.tmp topol.top
  printf '{moltype:<20}1\\n' >> topol.top
fi

"$GMX" editconf -f complex_vacuum.gro -o boxed.gro -c -d 1.0 -bt dodecahedron
"$GMX" solvate -cp boxed.gro -cs spc216.gro -o solvated.gro -p topol.top
"$GMX" grompp -f ions.mdp -c solvated.gro -p topol.top -o ions.tpr -maxwarn 1
echo SOL | "$GMX" genion -s ions.tpr -o ionized.gro -p topol.top -pname NA -nname CL -neutral -conc {setup.ionic_strength_m:g} -seed {seed}
"$GMX" grompp -f em.mdp -c ionized.gro -p topol.top -o em.tpr
"$GMX" mdrun -deffnm em $MDRUN_FLAGS
"$GMX" grompp -f nvt.mdp -c em.gro -r em.gro -p topol.top -o nvt.tpr
"$GMX" mdrun -deffnm nvt $MDRUN_FLAGS
"$GMX" grompp -f npt.mdp -c nvt.gro -r nvt.gro -t nvt.cpt -p topol.top -o npt.tpr
"$GMX" mdrun -deffnm npt $MDRUN_FLAGS
echo "done: equilibrated complex in $(pwd)/npt.gro, topology $(pwd)/topol.top"\necho "check the pose held: caterva complex --check $(pwd) --ligand {resname or moltype}"
"""


#: A ligand whose heavy atoms moved more than this from the crystal pose,
#: after the protein is superposed, is reported as having left it. 2 A: a
#: chosen threshold, about the distance at which a pose is called different
#: in docking benchmarks.
POSE_KEPT_NM = 0.20


def _gro(path: Path):
    lines = Path(path).read_text().splitlines()
    n = int(lines[1].split()[0])
    return [(l[5:10].strip(), l[10:15].strip(), np.array([float(l[20:28]), float(l[28:36]), float(l[36:44])]))
            for l in lines[2:2 + n]]


def itp_graph(itp: Path) -> Tuple[List[str], List[str], List[Tuple[int, int]]]:
    """(atom names, elements, bonds as 0-based pairs) from an .itp's first
    moleculetype. Elements are read from the atom names' leading letters."""
    names, bonds, section = [], [], None
    for raw in Path(itp).read_text().splitlines():
        line = raw.split(";", 1)[0].strip()
        if not line:
            continue
        if line.startswith("["):
            section = line.strip("[] ").lower()
            if section == "moleculetype" and names:
                break
            continue
        f = line.split()
        if section == "atoms" and len(f) >= 5:
            names.append(f[4])
        elif section == "bonds" and len(f) >= 2:
            bonds.append((int(f[0]) - 1, int(f[1]) - 1))
    return names, [_element(n) for n in names], bonds


def automorphisms(elements: Sequence[str], bonds: Sequence[Tuple[int, int]], limit: int = 20000) -> List[List[int]]:
    """Every relabelling of the atoms that keeps elements and bonds, by
    backtracking (the molecule's graph symmetries). Benzene's heavy atoms
    have 12; an asymmetric ligand has 1. Capped, and the cap is reported
    by the caller rather than silently truncating a symmetric answer."""
    n = len(elements)
    adj = [set() for _ in range(n)]
    for i, j in bonds:
        adj[i].add(j); adj[j].add(i)
    deg = [len(a) for a in adj]
    order = sorted(range(n), key=lambda i: -deg[i])
    out: List[List[int]] = []
    image = [-1] * n
    used = [False] * n

    def extend(k: int) -> None:
        if len(out) >= limit:
            return
        if k == n:
            out.append(image.copy())
            return
        i = order[k]
        for j in range(n):
            if used[j] or elements[j] != elements[i] or deg[j] != deg[i]:
                continue
            if any(image[a] != -1 and image[a] not in adj[j] for a in adj[i]):
                continue
            image[i], used[j] = j, True
            extend(k + 1)
            image[i], used[j] = -1, False

    extend(0)
    return out


def symmetric_rmsd(A: np.ndarray, B: np.ndarray, perms: Sequence[Sequence[int]]) -> float:
    """min over graph symmetries of RMSD(A, B[perm])."""
    return min(float(np.sqrt(((A - B[list(p)]) ** 2).sum(1).mean())) for p in perms)


def check(directory: Path, resname: str, itp: Optional[Path] = None) -> Tuple[float, float, int]:
    """(ligand heavy-atom RMSD nm, protein C-alpha RMSD nm, C-alpha count)
    between the built start (boxed.gro) and the equilibrated npt.gro, after
    superposing the protein's C-alpha atoms."""
    start, end = _gro(directory / "boxed.gro"), _gro(directory / "npt.gro")
    n = len(start)
    if [a[:2] for a in end[:n]] != [a[:2] for a in start]:
        raise ValueError("npt.gro does not begin with the atoms of boxed.gro; not this build's output")
    ca = [i for i, (res, name, _) in enumerate(start) if name == "CA" and res != resname]
    lig = [i for i, (res, name, _) in enumerate(start) if res == resname and not name.upper().startswith("H")]
    if len(ca) < 3 or not lig:
        raise ValueError(f"need C-alpha atoms and {resname} heavy atoms in {directory}/boxed.gro")
    P = np.array([end[i][2] for i in ca]); Q = np.array([start[i][2] for i in ca])
    R, t = kabsch(P, Q)
    ca_rmsd = float(np.sqrt((((P @ R + t) - Q) ** 2).sum(1).mean()))
    L = np.array([end[i][2] for i in lig]) @ R + t
    L0 = np.array([start[i][2] for i in lig])
    perms: List[List[int]] = [list(range(len(lig)))]
    itp = itp or next((p for p in sorted(directory.glob("*.itp")) if not p.name.startswith("posre")
                       and resname in p.read_text()), None)
    if itp is not None:
        names, elems, bonds = itp_graph(itp)
        heavy = [k for k, e in enumerate(elems) if e != "H"]
        lig_names = [start[i][1] for i in lig]
        if [names[k] for k in heavy] == lig_names:
            remap = {k: m for m, k in enumerate(heavy)}
            hb = [(remap[a], remap[b]) for a, b in bonds if a in remap and b in remap]
            perms = automorphisms([elems[k] for k in heavy], hb)
    return symmetric_rmsd(L0, L, perms), ca_rmsd, len(ca)


def pose_over_trajectory(directory: Path, resname: str, xtc_name: str = "npt.xtc",
                         itp: Optional[Path] = None) -> List[Tuple[float, float, float]]:
    """(time ps, symmetric RMSD nm, centroid shift nm) of the ligand in every
    frame of the equilibration, read natively from the .xtc: each frame's
    protein C-alpha atoms made whole and superposed on the start, the ligand
    made whole and moved to the periodic image nearest the protein."""
    from caterva.md import xtc
    start = _gro(directory / "boxed.gro")
    ca = [i for i, (res, name, _) in enumerate(start) if name == "CA" and res != resname]
    lig = [i for i, (res, name, _) in enumerate(start) if res == resname and not name.upper().startswith("H")]
    Q = np.array([start[i][2] for i in ca])
    L0 = np.array([start[i][2] for i in lig])
    perms: List[List[int]] = [list(range(len(lig)))]
    itp = itp or next((p for p in sorted(directory.glob("*.itp")) if not p.name.startswith("posre")
                       and resname in p.read_text()), None)
    if itp is not None:
        names, elems, bonds = itp_graph(itp)
        heavy = [k for k, e in enumerate(elems) if e != "H"]
        if [names[k] for k in heavy] == [start[i][1] for i in lig]:
            remap = {k: m for m, k in enumerate(heavy)}
            perms = automorphisms([elems[k] for k in heavy],
                                  [(remap[a], remap[b]) for a, b in bonds if a in remap and b in remap])
    out = []
    for f in xtc.frames(directory / xtc_name):
        P = xtc.make_whole(f.x[ca], f.box)
        L = xtc.make_whole(f.x[lig], f.box)
        L = L + xtc.nearest_image(L.mean(0) - P.mean(0), f.box)[0] - (L.mean(0) - P.mean(0))
        R, t = kabsch(P, Q)
        Lf = L @ R + t
        out.append((f.time, symmetric_rmsd(L0, Lf, perms), float(np.linalg.norm(Lf.mean(0) - L0.mean(0)))))
    return out


def centroid_shift(directory: Path, resname: str) -> float:
    """How far the ligand's heavy-atom centroid moved, protein superposed:
    blind to symmetry and to rotation in place, so it says whether the
    ligand stayed where it was even when the RMSD cannot."""
    start, end = _gro(directory / "boxed.gro"), _gro(directory / "npt.gro")
    ca = [i for i, (res, name, _) in enumerate(start) if name == "CA" and res != resname]
    lig = [i for i, (res, name, _) in enumerate(start) if res == resname and not name.upper().startswith("H")]
    P = np.array([end[i][2] for i in ca]); Q = np.array([start[i][2] for i in ca])
    R, t = kabsch(P, Q)
    c1 = (np.array([end[i][2] for i in lig]) @ R + t).mean(0)
    c0 = np.array([start[i][2] for i in lig]).mean(0)
    return float(np.linalg.norm(c1 - c0))


@dataclass
class PoseCheck:
    """What `--check DIR --ligand RES` measured and decided."""

    ligand: str
    #: Ligand heavy-atom RMSD from the crystal pose after equilibration
    #: (symmetry-equivalent poses counted as the same), nm.
    rmsd_nm: float
    #: The protein's C-alpha RMSD after superposition, nm, over `ca_atoms`.
    ca_rmsd_nm: float
    ca_atoms: int
    #: How far the ligand's heavy-atom centroid moved, protein superposed, nm.
    centroid_shift_nm: float
    #: (time ps, RMSD nm, centroid shift nm) per frame of npt.xtc, when present.
    series: Optional[List[Tuple[float, float, float]]]
    kept: bool

    @property
    def worst(self) -> Optional[Tuple[float, float, float]]:
        """The frame of npt.xtc with the largest RMSD."""
        return max(self.series, key=lambda r: r[1]) if self.series else None


def check_pose(directory: Path, resname: str) -> PoseCheck:
    """Did the ligand keep its crystal pose through equilibration? Kept when
    its RMSD in npt.gro, and in the worst frame of npt.xtc when there is
    one, is within POSE_KEPT_NM. Raises OSError or ValueError for a
    directory that is not a finished build."""
    rmsd, ca, n = check(directory, resname)
    kept = rmsd <= POSE_KEPT_NM
    series = None
    if (directory / "npt.xtc").is_file():
        series = pose_over_trajectory(directory, resname)
        kept = kept and max(r[1] for r in series) <= POSE_KEPT_NM
    return PoseCheck(resname, rmsd, ca, n, centroid_shift(directory, resname), series, kept)


def pose_lines(c: PoseCheck) -> List[str]:
    """What `--check` prints for a PoseCheck."""
    out = [f"{c.ligand}: heavy atoms {c.rmsd_nm * 10:.2f} A from the crystal pose after equilibration, "
           f"counting its symmetry-equivalent poses as the same pose; centroid moved "
           f"{c.centroid_shift_nm * 10:.2f} A (protein superposed on {c.ca_atoms} C-alpha atoms, which moved "
           f"{c.ca_rmsd_nm * 10:.2f} A)."]
    worst = c.worst
    if worst is not None:
        out.append(f"  over npt.xtc ({len(c.series)} frames, read natively): worst {worst[1] * 10:.2f} A at "
                   f"{worst[0]:.0f} ps, centroid at most {max(r[2] for r in c.series) * 10:.2f} A from the start")
    out.append("KEPT its pose: ready for caterva fep." if c.kept else
               f"LEFT its pose (more than {POSE_KEPT_NM * 10:.0f} A): the restraints caterva fep would "
               "choose would hold a pose the complex does not have. Check the ligand topology and "
               "protonation before spending the compute.")
    return out


def build_parser(prog: str = "caterva complex") -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=prog, description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--check", type=Path, metavar="DIR",
                   help="after build.sh: did the ligand keep its crystal pose through equilibration?")
    p.add_argument("--pdb", help="PDB entry id, or a local .pdb file")
    p.add_argument("--chain", help="keep one chain (and take the ligand from it)")
    p.add_argument("--ligand", help="the ligand's residue name in the entry (e.g. BNZ)")
    p.add_argument("--ligand-itp", type=Path, help="your ligand topology (.itp)")
    p.add_argument("--ligand-coords", type=Path,
                   help="the coordinates your parameterisation tool wrote (.gro or .pdb), same atom names as the itp")
    p.add_argument("--temperature", type=float, default=298.15, help="kelvin (default 298.15, chosen)")
    p.add_argument("--out", type=Path)
    return p


def main(argv: Optional[Sequence[str]] = None, prog: str = "caterva complex") -> int:
    p = build_parser(prog)
    try:
        a = p.parse_args(argv)
    except SystemExit as e:
        return EXIT_USAGE if e.code else EXIT_OK

    if a.check:
        if not a.ligand:
            print(f"{prog}: --check needs --ligand (the residue name)", file=sys.stderr)
            return EXIT_USAGE
        try:
            c = check_pose(a.check, a.ligand)
        except (OSError, ValueError) as e:
            print(f"{prog}: {e}", file=sys.stderr)
            return EXIT_REFUSED
        for line in pose_lines(c):
            print(line)
        return EXIT_OK if c.kept else 4
    missing = [f for f in ("pdb", "ligand", "ligand_itp", "ligand_coords", "out") if getattr(a, f) is None]
    if missing:
        print(f"{prog}: missing " + ", ".join("--" + m.replace("_", "-") for m in missing), file=sys.stderr)
        return EXIT_USAGE
    for f in (a.ligand_itp, a.ligand_coords):
        if not f.is_file():
            print(f"{prog}: {f} does not exist", file=sys.stderr)
            return EXIT_REFUSED
    local = Path(a.pdb)
    try:
        if local.is_file():
            pdb_text, pdb_id = local.read_text(), local.stem
        else:
            pdb_id = a.pdb.upper()
            with urllib.request.urlopen(f"https://files.rcsb.org/download/{pdb_id}.pdb", timeout=30) as r:
                pdb_text = r.read().decode()
    except Exception as e:
        print(f"{prog}: could not read PDB {a.pdb}: {e}", file=sys.stderr)
        return EXIT_REFUSED
    try:
        crystal, where = crystal_ligand(pdb_text, a.ligand, a.chain)
        pose = pose_onto_crystal(read_coords(a.ligand_coords), crystal)
        moltype = moleculetype_name(a.ligand_itp)
    except ValueError as e:
        print(f"{prog}: {e}", file=sys.stderr)
        return EXIT_REFUSED

    out = a.out
    out.mkdir(parents=True, exist_ok=True)
    protein, dropped = protein_pdb(pdb_text, a.chain)
    dropped.pop(a.ligand, None)
    setup = MdSetup(pdb_id, a.chain, Conditions(temperature_k=a.temperature,
                                                temperature_source="chosen: --temperature"),
                    replicas=1)
    mdps = setup.files()
    (out / "protein.pdb").write_text(protein)
    (out / "ligand.gro").write_text(ligand_gro(pose.atoms, a.ligand))
    (out / a.ligand_itp.name).write_text(a.ligand_itp.read_text())
    (out / "ions.mdp").write_text(mdps["ions.mdp"])
    (out / "em.mdp").write_text(mdps["em.mdp"])
    (out / "nvt.mdp").write_text(mdps["rep1/nvt.mdp"])
    (out / "npt.mdp").write_text(mdps["npt.mdp"])
    (out / "build.sh").write_text(build_script(pdb_id, moltype, a.ligand_itp.name, setup, a.ligand))
    (out / "BUILD.md").write_text(
        f"# Complex: PDB {pdb_id.upper()} + {a.ligand}\n\n"
        f"- Ligand pose: the entry's {a.ligand} ({where}); your coordinates superposed onto it "
        f"by {len(pose.matched)} shared heavy-atom names, RMSD {pose.rmsd_nm * 10:.3f} A "
        f"({METHODS['kabsch'].cite()}).\n"
        + (f"- Crystal heavy atoms with no partner in yours: {', '.join(pose.unmatched_crystal)}.\n"
           if pose.unmatched_crystal else "")
        + (f"- Your heavy atoms with no partner in the crystal: {', '.join(pose.unmatched_yours)}.\n"
           if pose.unmatched_yours else "")
        + f"- Dropped from the entry: {', '.join(f'{k} ({v} atoms)' for k, v in sorted(dropped.items())) or 'nothing'}.\n"
        f"- Equilibration: the mdp settings of `caterva md` (see its PROVENANCE), "
        f"{a.temperature:.2f} K, protein heavy atoms restrained; the ligand is free.\n"
        f"- Ligand topology {a.ligand_itp.name} (moleculetype {moltype}): yours, not generated.\n")
    print(f"Wrote {out}/: {a.ligand} posed from {where}, heavy-atom RMSD {pose.rmsd_nm * 10:.3f} A "
          f"over {len(pose.matched)} atoms.")
    if pose.unmatched_crystal:
        print(f"  crystal atoms with no partner in yours: {', '.join(pose.unmatched_crystal)}")
    print(f"  dropped: {', '.join(sorted(dropped)) or 'nothing'}")
    print(f"Then: bash {out}/build.sh")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
