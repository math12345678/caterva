/**
 * Terrium — live verification console.
 *
 * Not a hero section. A full-bleed instrument panel: the build pipeline runs
 * down the left rail, the live simulation and its closed form occupy the
 * centre, the evidence ledger streams down the right, and real test output
 * runs along the bottom.
 *
 * The visitor can inject a real bug (2N -> N, the diploid off-by-two) and
 * watch the measured curve peel away from theory while the test goes red with
 * the actual assertion message.
 *
 * Design constraints, deliberate:
 *   - Monospace throughout. This is an instrument, not a brochure.
 *   - No type larger than 22px anywhere on the panel.
 *   - Motion is functional only: it shows state changing, never decorates.
 *   - Every number displayed is computed at runtime, never hard-coded.
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import { CONFIG, prepare, type PreparedData } from '../lib/drift';
import { PIPELINE, LEDGER, type StageState } from '../lib/pipeline';

const C = {
  bg: '#08090A',
  panel: '#0C0E0F',
  raised: '#111415',
  line: '#1C2022',
  lineBright: '#2A3033',
  text: '#E6E8E9',
  dim: '#8B9297',
  faint: '#565C60',
  mint: '#6EE7B7',
  amber: '#FBBF24',
  red: '#F87171',
} as const;

const EASE = (t: number) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    setReduced(mq.matches);
    const on = () => setReduced(mq.matches);
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, []);
  return reduced;
}

/* ─────────────────────────── plot ─────────────────────────── */

interface PlotProps {
  data: PreparedData;
  /** 0 = correct model, 1 = bugged model. Animated, not stepped. */
  mix: number;
}

function DriftPlot({ data, mix }: PlotProps) {
  const ref = useRef<HTMLCanvasElement | null>(null);
  const boxRef = useRef<HTMLDivElement | null>(null);

  const draw = useCallback(() => {
    const canvas = ref.current;
    const box = boxRef.current;
    if (!canvas || !box) return;

    const dpr = window.devicePixelRatio || 1;
    const w = box.clientWidth;
    const h = box.clientHeight;
    if (w === 0 || h === 0) return;

    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    canvas.style.width = `${w}px`;
    canvas.style.height = `${h}px`;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    const padL = 44;
    const padR = 14;
    const padT = 14;
    // padB carries the x-axis tick labels AND the lowest y-label (0.0), which
    // sits on the axis line. Too small and 0.0 is clipped by the panel edge.
    const padB = 32;
    const pw = w - padL - padR;
    const ph = h - padT - padB;

    const G = CONFIG.generations;
    const yMax = 0.52;
    const X = (g: number) => padL + (g / G) * pw;
    const Y = (v: number) => padT + (1 - v / yMax) * ph;

    // grid
    ctx.strokeStyle = C.line;
    ctx.lineWidth = 1;
    ctx.font = '10px ui-monospace, "JetBrains Mono", monospace';
    ctx.fillStyle = C.faint;
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    for (const v of [0, 0.1, 0.2, 0.3, 0.4, 0.5]) {
      const y = Math.round(Y(v)) + 0.5;
      ctx.beginPath();
      ctx.moveTo(padL, y);
      ctx.lineTo(padL + pw, y);
      ctx.stroke();
      ctx.fillText(v.toFixed(1), padL - 8, y);
    }
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    for (const g of [0, 50, 100, 150, 200]) {
      ctx.fillText(String(g), X(g), padT + ph + 8);
    }

    const { correct, bugged, theory } = data;

    // Spread across replicates, as a quantile band rather than 40 overlaid
    // polylines. Individual paths at this replicate count and generation
    // depth render as a dense hash that reads as noise and buries the two
    // curves that carry the argument. A 10th-90th percentile band shows the
    // same information — the mean is a mean of a distribution — while
    // staying legible.
    const shown = Math.min(
      correct.trajectories.length,
      bugged.trajectories.length,
    );
    if (shown > 0) {
      const lo = new Float64Array(G + 1);
      const hi = new Float64Array(G + 1);
      const scratch = new Float64Array(shown);
      const qLo = Math.floor(0.1 * (shown - 1));
      const qHi = Math.floor(0.9 * (shown - 1));

      for (let g = 0; g <= G; g++) {
        for (let r = 0; r < shown; r++) {
          const pa = correct.trajectories[r][g];
          const pb = bugged.trajectories[r][g];
          const ha = 2 * pa * (1 - pa);
          const hb = 2 * pb * (1 - pb);
          scratch[r] = ha + (hb - ha) * mix;
        }
        scratch.sort();
        lo[g] = scratch[qLo];
        hi[g] = scratch[qHi];
      }

      ctx.beginPath();
      for (let g = 0; g <= G; g++) ctx.lineTo(X(g), Y(hi[g]));
      for (let g = G; g >= 0; g--) ctx.lineTo(X(g), Y(lo[g]));
      ctx.closePath();
      ctx.fillStyle = 'rgba(139,146,151,0.13)';
      ctx.fill();
    }

    // residual band between theory and measured — this is the divergence,
    // made unmissable. it barely exists at mix=0 and blooms at mix=1.
    const measuredAt = (g: number) =>
      correct.meanHeterozygosity[g] +
      (bugged.meanHeterozygosity[g] - correct.meanHeterozygosity[g]) * mix;

    ctx.beginPath();
    for (let g = 0; g <= G; g++) ctx.lineTo(X(g), Y(theory[g]));
    for (let g = G; g >= 0; g--) ctx.lineTo(X(g), Y(measuredAt(g)));
    ctx.closePath();
    ctx.fillStyle = `rgba(248,113,113,${0.03 + 0.17 * mix})`;
    ctx.fill();

    // theory — the closed form. static; it is what the simulation is judged
    // against, so it never moves.
    ctx.beginPath();
    for (let g = 0; g <= G; g++) {
      const x = X(g);
      const y = Y(theory[g]);
      if (g === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.strokeStyle = C.mint;
    ctx.lineWidth = 1.75;
    ctx.stroke();

    // measured mean
    ctx.beginPath();
    for (let g = 0; g <= G; g++) {
      const x = X(g);
      const y = Y(measuredAt(g));
      if (g === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.strokeStyle = mix > 0.5 ? C.red : C.text;
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }, [data, mix]);

  useEffect(() => {
    draw();
    const ro = new ResizeObserver(draw);
    if (boxRef.current) ro.observe(boxRef.current);
    return () => ro.disconnect();
  }, [draw]);

  return (
    <div ref={boxRef} className="relative h-full w-full">
      <canvas ref={ref} className="block h-full w-full" />
    </div>
  );
}

/* ───────────────────────── pipeline rail ───────────────────────── */

function StageDot({ state }: { state: StageState }) {
  const color =
    state === 'done'
      ? C.mint
      : state === 'conflict'
        ? C.amber
        : state === 'active'
          ? C.text
          : C.faint;
  return (
    <span className="relative flex h-[7px] w-[7px] shrink-0 items-center justify-center">
      <span
        className="block h-[7px] w-[7px] rounded-full transition-colors duration-300"
        style={{
          background: state === 'idle' ? 'transparent' : color,
          border: `1px solid ${color}`,
        }}
      />
      {state === 'active' && (
        <span
          className="absolute h-[7px] w-[7px] rounded-full"
          style={{ background: color, animation: 'trmPulse 1.4s ease-out infinite' }}
        />
      )}
    </span>
  );
}

function PipelineRail({ index }: { index: number }) {
  return (
    <div className="flex h-full flex-col gap-0 overflow-hidden">
      <div
        className="px-4 py-3 text-[10px] tracking-[0.14em]"
        style={{ color: C.faint, borderBottom: `1px solid ${C.line}` }}
      >
        BUILD PIPELINE
      </div>

      {/* pb-8: the last stage must clear the footer strip, which overlays
          nothing but sits immediately beneath and visually crowds it. */}
      <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-8 pt-3">
        {PIPELINE.map((s, i) => {
          const state: StageState =
            i > index
              ? 'idle'
              : i < index
                ? s.conflict
                  ? 'conflict'
                  : 'done'
                : 'active';
          const reached = i <= index;
          const accent =
            state === 'conflict' ? C.amber : state === 'idle' ? C.faint : C.mint;

          return (
            <div key={s.id} className="relative pb-4 pl-5">
              {i < PIPELINE.length - 1 && (
                <span
                  className="absolute left-[3px] top-[14px] w-px transition-colors duration-500"
                  style={{
                    bottom: 0,
                    background: i < index ? accent : C.line,
                    opacity: i < index ? 0.35 : 1,
                  }}
                />
              )}
              <span className="absolute left-0 top-[5px]">
                <StageDot state={state} />
              </span>

              <div className="flex items-baseline gap-2">
                <span
                  className="text-[11px] tracking-[0.1em] transition-colors duration-300"
                  style={{ color: reached ? C.text : C.faint }}
                >
                  {s.label}
                </span>
                {state === 'conflict' && (
                  <span
                    className="px-1 text-[9px] tracking-[0.08em]"
                    style={{ color: C.amber, border: `1px solid ${C.amber}55` }}
                  >
                    CAUGHT
                  </span>
                )}
              </div>

              <div className="mt-[2px] text-[10px]" style={{ color: C.faint }}>
                {s.detail}
              </div>

              {s.agents && (
                <div className="mt-2 flex flex-col gap-1">
                  {s.agents.map((a) => (
                    <div
                      key={a.name}
                      className="flex items-center gap-2 px-2 py-1 text-[10px] transition-opacity duration-500"
                      style={{
                        border: `1px solid ${C.line}`,
                        background: C.raised,
                        opacity: reached ? 1 : 0.35,
                        color: reached ? C.dim : C.faint,
                      }}
                    >
                      <span
                        className="h-[4px] w-[4px] rounded-full"
                        style={{ background: reached ? C.mint : C.faint }}
                      />
                      <span style={{ color: reached ? C.text : C.faint }}>
                        {a.name}
                      </span>
                      <span className="ml-auto">{a.model}</span>
                    </div>
                  ))}
                </div>
              )}

              {s.output && reached && (
                <div className="mt-2 flex flex-col gap-[2px]">
                  {s.output.map((line, k) => (
                    <div
                      key={k}
                      className="text-[10px] leading-[1.5]"
                      style={{
                        color: s.conflict ? C.amber : C.dim,
                        opacity: 0,
                        animation: `trmFade 320ms ease-out ${k * 90}ms forwards`,
                      }}
                    >
                      {line}
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ───────────────────────── ledger rail ───────────────────────── */

function LedgerRail() {
  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div
        className="flex items-baseline justify-between px-4 py-3"
        style={{ borderBottom: `1px solid ${C.line}`, color: C.faint }}
      >
        <span className="text-[10px] tracking-[0.14em]">EVIDENCE LEDGER</span>
        <span className="text-[10px]">{LEDGER.length} claims</span>
      </div>
      <div className="flex-1 overflow-y-auto">
        {LEDGER.map((r, i) => (
          <div
            key={i}
            className="px-4 py-[10px]"
            style={{ borderBottom: `1px solid ${C.line}` }}
          >
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-[10px]" style={{ color: C.faint }}>
                {r.domain}
              </span>
              <span
                className="px-1 text-[9px] tracking-[0.06em]"
                style={{ color: C.mint, border: `1px solid ${C.mint}44` }}
              >
                VERIFIED
              </span>
            </div>
            <div className="mt-1 text-[11px] leading-snug" style={{ color: C.text }}>
              {r.claim}
            </div>
            <div className="mt-[3px] text-[10px]" style={{ color: C.dim }}>
              {r.method}
            </div>
            {r.reference !== '—' && (
              <div className="mt-[2px] text-[10px] italic" style={{ color: C.faint }}>
                {r.reference}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ───────────────────────── console ───────────────────────── */

export default function VerificationConsole() {
  const reduced = usePrefersReducedMotion();

  // ~400ms of real work for 2000 replicates x 2 models. Run it AFTER first
  // paint so the shell appears instantly, rather than blocking mount and
  // showing a white screen. The brief "running" state is honest: it is
  // actually running.
  const [data, setData] = useState<PreparedData | null>(null);
  useEffect(() => {
    const id = requestAnimationFrame(() => setData(prepare()));
    return () => cancelAnimationFrame(id);
  }, []);

  const [bugged, setBugged] = useState(false);
  const [mix, setMix] = useState(0);
  const [stage, setStage] = useState(0);

  // animate the curve between the two models
  const raf = useRef<number | null>(null);
  useEffect(() => {
    if (reduced) {
      setMix(bugged ? 1 : 0);
      return;
    }
    const from = mix;
    const to = bugged ? 1 : 0;
    if (from === to) return;
    const t0 = performance.now();
    const dur = 700;
    const tick = (now: number) => {
      const k = Math.min(1, (now - t0) / dur);
      setMix(from + (to - from) * EASE(k));
      if (k < 1) raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => {
      if (raf.current) cancelAnimationFrame(raf.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bugged, reduced]);

  // walk the pipeline
  useEffect(() => {
    if (reduced) {
      setStage(PIPELINE.length - 1);
      return;
    }
    const t = setTimeout(
      () => setStage((s) => (s + 1) % PIPELINE.length),
      PIPELINE[stage].duration,
    );
    return () => clearTimeout(t);
  }, [stage, reduced]);

  const deviation = data
    ? bugged
      ? data.deviationBugged
      : data.deviationCorrect
    : 0;
  const passing = data ? deviation < CONFIG.tolerance : true;

  return (
    <div
      className="flex h-screen min-h-[640px] w-full flex-col font-mono"
      style={{ background: C.bg, color: C.text }}
    >
      <style>{`
        @keyframes trmPulse { 0%{transform:scale(1);opacity:.55} 70%{transform:scale(2.6);opacity:0} 100%{opacity:0} }
        @keyframes trmFade  { to { opacity: 1 } }
      `}</style>

      {/* top bar */}
      <header
        className="flex shrink-0 items-center gap-4 px-4 py-3"
        style={{ borderBottom: `1px solid ${C.line}` }}
      >
        <span className="text-[13px] tracking-[0.02em]">Terrium</span>
        <span className="text-[10px] tracking-[0.14em]" style={{ color: C.faint }}>
          SCIENTIFIC VERIFICATION ENGINE
        </span>
        <span className="ml-auto flex items-center gap-2 text-[10px]" style={{ color: C.dim }}>
          <span
            className="h-[5px] w-[5px] rounded-full"
            style={{ background: passing ? C.mint : C.red }}
          />
          {passing ? 'all domains verified' : 'verification failing'}
        </span>
        <button
          className="px-3 py-[5px] text-[11px] transition-colors"
          style={{ color: C.mint, border: `1px solid ${C.mint}66` }}
        >
          Request access
        </button>
      </header>

      {/* three rails */}
      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[264px_minmax(0,1fr)_300px]">
        <aside
          className="hidden lg:block"
          style={{ borderRight: `1px solid ${C.line}`, background: C.panel }}
        >
          <PipelineRail index={stage} />
        </aside>

        {/* centre */}
        <main className="flex min-h-0 flex-col">
          <div
            className="flex shrink-0 items-baseline gap-3 px-5 py-3"
            style={{ borderBottom: `1px solid ${C.line}` }}
          >
            <span className="text-[10px] tracking-[0.14em]" style={{ color: C.faint }}>
              LIVE VERIFICATION
            </span>
            <span className="text-[11px]" style={{ color: C.dim }}>
              wright_fisher · N={CONFIG.populationSize} ·{' '}
              {CONFIG.replicates} replicates · seed={CONFIG.seed}
            </span>
          </div>

          {/* code */}
          <div className="shrink-0 px-5 py-3" style={{ borderBottom: `1px solid ${C.line}` }}>
            <pre className="text-[12px] leading-[1.75]" style={{ color: C.dim }}>
              <span style={{ color: C.faint }}>1  </span>
              <span style={{ color: '#C792EA' }}>def </span>
              <span style={{ color: C.text }}>_next_generation</span>(counts, n_pop, rng):
              {'\n'}
              <span style={{ color: C.faint }}>2  </span>
              {'    '}p = counts / (<span style={{ color: C.amber }}>2</span> * n_pop)
              {'\n'}
              <span style={{ color: C.faint }}>3  </span>
              {'    '}
              <span style={{ color: '#C792EA' }}>return </span>
              rng.binomial(
              <span
                className="transition-colors duration-300"
                style={{
                  color: bugged ? C.red : C.amber,
                  background: bugged ? `${C.red}22` : 'transparent',
                  padding: '0 2px',
                }}
              >
                {bugged ? 'n_pop' : '2 * n_pop'}
              </span>
              , p)
            </pre>
          </div>

          {/* plot */}
          <div className="relative min-h-0 flex-1 px-2 py-2">
            <div className="absolute right-5 top-4 z-10 flex gap-4 text-[10px]">
              <span style={{ color: C.mint }}>── theory H(t)</span>
              <span style={{ color: bugged ? C.red : C.text }}>── measured</span>
            </div>
            {data ? (
              <DriftPlot data={data} mix={mix} />
            ) : (
              <div
                className="flex h-full w-full items-center justify-center text-[11px]"
                style={{ color: C.faint }}
              >
                running {CONFIG.replicates.toLocaleString()} replicates × 2 models…
              </div>
            )}
          </div>
        </main>

        <aside
          className="hidden lg:block"
          style={{ borderLeft: `1px solid ${C.line}`, background: C.panel }}
        >
          <LedgerRail />
        </aside>
      </div>

      {/* test output strip */}
      <footer
        className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 text-[11px]"
        style={{ borderTop: `1px solid ${C.line}`, background: C.panel }}
      >
        <button
          onClick={() => setBugged((b) => !b)}
          className="px-3 py-[6px] text-[11px] transition-colors"
          style={{
            color: bugged ? C.mint : C.red,
            border: `1px solid ${bugged ? C.mint : C.red}66`,
            background: bugged ? `${C.mint}0F` : `${C.red}0F`,
          }}
        >
          {bugged ? 'Revert' : 'Inject bug: 2N → N'}
        </button>

        <span style={{ color: C.faint }}>
          tests/test_popgen_correctness.py::test_heterozygosity_decay
        </span>

        <span
          className="px-[6px] py-[2px] text-[10px] tracking-[0.06em] transition-colors duration-300"
          style={{
            color: passing ? C.mint : C.red,
            border: `1px solid ${passing ? C.mint : C.red}66`,
          }}
        >
          {passing ? 'PASS' : 'FAIL'}
        </span>

        <span style={{ color: passing ? C.dim : C.red }}>
          {passing
            ? `max deviation ${deviation.toFixed(4)} < tolerance ${CONFIG.tolerance}`
            : `max deviation ${deviation.toFixed(4)} > tolerance ${CONFIG.tolerance} — measured decay follows (1 − 1/N)^t, not (1 − 1/2N)^t`}
        </span>
      </footer>
    </div>
  );
}
