"""The methods Caterva's structure and dynamics outputs rest on, cited.

Every DOI here was resolved against Crossref on 2026-09-27 and matched on
first author, year and title before it was written down. A setup file that
names a force field without saying whose, and a citation that does not
resolve, are the same defect this project exists to refuse.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Method:
    key: str
    what: str
    citation: str
    doi: str

    def cite(self) -> str:
        return f"{self.citation}, doi:{self.doi}"


METHODS = {m.key: m for m in (
    Method("pdb", "Protein Data Bank",
           "Berman et al. (2000) Nucleic Acids Res. 28:235", "10.1093/nar/28.1.235"),
    Method("chimerax", "UCSF ChimeraX",
           "Pettersen et al. (2021) Protein Sci. 30:70", "10.1002/pro.3943"),
    Method("gromacs", "GROMACS",
           "Abraham et al. (2015) SoftwareX 1-2:19", "10.1016/j.softx.2015.06.001"),
    Method("amber99sb-ildn", "AMBER ff99SB-ILDN protein force field",
           "Lindorff-Larsen et al. (2010) Proteins 78:1950", "10.1002/prot.22711"),
    Method("tip3p", "TIP3P water model",
           "Jorgensen et al. (1983) J. Chem. Phys. 79:926", "10.1063/1.445869"),
    Method("v-rescale", "velocity-rescaling thermostat",
           "Bussi, Donadio & Parrinello (2007) J. Chem. Phys. 126:014101", "10.1063/1.2408420"),
    Method("parrinello-rahman", "Parrinello-Rahman barostat",
           "Parrinello & Rahman (1981) J. Appl. Phys. 52:7182", "10.1063/1.328693"),
    Method("pme", "smooth particle mesh Ewald electrostatics",
           "Essmann et al. (1995) J. Chem. Phys. 103:8577", "10.1063/1.470117"),
    Method("c-rescale", "stochastic cell-rescaling barostat (C-rescale)",
           "Bernetti & Bussi (2020) J. Chem. Phys. 153:114107", "10.1063/5.0020514"),
    Method("lincs", "LINCS bond constraints",
           "Hess et al. (1997) J. Comput. Chem. 18:1463",
           "10.1002/(SICI)1096-987X(199709)18:12<1463::AID-JCC4>3.0.CO;2-H"),
    Method("propka", "PROPKA3 pKa prediction",
           "Olsson et al. (2011) J. Chem. Theory Comput. 7:525", "10.1021/ct100578z"),
    Method("mcsa", "Mechanism and Catalytic Site Atlas (M-CSA)",
           "Ribeiro et al. (2018) Nucleic Acids Res. 46:D618", "10.1093/nar/gkx1012"),
    Method("needleman-wunsch", "global sequence alignment",
           "Needleman & Wunsch (1970) J. Mol. Biol. 48:443",
           "10.1016/0022-2836(70)90057-4"),
    Method("blosum62", "BLOSUM62 substitution matrix",
           "Henikoff & Henikoff (1992) Proc. Natl. Acad. Sci. USA 89:10915",
           "10.1073/pnas.89.22.10915"),
)}

__all__ = ["Method", "METHODS"]
