# ADR 0001: Do not depend on the `tellurium` umbrella package

**Status:** Accepted

## Context

The obvious way to get antimony + roadrunner + libsbml in one dependency is
`pip install tellurium`, which bundles them together along with several
other packages for COMBINE archive support and numerical markup handling.

In practice, `tellurium` also pulls in `python-libcombine` and
`python-libnuml`. Neither has prebuilt wheels for every platform/Python
version combination Terrium needs to support, and on any platform without a
prebuilt wheel, `pip install` falls back to compiling from source, which
requires `cmake` and `swig` to be installed separately. This turns "install
one package" into "debug a C++ build toolchain," for functionality (COMBINE
archives, numerical markup) that Terrium doesn't use at all.

## Decision

Depend directly on the three sub-packages that actually do the work:
`libroadrunner` (ODE integration), `antimony` (model definition language,
translates to SBML), and `python-libsbml` (SBML validation). Do not add
`tellurium` itself as a dependency, and document this prominently
(`requirements.txt` has a `NOTE` comment, `README.md` has a dedicated
section) so nobody re-adds it by habit, since `tellurium` is the
"obviously correct" name for this kind of pipeline.

## Consequences

- Installation is faster and more reliable across platforms, since all
  three real dependencies do publish prebuilt wheels for the supported
  Python range (3.10-3.13).
- Anyone reading Terrium's imports and expecting to see `import tellurium`
  needs the README's explanation, or the deviation looks like a mistake.
- If Terrium ever needs COMBINE archive import/export (e.g., accepting a
  model file from another tool), this decision needs revisiting --
  `python-libcombine` would become a real, justified dependency at that
  point rather than unnecessary bulk.
