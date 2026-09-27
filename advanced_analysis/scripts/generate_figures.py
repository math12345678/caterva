"""Generate a publication-quality figure suite from the Caterva engine.

Every figure runs the real engine (deterministic ODE via roadrunner, exact
Gillespie SSA, discrete recurrences) and overlays the closed-form reference
the engine itself is validated against, so each plot is simultaneously a
visualization and a verification artifact.

Every figure also renders its ``modelCitations`` and per-parameter provenance
on the canvas, matching ADR 0008: parameters resolved from literature carry
their locatable citation (e.g. the BRENDA golden-set Km/Ki), while teaching
values are explicitly labeled "default" and never claim a citation.

Outputs PNG at 200 dpi into ``advanced_analysis/figures/``.
"""

from __future__ import annotations

import json
import math
import pathlib
import sys

import numpy as np

_REPO = pathlib.Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import rcParams  # noqa: E402

from caterva import caterva_engine as te  # noqa: E402

FIGS = pathlib.Path(__file__).resolve().parents[1] / "figures"
FIGS.mkdir(exist_ok=True)

rcParams.update({
    "font.family": "serif",
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10.5,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 8.5,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.dpi": 200,
    "savefig.bbox": "tight",
    "axes.grid": True,
    "grid.alpha": 0.3,
    "grid.linewidth": 0.5,
})

PALETTE = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#8c564b"]


def arr(res, col: str) -> np.ndarray:
    return np.asarray(res.column(col), dtype=float)


def save(fig, name: str) -> None:
    path = FIGS / name
    fig.savefig(path)
    plt.close(fig)
    print(f"  wrote {path.name}")


def finalize(fig, name: str, refs: list[str], provenance: list[str]) -> None:
    """Lay out with a reserved bottom strip, then draw citations + provenance.

    ``refs`` are the figure's ``modelCitations`` (locatable: DOI or URL).
    ``provenance`` clauses state each plotted parameter's origin: ``resolved``
    values carry their literature citation; everything else is a teaching
    ``default``. Mirrors ADR 0008's origin model — a default is labeled
    default and never passed off as literature.
    """
    fig_h = fig.get_figheight()
    n_lines = len(refs) + 1 + (1 if refs else 0)
    text_h = n_lines * 0.122
    block = max(0.07, min(0.18, (text_h + 0.10) / fig_h))
    fig.tight_layout(rect=[0, block, 1, 1])
    lines = []
    if refs:
        lines.append("References")
        lines += [f"[{j}] {r}" for j, r in enumerate(refs, 1)]
    lines.append("Parameter provenance: " + " · ".join(provenance))
    fig.text(0.02, 0.008, "\n".join(lines), ha="left", va="bottom",
             fontsize=6.5, linespacing=1.35)
    save(fig, name)


# ---------------------------------------------------------------------------
# 1. Enzyme kinetics: Michaelis-Menten + competitive inhibition
# ---------------------------------------------------------------------------

def fig_michaelis_menten() -> None:
    # Km resolved from the BRENDA golden set (LDH/L-lactate, Homo sapiens);
    # Vmax and S0 are teaching defaults (see ADR 0008 provenance, ADR 0013).
    km, vmax, s0 = 10.73, 20.0, 40.0
    res = te.simulate_michaelis_menten(km=km, vmax=vmax, s0=s0, end=8.0, points=401)

    t = arr(res, "time")
    s = arr(res, "[S]")
    p = arr(res, "[P]")

    # Closed-form implicit solution: Km ln(S0/S) + (S0 - S) = Vmax t
    s_theory = np.linspace(s0, 1e-3, 400)
    t_theory = (km * np.log(s0 / s_theory) + (s0 - s_theory)) / vmax
    p_theory = s0 - s_theory

    # Rate law: v(S) = Vmax S / (Km + S)
    s_grid = np.linspace(0, s0, 200)
    v_law = vmax * s_grid / (km + s_grid)
    v_half = vmax / 2

    fig, axes = plt.subplots(1, 3, figsize=(13, 4.4))

    ax = axes[0]
    ax.plot(t, s, color=PALETTE[0], lw=2, label=r"$S(t)$ (engine)")
    ax.plot(t, p, color=PALETTE[1], lw=2, label=r"$P(t)$ (engine)")
    ax.plot(t_theory, s_theory, color=PALETTE[0], ls="--", lw=1,
            label=r"$K_m\ln\frac{S_0}{S} + S_0 - S = V_{\max}t$")
    ax.plot(t_theory, p_theory, color=PALETTE[1], ls="--", lw=1, alpha=0.7)
    ax.set_xlabel("time")
    ax.set_ylabel("concentration")
    ax.set_title("Michaelis–Menten trajectory vs exact solution")
    ax.legend(loc="center right")

    ax = axes[1]
    ax.plot(s_grid, v_law, color=PALETTE[0], lw=2,
            label=r"$v = V_{\max}S/(K_m+S)$")
    ax.axhline(v_half, color=PALETTE[3], lw=0.8, ls=":", alpha=0.8)
    ax.axvline(km, color=PALETTE[3], lw=0.8, ls=":", alpha=0.8)
    ax.annotate(r"$v = V_{\max}/2$", xy=(km, v_half), xytext=(3.2, 3.1),
                arrowprops=dict(arrowstyle="->", lw=0.8, color="0.4"))
    ax.annotate(r"$S = K_m$", xy=(km, 0.4), xytext=(0.1, 0.55),
                arrowprops=dict(arrowstyle="->", lw=0.8, color="0.4"))
    ax.set_xlabel(r"substrate $S$")
    ax.set_ylabel(r"reaction rate $v$")
    ax.set_title(r"$v$ vs $S$; $K_m=%.1f$, $V_{\max}=%.1f$" % (km, vmax))
    ax.set_xlim(0, s0)
    ax.set_ylim(0, vmax * 1.05)
    ax.legend(loc="center right")

    ax = axes[2]
    residual = (km * np.log(s0 / np.maximum(s, 1e-12)) + (s0 - s)) - vmax * t
    ax.plot(t, residual, color=PALETTE[0], lw=1)
    ax.axhline(0, color="0.3", lw=0.8)
    ax.set_xlabel("time")
    ax.set_ylabel("implicit-solution residual")
    ax.set_title(f"residual (max |r| = {np.max(np.abs(residual)):.1e})")

    fig.suptitle("Enzyme kinetics — Michaelis–Menten", y=1.03)
    finalize(
        fig, "01_michaelis_menten.png",
        refs=[
            "Michaelis, L. & Menten, M. L. (1913) Die Kinetik der "
            "Invertinwirkung, Biochem. Z. 49, 333-369; English translation: "
            "Goody, R. S. & Johnson, K. A. (2011) Biochemistry 50, 8264-8269. "
            "doi:10.1021/bi201284u",
            "Briggs, G. E. & Haldane, J. B. S. (1925) A note on the kinetics "
            "of enzyme action. Biochem. J. 19, 338-339. doi:10.1042/bj0190338",
            "BRENDA L-lactate dehydrogenase (EC 1.1.1.27): "
            "Km(L-lactate, Homo sapiens) = 10.73 mM, ref 740253. "
            "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
        ],
        provenance=[
            "Km = 10.73 mM resolved (BRENDA golden set G1, ref 740253)",
            "Vmax = 20 mM/s and S0 = 40 mM are teaching defaults",
        ])


def fig_competitive_inhibition() -> None:
    # Km and Ki resolved from the BRENDA golden set (LDH/lactate and
    # LDH/gossypol, Homo sapiens); Vmax/S0 and the inhibitor sweep (given as
    # I/Ki multiples) are teaching defaults.
    km, vmax, s0 = 10.73, 20.0, 40.0
    ki = 0.0014
    i_ratios = [0.0, 0.5, 1.0, 2.0, 4.0]
    colors = plt.cm.viridis(np.linspace(0.15, 0.85, len(i_ratios)))

    t_grid = None
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.4))

    for ratio, c in zip(i_ratios, colors):
        res = te.simulate_mm_competitive_inhibition(
            km=km, vmax=vmax, ki=ki, s0=s0, i=ratio * ki, end=32.0, points=401)
        t_grid = arr(res, "time")
        s = arr(res, "[S]")
        km_app = km * (1.0 + ratio)

        axes[0].plot(t_grid, s, color=c, lw=1.8,
                     label=rf"$I/K_i={ratio:g}$, $K_m^{{\rm app}}={km_app:.2f}$")

        s_theory = np.linspace(s0, 1e-3, 400)
        t_theory = (km_app * np.log(s0 / s_theory) + (s0 - s_theory)) / vmax
        axes[0].plot(t_theory, s_theory, color=c, ls="--", lw=0.7, alpha=0.6)

        s_grid = np.linspace(0, s0, 200)
        v_law = vmax * s_grid / (km_app + s_grid)
        axes[1].plot(s_grid, v_law, color=c, lw=1.8,
                     label=rf"$I/K_i={ratio:g}$, $K_m^{{\rm app}}={km_app:.2f}$")

    axes[0].set_xlabel("time")
    axes[0].set_ylabel(r"substrate $S$")
    axes[0].set_title("Inhibitor raises the apparent $K_m$ (slows substrate use)")
    axes[0].legend(fontsize=7.5, loc="center right")

    axes[1].set_xlabel(r"substrate $S$")
    axes[1].set_ylabel(r"rate $v$")
    axes[1].set_title(r"$v$–$S$ curves: pure competitive shift, same $V_{\max}$")
    axes[1].legend(fontsize=7.5, loc="center right")

    fig.suptitle("Enzyme kinetics — competitive inhibition "
                 r"($K_m^{app} = K_m(1 + I/K_i)$)", y=1.03)
    finalize(
        fig, "02_competitive_inhibition.png",
        refs=[
            "Briggs, G. E. & Haldane, J. B. S. (1925) A note on the kinetics "
            "of enzyme action. Biochem. J. 19, 338-339. doi:10.1042/bj0190338",
            "BRENDA L-lactate dehydrogenase (EC 1.1.1.27): "
            "Km(L-lactate, Homo sapiens) = 10.73 mM, ref 740253. "
            "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
            "BRENDA L-lactate dehydrogenase (EC 1.1.1.27): "
            "Ki(gossypol, Homo sapiens) = 0.0014 mM, ref 711801. "
            "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
        ],
        provenance=[
            "Km = 10.73 mM (resolved, BRENDA G1 ref 740253); "
            "Ki = 0.0014 mM (resolved, G4 ref 711801)",
            "Vmax, S0, and inhibitor levels (Ki multiples) are teaching defaults",
        ])


# ---------------------------------------------------------------------------
# 2. Epidemiology: SIR and SEIR
# ---------------------------------------------------------------------------

def fig_sir() -> None:
    beta, gamma = 0.3, 0.1
    s0, i0 = 990.0, 10.0
    res = te.simulate_sir(beta=beta, gamma=gamma, s0=s0, i0=i0,
                          end=150.0, points=601)
    t = arr(res, "time")
    s = arr(res, "[S]")
    i = arr(res, "[I]")
    r = arr(res, "[R]")
    n = s + i + r

    r0 = beta / gamma

    fig, axes = plt.subplots(1, 3, figsize=(13, 4.4))

    axes[0].plot(t, s, color=PALETTE[0], lw=2, label="S (engine)")
    axes[0].plot(t, i, color=PALETTE[1], lw=2, label="I (engine)")
    axes[0].plot(t, r, color=PALETTE[2], lw=2, label="R (engine)")
    axes[0].set_xlabel("time")
    axes[0].set_ylabel("individuals")
    axes[0].set_title(rf"SIR trajectory, $R_0 = \beta/\gamma = {r0:.1f}$")
    axes[0].legend(loc="center right")

    # phase plane: dI/dS
    axes[1].plot(s, i, color=PALETTE[4], lw=2)
    axes[1].plot(s0, i0, "o", color="0.2", ms=4)
    axes[1].axvline(1.0 / r0 * 0.0 + 1.0 / r0, color=PALETTE[3], ls=":", lw=1)
    axes[1].set_xlabel("S")
    axes[1].set_ylabel("I")
    axes[1].set_title(rf"Phase plane; I peaks at $S = 1/R_0 = {1/r0:.2f}$")
    axes[1].annotate(r"$S = 1/R_0$", xy=(1 / r0, np.max(i) * 0.8),
                     xytext=(600, np.max(i) * 0.85),
                     arrowprops=dict(arrowstyle="->", lw=0.8, color="0.4"))

    axes[2].plot(t, n, color=PALETTE[0], lw=2)
    axes[2].set_xlabel("time")
    axes[2].set_ylabel(r"$S+I+R$")
    axes[2].set_title(rf"Conservation $N={n[0]:.0f}$ "
                      f"(max drift {np.max(np.abs(n - n[0])):.1e})")

    fig.suptitle("Epidemiology — SIR compartment model", y=1.03)
    finalize(
        fig, "03_sir.png",
        refs=[
            "Kermack, W. O. & McKendrick, A. G. (1927) A contribution to the "
            "mathematical theory of epidemics. Proc. R. Soc. A 115, 700-721. "
            "doi:10.1098/rspa.1927.0118",
        ],
        provenance=[
            "beta = 0.3, gamma = 0.1 per day, N = 1000 are teaching defaults "
            "(R0 = beta/gamma = 3)",
        ])


def fig_seir() -> None:
    beta, sigma, gamma = 0.5, 0.25, 0.1
    s0, e0, i0 = 990.0, 5.0, 5.0
    res = te.simulate_seir(beta=beta, sigma=sigma, gamma=gamma, s0=s0,
                           e0=e0, i0=i0, end=120.0, points=481)
    t = arr(res, "time")
    s = arr(res, "[S]")
    e = arr(res, "[E]")
    i = arr(res, "[I]")
    r = arr(res, "[R]")

    # No-incubation SIR with identical beta/gamma/R0 for contrast
    sir = te.simulate_sir(beta=beta, gamma=gamma, s0=s0, i0=e0 + i0,
                          end=120.0, points=481)

    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.4))

    axes[0].plot(t, s, color=PALETTE[0], lw=2, label="S")
    axes[0].plot(t, e, color=PALETTE[3], lw=2, label="E (exposed)")
    axes[0].plot(t, i, color=PALETTE[1], lw=2, label="I (infectious)")
    axes[0].plot(t, r, color=PALETTE[2], lw=2, label="R")
    axes[0].set_xlabel("time")
    axes[0].set_ylabel("individuals")
    axes[0].set_title("SEIR with incubation phase")
    axes[0].legend(loc="center right")

    axes[1].plot(arr(sir, "time"), arr(sir, "[I]"), color=PALETTE[1], lw=1.6,
                 ls="--", label="SIR (no incubation)")
    axes[1].plot(t, i, color=PALETTE[0], lw=2, label="SEIR infectious peak")
    axes[1].set_xlabel("time")
    axes[1].set_ylabel("infectious")
    axes[1].set_title("Incubation delays and widens the infectious peak")
    axes[1].legend(loc="center right")

    fig.suptitle("Epidemiology — SEIR with exposed compartment", y=1.03)
    finalize(
        fig, "04_seir.png",
        refs=[
            "Kermack, W. O. & McKendrick, A. G. (1927) A contribution to the "
            "mathematical theory of epidemics. Proc. R. Soc. A 115, 700-721. "
            "doi:10.1098/rspa.1927.0118",
        ],
        provenance=[
            "beta, sigma, gamma, and initial compartments are teaching defaults",
        ])


# ---------------------------------------------------------------------------
# 3. Stochastic: Gillespie SSA (exact, single-trajectory and ensemble)
# ---------------------------------------------------------------------------

def fig_gillespie() -> None:
    a0, k, end = 100, 1.0, 5.0

    single = te.simulate_gillespie_ssa(a0=a0, k=k, end=end, seed=42)
    t_single = arr(single, "time")
    a_single = arr(single, "a")

    reps = te.simulate_gillespie_ssa_replicates(a0=a0, k=k, end=end,
                                                n_replicates=500, seed=7)
    t_rep = arr(reps, "time")
    mean_a = arr(reps, "mean_a")
    mean_b = arr(reps, "mean_b")

    # Deterministic reference a(t) = a0 e^{-kt}, b(t) = a0(1 - e^{-kt})
    t_theory = np.linspace(0, end, 300)
    a_theory = a0 * np.exp(-k * t_theory)
    b_theory = a0 * (1 - np.exp(-k * t_theory))

    # Empirical SD of the ensemble from the per-replicate endpoint spread
    final_as = np.asarray([row[0] for row in (reps.replicate_data or [])])
    sd_final = np.std(final_as)
    theory_sd_final = math.sqrt(a0 * (1 - math.exp(-k * end)))

    fig, axes = plt.subplots(1, 3, figsize=(13, 4.4))

    axes[0].step(t_single, a_single, where="post", color=PALETTE[0], lw=1.2,
                 label="SSA trajectory (seed 42)")
    axes[0].plot(t_theory, a_theory, color=PALETTE[1], lw=2, ls="--",
                 label=r"$a_0 e^{-kt}$")
    axes[0].set_xlabel("time")
    axes[0].set_ylabel("molecules A")
    axes[0].set_title("Exact SSA single trajectory vs closed form")
    axes[0].legend(loc="center right")

    axes[1].plot(t_rep, mean_a, color=PALETTE[0], lw=2,
                 label=r"$\bar a(t)$, 500 replicates")
    axes[1].plot(t_theory, a_theory, color=PALETTE[1], lw=1.5, ls="--",
                 label=r"$a_0 e^{-kt}$")
    axes[1].fill_between(t_theory, a_theory - 2 * np.sqrt(a_theory),
                         a_theory + 2 * np.sqrt(a_theory), color=PALETTE[1],
                         alpha=0.12, label=r"$\pm 2\sqrt{\mathrm{Var}}$")
    axes[1].set_xlabel("time")
    axes[1].set_ylabel("molecules A")
    axes[1].set_title("Ensemble mean tracks the deterministic mean")
    axes[1].legend(loc="center right")

    axes[2].hist(final_as, bins=30, color=PALETTE[4], alpha=0.85)
    axes[2].axvline(a_theory[-1], color=PALETTE[1], lw=2, ls="--",
                    label=rf"$E[a_{{T}}]={a_theory[-1]:.1f}$")
    axes[2].set_xlabel("final A count")
    axes[2].set_ylabel("replicates")
    axes[2].set_title(
        rf"Endpoint distribution: SD={sd_final:.2f} vs "
        rf"theory={theory_sd_final:.2f}")
    axes[2].legend(loc="upper left")

    fig.suptitle("Stochastic — Gillespie exact SSA (first-order decay)", y=1.03)
    finalize(
        fig, "05_gillespie_ssa.png",
        refs=[
            "Gillespie, D. T. (1976) A general method for numerically "
            "simulating the stochastic time evolution of coupled chemical "
            "reactions. J. Comput. Phys. 22, 403-434. "
            "doi:10.1016/0021-9991(76)90041-3",
            "Gillespie, D. T. (1977) Exact stochastic simulation of coupled "
            "chemical reactions. J. Phys. Chem. 81, 2340-2361. "
            "doi:10.1021/j100540a008",
        ],
        provenance=[
            "a0 = 100, k = 1.0, 500 replicates, and seeds are teaching/default "
            "choices",
        ])


# ---------------------------------------------------------------------------
# 4. Population genetics: Wright-Fisher drift + selection + LD
# ---------------------------------------------------------------------------

def fig_wright_fisher() -> None:
    n, p0, gens, reps = 100, 0.5, 200, 60

    wf = te.simulate_wright_fisher(population_size=n, starting_frequency=p0,
                                   generations=gens, replicate_runs=reps,
                                   return_replicate_data=True, seed=11)
    g = arr(wf, "generation")
    h = arr(wf, "heterozygosity")
    h_se = arr(wf, "heterozygosity_se")
    h_theory = np.asarray(wf.theoretical_heterozygosity())

    # raw per-replicate trajectories for the "spaghetti" panel
    rep_rows = np.asarray(wf.replicate_data) if wf.replicate_data else None
    rep_gens = rep_rows[:, 0]
    rep_freqs = rep_rows[:, 1:]

    # selection contrast: deterministic closed form p0/(p0+(1-p0)(1+s)^-t)
    wf_sel = te.simulate_wright_fisher(population_size=n, starting_frequency=p0,
                                       generations=150, replicate_runs=reps,
                                       selection_coefficient=0.08, seed=13)
    g_sel = arr(wf_sel, "generation")
    freq_sel = arr(wf_sel, "mean_frequency")
    freq_sel_se = arr(wf_sel, "mean_frequency_se")
    freq_theory = np.asarray(wf_sel.theoretical_frequency())

    fig = plt.figure(figsize=(13, 8.6))
    gs = fig.add_gridspec(2, 3)

    ax = fig.add_subplot(gs[0, 0])
    for j in range(min(20, rep_freqs.shape[1])):
        ax.plot(rep_gens, rep_freqs[:, j], lw=0.5, alpha=0.4, color=PALETTE[0])
    ax.axhline(p0, color="0.2", lw=1, ls=":")
    ax.set_xlabel("generation")
    ax.set_ylabel("allele A frequency")
    ax.set_title("Drift trajectories (per replicate)")
    ax.set_ylim(0, 1)

    ax = fig.add_subplot(gs[0, 1])
    ax.plot(g, h, color=PALETTE[0], lw=2, label="simulated $H_t$")
    ax.fill_between(g, h - 2 * h_se, h + 2 * h_se, color=PALETTE[0], alpha=0.15,
                    label=r"$\pm 2$ SE")
    ax.plot(g, h_theory, color=PALETTE[1], lw=1.5, ls="--",
            label=r"$H_0(1-1/2N)^t$")
    ax.set_xlabel("generation")
    ax.set_ylabel("heterozygosity")
    ax.set_title(rf"Heterozygosity decay, $N={n}$")
    ax.legend(loc="upper right")

    ax = fig.add_subplot(gs[0, 2])
    edges = np.linspace(0, 1, 21)
    hist, _ = np.histogram(rep_freqs[-1, :], bins=edges)
    ax.bar(edges[:-1], hist, width=1 / 20 * 0.9, color=PALETTE[4], alpha=0.85)
    ax.set_xlabel("final allele frequency")
    ax.set_ylabel("replicates")
    ax.set_title("Allele-frequency spectrum at absorption/final generation")

    ax = fig.add_subplot(gs[1, 0])
    ax.plot(g_sel, freq_sel, color=PALETTE[0], lw=2, label="simulated")
    ax.fill_between(g_sel, freq_sel - 2 * freq_sel_se,
                    freq_sel + 2 * freq_sel_se, color=PALETTE[0], alpha=0.15)
    ax.plot(g_sel, freq_theory, color=PALETTE[1], lw=1.5, ls="--",
            label=r"$p_0/(p_0+(1-p_0)(1+s)^{-t})$")
    ax.set_xlabel("generation")
    ax.set_ylabel("allele A frequency")
    ax.set_title("Selection ($s=0.08$) vs deterministic closed form")
    ax.legend(loc="center right")
    ax.set_ylim(0, 1)

    ax = fig.add_subplot(gs[1, 1])
    r_rate = 0.1
    d0 = 0.25 * 0.25
    ld = te.simulate_two_locus_wright_fisher(
        population_size=100, generations=200, recombination_rate=r_rate,
        starting_frequencies=(0.25, 0.25, 0.25, 0.25), replicate_runs=30, seed=5)
    g_ld = arr(ld, "generation")
    d_sim = arr(ld, "mean_D")
    sd_d = arr(ld, "sd_D")
    d_theory = np.asarray([
        te.theoretical_ld_decay(d_initial=d0, recombination_rate=r_rate,
                                generations=int(g), population_size=100)
        for g in g_ld])
    ax.plot(g_ld, d_sim, color=PALETTE[0], lw=2, label="simulated $D_t$")
    ax.fill_between(g_ld, d_sim - 2 * sd_d, d_sim + 2 * sd_d, color=PALETTE[0],
                    alpha=0.15)
    ax.plot(g_ld, d_theory, color=PALETTE[1], lw=1.5, ls="--",
            label=r"$D_0(1-r)^t$")
    ax.set_xlabel("generation")
    ax.set_ylabel(r"linkage disequilibrium $D$")
    ax.set_title("Linkage disequilibrium decay")
    ax.legend(loc="upper right")

    ax = fig.add_subplot(gs[1, 2])
    s_values = [-0.1, -0.02, 0.0, 0.02, 0.1]
    p_test = np.linspace(0.01, 0.99, 50)
    for s in s_values:
        probs = [te.kimura_fixation_probability(p, s, n) for p in p_test]
        ax.plot(p_test, probs, lw=1.8, label=rf"$s={s:+.2f}$")
    ax.plot(p_test, p_test, color="0.3", lw=0.8, ls=":", label="$p$ (neutral)")
    ax.set_xlabel(r"starting frequency $p_0$")
    ax.set_ylabel(r"fixation probability")
    ax.set_title(rf"Kimura fixation probability, $N={n}$")
    ax.legend(loc="upper left")

    fig.suptitle("Population genetics — Wright–Fisher", y=1.01)
    finalize(
        fig, "06_wright_fisher.png",
        refs=[
            "Wright, S. (1931) Evolution in Mendelian populations. "
            "Genetics 16, 97-159. doi:10.1093/genetics/16.2.97",
            "Kimura, M. (1962) On the probability of fixation of mutant genes "
            "in a population. Genetics 47, 713-719. doi:10.1093/genetics/47.6.713",
            "Lewontin, R. C. & Kojima, K. (1960) The evolutionary dynamics of "
            "complex polymorphisms. Evolution 14, 458-472. "
            "doi:10.1111/j.1558-5646.1960.tb03113.x",
        ],
        provenance=[
            "N = 100, p0 = 0.5, s = 0.08, r = 0.1, 30-60 replicates are "
            "teaching defaults",
        ])


# ---------------------------------------------------------------------------
# 5. Discrete: PCR and Monte Carlo
# ---------------------------------------------------------------------------

def fig_pcr() -> None:
    n0, eff = 100.0, 0.9
    cycles = 30

    exp = te.simulate_pcr(n0=n0, efficiency=eff, cycles=cycles)
    plat = te.simulate_pcr(n0=n0, efficiency=eff, cycles=cycles,
                           plateau_capacity=1e6)
    c = arr(exp, "cycle")
    copies_exp = arr(exp, "copies")
    copies_plat = arr(plat, "copies")
    closed = n0 * (1 + eff) ** c

    fig, axes = plt.subplots(1, 2, figsize=(10.5, 3.8))

    axes[0].plot(c, copies_exp, "o-", color=PALETTE[0], ms=3, lw=1.2,
                 label=r"engine $N_c$")
    axes[0].plot(c, closed, color=PALETTE[1], lw=1.5, ls="--",
                 label=r"$N_0(1+\varepsilon)^c$")
    axes[0].set_yscale("log")
    axes[0].set_xlabel("cycle")
    axes[0].set_ylabel("copy number (log)")
    axes[0].set_title(rf"Ideal amplification, $\varepsilon={eff}$")
    axes[0].legend(loc="upper left")

    axes[1].plot(c, copies_plat, "o-", color=PALETTE[2], ms=3, lw=1.2,
                 label="engine (logistic plateau)")
    axes[1].axhline(1e6, color="0.3", lw=0.8, ls=":", label="capacity $=10^6$")
    axes[1].set_yscale("log")
    axes[1].set_xlabel("cycle")
    axes[1].set_ylabel("copy number (log)")
    axes[1].set_title("Plateau from reagent exhaustion (logistic term)")
    axes[1].legend(loc="upper left")

    fig.suptitle("Discrete — PCR amplification", y=1.03)
    finalize(
        fig, "07_pcr.png",
        refs=[
            "Saiki, R. K. et al. (1985) Enzymatic amplification of "
            "beta-globin genomic sequences and restriction site analysis for "
            "diagnosis of sickle cell anemia. Science 230, 1350-1354. "
            "doi:10.1126/science.2999980",
        ],
        provenance=[
            "n0 = 100, efficiency = 0.9, and plateau capacity 1e6 are "
            "teaching defaults",
        ])


def fig_monte_carlo() -> None:
    n = 200_000
    mc = te.simulate_monte_carlo_pi(n_samples=n, seed=42)
    sample_n = arr(mc, "n")
    est = arr(mc, "estimate")
    se = arr(mc, "se")

    # theoretical 1/sqrt(N) convergence band around pi
    n_theory = np.logspace(1, math.log10(n), 200)
    se_theory = 4 * np.sqrt(0.25 * 0.75 / n_theory)  # worst-case p=0.5

    fig, axes = plt.subplots(1, 2, figsize=(10.5, 3.8))

    axes[0].plot(sample_n, est, color=PALETTE[0], lw=1.5,
                 label="running estimate")
    axes[0].fill_between(sample_n, est - se, est + se, color=PALETTE[0],
                         alpha=0.15, label=r"$\hat\pi \pm$ SE")
    axes[0].axhline(math.pi, color=PALETTE[1], lw=1.8, ls="--", label=r"$\pi$")
    axes[0].set_xscale("log")
    axes[0].set_xlabel("samples drawn")
    axes[0].set_ylabel(r"$\hat\pi$")
    axes[0].set_title("Convergence of Monte Carlo estimate")
    axes[0].legend(loc="upper right")

    err = np.abs(est - math.pi)
    axes[1].loglog(sample_n, np.maximum(err, 1e-9), color=PALETTE[0], lw=1.5,
                   label=r"$|\hat\pi - \pi|$")
    axes[1].loglog(n_theory, 1.96 * se_theory, color=PALETTE[1], lw=1.5,
                   ls="--", label=r"$1.96\,{\rm SE}$ (95% band)")
    axes[1].loglog(n_theory, 4 / np.sqrt(n_theory), color=PALETTE[3], lw=1.2,
                   ls=":", label=r"$C/\sqrt{N}$")
    axes[1].set_xlabel("samples drawn")
    axes[1].set_ylabel("error")
    axes[1].set_title(r"$1/\sqrt{N}$ convergence")

    axes[1].legend(loc="lower left")

    fig.suptitle("Discrete — Monte Carlo estimate of $\\pi$", y=1.03)
    finalize(
        fig, "08_monte_carlo.png",
        refs=[
            "Metropolis, N. & Ulam, S. (1949) The Monte Carlo method. "
            "J. Am. Stat. Assoc. 44, 335-341. doi:10.1080/01621459.1949.10483310",
        ],
        provenance=[
            "n = 200,000 samples and seed 42 are teaching/default choices",
        ])


# ---------------------------------------------------------------------------
# 6. Molecular dynamics: energy conservation
# ---------------------------------------------------------------------------

def fig_md() -> None:
    res = te.simulate_molecular_dynamics(n_particles=64, temperature=0.3,
                                         timestep=0.005, n_steps=600, seed=42)
    t = arr(res, "time")
    etot = arr(res, "total_energy")
    ekin = arr(res, "kinetic_energy")
    epot = arr(res, "potential_energy")
    mom = arr(res, "total_momentum_magnitude")

    drift = np.max(np.abs(etot - etot[0])) / abs(etot[0])

    fig, axes = plt.subplots(1, 3, figsize=(13, 4.4))

    axes[0].plot(t, etot, color=PALETTE[0], lw=2, label="$E_{tot}$")
    axes[0].plot(t, ekin, color=PALETTE[1], lw=1.2, label="$E_{kin}$")
    axes[0].plot(t, epot, color=PALETTE[2], lw=1.2, label="$E_{pot}$")
    axes[0].set_xlabel("time (reduced)")
    axes[0].set_ylabel("energy")
    axes[0].set_title(rf"NVE: $E_{{\rm tot}}$ drift = {drift:.1e}")
    axes[0].legend(loc="center right")

    axes[1].plot(t, etot - etot[0], color=PALETTE[0], lw=1.5)
    axes[1].axhline(0, color="0.3", lw=0.8)
    axes[1].set_xlabel("time (reduced)")
    axes[1].set_ylabel(r"$\Delta E_{tot}$")
    axes[1].set_title("Energy conservation residual (velocity Verlet)")

    axes[2].plot(t, mom, color=PALETTE[4], lw=1.5)
    axes[2].set_xlabel("time (reduced)")
    axes[2].set_ylabel(r"$|P_{tot}|$")
    axes[2].set_title(rf"Momentum conservation, max $|P|$ = {mom.max():.2e}")

    fig.suptitle("Molecular dynamics — Lennard-Jones cluster (NVE)", y=1.03)
    finalize(
        fig, "09_molecular_dynamics.png",
        refs=[
            "Verlet, L. (1967) Computer experiments on classical fluids. I. "
            "Thermodynamical properties of Lennard-Jones molecules. "
            "Phys. Rev. 159, 98-103. doi:10.1103/PhysRev.159.98",
            "Jones, J. E. (1924) On the determination of molecular fields. II. "
            "From the equation of state of a gas. Proc. R. Soc. A 106, 463-477. "
            "doi:10.1098/rspa.1924.0082",
        ],
        provenance=[
            "N = 64, T = 0.3, dt = 0.005, 600 steps (Lennard-Jones reduced "
            "units) are teaching defaults",
        ])


# ---------------------------------------------------------------------------
# 7. Benchmark performance from benchmark_results.json
# ---------------------------------------------------------------------------

def fig_benchmarks() -> None:
    path = _REPO / "benchmark_results" / "benchmark_results.json"
    with open(path) as fh:
        data = json.load(fh)

    domains = sorted({row["domain"] for row in data})
    sizes = ["small", "medium", "large"]
    means = {
        size: {row["domain"]: row["mean_time_s"] for row in data
               if row["problem_size"] == size}
        for size in sizes
    }

    domain_labels = {
        "michaelis_menten": "Michaelis–Menten",
        "competitive_inhibition": "Comp. inhibition",
        "sir": "SIR",
        "seir": "SEIR",
        "gillespie_ssa": "SSA 1st-order",
        "gillespie_ssa_bimolecular": "SSA bimolecular",
        "gillespie_ssa_replicates": "SSA replicates",
        "monte_carlo_pi": "Monte Carlo $\\pi$",
        "molecular_dynamics": "Molecular dynamics",
        "pcr": "PCR",
        "wright_fisher": "Wright–Fisher",
    }

    x = np.arange(len(domains))
    width = 0.26

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))

    colors = {s: c for s, c in zip(sizes, [PALETTE[0], PALETTE[3], PALETTE[1]])}
    for j, size in enumerate(sizes):
        vals = [means[size].get(d, np.nan) for d in domains]
        axes[0].bar(x + (j - 1) * width, vals, width, label=size.title(),
                    color=colors[size], alpha=0.9)
    axes[0].set_yscale("log")
    axes[0].set_xticks(x)
    axes[0].set_xticklabels([domain_labels.get(d, d) for d in domains],
                            rotation=35, ha="right", fontsize=7.5)
    axes[0].set_ylabel("mean wall time (s, log)")
    axes[0].set_title("Benchmark wall time by domain and problem size")
    axes[0].legend(loc="upper left")

    ratios = []
    labels = []
    for d in domains:
        if d in means["small"] and d in means["large"]:
            ratios.append(means["large"][d] / max(means["small"][d], 1e-12))
            labels.append(domain_labels.get(d, d))
    order = np.argsort(ratios)
    axes[1].barh([labels[i] for i in order], [ratios[i] for i in order],
                 color=PALETTE[4], alpha=0.9)
    axes[1].set_xscale("log")
    axes[1].set_xlabel("large / small wall-time ratio (log)")
    axes[1].set_title("Scaling sensitivity (largest → smallest ratio)")
    axes[1].grid(axis="x", alpha=0.3)

    fig.suptitle("Benchmarks — wall time by domain and problem size", y=1.02)
    finalize(
        fig, "10_benchmarks.png",
        refs=[],
        provenance=[
            "Internal benchmark measurement (benchmark_results.json); wall "
            "time is an implementation artifact, not a modeled quantity",
        ])


# ---------------------------------------------------------------------------

def main() -> None:
    print("Generating Caterva figure suite ->", FIGS)
    fig_michaelis_menten()
    fig_competitive_inhibition()
    fig_sir()
    fig_seir()
    fig_gillespie()
    fig_wright_fisher()
    fig_pcr()
    fig_monte_carlo()
    fig_md()
    fig_benchmarks()
    print(f"Done. {len(list(FIGS.glob('*.png')))} figures in {FIGS}")


if __name__ == "__main__":
    main()
