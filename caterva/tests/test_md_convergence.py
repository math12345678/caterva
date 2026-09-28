"""`caterva md --summarise`: a replica set is called a result only when it is one.

Synthetic AR(1) series stand in for trajectories, because their correlation
time is known exactly. Measured over 100 random seeds when this was written
(2026-09-28): under-sampled replicas were called unconverged 100/100;
replicas with different means were flagged 100/100 (as disagreeing or
unconverged); converged replicas were called consistent 94/100. The 6% false
alarm is the conservative direction and is stated rather than hidden. The
tests below use fixed seeds.
"""
from __future__ import annotations

import math
import random

import pytest

from caterva.md.__main__ import EXIT_NOT_A_RESULT, main
from caterva.md.convergence import MIN_EFFECTIVE_SAMPLES, block_average, collect, read_xvg, summarise


def ar1(rng: random.Random, n: int, phi: float, mu: float, sd: float = 1.0):
    x, out = mu, []
    for _ in range(n):
        x = mu + phi * (x - mu) + rng.gauss(0, sd * math.sqrt(1 - phi * phi))
        out.append(x)
    return out


def test_block_averaging_recovers_the_known_correlated_error():
    # AR(1), phi 0.9: the true error of the mean is sd/sqrt(n) * sqrt((1+phi)/(1-phi)).
    rng = random.Random(3)
    xs = ar1(rng, 8192, 0.9, 0.0)
    b = block_average(xs)
    true = 1 / math.sqrt(8192) * math.sqrt(1.9 / 0.1)
    naive = b.levels[0][1]
    assert b.plateaued
    assert naive < 0.5 * true  # the uncorrelated estimate is badly wrong ...
    assert 0.7 * true < b.sem < 1.3 * true  # ... and blocking fixes it
    assert b.effective_samples == pytest.approx(8192 * (naive / b.sem) ** 2)


def test_converged_replicas_are_consistent():
    rng = random.Random(0)
    s = summarise([(f"rep{i}", ar1(rng, 4000, 0.5, 0.20, 0.02)) for i in (1, 2, 3)], "RMSD", "nm")
    assert s.verdict == "consistent", s.reasons
    assert s.spread is not None and abs(s.mean - 0.20) < 0.01


def test_under_sampled_replicas_are_unconverged():
    rng = random.Random(0)
    s = summarise([(f"rep{i}", ar1(rng, 400, 0.995, 0.20, 0.05)) for i in (1, 2, 3)], "RMSD", "nm")
    assert s.verdict == "unconverged"
    assert any("independent samples" in r or "still rising" in r for r in s.reasons)


def test_replicas_in_different_states_are_not_averaged_into_one():
    rng = random.Random(0)
    s = summarise([("rep1", ar1(rng, 4000, 0.3, 0.15, 0.01)),
                   ("rep2", ar1(rng, 4000, 0.3, 0.25, 0.01)),
                   ("rep3", ar1(rng, 4000, 0.3, 0.20, 0.01))], "RMSD", "nm")
    assert s.verdict in ("replicas disagree", "unconverged")
    assert s.verdict != "consistent"


def test_one_replica_is_one_sample_however_smooth():
    rng = random.Random(0)
    s = summarise([("rep1", ar1(rng, 4000, 0.3, 0.2, 0.001))], "RMSD", "nm")
    assert s.verdict == "one sample" and s.spread is None


def test_too_few_frames_gives_no_error_rather_than_a_small_one():
    s = summarise([("rep1", [0.1] * 10), ("rep2", [0.1] * 10)], "RMSD", "nm")
    assert s.verdict == "unconverged"


def test_the_threshold_is_what_the_docs_say():
    assert MIN_EFFECTIVE_SAMPLES == 10


# --- files and the command -------------------------------------------------------

def _xvg(values):
    head = '# gmx rms\n@    title "RMSD"\n@    xaxis  label "Time (ns)"\n'
    return head + "".join(f"{i * 0.01:.3f}  {v:.6f}\n" for i, v in enumerate(values))


def test_read_xvg_skips_gromacs_headers(tmp_path):
    p = tmp_path / "a.xvg"
    p.write_text(_xvg([0.1, 0.2]))
    assert read_xvg(p) == [(0.0, 0.1), (0.01, 0.2)]


def _write_run(tmp_path, series):
    for i, values in enumerate(series, start=1):
        (tmp_path / f"rep{i}").mkdir()
        (tmp_path / f"rep{i}" / "rmsd.xvg").write_text(_xvg(values))
    return tmp_path


def test_collect_orders_replicas_numerically(tmp_path):
    rng = random.Random(1)
    _write_run(tmp_path, [ar1(rng, 50, 0.1, 0.2)] * 11)
    assert [name for name, _ in collect(tmp_path)][:3] == ["rep1", "rep2", "rep3"]
    assert collect(tmp_path)[-1][0] == "rep11"


def test_summarise_exit_codes_and_report(tmp_path, capsys):
    rng = random.Random(0)
    (tmp_path / "good").mkdir()
    good = _write_run(tmp_path / "good", [ar1(rng, 4000, 0.5, 0.20, 0.02) for _ in range(3)])
    assert main(["--summarise", str(good)]) == 0
    out = capsys.readouterr().out
    assert "Verdict: consistent" in out and "doi:10.1063/1.457480" in out
    assert (good / "CONVERGENCE.md").exists()

    (tmp_path / "bad").mkdir()
    bad = _write_run(tmp_path / "bad", [ar1(rng, 400, 0.995, 0.20, 0.05) for _ in range(3)])
    assert main(["--summarise", str(bad)]) == EXIT_NOT_A_RESULT


def test_summarise_refuses_a_directory_that_has_not_run(tmp_path):
    assert main(["--summarise", str(tmp_path)]) == 3
