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
