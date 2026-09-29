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

Exit codes: 0 written, 3 refused and said why, 2 malformed question, 1 a crash.
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
    H = (P - pc).T @ (Q - qc)
    U, _, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    D = np.diag([1.0, 1.0, d])  # a rotation, never a reflection
    R = U @ D @ Vt
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


def build_script(pdb_id: str, moltype: str, itp_name: str, setup: MdSetup) -> str:
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
echo "done: equilibrated complex in $(pwd)/npt.gro, topology $(pwd)/topol.top"
"""


def main(argv: Optional[Sequence[str]] = None, prog: str = "caterva complex") -> int:
    p = argparse.ArgumentParser(prog=prog, description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--pdb", required=True, help="PDB entry id, or a local .pdb file")
    p.add_argument("--chain", help="keep one chain (and take the ligand from it)")
    p.add_argument("--ligand", required=True, help="the ligand's residue name in the entry (e.g. BNZ)")
    p.add_argument("--ligand-itp", type=Path, required=True, help="your ligand topology (.itp)")
    p.add_argument("--ligand-coords", type=Path, required=True,
                   help="the coordinates your parameterisation tool wrote (.gro or .pdb), same atom names as the itp")
    p.add_argument("--temperature", type=float, default=298.15, help="kelvin (default 298.15, chosen)")
    p.add_argument("--out", type=Path, required=True)
    try:
        a = p.parse_args(argv)
    except SystemExit as e:
        return EXIT_USAGE if e.code else EXIT_OK

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
    (out / "build.sh").write_text(build_script(pdb_id, moltype, a.ligand_itp.name, setup))
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
