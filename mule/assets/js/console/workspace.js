/* ============================================================
   terrium — console output workspace

   The workspace assembles as a consequence of the timeline: each
   agent that emits something adds its own block here, in order.
   Pure construction — the console controller decides when.
   ============================================================ */

import { h, s } from '../lib/dom.js';
import { kineticsSeries, plotToPath, plotPoint } from '../lib/geometry.js';
import { WORKSPACE, CURVE } from '../config/console.js';

const block = (kind, title, body, tone) =>
  h('section', {
    class: `ws-block ws-block--${kind}`,
    dataset: { block: kind, tone: tone || null }
  }, [
    h('p', { class: 'label label--micro ws-block__t', text: title }),
    body
  ]);

/* --- evidence trail ---------------------------------------- */
function evidenceBlock(spec) {
  return block('evidence', spec.title,
    h('ul', { class: 'ws-ev' }, spec.items.map((it) =>
      h('li', {
        class: 'ws-ev__i',
        dataset: { st: it.status || 'supported' }
      }, [
        h('span', { class: 'ws-ev__ref mono', text: it.ref }),
        h('span', { class: 'ws-ev__role', text: it.role }),
        h('span', { class: 'ws-ev__scope', text: it.scope })
      ])
    )),
    spec.tone
  );
}

/* --- parameters -------------------------------------------- */
function paramsBlock(spec) {
  return block('params', spec.title,
    h('ul', { class: 'ws-par' }, spec.items.map((it) =>
      h('li', { class: `ws-par__i ws-par__i--${it.status}` }, [
        h('span', { class: 'ws-par__n mono', text: it.name }),
        h('span', { class: 'ws-par__v mono', text: it.value }),
        h('span', { class: 'ws-par__u mono', text: it.unit })
      ])
    )),
    spec.tone
  );
}

/* --- the illustrative curve --------------------------------
   Drawn from the same generator the cathedral uses, so the shape
   in the console and the shape in the architecture are literally
   the same curve rather than two drawings that resemble it. */
function plotBlock(spec) {
  const W = 340, H = 190;
  const plot = { x: 44, y: 14, w: W - 60, h: H - 52 };
  const series = kineticsSeries(CURVE);

  const svg = s('svg', {
    class: 'ws-plot',
    viewBox: `0 0 ${W} ${H}`,
    preserveAspectRatio: 'xMidYMid meet',
    role: 'img',
    'aria-label':
      'Illustrative saturation curve: velocity rises steeply at low substrate concentration and flattens toward a plateau. Shape demonstration only, not a measurement.'
  });

  // axes
  svg.appendChild(s('path', {
    class: 'ws-plot__axis',
    d: `M ${plot.x} ${plot.y} L ${plot.x} ${plot.y + plot.h} L ${plot.x + plot.w} ${plot.y + plot.h}`
  }));
  // plateau datum: what "saturating" means, drawn rather than asserted
  svg.appendChild(s('line', {
    class: 'ws-plot__datum',
    x1: plot.x, y1: plot.y + plot.h - (1 / 1.12) * plot.h,
    x2: plot.x + plot.w, y2: plot.y + plot.h - (1 / 1.12) * plot.h
  }));
  svg.appendChild(s('text', {
    class: 'ws-plot__tick', x: plot.x - 8, y: plot.y + plot.h - (1 / 1.12) * plot.h + 4,
    text: 'Vmax'
  }));
  svg.appendChild(s('text', {
    class: 'ws-plot__tick', x: plot.x - 8, y: plot.y + plot.h + 4, text: '0'
  }));

  const curve = s('path', {
    class: 'ws-plot__curve',
    d: plotToPath(series.curve, plot, series.vmax)
  });
  svg.appendChild(curve);

  series.points.forEach((p, i) => {
    const pt = plotPoint(p, plot, CURVE.sMax, series.vmax);
    svg.appendChild(s('rect', {
      class: 'ws-plot__pt',
      x: pt.x - 2.4, y: pt.y - 2.4, width: 4.8, height: 4.8,
      style: `--i:${i}`
    }));
  });

  svg.appendChild(s('text', {
    class: 'ws-plot__lab', x: plot.x + plot.w / 2, y: H - 18,
    text: 'SUBSTRATE CONCENTRATION \u2192'
  }));
  svg.appendChild(s('text', {
    class: 'ws-plot__lab ws-plot__lab--y', x: 12, y: plot.y + plot.h / 2,
    text: 'VELOCITY',
    transform: `rotate(-90 12 ${plot.y + plot.h / 2})`
  }));

  return block('plot', spec.title, svg);
}

/* --- verification checks -----------------------------------
   The glyph changes with the status as well as the colour, because a
   check that did not run and a check that passed must not be
   distinguishable by hue alone. */
const VER_GLYPH = { supported: '\u25C6', blocked: '\u2715', pending: '\u25CB', review: '\u25B2' };

function verifyBlock(spec) {
  return block('verify', spec.title,
    h('ul', { class: 'ws-ver' }, spec.items.map((it) => {
      const st = it.status || 'supported';
      return h('li', { class: 'ws-ver__i', dataset: { st } }, [
        h('span', { class: 'ws-ver__g', text: VER_GLYPH[st] || VER_GLYPH.supported }),
        h('span', { class: 'ws-ver__c', text: it.check }),
        h('span', { class: 'ws-ver__r mono', text: it.result })
      ]);
    })),
    spec.tone
  );
}

/* --- claim trace ------------------------------------------- */
function trailBlock(spec) {
  return block('trail', spec.title,
    h('ul', { class: 'ws-tr' }, spec.items.map((it) =>
      h('li', { class: 'ws-tr__i' }, [
        h('span', { class: 'ws-tr__c', text: it.claim }),
        h('span', { class: 'ws-tr__arrow mono', text: '\u2192' }),
        h('span', { class: 'ws-tr__b mono', text: it.basis })
      ])
    ))
  );
}

/* --- the disclosed assumption ------------------------------
   Given the loudest treatment in the workspace on purpose. It is
   the one item here that is not a success. */
function assumptionBlock(spec) {
  const blocked = spec.tone === 'blocked';
  return block('assumption', spec.title,
    h('div', { class: 'ws-as' }, [
      h('span', { class: 'ws-as__g', text: blocked ? '\u2715' : '\u25B2' }),
      h('p', { class: 'ws-as__t', text: spec.text })
    ]),
    spec.tone
  );
}

/* --- the finished record ----------------------------------- */
function recordBlock(spec) {
  return block('record', spec.title,
    h('ul', { class: 'ws-rec' }, spec.lines.map((l) =>
      h('li', { class: 'ws-rec__i', text: l })
    )),
    spec.tone
  );
}

const BUILD = {
  evidence: evidenceBlock,
  params: paramsBlock,
  plot: plotBlock,
  verify: verifyBlock,
  trail: trailBlock,
  assumption: assumptionBlock,
  record: recordBlock
};

/** Build one workspace block by key, or null if the key is unknown. */
export function buildBlock(key) {
  const spec = WORKSPACE[key];
  if (!spec) return null;
  const fn = BUILD[spec.kind];
  return fn ? fn(spec) : null;
}
