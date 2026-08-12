/* ============================================================
   terrium — TERRIUM ATLAS topology

   The atlas is a map of the whole system, drawn once from this
   file. Nothing here knows anything about the DOM: this module
   is geometry and topology only, and `atlas/render.js` is the
   only thing that turns it into shapes.

   Coordinate space is a single wide plate. The camera crops it;
   it is never re-laid-out per breakpoint, because a map that
   rearranges itself is not a map.

   READ THIS BEFORE EDITING GEOMETRY
   Routes carry explicit `via` waypoints in absolute atlas
   coordinates. They are not auto-routed. That is deliberate:
   auto-routing between boxes is what produces the generic
   flowchart look the atlas exists to avoid. The waypoints put
   every line into a shared corridor grid, the way a transit
   diagram does, so the map reads as infrastructure.

   Corridor lanes currently in use — keep new routes on these:
     vertical    x =  300  430  660  1300  1320  1370  1470
                 x = 1900  2050  2340  2660  2930  2970  3150
     horizontal  y =  690  1420  1450  1490
   ============================================================ */

/** The whole drawable world.
    Height carries deliberate margin below the execution layer (which ends
    at y=2030): the stage draws a vignette over its lower edge, and without
    clear substrate down there the runtime rack fades out mid-module. */
export const ATLAS = { w: 3800, h: 2280 };

/* Zoom levels. Each level is a real change of information density,
   not a scale factor: the renderer reads `lod` to decide what may
   be drawn at all, so LAYER view is not just SYSTEM view enlarged. */
export const ZOOM = [
  {
    id: 'system',
    word: 'SYSTEM',
    lod: 'system',
    /* Bounds the architecture, not the plate. Content spans x 100→3700 and
       y 90→2030, but every region sets its name and coordinate ABOVE its own
       box (down to y-46), and the evidence region's box starts at y=90 — so
       framing from y=90 decapitates the topmost labels. Hence y=20.
       The floor sits at 2090 to clear the stage's bottom vignette, which
       otherwise fades out the runtime rack mid-module. */
    frame: { x: 60, y: 20, w: 3680, h: 2070 },
    caption: 'Seven regions. Eight declared routes.'
  },
  {
    id: 'layers',
    word: 'LAYERS',
    lod: 'layers',
    frame: { x: 560, y: 40, w: 2560, h: 1500 },
    caption: 'Every module, every route, every information type.'
  },
  {
    id: 'agents',
    word: 'AGENTS',
    lod: 'agents',
    frame: { x: 1300, y: 560, w: 1700, h: 1000 },
    caption: 'Ports, scope guards and notation at working distance.'
  }
];

/* ------------------------------------------------------------
   REGIONS
   `character` is the single switch the renderer uses to decide a
   region's drawing language. Each region is built differently on
   purpose — an evidence archive should not be drawn with the same
   marks as a compute rack, or the map says they are the same kind
   of thing, which is the central lie of every generic diagram.
   ------------------------------------------------------------ */
export const REGIONS = [
  {
    id: 'intake',
    index: '01',
    word: 'HUMAN INTAKE',
    character: 'open',
    coord: 'R01 / 00.4W',
    note: 'Where a person states intent',
    box: { x: 100, y: 760, w: 520, h: 560 }
  },
  {
    id: 'evidence',
    index: '03',
    word: 'EVIDENCE LAYER',
    character: 'archive',
    coord: 'R03 / 12.8N',
    note: 'Conceptual source records — illustrative only',
    box: { x: 700, y: 90, w: 1180, h: 560 }
  },
  {
    id: 'interpretation',
    index: '02',
    word: 'INTERPRETATION LAYER',
    character: 'facet',
    coord: 'R02 / 04.1W',
    note: 'Language becomes a stated method',
    box: { x: 740, y: 720, w: 520, h: 640 }
  },
  {
    id: 'configuration',
    index: '04',
    word: 'CONFIGURATION LAYER',
    character: 'plate',
    coord: 'R04 / 06.6C',
    note: 'Mechanical assembly of a runnable scope',
    box: { x: 1380, y: 720, w: 560, h: 660 }
  },
  {
    id: 'execution',
    index: '05',
    word: 'EXECUTION LAYER',
    character: 'rack',
    coord: 'R05 / 08.2S',
    note: 'Where the arithmetic actually happens',
    box: { x: 1340, y: 1560, w: 700, h: 470 }
  },
  {
    id: 'trust',
    index: '06',
    word: 'TRUST LAYER',
    character: 'shield',
    coord: 'R06 / 14.0E',
    note: 'Nothing leaves without passing through',
    dominant: true,
    box: { x: 2080, y: 640, w: 820, h: 820 },
    ring: { cx: 2490, cy: 1050, outer: 352, inner: 246, facets: 24 }
  },
  {
    id: 'output',
    index: '07',
    word: 'OUTPUT LAYER',
    character: 'paper',
    coord: 'R07 / 19.3E',
    note: 'The record the architecture produces',
    box: { x: 3000, y: 700, w: 700, h: 700 }
  }
];

/* ------------------------------------------------------------
   NODES
   `kind` refines `character` for a single module. `status` is the
   illustrated run's outcome for that module and always resolves
   to a word + glyph, never a colour alone.
   ------------------------------------------------------------ */
export const NODES = [
  /* --- 01 HUMAN INTAKE — quiet, open, unfenced ------------- */
  {
    id: 'question', region: 'intake', kind: 'open-major', coord: '01.1',
    label: 'Scientific Question', sub: 'PLAIN LANGUAGE', status: 'user',
    box: { x: 150, y: 830, w: 420, h: 150 }
  },
  {
    id: 'setup-files', region: 'intake', kind: 'open', coord: '01.2',
    label: 'Uploaded Setup Files', sub: 'OPTIONAL', status: 'user',
    box: { x: 150, y: 1020, w: 420, h: 110 }
  },
  {
    id: 'decision-point', region: 'intake', kind: 'open', coord: '01.3',
    label: 'User Decision Point', sub: 'HELD OPEN', status: 'user',
    box: { x: 150, y: 1170, w: 420, h: 110 }
  },

  /* --- 02 INTERPRETATION LAYER ---------------------------- */
  {
    id: 'model-picker', region: 'interpretation', kind: 'facet-major', coord: '02.1',
    label: 'Model Picker', sub: 'METHOD SELECTION', status: 'supported',
    box: { x: 790, y: 790, w: 420, h: 150 }
  },
  {
    id: 'domain-class', region: 'interpretation', kind: 'facet', coord: '02.2',
    label: 'Domain Classification', sub: 'FIELD + REGIME', status: 'supported',
    box: { x: 790, y: 980, w: 420, h: 120 }
  },
  {
    id: 'constraint-recognition', region: 'interpretation', kind: 'facet', coord: '02.3',
    label: 'Constraint Recognition', sub: 'LIMITS + BOUNDS', status: 'supported',
    box: { x: 790, y: 1140, w: 420, h: 120 }
  },

  /* --- 03 EVIDENCE LAYER ----------------------------------
     Five conceptual sources over one retrieval manifold. Every
     card is labelled CONCEPTUAL SOURCE and nothing in the atlas
     claims a live connection to any of these services. */
  {
    id: 'src-pubmed', region: 'evidence', kind: 'archive', coord: '03.1',
    label: 'PubMed', sub: 'CONCEPTUAL SOURCE / LITERATURE', status: 'pending',
    leaves: 5, box: { x: 740, y: 210, w: 190, h: 230 }
  },
  {
    id: 'src-semantic', region: 'evidence', kind: 'archive', coord: '03.2',
    label: 'Semantic Scholar', sub: 'CONCEPTUAL SOURCE / CITATION GRAPH', status: 'pending',
    leaves: 7, box: { x: 950, y: 210, w: 190, h: 230 }
  },
  {
    id: 'src-openalex', region: 'evidence', kind: 'archive', coord: '03.3',
    label: 'OpenAlex', sub: 'CONCEPTUAL SOURCE / COVERAGE', status: 'pending',
    leaves: 6, box: { x: 1160, y: 210, w: 190, h: 230 }
  },
  {
    id: 'src-crossref', region: 'evidence', kind: 'archive', coord: '03.4',
    label: 'CrossRef', sub: 'CONCEPTUAL SOURCE / CITATION CONFIRMATION', status: 'pending',
    leaves: 4, box: { x: 1370, y: 210, w: 190, h: 230 }
  },
  {
    id: 'src-arxiv', region: 'evidence', kind: 'archive', coord: '03.5',
    label: 'arXiv', sub: 'CONCEPTUAL SOURCE / METHODOLOGY', status: 'pending',
    leaves: 6, box: { x: 1580, y: 210, w: 190, h: 230 }
  },
  {
    id: 'literature-retrieval', region: 'evidence', kind: 'manifold', coord: '03.0',
    label: 'Literature Retrieval', sub: 'EVIDENCE OBJECT ASSEMBLY', status: 'supported',
    box: { x: 740, y: 490, w: 1030, h: 110 }
  },

  /* --- 04 CONFIGURATION LAYER ----------------------------
     Nodes stop at x=1830 so the 1900 riser stays clear. */
  {
    id: 'equation-selector', region: 'configuration', kind: 'plate', coord: '04.1',
    label: 'Equation Selector', sub: 'FORM OF THE MODEL', status: 'supported',
    box: { x: 1430, y: 790, w: 400, h: 120 }
  },
  {
    id: 'parameter-builder', region: 'configuration', kind: 'plate-major', coord: '04.2',
    label: 'Parameter Builder', sub: 'VALUES + SOURCE SCOPE', status: 'supported',
    box: { x: 1430, y: 930, w: 400, h: 140 }
  },
  {
    id: 'scope-guard', region: 'configuration', kind: 'plate', coord: '04.3',
    label: 'Scope Guard', sub: 'REFUSES OUT-OF-SCOPE USE', status: 'supported',
    box: { x: 1430, y: 1090, w: 400, h: 110 }
  },
  {
    id: 'assumption-register', region: 'configuration', kind: 'plate', coord: '04.4',
    label: 'Assumption Register', sub: 'WHAT WAS ASSUMED', status: 'review',
    box: { x: 1430, y: 1220, w: 400, h: 110 }
  },

  /* --- 05 EXECUTION LAYER -------------------------------- */
  {
    id: 'execution-router', region: 'execution', kind: 'router', coord: '05.0',
    label: 'Execution Router', sub: 'ENVIRONMENT SELECTION', status: 'supported',
    box: { x: 1390, y: 1630, w: 260, h: 396 }
  },
  {
    id: 'rt-browser', region: 'execution', kind: 'rack', coord: '05.1',
    label: 'Browser Runtime', sub: 'LIGHT ANALYTICAL WORK', status: 'pending',
    box: { x: 1710, y: 1630, w: 280, h: 84 }
  },
  {
    id: 'rt-ode', region: 'execution', kind: 'rack-active', coord: '05.2',
    label: 'Local ODE Runtime', sub: 'SELECTED FOR THIS RUN', status: 'supported',
    box: { x: 1710, y: 1734, w: 280, h: 84 }
  },
  {
    id: 'rt-backend', region: 'execution', kind: 'rack', coord: '05.3',
    label: 'Backend Runtime', sub: 'HEAVIER NUMERICAL WORK', status: 'pending',
    box: { x: 1710, y: 1838, w: 280, h: 84 }
  },
  {
    id: 'rt-hpc', region: 'execution', kind: 'rack-external', coord: '05.4',
    label: 'User-Provided HPC / Cloud', sub: 'OUTSIDE TERRIUM', status: 'blocked',
    box: { x: 1710, y: 1942, w: 280, h: 84 }
  },

  /* --- 06 TRUST LAYER — four gates on one ring ----------- */
  {
    id: 'hallucination-check', region: 'trust', kind: 'shield', coord: '06.1',
    label: 'Hallucination Check', sub: 'EVIDENCE BASIS', status: 'supported',
    box: { x: 2200, y: 760, w: 280, h: 130 }
  },
  {
    id: 'correctness', region: 'trust', kind: 'shield', coord: '06.2',
    label: 'Correctness Verification', sub: 'BEHAVIOUR SANITY', status: 'supported',
    box: { x: 2520, y: 760, w: 280, h: 130 }
  },
  {
    id: 'critique', region: 'trust', kind: 'shield-review', coord: '06.3',
    label: 'Critique', sub: 'DISCLOSES WEAKNESS', status: 'review',
    box: { x: 2200, y: 1210, w: 280, h: 130 }
  },
  {
    id: 'polish', region: 'trust', kind: 'shield', coord: '06.4',
    label: 'Polish', sub: 'RECORD FORMATTING', status: 'supported',
    box: { x: 2520, y: 1210, w: 280, h: 130 }
  },

  /* --- 07 OUTPUT LAYER — pale record ---------------------- */
  {
    id: 'notebook', region: 'output', kind: 'paper-major', coord: '07.1',
    label: 'Interactive Notebook', sub: 'THE RUN, RE-RUNNABLE', status: 'supported',
    box: { x: 3050, y: 770, w: 600, h: 190 }
  },
  {
    id: 'verification-record', region: 'output', kind: 'paper', coord: '07.2',
    label: 'Verification Record', sub: 'WHAT WAS CHECKED', status: 'supported',
    box: { x: 3050, y: 990, w: 600, h: 120 }
  },
  {
    id: 'source-trail', region: 'output', kind: 'paper', coord: '07.3',
    label: 'Source Trail', sub: 'CLAIM TO BASIS', status: 'supported',
    box: { x: 3050, y: 1130, w: 600, h: 120 }
  },
  {
    id: 'setup-package', region: 'output', kind: 'paper', coord: '07.4',
    label: 'Setup Package', sub: 'FOR COMPUTE TERRIUM CANNOT RUN', status: 'review',
    box: { x: 3050, y: 1270, w: 600, h: 120 }
  }
];

/** id → node, built once. */
export const NODE = Object.fromEntries(NODES.map((n) => [n.id, n]));
/** id → region, built once. */
export const REGION = Object.fromEntries(REGIONS.map((r) => [r.id, r]));

/* ------------------------------------------------------------
   ROUTES
   The eight declared routes of the architecture. Each is a real
   information path with a stated payload — `info` is what the
   reader sees on hover, and it names the *type* of information
   travelling, not a decoration.

   `points` is the complete polyline in atlas coordinates. Segments
   were checked against each other: none of the eight cross.
   ------------------------------------------------------------ */
export const ROUTES = [
  {
    id: 'r-question-model',
    from: 'question', to: 'model-picker',
    word: 'QUESTION \u2192 MODEL PICKER',
    info: 'Stated question + isolated quantities',
    points: [[570, 905], [700, 905], [700, 865], [790, 865]]
  },
  {
    id: 'r-model-literature',
    from: 'model-picker', to: 'literature-retrieval',
    word: 'MODEL PICKER \u2192 LITERATURE RETRIEVAL',
    info: 'Method identity + required quantities',
    points: [[930, 790], [930, 600]]
  },
  {
    id: 'r-literature-config',
    from: 'literature-retrieval', to: 'parameter-builder',
    word: 'LITERATURE RETRIEVAL \u2192 CONFIGURATION',
    info: 'Evidence objects + source scope',
    points: [[1770, 545], [1880, 545], [1880, 1000], [1830, 1000]]
  },
  {
    id: 'r-config-execution',
    from: 'parameter-builder', to: 'execution-router',
    word: 'CONFIGURATION \u2192 EXECUTION ROUTER',
    info: 'Parameter proposal + source scope',
    points: [[1430, 1000], [1400, 1000], [1400, 1500], [1470, 1500], [1470, 1630]]
  },
  {
    id: 'r-execution-trust',
    from: 'rt-ode', to: 'correctness',
    word: 'EXECUTION \u2192 TRUST LAYER',
    info: 'Illustrative result series + run manifest',
    points: [[1990, 1776], [2050, 1776], [2050, 1490], [2490, 1490], [2490, 1402]]
  },
  {
    id: 'r-trust-notebook',
    from: 'polish', to: 'notebook',
    word: 'TRUST LAYER \u2192 NOTEBOOK RECORD',
    info: 'Checked claims + disclosed assumptions',
    points: [[2800, 1275], [2930, 1275], [2930, 865], [3050, 865]]
  },
  {
    /* An upstream return. The critique does not merely annotate the record —
       it writes back into the register the configuration layer holds, so the
       assumption is carried by the run itself and not only by the report. */
    id: 'r-critique-register',
    from: 'critique', to: 'assumption-register',
    word: 'CRITIQUE \u2192 ASSUMPTION REGISTER',
    info: 'Scope disclosure returned upstream',
    upstream: true,
    points: [[2200, 1275], [1830, 1275]]
  },
  {
    id: 'r-hallucination-trail',
    from: 'hallucination-check', to: 'source-trail',
    word: 'HALLUCINATION CHECK \u2192 EVIDENCE TRAIL',
    info: 'Claim-to-basis mapping',
    points: [[2340, 760], [2340, 600], [3720, 600], [3720, 1190], [3650, 1190]]
  }
];

/* ------------------------------------------------------------
   FAILURE PATHS
   Shown in FAILURE mode. These are the most persuasive thing on
   the map: a system that shows how it declines is more credible
   than one that only shows itself succeeding. Each names the
   trigger and the safe consequence, and none of them end in a
   silent guess.
   ------------------------------------------------------------ */
export const FAILURES = [
  {
    id: 'f-ambiguous',
    index: 'F1',
    from: 'model-picker', to: 'decision-point',
    word: 'QUESTION AMBIGUITY',
    trigger: 'The question does not determine a single method.',
    consequence: 'Terrium returns a clarification request instead of guessing a model.',
    info: 'Clarification request + candidate readings',
    status: 'user',
    points: [[790, 930], [660, 930], [660, 1225], [570, 1225]]
  },
  {
    id: 'f-source-gap',
    index: 'F2',
    from: 'hallucination-check', to: 'critique',
    word: 'SOURCE GAP',
    trigger: 'A constant has no relevant basis in the retrieved evidence.',
    consequence: 'The claim is flagged unsupported. No source is invented to cover it.',
    info: 'Unsupported-claim flag',
    status: 'blocked',
    points: [[2340, 890], [2340, 1210]]
  },
  {
    id: 'f-compute-boundary',
    index: 'F3',
    from: 'rt-hpc', to: 'setup-package',
    word: 'COMPUTE BOUNDARY',
    trigger: 'The method requires compute Terrium does not provide.',
    consequence: 'A complete setup package is prepared for the user\u2019s own environment.',
    info: 'Runnable setup package + environment manifest',
    status: 'review',
    points: [[1990, 1984], [3350, 1984], [3350, 1390]]
  },
  {
    id: 'f-sanity',
    index: 'F4',
    from: 'correctness', to: 'notebook',
    word: 'SANITY CHECK PROBLEM',
    trigger: 'The output does not show the behaviour the method requires.',
    consequence: 'The execution is withheld from the final record rather than reported.',
    info: 'Withheld run + reason',
    status: 'blocked',
    terminal: 'withheld',
    points: [[2800, 825], [2960, 825]]
  },
  {
    id: 'f-scope',
    index: 'F5',
    from: 'critique', to: 'notebook',
    word: 'DISCLOSED ASSUMPTION',
    trigger: 'A condition shaping the run is not established by the source scope.',
    consequence: 'The assumption is disclosed on the face of the record, not buried.',
    info: 'Scope disclosure carried into the record',
    status: 'review',
    points: [[2410, 1340], [2410, 1440], [3010, 1440], [3010, 920], [3050, 920]]
  }
];

/* ------------------------------------------------------------
   RUN SEQUENCE
   The illustrative pipeline, as the atlas plays it. Each beat
   activates a node and, optionally, the route that carried the
   information into it. `at` is elapsed ms from the start.
   ------------------------------------------------------------ */
export const ATLAS_RUN = [
  { at: 0, node: 'question', log: 'QUESTION ACCEPTED / PLAIN LANGUAGE' },
  { at: 700, route: 'r-question-model', node: 'model-picker', log: 'METHOD SELECTED / SATURATION KINETICS \u2014 ILLUSTRATIVE' },
  { at: 1500, node: 'domain-class', log: 'DOMAIN CLASSIFIED / ENZYME KINETICS' },
  { at: 2000, node: 'constraint-recognition', log: 'CONSTRAINTS RECOGNISED / BOUNDS ATTACHED' },
  { at: 2600, route: 'r-model-literature', node: 'literature-retrieval', log: 'EVIDENCE ROUTED / 3 ILLUSTRATIVE OBJECTS' },
  { at: 3100, node: 'src-pubmed' },
  { at: 3260, node: 'src-semantic' },
  { at: 3420, node: 'src-openalex' },
  { at: 3580, node: 'src-crossref' },
  { at: 3740, node: 'src-arxiv' },
  { at: 4300, route: 'r-literature-config', node: 'equation-selector', log: 'EQUATION FORM FIXED' },
  { at: 4800, node: 'parameter-builder', log: 'PARAMETERS ASSEMBLED / SOURCE SCOPE ATTACHED' },
  { at: 5300, node: 'scope-guard', log: 'SCOPE GUARD ENGAGED' },
  { at: 5700, node: 'assumption-register', log: 'ASSUMPTION REGISTERED / 1 ENTRY' },
  { at: 6300, route: 'r-config-execution', node: 'execution-router', log: 'EXECUTION ENVIRONMENT SELECTED' },
  { at: 6900, node: 'rt-ode', log: 'LOCAL ODE RUNTIME / ILLUSTRATIVE RUN' },
  { at: 7700, route: 'r-execution-trust', node: 'correctness', log: 'SANITY CHECK COMPLETE' },
  { at: 8400, node: 'hallucination-check', log: 'CLAIM TRACE COMPLETE' },
  { at: 8900, route: 'r-hallucination-trail', node: 'source-trail', log: 'SOURCE TRAIL BOUND' },
  { at: 9500, node: 'critique', log: 'REVIEW POINT ADDED / TEMPERATURE CONDITION' },
  { at: 10000, route: 'r-critique-register', node: 'assumption-register', log: 'DISCLOSURE RETURNED UPSTREAM' },
  { at: 10600, node: 'polish', log: 'RECORD FORMATTED' },
  { at: 11200, route: 'r-trust-notebook', node: 'notebook', log: 'ILLUSTRATED RECORD COMPLETE' },
  { at: 11700, node: 'verification-record' },
  { at: 12000, node: 'setup-package', log: 'RUN CLOSED / ILLUSTRATIVE ARCHITECTURE' }
];

/* ------------------------------------------------------------
   DERIVED INDEXES
   Built once at module load so hover tracing never has to scan.
   ------------------------------------------------------------ */

/** node id → routes leaving it. */
export const OUT = {};
/** node id → routes arriving at it. */
export const IN = {};
for (const r of ROUTES) {
  (OUT[r.from] ||= []).push(r);
  (IN[r.to] ||= []).push(r);
}

/** region id → its nodes, in declaration order. */
export const REGION_NODES = {};
for (const n of NODES) (REGION_NODES[n.region] ||= []).push(n);

/**
 * The full path through a node: everything upstream that feeds it and
 * everything downstream it reaches. Hovering a node lights this whole
 * chain, which is the point — a component means nothing without the
 * path it sits on. Upstream returns are followed too, but only once,
 * so the critique→register edge cannot loop the walk forever.
 */
export function tracePath(nodeId) {
  const nodes = new Set([nodeId]);
  const routes = new Set();
  const walk = (id, dir) => {
    const edges = dir === 'up' ? IN[id] : OUT[id];
    if (!edges) return;
    for (const r of edges) {
      if (routes.has(r.id)) continue;
      routes.add(r.id);
      const next = dir === 'up' ? r.from : r.to;
      nodes.add(next);
      walk(next, dir);
    }
  };
  walk(nodeId, 'up');
  walk(nodeId, 'down');
  return { nodes: [...nodes], routes: [...routes] };
}

/** Centre of a node box, for camera framing and port maths. */
export const centre = (box) => ({ x: box.x + box.w / 2, y: box.y + box.h / 2 });

