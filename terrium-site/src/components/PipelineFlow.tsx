/**
 * The build architecture, drawn.
 *
 * A spec is dispatched to two AI implementers that never see each other.
 * Their reports disagree. A reviewer reruns the disagreement independently,
 * finds the truth, and corrects the permanent record.
 *
 * The connector paths draw themselves as the section scrolls, and a packet
 * travels the route. The divergence node is the one that matters and is the
 * only element allowed to interrupt the mint palette.
 */

import { useEffect, useRef, useState } from 'react';
import { useInView, useReducedMotion } from '../lib/motion';

interface Node {
  id: string;
  label: string;
  sub: string;
  x: number;
  y: number;
  w: number;
  tone?: 'mint' | 'amber';
  detail?: string[];
}

const W = 1000;
const H = 470;

const NODES: Node[] = [
  {
    id: 'spec', label: 'SPEC', sub: 'stage_02 · wright_fisher',
    x: 40, y: 200, w: 180,
    detail: ['governing model  binomial, 2N copies', 'target  H(t) = H0 (1 − 1/2N)^t', 'pre-specified bug  2N → N'],
  },
  { id: 'a1', label: 'opencode', sub: 'nemotron-3', x: 300, y: 108, w: 190 },
  { id: 'a2', label: 'freebuff', sub: 'deepseek-v4-pro', x: 300, y: 292, w: 190 },
  {
    id: 'div', label: 'DIVERGENCE', sub: 'the reports disagree',
    x: 566, y: 200, w: 190, tone: 'amber',
    detail: ['report   “3 tests fail under 2N → N”', 'rerun    2 tests fail', 'cause    fixation target runs other', '         parameters — untouched'],
  },
  { id: 'ok', label: 'VERIFIED', sub: 'record corrected', x: 826, y: 200, w: 140, tone: 'mint' },
];

const EDGES: [string, string][] = [
  ['spec', 'a1'], ['spec', 'a2'], ['a1', 'div'], ['a2', 'div'], ['div', 'ok'],
];

const NODE_H = 54;

function anchor(n: Node, side: 'l' | 'r') {
  return { x: side === 'r' ? n.x + n.w : n.x, y: n.y + NODE_H / 2 };
}

function edgePath(a: Node, b: Node): string {
  const p1 = anchor(a, 'r');
  const p2 = anchor(b, 'l');
  const dx = Math.max(46, (p2.x - p1.x) * 0.5);
  return `M ${p1.x} ${p1.y} C ${p1.x + dx} ${p1.y}, ${p2.x - dx} ${p2.y}, ${p2.x} ${p2.y}`;
}

export default function PipelineFlow() {
  const [ref, inView] = useInView<HTMLDivElement>('-18% 0px -18% 0px');
  const reduced = useReducedMotion();
  const [active, setActive] = useState(-1);
  const pathRefs = useRef<(SVGPathElement | null)[]>([]);

  // Walk the stages once in view.
  useEffect(() => {
    if (!inView) return;
    if (reduced) {
      setActive(NODES.length);
      return;
    }
    let i = -1;
    const id = window.setInterval(() => {
      i += 1;
      setActive(i);
      if (i >= NODES.length) window.clearInterval(id);
    }, 620);
    return () => window.clearInterval(id);
  }, [inView, reduced]);

  const byId = (id: string) => NODES.find((n) => n.id === id)!;
  const nodeIndex = (id: string) => NODES.findIndex((n) => n.id === id);

  return (
    <section className="relative z-10 mx-auto max-w-[1140px] px-6 py-24" ref={ref}>
      <div
        className="mb-8 transition-all duration-700"
        style={{ opacity: inView ? 1 : 0, transform: inView ? 'none' : 'translateY(10px)' }}
      >
        <div className="font-mono text-[10px] tracking-[0.18em] text-faint">
          BUILD ARCHITECTURE
        </div>
        <h2 className="mt-2 font-sans text-[26px] font-medium tracking-[-0.015em] text-ink">
          Two models. One spec. Neither is trusted.
        </h2>
        <p className="mt-2 max-w-[68ch] font-sans text-[14px] leading-relaxed text-dim">
          Every domain is implemented twice, independently, from byte-identical
          prompts. Where the two reports disagree, a reviewer reproduces the
          disagreement from scratch. The example below is real — it happened
          while building the population-genetics domain.
        </p>
      </div>

      <div
        className="overflow-x-auto rounded-md border border-line bg-panel/60 backdrop-blur-sm"
        style={{ boxShadow: '0 24px 70px -34px rgba(0,0,0,0.9)' }}
      >
        <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full min-w-[820px]">
          <defs>
            <linearGradient id="mintFade" x1="0" x2="1">
              <stop offset="0%" stopColor="#6EE7B7" stopOpacity="0.15" />
              <stop offset="100%" stopColor="#6EE7B7" stopOpacity="0.5" />
            </linearGradient>
            <filter id="glow" x="-60%" y="-60%" width="220%" height="220%">
              <feGaussianBlur stdDeviation="3.2" result="b" />
              <feMerge>
                <feMergeNode in="b" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          {EDGES.map(([from, to], i) => {
            const dPath = edgePath(byId(from), byId(to));
            const reached = active >= nodeIndex(to);
            return (
              <g key={`${from}-${to}`}>
                <path d={dPath} fill="none" stroke="#1A1E20" strokeWidth={1.25} />
                <path
                  ref={(el) => (pathRefs.current[i] = el)}
                  d={dPath}
                  fill="none"
                  stroke="url(#mintFade)"
                  strokeWidth={1.5}
                  strokeDasharray="1000"
                  strokeDashoffset={reached ? 0 : 1000}
                  style={{
                    transition: reduced
                      ? undefined
                      : 'stroke-dashoffset 900ms cubic-bezier(0.16,1,0.3,1)',
                  }}
                />
                {reached && !reduced && (
                  <circle r="2.6" fill="#6EE7B7" filter="url(#glow)">
                    <animateMotion dur="2.6s" repeatCount="indefinite" path={dPath} />
                    <animate
                      attributeName="opacity"
                      values="0;1;1;0"
                      dur="2.6s"
                      repeatCount="indefinite"
                    />
                  </circle>
                )}
              </g>
            );
          })}

          {NODES.map((n, i) => {
            const on = active >= i;
            const amber = n.tone === 'amber';
            const stroke = !on ? '#1A1E20' : amber ? '#FBBF24' : '#6EE7B7';
            return (
              <g
                key={n.id}
                style={{
                  opacity: on ? 1 : 0.42,
                  transition: reduced ? undefined : 'opacity 500ms ease',
                }}
              >
                <rect
                  x={n.x} y={n.y} width={n.w} height={NODE_H} rx={5}
                  fill="#0A0C0D"
                  stroke={stroke}
                  strokeOpacity={on ? 0.55 : 1}
                  strokeWidth={1.25}
                  filter={on && amber ? 'url(#glow)' : undefined}
                />
                <text
                  x={n.x + 14} y={n.y + 22}
                  className="font-mono"
                  fontSize="12"
                  fill={on ? (amber ? '#FBBF24' : '#E8EAEB') : '#555B5F'}
                  letterSpacing="0.08em"
                >
                  {n.label}
                </text>
                <text
                  x={n.x + 14} y={n.y + 39}
                  className="font-mono" fontSize="10" fill="#8C9398"
                >
                  {n.sub}
                </text>

                {n.detail && on && (
                  <g>
                    {n.detail.map((line, k) => (
                      <text
                        key={k}
                        x={n.x + 2}
                        y={n.y + NODE_H + 22 + k * 15}
                        className="font-mono"
                        fontSize="9.5"
                        fill={amber ? '#FBBF24' : '#555B5F'}
                        opacity={0}
                      >
                        {line}
                        <animate
                          attributeName="opacity"
                          from="0" to={amber ? 0.95 : 0.8}
                          dur="360ms" begin={`${k * 80}ms`} fill="freeze"
                        />
                      </text>
                    ))}
                  </g>
                )}
              </g>
            );
          })}

          <text x={300} y={92} className="font-mono" fontSize="9.5" fill="#555B5F" letterSpacing="0.12em">
            IDENTICAL PROMPT · NO CONTACT
          </text>
        </svg>
      </div>

      <p className="mt-5 max-w-[70ch] font-mono text-[11.5px] leading-relaxed text-faint">
        Agreement between two implementers is not evidence of correctness.
        Both can share an error, and once did — a mutation blast radius
        overstated in a report that had already passed its own review. The
        reviewer reran it and found two failing tests where three were claimed.
      </p>
    </section>
  );
}
