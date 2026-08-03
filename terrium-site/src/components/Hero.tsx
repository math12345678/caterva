/**
 * Opening. Restrained on purpose — the lattice behind it is already moving,
 * and the console below is already doing something real, so this does not
 * need to shout.
 */

import { useCountUp, useReducedMotion, useTypewriter } from '../lib/motion';
import { useEffect, useState } from 'react';

const WORDS = ['exact mathematics.', 'a closed form.', 'a 1971 paper.', 'a second model.'];

export default function Hero() {
  const reduced = useReducedMotion();
  const [i, setI] = useState(0);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const t = window.setTimeout(() => setMounted(true), 60);
    return () => window.clearTimeout(t);
  }, []);

  const { shown, done } = useTypewriter(WORDS[i], mounted, 26, 400);

  useEffect(() => {
    if (!done || reduced) return;
    const t = window.setTimeout(() => setI((v) => (v + 1) % WORDS.length), 2100);
    return () => window.clearTimeout(t);
  }, [done, i, reduced]);

  const claims = useCountUp(8, mounted, 1400);
  const domains = useCountUp(6, mounted, 1100);

  const rise = (delay: number) => ({
    opacity: mounted ? 1 : 0,
    transform: mounted ? 'none' : 'translateY(14px)',
    transition: `opacity 900ms cubic-bezier(0.16,1,0.3,1) ${delay}ms, transform 900ms cubic-bezier(0.16,1,0.3,1) ${delay}ms`,
  });

  return (
    <header className="relative z-10 mx-auto flex min-h-[86vh] max-w-[1140px] flex-col justify-center px-6 pb-16 pt-28">
      <div style={rise(0)} className="flex items-center gap-3">
        <span className="relative flex h-1.5 w-1.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-verified opacity-60" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-verified" />
        </span>
        <span className="font-mono text-[10px] tracking-[0.2em] text-faint">
          SCIENTIFIC VERIFICATION ENGINE
        </span>
      </div>

      <h1
        style={rise(90)}
        className="mt-7 max-w-[19ch] font-sans text-[clamp(38px,6.4vw,72px)] font-medium leading-[1.02] tracking-[-0.038em] text-ink"
      >
        Every number,
        <br />
        checked against
      </h1>

      <div
        style={rise(150)}
        className="mt-1 h-[clamp(46px,7.2vw,84px)] font-sans text-[clamp(38px,6.4vw,72px)] font-medium leading-[1.02] tracking-[-0.038em] text-verified"
      >
        {shown}
        <span className="ml-0.5 inline-block w-[3px] translate-y-[-2px] animate-pulse bg-verified align-middle" style={{ height: '0.78em' }} />
      </div>

      <p
        style={rise(230)}
        className="mt-8 max-w-[58ch] font-sans text-[16px] leading-[1.65] text-dim"
      >
        Terrium resolves real parameters from published literature, runs the
        simulation, and shows its work. Built by two AI models working from
        identical specifications — and neither of them is trusted until a third
        reproduces the result.
      </p>

      <div style={rise(310)} className="mt-9 flex flex-wrap items-center gap-3">
        <a
          href="#request"
          className="group relative overflow-hidden rounded-md bg-verified px-5 py-2.5 font-mono text-[13px] font-medium text-void transition-transform duration-300 hover:scale-[1.02]"
        >
          <span className="relative z-10">Request access</span>
          <span className="absolute inset-0 -translate-x-full bg-white/25 transition-transform duration-500 group-hover:translate-x-full" />
        </a>
        <a
          href="#shell"
          className="rounded-md border border-line px-5 py-2.5 font-mono text-[13px] text-dim transition-colors duration-300 hover:border-verified/40 hover:text-ink"
        >
          Open the shell
        </a>
      </div>

      <div
        style={rise(390)}
        className="mt-14 flex flex-wrap gap-x-10 gap-y-4 border-t border-line pt-6 font-mono text-[11px] text-faint"
      >
        <span>
          <span className="text-ink">{claims}</span> verified claims
        </span>
        <span>
          <span className="text-ink">{domains}</span> simulation domains
        </span>
        <span>
          <span className="text-ink">2</span> independent implementers
        </span>
        <span className="text-verified/70">every mutation reproduced before it counts</span>
      </div>
    </header>
  );
}
