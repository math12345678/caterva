/**
 * Ledger, validation contract, constitution, self-audit, close.
 *
 * All share one reveal primitive so the page has a single motion language
 * rather than five competing ones.
 */

import type { ReactNode } from 'react';
import { LEDGER } from '../lib/pipeline';
import { useInView } from '../lib/motion';

function Reveal({
  children,
  delay = 0,
  className = '',
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
}) {
  const [ref, seen] = useInView<HTMLDivElement>();
  return (
    <div
      ref={ref}
      className={className}
      style={{
        opacity: seen ? 1 : 0,
        transform: seen ? 'none' : 'translateY(12px)',
        transition: `opacity 760ms cubic-bezier(0.16,1,0.3,1) ${delay}ms, transform 760ms cubic-bezier(0.16,1,0.3,1) ${delay}ms`,
      }}
    >
      {children}
    </div>
  );
}

function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <div className="font-mono text-[10px] tracking-[0.18em] text-faint">{children}</div>
  );
}

function Title({ children }: { children: ReactNode }) {
  return (
    <h2 className="mt-2 font-sans text-[26px] font-medium tracking-[-0.015em] text-ink">
      {children}
    </h2>
  );
}

/* ─────────────────────────── ledger ─────────────────────────── */

export function Ledger() {
  return (
    <section className="relative z-10 mx-auto max-w-[1140px] px-6 py-24">
      <Reveal>
        <Eyebrow>EVIDENCE LEDGER</Eyebrow>
        <Title>{LEDGER.length} claims, and where each one comes from.</Title>
        <p className="mt-2 max-w-[66ch] font-sans text-[14px] leading-relaxed text-dim">
          The rightmost column is the product. It is the difference between
          “our simulation says” and “this reproduces a result published in
          1962 that we did not produce.”
        </p>
      </Reveal>

      <Reveal delay={80} className="mt-8 overflow-x-auto">
        <table className="w-full min-w-[760px] border-collapse font-mono text-[12px]">
          <thead>
            <tr className="border-b border-lineBright text-left text-[10px] tracking-[0.12em] text-faint">
              <th className="py-2.5 pr-4 font-normal">DOMAIN</th>
              <th className="py-2.5 pr-4 font-normal">CLAIM</th>
              <th className="py-2.5 pr-4 font-normal">METHOD</th>
              <th className="py-2.5 pr-4 font-normal">REFERENCE</th>
              <th className="py-2.5 font-normal">STATUS</th>
            </tr>
          </thead>
          <tbody>
            {LEDGER.map((r, i) => (
              <tr
                key={i}
                className="group border-b border-line transition-colors duration-200 hover:bg-raised/50"
              >
                <td className="py-3 pr-4 align-top text-faint">{r.domain}</td>
                <td className="py-3 pr-4 align-top text-ink">{r.claim}</td>
                <td className="py-3 pr-4 align-top text-dim">{r.method}</td>
                <td className="py-3 pr-4 align-top italic text-faint transition-colors group-hover:text-dim">
                  {r.reference}
                </td>
                <td className="py-3 align-top">
                  <span className="whitespace-nowrap rounded-sm border border-verified/35 px-1.5 py-0.5 text-[9.5px] tracking-[0.06em] text-verified">
                    VERIFIED
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Reveal>
    </section>
  );
}

/* ──────────────────────── validation contract ──────────────────────── */

const STATES = [
  {
    // Was `Km = 0.12 mM` / `EC 1.1.1.27`. EC 1.1.1.27 is lactate
    // dehydrogenase, for which this product resolves Km = 10.73 mM -- and
    // reports it FLAGGED, not verified, because the source does not state
    // an assay temperature. So the VERIFIED example was a number the
    // product does not produce, for an enzyme it declines to call
    // verified.
    //
    // Replaced with a real one, measured 2026-09-05: hexokinase Km
    // resolves to 6 mM from BRENDA ref 641068 with citationStatus
    // "verified".
    tone: 'verified' as const,
    label: 'VERIFIED',
    value: 'Km = 6 mM',
    source: 'BRENDA ref 641068 · EC 2.7.1.1',
    note: 'checked against the source. the simulation runs.',
  },
  {
    tone: 'flagged' as const,
    label: 'FLAGGED',
    value: 'T* = 1.4',
    source: 'above cluster melting, T* ≈ 0.26–0.30',
    note: 'physically possible. the simulation runs, with the warning attached.',
  },
  {
    tone: 'rejected' as const,
    label: 'REJECTED',
    value: 'efficiency = 1.4',
    source: 'a single amplicon cannot be copied twice per cycle',
    note: 'physically impossible. the simulation refuses to run.',
  },
];

const TONE = {
  verified: 'border-verified/35 text-verified',
  flagged: 'border-flagged/35 text-flagged',
  rejected: 'border-rejected/35 text-rejected',
};

export function Contract() {
  return (
    <section className="relative z-10 mx-auto max-w-[1140px] px-6 py-24">
      <Reveal>
        <Eyebrow>VALIDATION CONTRACT</Eyebrow>
        <Title>Three outcomes. Never silently accepted.</Title>
      </Reveal>

      <div className="mt-8 grid gap-4 md:grid-cols-3">
        {STATES.map((s, i) => (
          <Reveal key={s.label} delay={i * 90}>
            <div className="group h-full rounded-md border border-line bg-panel/70 p-5 backdrop-blur-sm transition-colors duration-300 hover:border-lineBright">
              <span
                className={`inline-block rounded-sm border px-1.5 py-0.5 font-mono text-[9.5px] tracking-[0.08em] ${TONE[s.tone]}`}
              >
                {s.label}
              </span>
              <div className="mt-4 font-mono text-[15px] text-ink">{s.value}</div>
              <div className="mt-1.5 font-mono text-[11px] text-dim">{s.source}</div>
              <div className="mt-4 border-t border-line pt-3 font-sans text-[13px] leading-relaxed text-faint">
                {s.note}
              </div>
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  );
}

/* ───────────────────────── constitution ───────────────────────── */

const RULES: [string, string, string][] = [
  ['01', 'Every numerical claim is checked against an independent source of truth.', '“looks like a reasonable curve” is not verification'],
  ['02', 'Impossible is rejected. Implausible is flagged. Neither is silently accepted.', 'a flagged parameter still runs — with the warning attached'],
  ['03', 'Continuous vs. discrete is decided per domain, explicitly, before code.', 'molecular dynamics is continuous and still refuses the ODE pipeline'],
  ['04', 'Shared constraints are enforced by a test, not a comment.', 'Km bounds drifted between two layers; 5000 mM was flagged by one and silently accepted by the other'],
  ['05', 'Undeclared dependencies get a permanent automated guard.', 'not a one-time fix — CI caught what four local machines did not'],
  ['06', 'Mutation testing verifies the test suite itself.', 'a report claimed three tests would catch a bug; the rerun found two'],
  ['07', 'Never install the umbrella package.', 'it pulls two C extensions Caterva never uses and dies at cmake'],
  ['08', 'Never chain the mutation run and the revert with &&.', 'the mutated test is supposed to fail, so && short-circuits and skips the revert'],
  ['09', 'Conservative defaults over irreversible optimism.', 'cheap to reverse: move fast. expensive to reverse: move carefully'],
];

export function Constitution() {
  return (
    <section className="relative z-10 mx-auto max-w-[1140px] px-6 py-24">
      <Reveal>
        <Eyebrow>ENGINEERING CONSTITUTION</Eyebrow>
        <Title>Nine rules. Each one came from a real bug.</Title>
        <p className="mt-2 max-w-[66ch] font-sans text-[14px] leading-relaxed text-dim">
          None of these are generic best practice. Every one was written the
          day something broke.
        </p>
      </Reveal>

      <div className="mt-8 border-t border-line">
        {RULES.map(([n, rule, origin], i) => (
          <Reveal key={n} delay={Math.min(i * 45, 260)}>
            <div className="group grid grid-cols-[42px_1fr] gap-3 border-b border-line py-4 transition-colors duration-300 hover:bg-raised/40 md:grid-cols-[56px_1fr_1fr] md:gap-6">
              <div className="font-mono text-[12px] text-faint transition-colors group-hover:text-verified">
                {n}
              </div>
              <div className="font-sans text-[14px] leading-snug text-ink">{rule}</div>
              <div className="col-start-2 font-mono text-[11px] leading-relaxed text-faint md:col-start-3">
                {origin}
              </div>
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  );
}

/* ───────────────────────── self audit ───────────────────────── */

const BUGS = [
  'duplicate error messages in three validators',
  'a dependency guard blind to package-level imports',
  'six CLI tests running from the wrong working directory',
  'a bare float equality comparison in a symmetry assertion',
  'a population-genetics test whose parameters were too small to avoid fixation — it looked like a broken implementation; the implementation was correct, the test was not',
  'an eigenvector sign bug invisible on the author’s machine and deterministic on the pinned CI configuration, silently producing NaN instead of raising',
];

export function SelfAudit() {
  return (
    <section className="relative z-10 mx-auto max-w-[1140px] px-6 py-24">
      <Reveal>
        <Eyebrow>INTERNAL POSTMORTEM</Eyebrow>
        <Title>We audited ourselves and wrote down what we found.</Title>
      </Reveal>

      <Reveal delay={80} className="mt-8">
        <div className="rounded-md border border-line bg-panel/60 backdrop-blur-sm">
          {BUGS.map((b, i) => (
            <div
              key={i}
              className="flex gap-4 border-b border-line px-5 py-3.5 last:border-b-0"
            >
              <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-rejected/70" />
              <span className="font-mono text-[12px] leading-relaxed text-dim">{b}</span>
            </div>
          ))}
        </div>
      </Reveal>

      <Reveal delay={140}>
        <p className="mt-5 font-mono text-[11.5px] text-faint">
          Found by auditing our own work. Written down instead of quietly fixed.
        </p>
      </Reveal>
    </section>
  );
}

/* ───────────────────────── close ───────────────────────── */

export function Close() {
  return (
    <section id="request" className="relative z-10 mx-auto max-w-[1140px] px-6 pb-28 pt-14">
      <Reveal>
        <div className="rounded-md border border-line bg-panel/70 px-7 py-9 backdrop-blur-sm">
          <div className="flex flex-wrap items-end justify-between gap-6">
            <div>
              <Eyebrow>EARLY ACCESS</Eyebrow>
              <div className="mt-3 font-sans text-[20px] font-medium tracking-[-0.01em] text-ink">
                Built for labs that check their work.
              </div>
              <div className="mt-1.5 font-mono text-[11.5px] text-faint">
                In development. Five domains complete, molecular dynamics in review.
              </div>
            </div>
            <a
              href="mailto:admin.terrium@gmail.com"
              className="group relative overflow-hidden rounded-md bg-verified px-5 py-2.5 font-mono text-[13px] font-medium text-void transition-transform duration-300 hover:scale-[1.02]"
            >
              <span className="relative z-10">Request access →</span>
              <span className="absolute inset-0 -translate-x-full bg-white/25 transition-transform duration-500 group-hover:translate-x-full" />
            </a>
          </div>
        </div>
      </Reveal>
    </section>
  );
}
