# Real alchemical output for the estimator tests

The solvent leg of `caterva fep` for benzene, replica 1: 25 lambda windows
(charges off in 4, van der Waals in 20), 50 ps of production each after
10 ps NVT and 10 ps NPT, at 310.15 K, run with GROMACS 2026.1 on
2026-09-28 from the setup `caterva fep` wrote (energies at every state,
calc-lambda-neighbors = -1).

- `benzene_solvent_rep1.npz`: `du[window, state, sample]`, each window's
  samples' reduced energy at every state relative to its own, as
  `read_dhdl` returns it (stored float32), and `temperature`.
- `benzene_solvent_lambda5.xvg.gz`: window 5's dhdl.xvg as GROMACS wrote it.
- `benzene_solvent_rep1_gmxbar.txt`: `gmx bar`'s 24 neighbour free
  energies (kJ/mol, as printed to 2 decimals) on the same 25 files. Its
  total was -1.31 +/- 1.13 kJ/mol.

The benzene topology is a TEST FIXTURE built from the force field's own
aromatic atom types, not a production parameterisation, and the windows
are short: these files test that the estimators compute what they claim
on real GROMACS output. They say nothing about benzene's hydration free
energy.
