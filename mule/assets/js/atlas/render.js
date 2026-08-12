/* ============================================================
   terrium — atlas rendering

   Pure construction. This module reads config/atlas.js and returns
   SVG; it holds no state and installs no listeners. Interaction
   lives in atlas/index.js, camera work in atlas/camera.js.

   Each region is drawn in its own language, chosen by
   `region.character`. That is the whole art direction: an evidence
   archive is built from stacked leaves, a compute layer from rack
   slots, the trust layer from a faceted ring. If they were all
   drawn as rounded rectangles the map would be asserting that
   these are interchangeable, which is the failure mode of every
   generic systems diagram.
   ============================================================ */

import { s } from '../lib/dom.js';
import { facetPath, facetedEllipse, vaultSpokes } from '../lib/geometry.js';
import { ATLAS, REGIONS, NODES, REGION_NODES, ROUTES, FAILURES, centre } from '../config/atlas.js';
import { STATUS } from '../config/architecture.js';
import { lanePath, labelAnchor, arrivalChevron, laneLength } from './lanes.js';

/* ------------------------------------------------------------
   SUBSTRATE
   Three depth planes, drawn first and parallaxed independently:
   a coordinate field, a set of structural risers, and the region
   plates. Depth is what stops a flat graph reading as a diagram.
   ------------------------------------------------------------ */
function buildSubstrate() {
  const g = s('g', { class: 'atl-substrate', 'aria-hidden': 'true' });

  /* Deep plane: a sparse survey grid. Wide spacing, because a fine grid
     reads as graph paper and pulls the eye away from the structure. */
  const deep = s('g', { class: 'atl-plane atl-plane--deep', 'data-depth': '0.25' });
  for (let x = 0; x <= ATLAS.w; x += 200) {
    deep.appendChild(s('line', { class: 'atl-grid-line', x1: x, y1: 0, x2: x, y2: ATLAS.h }));
  }
  for (let y = 0; y <= ATLAS.h; y += 200) {
    deep.appendChild(s('line', { class: 'atl-grid-line', x1: 0, y1: y, x2: ATLAS.w, y2: y }));
  }
  /* Survey ticks every 400, labelled. Quiet technical notation: the map
     behaves as though it were surveyed, not sketched. */
  for (let x = 400; x < ATLAS.w; x += 400) {
    for (let y = 400; y < ATLAS.h; y += 400) {
      deep.appendChild(s('path', { class: 'atl-tick', d: `M ${x - 6} ${y} L ${x + 6} ${y} M ${x} ${y - 6} L ${x} ${y + 6}` }));
    }
  }

  /* Structural risers: the armature the corridor grid is cut from, drawn so
     the lane structure reads as architecture even where no route runs.

     These live on the DEEP plane, with the grid, not on a plane above it.
     Region plates are deliberately translucent so the survey shows through
     them, which means a riser drawn in front of the plates reads as a stray
     connection running into a module rather than as substrate behind it.
     Depth order is what distinguishes ground from wiring here. */
  const risers = [660, 2060, 2960, 3760];
  risers.forEach((x) => {
    deep.appendChild(s('line', { class: 'atl-riser', x1: x, y1: 60, x2: x, y2: ATLAS.h - 60 }));
  });
  /* Two datums: the return beam the evidence trail is hung from, and the
     line the execution layer stands on. */
  [600, 1500].forEach((y) => {
    deep.appendChild(s('line', { class: 'atl-riser atl-riser--h', x1: 60, y1: y, x2: ATLAS.w - 60, y2: y }));
  });
  g.appendChild(deep);

  return g;
}

/* ------------------------------------------------------------
   REGION PLATES
   A region is a plate with a chamfered silhouette, an index, a
   name, a survey coordinate and a one-line note. The plate is the
   only thing drawn at SYSTEM zoom besides the routes.
   ------------------------------------------------------------ */
function buildRegionPlate(region) {
  const { box } = region;
  const g = s('g', {
    class: `atl-region atl-region--${region.character}${region.dominant ? ' is-dominant' : ''}`,
    dataset: { region: region.id }
  });

  g.appendChild(s('path', { class: 'atl-region__fill', d: facetPath(box, 22) }));
  g.appendChild(s('path', { class: 'atl-region__edge', d: facetPath(box, 22) }));

  /* Corner registration, top-left and bottom-right only. Four corners
     reads as a selection box; two reads as a survey plate. */
  const k = 26;
  g.appendChild(s('path', {
    class: 'atl-region__reg',
    d: `M ${box.x} ${box.y + k} L ${box.x} ${box.y} L ${box.x + k} ${box.y}`
  }));
  g.appendChild(s('path', {
    class: 'atl-region__reg',
    d: `M ${box.x + box.w} ${box.y + box.h - k} L ${box.x + box.w} ${box.y + box.h} L ${box.x + box.w - k} ${box.y + box.h}`
  }));

  /* Label column offsets are set so the index never runs into the name.
     At 30px with 0.14em tracking a two-digit index occupies ~46 units, so
     the name starts at +104 rather than +74, where it collided. */
  const head = s('g', { class: 'atl-region__head' });
  head.appendChild(s('text', { class: 'atl-region__index', x: box.x + 26, y: box.y - 46, text: region.index }));
  head.appendChild(s('text', { class: 'atl-region__word', x: box.x + 104, y: box.y - 46, text: region.word }));
  head.appendChild(s('text', { class: 'atl-region__coord', x: box.x + 26, y: box.y - 18, text: region.coord }));
  head.appendChild(s('text', {
    class: 'atl-region__note', x: box.x + 200, y: box.y - 18, text: region.note
  }));
  g.appendChild(head);

  return g;
}

/* ------------------------------------------------------------
   NODES
   Dispatch on `kind`. Every module gets: a silhouette in its
   region's language, a label, a sub-label, a coordinate, and a
   status mark carrying a glyph as well as a colour.
   ------------------------------------------------------------ */
function statusMark(node, x, y) {
  const st = STATUS[node.status];
  if (!st) return null;
  const g = s('g', { class: `atl-node__status atl-node__status--${node.status}` });
  g.appendChild(s('text', { class: 'atl-node__glyph', x, y, text: st.glyph }));
  return g;
}

function nodeLabels(node) {
  const { box } = node;
  const g = s('g', { class: 'atl-node__labels' });
  g.appendChild(s('text', {
    class: 'atl-node__coord', x: box.x + 18, y: box.y + 26, text: node.coord
  }));
  g.appendChild(s('text', {
    class: 'atl-node__label', x: box.x + 18, y: box.y + 62, text: node.label
  }));
  g.appendChild(s('text', {
    class: 'atl-node__sub', x: box.x + 18, y: box.y + 86, text: node.sub
  }));
  const mark = statusMark(node, box.x + box.w - 18, box.y + 26);
  if (mark) g.appendChild(mark);
  return g;
}

/* --- 01 open: intake. No fence, only a floor and a corner. ---- */
function drawOpen(node) {
  const { box } = node;
  const g = s('g', { class: 'atl-shape atl-shape--open' });
  /* Intake is "quiet and open", so these modules are deliberately not
     enclosed: an open bracket and a floor rule, nothing that reads as a
     container. A person's question is not yet inside the machine. */
  g.appendChild(s('path', {
    class: 'atl-open__bracket',
    d: `M ${box.x + 30} ${box.y} L ${box.x} ${box.y} L ${box.x} ${box.y + box.h} L ${box.x + 30} ${box.y + box.h}`
  }));
  g.appendChild(s('line', {
    class: 'atl-open__floor', x1: box.x, y1: box.y + box.h, x2: box.x + box.w, y2: box.y + box.h
  }));
  if (node.kind === 'open-major') {
    /* The question itself carries the run's origin mark. */
    g.appendChild(s('path', {
      class: 'atl-open__origin',
      d: `M ${box.x + box.w - 46} ${box.y + box.h - 30} l 12 0 l 0 -12`
    }));
  }
  return g;
}

/* --- 02 facet: interpretation. Chamfered, hard-edged. -------- */
function drawFacet(node) {
  const { box } = node;
  const g = s('g', { class: 'atl-shape atl-shape--facet' });
  g.appendChild(s('path', { class: 'atl-facet__fill', d: facetPath(box, 16) }));
  g.appendChild(s('path', { class: 'atl-facet__edge', d: facetPath(box, 16) }));
  /* An interior facet line: the module has structure, it is not a card. */
  g.appendChild(s('line', {
    class: 'atl-facet__seam',
    x1: box.x + 16, y1: box.y + box.h - 22, x2: box.x + box.w - 16, y2: box.y + box.h - 22
  }));
  return g;
}

/* --- 03 archive: evidence. Stacked leaves, source-rich. ------ */
function drawArchive(node) {
  const { box } = node;
  const g = s('g', { class: 'atl-shape atl-shape--archive' });
  /* A source region is drawn as a stack of records seen edge-on. The
     leaf count varies per source so the archive is granular rather than
     five identical cards, and no leaf carries a fabricated citation —
     they are record edges, not titles. */
  const leaves = node.leaves || 5;
  const gap = (box.h - 78) / leaves;
  for (let i = 0; i < leaves; i++) {
    const y = box.y + 64 + i * gap;
    const inset = 10 + (i % 2) * 8;
    g.appendChild(s('line', {
      class: 'atl-archive__leaf',
      x1: box.x + inset, y1: y, x2: box.x + box.w - inset, y2: y,
      dataset: { leaf: String(i) }
    }));
  }
  g.appendChild(s('path', { class: 'atl-archive__edge', d: facetPath(box, 12) }));
  /* Spine down the left: the bound edge of the stack. */
  g.appendChild(s('line', {
    class: 'atl-archive__spine', x1: box.x + 4, y1: box.y + 12, x2: box.x + 4, y2: box.y + box.h - 12
  }));
  return g;
}

/* --- 03b manifold: retrieval assembly under the sources ------ */
function drawManifold(node) {
  const { box } = node;
  const g = s('g', { class: 'atl-shape atl-shape--manifold' });
  g.appendChild(s('path', { class: 'atl-manifold__fill', d: facetPath(box, 14) }));
  g.appendChild(s('path', { class: 'atl-manifold__edge', d: facetPath(box, 14) }));
  /* Intake ports, one under each source column, so the manifold visibly
     collects from the five archives standing above it. */
  [835, 1045, 1255, 1465, 1675].forEach((x, i) => {
    g.appendChild(s('line', {
      class: 'atl-manifold__port', x1: x, y1: box.y, x2: x, y2: box.y + 18,
      dataset: { port: String(i) }
    }));
  });
  return g;
}

/* --- 04 plate: configuration. Mechanical assembly. ---------- */
function drawPlate(node) {
  const { box } = node;
  const g = s('g', { class: 'atl-shape atl-shape--plate' });
  g.appendChild(s('path', { class: 'atl-plate__fill', d: facetPath(box, 10) }));
  g.appendChild(s('path', { class: 'atl-plate__edge', d: facetPath(box, 10) }));
  /* Fixing points. Configuration is assembly, so its modules are drawn
     as bolted plates: four small locators, one per corner inset. */
  const inset = 13;
  [[box.x + inset, box.y + inset], [box.x + box.w - inset, box.y + inset],
   [box.x + inset, box.y + box.h - inset], [box.x + box.w - inset, box.y + box.h - inset]]
    .forEach(([cx, cy]) => {
      g.appendChild(s('path', {
        class: 'atl-plate__fix', d: `M ${cx - 4} ${cy} L ${cx + 4} ${cy} M ${cx} ${cy - 4} L ${cx} ${cy + 4}`
      }));
    });
  if (node.kind === 'plate-major') {
    g.appendChild(s('line', {
      class: 'atl-plate__rail',
      x1: box.x + 24, y1: box.y + box.h - 26, x2: box.x + box.w - 24, y2: box.y + box.h - 26
    }));
  }
  return g;
}

/* --- 05 rack / router: execution. Computational hardware. --- */
function drawRack(node) {
  const { box } = node;
  const g = s('g', { class: `atl-shape atl-shape--rack atl-shape--${node.kind}` });
  g.appendChild(s('rect', {
    class: 'atl-rack__fill', x: box.x, y: box.y, width: box.w, height: box.h
  }));
  g.appendChild(s('rect', {
    class: 'atl-rack__edge', x: box.x, y: box.y, width: box.w, height: box.h
  }));
  /* Slot ventilation on the left edge — the mark that says "this is where
     the arithmetic physically happens". */
  for (let i = 0; i < 4; i++) {
    const y = box.y + 18 + i * 16;
    g.appendChild(s('line', {
      class: 'atl-rack__vent', x1: box.x + 8, y1: y, x2: box.x + 26, y2: y
    }));
  }
  if (node.kind === 'rack-external') {
    /* Outside the product. Drawn dashed, because a boundary the system
       does not own must not look like equipment it owns. */
    g.appendChild(s('rect', {
      class: 'atl-rack__external', x: box.x, y: box.y, width: box.w, height: box.h
    }));
  }
  return g;
}

function drawRouter(node) {
  const { box } = node;
  const g = s('g', { class: 'atl-shape atl-shape--router' });
  g.appendChild(s('path', { class: 'atl-router__fill', d: facetPath(box, 18) }));
  g.appendChild(s('path', { class: 'atl-router__edge', d: facetPath(box, 18) }));
  /* Four outgoing ports on the right edge, aligned to the four runtimes,
     so the routing decision is visible as geometry rather than asserted. */
  [1672, 1776, 1880, 1984].forEach((y, i) => {
    g.appendChild(s('path', {
      class: 'atl-router__port',
      d: `M ${box.x + box.w - 16} ${y} L ${box.x + box.w} ${y}`,
      dataset: { port: String(i) }
    }));
  });
  return g;
}

/* --- 06 shield: trust. The dominant region. ------------------ */
function drawShield(node) {
  const { box } = node;
  const g = s('g', { class: `atl-shape atl-shape--shield${node.kind === 'shield-review' ? ' is-review' : ''}` });
  g.appendChild(s('path', { class: 'atl-shield__fill', d: facetPath(box, 20) }));
  g.appendChild(s('path', { class: 'atl-shield__edge', d: facetPath(box, 20) }));
  /* A gate, not a card: two heavy jambs mark the passage through it. */
  g.appendChild(s('path', {
    class: 'atl-shield__jamb',
    d: `M ${box.x + 6} ${box.y + 22} L ${box.x + 6} ${box.y + box.h - 22}`
  }));
  g.appendChild(s('path', {
    class: 'atl-shield__jamb',
    d: `M ${box.x + box.w - 6} ${box.y + 22} L ${box.x + box.w - 6} ${box.y + box.h - 22}`
  }));
  return g;
}

/* --- 07 paper: output. Pale record leaving the machine. ------ */
function drawPaper(node) {
  const { box } = node;
  const g = s('g', { class: `atl-shape atl-shape--paper${node.kind === 'paper-major' ? ' is-major' : ''}` });
  g.appendChild(s('path', { class: 'atl-paper__fill', d: facetPath(box, 8) }));
  g.appendChild(s('path', { class: 'atl-paper__edge', d: facetPath(box, 8) }));
  if (node.kind === 'paper-major') {
    /* Text rules standing in for the notebook's content. Deliberately
       abstract: no fabricated result or citation is drawn anywhere. */
    for (let i = 0; i < 4; i++) {
      const y = box.y + 112 + i * 18;
      const w = [0.72, 0.86, 0.55, 0.79][i] * (box.w - 60);
      g.appendChild(s('line', { class: 'atl-paper__rule', x1: box.x + 30, y1: y, x2: box.x + 30 + w, y2: y }));
    }
  }
  return g;
}

const SHAPE = {
  open: drawOpen, 'open-major': drawOpen,
  facet: drawFacet, 'facet-major': drawFacet,
  archive: drawArchive, manifold: drawManifold,
  plate: drawPlate, 'plate-major': drawPlate,
  router: drawRouter,
  rack: drawRack, 'rack-active': drawRack, 'rack-backend': drawRack,
  'rack-external': drawRack,
  shield: drawShield, 'shield-review': drawShield,
  paper: drawPaper, 'paper-major': drawPaper
};

function buildNode(node) {
  const g = s('g', {
    class: `atl-node atl-node--${node.region} atl-node--${node.kind}`,
    dataset: { node: node.id, region: node.region },
    tabindex: '0',
    role: 'button'
  });
  const draw = SHAPE[node.kind] || drawFacet;
  g.appendChild(draw(node));
  g.appendChild(nodeLabels(node));
  /* Hit area. The silhouettes are open shapes with no fill in some
     regions, so without this a click between two strokes would miss. */
  g.appendChild(s('rect', {
    class: 'atl-node__hit',
    x: node.box.x, y: node.box.y, width: node.box.w, height: node.box.h
  }));
  return g;
}

/* ------------------------------------------------------------
   TRUST RING
   The trust layer is the only region with its own enclosing
   structure. The brief calls for visual dominance and a protective
   geometry, so the four gates sit inside a faceted double ring
   with radial spokes — the same vault language the cathedral uses,
   at map scale.
   ------------------------------------------------------------ */
function buildTrustRing(region) {
  const { ring } = region;
  if (!ring) return null;
  const g = s('g', { class: 'atl-ring', 'aria-hidden': 'true' });
  /* facetedEllipse returns a closed path, and vaultSpokes takes {rx,ry}
     radii rather than scalars — the same generators the cathedral vault
     uses, so the two drawings share a vocabulary. */
  g.appendChild(s('path', {
    class: 'atl-ring__outer',
    d: facetedEllipse(ring.cx, ring.cy, ring.outer, ring.outer, ring.facets)
  }));
  g.appendChild(s('path', {
    class: 'atl-ring__inner',
    d: facetedEllipse(ring.cx, ring.cy, ring.inner, ring.inner, ring.facets, Math.PI / ring.facets)
  }));
  g.appendChild(s('path', {
    class: 'atl-ring__spokes',
    d: vaultSpokes(
      ring.cx, ring.cy,
      { rx: ring.outer, ry: ring.outer },
      { rx: ring.inner, ry: ring.inner },
      ring.facets
    )
  }));
  /* A slow sweep line, the one moving element in OBSERVE mode: the
     trust layer is the part of the system that is always watching. */
  g.appendChild(s('line', {
    class: 'atl-ring__sweep',
    x1: ring.cx, y1: ring.cy, x2: ring.cx, y2: ring.cy - ring.outer
  }));
  return g;
}

/* ------------------------------------------------------------
   LANES
   Routes and failure paths, each with an invisible wide hit line
   so hovering does not require pixel accuracy on a 2px stroke.
   ------------------------------------------------------------ */
function buildLane(route, kind) {
  const d = lanePath(route.points);
  const g = s('g', {
    class: `atl-lane atl-lane--${kind}${route.upstream ? ' is-upstream' : ''}`,
    dataset: { route: route.id, kind }
  });
  g.appendChild(s('path', { class: 'atl-lane__casing', d }));
  const line = s('path', { class: 'atl-lane__line', d });
  line.style.setProperty('--len', String(laneLength(route.points)));
  g.appendChild(line);
  /* The travelling pulse. One per route, and only shown while the route
     is active — a permanently animated lane is decoration. */
  const pulse = s('path', { class: 'atl-lane__pulse', d });
  pulse.style.setProperty('--len', String(laneLength(route.points)));
  g.appendChild(pulse);
  g.appendChild(s('path', { class: 'atl-lane__chevron', d: arrivalChevron(route.points) }));
  g.appendChild(s('path', { class: 'atl-lane__hit', d }));

  const anchor = labelAnchor(route.points);
  const label = s('g', {
    class: `atl-lane__label${anchor.horizontal ? '' : ' is-vertical'}`,
    dataset: { anchor: anchor.horizontal ? 'h' : 'v' }
  });
  const text = s('text', {
    class: 'atl-lane__info',
    x: anchor.x, y: anchor.y - 12,
    text: route.info
  });
  if (!anchor.horizontal) {
    text.setAttribute('transform', `rotate(-90 ${anchor.x} ${anchor.y})`);
    text.setAttribute('y', anchor.y);
    text.setAttribute('x', anchor.x);
    text.setAttribute('dy', '-12');
  }
  label.appendChild(text);
  g.appendChild(label);
  return g;
}

/* ------------------------------------------------------------
   ASSEMBLY
   ------------------------------------------------------------ */
export function buildAtlas() {
  const svg = s('svg', {
    class: 'atl-svg',
    viewBox: `0 0 ${ATLAS.w} ${ATLAS.h}`,
    preserveAspectRatio: 'xMidYMid meet',
    role: 'img',
    'aria-label':
      'Terrium system map. Seven regions: human intake, interpretation, evidence, configuration, execution, trust and output, connected by eight labelled information routes. An equivalent text description follows.'
  });

  svg.appendChild(buildSubstrate());

  /* Region plates on their own plane so they parallax as one. */
  const plates = s('g', { class: 'atl-plane atl-plane--plates', 'data-depth': '0.8' });
  REGIONS.forEach((r) => plates.appendChild(buildRegionPlate(r)));
  svg.appendChild(plates);

  const trust = REGIONS.find((r) => r.id === 'trust');
  const ring = buildTrustRing(trust);
  if (ring) svg.appendChild(ring);

  /* Failure lanes below the live routes: in FAILURE mode they come
     forward by opacity, not by re-ordering the tree. */
  const failLayer = s('g', { class: 'atl-lanes atl-lanes--failure' });
  FAILURES.forEach((f) => failLayer.appendChild(buildLane(f, 'failure')));
  svg.appendChild(failLayer);

  const laneLayer = s('g', { class: 'atl-lanes atl-lanes--route' });
  ROUTES.forEach((r) => laneLayer.appendChild(buildLane(r, 'route')));
  svg.appendChild(laneLayer);

  const nodeLayer = s('g', { class: 'atl-nodes atl-plane', 'data-depth': '1' });
  NODES.forEach((n) => nodeLayer.appendChild(buildNode(n)));
  svg.appendChild(nodeLayer);

  return svg;
}

export { REGION_NODES, centre };
