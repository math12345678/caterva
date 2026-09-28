"""Tests moved from caterva/tests/test_model_provenance.py on 2026-09-27 with their domains."""

MODELS = [
    build_michaelis_menten_antimony(km=2.5, vmax=5.0, s0=10.0),
    build_mm_competitive_antimony(km=2.5, vmax=5.0, ki=1.2, s0=10.0, i=0.5),
    build_sir_antimony(beta=0.3, gamma=0.1, s0=990.0, i0=10.0, r0_recovered=0.0),
]


