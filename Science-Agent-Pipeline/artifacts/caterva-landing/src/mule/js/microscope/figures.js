/* ============================================================
   caterva — microscope figures

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
        h('span', { class: 'mono mi-src__ref', text: 'BRENDA 286469' }),
        h('span', { class: 'label label--micro mi-src__k', text: 'Measured row' })
      ]),
      h('p', { class: 'mi-src__role', text: 'EC 1.1.1.27 \u00B7 Homo sapiens \u00B7 pyruvate' }),
      /* Bars, not a made-up title: the page states no author or title the
         BRENDA record does not carry. The reference id is the locator. */
      h('div', { class: 'mi-src__lines' }, [
        h('span', { class: 'mi-src__l', style: '--w:82%' }),
        h('span', { class: 'mi-src__l', style: '--w:96%' }),
        h('span', { class: 'mi-src__l', style: '--w:64%' })
      ]),
      h('p', { class: 'mi-src__foot mono', text: 'brenda-enzymes.org / ec 1.1.1.27 / ref 286469' })
    ]),
    h('div', { class: 'mi-src__tie' }, [
      h('span', { class: 'mi-src__tie-l' }),
      h('span', { class: 'mono mi-src__tie-t', text: 'BOUND TO Km' })
    ])
  ]);
}

/* --- 04 what the source does not say ------------------------
   No supported band is drawn, because the source declares none. What is
   drawn is what is known: the two human values on one axis, the gap
   between them, and the missing conditions as an open edge. */
function scopeFigure() {
  const x0 = 46, x1 = W - 34, y = 110;
  const span = x1 - x0;
  const at = (v) => x0 + (v / SCOPE_BAND.sMax) * span;
  const a = at(SCOPE_BAND.km), b = at(SCOPE_BAND.other);

  return frame('scope', [
    s('path', { class: 'mi-sc__axis', d: `M ${x0} ${y + 20} L ${x1} ${y + 20}` }),
    s('path', { class: 'mi-sc__stop', d: `M ${x0} ${y + 12} L ${x0} ${y + 28}` }),
    s('text', { class: 'mi-sc__t', x: x0, y: y + 40, text: '0 mM' }),
    s('text', { class: 'mi-sc__t mi-sc__t--end', x: x1, y: y + 40, text: `${SCOPE_BAND.sMax} mM` }),
    // the spread between the two papers
    s('rect', { class: 'mi-sc__band', x: a, y: y - 14, width: b - a, height: 28 }),
    s('text', { class: 'mi-sc__in', x: (a + b) / 2, y: y + 4, text: `${SCOPE_BAND.fold}-FOLD APART` }),
    // the carried value
    s('path', { class: 'mi-sc__km', d: `M ${a} ${y - 30} L ${a} ${y + 22}` }),
    s('text', { class: 'mi-sc__km-t', x: a + 4, y: y - 36, text: 'Km 0.03 \u00B7 ref 286469 (carried)' }),
    // the other human paper
    s('path', { class: 'mi-sc__stop', d: `M ${b} ${y - 30} L ${b} ${y + 22}` }),
    s('text', { class: 'mi-sc__t mi-sc__t--end', x: b, y: y - 36, text: '0.398 \u00B7 ref 286442' }),
    // the axis the source never declared
    s('path', { class: 'mi-sc__gap', d: `M ${x0} 34 L ${x1} 34` }),
    s('text', { class: 'mi-sc__gap-t', x: x0, y: 26, text: '\u25B2 ASSAY CONDITIONS NOT STATED BY THE SOURCE' }),
    s('text', { class: 'mi-fig__cap', x: W / 2, y: 196, text: 'WHAT IS UNKNOWN IS PART OF THE VALUE' })
  ]);
}

/* --- 05 what Caterva did ------------------------------------- */
function checkFigure() {
  return h('div', { class: 'mi-ck' }, [
    h('div', { class: 'mi-ck__pair' }, [
      h('div', { class: 'mi-ck__side' }, [
        h('span', { class: 'label label--micro', text: 'Carried' }),
        h('p', { class: 'mi-ck__t', text: 'Km = 0.03 mM' })
      ]),
      h('div', { class: 'mi-ck__gate' }, [
        h('span', { class: 'mi-ck__glyph', text: '\u25CE' }),
        h('span', { class: 'mono mi-ck__gate-t', text: 'LITERATURE RESOLVER' })
      ]),
      h('div', { class: 'mi-ck__side mi-ck__side--r' }, [
        h('span', { class: 'label label--micro', text: 'Also found' }),
        h('p', { class: 'mi-ck__t', text: '0.398 mM / ref 286442' })
      ])
    ]),
    h('ul', { class: 'mi-ck__out' }, [
      h('li', { class: 'mi-ck__o', dataset: { st: 'supported' } }, [
        h('span', { class: 'mi-ck__o-g', text: '\u25C6' }),
        h('span', { text: 'Exact match: human enzyme, same substrate' })
      ]),
      h('li', { class: 'mi-ck__o', dataset: { st: 'review' } }, [
        h('span', { class: 'mi-ck__o-g', text: '\u25B2' }),
        h('span', { text: 'Two papers disagree 13.3-fold: reported, not averaged' })
      ]),
      h('li', { class: 'mi-ck__o', dataset: { st: 'review' } }, [
        h('span', { class: 'mi-ck__o-g', text: '\u25B2' }),
        h('span', { text: 'Assay conditions unstated: left unknown, not assumed' })
      ])
    ])
  ]);
}

/* --- 06 the printed record --------------------------------- */
function recordFigure(level) {
  return h('div', { class: 'mi-rec' }, [
    h('div', { class: 'mi-rec__head' }, [
      h('span', { class: 'label label--micro', text: 'Notebook record / parameter entry' }),
      h('span', { class: 'mono mi-rec__id', text: 'BRENDA 286469' })
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
