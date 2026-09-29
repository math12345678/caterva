"""Write an absolute binding free-energy calculation whose target is a cited Ki.

The calculation runs at the temperature the Ki was measured at, is scored
against the band `caterva bind` builds from the same rows, and records in
PROVENANCE.md where every setting came from, as `caterva md` does. It does
not parameterise the ligand: the topology is yours (ACPYPE/GAFF, CGenFF,
OpenFF), because an invented one would make the computed ΔG a statement
about the invention.
"""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from caterva.bind.core import Target
from caterva.fep.core import (
    K_ANGLE, K_DISTANCE, Restraint, choose_restraint, ligand_atoms, read_gro,
    restraint_cost_kj, schedule,
)
from caterva.md.setup import Parameter
from caterva.methods import METHODS

KJ_PER_KCAL = 4.184


def moleculetype_name(itp: Path) -> str:
    text = Path(itp).read_text()
    m = re.search(r"\[\s*moleculetype\s*\][^\n]*\n(?:\s*;[^\n]*\n)*\s*(\S+)", text)
    if not m:
        raise ValueError(f"{itp}: no [ moleculetype ] entry")
    return m.group(1)


def _includes(top: Path) -> List[str]:
    return re.findall(r'^\s*#include\s+"([^"]+)"', top.read_text(), re.M)


@dataclass
class Temperature:
    kelvin: float
    origin: str   # measured | chosen
    source: str


def temperature_for(target: Target, override_c: Optional[float] = None) -> Temperature:
    """The Ki's assay temperature when its rows agree on one; otherwise a
    labelled choice, never an average of temperatures nobody measured at."""
    if override_c is not None:
        return Temperature(override_c + 273.15, "chosen", f"--temperature {override_c:g} C")
    temps = sorted({m.temperature_c for m in target.used if m.temperature_c is not None})
    refs = ", ".join(f"BRENDA ref {r}" for r in target.references)
    if len(temps) == 1 and all(m.temperature_c is not None for m in target.used):
        return Temperature(temps[0] + 273.15, "measured", f"assay temperature of the Ki ({refs})")
    if not temps:
        return Temperature(298.15, "chosen",
                           f"25 C: the Ki rows ({refs}) state no assay temperature; the target band "
                           f"already spans 4-37 C for that reason")
    return Temperature(298.15, "chosen",
                       f"25 C: the Ki rows were measured at {', '.join(f'{t:g}' for t in temps)} C "
                       f"(or unstated); pass --temperature to run at one of them")


@dataclass
class FepSetup:
    target: Target
    complex_gro: Path
    topology: Path
    ligand_resname: str
    ligand_itp: Path
    temperature: Temperature
    ph: Optional[float] = None
    replicas: int = 3
    ns: float = 5.0
    seed: int = 20260928
    ionic_strength_m: float = 0.15
    force_field: str = "amber99sb-ildn"
    water: str = "tip3p"
    restraint: Optional[Restraint] = None
    moleculetype: str = ""
    parameters: List[Parameter] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not 1 <= self.replicas <= 100:
            raise ValueError("replicas must be 1 to 100 (per-window seeds are spaced by replica)")
        atoms = read_gro(self.complex_gro)
        ligand_atoms(atoms, self.ligand_resname)  # raises with what IS there
        self.restraint = choose_restraint(atoms, self.ligand_resname)
        self.moleculetype = moleculetype_name(self.ligand_itp)
        if "intermolecular_interactions" in self.topology.read_text():
            raise ValueError(f"{self.topology} already has [ intermolecular_interactions ]; "
                             "remove them so the restraints written here are the only ones")
        m, t, r = METHODS, self.temperature, self.restraint
        self.parameters = [
            Parameter("temperature", f"{t.kelvin:.2f} K", t.origin, t.source),
            Parameter("target", self._band(), "measured",
                      "caterva bind on the same rows: ΔG = RT ln(Ki / 1 M) at each row's temperature"),
            Parameter("pH (protonation)", f"{self.ph:g}" if self.ph is not None else "as in your topology",
                      "measured" if self.ph is not None else "chosen",
                      ("the Ki's assay pH; protein AND ligand protonation in your topology must match it "
                       f"({m['propka'].cite()} for the protein)") if self.ph is not None
                      else "no assay pH stated; the protonation states in your topology are an assumption"),
            Parameter("method", "absolute binding free energy by double decoupling", "method",
                      m["double-decoupling"].cite()),
            Parameter("orientational restraints", "Boresch: 1 distance, 2 angles, 3 dihedrals",
                      "method", m["boresch"].cite()),
            Parameter("restraint atoms", f"P1-P2-P3 {', '.join(_short(a) for a in r.protein)}; "
                                         f"L1-L2-L3 {', '.join(_short(a) for a in r.ligand)}",
                      "chosen", f"picked so no angle nears 0 or 180 degrees (smallest sine {r.quality:.2f}); "
                                "reference values measured on your complex"),
            Parameter("restraint force constants", f"{K_DISTANCE:g} kJ/mol/nm^2, {K_ANGLE:g} kJ/mol/rad^2",
                      "chosen", "10 kcal/mol/A^2 and 10 kcal/mol/rad^2, the values in common use"),
            Parameter("restraint correction", f"+{self.restraint_kj():.2f} kJ/mol "
                                              f"(+{self.restraint_kj() / KJ_PER_KCAL:.2f} kcal/mol) at 1 M",
                      "method", "analytic, eq. 32 of " + m["boresch"].cite()),
            Parameter("lambda windows", f"complex {len(schedule('complex'))} "
                                        f"(10 restraint, 4 charge, 20 van der Waals); solvent "
                                        f"{len(schedule('solvent'))}",
                      "chosen", "charges off before van der Waals; finest where soft-core curvature is"),
            Parameter("soft-core", "alpha 0.5, power 1, sigma 0.3 nm", "method", m["soft-core"].cite()),
            Parameter("estimator", "BAR over neighbouring windows, per replica", "method", m["bar"].cite()),
            Parameter("integrator", "stochastic dynamics, tau-t 1 ps, 2 fs", "method", m["sd"].cite()),
            Parameter("barostat", "C-rescale, tau 2 ps (NPT and production)", "method", m["c-rescale"].cite()),
            Parameter("electrostatics", "PME, 1.0 nm", "method", m["pme"].cite()),
            Parameter("van der Waals", "1.0 nm cut-off, dispersion correction to energy and pressure", "chosen",
                      "the cut-off the force field was parameterised with"),
            Parameter("constraints", "h-bonds, LINCS", "method", m["lincs"].cite()),
            Parameter("per-window sampling", f"EM, 100 ps NVT, 100 ps NPT, {self.ns:g} ns production", "chosen",
                      "override with --ns"),
            Parameter("replicas", str(self.replicas), "chosen",
                      "independent repeats of both legs; ΔG is reported as mean ± SEM across them"
                      if self.replicas > 1 else
                      "ONE SAMPLE: BAR's error is only the statistical error within one run, not "
                      "the spread between runs; use --replicas 3 for a result"),
            Parameter("seeds", ", ".join(f"rep{i + 1}: {s}" for i, s in enumerate(self.seeds())),
                      "chosen", "fixed so each run can be reproduced; each window and stage adds "
                                "1000 x lambda-index + 100 x stage, so no two share a noise sequence"),
            Parameter("solvent leg", f"ligand in a 1.2 nm dodecahedron of {self.water}, "
                                     f"{self.ionic_strength_m:g} M NaCl, neutralised", "chosen",
                      "the complex's own ionic strength is whatever your system has"),
            Parameter("ligand topology", f"{self.ligand_itp.name} (moleculetype {self.moleculetype})",
                      "chosen", "YOURS: supplied, not generated; its charges and types decide the answer"),
            Parameter("engine", "GROMACS", "method", m["gromacs"].cite()),
        ]

    def seeds(self) -> List[int]:
        return [self.seed + r for r in range(self.replicas)]

    def restraint_kj(self) -> float:
        return restraint_cost_kj(self.restraint, self.temperature.kelvin)

    def _band(self) -> str:
        return (f"{self.target.lo:.2f} to {self.target.hi:.2f} kcal/mol "
                f"({self.target.compound}, {', '.join('BRENDA ref ' + r for r in self.target.references)})")

    # -- files ------------------------------------------------------------

    def _mdp(self, stage: str, leg: str) -> str:
        t = f"{self.temperature.kelvin:.2f}"
        head = (f"; Caterva FEP, {leg} leg, {stage}. Every value: see PROVENANCE.md\n"
                "; __LAMBDA__ and __SEED__ are filled in by run.sh\n")
        common = (
            "cutoff-scheme           = Verlet\nnstlist                 = 10\npbc                     = xyz\n"
            "coulombtype             = PME\nrcoulomb                = 1.0\nrvdw                    = 1.0\n"
            "DispCorr                = EnerPres\nfourierspacing          = 0.16\n"
        )
        fe = (
            "free-energy             = yes\n"
            f"couple-moltype          = {self.moleculetype}\n"
            "couple-lambda0          = vdw-q\ncouple-lambda1          = none\ncouple-intramol         = no\n"
            "init-lambda-state       = __LAMBDA__\n"
            + schedule(leg).mdp()
            + "sc-alpha                = 0.5\nsc-power                = 1\nsc-sigma                = 0.3\n"
            "sc-r-power              = 6\nnstdhdl                 = 100\ncalc-lambda-neighbors   = -1\n"
            "separate-dhdl-file      = yes\n"
        )
        if stage == "em":
            return head + "integrator              = steep\nemtol                   = 1000\nnsteps                  = 5000\n" + common + fe
        steps = {"nvt": 50_000, "npt": 50_000, "prod": int(round(self.ns * 500_000))}[stage]
        text = (head + "integrator              = sd\ndt                      = 0.002\n"
                f"nsteps                  = {steps}\n"
                "constraints             = h-bonds\nconstraint-algorithm    = lincs\n"
                "tc-grps                 = System\ntau-t                   = 1.0\n"
                f"ref-t                   = {t}\nld-seed                 = __SEED__\n"
                "nstxout-compressed      = 5000\nnstenergy               = 1000\nnstlog                  = 5000\n"
                + common + fe)
        if stage == "nvt":
            text += f"pcoupl                  = no\ngen-vel                 = yes\ngen-temp                = {t}\ngen-seed                = __SEED__\n"
        else:
            text += ("pcoupl                  = C-rescale\npcoupltype              = isotropic\ntau-p                   = 2.0\n"
                     "ref-p                   = 1.0\ncompressibility         = 4.5e-5\ngen-vel                 = no\n"
                     "continuation            = yes\n")
        return text

    def _solvent_top(self) -> str:
        ff = f"{self.force_field}.ff"
        keep = [f'#include "{ff}/forcefield.itp"']
        for inc in _includes(self.topology):
            p = (self.topology.parent / inc)
            if inc.startswith(ff) or not p.is_file() or p.resolve() == self.ligand_itp.resolve():
                continue
            if re.search(r"\[\s*atomtypes\s*\]", p.read_text()) and "moleculetype" not in p.read_text():
                keep.append(f'#include "{p.name}"')
        keep += [f'#include "{self.ligand_itp.name}"', f'#include "{ff}/{self.water}.itp"', f'#include "{ff}/ions.itp"']
        return ("; Caterva FEP solvent leg: the ligand alone in water. See PROVENANCE.md\n"
                + "\n".join(keep) + f"\n\n[ system ]\n{self.moleculetype} in water\n\n[ molecules ]\n{self.moleculetype} 1\n")

    def _ligand_gro(self) -> str:
        atoms = ligand_atoms(read_gro(self.complex_gro), self.ligand_resname)
        lines = [f"{self.ligand_resname} from {self.complex_gro.name}", f"{len(atoms):5d}"]
        for i, a in enumerate(atoms, start=1):
            x, y, z = a.xyz
            lines.append(f"{1:5d}{a.resname:<5}{a.name:>5}{i:5d}{x:8.3f}{y:8.3f}{z:8.3f}")
        lines.append("   5.00000   5.00000   5.00000")
        return "\n".join(lines) + "\n"

    def record(self) -> Dict:
        r = self.restraint
        return {
            "target": {"compound": self.target.compound, "organism": self.target.organism,
                       "state": self.target.state, "band_kcal": [self.target.lo, self.target.hi],
                       "references": self.target.references, "caveats": self.target.caveats},
            "temperature_k": self.temperature.kelvin, "temperature_origin": self.temperature.origin,
            "replicas": self.replicas, "seeds": self.seeds(), "ns_per_window": self.ns,
            "windows": {"complex": len(schedule("complex")), "solvent": len(schedule("solvent"))},
            "ligand": {"resname": self.ligand_resname, "moleculetype": self.moleculetype,
                       "itp": self.ligand_itp.name},
            "restraint": {"protein": [a.index for a in r.protein], "ligand": [a.index for a in r.ligand],
                          "r_nm": r.r, "theta_a": r.theta_a, "theta_b": r.theta_b,
                          "correction_kj": self.restraint_kj(), "quality": r.quality},
        }

    def write(self, out: Path) -> List[str]:
        out = Path(out)
        written = []

        def put(rel: str, text: str) -> None:
            p = out / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
            written.append(rel)

        # The complex leg: your system, your topology and its local includes,
        # plus the restraint block.
        (out / "complex").mkdir(parents=True, exist_ok=True)
        for inc in _includes(self.topology):
            src = self.topology.parent / inc
            if src.is_file():
                dst = out / "complex" / inc
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
                written.append(f"complex/{inc}")
        for posre in self.topology.parent.glob("posre*.itp"):
            shutil.copyfile(posre, out / "complex" / posre.name)
        shutil.copyfile(self.complex_gro, out / "complex" / "start.gro")
        written.append("complex/start.gro")
        put("complex/topol.top", self.topology.read_text().rstrip("\n") + "\n" + self.restraint.gromacs())

        # The solvent leg: the same ligand, its coordinates from the complex.
        (out / "solvent").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.ligand_itp, out / "solvent" / self.ligand_itp.name)
        written.append(f"solvent/{self.ligand_itp.name}")
        for inc in _includes(self.topology):
            src = self.topology.parent / inc
            if src.is_file() and f'#include "{src.name}"' in self._solvent_top() and src.name != self.ligand_itp.name:
                shutil.copyfile(src, out / "solvent" / src.name)
        # The pristine topology: `gmx solvate` and `genion` edit topol.top in
        # place, so a solvent build that was interrupted and re-run counted
        # its water twice (found re-running the solvent leg). run.sh always
        # starts from this copy.
        put("solvent/topol.base.top", self._solvent_top())
        put("solvent/ligand.gro", self._ligand_gro())
        put("solvent/ions.mdp", "; places ions only; nothing is simulated with it\nintegrator = steep\nnsteps = 0\n"
            "cutoff-scheme = Verlet\ncoulombtype = cutoff\nrcoulomb = 1.0\nrvdw = 1.0\n")
        for leg in ("complex", "solvent"):
            for stage in ("em", "nvt", "npt", "prod"):
                put(f"{leg}/{stage}.mdp", self._mdp(stage, leg))
        put("run.sh", self._script())
        put("caterva-fep.json", json.dumps(self.record(), indent=2) + "\n")
        put("PROVENANCE.md", self.provenance())
        return written

    def _script(self) -> str:
        nc, ns = len(schedule("complex")), len(schedule("solvent"))
        return f"""#!/usr/bin/env bash
# Caterva absolute binding free energy: {self.target.compound} -> {self.target.organism}.
# Read PROVENANCE.md first. Needs GROMACS (gmx). Stops at the first error.
# Every window of every replica is independent: to spread them over a
# cluster, run one `leg rep lambda` triple per job with ONLY=leg:rep:lambda.
set -euo pipefail
GMX="${{GMX:-gmx}}"
MDRUN_FLAGS="${{MDRUN_FLAGS:--ntmpi 1}}"
cd "$(dirname "$0")"

# Solvent leg system: the ligand, in the pose it has in the complex, in water.
if [ ! -f solvent/start.gro ]; then
  ( cd solvent
    cp topol.base.top topol.top
    "$GMX" editconf -f ligand.gro -o boxed.gro -c -d 1.2 -bt dodecahedron
    "$GMX" solvate -cp boxed.gro -cs spc216.gro -o solvated.gro -p topol.top
    "$GMX" grompp -f ions.mdp -c solvated.gro -p topol.top -o ions.tpr -maxwarn 1
    echo SOL | "$GMX" genion -s ions.tpr -o start.gro -p topol.top -pname NA -nname CL -neutral -conc {self.ionic_strength_m:g} -seed {self.seed} )
fi

window() {{  # leg replica lambda seed
  local leg=$1 rep=$2 lam=$3 seed=$4 d="$1/rep$2/lambda$3"
  [ -f "$d/prod.xvg" ] && return 0
  mkdir -p "$d"
  # A distinct, reproducible stochastic-dynamics seed per window and stage:
  # SD draws its random forces from ld-seed, and one seed reused across
  # windows or continuations repeats the same noise, correlating windows
  # that BAR treats as independent. (GROMACS's grompp says so, found on the
  # first run of this script.)
  local i=0
  for s in em nvt npt prod; do
    sed -e "s/__LAMBDA__/$lam/" -e "s/__SEED__/$((seed + 1000 * lam + 100 * i))/" "$leg/$s.mdp" > "$d/$s.mdp"
    i=$((i + 1))
  done
  "$GMX" grompp -f "$d/em.mdp" -c "$leg/start.gro" -p "$leg/topol.top" -o "$d/em.tpr" -po "$d/em.out.mdp" -maxwarn 1
  "$GMX" mdrun -deffnm "$d/em" $MDRUN_FLAGS
  "$GMX" grompp -f "$d/nvt.mdp" -c "$d/em.gro" -p "$leg/topol.top" -o "$d/nvt.tpr" -po "$d/nvt.out.mdp" -maxwarn 1
  "$GMX" mdrun -deffnm "$d/nvt" $MDRUN_FLAGS
  "$GMX" grompp -f "$d/npt.mdp" -c "$d/nvt.gro" -t "$d/nvt.cpt" -p "$leg/topol.top" -o "$d/npt.tpr" -po "$d/npt.out.mdp" -maxwarn 1
  "$GMX" mdrun -deffnm "$d/npt" $MDRUN_FLAGS
  "$GMX" grompp -f "$d/prod.mdp" -c "$d/npt.gro" -t "$d/npt.cpt" -p "$leg/topol.top" -o "$d/prod.tpr" -po "$d/prod.out.mdp" -maxwarn 1
  "$GMX" mdrun -deffnm "$d/prod" -dhdl "$d/prod.xvg" $MDRUN_FLAGS
}}

SEEDS=({' '.join(map(str, self.seeds()))})
if [ -n "${{ONLY:-}}" ]; then
  IFS=: read -r leg rep lam <<< "$ONLY"; window "$leg" "$rep" "$lam" "${{SEEDS[$((rep-1))]}}"; exit 0
fi
for rep in $(seq 1 {self.replicas}); do
  for lam in $(seq 0 {nc - 1}); do window complex "$rep" "$lam" "${{SEEDS[$((rep-1))]}}"; done
  for lam in $(seq 0 {ns - 1}); do window solvent "$rep" "$lam" "${{SEEDS[$((rep-1))]}}"; done
done

# BAR per leg per replica; `caterva fep --summarise .` reads these. Each
# window's 200 ps of NVT+NPT is its equilibration, so all of production is
# used. (Not `bar -b`: it takes absolute time, and production starts at 200 ps.)
for leg in complex solvent; do
  for rep in $(seq 1 {self.replicas}); do
    "$GMX" bar -f "$leg"/rep$rep/lambda*/prod.xvg -o "$leg/rep$rep/bar.xvg" > "$leg/rep$rep/bar.log" 2>&1
  done
done
echo "done: caterva fep --summarise $(pwd)"
"""

    def provenance(self) -> str:
        rows = "\n".join(f"| {p.name} | {p.value} | {p.origin} | {p.source} |" for p in self.parameters)
        caveats = "\n".join(f"- {c}" for c in self.target.caveats) or "- none recorded"
        return f"""# Provenance: absolute binding free energy of {self.target.compound}

The number this calculation is held to is the measured band
**{self._band()}**, for the {self.target.state} state, built by
`caterva bind` from the Ki rows named there. Every setting is below with its
origin: **measured** (from those rows or your structure), **chosen** (a
labelled default), or **method** (a published method, cited).

| parameter | value | origin | source |
|---|---|---|---|
{rows}

## The cycle

    ΔG°bind = ΔG_solvent + ΔG_restraints_on - ΔG_complex

each ΔG a decoupling (charges, then van der Waals, switched off), the
complex leg first switching the Boresch restraints on. `caterva fep
--summarise .` combines the legs per replica and judges the result against
the band at 2σ.

## Caveats carried from the measurement

{caveats}

## What this does not do

- **Parameterise the ligand.** {self.ligand_itp.name} is yours. The answer is
  as good as its charges and atom types, and no better.
- **Equilibrate your complex.** start.gro is the structure you supplied; the
  restraint reference values were measured on it. Give it an equilibrated,
  solvated, neutralised complex.
- **Check the restraint anchors move little.** They are C-alpha atoms near
  the pocket; `caterva analyze` reports the pocket's flexibility, and an
  anchor on a loop that moves will slow convergence.
- **Sample slow rearrangements.** A ligand with several binding poses, or a
  pocket that opens on microseconds, needs more than {self.ns:g} ns a window.
"""


def _short(a) -> str:
    return f"{a.resname}{a.resnr}:{a.name}"


__all__ = ["FepSetup", "Temperature", "temperature_for", "moleculetype_name"]
