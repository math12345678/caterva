"""`caterva analyze`: the questions an enzyme's mechanism asks of its trajectory.

    caterva md --pdb 1I10 --chain A --out ldha-md && bash ldha-md/run.sh
    caterva analyze ldha-md
    caterva analyze ldha-md --script-only     # write analyze.sh, run nothing

For every pair of catalytic residues (M-CSA, mapped by `caterva prepare`),
the distance between their functional groups in each replica, against the
same distance in the starting crystal structure; and the flexibility (RMSF)
of the active-site pocket against the rest of the protein. Where two
catalytic groups are both in contact with a third, the angle between them at
the third (caterva/analyze/angles.py) and which face of the third they are on
(caterva/analyze/faces.py); and at every catalytic residue, the water that
reaches its functional atoms (caterva/analyze/water.py) and how much of its
surface solvent can reach, against the whole protein
(caterva/analyze/sasa.py). Each
distance and angle is reported as a spread across replicas with
block-averaged errors, and called a result only when the replicas agree
(see `caterva md --summarise`).

Caterva does the measuring itself, from the .xtc files it reads natively
(caterva/md/xtc.py), so this runs where GROMACS is not installed. The
same measurements as GROMACS commands are written to analyze.sh, and
`--gromacs` uses them instead, as a cross-check.

Exit codes: 0 every distance and angle is a consistent result, 4 at least
one is not (unconverged, replicas disagree, one sample), 2 malformed
question, 3 refused and said why (no finished run, no catalytic residues),
1 a crash. The verdicts on the hydrogen bonds, rotamers, faces, water and
solvent exposure do not set it; each says "not yet a result" in the report
while the distances are not consistent.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from caterva.analyze.plan import CONTACT_NM, POCKET_RADIUS, Plan, plan, read_pdb
from caterva.analyze.angles import AngleResult
from caterva.analyze.faces import Face
from caterva.analyze.hbonds import Occupancy
from caterva.analyze.rotamers import Rotamer
from caterva.analyze.sasa import Exposure
from caterva.analyze.water import Hydration
from caterva.md.convergence import CONFIDENCE, Summary, summarise

CONFIDENCE_PCT = CONFIDENCE * 100

#: A consistent mean this far from the crystal distance is reported as the
#: geometry having changed. 0.1 nm (1 A) is about a hydrogen bond's length
#: tolerance; a choice, stated as one.
MOVED_NM = 0.1

EXIT_NOT_A_RESULT = 4
#: A fluctuation needs at least two frames; below that RMSF is not measured,
#: on either route.
MIN_RMSF_FRAMES = 2


class AnalyzeError(Exception):
    """The analysis could not be run, as distinct from finding nothing."""


def read_columns(path: Path) -> List[List[float]]:
    """All numeric columns of an .xvg: [times, col1, col2, ...]."""
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip() or line[0] in "#@":
            continue
        rows.append([float(x) for x in line.split()])
    return [list(c) for c in zip(*rows)] if rows else []


def setup_info(directory: Path) -> Tuple[str, Optional[str]]:
    """The PDB id and chain a `caterva md` directory was written for."""
    meta = directory / "caterva-setup.json"
    if meta.exists():
        d = json.loads(meta.read_text())
        return d["pdb"], d.get("chain")
    run = directory / "run.sh"
    if run.exists():
        m = re.search(r"# Caterva MD setup: PDB (\w{4})(?:, chain (\w))?", run.read_text())
        if m:
            return m.group(1), m.group(2)
    raise AnalyzeError(f"{directory} is not a `caterva md` setup (no caterva-setup.json or run.sh)")


def replicas(directory: Path) -> List[Path]:
    reps = sorted((p for p in directory.glob("rep*") if p.is_dir()),
                  key=lambda p: int(re.sub(r"\D", "", p.name) or 0))
    return [r for r in reps if (r / "md.xtc").exists() and (r / "md.tpr").exists()]


def catalytic_residues(pdb: str, chain: Optional[str]) -> Tuple[List[Tuple[int, str]], str]:
    """Catalytic residues in the structure's own numbering, via `caterva prepare`."""
    from caterva.prepare.__main__ import _cache_dir, cached, live_fetch, run_audit

    a = run_audit(pdb, cached(live_fetch(), _cache_dir()))
    if a.reference is None:
        raise AnalyzeError(f"no catalytic residues for {pdb}: {'; '.join(a.not_checked[:1])}")
    use = chain or (a.chains[0] if a.chains else None)
    out = []
    for c in a.catalytic:
        if c.chain == use and c.found and c.auth_seq_id.lstrip("-").isdigit():
            out.append((int(c.auth_seq_id), c.found))
    source = (f"M-CSA entry {a.reference.mcsa_id} ({a.reference.enzyme}), mapped onto {pdb} chain {use} "
              f"at {a.reference.identity:.0%} identity")
    return out, source


def chi1_groups(directory: Path, p: Plan) -> List[Tuple[int, str, Tuple[int, int, int, int]]]:
    """(resnr, label, 0-based N/CA/CB/gamma indices) for each catalytic
    residue with a chi1, read from em.gro; empty before run.sh has made it."""
    from caterva.analyze.rotamers import chi1_atoms
    gro = directory / "em.gro"
    if not gro.exists():
        return []
    atoms = _gro_atoms(gro)
    out = []
    for site in p.sites:
        idx = chi1_atoms(atoms, site.resnr)
        if idx is not None:
            out.append((site.resnr, site.label, idx))
    return out


def write_chi1_index(directory: Path, groups) -> None:
    """chi1.ndx: one group of four atoms (1-based) per catalytic residue."""
    lines = []
    for resnr, _, idx in groups:
        lines += [f"[ chi1_{resnr} ]", " ".join(str(i + 1) for i in idx)]
    (directory / "chi1.ndx").write_text("\n".join(lines) + "\n")


def water_selections(p: Plan) -> str:
    """One `gmx select` selection per catalytic residue, quoted for the shell."""
    from caterva.analyze.water import selection
    return " ".join(f"'{selection(s.resnr, s.atoms)}'" for s in p.sites)


def sasa_selections(p: Plan) -> str:
    """One `gmx sasa -output` selection per catalytic residue, quoted for the shell."""
    from caterva.analyze.sasa import output_selection
    return " ".join(f"'{output_selection(s.resnr)}'" for s in p.sites)


def commands(p: Plan, reps: Sequence[str], gmx: str = "$GMX", chi1: Sequence = ()) -> List[str]:
    from caterva.analyze.sasa import gmx_options
    sel = " ".join(f"'{q.selection()}'" for q in p.pairs)
    angle_sel = " ".join(f"'{t.selection()}'" for t in p.angles)
    plane_sel = " ".join(f"'{t.selection()}'" for t in p.faces)
    arm_sel = " ".join(f"'{t.arm_selection()}'" for t in p.faces)
    water_sel = water_selections(p)
    sasa_sel = sasa_selections(p)
    lines = []
    for r in reps:
        if p.pairs:
            lines.append(f'{gmx} distance -s {r}/md.tpr -f {r}/md.xtc -select {sel} '
                         f'-oall {r}/catalytic.xvg -tu ns')
        # gmx rmsf fits every frame to the -s coordinates AS STORED, and a
        # tpr stores them wrapped into the box: on lysozyme (1AKI, 2026-09-29)
        # residues 66-74 sat a box length from their neighbours, and the fit
        # to that broken reference put their RMSF about 10% high. So the
        # reference is em.gro made whole (the one the native route fits to)
        # and the trajectory is made whole first; the two routes then agree
        # to 0.0001 nm on every residue.
        lines.append(f"printf 'Protein\\n' | {gmx} trjconv -s {r}/md.tpr -f em.gro -pbc mol "
                     f"-o {r}/rmsf_reference.pdb")
        lines.append(f"printf 'Protein\\n' | {gmx} trjconv -s {r}/md.tpr -f {r}/md.xtc -pbc mol "
                     f"-o {r}/md_whole.xtc")
        lines.append(f"printf 'C-alpha\\n' | {gmx} rmsf -s {r}/rmsf_reference.pdb -f {r}/md_whole.xtc "
                     f"-res -o {r}/rmsf.xvg")
        # chi1 of each catalytic residue, on the whole-molecule trajectory
        # (protein atoms first, so em.gro's indices hold in it).
        for g, (resnr, _, _) in enumerate(chi1):
            lines.append(f"printf '{g}\\n' | {gmx} angle -f {r}/md_whole.xtc -n chi1.ndx -type dihedral "
                         f"-ov {r}/chi1_{resnr}.xvg")
        # Angles between catalytic groups: one -oav column per selection of
        # three centres (vertex in the middle). gangle makes molecules whole
        # from the tpr (-rmpbc, its default) before it takes the centres,
        # and its arms are periodic (-pbc, also default); the native route
        # makes each group whole and takes nearest images. On both 10 ps
        # lysozyme replicas (2026-09-29) the two agreed to 0.0006 degrees in
        # every frame, and gmx select's water counts to the native ones
        # exactly.
        if p.angles:
            lines.append(f"{gmx} gangle -s {r}/md.tpr -f {r}/md.xtc -g1 angle -group1 {angle_sel} "
                         f"-oav {r}/angles.xvg")
        # Which face of the vertex the partners are on: the angle between
        # the normal of each angle's plane and the arm from the vertex to
        # its own CA, one -oav column per angle whose vertex has a CA
        # (caterva/analyze/faces.py). On the frames of a lysozyme replica,
        # as stored and across the periodic box, it equals 90 degrees minus
        # the native elevation to 0.001 degree (2026-09-29).
        if p.faces:
            lines.append(f"{gmx} gangle -s {r}/md.tpr -f {r}/md.xtc -g1 plane -group1 {plane_sel} "
                         f"-g2 vector -group2 {arm_sel} -oav {r}/faces.xvg")
        # Water at each catalytic residue: -os prints how many water oxygens
        # each selection holds, frame by frame.
        if p.sites:
            lines.append(f"{gmx} select -s {r}/md.tpr -f {r}/md.xtc -select {water_sel} -os {r}/water.xvg")
        # Solvent-accessible area of each catalytic residue, the whole
        # protein as the surface (caterva/analyze/sasa.py). -o prints, per
        # frame, the protein's total and then one column per -output
        # selection, which is what the report reads; -or is every residue's
        # mean and SD over the run, for a reader who wants the rest of the
        # protein. -nopbc: the molecule is made whole from the tpr (gmx's
        # -rmpbc) and its periodic images are not part of its surface, as on
        # the native route.
        if p.sites:
            lines.append(f"{gmx} sasa -s {r}/md.tpr -f {r}/md.xtc {gmx_options()} -output {sasa_sel} "
                         f"-o {r}/sasa.xvg -or {r}/sasa_residues.xvg")
    if p.sites and reps:
        # The water at the start, from em.gro (the structure every replica
        # began from), counted once. The tpr supplies residue names and
        # numbers; em.gro has the same atoms in the same order.
        lines.append(f"{gmx} select -s {reps[0]}/md.tpr -f em.gro -select {water_sel} -os water_start.xvg")
        # And the area at the start, from the same em.gro.
        lines.append(f"{gmx} sasa -s {reps[0]}/md.tpr -f em.gro {gmx_options()} -output {sasa_sel} "
                     "-o sasa_start.xvg")
    return lines


def script(p: Plan, reps: Sequence[str], chi1: Sequence = ()) -> str:
    return ("#!/usr/bin/env bash\n# Written by `caterva analyze`. Needs GROMACS (gmx on PATH, or GMX=...).\n"
            "set -euo pipefail\nGMX=\"${GMX:-gmx}\"\ncd \"$(dirname \"$0\")\"\n\n"
            + "\n".join(commands(p, reps, chi1=chi1)) + "\n")


@dataclass
class DistanceResult:
    label: str
    crystal_nm: Optional[float]
    summary: Summary

    @property
    def drift_nm(self) -> Optional[float]:
        return None if self.crystal_nm is None else self.summary.mean - self.crystal_nm

    @property
    def moved(self) -> bool:
        return self.drift_nm is not None and abs(self.drift_nm) > MOVED_NM


@dataclass
class Flexibility:
    per_replica: List[Tuple[str, float, float]]  # (replica, pocket mean RMSF, rest mean RMSF)

    @property
    def ratios(self) -> List[float]:
        return [p / r for _, p, r in self.per_replica
                if r > 0 and not math.isnan(p) and not math.isnan(r)]


@dataclass
class Analysis:
    pdb: str
    chain: Optional[str]
    source: str
    plan: Plan
    distances: List[DistanceResult] = field(default_factory=list)
    flexibility: Optional[Flexibility] = None
    #: Hydrogen-bond occupancy between catalytic side chains; None when the
    #: GROMACS route measured (it does not count hydrogen bonds).
    hbonds: Optional[List["Occupancy"]] = None
    #: chi1 rotamers of the catalytic residues; None on the GROMACS route.
    rotamers: Optional[List["Rotamer"]] = None
    #: Angles between catalytic groups in contact; empty when no group has
    #: two partners within CONTACT_NM in the crystal.
    angles: List["AngleResult"] = field(default_factory=list)
    #: Water at each catalytic residue; None when it was not measured.
    water: Optional[List["Hydration"]] = None
    #: Which face of each angle's vertex its partners are on; None when it
    #: was not measured.
    faces: Optional[List["Face"]] = None
    #: Solvent-accessible area of each catalytic residue; None when it was
    #: not measured.
    sasa: Optional[List["Exposure"]] = None
    #: Which route measured the areas, "native" or "gromacs": the two place
    #: their points differently, and the section says which was used.
    sasa_route: str = "native"
    #: Why the areas were not measured, when they were not (sasa_unmeasurable).
    sasa_not_measured: Optional[str] = None

    @property
    def distances_consistent(self) -> bool:
        """Every catalytic distance is a consistent result: the evidence the
        other sections' verdicts rest on (the flexibility ratio, and the
        hydrogen bonds, rotamers, faces and water, which have no
        block-averaged error of their own). A section says "not yet a
        result" when this is False.

        The angles are left out of this gate on purpose. Each angle is fixed
        by three of these distances (the law of cosines, frame by frame), so
        it says nothing about whether the runs sampled enough that the
        distances do not; counting it here only made the gate stricter with
        quantities it already had. An earlier version did count them, and
        one unconverged angle then marked every other section as not a
        result while every distance was consistent.

        With no distance at all (fewer than two catalytic groups) nothing
        shows the runs converged, so this is False, and the report says why.
        """
        return bool(self.distances) and all(d.summary.verdict == "consistent" for d in self.distances)

    @property
    def all_consistent(self) -> bool:
        """For the exit code: every distance and every angle is a consistent
        result. The angles count here although they do not gate the other
        sections, because their verdict is the same kind as the distances'
        (do the replicas agree on a measured value). The hydrogen bonds,
        rotamers, faces, water and solvent exposure carry verdicts too, but
        they classify against chosen thresholds, and each says "not yet a
        result" while the distances are not consistent; they do not set the
        exit code, as the module docstring and --help say."""
        return self.distances_consistent and all(t.summary.verdict == "consistent" for t in self.angles)


def measure(directory: Path, p: Plan, reps: Sequence[Path],
            chi1: Sequence = ()) -> Tuple[List[DistanceResult], Flexibility, List["Rotamer"]]:
    per_pair: Dict[int, List[Tuple[str, List[float]]]] = {i: [] for i in range(len(p.pairs))}
    flex = []
    pocket, rest = set(p.pocket), set(p.rest)
    for r in reps:
        frames = None
        if p.pairs:
            cols = read_columns(r / "catalytic.xvg")
            frames = len(cols[0])
            for i in range(len(p.pairs)):
                per_pair[i].append((r.name, [x for x in cols[i + 1]]))
        if frames is not None and frames < MIN_RMSF_FRAMES:
            # One frame has no fluctuation. gmx rmsf still prints 0.0001-
            # 0.0002 nm, its single-precision sqrt(<x^2> - <x>^2) on
            # coordinates of a few nm, and the native route says not
            # measurable; CI's comparison of the two routes found it.
            continue
        cols = read_columns(r / "rmsf.xvg")
        rmsf = dict(zip((int(x) for x in cols[0]), cols[1]))
        pv = [v for k, v in rmsf.items() if k in pocket and not math.isnan(v)]
        rv = [v for k, v in rmsf.items() if k in rest and not math.isnan(v)]
        if pv and rv:
            flex.append((r.name, sum(pv) / len(pv), sum(rv) / len(rv)))
    results = [DistanceResult(q.label, q.crystal_nm, summarise(per_pair[i], q.label, "nm"))
               for i, q in enumerate(p.pairs)]
    return results, Flexibility(flex), _gromacs_rotamers(directory, reps, chi1)


def _gromacs_rotamers(directory: Path, reps: Sequence[Path], chi1: Sequence) -> List["Rotamer"]:
    """Rotamers from gmx angle's chi1_<resnr>.xvg, with the starting chi1
    computed from em.gro (the same dihedral, checked against gmx angle)."""
    from caterva.analyze.rotamers import dihedral, populations
    if not chi1:
        return []
    gro = directory / "em.gro"
    x = [a[3] for a in _gro_atoms(gro)]
    box = _gro_box(gro.read_text().splitlines()[-1])
    out = []
    for resnr, label, idx in chi1:
        per = []
        for r in reps:
            xvg = r / f"chi1_{resnr}.xvg"
            if xvg.exists():
                per.append((r.name, populations(read_columns(xvg)[1])))
        out.append(Rotamer(label, dihedral(*(x[i] for i in idx), box), per))
    return out


def _gromacs_output(path: Path, what: str, columns: int) -> List[List[float]]:
    """An .xvg analyze.sh wrote, with the columns this plan expects. An older
    analyze.sh, or one written for another plan, is refused by name rather
    than read into the wrong rows.

    A missing file is refused too, where the rotamer route above skips a
    missing chi1 file. Skipping here would leave the angles out of
    Analysis.all_consistent, so `--gromacs --no-run` on the .xvg files of
    an analyze.sh older than the angle table could exit 0 without having
    measured one. So a run analysed before the angle and water tables
    existed has to run analyze.sh again (the message says so); the
    --no-run help and docs/USING_CATERVA.md say it too."""
    if not path.exists():
        raise AnalyzeError(f"{path} does not exist: run analyze.sh again (it measures {what})")
    cols = read_columns(path)
    if not cols:
        # Headers and no rows: a gmx run that stopped before its first
        # frame. "0 columns" would send the reader looking for the wrong fault.
        raise AnalyzeError(f"{path} has no frames of {what}: run analyze.sh again")
    if len(cols) != columns + 1:
        raise AnalyzeError(f"{path} has {max(len(cols) - 1, 0)} columns of {what}, the plan has {columns}: "
                           "run analyze.sh again")
    return cols


def gromacs_angles(p: Plan, reps: Sequence[Path]) -> List[AngleResult]:
    """Angles from gmx gangle's angles.xvg (-oav: one column per planned
    angle, in the plan's order), summarised as the native route does."""
    if not p.angles:
        return []
    per: Dict[int, List[Tuple[str, List[float]]]] = {i: [] for i in range(len(p.angles))}
    for r in reps:
        cols = _gromacs_output(r / "angles.xvg", "angles between catalytic groups", len(p.angles))
        for i in range(len(p.angles)):
            per[i].append((r.name, cols[i + 1]))
    return [AngleResult(t.label, t.crystal_deg, summarise(per[i], t.label, "degrees"))
            for i, t in enumerate(p.angles)]


def _face(t, per_replica) -> Face:
    """A Face for one of the plan's angles, with its crystal values."""
    from caterva.analyze.faces import polar_sine
    return Face(t.label, t.crystal_elevation_deg, polar_sine(t.crystal_deg, t.crystal_elevation_deg),
                list(per_replica))


def gromacs_faces(p: Plan, reps: Sequence[Path]) -> List[Face]:
    """Faces from gmx gangle's faces.xvg (-oav: one column per angle whose
    vertex has a CA, in the plan's order: the angle between the normal of
    the angle's plane and the arm to the CA, which is 90 degrees minus the
    elevation) and the angles themselves from angles.xvg, which the polar
    sine needs; judged frame by frame as the native route judges them."""
    from caterva.analyze.faces import face_fractions, from_gangle, polar_sine, side
    faces = p.faces
    if not faces:
        return []
    where = [p.angles.index(t) for t in faces]
    per: Dict[int, List[Tuple[str, float, float]]] = {i: [] for i in range(len(faces))}
    for r in reps:
        angles = _gromacs_output(r / "angles.xvg", "angles between catalytic groups", len(p.angles))
        cols = _gromacs_output(r / "faces.xvg", "which face of each angle's vertex its partners are on",
                               len(faces))
        if len(cols[0]) != len(angles[0]):
            raise AnalyzeError(f"{r / 'faces.xvg'} has {len(cols[0])} frames and {r / 'angles.xvg'} "
                               f"{len(angles[0])}: run analyze.sh again")
        for i, t in enumerate(faces):
            crystal = side(polar_sine(t.crystal_deg, t.crystal_elevation_deg))
            per[i].append(face_fractions(r.name, angles[where[i] + 1], [from_gangle(x) for x in cols[i + 1]],
                                         crystal))
    return [_face(t, per[i]) for i, t in enumerate(faces)]


def gromacs_water(directory: Path, p: Plan, reps: Sequence[Path]) -> List[Hydration]:
    """Water counts from gmx select's water.xvg (-os: one column per
    catalytic residue) and, for the start, water_start.xvg from em.gro."""
    from caterva.analyze.water import summarise_counts
    if not p.sites:
        return []
    what = "water at the catalytic residues"
    start = _gromacs_output(directory / "water_start.xvg", what, len(p.sites))
    per: Dict[int, List[Tuple[str, float, float]]] = {i: [] for i in range(len(p.sites))}
    for r in reps:
        cols = _gromacs_output(r / "water.xvg", what, len(p.sites))
        for i in range(len(p.sites)):
            per[i].append(summarise_counts(r.name, [int(round(v)) for v in cols[i + 1]]))
    return [Hydration(s.label, int(round(start[i + 1][0])), per[i]) for i, s in enumerate(p.sites)]


def _sasa_surface(directory: Path, p: Plan):
    """The protein of em.gro as a sasa.Surface for the catalytic residues,
    or refused by name: a residue not in it, or whose number belongs to two
    residues (more than one chain simulated, or an insertion code), would
    give no residue's area."""
    from caterva.analyze.sasa import Surface
    gro = directory / "em.gro"
    try:
        return Surface(_gro_atoms(gro), [s.resnr for s in p.sites], protein=set(p.pocket) | set(p.rest),
                       box=_gro_box(gro.read_text().splitlines()[-1]))
    except ValueError as e:
        raise AnalyzeError(f"solvent exposure: {e}") from None


def sasa_unmeasurable(directory: Path, p: Plan) -> Optional[str]:
    """Why the solvent exposure cannot be measured on this system, or None.
    A catalytic residue whose number belongs to two residues (more than one
    chain simulated, which `caterva md` does by default, or an insertion
    code), or one em.gro does not have, has no area of its own. Only the
    section is dropped, with the reason in its place: refusing the whole
    analysis for it would withhold the distances, RMSF, angles and water,
    which were reported for such runs before this section existed. Those
    sections share the underlying defect (`plan` merges atoms of the same
    residue number), which this does not fix."""
    if not p.sites or not (directory / "em.gro").exists():
        return None
    try:
        _sasa_surface(directory, p)
    except AnalyzeError as e:
        return str(e).removeprefix("solvent exposure: ")
    return None


def _exposures(p: Plan, at_start: Sequence[float], per: Dict[int, List[Tuple[str, float, float, float, float]]],
               in_chain: Optional[Sequence[bool]] = None) -> List[Exposure]:
    """One Exposure per catalytic residue, with whether it is inside the
    chain, which Tien et al.'s maxima need: `in_chain`, a peptide bond on
    both sides in em.gro (sasa.Surface.in_chain), as both routes give it.
    Without em.gro, which analyze.sh reads too, so only a directory it has
    not run in lacks it, the first and last residue numbers of protein.pdb
    are the chain's ends and no break is seen."""
    if in_chain is None:
        residues = set(p.pocket) | set(p.rest)
        ends = (min(residues), max(residues)) if residues else ()
        in_chain = [s.resnr not in ends for s in p.sites]
    return [Exposure(s.label, s.resname, float(at_start[i]), per[i], bool(in_chain[i]))
            for i, s in enumerate(p.sites)]


def gromacs_sasa(directory: Path, p: Plan, reps: Sequence[Path]) -> List[Exposure]:
    """Areas from gmx sasa's sasa.xvg (-o: the protein's total area, then
    one column per catalytic residue, frame by frame) and, for the start,
    sasa_start.xvg from em.gro; summarised as the native route summarises
    its own. em.gro, when it is there, is checked as the native route checks
    it (main asks sasa_unmeasurable first and does not call this when it
    gives a reason), so a residue numbered in two chains is not summed on
    this route while refused on the other."""
    from caterva.analyze.sasa import summarise_areas
    if not p.sites:
        return []
    surface = _sasa_surface(directory, p) if (directory / "em.gro").exists() else None
    what = "solvent-accessible area (one column for the whole protein, then one per catalytic residue)"

    def areas(path: Path) -> List[List[float]]:
        cols = _gromacs_output(path, what, len(p.sites) + 1)
        if not all(math.isfinite(v) for c in cols[1:] for v in c):
            # An area that is not a number is a damaged file, not a frame
            # without solvent. Summarised, it would print the replica as
            # "n/a" with the verdict "no frames", over frames that are valid.
            raise AnalyzeError(f"{path} has an area that is not a number: run analyze.sh again")
        return cols

    start = areas(directory / "sasa_start.xvg")
    per: Dict[int, List[Tuple[str, float, float, float, float]]] = {i: [] for i in range(len(p.sites))}
    for r in reps:
        cols = areas(r / "sasa.xvg")
        for i in range(len(p.sites)):
            per[i].append(summarise_areas(r.name, cols[i + 2]))
    return _exposures(p, [start[i + 2][0] for i in range(len(p.sites))], per,
                      surface.in_chain if surface is not None else None)


def _gro_index(path: Path) -> Dict[Tuple[int, str], int]:
    """(residue number, atom name) -> 0-based index in the simulated system,
    first occurrence; the numbering pdb2gmx keeps."""
    lines = path.read_text().splitlines()
    n = int(lines[1].split()[0])
    out: Dict[Tuple[int, str], int] = {}
    for i, l in enumerate(lines[2:2 + n]):
        out.setdefault((int(l[0:5]), l[10:15].strip()), i)
    return out


def distance_series(traj, ia: Sequence[int], ib: Sequence[int]) -> List[float]:
    """Per frame, the distance (nm) between the geometric centres of two atom
    groups, each made whole, across periodic boundaries: `gmx distance -select
    'cog of (...) plus cog of (...)'`, computed by Caterva."""
    import numpy as np
    from caterva.md import xtc
    out = []
    for f in traj:
        ca_ = xtc.make_whole(f.x[list(ia)], f.box).mean(0)
        cb_ = xtc.make_whole(f.x[list(ib)], f.box).mean(0)
        out.append(float(np.linalg.norm(xtc.nearest_image(cb_ - ca_, f.box)[0])))
    return out


def _gro_box(line: str):
    """A .gro box line as box vectors (rows): 3 values for a rectangular box,
    9 for a triclinic one, in the order v1(x) v2(y) v3(z) v1(y) v1(z) v2(x)
    v2(z) v3(x) v3(y)."""
    import numpy as np
    v = [float(x) for x in line.split()]
    box = np.diag(v[:3])
    if len(v) == 9:
        box[0, 1], box[0, 2], box[1, 0], box[1, 2], box[2, 0], box[2, 1] = v[3:9]
    return box


def _gro_atoms(path: Path):
    """(resnr, resname, name, xyz) for every atom of a .gro file."""
    import numpy as np
    lines = path.read_text().splitlines()
    n = int(lines[1].split()[0])
    return [(int(l[0:5]), l[5:10].strip(), l[10:15].strip(),
             np.array([float(l[20 + 8 * k:28 + 8 * k]) for k in range(3)])) for l in lines[2:2 + n]]


def measure_native(directory: Path, p: Plan, reps: Sequence[Path], sasa: bool = True
                   ) -> Tuple[List[DistanceResult], Flexibility, List["Occupancy"], List["Rotamer"],
                              List[AngleResult], List[Hydration], List[Face], Optional[List[Exposure]]]:
    """The same distances, RMSF, chi1, angles, faces, water counts and
    solvent-accessible areas as analyze.sh, and the hydrogen bonds it does
    not count, computed by Caterva from the trajectories it reads itself
    (caterva/md/xtc.py), with no GROMACS. Each trajectory is read once and
    every quantity taken from it."""
    import numpy as np
    from caterva.md import xtc
    ref_gro = directory / "em.gro"
    if not ref_gro.exists():
        raise AnalyzeError(f"{ref_gro} does not exist: run {directory}/run.sh first")
    index = _gro_index(ref_gro)

    def atoms_of(site) -> List[int]:
        missing = [n for n in site.atoms if (site.resnr, n) not in index]
        if missing:
            raise AnalyzeError(f"{site.label}: atom(s) {', '.join(missing)} not in {ref_gro.name}")
        return [index[(site.resnr, n)] for n in site.atoms]

    pair_atoms = [(atoms_of(q.a), atoms_of(q.b)) for q in p.pairs]
    residues = sorted(set(p.pocket) | set(p.rest))
    ca = [(r, index[(r, "CA")]) for r in residues if (r, "CA") in index]
    ref_lines = ref_gro.read_text().splitlines()
    ref = np.array([[float(ref_lines[2 + i][20 + 8 * k:28 + 8 * k]) for k in range(3)] for _, i in ca])
    from caterva.analyze.hbonds import Occupancy, count_frame, occupancy, side_chain_group
    per_pair: Dict[int, List[Tuple[str, List[float]]]] = {i: [] for i in range(len(p.pairs))}
    flex = []
    pocket, rest = set(p.pocket), set(p.rest)
    atoms = _gro_atoms(ref_gro)
    groups = {}
    for q in p.pairs:
        for site in (q.a, q.b):
            if site.resnr not in groups:
                try:
                    groups[site.resnr] = side_chain_group(atoms, site.resnr)
                except ValueError:
                    groups[site.resnr] = None  # glycine: no side chain to bond
    start_x = np.array([a[3] for a in atoms])
    start_box = _gro_box(ref_lines[-1])
    from caterva.analyze.rotamers import Rotamer, chi1_atoms, chi1_series, dihedral, populations
    chi_sites = []
    for site in p.sites:
        idx = chi1_atoms(atoms, site.resnr)
        if idx is not None:
            chi_sites.append((site, idx))
    chi_pops: Dict[int, List[Tuple[str, Dict[str, float]]]] = {site.resnr: [] for site, _ in chi_sites}
    hb: Dict[int, List[Tuple[str, float, float]]] = {i: [] for i in range(len(p.pairs))}
    from caterva.analyze.angles import angle_series
    from caterva.analyze import water as wat
    angle_atoms = [(atoms_of(t.a), atoms_of(t.v), atoms_of(t.b)) for t in p.angles]
    per_angle: Dict[int, List[Tuple[str, List[float]]]] = {i: [] for i in range(len(p.angles))}
    from caterva.analyze.faces import elevation_series, face_fractions, polar_sine, side
    face_where = [p.angles.index(t) for t in p.faces]
    for t in p.faces:
        if (t.v.resnr, "CA") not in index:
            raise AnalyzeError(f"{t.v.label}: atom CA not in {ref_gro.name}")
    face_ca = [index[(t.v.resnr, "CA")] for t in p.faces]
    per_face: Dict[int, List[Tuple[str, float, float]]] = {i: [] for i in range(len(p.faces))}
    site_atoms = [atoms_of(s) for s in p.sites]
    oxygens = np.array(wat.water_oxygens(atoms), dtype=int)
    per_water: Dict[int, List[Tuple[str, float, float]]] = {i: [] for i in range(len(p.sites))}
    from caterva.analyze.sasa import summarise_areas
    surface = _sasa_surface(directory, p) if p.sites and sasa else None
    per_area: Dict[int, List[Tuple[str, float, float, float, float]]] = {i: [] for i in range(len(p.sites))}
    for r in reps:
        traj = xtc.read(r / "md.xtc")
        for i, (ia, iv, ib) in enumerate(angle_atoms):
            per_angle[i].append((r.name, angle_series(traj, ia, iv, ib)))
        for i, t in enumerate(p.faces):
            j = face_where[i]
            crystal = side(polar_sine(t.crystal_deg, t.crystal_elevation_deg))
            per_face[i].append(face_fractions(r.name, per_angle[j][-1][1],
                                              elevation_series(traj, *angle_atoms[j], face_ca[i]), crystal))
        for i, idx in enumerate(site_atoms):
            per_water[i].append(wat.summarise_counts(r.name, wat.counts(traj, idx, oxygens)))
        if surface is not None:
            for i, series in enumerate(surface.series(traj)):
                per_area[i].append(summarise_areas(r.name, series))
        for i, q in enumerate(p.pairs):
            ga, gb = groups[q.a.resnr], groups[q.b.resnr]
            if ga is not None and gb is not None:
                frac, mean, _ = occupancy(traj, ga, gb)
                hb[i].append((r.name, frac, mean))
        for i, (ia, ib) in enumerate(pair_atoms):
            per_pair[i].append((r.name, distance_series(traj, ia, ib)))
        for site, idx in chi_sites:
            chi_pops[site.resnr].append((r.name, populations(chi1_series(traj, idx))))
        if len(traj) < MIN_RMSF_FRAMES:
            continue
        f_ca = xtc.rmsf(traj, [i for _, i in ca], ref)
        rmsf = {res: float(v) for (res, _), v in zip(ca, f_ca)}
        pv = [v for k, v in rmsf.items() if k in pocket]
        rv = [v for k, v in rmsf.items() if k in rest]
        if pv and rv:
            flex.append((r.name, sum(pv) / len(pv), sum(rv) / len(rv)))
    results = [DistanceResult(q.label, q.crystal_nm, summarise(per_pair[i], q.label, "nm"))
               for i, q in enumerate(p.pairs)]
    occupancies = []
    for i, q in enumerate(p.pairs):
        ga, gb = groups[q.a.resnr], groups[q.b.resnr]
        if ga is None or gb is None:
            continue
        occupancies.append(Occupancy(q.label, hb[i], count_frame(start_x, start_box, ga, gb)))
    rotamers = [Rotamer(site.label, dihedral(*(start_x[i] for i in idx), start_box), chi_pops[site.resnr])
                for site, idx in chi_sites]
    angles = [AngleResult(t.label, t.crystal_deg, summarise(per_angle[i], t.label, "degrees"))
              for i, t in enumerate(p.angles)]
    water = [Hydration(s.label, wat.count_frame(start_x, start_box, site_atoms[i], oxygens), per_water[i])
             for i, s in enumerate(p.sites)]
    faces = [_face(t, per_face[i]) for i, t in enumerate(p.faces)]
    # sasa=False (sasa_unmeasurable gave a reason): None, not measured.
    exposures = (_exposures(p, surface.areas(start_x, start_box), per_area, surface.in_chain)
                 if surface is not None else ([] if sasa else None))
    return results, Flexibility(flex), occupancies, rotamers, angles, water, faces, exposures


#: Occupancy thresholds for naming what happened to a hydrogen bond. Chosen,
#: and printed with the table.
KEPT, LOST, FORMED, SPLIT = 0.8, 0.2, 0.5, 0.5


def hbond_verdict(o) -> str:
    fr = o.fractions
    if len(fr) < 2:
        return "one replica"
    if max(fr) - min(fr) > SPLIT:
        return "replicas disagree"
    if o.at_start > 0 and min(fr) >= KEPT:
        return "kept"
    if o.at_start > 0 and max(fr) <= LOST:
        return "lost"
    if o.at_start == 0 and min(fr) >= FORMED:
        return "formed"
    if o.at_start == 0 and max(fr) <= LOST:
        return "rarely formed"
    return "partial"


def run_gromacs(directory: Path, p: Plan, reps: Sequence[Path], gmx: str, chi1: Sequence = ()) -> None:
    for line in commands(p, [r.name for r in reps], gmx=shlex_quote(gmx), chi1=chi1):
        proc = subprocess.run(["bash", "-c", line], cwd=directory, capture_output=True, text=True)
        if proc.returncode != 0:
            raise AnalyzeError(f"GROMACS failed:\n  {line}\n{proc.stderr.strip()[-800:]}")


def shlex_quote(s: str) -> str:
    import shlex
    return shlex.quote(s)


def report(a: Analysis) -> List[str]:
    L = [f"# Enzyme analysis: {a.pdb}" + (f" chain {a.chain}" if a.chain else ""), "",
         f"Catalytic residues from {a.source}.", ""]
    if a.plan.notes:
        L += [f"- {n}" for n in a.plan.notes] + [""]
    L += ["## Catalytic geometry", "",
          "Distance between the functional groups of each pair of catalytic residues "
          "(geometric centres), across replicas, against the starting crystal structure.", "",
          "| pair | crystal (nm) | simulated (nm, mean ± SD of replicas) | 95% CI of the mean | change | verdict |",
          "|---|---|---|---|---|---|"]
    for d in a.distances:
        s = d.summary
        sim = f"{s.mean:.3f}" + (f" ± {s.spread:.3f}" if s.spread is not None else "")
        cr = "?" if d.crystal_nm is None else f"{d.crystal_nm:.3f}"
        if d.drift_nm is None:
            ch = "?"
        elif s.verdict != "consistent":
            ch = f"({d.drift_nm:+.3f}, not yet a result)"
        else:
            ch = f"**{d.drift_nm:+.3f}, moved**" if d.moved else f"{d.drift_nm:+.3f}, held"
        ci = "n/a" if math.isnan(s.ci95) else f"± {s.ci95:.3f}"
        L.append(f"| {d.label} | {cr} | {sim} | {ci} | {ch} | {s.verdict} |")
    L.append("")
    if not a.distances:
        # The verdicts of every later section rest on the distances
        # (Analysis.distances_consistent). Without one, each of them reads
        # "not yet a result", and this is the reason, said once.
        L += ["- No catalytic distance: fewer than two catalytic groups, so no pair to measure. The distances "
              "are what shows the runs converged, so no verdict below can be a result.", ""]
    L += replica_sufficiency(a)
    grouped: Dict[str, List[str]] = {}
    for d in a.distances:
        if d.summary.verdict != "consistent" and d.summary.reasons:
            grouped.setdefault(d.summary.reasons[0], []).append(d.label)
    for reason, labels in grouped.items():
        who = "every pair" if len(labels) == len(a.distances) and len(labels) > 1 else ", ".join(labels)
        L.append(f"- {who}: {reason}")
    L += hbond_section(a)
    L += rotamer_section(a)
    L += angle_section(a)
    L += face_section(a)
    L += water_section(a)
    L += sasa_section(a)
    f = a.flexibility
    L += ["", "## Active-site flexibility", "",
          f"Mean Cα RMSF of the {len(a.plan.pocket)} residues within {POCKET_RADIUS:g} Å of a catalytic "
          f"residue (the pocket) against the other {len(a.plan.rest)}.", ""]
    rs = f.ratios if f else []
    if f and f.per_replica and rs:
        L += ["| replica | pocket (nm) | rest (nm) | pocket / rest |", "|---|---|---|---|"]
        for name, pv, rv in f.per_replica:
            ratio = f"{pv / rv:.2f}" if rv > 0 else "n/a"
            L.append(f"| {name} | {pv:.4f} | {rv:.4f} | {ratio} |")
        if len(rs) > 1:
            m = sum(rs) / len(rs)
            sd = math.sqrt(sum((x - m) ** 2 for x in rs) / (len(rs) - 1))
            if a.distances_consistent:
                L += ["", f"Pocket / rest: {m:.2f} ± {sd:.2f} across {len(rs)} replicas "
                          "(below 1: the active site is more rigid than the protein around it)."]
            else:
                L += ["", f"Not yet a result: pocket / rest {m:.2f} ± {sd:.2f}, from runs the catalytic "
                          "distances above do not show to be converged. RMSF from unconverged runs "
                          "measures how far each residue got, not how mobile it is."]
        else:
            L += ["", "One usable replica: the ratio has no spread."]
    else:
        L += ["Not measurable: RMSF needs more than one frame per replica, and these runs are too short."]
    L += ["", "## Not measured", "",
          "- ligand pose and contacts: `caterva md` strips ligands until they can be parameterised "
          "(MD roadmap M4)", "",
          f"`{MOVED_NM:g} nm` is the chosen threshold for calling a distance changed. The measuring commands "
          "are in analyze.sh. Errors: Flyvbjerg & Petersen (1989) J. Chem. Phys. 91:461, "
          "doi:10.1063/1.457480. Catalytic residues: Ribeiro et al. (2018) Nucleic Acids Res. "
          "46:D618, doi:10.1093/nar/gkx1012."]
    return L


#: The precision a catalytic distance needs before "held" or "moved" can be
#: decided with confidence: half the moved threshold, so the interval cannot
#: straddle both answers. A choice, derived from MOVED_NM.
RESOLVE_NM = MOVED_NM / 2


def replica_sufficiency(a: Analysis) -> List[str]:
    """Are there enough replicas to decide held or moved? From the spread the
    replicas actually show, not a rule of thumb."""
    return _sufficiency([(d.label, d.summary) for d in a.distances], RESOLVE_NM, MOVED_NM, " nm", 3,
                        "distance")


def _sufficiency(items: Sequence[Tuple[str, Summary]], resolve: float, moved: float, unit: str,
                 digits: int, noun: str, explain: bool = True) -> List[str]:
    """replica_sufficiency for any quantity with a moved threshold: the
    distances, and the angles with theirs. `items` is (label, Summary)."""
    measured = [(label, s) for label, s in items if s.spread is not None and not math.isnan(s.ci95)]
    if not measured:
        return []
    n = len(measured[0][1].replicas)
    short = [(label, s, s.replicas_for(resolve)) for label, s in measured if s.ci95 > resolve]
    if not short:
        return [f"- Replicas: {n} are enough; every {noun}'s {int(CONFIDENCE_PCT)}% confidence interval is "
                f"within ± {resolve:g}{unit}, half the {moved:g}{unit} moved threshold.", ""]
    worst = max(short, key=lambda x: x[1].ci95)
    needs = [k for _, _, k in short if k is not None]
    most = max(needs) if needs else None
    return [f"- Replicas: {n} are not enough to decide held or moved for {len(short)} of {len(measured)} "
            f"{noun}s: their {int(CONFIDENCE_PCT)}% confidence intervals are wider than ± {resolve:g}{unit} "
            f"(worst: {worst[0]}, ± {worst[1].ci95:.{digits}f}{unit}). "
            + (f"If the spread between runs stays as it is, {most} replicas would resolve all of them."
               if most else "Even many more replicas would not, at the spread seen: the runs are too short.")
            + (" (With few replicas the interval is wide by construction: Student's t for 2 replicas is 12.7; "
               "and two runs estimate the spread itself poorly, so treat that count as a first guess.)"
               if explain else ""),
            ""]


def hbond_section(a: Analysis) -> List[str]:
    L = ["", "## Hydrogen bonds between catalytic side chains", ""]
    if a.hbonds is None:
        return L + ["Not measured on the GROMACS route (`--gromacs`); the native route counts them."]
    bonded = [o for o in a.hbonds if o.at_start or any(f > 0 for f in o.fractions)]
    L += ["Fraction of frames in which two catalytic side chains are hydrogen-bonded, per replica. "
          "Donor-acceptor at most 0.35 nm and acceptor-donor-hydrogen at most 30 degrees, the criterion "
          "of `gmx hbond`; backbone atoms excluded.", ""]
    if not bonded:
        return L + [f"None of the {len(a.hbonds)} pairs of catalytic side chains hydrogen-bonded, at the "
                    "start or in any frame."]
    names = [n for n, _, _ in bonded[0].per_replica]
    L += ["| pair | bonds at start | " + " | ".join(names) + " | verdict |",
          "|---|---|" + "---|" * len(names) + "---|"]
    for o in bonded:
        v = hbond_verdict(o)
        if not a.distances_consistent and v not in ("one replica",):
            v = f"({v}, not yet a result)"
        L.append(f"| {o.label} | {o.at_start} | " + " | ".join(f"{f:.2f}" for f in o.fractions) + f" | {v} |")
    never = len(a.hbonds) - len(bonded)
    if never:
        L += ["", f"The other {never} pair(s) never hydrogen-bonded, at the start or in any frame."]
    L += ["", f"Verdicts (chosen thresholds): kept, bonded at the start and in at least {KEPT:.0%} of frames "
          f"in every replica; lost, bonded at the start and in at most {LOST:.0%}; formed, not bonded at the "
          f"start and in at least {FORMED:.0%}; rarely formed, not bonded at the start and in at most "
          f"{LOST:.0%}; replicas disagree, when their occupancies differ by more "
          f"than {SPLIT:.0%}."]
    return L


def rotamer_section(a: Analysis) -> List[str]:
    from caterva.analyze.rotamers import FLIPPED, KEPT, SPLIT, WELLS, rotamer_verdict
    L = ["", "## Catalytic side-chain rotamers", ""]
    if a.rotamers is None:
        return L + ["Not measured."]
    if not a.rotamers:
        return L + ["No catalytic residue has a chi1 (glycine and alanine have none)."]
    L += ["chi1 (N-CA-CB-gamma) of each catalytic residue, frame by frame, in the well it is nearest: "
          "+60, 180 or -60 degrees. The distances above are between functional-group centres and cannot "
          "see a side chain turn over; this can. Per replica, the fraction of frames in the well the "
          "residue started in.", ""]
    names = [n for n, _ in a.rotamers[0].per_replica]
    L += ["| residue | chi1 at start | " + " | ".join(names) + " | verdict |",
          "|---|---|" + "---|" * len(names) + "---|"]
    for r in a.rotamers:
        v = rotamer_verdict(r)
        if not a.distances_consistent and v != "one replica":
            v = f"({v}, not yet a result)"
        L.append(f"| {r.label} | {r.at_start:.0f} ({r.start_well}) | "
                 + " | ".join(f"{k:.2f}" for k in r.kept) + f" | {v} |")
    L += ["", f"Verdicts (chosen thresholds): kept, in the starting well in at least {KEPT:.0%} of frames in "
          f"every replica; flipped, in at most {FLIPPED:.0%}, named by the well it moved to when the replicas "
          f"agree on one; replicas disagree, when their fractions differ by more than {SPLIT:.0%}. "
          f"The wells are named by angle ({', '.join(WELLS)}) because gauche+ and gauche- are used in both "
          f"senses in the literature."]
    return L


def angle_section(a: Analysis) -> List[str]:
    from caterva.analyze.angles import MOVED_DEG, RESOLVE_DEG
    from caterva.md.convergence import DISCARD
    L = ["", "## Angles between catalytic groups", ""]
    if not a.angles:
        n = sum(1 for s in a.plan.sites if s.functional)
        return L + [f"None measured: of the {n} catalytic groups with their functional atoms, none has two "
                    f"others within {CONTACT_NM:g} nm of it in the crystal (functional-group centres)."]
    L += [f"The angle at one catalytic group (the middle one of each three) between two others, for every "
          f"group with two partners within {CONTACT_NM:g} nm of it in the crystal (the functional-group "
          "centres the distances use), frame by frame, each arm to its nearest periodic image. Per replica, "
          f"the mean over the second half of the run (the first {DISCARD:.0%} is discarded as relaxation, as "
          "for the distances).", "",
          "Each angle is fixed, frame by frame, by three distances in the table above (the sides of its "
          "triangle), so it adds no information about where the groups are: it states that triangle as its "
          "shape at one group, with a verdict of its own. Nor can it tell which side of the group a partner "
          "is on, since a partner that turns about the line through the other two keeps the same angle; "
          "the next section does. An angle that is not yet a result makes the exit code 4, but the sections "
          "below and above are judged by the distances alone.", ""]
    names = [r.name for r in a.angles[0].summary.replicas]
    L += ["| angle (vertex in the middle) | crystal (°) | " + " | ".join(names)
          + " | simulated (°, mean ± SD of replicas) | 95% CI of the mean | change | verdict |",
          "|---|---|" + "---|" * len(names) + "---|---|---|---|"]
    for t in a.angles:
        s = t.summary
        sim = f"{s.mean:.1f}" + (f" ± {s.spread:.1f}" if s.spread is not None else "")
        ci = "n/a" if math.isnan(s.ci95) else f"± {s.ci95:.1f}"
        if s.verdict != "consistent":
            ch = f"({t.change_deg:+.1f}, not yet a result)"
        else:
            ch = f"**{t.change_deg:+.1f}, moved**" if t.moved else f"{t.change_deg:+.1f}, held"
        L.append(f"| {t.label} | {t.crystal_deg:.1f} | " + " | ".join(f"{r.result.mean:.1f}" for r in s.replicas)
                 + f" | {sim} | {ci} | {ch} | {s.verdict} |")
    L.append("")
    L += _sufficiency([(t.label, t.summary) for t in a.angles], RESOLVE_DEG, MOVED_DEG, "°", 1, "angle",
                      explain=False)
    grouped: Dict[str, List[str]] = {}
    for t in a.angles:
        if t.summary.verdict != "consistent" and t.summary.reasons:
            grouped.setdefault(t.summary.reasons[0], []).append(t.label)
    for reason, labels in grouped.items():
        who = "every angle" if len(labels) == len(a.angles) and len(labels) > 1 else ", ".join(labels)
        L.append(f"- {who}: {reason}")
    L += ["", f"`{MOVED_DEG:g}°` is the chosen threshold for calling an angle changed: a group 0.4 nm from the "
              f"vertex that turns that far moves about {MOVED_NM:g} nm, the distance threshold. "
              f"`{CONTACT_NM:g} nm` between centres is as far apart as two groups can be and still have two of "
              "their atoms within a hydrogen bond or salt bridge of each other (0.35 nm), given the 0.10-0.14 "
              "nm from each group's centre to its atoms. It is an upper bound, not a test for a bond: two "
              "groups within it need not be bonded (the native route's hydrogen-bond table says which are)."]
    return L


def face_section(a: Analysis) -> List[str]:
    from caterva.analyze.angles import MOVED_DEG
    from caterva.analyze.faces import FLAT_DEG, FLAT_IN_CRYSTAL, KEPT, SPLIT, face_name, face_verdict
    L = ["", "## Which face of the vertex its partners are on", ""]
    if a.faces is None:
        return L + ["Not measured."]
    if not a.faces:
        if not a.angles:
            return L + ["None measured: there is no angle above to take the faces of."]
        return L + ["None measured: no vertex of an angle above has a Cα in the structure to take its faces "
                    "against."]
    L += ["For each angle above: seen from the vertex's own Cα, does the first partner run clockwise or "
          "anticlockwise to the second about the vertex? That is which face of the vertex each partner is "
          "on. Neither the angle nor the distances can see it: a partner that turns about the line through "
          "the other two keeps them all. It is measured as the elevation of the arm from the vertex's "
          "functional-group centre to its Cα out of the plane of the angle (each arm to its nearest periodic "
          "image), signed as the dihedral first partner-vertex-second partner-Cα, positive clockwise. "
          "Because the Cα is the vertex's own, a side chain that turns over under its partners changes face "
          "too; the rotamer table says whether one did.", "",
          "Out of flat is arcsin(sin(angle) × sin(elevation)): each of the three arms from the vertex (to the "
          "two partners and to its Cα) stands at least that far out of the plane of the other two. A frame is "
          f"on a face only when it is at least {FLAT_DEG:g}°; nearer flat, which face is noise, and the frame "
          "is on neither. Per replica, the fraction of frames on the crystal's face and, in brackets, on the "
          "other face; the rest are flat. Every frame is counted, as for the rotamers and water.", ""]
    names = [n for n, _, _ in a.faces[0].per_replica]
    L += ["| angle (vertex in the middle) | out of flat, crystal (°) | crystal face | " + " | ".join(names)
          + " | verdict |",
          "|---|---|---|" + "---|" * len(names) + "---|"]
    for f in a.faces:
        v = face_verdict(f)
        if not a.distances_consistent and v not in ("one replica", "no frames", FLAT_IN_CRYSTAL):
            v = f"({v}, not yet a result)"
        cells = " | ".join("n/a" if f.crystal_side == 0 or math.isnan(k) else f"{k:.2f} ({o:.2f})"
                           for _, k, o in f.per_replica)
        L.append(f"| {f.label} | {f.crystal_out_of_flat_deg:+.1f} | {face_name(f.crystal_side)} | {cells} | {v} |")
    L += ["", f"Verdicts (chosen thresholds): kept its face, on the crystal's face in at least {KEPT:.0%} of "
              f"frames in every replica; changed face, on the other face in at least {KEPT:.0%}; went flat, "
              f"flat in at least {KEPT:.0%}; replicas disagree, when their fractions on either face differ by "
              f"more than {SPLIT:.0%}; partial, anything else. Flat in the crystal: the crystal's own arms are "
              f"within {FLAT_DEG:g}° of flat, so there is no face to keep. `{FLAT_DEG:g}°` is half the "
              f"{MOVED_DEG:g}° angle threshold: a partner counted on opposite faces in two frames has turned at "
              f"least {MOVED_DEG:g}° through the flat arrangement, which moves a group 0.4 nm from the vertex "
              f"by about {MOVED_NM:g} nm."]
    return L


def water_section(a: Analysis) -> List[str]:
    from caterva.analyze.water import DRY, SPLIT, STAND_IN, WATER_NM, WET, hydration_verdict
    L = ["", "## Water at the catalytic residues", ""]
    if a.water is None:
        return L + ["Not measured."]
    if not a.water:
        return L + ["No catalytic residue to count water at."]
    L += [f"Water oxygens within {WATER_NM:g} nm of any of each catalytic residue's functional atoms (nearest "
          "periodic image). Every frame is counted, as for the hydrogen bonds and rotamers: unlike the "
          "distances and angles, nothing is discarded as relaxation, so these fractions include the start "
          "of each run. Per replica: the mean number of waters, and in brackets the fraction of frames with "
          "at least one. At start: the count in em.gro, the minimised, solvated structure every replica "
          "began from.", ""]
    names = [n for n, _, _ in a.water[0].per_replica]
    L += ["| residue | atoms | at start | " + " | ".join(names) + " | verdict |",
          "|---|---|---|" + "---|" * len(names) + "---|"]
    stand_ins = []
    for h, site in zip(a.water, a.plan.sites):
        atoms = " ".join(site.atoms)
        if not site.functional:
            # Water at a CA is backbone exposure, not the hydration of a
            # catalytic group; the angles leave stand-ins out for the same
            # reason (caterva/analyze/plan.py, contact_angles).
            v, atoms = STAND_IN, f"{atoms} (stand-in)"
            stand_ins.append(h.label)
        else:
            v = hydration_verdict(h)
            if not a.distances_consistent and v not in ("one replica", "no frames"):
                v = f"({v}, not yet a result)"
        L.append(f"| {h.label} | {atoms} | {h.at_start} | "
                 + " | ".join("n/a" if math.isnan(f) else f"{m:.2f} ({f:.2f})" for _, m, f in h.per_replica)
                 + f" | {v} |")
    if stand_ins:
        L += ["", f"{', '.join(stand_ins)}: no functional atoms defined for the residue, or missing from the "
                  "structure, so the count is of water at its Cα. That says how exposed its backbone is, not "
                  "how hydrated a catalytic group is, and it is given no verdict."]
    L += ["", f"Verdicts (chosen thresholds): hydrated, at least one water in at least {WET:.0%} of frames in "
              f"every replica; dry, in at most {DRY:.0%}; intermittent, in between; replicas disagree, when "
              f"their fractions differ by more than {SPLIT:.0%}. `{WATER_NM:g} nm` is the donor-acceptor limit "
              "of `gmx hbond`, so a counted water is close enough to hydrogen-bond to the group; in a lysozyme "
              "run it takes in the first shell of water around carboxylate and hydroxyl oxygens and stops short "
              "of the second (the g(r) is in caterva/analyze/water.py)."]
    return L


def _area_cell(e: "Exposure", area: float, sd: Optional[float] = None, low: Optional[float] = None,
               high: Optional[float] = None) -> str:
    """An area (nm^2) as the solvent-exposure table prints it: with its SD
    and middle-95% range for a replica, and its relative area in
    parentheses when the residue type has a maximum."""
    if math.isnan(area):
        return "n/a"
    text = f"{area:.2f}"
    if low is not None and high is not None:
        text += " ± " + ("n/a" if sd is None or math.isnan(sd) else f"{sd:.2f}") + f" [{low:.2f}, {high:.2f}]"
    rel = e.relative(area)
    return text + (f" ({rel:.0%})" if rel is not None else "")


def sasa_section(a: Analysis) -> List[str]:
    from caterva.analyze.sasa import (BURIED, CHAIN_END, DOTS, EXPOSED, GMX_DOTS, NO_FRAMES, ONE_REPLICA,
                                      PROBE_NM, exposure_verdict)
    L = ["", "## Solvent exposure of the catalytic residues", ""]
    if a.sasa is None:
        return L + [f"Not measured: {a.sasa_not_measured}." if a.sasa_not_measured else "Not measured."]
    if not a.sasa:
        return L + ["No catalytic residue to measure."]
    # The two routes place their points differently; the section names the
    # method that produced these numbers, not the other route's.
    method = (f"`gmx sasa`'s points, the double cubic lattice of Eisenhaber et al. (1995) J. Comput. Chem. "
              f"16:273, -ndots {DOTS}, which it rounds up to {GMX_DOTS:,} per atom"
              if a.sasa_route == "gromacs" else
              f"Shrake & Rupley's method, {DOTS:,} points per atom on a golden-section spiral")
    L += ["How much of each catalytic residue's surface solvent can reach: its solvent-accessible area in "
          f"nm² ({method}; a {PROBE_NM:g} nm probe; Bondi's radii as GROMACS's "
          "vdwradii.dat lists them, hydrogens included). The surface is the whole protein, since a residue's "
          "exposure is set by its neighbours; water and ions are not part of it, and `caterva md` simulates "
          "no ligand. The protein is made whole in each frame and its periodic images are not counted. At "
          "start: em.gro, the minimised, solvated structure every replica began from. Per replica: the mean "
          "± SD over frames, in brackets the range the middle 95% of frames fall in, and in parentheses the "
          "mean as a share of the largest area the residue type can have (relative area). Every frame is "
          "counted, as for the water.", ""]
    names = [r[0] for r in a.sasa[0].per_replica]
    L += ["| residue | largest possible (nm²) | at start | " + " | ".join(names) + " | verdict |",
          "|---|---|---|" + "---|" * len(names) + "---|"]
    for e in a.sasa:
        v = exposure_verdict(e)
        about_the_residue = v not in (ONE_REPLICA, NO_FRAMES, CHAIN_END) and not v.startswith("no maximum")
        if not a.distances_consistent and about_the_residue:
            v = f"({v}, not yet a result)"
        largest = "n/a" if e.max_area is None else f"{e.max_area:.2f}"
        cells = " | ".join(_area_cell(e, mean, sd, low, high) for _, mean, sd, low, high in e.per_replica)
        L.append(f"| {e.label} | {largest} | {_area_cell(e, e.at_start)} | {cells} | {v} |")
    L += ["", f"Verdicts (chosen thresholds): buried, below {BURIED:.0%} of the largest possible area; exposed, "
              f"at {EXPOSED:.0%} or above; partly exposed, in between. The start is judged by its area and each "
              "replica by its mean: \"throughout\" when every replica stays as the residue started, otherwise "
              "which replicas left that state, and \"replicas disagree\" when they did not all leave it the same "
              "way. A replica whose mean crosses a threshold while the middle 95% of its frames still reaches "
              "back into the starting state is named as such (\"buried in rep2 by its mean, with frames still "
              "partly exposed\"), not as having left it, and does not make the replicas disagree: a mean near a "
              "threshold can fall on its other side in another run of the same system. With one replica there "
              "is no verdict, since it is about whether a change happens again in another run. The "
              "largest possible areas are Tien et al. (2013) PLoS ONE 8:e80635, doi:10.1371/journal.pone.0080635, "
              "Table 1 (theoretical, ALLOWED region): DSSP's areas, heavy atoms with DSSP's radii, so the share "
              "is a guide to how exposed a residue is for its size, not a value on their scale "
              "(caterva/analyze/sasa.py says how the two compare on real proteins). They have none for a residue "
              "without a peptide bond on both sides in em.gro (either end of the chain, or beside a break), "
              "which gets no share and no verdict. Shrake & Rupley (1973) J. Mol. Biol. 79:351, "
              "doi:10.1016/0022-2836(73)90011-9."]
    return L


def build_parser(prog: str = "caterva analyze") -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=prog, description=__doc__.splitlines()[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog=("Measures, per replica, against the starting structure:\n"
                                        "  the distance between every pair of catalytic groups; the angles\n"
                                        "  between groups in contact, and which face of each vertex its\n"
                                        "  partners are on; chi1 rotamers; hydrogen bonds (native route only);\n"
                                        "  the water at each catalytic residue, and its solvent-accessible\n"
                                        "  area with the whole protein as the surface (probe 0.14 nm); and the\n"
                                        "  active-site pocket's C-alpha RMSF against the rest of the protein.\n\n"
                                        "Examples:\n"
                                        f"  {prog} ldha-md\n  {prog} ldha-md --script-only\n"
                                        "\nExit codes: 0 every distance and angle consistent, 4 at least one\n"
                                        "not a result, 2 malformed question, 3 refused and said why, 1 a crash.\n"
                                        "The verdicts on hydrogen bonds, rotamers, faces, water and solvent\n"
                                        "exposure do not set the exit code."))
    p.add_argument("directory", help="a finished `caterva md` setup")
    p.add_argument("--script-only", action="store_true",
                   help="write analyze.sh and stop; run it, then rerun without this flag")
    p.add_argument("--no-run", action="store_true",
                   help="use the .xvg files analyze.sh already wrote; do not call GROMACS (a run whose "
                        "analyze.sh predates the angle, face, water and solvent-exposure tables is refused "
                        "by name: run it again)")
    p.add_argument("--gromacs", action="store_true",
                   help="measure with gmx distance, rmsf, angle, gangle, select and sasa (analyze.sh) "
                        "instead of Caterva's own reader")
    return p


def main(argv: Optional[Sequence[str]] = None, prog: str = "caterva analyze",
         catalytic=catalytic_residues) -> int:
    args = build_parser(prog).parse_args(argv)
    d = Path(args.directory)
    try:
        pdb, chain = setup_info(d)
        protein = d / "protein.pdb"
        if not protein.exists():
            raise AnalyzeError(f"{protein} does not exist: run {d}/run.sh first")
        residues, source = catalytic(pdb, chain)
        if not residues:
            raise AnalyzeError(f"no catalytic residues of {pdb} could be placed in the simulated chain")
        p = plan(read_pdb(protein.read_text(), chain), residues)
        reps = replicas(d)
        chi1 = chi1_groups(d, p)
        no_sasa = sasa_unmeasurable(d, p)
        if chi1:
            write_chi1_index(d, chi1)
        (d / "analyze.sh").write_text(script(p, [r.name for r in reps] or ["rep1"], chi1))
        if args.script_only:
            print(f"Wrote {d}/analyze.sh ({len(p.pairs)} catalytic distances, {len(p.angles)} angles, "
                  f"the faces of {len(p.faces)}, water and solvent-accessible area at {len(p.sites)} residues, "
                  f"pocket of {len(p.pocket)} residues).")
            return 0
        if not reps:
            raise AnalyzeError(f"no finished replicas (rep*/md.xtc) under {d}: run {d}/run.sh first")
        if args.gromacs or args.no_run:
            if not args.no_run:
                gmx = os.environ.get("GMX", "gmx")
                if shutil.which(gmx) is None and not Path(gmx).exists():
                    raise AnalyzeError(f"GROMACS not found ({gmx!r}): set GMX=/path/to/gmx, or run analyze.sh "
                                       "elsewhere and rerun with --no-run")
                run_gromacs(d, p, reps, gmx, chi1)
            distances, flex, rotamers = measure(d, p, reps, chi1)
            angles, water = gromacs_angles(p, reps), gromacs_water(d, p, reps)
            faces, exposure = gromacs_faces(p, reps), (gromacs_sasa(d, p, reps) if no_sasa is None else None)
            hbonds = None
        else:
            distances, flex, hbonds, rotamers, angles, water, faces, exposure = measure_native(
                d, p, reps, sasa=no_sasa is None)
    except AnalyzeError as e:
        print(f"caterva analyze: {e}", file=sys.stderr)
        return 3
    a = Analysis(pdb, chain, source, p, distances, flex, hbonds, rotamers, angles, water, faces, exposure,
                 sasa_route="gromacs" if args.gromacs or args.no_run else "native", sasa_not_measured=no_sasa)
    text = "\n".join(report(a)) + "\n"
    print(text, end="")
    (d / "ANALYSIS.md").write_text(text, encoding="utf-8")
    return 0 if a.all_consistent else EXIT_NOT_A_RESULT


def console_main() -> int:
    return main()


if __name__ == "__main__":
    sys.exit(main())
