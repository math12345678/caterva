/* ============================================================
   Chapter 03 — execution strata
   Three architectural substrates beneath the same engine.
   Not pricing cards: foundations at different depths.
   ============================================================ */

import { h, s, qs } from '../lib/dom.js';
import { facetPath, facetedEllipse } from '../lib/geometry.js';

const STRATA = [
  {
    id: 'browser',
    depth: '01',
    name: 'Browser runtime',
    label: 'Runs locally when the method permits.',
    methods: ['PCR amplification', 'Monte Carlo simulation', 'Population genetics'],
    availability: 'LOCAL',
    status: 'supported'
  },
  {
    id: 'ode',
    depth: '02',
    name: 'Local ODE runtime',
    label: 'Solves browser-compatible mathematical systems locally.',
    methods: ['SIR / SEIR modeling', 'Michaelis\u2013Menten kinetics'],
    availability: 'LOCAL / NUMERICAL',
    status: 'supported'
  },
  {
    id: 'server',
    depth: '03',
    name: 'Server or user-provided compute',
    label: 'Uses backend or user-provided compute when the method requires it.',
    methods: ['Molecular dynamics', 'Compute-intensive workloads'],
    availability: 'EXTERNAL / HPC OR CLOUD',
    status: 'review'
  }
];

/** Substrate cross-section: a foundation slab at increasing depth. */
function substrateMark(id, index) {
  const svg = s('svg', {
    class: 'strata-mark', viewBox: '0 0 220 96', 'aria-hidden': 'true',
    preserveAspectRatio: 'xMidYMid meet'
  });

  // engine feed from above — same core feeding every substrate
  svg.appendChild(s('path', { class: 'strata-feed', d: 'M 110 0 L 110 22' }));
  svg.appendChild(s('path', { class: 'strata-feed', d: 'M 96 22 L 124 22' }));

  if (id === 'browser') {
    // shallow slab, dense small cells: many light runs
    svg.appendChild(s('path', { class: 'strata-slab', d: facetPath({ x: 24, y: 30, w: 172, h: 42 }, 10) }));
    for (let i = 0; i < 7; i += 1) {
      svg.appendChild(s('rect', {
        class: 'strata-cell', x: 36 + i * 22, y: 42, width: 12, height: 18,
        style: `--d:${i * 70}ms`
      }));
    }
  } else if (id === 'ode') {
    // integrating substrate: a stepped solver lattice
    svg.appendChild(s('path', { class: 'strata-slab', d: facetPath({ x: 24, y: 30, w: 172, h: 48 }, 10) }));
    const pts = [];
    for (let i = 0; i <= 8; i += 1) {
      const x = 38 + i * 18;
      const y = 66 - Math.min(26, (i * i) * 0.62);
      pts.push(`${x} ${y}`);
    }
    svg.appendChild(s('path', { class: 'strata-solve', d: `M ${pts.join(' L ')}` }));
    for (let i = 0; i < 5; i += 1) {
      svg.appendChild(s('line', {
        class: 'strata-tick', x1: 38 + i * 36, y1: 68, x2: 38 + i * 36, y2: 74
      }));
    }
  } else {
    // deep foundation: external compute, drawn as a separate mass
    svg.appendChild(s('path', {
      class: 'strata-slab strata-slab--external',
      d: facetPath({ x: 24, y: 34, w: 172, h: 46 }, 10)
    }));
    svg.appendChild(s('path', { class: 'strata-gap', d: 'M 24 30 L 196 30' }));
    svg.appendChild(s('path', { class: 'strata-ring', d: facetedEllipse(110, 57, 30, 17, 8) }));
    svg.appendChild(s('path', { class: 'strata-ring', d: facetedEllipse(110, 57, 18, 10, 8, 0.4) }));
    [46, 174].forEach((x) => {
      svg.appendChild(s('path', { class: 'strata-feed strata-feed--out', d: `M ${x} 42 L ${x} 72` }));
    });
  }

  // depth rule
  svg.appendChild(s('text', {
    class: 'strata-depth', x: 8, y: 92, text: `\u2013 DEPTH ${index}`
  }));
  return svg;
}

export function initExecutionStrata() {
  const mount = qs('[data-strata]');
  if (!mount) return;

  mount.replaceChildren(
    h('div', { class: 'strata__spine', 'aria-hidden': 'true' }),
    ...STRATA.map((st, i) =>
      h('article', { class: 'stratum', dataset: { status: st.status } }, [
        h('div', { class: 'stratum__head' }, [
          h('span', { class: 'label label--micro stratum__depth', text: `${st.depth} / substrate` }),
          h('h3', { class: 'stratum__name', text: st.name })
        ]),
        h('div', { class: 'stratum__mark' }, [substrateMark(st.id, st.depth)]),
        h('div', { class: 'stratum__body' }, [
          h('p', { class: 'stratum__label', text: st.label }),
          h('ul', { class: 'stratum__methods' },
            st.methods.map((m) => h('li', { class: 'mono', text: m }))
          ),
          h('p', { class: 'stratum__avail', dataset: { status: st.status } }, [
            h('span', { 'aria-hidden': 'true', text: st.status === 'review' ? '\u25B2' : '\u25C6' }),
            h('span', { text: st.availability })
          ])
        ])
      ])
    )
  );
}
