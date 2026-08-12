/* ============================================================
   Chapter 02 — exploded view of the Verification Vault
   The four stages separate so each check can be seen working.
   ============================================================ */

import { h, s, qs, qsa, primeDash, prefersReducedMotion } from '../lib/dom.js';
import { facetPath, facetedEllipse, kineticsSeries, plotToPath, envelopePath, elbowPath } from '../lib/geometry.js';
import { CURVE_MODEL } from '../config/architecture.js';

const STEPS = [
  {
    id: 'generate',
    label: 'Generation',
    readout: 'CONFIGURATION PROPOSED / 6 PARAMETERS \u2014 UNCHECKED',
    note: 'A configuration exists. Nothing has been verified yet.'
  },
  {
    id: 'trace',
    label: 'Hallucination check',
    readout: 'TRACED / 3 OF 6 PARAMETERS RESOLVED TO EVIDENCE',
    note: 'Each constant is followed back to an evidence object.'
  },
  {
    id: 'envelope',
    label: 'Correctness',
    readout: 'BEHAVIOUR / WITHIN METHOD-APPROPRIATE ENVELOPE',
    note: 'The output curve is compared against an expected-behaviour region.'
  },
  {
    id: 'critique',
    label: 'Critique',
    readout: 'DISCLOSED / TEMPERATURE ASSUMPTION 37\u00B0C \u2014 REVIEW',
    note: 'An assumption outside the source scope is surfaced, not absorbed.'
  },
  {
    id: 'polish',
    label: 'Polish',
    readout: 'COMPOSED / RECORD RETAINS THE DISCLOSURE',
    note: 'The final record is formatted. The amber flag survives it.'
  }
];

const W = 900;
const H = 520;

function buildStage() {
  const svg = s('svg', {
    class: 'exp-svg', viewBox: `0 0 ${W} ${H}`,
    preserveAspectRatio: 'xMidYMid meet',
    role: 'img',
    'aria-label': 'Exploded view of the verification vault: a configuration is traced to evidence, an output curve is compared against an expected-behaviour envelope, an assumption is disclosed in amber, and the final record retains that disclosure.'
  });

  /* --- layer 1: the configuration being checked --- */
  const cfg = s('g', { class: 'exp-layer exp-config' });
  cfg.appendChild(s('text', { class: 'exp-t-micro', x: 60, y: 78, text: 'CONFIGURATION' }));
  [0, 1, 2, 3, 4, 5].forEach((i) => {
    const y = 96 + i * 34;
    const review = i === 3;
    const g = s('g', { class: `exp-param${review ? ' is-review' : ''}`, 'data-param-row': i });
    g.appendChild(s('path', { class: 'exp-plate', d: facetPath({ x: 60, y, w: 176, h: 26 }, 7) }));
    g.appendChild(s('text', {
      class: 'exp-t-value', x: 72, y: y + 17,
      text: ['Km', 'Vmax', '[S]', 'T', 't', '\u03B5'][i]
    }));
    g.appendChild(s('text', {
      class: 'exp-t-micro exp-status', x: 226, y: y + 17, 'text-anchor': 'end',
      text: review ? '\u25B2 REVIEW' : (i === 2 || i === 4 ? '\u25A0 USER' : '\u25C6 TRACED')
    }));
    cfg.appendChild(g);
  });
  svg.appendChild(cfg);

  /* --- layer 2: evidence column --- */
  const ev = s('g', { class: 'exp-layer exp-evidence' });
  ev.appendChild(s('text', { class: 'exp-t-micro', x: 352, y: 78, text: 'EVIDENCE' }));
  ['DEMO SOURCE', 'SCOPE', 'METHOD'].forEach((lbl, i) => {
    const y = 108 + i * 60;
    ev.appendChild(s('path', { class: 'exp-ev-plate', d: facetPath({ x: 352, y, w: 128, h: 40 }, 8) }));
    ev.appendChild(s('text', { class: 'exp-t-micro exp-ev-label', x: 364, y: y + 18, text: lbl }));
    ev.appendChild(s('text', {
      class: 'exp-t-micro', x: 364, y: y + 31,
      text: ['KINETICS METHOD', 'CONDITION SET', 'ODE SOLUTION'][i], style: 'font-size:7px'
    }));
  });
  svg.appendChild(ev);

  /* --- trace lines: parameter → evidence --- */
  const traces = s('g', { class: 'exp-traces' });
  [
    [109, 128, true], [143, 128, true], [211, 188, true], [245, 248, false]
  ].forEach(([fy, ty, ok], i) => {
    traces.appendChild(s('path', {
      class: `exp-trace${ok ? '' : ' exp-trace--unresolved'}`,
      d: elbowPath({ x: 236, y: fy }, { x: 352, y: ty }),
      style: `animation-delay:${i * 160}ms`
    }));
  });
  svg.appendChild(traces);

  /* --- layer 3: curve vs envelope --- */
  const plot = { x: 556, y: 104, w: 250, h: 156 };
  const { curve, vmax } = kineticsSeries(CURVE_MODEL);
  const cv = s('g', { class: 'exp-layer exp-curve-layer' });
  cv.appendChild(s('text', { class: 'exp-t-micro', x: 556, y: 78, text: 'EXECUTED OUTPUT / ILLUSTRATIVE' }));
  cv.appendChild(s('path', {
    class: 'exp-axis',
    d: `M ${plot.x} ${plot.y} L ${plot.x} ${plot.y + plot.h} L ${plot.x + plot.w} ${plot.y + plot.h}`
  }));
  cv.appendChild(s('path', { class: 'exp-envelope', d: envelopePath(curve, plot, vmax, 0.085) }));
  cv.appendChild(s('path', { class: 'exp-curve', d: plotToPath(curve, plot, vmax) }));
  cv.appendChild(s('text', {
    class: 'exp-t-micro', x: 556, y: plot.y + plot.h + 18,
    text: 'EXPECTED-BEHAVIOUR REGION', style: 'font-size:7px'
  }));
  svg.appendChild(cv);

  /* --- layer 4: amber disclosure --- */
  const cr = s('g', { class: 'exp-layer exp-critique' });
  const fbox = { x: 352, y: 320, w: 300, h: 66 };
  cr.appendChild(s('path', {
    class: 'exp-fracture',
    d: 'M 300 306 L 352 316 L 420 310 L 500 322 L 596 314 L 668 326'
  }));
  cr.appendChild(s('path', { class: 'exp-flag', d: facetPath(fbox, 9) }));
  cr.appendChild(s('text', { class: 'exp-t-micro exp-flag-t', x: fbox.x + 14, y: fbox.y + 22, text: 'TEMPERATURE ASSUMPTION / 37\u00B0C' }));
  cr.appendChild(s('text', { class: 'exp-t-micro exp-flag-t', x: fbox.x + 14, y: fbox.y + 38, text: 'STATUS / DISCLOSED FOR REVIEW' }));
  cr.appendChild(s('text', {
    class: 'exp-t-micro exp-flag-note', x: fbox.x + 14, y: fbox.y + 54,
    text: 'NOT ESTABLISHED BY THE SAMPLE SOURCE SCOPE', style: 'font-size:7px'
  }));
  cr.appendChild(s('text', {
    class: 'exp-t-micro exp-flag-t', x: fbox.x + fbox.w - 14, y: fbox.y + 22,
    'text-anchor': 'end', text: '\u25B2'
  }));
  svg.appendChild(cr);

  /* --- layer 5: polished record retaining the flag --- */
  const rec = s('g', { class: 'exp-layer exp-record' });
  const rbox = { x: 690, y: 300, w: 168, h: 172 };
  rec.appendChild(s('path', { class: 'exp-rec-plate', d: facetPath(rbox, 12) }));
  rec.appendChild(s('text', { class: 'exp-t-micro exp-rec-t', x: rbox.x + 16, y: rbox.y + 26, text: 'VERIFIED RUN / 0007' }));
  rec.appendChild(s('line', {
    x1: rbox.x + 16, y1: rbox.y + 36, x2: rbox.x + rbox.w - 16, y2: rbox.y + 36,
    stroke: 'rgba(22,32,31,0.2)', 'stroke-width': 1, 'vector-effect': 'non-scaling-stroke'
  }));
  [['6', 'PARAMETERS'], ['3', 'EVIDENCE'], ['4', 'CHECKS']].forEach(([k, v], i) => {
    rec.appendChild(s('text', { class: 'exp-rec-num', x: rbox.x + 16, y: rbox.y + 62 + i * 24, text: k }));
    rec.appendChild(s('text', { class: 'exp-t-micro exp-rec-l', x: rbox.x + 38, y: rbox.y + 61 + i * 24, text: v }));
  });
  rec.appendChild(s('path', {
    class: 'exp-rec-warn', d: facetPath({ x: rbox.x + 16, y: rbox.y + 128, w: rbox.w - 32, h: 30 }, 6)
  }));
  rec.appendChild(s('text', {
    class: 'exp-t-micro exp-rec-warn-t', x: rbox.x + 26, y: rbox.y + 141, text: '\u25B2 1 ASSUMPTION'
  }));
  rec.appendChild(s('text', {
    class: 'exp-t-micro exp-rec-warn-t', x: rbox.x + 26, y: rbox.y + 152, text: 'DISCLOSED', style: 'font-size:7px'
  }));
  svg.appendChild(rec);

  /* --- vault silhouette holding it all together --- */
  const ring = s('g', { class: 'exp-ring', 'aria-hidden': 'true' });
  ring.appendChild(s('path', { class: 'exp-ring-path', d: facetedEllipse(450, 262, 424, 236, 16) }));
  ring.appendChild(s('path', { class: 'exp-ring-path exp-ring-path--inner', d: facetedEllipse(450, 262, 372, 196, 16, Math.PI / 16) }));
  svg.insertBefore(ring, svg.firstChild);

  return svg;
}

export function initExplodedVault() {
  const mount = qs('[data-exploded-stage]');
  const stepsEl = qs('[data-exploded-steps]');
  const readout = qs('[data-exploded-readout]');
  const shell = qs('[data-exploded]');
  if (!mount || !stepsEl) return;

  const svg = buildStage();
  mount.replaceChildren(svg);
  qsa('.exp-curve, .exp-axis, .exp-trace, .exp-fracture', svg).forEach(primeDash);

  let index = 0;

  const render = (i) => {
    index = i;
    STEPS.forEach((st, n) => {
      svg.classList.toggle(`is-${st.id}`, n <= i);
    });
    qsa('.exp-step', stepsEl).forEach((el, n) => {
      const on = n === i;
      el.classList.toggle('is-active', on);
      el.classList.toggle('is-done', n < i);
      el.setAttribute('aria-selected', on ? 'true' : 'false');
      el.tabIndex = on ? 0 : -1;
    });
    readout.textContent = `${STEPS[i].readout}  \u2014  ${STEPS[i].note}`;
  };

  stepsEl.setAttribute('role', 'tablist');
  stepsEl.replaceChildren(
    ...STEPS.map((st, i) => {
      const btn = h('button', {
        class: 'exp-step', type: 'button', role: 'tab',
        'aria-selected': 'false', tabindex: '-1'
      }, [
        h('span', { class: 'exp-step__n label label--micro', text: String(i + 1).padStart(2, '0') }),
        h('span', { class: 'exp-step__l', text: st.label })
      ]);
      btn.addEventListener('click', () => render(i));
      btn.addEventListener('keydown', (e) => {
        const dirs = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
        if (dirs[e.key]) {
          e.preventDefault();
          const next = (i + dirs[e.key] + STEPS.length) % STEPS.length;
          render(next);
          qsa('.exp-step', stepsEl)[next].focus();
        }
      });
      return btn;
    })
  );

  render(0);

  // Advance through the stages once, when the chapter is first seen.
  if (!prefersReducedMotion() && 'IntersectionObserver' in window) {
    let played = false;
    const io = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting && !played) {
          played = true;
          io.disconnect();
          let n = 1;
          const tick = () => {
            if (n >= STEPS.length) return;
            render(n);
            n += 1;
            setTimeout(tick, 1250);
          };
          setTimeout(tick, 700);
        }
      });
    }, { threshold: 0.35 });
    io.observe(shell);
  } else {
    render(STEPS.length - 1);
  }
}
