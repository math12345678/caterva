/* ============================================================
   terrium — microscope figures

   Six drawings for six kinds of fact. A value is drawn as a
   magnitude, a decision as an equation with one term marked, a
   source as an archival card, a scope as a bounded interval, a
   check as a comparison, a record as printed paper.

   Pure construction. The controller decides which one is on
   screen and when.
   ============================================================ */

import { h, s } from '../lib/dom.js';
import { EQUATION, SCOPE_BAND, PARAM } from '../config/microscope.js';

const W = 420;
const H = 210;

const frame = (kind, children) =>
  s('svg', {
    class: `mi-fig mi-fig--${kind}`,
    viewBox: `0 0 ${W} ${H}`,
    preserveAspectRatio: 'xMidYMid meet',
    'aria-hidden': 'true'
  }, children);

/* --- 01 the bare value ------------------------------------- */
function valueFigure() {
  const cx = W / 2;
  return frame('value', [
    /* Reticle: the value is being looked at, and the marks say so. */
    s('circle', { class: 'mi-ret', cx, cy: 96, r: 74 }),
    s('circle', { class: 'mi-ret mi-ret--in', cx, cy: 96, r: 52 }),
    s('path', { class: 'mi-ret', d: `M ${cx - 92} 96 L ${cx - 78} 96` }),
    s('path', { class: 'mi-ret', d: `M ${cx + 78} 96 L ${cx + 92} 96` }),
    s('path', { class: 'mi-ret', d: `M ${cx} 8 L ${cx} 20` }),
    s('path', { class: 'mi-ret', d: `M ${cx} 172 L ${cx} 184` }),
    s('text', { class: 'mi-val', x: cx, y: 108, text: PARAM.value }),
    s('text', { class: 'mi-val__u', x: cx, y: 134, text: PARAM.unit }),
    s('text', { class: 'mi-val__n', x: cx, y: 62, text: PARAM.name }),
    /* A number with nothing behind it. Stated, not implied. */
    s('text', { class: 'mi-fig__cap', x: cx, y: 200, text: 'NO BASIS SHOWN AT THIS DEPTH' })
  ]);
}

/* --- 02 the model form ------------------------------------- */
function equationFigure() {
  const el = h('div', { class: 'mi-eq' }, [
    h('p', { class: 'mi-eq__row' }, EQUATION.map((tk) =>
      h('span', { class: `mi-eq__t mi-eq__t--${tk.role}`, text: tk.t })
    )),
    h('p', { class: 'mi-eq__note' }, [
      h('span', { class: 'mi-eq__brace', text: '\u2514' }),
      h('span', { text: 'Km is the substrate concentration at which velocity reaches half of Vmax. Change the model form and the term stops meaning this.' })
    ])
  ]);
  return el;
}

/* --- 03 the source card ------------------------------------
   Drawn as an archival object rather than a citation string: the
   product's claim is that evidence is a first-class artifact, and a
   line of grey text would contradict that. */
function sourceFigure() {
  return h('div', { class: 'mi-src' }, [
    h('div', { class: 'mi-src__card' }, [
      h('div', { class: 'mi-src__head' }, [
        h('span', { class: 'mono mi-src__ref', text: 'DEMO-02' }),
        h('span', { class: 'label label--micro mi-src__k', text: 'Demonstration record' })
      ]),
      h('p', { class: 'mi-src__role', text: 'Kinetics method record' }),
      /* Redaction bars, not lorem text: there is no fabricated title or
         author here, and the drawing has to make that absence deliberate
         rather than look like missing data. */
      h('div', { class: 'mi-src__lines' }, [
        h('span', { class: 'mi-src__l', style: '--w:82%' }),
        h('span', { class: 'mi-src__l', style: '--w:96%' }),
        h('span', { class: 'mi-src__l', style: '--w:64%' })
      ]),
      h('p', { class: 'mi-src__foot mono', text: 'ILLUSTRATIVE / NO REAL CITATION' })
    ]),
    h('div', { class: 'mi-src__tie' }, [
      h('span', { class: 'mi-src__tie-l' }),
      h('span', { class: 'mono mi-src__tie-t', text: 'BOUND TO Km' })
    ])
  ]);
}

/* --- 04 the scope interval --------------------------------- */
function scopeFigure() {
  const x0 = 46, x1 = W - 34, y = 104;
  const span = x1 - x0;
  const at = (v) => x0 + (v / SCOPE_BAND.sMax) * span;

  return frame('scope', [
    // the supported interval, drawn as an occupied band
    s('rect', {
      class: 'mi-sc__band',
      x: at(SCOPE_BAND.supported[0]), y: y - 20,
      width: at(SCOPE_BAND.supported[1]) - at(SCOPE_BAND.supported[0]), height: 40
    }),
    s('path', { class: 'mi-sc__axis', d: `M ${x0} ${y + 20} L ${x1} ${y + 20}` }),
    // end stops: a scope has edges, and they are drawn as edges
    s('path', { class: 'mi-sc__stop', d: `M ${x0} ${y - 26} L ${x0} ${y + 26}` }),
    s('path', { class: 'mi-sc__stop', d: `M ${x1} ${y - 26} L ${x1} ${y + 26}` }),
    s('text', { class: 'mi-sc__t', x: x0, y: y + 40, text: '0 mM' }),
    s('text', { class: 'mi-sc__t mi-sc__t--end', x: x1, y: y + 40, text: '5.0 mM' }),
    // Km sitting inside it
    s('path', { class: 'mi-sc__km', d: `M ${at(SCOPE_BAND.km)} ${y - 32} L ${at(SCOPE_BAND.km)} ${y + 22}` }),
    s('text', { class: 'mi-sc__km-t', x: at(SCOPE_BAND.km), y: y - 40, text: 'Km 0.42' }),
    s('text', { class: 'mi-sc__in', x: (x0 + x1) / 2, y: y + 4, text: 'SUPPORTED SUBSTRATE RANGE' }),
    // the axis the source never declared
    s('path', { class: 'mi-sc__gap', d: `M ${x0} 42 L ${x1} 42` }),
    s('text', { class: 'mi-sc__gap-t', x: x0, y: 32, text: '\u25B2 TEMPERATURE CONDITION NOT ESTABLISHED' }),
    s('text', { class: 'mi-fig__cap', x: W / 2, y: 190, text: 'THE BOUNDARY IS PART OF THE VALUE' })
  ]);
}

/* --- 05 the check ------------------------------------------ */
function checkFigure() {
  return h('div', { class: 'mi-ck' }, [
    h('div', { class: 'mi-ck__pair' }, [
      h('div', { class: 'mi-ck__side' }, [
        h('span', { class: 'label label--micro', text: 'Claim' }),
        h('p', { class: 'mi-ck__t', text: 'Km = 0.42 mM' })
      ]),
      h('div', { class: 'mi-ck__gate' }, [
        h('span', { class: 'mi-ck__glyph', text: '\u25CE' }),
        h('span', { class: 'mono mi-ck__gate-t', text: 'HALLUCINATION CHECK' })
      ]),
      h('div', { class: 'mi-ck__side mi-ck__side--r' }, [
        h('span', { class: 'label label--micro', text: 'Basis' }),
        h('p', { class: 'mi-ck__t', text: 'DEMO-02 / kinetics method record' })
      ])
    ]),
    h('ul', { class: 'mi-ck__out' }, [
      h('li', { class: 'mi-ck__o', dataset: { st: 'supported' } }, [
        h('span', { class: 'mi-ck__o-g', text: '\u25C6' }),
        h('span', { text: 'Basis is relevant to the claim' })
      ]),
      h('li', { class: 'mi-ck__o', dataset: { st: 'review' } }, [
        h('span', { class: 'mi-ck__o-g', text: '\u25B2' }),
        h('span', { text: 'Scope narrower than the run \u2014 disclosed, not resolved' })
      ]),
      h('li', { class: 'mi-ck__o', dataset: { st: 'supported' } }, [
        h('span', { class: 'mi-ck__o-g', text: '\u25C6' }),
        h('span', { text: 'No unsupported claim shown' })
      ])
    ])
  ]);
}

/* --- 06 the printed record --------------------------------- */
function recordFigure(level) {
  return h('div', { class: 'mi-rec' }, [
    h('div', { class: 'mi-rec__head' }, [
      h('span', { class: 'label label--micro', text: 'Notebook record / parameter entry' }),
      h('span', { class: 'mono mi-rec__id', text: 'ILLUSTRATIVE' })
    ]),
    h('dl', { class: 'mi-rec__body' }, level.record.flatMap((r) => [
      h('dt', { class: 'mono mi-rec__k', text: r.k }),
      h('dd', { class: 'mi-rec__v', dataset: { tone: r.tone || null }, text: r.v })
    ]))
  ]);
}

const FIG = {
  value: valueFigure,
  equation: equationFigure,
  source: sourceFigure,
  scope: scopeFigure,
  check: checkFigure,
  record: recordFigure
};

/** Build the figure for one level. */
export function buildFigure(level) {
  const fn = FIG[level.figure];
  return fn ? fn(level) : null;
}
