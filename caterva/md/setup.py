"""A GROMACS setup in which every number says where it came from.

WHY THIS EXISTS
---------------
An MD input is a few dozen numbers -- temperature, ionic strength, force
field, water model, thermostat, cut-offs, time step -- and in most
simulations nobody can say afterwards why any of them has the value it has.
Caterva's kinetics already know the conditions an enzyme's constants were
MEASURED under. A simulation meant to explain those constants should run at
those conditions, and say so; where it does not, it should say that too.

So each parameter here carries one of three origins:

    measured   taken from the assay behind a cited kinetic constant
    chosen     a default, labelled as one, overridable on the command line
    method     a published algorithm or model, with its verified DOI

WHAT IT DOES NOT DO
-------------------
It writes inputs and a script; GROMACS runs them. It does not parameterise
ligands: pdb2gmx has no topology for oxamate or NADH, and inventing one
would be the MD version of an invented rate constant. Bound small molecules
are stripped and LISTED, with the tools that can parameterise them. It does
not set protonation states from a pH either: GROMACS assigns standard
states, and the assay pH is recorded beside a pointer to PROPKA rather than
silently assumed to be 7.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from caterva.methods import METHODS

ORIGINS = ("measured", "chosen", "method")


@dataclass(frozen=True)
class Parameter:
    name: str
    value: str
    origin: str
    source: str

    def __post_init__(self) -> None:
        if self.origin not in ORIGINS:
            raise ValueError(f"origin must be one of {ORIGINS}, not {self.origin!r}")


@dataclass
class Conditions:
    """Temperature and pH, and where each came from."""
    temperature_k: float = 298.15
    temperature_source: str = "chosen: 25 C, no measured value supplied"
    ph: Optional[float] = None
    ph_source: str = "not stated; GROMACS assigns standard protonation states"
    measured_temperature: bool = False


@dataclass
class MdSetup:
    pdb_id: str
    chain: Optional[str]
    conditions: Conditions
    ns: float = 10.0
    ionic_strength_m: float = 0.15
    seed: int = 20260927
    force_field: str = "amber99sb-ildn"
    water: str = "tip3p"
    parameters: List[Parameter] = field(default_factory=list)

    def __post_init__(self) -> None:
        c = self.conditions
        m = METHODS
        self.parameters = [
            Parameter("temperature", f"{c.temperature_k:.2f} K",
                      "measured" if c.measured_temperature else "chosen", c.temperature_source),
            Parameter("pH (protonation)", f"{c.ph:g}" if c.ph is not None else "standard states",
                      "measured" if c.ph is not None else "chosen",
                      c.ph_source + (f"; assign states at this pH with {m['propka'].cite()}"
                                     if c.ph is not None else "")),
            Parameter("ionic strength", f"{self.ionic_strength_m:g} M NaCl, net charge neutralised",
                      "chosen", "physiological default; override with --ionic-strength"),
            Parameter("pressure", "1.0 bar", "chosen", "ambient"),
            Parameter("production length", f"{self.ns:g} ns", "chosen", "override with --ns"),
            Parameter("velocity seed", str(self.seed), "chosen",
                      "fixed so a run can be reproduced (also seeds ion placement); change it for independent replicas"),
            Parameter("force field", self.force_field, "method", m["amber99sb-ildn"].cite()),
            Parameter("water model", self.water, "method", m["tip3p"].cite()),
            Parameter("thermostat", "V-rescale, tau 0.1 ps", "method", m["v-rescale"].cite()),
            Parameter("barostat (equilibration)", "C-rescale, tau 2 ps", "method", m["c-rescale"].cite()),
            Parameter("barostat (production)", "Parrinello-Rahman, tau 2 ps", "method",
                      m["parrinello-rahman"].cite()),
            Parameter("electrostatics", "PME, 1.0 nm real-space cut-off", "method",
                      m["pme"].cite() + " (ions.mdp, which only places ions and simulates "
                      "nothing, uses a plain cut-off: the system is still charged then)"),
            Parameter("PME grid", "0.16 nm spacing, 4th-order interpolation", "chosen",
                      "GROMACS's defaults for PME accuracy"),
            Parameter("van der Waals", "1.0 nm cut-off, dispersion correction to energy and pressure",
                      "chosen", "the cut-off the force field was parameterised with"),
            Parameter("neighbour list", "Verlet buffer, updated every 10 steps", "chosen",
                      "GROMACS default; the buffer is sized automatically"),
            Parameter("compressibility", "4.5e-5 1/bar", "chosen", "isothermal compressibility of water near 300 K"),
            Parameter("minimisation", "steepest descent to max force < 1000 kJ/mol/nm, at most 50000 steps",
                      "chosen", "standard pre-equilibration target"),
            Parameter("equilibration", "NVT 100 ps then NPT 100 ps, protein heavy atoms restrained",
                      "chosen", "restraints released for production"),
            Parameter("output", "coordinates every 10 ps; energies and log every 2 ps", "chosen",
                      "enough to analyse, small enough to keep"),
            Parameter("constraints", "h-bonds, LINCS; 2 fs time step", "method", m["lincs"].cite()),
            Parameter("engine", "GROMACS", "method", m["gromacs"].cite()),
            Parameter("structure", f"PDB {self.pdb_id}" + (f", chain {self.chain}" if self.chain else ""),
                      "measured", f"{m['pdb'].cite()}; entry doi:10.2210/pdb{self.pdb_id.lower()}/pdb"),
        ]

    # -- the files -----------------------------------------------------

    def _common(self) -> str:
        return (
            "cutoff-scheme   = Verlet\n"
            "nstlist         = 10\n"
            "pbc             = xyz\n"
            "coulombtype     = PME\n"
            "rcoulomb        = 1.0\n"
            "rvdw            = 1.0\n"
            "DispCorr        = EnerPres\n"
        )

    def _dynamics(self, *, nsteps: int, posres: bool, continuation: bool,
                  barostat: Optional[str]) -> str:
        t = f"{self.conditions.temperature_k:.2f}"
        text = (
            ("define          = -DPOSRES\n" if posres else "")
            + "integrator      = md\n"
            f"nsteps          = {nsteps}\n"
            "dt              = 0.002\n"
            "nstxout-compressed = 5000\n"
            "nstenergy       = 1000\n"
            "nstlog          = 1000\n"
            f"continuation    = {'yes' if continuation else 'no'}\n"
            "constraint_algorithm = lincs\n"
            "constraints     = h-bonds\n"
            "lincs_iter      = 1\n"
            "lincs_order     = 4\n"
            + self._common()
            + "fourierspacing  = 0.16\n"
            "pme_order       = 4\n"
            "tcoupl          = V-rescale\n"
            "tc-grps         = Protein Non-Protein\n"
            "tau_t           = 0.1 0.1\n"
            f"ref_t           = {t} {t}\n"
        )
        if barostat:
            text += (
                f"pcoupl          = {barostat}\n"
                "pcoupltype      = isotropic\n"
                "tau_p           = 2.0\n"
                "ref_p           = 1.0\n"
                "compressibility = 4.5e-5\n"
                + ("refcoord_scaling = com\n" if posres else "")
            )
        else:
            text += "pcoupl          = no\n"
        if continuation:
            text += "gen_vel         = no\n"
        else:
            text += f"gen_vel         = yes\ngen_temp        = {t}\ngen_seed        = {self.seed}\n"
        return text

    def files(self) -> Dict[str, str]:
        header = f"; Caterva MD setup for PDB {self.pdb_id}. Every value: see PROVENANCE.md\n"
        min_mdp = (header + "integrator      = steep\nemtol           = 1000.0\n"
                   "emstep          = 0.01\nnsteps          = 50000\n" + self._common())
        steps = int(round(self.ns * 1_000_000 / 2))  # 2 fs
        # ions.mdp only builds the .tpr genion reads; nothing is simulated
        # with it. It uses plain cut-off electrostatics because the system is
        # still charged at that point, and grompp rightly refuses PME on a
        # charged system (found running this setup with GROMACS 2021).
        ions_mdp = (header + "integrator      = steep\nemtol           = 1000.0\n"
                    "emstep          = 0.01\nnsteps          = 50000\n"
                    + self._common().replace("coulombtype     = PME", "coulombtype     = cutoff"))
        return {
            "ions.mdp": ions_mdp,
            "em.mdp": min_mdp,
            "nvt.mdp": header + self._dynamics(nsteps=50_000, posres=True, continuation=False, barostat=None),
            "npt.mdp": header + self._dynamics(nsteps=50_000, posres=True, continuation=True, barostat="C-rescale"),
            "md.mdp": header + self._dynamics(nsteps=steps, posres=False, continuation=True,
                                              barostat="Parrinello-Rahman"),
            "run.sh": self._script(),
            "PROVENANCE.md": self.provenance(),
        }

    def _script(self) -> str:
        pdb = self.pdb_id.upper()
        chain = self.chain or ""
        return f"""#!/usr/bin/env bash
# Caterva MD setup: PDB {pdb}{', chain ' + chain if chain else ''}. Read PROVENANCE.md first.
# Needs GROMACS (gmx) on PATH, and curl. Stops at the first error.
set -euo pipefail
GMX="${{GMX:-gmx}}"
# One thread-MPI rank with OpenMP threads runs on any machine; GROMACS's own
# rank choice failed on a 14-core Mac (14 = 2 x 7 cannot be decomposed).
# On a cluster or GPU node, set MDRUN_FLAGS to what that machine wants.
MDRUN_FLAGS="${{MDRUN_FLAGS:--ntmpi 1}}"
cd "$(dirname "$0")"

# The PDB wwPDB copy of the entry.
[ -f {pdb}.pdb ] || curl -fsSL -o {pdb}.pdb https://files.rcsb.org/download/{pdb}.pdb

# Protein only{', chain ' + chain if chain else ''}. pdb2gmx has no topology for small molecules, so
# they are removed here and listed, not guessed.
awk -v chain="{chain}" '
  /^(ATOM|TER)/ && (chain == "" || substr($0,22,1) == chain) {{ print; next }}
  /^HETATM/ && (chain == "" || substr($0,22,1) == chain) {{ het[substr($0,18,3)]++ }}
  END {{
    for (h in het) if (h != "HOH") printf "stripped: %s (%d atoms)\\n", h, het[h] > "/dev/stderr"
    print "END"
  }}' {pdb}.pdb > protein.pdb

"$GMX" pdb2gmx -f protein.pdb -o processed.gro -p topol.top -ff {self.force_field} -water {self.water} -ignh
"$GMX" editconf -f processed.gro -o boxed.gro -c -d 1.0 -bt dodecahedron
"$GMX" solvate -cp boxed.gro -cs spc216.gro -o solvated.gro -p topol.top
"$GMX" grompp -f ions.mdp -c solvated.gro -p topol.top -o ions.tpr -maxwarn 0
echo SOL | "$GMX" genion -s ions.tpr -o ionized.gro -p topol.top -pname NA -nname CL -neutral -conc {self.ionic_strength_m:g} -seed {self.seed}

"$GMX" grompp -f em.mdp -c ionized.gro -p topol.top -o em.tpr
"$GMX" mdrun -deffnm em $MDRUN_FLAGS
"$GMX" grompp -f nvt.mdp -c em.gro -r em.gro -p topol.top -o nvt.tpr
"$GMX" mdrun -deffnm nvt $MDRUN_FLAGS
"$GMX" grompp -f npt.mdp -c nvt.gro -r nvt.gro -t nvt.cpt -p topol.top -o npt.tpr
"$GMX" mdrun -deffnm npt $MDRUN_FLAGS
"$GMX" grompp -f md.mdp -c npt.gro -t npt.cpt -p topol.top -o md.tpr
"$GMX" mdrun -deffnm md $MDRUN_FLAGS
"""

    def provenance(self) -> str:
        rows = "\n".join(f"| {p.name} | {p.value} | {p.origin} | {p.source} |" for p in self.parameters)
        c = self.conditions
        ph_note = (
            f"The assay pH was {c.ph:g}. GROMACS's pdb2gmx assigns standard protonation "
            "states, which is only right near neutral pH; before production, check the "
            "titratable residues at this pH (PROPKA) and set them with pdb2gmx's "
            "-his/-asp/-glu/-lys options."
            if c.ph is not None else
            "No assay pH was supplied, so the standard protonation states pdb2gmx assigns "
            "are an assumption, not a measurement."
        )
        return f"""# Provenance: MD setup for PDB {self.pdb_id}

Every setting in the `*.mdp` files, and the choices `run.sh` makes, is in
this table with where it came from (a test maps each mdp key to a row): **measured** (from the assay behind a cited kinetic constant, or the
deposited structure), **chosen** (a labelled default), or **method** (a
published model or algorithm, cited).

| parameter | value | origin | source |
|---|---|---|---|
{rows}

## What this setup does not do

- **Small molecules are stripped.** `run.sh` removes every HETATM record and
  prints what it removed. A substrate, inhibitor or cofactor needs its own
  topology (for example from ACPYPE/GAFF or CGenFF) before it can be
  simulated; none is invented here.
- **Protonation.** {ph_note}
- **Length.** {self.ns:g} ns samples side-chain and loop motion. It does not
  sample catalysis, and a kcat cannot be read off it.

## Stages

energy minimisation (steepest descent) -> NVT 100 ps (position restraints)
-> NPT 100 ps (C-rescale, restraints) -> production {self.ns:g} ns
(Parrinello-Rahman), all at {c.temperature_k:.2f} K.
"""


__all__ = ["Conditions", "MdSetup", "Parameter", "ORIGINS"]
