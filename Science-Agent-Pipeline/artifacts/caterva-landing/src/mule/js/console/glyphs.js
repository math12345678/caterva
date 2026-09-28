/* ============================================================
   caterva — agent glyphs

   Each agent carries a distinct structural mark. The point is not
   decoration: nine identical dots in a timeline would say the nine
   stages are the same kind of work, when the whole argument of the
   product is that they are not. A sieve looks like filtering, a
   gauge like measurement, a fracture like disclosure.

   All are drawn in one 34×34 box, stroke-only, so they sit on the
   timeline spine at a consistent optical weight.
   ============================================================ */

import { s } from '../lib/dom.js';

const BOX = 34;
const c = BOX / 2;

const wrap = (kind, children) =>
  s('svg', {
    class: `ag-glyph ag-glyph--${kind}`,
    viewBox: `0 0 ${BOX} ${BOX}`,
    width: BOX, height: BOX,
    'aria-hidden': 'true'
  }, children);

/** 01 lens — selection: converging on one choice. */
const lens = () => wrap('lens', [
  s('circle', { class: 'gl-line', cx: c, cy: c, r: 11 }),
  s('path', { class: 'gl-line', d: `M ${c - 11} ${c} Q ${c} ${c - 12} ${c + 11} ${c} Q ${c} ${c + 12} ${c - 11} ${c} Z` }),
  s('circle', { class: 'gl-fill', cx: c, cy: c, r: 2.4 })
]);

/** 02 stack — retrieval: records gathered edge-on. */
const stack = () => wrap('stack', [
  s('path', { class: 'gl-line', d: `M 6 ${c - 8} L 28 ${c - 8}` }),
  s('path', { class: 'gl-line', d: `M 8 ${c - 3} L 26 ${c - 3}` }),
  s('path', { class: 'gl-line', d: `M 6 ${c + 2} L 28 ${c + 2}` }),
  s('path', { class: 'gl-line', d: `M 8 ${c + 7} L 26 ${c + 7}` }),
  s('path', { class: 'gl-accent', d: `M 4 ${c - 11} L 4 ${c + 10}` })
]);

/** 03 assembly — configuration: parts brought into register. */
const assembly = () => wrap('assembly', [
  s('rect', { class: 'gl-line', x: 6, y: 6, width: 10, height: 10 }),
  s('rect', { class: 'gl-line', x: 18, y: 18, width: 10, height: 10 }),
  s('path', { class: 'gl-accent', d: 'M 16 11 L 23 11 L 23 18' })
]);

/** 04 switch — routing: one path chosen from several. */
const swtch = () => wrap('switch', [
  s('path', { class: 'gl-line', d: `M 5 ${c} L 15 ${c}` }),
  s('path', { class: 'gl-line', d: `M 15 ${c} L 29 9` }),
  s('path', { class: 'gl-accent', d: `M 15 ${c} L 29 ${c}` }),
  s('path', { class: 'gl-line', d: `M 15 ${c} L 29 25` }),
  s('circle', { class: 'gl-fill', cx: 15, cy: c, r: 2.2 })
]);

/** 05 core — execution: the chamber where arithmetic happens. */
const core = () => wrap('core', [
  s('path', { class: 'gl-line', d: 'M 11 6 L 23 6 L 28 17 L 23 28 L 11 28 L 6 17 Z' }),
  s('path', { class: 'gl-accent', d: `M 11 20 Q 17 20 17 14 Q 17 10 23 10` })
]);

/** 06 sieve — the check that stops unsupported claims passing. */
const sieve = () => wrap('sieve', [
  s('path', { class: 'gl-line', d: 'M 5 9 L 29 9 L 21 20 L 21 28 L 13 28 L 13 20 Z' }),
  s('path', { class: 'gl-accent', d: 'M 10 14 L 24 14' })
]);

/** 07 gauge — measurement against an expected behaviour. */
const gauge = () => wrap('gauge', [
  s('path', { class: 'gl-line', d: `M 6 23 A 11 11 0 0 1 28 23` }),
  s('path', { class: 'gl-accent', d: `M 17 23 L 24 14` }),
  s('circle', { class: 'gl-fill', cx: 17, cy: 23, r: 2 })
]);

/** 08 fracture — disclosure: the honest crack in the structure. */
const fracture = () => wrap('fracture', [
  s('rect', { class: 'gl-line', x: 6, y: 7, width: 22, height: 20 }),
  s('path', { class: 'gl-accent', d: 'M 13 7 L 16 15 L 12 19 L 18 27' })
]);

/** 09 plate — the finished record, formatted. */
const plate = () => wrap('plate', [
  s('path', { class: 'gl-line', d: 'M 7 6 L 27 6 L 27 28 L 7 28 Z' }),
  s('path', { class: 'gl-accent', d: 'M 12 13 L 22 13' }),
  s('path', { class: 'gl-accent', d: 'M 12 18 L 20 18' }),
  s('path', { class: 'gl-accent', d: 'M 12 23 L 23 23' })
]);

const MAP = { lens, stack, assembly, switch: swtch, core, sieve, gauge, fracture, plate };

export function agentGlyph(kind) {
  return (MAP[kind] || lens)();
}
