/* ============================================================
   caterva — Evidence Cathedral renderer
   Builds one tall SVG architecture from the config. Pure
   construction: no state transitions live here.
   ============================================================ */

import { s, primeDash } from '../lib/dom.js';
import {
  STAGE, QUESTION_CHAMBER, ARRAY_MODULES, EVIDENCE, ASSEMBLY, PARAMETERS,
  BERTH, VAULT, SENTINELS, CORE, RECORD, CURVE_MODEL, STATUS
} from '../config/architecture.js';
import {
  facetPath, chamberPath, facetedEllipse, vaultSpokes, routePath,
  elbowPath, fracturePath, kineticsSeries, plotToPath, plotPoint, envelopePath
} from '../lib/geometry.js';

/**
 * Interactive node scaffolding: focus ring + halo + a11y wiring.
 *
 * RECTANGLES ONLY, and that is now stated rather than branched on.
 *
 * This took a `shape` parameter and chose a circular ring when it was
 * `'circle'`. Nothing ever passed it. `shape` appeared exactly three
 * times in the whole `mule/` tree -- this parameter and its two
 * comparisons -- across ten call sites, and every box supplied is
 * `{x, y, w, h}`. So `shape` was always `undefined`, both ternaries
 * always took the else branch, and the circular half had never executed.
 *
 * Removing it cannot change what renders: that is a proof rather than an
 * expectation, since the condition was unsatisfiable. It was found by
 * type-checking this directory for the first time -- nine of the
 * seventeen findings were this one function, reported once per caller.
 *
 * If a circular node is ever added, this needs the branch back AND a
 * caller that passes the shape. Half of that arrangement, sitting here
 * unreachable, is indistinguishable from support that exists.
 *
 * @param {SVGGElement} group
 * @param {{ id: string, kind: string, name: string,
 *           box: { x: number, y: number, w: number, h: number } }} node
 */
function interactive(group, { id, kind, name, box }) {
  group.setAttribute('tabindex', '0');
  group.setAttribute('role', 'button');
  group.setAttribute('data-node', id);
  group.setAttribute('data-kind', kind);
  group.setAttribute('aria-label', name);
  const pad = 7;
  const ringBox = s('rect', {
    class: 'focus-ring',
    x: box.x - pad, y: box.y - pad,
    width: box.w + pad * 2, height: box.h + pad * 2,
  });
  const halo = s('rect', {
    class: 'halo',
    x: box.x - pad * 2, y: box.y - pad * 2,
    width: box.w + pad * 4, height: box.h + pad * 4,
  });
  group.appendChild(halo);
  group.appendChild(ringBox);
  return group;
}

/* ============================================================
   DEFS — depth gradients, masks. No decorative filters.
   ============================================================ */
function buildDefs() {
  return s('defs', {}, [
    s('linearGradient', { id: 'vaultDepth', x1: '0', y1: '0', x2: '0', y2: '1' }, [
      s('stop', { offset: '0', 'stop-color': '#2a2d35', 'stop-opacity': '0.2' }),
      s('stop', { offset: '0.5', 'stop-color': '#1f2127', 'stop-opacity': '0.86' }),
      s('stop', { offset: '1', 'stop-color': '#2a2d35', 'stop-opacity': '0.3' })
    ]),
    s('linearGradient', { id: 'chamberGlow', x1: '0', y1: '0', x2: '0', y2: '1' }, [
      s('stop', { offset: '0', 'stop-color': '#7f9dab', 'stop-opacity': '0.16' }),
      s('stop', { offset: '1', 'stop-color': '#7f9dab', 'stop-opacity': '0.01' })
    ]),
    s('linearGradient', { id: 'recordEdge', x1: '0', y1: '0', x2: '0', y2: '1' }, [
      s('stop', { offset: '0', 'stop-color': '#fdf8ee', 'stop-opacity': '1' }),
      s('stop', { offset: '1', 'stop-color': '#e4e3db', 'stop-opacity': '1' })
    ]),
    s('radialGradient', { id: 'coreDepth', cx: '0.5', cy: '0.5', r: '0.6' }, [
      s('stop', { offset: '0', 'stop-color': '#0f1a1a', 'stop-opacity': '1' }),
      s('stop', { offset: '1', 'stop-color': '#1f2127', 'stop-opacity': '1' })
    ]),

    /* Structural recess. Chambers are cut into mass rather than floating on
       it, so their interiors darken toward the top edge where the surrounding
       structure would occlude light. */
    s('linearGradient', { id: 'recess', x1: '0', y1: '0', x2: '0', y2: '1' }, [
      s('stop', { offset: '0', 'stop-color': '#000', 'stop-opacity': '0.5' }),
      s('stop', { offset: '0.55', 'stop-color': '#000', 'stop-opacity': '0.14' }),
      s('stop', { offset: '1', 'stop-color': '#0f1a1a', 'stop-opacity': '0.05' })
    ]),

    /* Teal bounce. Where evidence resolves, a little of that light falls on
       the architecture next to it. Illumination, never a glow effect. */
    s('radialGradient', { id: 'bounce', cx: '0.5', cy: '0.5', r: '0.5' }, [
      s('stop', { offset: '0', 'stop-color': '#7f9dab', 'stop-opacity': '0.2' }),
      s('stop', { offset: '0.6', 'stop-color': '#7f9dab', 'stop-opacity': '0.05' }),
      s('stop', { offset: '1', 'stop-color': '#7f9dab', 'stop-opacity': '0' })
    ]),
    s('radialGradient', { id: 'bounceReview', cx: '0.5', cy: '0.5', r: '0.5' }, [
      s('stop', { offset: '0', 'stop-color': '#d9ad6a', 'stop-opacity': '0.17' }),
      s('stop', { offset: '0.6', 'stop-color': '#d9ad6a', 'stop-opacity': '0.04' }),
      s('stop', { offset: '1', 'stop-color': '#d9ad6a', 'stop-opacity': '0' })
    ]),

    /* Fine internal grid for chamber interiors — machined, not decorative. */
    s('pattern', {
      id: 'micrograte', width: '8', height: '8', patternUnits: 'userSpaceOnUse'
    }, [
      s('path', {
        d: 'M 8 0 L 0 0 L 0 8', fill: 'none',
        stroke: 'rgba(213, 225, 230,0.055)', 'stroke-width': '0.5'
      })
    ]),

    /* The lateral void is composed, not empty: distant structure falls off
       toward the edges of the field so the monument sits in atmosphere. */
    s('linearGradient', { id: 'distantFade', x1: '0', y1: '0', x2: '1', y2: '0' }, [
      s('stop', { offset: '0', 'stop-color': '#1f2127', 'stop-opacity': '1' }),
      s('stop', { offset: '0.34', 'stop-color': '#1f2127', 'stop-opacity': '0' }),
      s('stop', { offset: '0.66', 'stop-color': '#1f2127', 'stop-opacity': '0' }),
      s('stop', { offset: '1', 'stop-color': '#1f2127', 'stop-opacity': '1' })
    ])
  ]);
}

/* ============================================================
   DISTANT STRUCTURE — the depth layer behind the architecture

   A 1000-unit-wide portrait monument cannot fill a landscape
   screen, and the fitted wide frame left a large lateral void with
   nothing composed in it. This layer occupies that space with
   structure that is unmistakably *behind* the working architecture:
   buttress ribs carrying the tiers outward to ground, survey arcs
   around the vault, and datum rules. It parallaxes slightly on
   desktop, which is what makes the monument read as built rather
   than drawn.
   ============================================================ */
function buildDistant() {
  const g = s('g', { class: 'distant', 'aria-hidden': 'true' });

  // Buttress ribs: mass carrying each tier laterally out of frame.
  const ribs = s('g', { class: 'distant-ribs' });
  [
    { y: 300, spread: 470, drop: 250 },
    { y: 650, spread: 560, drop: 300 },
    { y: 1080, spread: 640, drop: 340 },
    { y: 1470, spread: 540, drop: 220 }
  ].forEach(({ y, spread, drop }) => {
    [-1, 1].forEach((dir) => {
      const x0 = STAGE.spine + dir * 300;
      const x1 = STAGE.spine + dir * spread;
      ribs.appendChild(s('path', {
        class: 'distant-line',
        d: `M ${x0} ${y} L ${x1} ${y + drop * 0.35} L ${x1} ${y + drop}`
      }));
      ribs.appendChild(s('path', {
        class: 'distant-line',
        d: `M ${x0} ${y + 26} L ${x1 - dir * 40} ${y + drop * 0.4 + 26}`,
        opacity: 0.5
      }));
    });
  });
  g.appendChild(ribs);

  // Survey arcs concentric to the vault: the checking apparatus implied at
  // architectural scale, far behind the sentinels themselves.
  const arcs = s('g', { class: 'distant-arcs' });
  [420, 520, 620].forEach((r, i) => {
    arcs.appendChild(s('path', {
      class: 'distant-line',
      d: facetedEllipse(STAGE.spine, 1100, r, r * 0.78, 24, i * 0.13),
      opacity: 0.44 - i * 0.1
    }));
  });
  g.appendChild(arcs);

  // Datum rules: the survey grid the monument was set out on.
  const datum = s('g', { class: 'distant-datum' });
  for (let x = -600; x <= 1600; x += 200) {
    if (x > 60 && x < 940) continue;
    datum.appendChild(s('line', {
      class: 'distant-line', x1: x, y1: -120, x2: x, y2: STAGE.h + 120, opacity: 0.3
    }));
  }
  g.appendChild(datum);

  return g;
}

/* ============================================================
   SHEET — the margin of the elevation drawing

   The wide shot has to letterbox: the monument is 1000 x 1680 and
   screens are landscape. Rather than fight that with empty void,
   the margins carry what the margin of a real setting-out drawing
   carries — the run identity, the tier schedule, a vertical scale
   with elevations, and the disclosure that this is illustrative.
   ============================================================ */
function buildSheet() {
  const g = s('g', { class: 'sheet', 'aria-hidden': 'true' });
  const L = -560;          // left margin column
  const R = STAGE.w + 560; // right margin column

  // Left: sheet identity block.
  g.appendChild(s('line', { class: 'sheet-rule', x1: L, y1: 150, x2: L + 330, y2: 150 }));
  g.appendChild(s('text', { class: 'sheet-note', x: L, y: 138, text: 'CATERVA / EVIDENCE CATHEDRAL' }));
  g.appendChild(s('text', {
    class: 'sheet-note', x: L, y: 176, text: 'RUN 0007 \u2014 ILLUSTRATIVE',
    style: 'font-size:7.4px', opacity: 0.72
  }));

  // Left: the tier schedule — the architecture indexed as a drawing legend.
  [
    ['01', 'QUESTION'], ['02', 'INTERPRETATION'], ['03', 'CONFIGURATION'],
    ['04', 'VERIFICATION'], ['05', 'EXECUTION'], ['06', 'RECORD']
  ].forEach(([n, label], i) => {
    const y = 250 + i * 30;
    g.appendChild(s('text', {
      class: 'sheet-note', x: L, y, text: n, style: 'font-size:7.4px', opacity: 0.6
    }));
    g.appendChild(s('text', {
      class: 'sheet-note', x: L + 34, y, text: label, style: 'font-size:7.4px'
    }));
  });

  // Left: vertical elevation scale, read against the monument's own height.
  const sTop = 470;
  const sBot = 1600;
  g.appendChild(s('line', { class: 'sheet-rule', x1: L + 6, y1: sTop, x2: L + 6, y2: sBot }));
  for (let y = sTop; y <= sBot; y += 113) {
    const major = Math.round((y - sTop) / 113) % 2 === 0;
    g.appendChild(s('line', {
      class: 'sheet-rule', x1: L + 6, y1: y, x2: L + (major ? 22 : 14), y2: y
    }));
    if (major) {
      g.appendChild(s('text', {
        class: 'sheet-note', x: L + 30, y: y + 3,
        text: `+${String(Math.round((sBot - y) / 10) * 10).padStart(4, '0')}`,
        style: 'font-size:6.4px', opacity: 0.5
      }));
    }
  }

  // Right: the section note. States plainly what the drawing depicts.
  g.appendChild(s('line', { class: 'sheet-rule', x1: R - 330, y1: 150, x2: R, y2: 150 }));
  g.appendChild(s('text', {
    class: 'sheet-note', x: R, y: 138, 'text-anchor': 'end', text: 'LONGITUDINAL SECTION'
  }));
  [
    'ONE QUESTION ENTERS AT TIER 01.',
    'EVIDENCE IS RETRIEVED, ROUTED AND DOCKED.',
    'GENERATION OCCURS AT THE CORE.',
    'FOUR CHECKS SURROUND IT.',
    'A SCIENTIFIC RECORD LEAVES AT TIER 06.'
  ].forEach((line, i) => {
    g.appendChild(s('text', {
      class: 'sheet-note', x: R, y: 180 + i * 22, 'text-anchor': 'end',
      text: line, style: 'font-size:7.4px', opacity: 0.66
    }));
  });

  // Right: the honesty note, in the position a drawing carries its status.
  g.appendChild(s('line', { class: 'sheet-rule', x1: R - 330, y1: 1520, x2: R, y2: 1520 }));
  g.appendChild(s('text', {
    class: 'sheet-note', x: R, y: 1548, 'text-anchor': 'end',
    text: 'ILLUSTRATIVE DEMONSTRATION', style: 'font-size:7.4px'
  }));
  g.appendChild(s('text', {
    class: 'sheet-note', x: R, y: 1568, 'text-anchor': 'end',
    text: 'NOT AN EXPERIMENTAL RESULT', style: 'font-size:7.4px', opacity: 0.66
  }));
  g.appendChild(s('text', {
    class: 'sheet-note', x: R, y: 1596, 'text-anchor': 'end',
    text: 'PRE-VALIDATION / SEEKING PILOT PARTNERS',
    style: 'font-size:6.4px', opacity: 0.5
  }));

  return g;
}

/* ============================================================
   SUBSTRATE — coordinate grid + the vertical spine
   ============================================================ */
function buildSubstrate() {
  const g = s('g', { class: 'substrate', 'aria-hidden': 'true' });

  // sparse coordinate rules: architectural, not a background texture
  const rules = s('g', { class: 'grid-rules' });
  for (let x = 100; x < STAGE.w; x += 100) {
    rules.appendChild(s('line', {
      class: 'hair', x1: x, y1: 40, x2: x, y2: STAGE.h - 40,
      opacity: x === STAGE.spine ? 0 : 0.35
    }));
  }
  for (let y = 120; y < STAGE.h; y += 120) {
    rules.appendChild(s('line', { class: 'hair', x1: 60, y1: y, x2: STAGE.w - 60, y2: y, opacity: 0.22 }));
  }
  g.appendChild(rules);

  // Tier registration ticks down the right edge. Deliberately unlettered:
  // text pinned to the stage edge cannot survive the camera cropping into
  // a tier, and it arrived half-cut. The monumental tier titles name the
  // tiers in the wide shot; the framing controls name them when close.
  const marks = s('g', { class: 'tier-marks' });
  [212, 500, 820, 1360, 1560].forEach((y) => {
    marks.appendChild(s('line', { class: 'hair', x1: STAGE.w - 40, y1: y, x2: STAGE.w - 8, y2: y }));
    marks.appendChild(s('line', {
      class: 'hair', x1: STAGE.w - 8, y1: y - 7, x2: STAGE.w - 8, y2: y + 7
    }));
  });
  g.appendChild(marks);

  /* Tier naming in the wide shot. Previously these were monumental 30px
     titles set beside the structure; they competed with the architecture for
     attention and read as a label layer stuck on top of it. The tier schedule
     now lives in the sheet margin where a drawing's legend belongs, so here
     only a quiet index mark remains, pinned to the structure it names. */
  const lod = s('g', { class: 'tier-titles' });
  // Annotated because the literal mixes numbers and strings, so `y` infers
  // as `string | number` and `y - 3` below is unchecked. Every entry is a
  // number today; the annotation is what keeps that true.
  /** @type {Array<[number, string]>} */ ([
    [212, '01'], [470, '02'], [800, '03'], [1330, '04'], [1394, '05'], [1640, '06']
  ]).forEach(([y, index]) => {
    lod.appendChild(s('text', {
      class: 'tier-title-index', x: 118, y, 'text-anchor': 'end', text: `TIER ${index}`
    }));
    lod.appendChild(s('line', { class: 'hair', x1: 128, y1: y - 3, x2: 150, y2: y - 3, opacity: 0.5 }));
  });
  g.appendChild(lod);

  /* The spine. Not a connector line but the monument's structural axis:
     a narrow shaft with its own walls, cross-braced at each tier boundary,
     carrying the flow of logic from chamber to record. Everything in the
     cathedral is symmetric about it. */
  const spineTop = 196;
  const spineBot = STAGE.h - 46;
  const spineG = s('g', { class: 'spine' });

  // shaft walls
  [-5, 5].forEach((dx) => {
    spineG.appendChild(s('line', {
      class: 'spine-wall', x1: STAGE.spine + dx, y1: spineTop,
      x2: STAGE.spine + dx, y2: spineBot
    }));
  });

  // cross-bracing at tier boundaries: the axis is assembled, not drawn
  [260, 470, 546, 800, 842, 1214, 1330, 1394].forEach((y) => {
    spineG.appendChild(s('path', {
      class: 'spine-brace',
      d: `M ${STAGE.spine - 13} ${y - 6} L ${STAGE.spine - 5} ${y} L ${STAGE.spine - 13} ${y + 6}
          M ${STAGE.spine + 13} ${y - 6} L ${STAGE.spine + 5} ${y} L ${STAGE.spine + 13} ${y + 6}`
    }));
  });

  const spineD = `M ${STAGE.spine} ${spineTop} L ${STAGE.spine} ${spineBot}`;
  spineG.appendChild(s('path', { class: 'spine-line', d: spineD }));
  spineG.appendChild(s('path', { class: 'spine-flow', d: spineD }));
  g.appendChild(spineG);

  return g;
}

/* Small engraved metadata. Real machines carry their own identifying marks;
   these name coordinates, tier indices and datum references. Only legible
   when the camera is close, which is what makes close inspection rewarding. */
function engrave(x, y, text, opts = {}) {
  return s('text', {
    class: 'engraving', x, y, text,
    'text-anchor': opts.anchor || 'start',
    transform: opts.rotate ? `rotate(${opts.rotate} ${x} ${y})` : null
  });
}

/* ============================================================
   TIER 01 — QUESTION CHAMBER
   ============================================================ */
function buildQuestionChamber(question) {
  const cfg = QUESTION_CHAMBER;
  const { box } = cfg;
  const g = s('g', { class: 'tier tier--question node', 'data-state': 'dormant', 'data-tier': 'question' });

  // The chamber is cut into structure: recess shading first, then the fine
  // internal grating of a machined interior, then the shell edge on top.
  g.appendChild(s('path', {
    class: 'node-recess', d: chamberPath(box, cfg.inset), fill: 'url(#recess)', stroke: 'none'
  }));
  g.appendChild(s('path', {
    class: 'node-grate', d: chamberPath(box, cfg.inset), fill: 'url(#micrograte)', stroke: 'none'
  }));
  g.appendChild(s('path', { class: 'node-shell', d: chamberPath(box, cfg.inset) }));
  g.appendChild(s('path', {
    class: 'node-mech', d: chamberPath({ x: box.x + 16, y: box.y + 12, w: box.w - 32, h: box.h - 10 }, cfg.inset),
    fill: 'url(#chamberGlow)', stroke: 'none'
  }));
  // A second, inset shell line: layered linework reads as thickness.
  g.appendChild(s('path', {
    class: 'node-liner',
    d: chamberPath({ x: box.x + 7, y: box.y + 5, w: box.w - 14, h: box.h - 8 }, cfg.inset - 6)
  }));

  // language being accepted: horizontal intake striations
  const intake = s('g', { class: 'node-mech' });
  for (let i = 0; i < 5; i += 1) {
    intake.appendChild(s('line', {
      class: 'hair', x1: box.x + 26 + i * 6, y1: box.y + 8,
      x2: box.x + 26 + i * 6, y2: box.y + 22, opacity: 0.5
    }));
    intake.appendChild(s('line', {
      class: 'hair', x1: box.x + box.w - 26 - i * 6, y1: box.y + 8,
      x2: box.x + box.w - 26 - i * 6, y2: box.y + 22, opacity: 0.5
    }));
  }
  g.appendChild(intake);

  g.appendChild(s('text', { class: 't-label node-label', x: box.x, y: box.y - 16, text: cfg.label }));
  g.appendChild(s('text', {
    class: 't-micro node-out', x: box.x + box.w, y: box.y - 16,
    'text-anchor': 'end', text: cfg.state
  }));

  // the question itself, wrapped as accepted language
  const textGroup = s('text', { class: 't-display', x: box.x + box.w / 2, y: box.y + 48, 'text-anchor': 'middle', 'data-question-text': '' });
  wrapQuestion(textGroup, question, box.x + box.w / 2);
  g.appendChild(textGroup);

  // aperture: where language leaves as structure
  g.appendChild(s('path', {
    class: 'node-inner', d: `M ${box.x + box.w / 2 - 16} ${box.y + box.h} L ${box.x + box.w / 2} ${box.y + box.h + 14} L ${box.x + box.w / 2 + 16} ${box.y + box.h}`
  }));

  /* Concept isolation. Stage 02 separates scientific quantities from the
     sentence, so the isolated terms are racked in the chamber's lower bay,
     directly beneath the language they came from and above the aperture they
     leave through. Below the chamber they collided with the interpretation
     array's own label; inside, the containment is the point — the terms are
     still in the intake, already structured. */
  const concepts = s('g', { class: 'concepts' });
  const rackY = box.y + 83;
  const terms = ['SUBSTRATE CONCENTRATION', 'ENZYME VELOCITY', 'DEPENDENCE'];
  const plateW = (t) => t.length * 4.3 + 16;
  const gap = 10;
  const total = terms.reduce((n, t) => n + plateW(t), 0) + gap * (terms.length - 1);
  let cx = STAGE.spine - total / 2;
  terms.forEach((t, i) => {
    const w = plateW(t);
    const cg = s('g', { class: 'concept', style: `--d:${i * 150}ms` });
    cg.appendChild(s('path', {
      class: 'concept-plate', d: facetPath({ x: cx, y: rackY, w, h: 15 }, 4)
    }));
    cg.appendChild(s('text', {
      class: 't-micro concept-text', x: cx + w / 2, y: rackY + 10.5,
      'text-anchor': 'middle', text: t, style: 'font-size:6.4px'
    }));
    // riser down to the aperture: these terms are what leaves as structure
    cg.appendChild(s('path', {
      class: 'hair concept-riser',
      d: `M ${cx + w / 2} ${rackY + 15} L ${cx + w / 2} ${rackY + 22}
          L ${STAGE.spine} ${rackY + 30}`
    }));
    concepts.appendChild(cg);
    cx += w + gap;
  });
  // What the parse produced, stated once rather than tagged on every plate.
  concepts.appendChild(s('text', {
    class: 'engraving', x: STAGE.spine - total / 2 - 9, y: rackY + 10.5,
    'text-anchor': 'end', text: 'ISOLATED'
  }));
  g.appendChild(concepts);

  // engraved chamber metadata, legible only close in
  g.appendChild(engrave(box.x, box.y - 4, 'CH-01 / LANGUAGE INTAKE'));
  g.appendChild(engrave(box.x + box.w, box.y - 4, `DATUM ${STAGE.spine}`, { anchor: 'end' }));

  interactive(g, {
    id: cfg.id, kind: 'chamber', name: `Question chamber. ${question}`, box
  });
  return g;
}

/** Wrap the question into up to 3 tspans. */
/** Leading for the chamber's question type. Shared so a re-wrapped question
    can never drift from the leading used at first render. */
export const QUESTION_LEADING = 22;

export function wrapQuestion(textEl, question, cx, lineH = QUESTION_LEADING) {
  while (textEl.firstChild) textEl.removeChild(textEl.firstChild);
  const words = String(question).trim().split(/\s+/);
  const lines = [];
  let cur = '';
  const max = 34;
  words.forEach((w) => {
    if ((cur + ' ' + w).trim().length > max) {
      lines.push(cur.trim());
      cur = w;
    } else {
      cur = `${cur} ${w}`;
    }
  });
  if (cur.trim()) lines.push(cur.trim());
  const shown = lines.slice(0, 3);
  if (lines.length > 3) shown[2] = `${shown[2].slice(0, 30)}\u2026`;
  shown.forEach((line, i) => {
    textEl.appendChild(s('tspan', { x: cx, dy: i === 0 ? 0 : lineH, text: line }));
  });
  const offset = (shown.length - 1) * lineH * 0.5;
  textEl.setAttribute('transform', `translate(0 ${-offset})`);
}

/* ============================================================
   TIER 02 — INTERPRETATION ARRAY
   Four faceted modules, each with a distinct internal mechanism.
   ============================================================ */
function moduleMechanism(kind, box) {
  const cx = box.x + box.w / 2;
  const cy = box.y + box.h * 0.52;
  const g = s('g', { class: 'node-mech' });

  if (kind === 'lens') {
    // Model Picker: a rotating selection lens narrowing on one option.
    g.appendChild(s('g', { class: 'mech-lens' }, [
      s('path', { class: 'struct', d: facetedEllipse(cx, cy, 26, 26, 6) }),
      s('path', { class: 'hair', d: facetedEllipse(cx, cy, 16, 16, 6, 0.5) }),
      s('line', { class: 'hair', x1: cx - 30, y1: cy, x2: cx + 30, y2: cy })
    ]));
    g.appendChild(s('circle', { cx, cy, r: 3.2, fill: 'var(--signal-teal)' }));
  }

  if (kind === 'stack') {
    // Literature Retrieval: a stack of sheets fanning open.
    const stack = s('g', { class: 'mech-stack' });
    for (let i = 0; i < 3; i += 1) {
      stack.appendChild(s('rect', {
        x: cx - 17, y: cy - 16 + i * 11, width: 34, height: 8,
        fill: 'rgba(157, 184, 196,0.14)', stroke: 'var(--mineral-teal)',
        'stroke-width': 1, 'vector-effect': 'non-scaling-stroke'
      }));
    }
    g.appendChild(stack);
  }

  if (kind === 'lattice') {
    // Configuration: a parameter lattice locking into a grid.
    const lat = s('g', { class: 'mech-lattice' });
    for (let i = 0; i < 4; i += 1) {
      lat.appendChild(s('line', {
        class: 'hair', x1: cx - 24 + i * 16, y1: cy - 20,
        x2: cx - 24 + i * 16, y2: cy + 20, opacity: 0.3
      }));
      lat.appendChild(s('line', {
        class: 'hair', x1: cx - 26, y1: cy - 20 + i * 13,
        x2: cx + 26, y2: cy - 20 + i * 13, opacity: 0.3
      }));
    }
    [[-8, -7], [8, 6], [-16, 6], [16, -7]].forEach(([dx, dy]) => {
      lat.appendChild(s('rect', {
        x: cx + dx - 3, y: cy + dy - 3, width: 6, height: 6,
        fill: 'var(--mineral-teal)', opacity: 0.85
      }));
    });
    g.appendChild(lat);
  }

  if (kind === 'switch') {
    // Compute Router: a switch arm selecting one of three substrates.
    const sw = s('g', { class: 'mech-switch' });
    sw.appendChild(s('line', { class: 'hair', x1: cx - 26, y1: cy + 20, x2: cx + 26, y2: cy + 20 }));
    [-22, 0, 22].forEach((dx, i) => {
      sw.appendChild(s('rect', {
        x: cx + dx - 5, y: cy + 17, width: 10, height: 7,
        fill: i === 1 ? 'var(--signal-teal)' : 'none',
        stroke: 'var(--structural-slate)', 'stroke-width': 1,
        'vector-effect': 'non-scaling-stroke'
      }));
    });
    sw.appendChild(s('line', {
      class: 'switch-arm struct', x1: cx, y1: cy - 20, x2: cx, y2: cy + 16,
      stroke: 'var(--mineral-teal)'
    }));
    sw.appendChild(s('circle', { cx, cy: cy - 20, r: 2.6, fill: 'var(--mineral-teal)' }));
    g.appendChild(sw);
  }

  return g;
}

function cornerLocks(box) {
  const g = s('g', { class: 'node-lock' });
  const t = 6;
  [[box.x, box.y, 1, 1], [box.x + box.w, box.y, -1, 1],
   [box.x, box.y + box.h, 1, -1], [box.x + box.w, box.y + box.h, -1, -1]]
    .forEach(([px, py, sx, sy]) => {
      g.appendChild(s('path', {
        d: `M ${px} ${py + t * sy} L ${px} ${py} L ${px + t * sx} ${py}`,
        stroke: 'var(--signal-teal)', 'stroke-width': 1.4, fill: 'none',
        'vector-effect': 'non-scaling-stroke'
      }));
    });
  return g;
}

function buildInterpretationArray() {
  const tier = s('g', { class: 'tier tier--array', 'data-tier': 'array' });

  tier.appendChild(s('text', {
    class: 't-micro', x: 148, y: 232, text: 'INTERPRETATION ARRAY'
  }));
  tier.appendChild(s('line', { class: 'hair', x1: 148, y1: 240, x2: 864, y2: 240 }));

  ARRAY_MODULES.forEach((mod) => {
    const { box } = mod;
    const g = s('g', {
      class: 'node module', 'data-state': 'dormant', 'data-module': mod.id
    });

    g.appendChild(s('path', { class: 'node-shell', d: facetPath(box, 16) }));
    g.appendChild(s('path', {
      class: 'node-inner',
      d: facetPath({ x: box.x + 9, y: box.y + 9, w: box.w - 18, h: box.h - 18 }, 11)
    }));
    g.appendChild(moduleMechanism(mod.silhouette, box));
    g.appendChild(cornerLocks(box));

    // header: index + label
    g.appendChild(s('text', { class: 't-micro', x: box.x + 12, y: box.y + 22, text: mod.index }));
    g.appendChild(s('text', {
      class: 't-micro node-label', x: box.x + box.w - 12, y: box.y + 22,
      'text-anchor': 'end', text: mod.label.split(' ')[0]
    }));

    // output readout below the module
    const out = s('g', { class: 'node-out' });
    out.appendChild(s('line', {
      class: 'hair', x1: box.x, y1: box.y + box.h + 16, x2: box.x + box.w, y2: box.y + box.h + 16,
      stroke: 'var(--line-structural)'
    }));
    out.appendChild(s('text', { class: 't-micro', x: box.x, y: box.y + box.h + 32, text: mod.output.label }));
    const val = s('text', { class: 't-value', x: box.x, y: box.y + box.h + 48 });
    const words = mod.output.value.split(' ');
    let line = '';
    const lines = [];
    words.forEach((w) => {
      if ((line + ' ' + w).trim().length > 20) { lines.push(line.trim()); line = w; }
      else line = `${line} ${w}`;
    });
    if (line.trim()) lines.push(line.trim());
    // Two lines maximum: the readout must not reach down into the
    // Configuration Assembly label below.
    const shown = lines.slice(0, 2);
    if (lines.length > 2) shown[1] = `${shown[1]}\u2026`;
    shown.forEach((l, i) => {
      val.appendChild(s('tspan', { x: box.x, dy: i === 0 ? 0 : 14, text: l }));
    });
    out.appendChild(val);
    g.appendChild(out);

    interactive(g, { id: mod.id, kind: 'module', name: `${mod.name} agent. ${mod.output.label}: ${mod.output.value}`, box });
    tier.appendChild(g);
  });

  return tier;
}

/* ============================================================
   EVIDENCE LAYER — routes + travelling artifacts
   ============================================================ */
function evidenceForm(form) {
  // Each evidence object is a small architectural artifact.
  const g = s('g', {});
  if (form === 'sheet') {
    g.appendChild(s('path', {
      class: 'ev-body', d: 'M -13 -8 L 9 -8 L 13 -4 L 13 8 L -13 8 Z'
    }));
    g.appendChild(s('line', { class: 'hair', x1: -8, y1: -2, x2: 6, y2: -2, stroke: 'var(--fog-teal)', opacity: 0.6 }));
    g.appendChild(s('line', { class: 'hair', x1: -8, y1: 3, x2: 2, y2: 3, stroke: 'var(--fog-teal)', opacity: 0.4 }));
  } else if (form === 'shard') {
    g.appendChild(s('path', { class: 'ev-body', d: 'M 0 -10 L 13 -3 L 9 9 L -9 9 L -13 -3 Z' }));
    g.appendChild(s('path', { class: 'hair', d: 'M 0 -10 L 0 9 M -13 -3 L 13 -3', stroke: 'var(--fog-teal)', opacity: 0.45 }));
  } else {
    g.appendChild(s('path', { class: 'ev-body', d: 'M -13 -7 L 13 -7 L 13 7 L -13 7 Z' }));
    g.appendChild(s('circle', { cx: 0, cy: 0, r: 3, class: 'ev-tag' }));
    g.appendChild(s('line', { class: 'hair', x1: -13, y1: 0, x2: -5, y2: 0, stroke: 'var(--fog-teal)', opacity: 0.5 }));
    g.appendChild(s('line', { class: 'hair', x1: 5, y1: 0, x2: 13, y2: 0, stroke: 'var(--fog-teal)', opacity: 0.5 }));
  }
  return g;
}

function buildEvidenceLayer() {
  const tier = s('g', { class: 'tier tier--evidence', 'data-tier': 'evidence' });

  /* Bounce light. When an evidence object lands in its dock, a little of that
     resolution falls on the structure immediately around it. This is the only
     place in the cathedral where light is emitted rather than reflected, and it
     is emitted by the one event that earns it: a claim meeting its basis. Sized
     to the neighbouring berth, not to the artifact, because the point is what
     the evidence illuminates rather than the evidence itself. */
  const bounces = s('g', { class: 'ev-bounces', 'aria-hidden': 'true' });
  EVIDENCE.forEach((ev) => {
    bounces.appendChild(s('ellipse', {
      class: 'ev-bounce', 'data-bounce': ev.id,
      cx: ev.dock.x, cy: ev.dock.y, rx: 104, ry: 74, fill: 'url(#bounce)'
    }));
  });
  tier.appendChild(bounces);

  // defined routes first, so artifacts sit above them
  const routes = s('g', { class: 'evidence-routes' });
  EVIDENCE.forEach((ev) => {
    routes.appendChild(s('path', {
      class: 'evidence-route',
      d: routePath(ev.origin, ev.dock, { bend: 0.62 })
    }));
  });
  tier.appendChild(routes);

  /* Empty cradles, cut before anything arrives. An artifact that simply stops
     at a coordinate reads as drifting; an artifact that drops into a machined
     berth reads as seated. The cradle is the reason the arrival lands. */
  const cradles = s('g', { class: 'ev-cradles', 'aria-hidden': 'true' });
  EVIDENCE.forEach((ev) => {
    const { x, y } = ev.dock;
    cradles.appendChild(s('path', {
      class: 'ev-dock', 'data-dock-for': ev.id,
      d: `M ${x - 19} ${y - 13} L ${x - 19} ${y + 13} L ${x + 19} ${y + 13} L ${x + 19} ${y - 13}`
    }));
  });
  tier.appendChild(cradles);

  EVIDENCE.forEach((ev) => {
    const g = s('g', { class: 'evidence', 'data-evidence': ev.id });
    const carrier = s('g', {
      class: 'ev-carrier',
      transform: `translate(${ev.origin.x} ${ev.origin.y})`,
      'data-origin': `${ev.origin.x},${ev.origin.y}`,
      'data-dock': `${ev.dock.x},${ev.dock.y}`
    });
    // Collar that contracts onto the artifact at the moment of seating.
    carrier.appendChild(s('path', {
      class: 'ev-seat',
      d: 'M -17 -11 L -11 -11 M 11 -11 L 17 -11 M -17 11 L -11 11 M 11 11 L 17 11'
        + ' M -17 -11 L -17 -5 M -17 11 L -17 5 M 17 -11 L 17 -5 M 17 11 L 17 5'
    }));
    carrier.appendChild(evidenceForm(ev.form));
    // Clamps holding it in the cradle once it has arrived.
    carrier.appendChild(s('path', {
      class: 'ev-clamp',
      d: 'M -19 -13 L -14 -13 M -19 13 L -14 13 M 19 -13 L 14 -13 M 19 13 L 14 13'
    }));

    // Labels stack centred beneath the artifact, inside the open channel
    // between the berth column and the assembly core, so they never run
    // across a parameter plate.
    const dir = ev.tie === 'left' ? -1 : 1;
    const lbl = s('g', { class: 'ev-label' });
    lbl.appendChild(s('text', {
      class: 't-micro', x: 0, y: 22, 'text-anchor': 'middle',
      text: ev.label, fill: 'var(--fog-teal)'
    }));
    lbl.appendChild(s('text', {
      class: 't-micro', x: 0, y: 32, 'text-anchor': 'middle',
      text: ev.sub, opacity: 0.7, style: 'font-size:7px'
    }));
    // short structural tie toward the parameter this evidence supports
    lbl.appendChild(s('line', {
      class: 'hair', x1: 15 * dir, y1: 0, x2: 34 * dir, y2: 0,
      stroke: 'var(--deep-teal)'
    }));
    carrier.appendChild(lbl);

    /* Scope tag, hung off the artifact like a physical label on a specimen.
       Close range only, and set to the short `tag` string: the channel between
       the berth column and the core is ~106px, and the full scope statement ran
       straight across the parameter plates on both sides. The inspector carries
       the complete wording; the artifact carries only what fits legibly on it. */
    const scope = s('g', { class: 'ev-scope' });
    scope.appendChild(s('line', {
      class: 'hair', x1: 0, y1: 36, x2: 0, y2: 42, stroke: 'var(--deep-teal)'
    }));
    scope.appendChild(s('text', {
      class: 't-micro', x: 0, y: 50, 'text-anchor': 'middle',
      text: ev.tag, opacity: 0.6, style: 'font-size:6.2px'
    }));
    carrier.appendChild(scope);

    g.appendChild(carrier);

    const box = { x: ev.dock.x - 16, y: ev.dock.y - 12, w: 32, h: 24 };
    interactive(g, {
      id: ev.id, kind: 'evidence',
      name: `Evidence object. ${ev.label} — ${ev.sub}. Scope: ${ev.scope}. Illustrative record.`,
      box
    });
    tier.appendChild(g);
  });

  return tier;
}

/* ============================================================
   TIER 03 — CONFIGURATION ASSEMBLY
   ============================================================ */
function buildAssembly() {
  const tier = s('g', { class: 'tier tier--assembly', 'data-tier': 'assembly' });
  const { box, core } = ASSEMBLY;

  // outer assembly frame — open-sided, not a card
  tier.appendChild(s('path', {
    class: 'struct',
    d: `M ${box.x} ${box.y + 26} L ${box.x} ${box.y} L ${box.x + 92} ${box.y}
        M ${box.x + box.w - 92} ${box.y} L ${box.x + box.w} ${box.y} L ${box.x + box.w} ${box.y + 26}
        M ${box.x} ${box.y + box.h - 26} L ${box.x} ${box.y + box.h} L ${box.x + 92} ${box.y + box.h}
        M ${box.x + box.w - 92} ${box.y + box.h} L ${box.x + box.w} ${box.y + box.h} L ${box.x + box.w} ${box.y + box.h - 26}`
  }));
  tier.appendChild(s('text', { class: 't-micro', x: box.x, y: box.y - 12, text: ASSEMBLY.label }));

  // central core mechanism: concentric faceted rings
  const coreG = s('g', { class: 'assembly-core' });
  coreG.appendChild(s('path', { class: 'core-ring core-ring--a', d: facetedEllipse(core.x, core.y, core.r, core.r, 12) }));
  coreG.appendChild(s('path', { class: 'core-ring core-ring--b', d: facetedEllipse(core.x, core.y, core.r - 16, core.r - 16, 8, 0.4) }));
  coreG.appendChild(s('path', {
    class: 'hair', d: vaultSpokes(core.x, core.y, { rx: core.r, ry: core.r }, { rx: core.r - 16, ry: core.r - 16 }, 12)
  }));
  coreG.appendChild(s('circle', { cx: core.x, cy: core.y, r: 4, fill: 'var(--signal-teal)', opacity: 0.9 }));
  tier.appendChild(coreG);

  // parameter berths flanking the core
  PARAMETERS.forEach((p) => {
    const x = p.side === 'left' ? BERTH.leftX : BERTH.rightX;
    const y = BERTH.ys[p.slot];
    const bx = x - BERTH.w / 2;
    const by = y - BERTH.h / 2;
    const box2 = { x: bx, y: by, w: BERTH.w, h: BERTH.h };

    const g = s('g', { class: 'berth', 'data-param': p.id, 'data-status': p.status });

    g.appendChild(s('path', { class: 'berth-slot', d: facetPath(box2, 9) }));

    // parameter unit travels inward from outside the frame
    const dx = p.side === 'left' ? -70 : 70;
    const param = s('g', { class: 'param', transform: `translate(${dx} 0)`, style: `transform: translate(${dx}px, 0px)` });
    param.appendChild(s('path', { class: 'param-plate', d: facetPath(box2, 9) }));
    param.appendChild(s('text', { class: 't-symbol', x: bx + 12, y: y + 5, text: p.symbol }));
    param.appendChild(s('text', {
      class: 't-value', x: bx + BERTH.w - 12, y: y - 3, 'text-anchor': 'end', text: p.value
    }));
    param.appendChild(s('text', {
      class: 't-micro param-name', x: bx + BERTH.w - 12, y: y + 12, 'text-anchor': 'end',
      text: STATUS[p.status].word
    }));
    param.appendChild(s('text', {
      class: 'status-glyph', x: bx + 12, y: y - 12, text: STATUS[p.status].glyph
    }));
    // connection stub toward the core
    const stubX = p.side === 'left' ? bx + BERTH.w : bx;
    const stubDir = p.side === 'left' ? 1 : -1;
    param.appendChild(s('line', {
      class: 'hair', x1: stubX, y1: y, x2: stubX + 26 * stubDir, y2: y,
      stroke: 'var(--line-structural)'
    }));
    g.appendChild(param);

    interactive(g, {
      id: p.id, kind: 'parameter',
      name: `Parameter ${p.symbol}, ${p.name}. Value ${p.value}. Status: ${STATUS[p.status].word}. ${p.basis}`,
      box: box2
    });
    tier.appendChild(g);
  });

  // assembly node itself is inspectable
  const holder = s('g', { class: 'node assembly-node', 'data-state': 'dormant' });
  holder.appendChild(s('rect', {
    x: box.x + 120, y: box.y - 2, width: box.w - 240, height: 18, fill: 'transparent'
  }));
  interactive(holder, {
    id: ASSEMBLY.id, kind: 'assembly', name: 'Configuration assembly. Six parameters docked.',
    box: { x: box.x + 120, y: box.y - 2, w: box.w - 240, h: 18 }
  });
  tier.appendChild(holder);

  return tier;
}

/* ============================================================
   TIER 04 — THE VERIFICATION VAULT
   ============================================================ */
function buildVault() {
  const tier = s('g', { class: 'tier tier--vault', 'data-tier': 'vault' });
  const { center, outer, inner, facets } = VAULT;

  tier.appendChild(s('path', {
    class: 'vault-shell', d: facetedEllipse(center.x, center.y, outer.rx, outer.ry, facets)
  }));

  // concentric faceted rings + radial structure
  tier.appendChild(s('path', { class: 'vault-ring', d: facetedEllipse(center.x, center.y, outer.rx, outer.ry, facets) }));
  tier.appendChild(s('path', {
    class: 'vault-facet', d: facetedEllipse(center.x, center.y, (outer.rx + inner.rx) / 2, (outer.ry + inner.ry) / 2, facets, Math.PI / facets)
  }));
  tier.appendChild(s('path', { class: 'vault-ring', d: facetedEllipse(center.x, center.y, inner.rx, inner.ry, facets) }));
  tier.appendChild(s('path', { class: 'vault-facet', d: vaultSpokes(center.x, center.y, outer, inner, facets) }));

  // rotating armature: the vault is a mechanism, calmly alive
  tier.appendChild(s('path', {
    class: 'vault-armature',
    d: facetedEllipse(center.x, center.y, inner.rx - 26, inner.ry - 22, 4, Math.PI / 4)
  }));

  tier.appendChild(s('text', {
    class: 't-label', x: center.x, y: center.y - outer.ry - 18, 'text-anchor': 'middle',
    text: VAULT.label, fill: 'var(--text-secondary)'
  }));

  /* SENTINEL 01 — HALLUCINATION CHECK
     Thin tracing beams that run from each parameter berth back to the actual
     evidence object that supports it. Previously these were four lines
     between invented coordinates inside the vault, which looked like a scan
     effect but asserted nothing. Now the geometry is derived from the same
     `supports` relations the inspector reads, so the beam a viewer sees is
     the claim-to-basis link, and a parameter with no evidence gets an amber
     beam that terminates in the void rather than at a source. */
  const traces = s('g', { class: 'vault-traces' });
  const evById = Object.fromEntries(EVIDENCE.map((e) => [e.id, e]));
  const paramById = Object.fromEntries(PARAMETERS.map((p) => [p.id, p]));
  const berthOf = (p) => ({
    x: p.side === 'left' ? BERTH.leftX + BERTH.w / 2 : BERTH.rightX - BERTH.w / 2,
    y: BERTH.ys[p.slot]
  });

  let ti = 0;
  EVIDENCE.forEach((ev) => {
    ev.supports.forEach((pid) => {
      const p = paramById[pid];
      if (!p) return;
      traces.appendChild(s('path', {
        class: 'trace-line', d: elbowPath(berthOf(p), ev.dock),
        style: `animation-delay: ${ti * 160}ms`
      }));
      ti += 1;
    });
  });
  // Parameters with no evidence basis: the beam searches and finds nothing.
  PARAMETERS.filter((p) => p.status !== 'supported').forEach((p) => {
    const b = berthOf(p);
    const dir = p.side === 'left' ? 1 : -1;
    traces.appendChild(s('path', {
      class: 'trace-line trace-line--unresolved',
      d: elbowPath(b, { x: b.x + 52 * dir, y: b.y + 16 }),
      style: `animation-delay: ${ti * 160}ms`
    }));
    ti += 1;
  });
  tier.appendChild(traces);

  // sentinels around the ring
  SENTINELS.forEach((sen) => {
    const a = sen.anchor;
    const w = 168;
    const hgt = 84;
    const box = { x: a.x - w / 2, y: a.y - hgt / 2, w, h: hgt };
    const g = s('g', { class: 'sentinel', 'data-sentinel': sen.id, 'data-state': 'idle' });

    /* A resolved sentinel throws light onto the vault wall behind it. Amber for
       critique, because the one sentinel that finds something must not be lit
       in the colour of agreement. */
    g.appendChild(s('ellipse', {
      class: 'sent-bounce', cx: a.x, cy: a.y, rx: 132, ry: 88,
      fill: sen.result.status === 'review' ? 'url(#bounceReview)' : 'url(#bounce)',
      'aria-hidden': 'true'
    }));

    g.appendChild(s('path', { class: 'sent-shell', d: facetPath(box, 12) }));
    g.appendChild(s('circle', { class: 'sent-eye', cx: box.x + 14, cy: box.y + 15, r: 3 }));
    g.appendChild(s('text', { class: 't-micro', x: box.x + 26, y: box.y + 18, text: `SENTINEL / ${sen.index}` }));
    g.appendChild(s('text', {
      class: 't-micro sent-label', x: box.x + 14, y: box.y + 40, text: sen.label,
      style: 'font-size:8.4px'
    }));

    // The readout stacks: a single line cannot hold both the field and the
    // value at this box width, and opposed anchors collide as strings grow.
    const res = s('g', { class: 'sent-result' });
    res.appendChild(s('line', {
      class: 'hair', x1: box.x + 14, y1: box.y + 48, x2: box.x + w - 14, y2: box.y + 48
    }));
    res.appendChild(s('text', {
      class: 't-micro', x: box.x + 14, y: box.y + 60, text: sen.result.label,
      opacity: 0.62, style: 'font-size:7px'
    }));
    res.appendChild(s('text', {
      class: 't-micro', x: box.x + 14, y: box.y + 71,
      text: sen.result.value, opacity: 0.95, style: 'font-size:8.4px',
      fill: sen.result.status === 'review' ? 'var(--status-review)' : 'var(--mineral-teal)'
    }));
    g.appendChild(res);

    // structural tie from sentinel into the vault ring
    const tieX = a.x < VAULT.center.x ? box.x + w : box.x;
    const tieDir = a.x < VAULT.center.x ? 1 : -1;
    g.appendChild(s('line', {
      class: 'hair', x1: tieX, y1: a.y, x2: tieX + 30 * tieDir, y2: a.y
    }));

    interactive(g, {
      id: sen.id, kind: 'sentinel',
      name: `Verification sentinel ${sen.index}: ${sen.name}. ${sen.result.label} ${sen.result.value}.`,
      box
    });
    tier.appendChild(g);
  });

  /* SENTINEL 03 — CRITIQUE
     A fault line that branches out of the critique sentinel itself and runs
     into the structure, ending at the disclosure note. It is deliberately a
     fracture in the architecture and not an alert badge: the system is
     admitting something about its own construction. Restrained amber, one
     line, no pulse — honest rather than alarmed. */
  const fr = s('g', { class: 'vault-critique' });
  const cSen = SENTINELS.find((x) => x.id === 's-critique');
  const frD = fracturePath(cSen.anchor.x + 84, cSen.anchor.y + 12, 200, 3.2);
  fr.appendChild(s('path', { class: 'fracture', d: frD }));

  const flag = s('g', { class: 'fracture-flag' });
  const fbox = { x: 352, y: 1252, w: 296, h: 62 };
  flag.appendChild(s('path', { class: 'flag-plate', d: facetPath(fbox, 10) }));
  flag.appendChild(s('text', { class: 't-micro', x: fbox.x + 12, y: fbox.y + 18, text: 'TEMPERATURE ASSUMPTION / 37\u00B0C' }));
  flag.appendChild(s('text', { class: 't-micro', x: fbox.x + 12, y: fbox.y + 33, text: 'STATUS / DISCLOSED FOR REVIEW' }));
  flag.appendChild(s('text', {
    class: 't-micro flag-note', x: fbox.x + 12, y: fbox.y + 50,
    text: 'NOT ESTABLISHED BY SAMPLE SOURCE SCOPE', style: 'font-size:7.4px'
  }));
  flag.appendChild(s('text', {
    class: 't-micro', x: fbox.x + fbox.w - 12, y: fbox.y + 18, 'text-anchor': 'end',
    text: STATUS.review.glyph, style: 'font-size:9px'
  }));
  fr.appendChild(flag);
  tier.appendChild(fr);

  // vault node itself is inspectable (outer ring hit area)
  const holder = s('g', { class: 'node vault-node', 'data-state': 'dormant' });
  holder.appendChild(s('rect', {
    x: center.x - 60, y: center.y - outer.ry - 30, width: 120, height: 20, fill: 'transparent'
  }));
  interactive(holder, {
    id: VAULT.id, kind: 'vault', name: 'The Verification Vault. Four sentinels surround the simulation core.',
    box: { x: center.x - 60, y: center.y - outer.ry - 30, w: 120, h: 20 }
  });
  tier.appendChild(holder);

  // completion bloom, fired only at verification resolve
  tier.appendChild(s('circle', { class: 'bloom', cx: center.x, cy: center.y, r: 120 }));

  return tier;
}

/* ============================================================
   TIER 05 — SIMULATION CORE (illustrative output)
   ============================================================ */
function buildCore() {
  const tier = s('g', { class: 'tier tier--core core-chamber', 'data-tier': 'core' });
  const { box, plot } = CORE;

  tier.appendChild(s('path', { class: 'chamber-shell', d: facetPath(box, 14) }));
  /* The core carries the same corner locks as every other module, because the
     same rule applies to it: a structure is only locked once something has
     checked it. Here that check is Correctness, so these engage when the
     envelope resolves rather than when the curve finishes drawing. A result
     that has merely been computed is not yet a result that holds. */
  tier.appendChild(cornerLocks(box));
  tier.appendChild(s('rect', {
    x: plot.x - 4, y: plot.y - 6, width: plot.w + 8, height: plot.h + 10, fill: 'url(#coreDepth)'
  }));
  tier.appendChild(s('text', {
    class: 't-micro', x: box.x + 12, y: box.y + 16, text: CORE.label, fill: 'var(--text-secondary)'
  }));

  // plot grid
  const grid = s('g', { class: 'plot-grid-group' });
  for (let i = 1; i < 4; i += 1) {
    grid.appendChild(s('line', {
      class: 'plot-grid', x1: plot.x, y1: plot.y + (plot.h / 4) * i,
      x2: plot.x + plot.w, y2: plot.y + (plot.h / 4) * i
    }));
    grid.appendChild(s('line', {
      class: 'plot-grid', x1: plot.x + (plot.w / 4) * i, y1: plot.y,
      x2: plot.x + (plot.w / 4) * i, y2: plot.y + plot.h
    }));
  }
  tier.appendChild(grid);

  // axes draw in
  tier.appendChild(s('path', {
    class: 'plot-axis',
    d: `M ${plot.x} ${plot.y} L ${plot.x} ${plot.y + plot.h} L ${plot.x + plot.w} ${plot.y + plot.h}`
  }));

  const { curve, points, vmax } = kineticsSeries(CURVE_MODEL);
  const sMax = CURVE_MODEL.sMax;

  /* SENTINEL 02's apparatus: the expected-behaviour envelope, its two bounds
     drawn as separate constructed lines, and the check bar that sweeps the
     plot. Held here rather than in the vault because the check happens to the
     output, and the output lives in the core. */
  tier.appendChild(s('path', { class: 'plot-envelope', d: envelopePath(curve, plot, vmax) }));
  const env = envelopePath(curve, plot, vmax);
  // The envelope path is upper-then-lower-reversed; split it so each bound
  // can draw independently and read as a constructed limit.
  const half = env.indexOf(' L ', Math.floor(env.length / 2));
  if (half > 0) {
    tier.appendChild(s('path', { class: 'plot-bound', d: env.slice(0, half) }));
    tier.appendChild(s('path', { class: 'plot-bound', d: `M ${env.slice(half + 3).replace(/ Z$/, '')}` }));
  }
  tier.appendChild(s('line', {
    class: 'plot-sweep', x1: plot.x, y1: plot.y - 4, x2: plot.x, y2: plot.y + plot.h + 4,
    style: `--sweep:${plot.w}px`
  }));

  // the curve itself
  tier.appendChild(s('path', { class: 'plot-curve', d: plotToPath(curve, plot, vmax) }));

  // plotted sample points
  const pts = s('g', { class: 'plot-points' });
  points.forEach((p, i) => {
    const { x, y } = plotPoint(p, plot, sMax, vmax);
    pts.appendChild(s('rect', {
      class: 'plot-point', x: x - 1.8, y: y - 1.8, width: 3.6, height: 3.6,
      style: `--d:${900 + i * 90}ms`
    }));
  });
  tier.appendChild(pts);

  // asymptote marker: approaching plateau
  const plateauY = plot.y + plot.h - (vmax / (vmax * 1.12)) * plot.h;
  tier.appendChild(s('line', {
    class: 'plot-grid', x1: plot.x, y1: plateauY, x2: plot.x + plot.w, y2: plateauY,
    stroke: 'rgba(157, 184, 196,0.3)', 'stroke-dasharray': '2 4'
  }));

  // axis labels
  tier.appendChild(s('text', {
    class: 't-micro', x: plot.x, y: plot.y + plot.h + 16, text: CORE.axes.x, style: 'font-size:7px'
  }));
  // y-axis label runs vertically along the axis, instrument-style
  tier.appendChild(s('text', {
    class: 't-micro', x: 0, y: 0, text: CORE.axes.y, style: 'font-size:7px',
    transform: `translate(${plot.x - 9} ${plot.y + plot.h}) rotate(-90)`
  }));
  tier.appendChild(s('text', {
    class: 't-micro plot-caption', x: box.x + box.w / 2, y: box.y + box.h - 12,
    'text-anchor': 'middle', text: CORE.caption, style: 'font-size:8px'
  }));

  interactive(tier, {
    id: CORE.id, kind: 'core',
    name: 'Simulation core. Illustrative kinetics output: velocity rises with substrate concentration and approaches a plateau.',
    box
  });
  return tier;
}

/* ============================================================
   TIER 06 — VERIFIED SCIENTIFIC RECORD
   ============================================================ */
function buildRecord() {
  const tier = s('g', { class: 'tier tier--record', 'data-tier': 'record' });
  const { box } = RECORD;
  const g = s('g', { class: 'record' });

  // release channel from the vault base into the record
  tier.appendChild(s('path', {
    class: 'hair',
    d: `M ${STAGE.spine - 22} ${box.y - 34} L ${STAGE.spine - 8} ${box.y - 6}
        M ${STAGE.spine + 22} ${box.y - 34} L ${STAGE.spine + 8} ${box.y - 6}`
  }));

  /* SENTINEL 04 — POLISH
     Registration marks that align the record. They converge on the plate as
     it is composed, which is what makes polish read as typesetting rather
     than decoration: the record is being squared up to a grid. They never
     touch the disclosure row — formatting cannot move a disclosure. */
  const reg = s('g', { class: 'rec-registration' });
  [[box.x, box.y], [box.x + box.w, box.y], [box.x, box.y + box.h], [box.x + box.w, box.y + box.h]]
    .forEach(([rx, ry], i) => {
      const dx = i % 2 === 0 ? 1 : -1;
      const dy = i < 2 ? 1 : -1;
      reg.appendChild(s('path', {
        class: 'rec-reg-mark',
        d: `M ${rx + dx * 30} ${ry} L ${rx} ${ry} L ${rx} ${ry + dy * 30}`
      }));
    });
  tier.appendChild(reg);

  g.appendChild(s('path', { class: 'rec-plate', d: facetPath(box, 18) }));
  g.appendChild(s('path', { class: 'rec-edge', d: facetPath(box, 18) }));
  g.appendChild(s('path', {
    class: 'rec-perf', d: `M ${box.x + 18} ${box.y + 1} L ${box.x + box.w - 18} ${box.y + 1}`
  }));

  g.appendChild(s('text', { class: 't-micro', x: box.x + 26, y: box.y + 32, text: RECORD.label, style: 'font-size:8.5px' }));
  g.appendChild(s('text', {
    class: 't-micro rec-title', x: box.x + 26, y: box.y + 54, text: RECORD.title,
    style: 'font-size:10.5px; letter-spacing:0.06em'
  }));
  g.appendChild(s('line', {
    x1: box.x + 26, y1: box.y + 68, x2: box.x + box.w - 26, y2: box.y + 68,
    stroke: 'rgba(42, 45, 53,0.2)', 'stroke-width': 1, 'vector-effect': 'non-scaling-stroke'
  }));

  RECORD.lines.forEach((line, i) => {
    const y = box.y + 94 + i * 26;
    g.appendChild(s('text', { class: 'rec-num', x: box.x + 26, y, text: line.k }));
    g.appendChild(s('text', {
      class: `t-micro${line.status === 'review' ? ' rec-review' : ''}`,
      x: box.x + 54, y: y - 1, text: line.v, style: 'font-size:8.4px'
    }));
    if (line.status === 'review') {
      g.appendChild(s('text', {
        class: 't-micro rec-review', x: box.x + box.w - 26, y: y - 1, 'text-anchor': 'end',
        text: STATUS.review.glyph, style: 'font-size:8.4px'
      }));
    }
    g.appendChild(s('line', {
      x1: box.x + 26, y1: y + 8, x2: box.x + box.w - 26, y2: y + 8,
      stroke: 'rgba(42, 45, 53,0.1)', 'stroke-width': 1, 'vector-effect': 'non-scaling-stroke'
    }));
  });

  // archival seal: faceted, not a checkmark badge
  const sx = box.x + box.w - 74;
  const sy = box.y + 44;
  g.appendChild(s('path', { class: 'rec-seal', d: facetedEllipse(sx, sy, 26, 26, 8) }));
  g.appendChild(s('path', { class: 'rec-seal', d: facetedEllipse(sx, sy, 18, 18, 8, 0.4) }));
  g.appendChild(s('path', { class: 'rec-seal-mark', d: `M ${sx - 6} ${sy} L ${sx} ${sy - 6} L ${sx + 6} ${sy} L ${sx} ${sy + 6} Z` }));
  g.appendChild(s('text', {
    class: 't-micro', x: sx, y: sy + 42, 'text-anchor': 'middle',
    text: 'ILLUSTRATIVE', fill: 'rgba(42, 45, 53,0.5)', style: 'font-size:7px'
  }));

  interactive(g, {
    id: RECORD.id, kind: 'record',
    name: 'Verified run 0007. Illustrative Michaelis-Menten kinetics record with one disclosed assumption.',
    box
  });
  tier.appendChild(g);
  return tier;
}

/* ============================================================
   MOUNT — assembles every tier into the stage SVG
   ============================================================ */
export function renderCathedral(mountEl, question) {
  const svg = s('svg', {
    class: 'cath-svg',
    viewBox: `0 0 ${STAGE.w} ${STAGE.h}`,
    preserveAspectRatio: 'xMidYMid meet',
    role: 'img',
    'aria-labelledby': 'cath-title cath-desc'
  });

  svg.appendChild(s('title', { id: 'cath-title', text: 'The Evidence Cathedral' }));
  svg.appendChild(s('desc', {
    id: 'cath-desc',
    text: 'A vertical computational architecture. A question enters at the top, passes through model selection, literature retrieval, configuration and compute routing, is executed in a central core, is surrounded by four verification sentinels, and is released as a verified scientific record at the base.'
  }));

  svg.appendChild(buildDefs());

  const camera = s('g', { class: 'camera' });
  camera.appendChild(buildDistant());
  camera.appendChild(buildSheet());
  camera.appendChild(buildSubstrate());
  camera.appendChild(buildQuestionChamber(question));
  camera.appendChild(buildInterpretationArray());
  camera.appendChild(buildEvidenceLayer());
  camera.appendChild(buildAssembly());
  camera.appendChild(buildVault());
  camera.appendChild(buildCore());
  camera.appendChild(buildRecord());
  svg.appendChild(camera);

  mountEl.replaceChildren(svg);

  // Prime every dash-animated path after insertion.
  svg.querySelectorAll('.plot-curve, .plot-axis, .trace-line, .fracture').forEach(primeDash);

  return svg;
}
