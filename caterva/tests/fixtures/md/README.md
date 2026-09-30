# A real GROMACS trajectory, for the native .xtc reader

`t4l_bnz_first6000.xtc`: the first 6,000 atoms (T4 lysozyme L99A, the
benzene, and 3,000-odd water atoms) of the first three frames (0, 10 and
20 ps) of the NPT equilibration `caterva complex` built from PDB 181L,
cut with `gmx trjconv` (GROMACS 2026.1, 2026-09-28). The waters matter:
the format compresses runs of close atoms specially, and only a system
with water exercises that path.

`t4l_bnz_first6000_gmx.npz`: `gmx trjconv`'s own decoding of the same file
(written as .gro), as integers in units of 0.001 nm, the file's precision.
The reader must reproduce every one exactly.

The benzene topology behind the run is a test fixture, not a production
parameterisation.

`t4l_bnz_first6000.gro.gz`: the same 6,000 atoms' names and residues (from
the run's em.gro), so selections can be made on the trajectory.
`gmx distance -s <that gro> -f t4l_bnz_first6000.xtc -select 'cog of
(resnr 11 and name OE1 OE2) plus cog of (resnr 20 and name OD1 OD2)'`
(T4 lysozyme's catalytic Glu11 and Asp20 carboxylates) printed 0.818,
0.806 and 0.825 nm for the three frames.

`lyso_1aki_res1-59.xtc` and `lyso_1aki_res1-59.gro.gz`: residues 1-59 (900
atoms) of hen lysozyme (1AKI), all 21 frames of replica 1 of a 10 ps
`caterva md` run (GROMACS 2026.1, 2026-09-29), cut with `gmx trjconv`, and
the matching atoms of that run's em.gro. `lyso_1aki_rep1_gmx_hbond.txt`:
per-frame hydrogen-bond counts from `gmx hbond -r 'resnr A and not name N H
O C CA HA OC1 OC2' -t '<same for B>'` on the full trajectory, one line per
catalytic pair (A B then 21 counts).

`lyso_1aki_rep1_gmx_chi1.txt`: chi1 (N-CA-CB-gamma) of six catalytic
residues, one line each (residue number, name, then the 21 per-frame angles
in degrees), from `gmx angle -type dihedral` (GROMACS 2026.1, 2026-09-29) on
`lyso_1aki_res1-59.xtc` with an index of the four atoms per residue taken
from `lyso_1aki_res1-59.gro.gz`.

`lyso_1aki_rep1_gmx_angles.txt`: the 24 angles between catalytic groups
that `caterva analyze` plans for lysozyme (both arms within 0.6 nm between
functional-group centres in 1AKI's protein.pdb), one line each: residue
numbers a, v, b (the vertex in the middle), then the 21 per-frame angles in
degrees, the `-oav` output of `gmx gangle -g1 angle -group1 'cog of (resnr
a and name ...) plus cog of (resnr v and name ...) plus cog of (resnr b and
name ...)'` (GROMACS 2026.1, 2026-09-29) on `lyso_1aki_res1-59.xtc` with
`lyso_1aki_res1-59.gro.gz` as the structure.

`lyso_1aki_res1-59_water.xtc` and `lyso_1aki_res1-59_water.gro.gz`: the
same 21 frames of replica 1 with the water at the active site: residues
1-59 (900 atoms) and every water (272, whole: OW, HW1, HW2) whose oxygen came
within 1.0 nm of a catalytic functional atom (Glu35 OE1 OE2, Asn46 OD1 ND2,
Asp48 OD1 OD2, Ser50 OG, Asp52 OD1 OD2, Asn59 OD1 ND2) in any frame of the
full trajectory or in em.gro. The waters were chosen by `gmx select
-select 'same residue as (resname SOL and name OW and within 1.0 of (...))'
-on` on rep1/md.xtc and on em.gro, the per-frame index groups merged, and
the 1,716 atoms cut with `gmx trjconv -n` (GROMACS 2026.1, 2026-09-29); the
.gro.gz is the same atoms of em.gro (133,676 and 22,312 bytes).

`lyso_1aki_rep1_gmx_water.txt`: for each of the six catalytic residues, its
number, name, the count in em.gro, then the 21 per-frame counts of water
oxygens within 0.35 nm of its functional atoms: `gmx select -select
'resname SOL and name OW and within 0.35 of (resnr N and name ...)' -os`
on `lyso_1aki_res1-59_water.xtc` (and on the .gro for the count at the
start). The same selections on the full 23,873-atom trajectory and em.gro
printed the same counts in every frame, which is what shows the cut kept
every water that matters.
