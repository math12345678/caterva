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

`lyso_1aki_res1-59_water_wrapped.xtc` and
`lyso_1aki_res1-59_water_wrapped.gro.gz`: the atoms and frames of
`lyso_1aki_res1-59_water.*` (1,716 atoms, 21 frames), moved so that the
active site straddles the periodic box. Neither fixture above does: on them every catalytic group is whole and no arm or
water-site pair crosses the box, so the angles and water counts come out
the same with the periodic handling taken out, and a broken
`nearest_image` or `make_whole` would pass. Made on the full 23,873-atom
replica 1 and em.gro with `gmx trjconv -trans -4.304 -5.831 -1.931 -pbc
atom -ur tric` (the translation puts the centroid of the six catalytic
groups at the corner of the triclinic cell; each atom is then put in the
cell), then cut to the fixture's atoms with `gmx trjconv -n` (GROMACS
2026.1, 2026-09-29; 140,472 and 22,607 bytes). The cut is exact: its
coordinates equal the wrapped full system's for those atoms in every
frame. In it Glu35, Asn46 and Asp48 have their two atoms on opposite sides
of the cell in all 21 frames, Asp52 in 20 and Asn59 in 16; 16 of the 18
arms of the 24 angles cross the box in at least one frame. Taken without
periodic handling, 494 of the 504 angle-frames are more than 1 degree off
(the worst 143.7 degrees), and 103 of the 126 residue-frame water counts
are wrong.

`lyso_1aki_rep1_gmx_angles_wrapped.txt`: in the format of
`lyso_1aki_rep1_gmx_angles.txt`, the `-oav` output of the same `gmx gangle`
command on the wrapped full trajectory with rep1/md.tpr, which lets gangle
make the molecules whole (`-rmpbc`). It differs from the unwrapped file by
up to 0.164 degrees because putting atoms back in a box that changes size
every frame (NPT) re-rounds them to the .xtc's 0.001 nm. Without the tpr,
`gmx gangle -s` on the wrapped .gro cannot make the split groups whole,
and its angles are off by up to 124.7 degrees (the error Caterva makes if
it takes nearest-image arms from centres of groups not made whole first),
so the reference had to come from the full system. `gmx select` with the
water selections on the wrapped full trajectory and wrapped em.gro printed
exactly `lyso_1aki_rep1_gmx_water.txt` again (compared with diff), so that
file is the water reference for the wrapped fixture too.

`lyso_1aki_rep1_gmx_faces.txt`: which face of each angle's vertex its
partners are on (caterva/analyze/faces.py), for the same 24 angles, one line
each in the format of `lyso_1aki_rep1_gmx_angles.txt`: residue numbers a, v,
b, then the 21 per-frame values `gmx gangle -g1 plane -group1 'cog of (resnr
a and name ...) plus cog of (resnr v and name ...) plus cog of (resnr b and
name ...)' -g2 vector -group2 'cog of (resnr v and name ...) plus cog of
(resnr v and name CA)' -oav` printed (GROMACS 2026.1, 2026-09-29) on
`lyso_1aki_res1-59.xtc` with `lyso_1aki_res1-59.gro.gz` as the structure:
the angle in degrees between the normal of the plane a-v-b, which gangle
takes as (v - a) x (b - a), and the arm from v's centre to its CA. 90 minus
it is the elevation Caterva measures. The residues are in M-CSA's order
(48, 50, 46, 59, 52, 35), as the lysozyme run had them, which decides which
partner of each angle comes first and so the sign of its face.

`lyso_1aki_rep1_gmx_faces_wrapped.txt`: the same command on the wrapped
full replica 1 (`gmx trjconv -trans -4.304 -5.831 -1.931 -pbc atom -ur tric`
on rep1/md.xtc, as for `lyso_1aki_res1-59_water_wrapped.xtc`, whose first
900 atoms it equals exactly in every frame) with rep1/md.tpr, so that
gangle makes the split groups whole. Taken without periodic handling, 489
of the 504 elevations on the wrapped fixture are more than a degree off
and 282 have the wrong sign.

`lyso_1aki_rep1_gmx_dihedrals.txt`: `gmx gangle -g1 dihedral -group1 'cog
of (resnr a ...) plus cog of (resnr v ...) plus cog of (resnr b ...) plus
cog of (resnr v and name CA)' -oav` on `lyso_1aki_res1-59.xtc` (GROMACS
2026.1, 2026-09-29), the signed dihedral a-v-b-CA, for each of the 24
angles taken both ways round (48 lines: a v b, then b v a). Its sign equals
the elevation's in all 1,008 values; it is kept to show why the elevation
and not this dihedral is thresholded. Asp48 sits almost in line with Asn59
and its CA (179.3 degrees at most), and there the dihedral
Asn46-Asn59-Asp48-CA runs from -168.9 to +132.4 degrees while the CA stays
within 11.3 degrees of the plane of the angle.

`t4l_bnz_first6000_gmx_sasa.txt`: the solvent-accessible area (nm^2) of
every residue of the T4 lysozyme protein in `t4l_bnz_first6000.gro.gz`
(its first 2,603 atoms, residues 1-162; `gmx sasa`'s Protein group leaves
out the benzene and the water), one line per residue: number, name, area.
From `gmx sasa -s t4l.gro -f t4l.gro -surface Protein -probe 0.14 -ndots
10000 -nopbc -or` on the decompressed .gro (GROMACS 2026.1, 2026-09-30),
the -or column as printed. -ndots 10000 makes it a converged reference: on
lysozyme's em.gro, gmx sasa at 10,000 was within 0.0035 nm^2 of Caterva at
50,000 points on every residue (caterva/analyze/sasa.py). The same run
gave a total of 87.130 nm^2.

`t4l_bnz_first6000_gmx_sasa_ndots2000.txt`: the same, from the same
command with `-ndots 2000` (GROMACS 2026.1, 2026-09-30), the number of
points analyze.sh asks for and Caterva's own route uses: the two routes'
difference on one structure, residue by residue. The run gave a total of
87.113 nm^2.

`lyso_1aki_rep1_gmx_sasa.txt`: for each of the six catalytic residues of
hen lysozyme, its number, name, its area in `lyso_1aki_res1-59.gro.gz`,
then its 21 per-frame areas (nm^2) in `lyso_1aki_res1-59.xtc`; and first a
line `total Protein` with the whole surface's area, in the same order. The
-o columns of `gmx sasa -s lyso_1aki_res1-59.gro -f lyso_1aki_res1-59.xtc
-surface Protein -probe 0.14 -ndots 2000 -nopbc -output 'group Protein and
resnr 35' ... 'group Protein and resnr 59' -o` (and `-f` the .gro for the
first number), GROMACS 2026.1, 2026-09-30: the options analyze.sh runs.
The surface is the fixture's protein, residues 1-59, not the whole enzyme,
so these are not lysozyme's areas; they are what `gmx sasa` measures on
the same atoms and frames Caterva is given. The fragment is whole in every
frame as stored.
