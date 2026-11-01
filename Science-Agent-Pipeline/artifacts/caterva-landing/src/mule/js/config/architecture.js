/* ============================================================
   caterva — architecture configuration
   The Evidence Cathedral is fully data-driven. Geometry lives in
   a single tall coordinate space (STAGE) and is rendered as SVG.
   Every visual state maps to a real pipeline concept.
   ============================================================ */

/** Master coordinate space for the cathedral. */
export const STAGE = { w: 1000, h: 1680, spine: 500 };

/** Status vocabulary. Never color-only: each carries a glyph + word. */
export const STATUS = {
  supported: { id: 'supported', word: 'SUPPORTED', glyph: '\u25C6', color: 'var(--status-supported)' },
  user: { id: 'user', word: 'USER-DEFINED', glyph: '\u25A0', color: 'var(--fog-teal)' },
  review: { id: 'review', word: 'REVIEW REQUIRED', glyph: '\u25B2', color: 'var(--status-review)' },
  blocked: { id: 'blocked', word: 'UNSUPPORTED', glyph: '\u2715', color: 'var(--status-blocked)' },
  pending: { id: 'pending', word: 'PENDING', glyph: '\u25CB', color: 'var(--status-pending)' }
};

/* ------------------------------------------------------------
   RUN STATE MACHINE
   Ordered stages. `at` is elapsed ms from run start.
   ------------------------------------------------------------ */
export const STAGES = [
  {
    id: 'idle', at: 0, rail: null,
    log: 'SYSTEM IDLE / AWAITING SCIENTIFIC QUESTION'
  },
  {
    id: 'questionAccepted', at: 0, rail: 'question', camera: 'question',
    title: 'QUESTION ACCEPTED',
    log: 'QUESTION / 0007 ACCEPTED'
  },
  {
    // The system separates scientific quantities from the sentence. Without
    // this beat the run jumps from language straight to a chosen model, and
    // the interpretation step — the part that is actually hard — is invisible.
    id: 'conceptsIsolated', at: 1250, rail: 'question', camera: 'question',
    title: 'CONCEPTS ISOLATED',
    log: 'QUESTION PARSED / 2 QUANTITIES, 1 RELATION'
  },
  {
    id: 'modelSelected', at: 2600, rail: 'model', camera: 'array',
    title: 'MODEL IDENTIFIED',
    log: 'MODEL CLASSIFIED / SATURATION KINETICS \u2014 ILLUSTRATIVE'
  },
  {
    id: 'literatureRetrieved', at: 4100, rail: 'evidence', camera: 'array',
    title: 'EVIDENCE RETRIEVED',
    log: 'EVIDENCE OBJECTS EMITTED / 3 DEMO RECORDS'
  },
  {
    id: 'configurationBuilt', at: 5700, rail: 'configure', camera: 'config',
    title: 'CONFIGURATION BUILT',
    log: 'PARAMETER SCOPE ATTACHED / 6 DOCKED, 1 FOR REVIEW'
  },
  {
    id: 'executionRouted', at: 7200, rail: 'configure', camera: 'config',
    title: 'EXECUTION ROUTED',
    log: 'LOCAL SOLVER SELECTED / ODE RUNTIME \u2014 ILLUSTRATED'
  },
  {
    id: 'simulationExecuted', at: 8600, rail: 'execute', camera: 'core',
    title: 'SIMULATION EXECUTED',
    log: 'ILLUSTRATIVE OUTPUT FORMED / SATURATION CURVE'
  },
  {
    id: 'hallucinationChecked', at: 10300, rail: 'verify', camera: 'vault',
    title: 'HALLUCINATION CHECK',
    log: 'CLAIM TRACE COMPLETE / 3 OF 6 TIED TO EVIDENCE'
  },
  {
    id: 'correctnessChecked', at: 11800, rail: 'verify', camera: 'vault',
    title: 'CORRECTNESS VERIFICATION',
    log: 'BEHAVIOUR CHECKED / WITHIN METHOD ENVELOPE'
  },
  {
    id: 'critiqueCompleted', at: 13300, rail: 'verify', camera: 'vault',
    title: 'CRITIQUE',
    log: 'ASSUMPTION DISCLOSED / TEMPERATURE OUTSIDE SOURCE SCOPE'
  },
  {
    id: 'polishCompleted', at: 14800, rail: 'verify', camera: 'vault',
    title: 'POLISH',
    log: 'RECORD COMPOSED / DISCLOSURE RETAINED'
  },
  {
    id: 'recordReleased', at: 16300, rail: 'record', camera: 'record',
    title: 'RECORD RELEASED',
    log: 'RECORD RELEASED / RUN 0007 INSPECTABLE'
  }
];

export const RUN_DURATION = STAGES[STAGES.length - 1].at + 1300;

/** Compact progress rail. */
export const RAIL = [
  { id: 'question', label: 'QUESTION' },
  { id: 'model', label: 'MODEL' },
  { id: 'evidence', label: 'EVIDENCE' },
  { id: 'configure', label: 'CONFIGURE' },
  { id: 'execute', label: 'EXECUTE' },
  { id: 'verify', label: 'VERIFY' },
  { id: 'record', label: 'RECORD' }
];

/* ------------------------------------------------------------
   CAMERA FRAMES — cinematic framing within the stage space
   ------------------------------------------------------------ */
export const FRAMES = {
  /* The wide shot is an elevation drawing, and it is framed as one: wide
     enough to include the sheet margins on both sides, centred on the spine.
     A portrait monument cannot fill a landscape screen, so the choice is
     between empty letterboxing and composed margin. This is the margin. */
  full: { x: -700, y: -40, w: 2400, h: 1760 },
  question: { x: 130, y: 10, w: 740, h: 560 },
  array: { x: 60, y: 150, w: 880, h: 700 },
  config: { x: 130, y: 546, w: 740, h: 500 },
  /* Held above the record plate. The record is archive paper and the vault is
     void-dark, so any part of the plate inside this frame becomes the
     brightest object on screen and steals the trust layer's moment. */
  vault: { x: 120, y: 806, w: 760, h: 560 },
  core: { x: 300, y: 930, w: 400, h: 360 },
  record: { x: 150, y: 1330, w: 700, h: 340 }
};

/* ------------------------------------------------------------
   MOBILE JOURNEY
   A phone is not a small desktop. Framing the whole cathedral on a
   narrow viewport renders the instrument text below legibility, so
   mobile walks the same architecture as a sequence of close, upright
   stations — more steps, each one readable. The geometry is identical;
   only the itinerary changes.

   On a portrait viewport the frame WIDTH sets the scale (height is
   expanded to fit), so each station declares a centre and a width. A
   ~430-unit width keeps the 8px instrument text legible on a phone.
   ------------------------------------------------------------ */
const station = (id, label, cx, cy, w = 430, h = 220) => ({
  id, label, frame: { x: cx - w / 2, y: cy - h / 2, w, h }
});

export const MOBILE_JOURNEY = [
  // The chamber is 514 units wide, so on a phone its width binds the scale and
  // the visible band becomes far taller than the frame asks for. Centred on the
  // chamber alone that band fills with empty void above the stage, so it is
  // dropped to hold the chamber and the array it feeds instead.
  station('m-question', 'Question', 500, 258, 560),
  station('m-array-a', 'Model + Retrieval', 318, 372),
  station('m-array-b', 'Configure + Route', 694, 372),
  station('m-config-a', 'Parameters / left', 300, 673),
  station('m-config-b', 'Parameters / right', 700, 673),
  station('m-core', 'Simulation Core', 500, 1100, 400),
  station('m-s01', 'Hallucination Check', 226, 968),
  station('m-s02', 'Correctness Check', 774, 968),
  station('m-s03', 'Critique', 226, 1240),
  station('m-disclosure', 'Disclosed Assumption', 500, 1283, 400),
  station('m-s04', 'Polish', 774, 1240),
  station('m-record', 'Verified Record', 500, 1514, 660, 300)
];

/** Run stage → mobile station. */
export const MOBILE_STATION = {
  questionAccepted: 'm-question',
  conceptsIsolated: 'm-question',
  modelSelected: 'm-array-a',
  literatureRetrieved: 'm-array-b',
  configurationBuilt: 'm-config-a',
  executionRouted: 'm-config-b',
  simulationExecuted: 'm-core',
  hallucinationChecked: 'm-s01',
  correctnessChecked: 'm-s02',
  critiqueCompleted: 'm-s03',
  polishCompleted: 'm-s04',
  recordReleased: 'm-record'
};

/* ------------------------------------------------------------
   TIER 1 — QUESTION CHAMBER
   ------------------------------------------------------------ */
export const QUESTION_CHAMBER = {
  id: 'question-chamber',
  kind: 'chamber',
  label: 'QUESTION / 0007',
  state: 'ACTIVE INPUT',
  // Taller than the sentence needs: the lower bay holds the isolated
  // concept rack produced at stage 02.
  box: { x: 236, y: 52, w: 528, h: 156 },
  inset: 96,
  aperture: { x: 500, y: 196 },
  activeAt: 'questionAccepted'
};

/* ------------------------------------------------------------
   TIER 2 — INTERPRETATION ARRAY
   Four faceted modules. Deliberately uneven tops: asymmetry
   held together by the central axis.
   ------------------------------------------------------------ */
export const ARRAY_MODULES = [
  {
    id: 'model-picker',
    kind: 'module',
    index: '01',
    name: 'Model Picker',
    label: 'MODEL PICKER',
    silhouette: 'lens',
    box: { x: 148, y: 268, w: 152, h: 190 },
    activeAt: 'modelSelected',
    output: { label: 'SELECTED MODEL', value: 'Michaelis\u2013Menten kinetics' }
  },
  {
    id: 'literature-retrieval',
    kind: 'module',
    index: '02',
    name: 'Literature Retrieval',
    label: 'LITERATURE RETRIEVAL',
    silhouette: 'stack',
    box: { x: 336, y: 252, w: 152, h: 218 },
    activeAt: 'literatureRetrieved',
    output: { label: 'EVIDENCE OBJECTS FOUND', value: '3 illustrative records' }
  },
  {
    id: 'configuration-agent',
    kind: 'module',
    index: '03',
    name: 'Configuration',
    label: 'CONFIGURATION',
    silhouette: 'lattice',
    box: { x: 524, y: 260, w: 152, h: 204 },
    activeAt: 'configurationBuilt',
    output: { label: 'PARAMETER SCHEMA CREATED', value: 'Km / Vmax / [S] / T / t / \u03B5' }
  },
  {
    id: 'compute-router',
    kind: 'module',
    index: '04',
    name: 'Compute Router',
    label: 'COMPUTE ROUTER',
    silhouette: 'switch',
    box: { x: 712, y: 276, w: 152, h: 176 },
    activeAt: 'executionRouted',
    output: { label: 'EXECUTION ENVIRONMENT', value: 'Local ODE runtime / illustrated' }
  }
];

/* ------------------------------------------------------------
   EVIDENCE OBJECTS — architectural data artifacts
   Illustrative only. No invented citations, DOIs or PMIDs.

   Docks sit in the open channels between the parameter berth
   columns and the central assembly core: evidence physically
   stands between a source and the parameter it supports.
   ------------------------------------------------------------ */
export const EVIDENCE = [
  {
    id: 'ev-method',
    kind: 'evidence',
    label: 'DEMO SOURCE',
    sub: 'KINETICS METHOD',
    // Scope travels with the object. A value without the conditions it was
    // measured under is the failure this whole architecture exists to prevent,
    // so scope is never a detail held somewhere else. `tag` is what fits on the
    // artifact in the 106px channel between berth and core; `scope` is the full
    // statement the inspector reads. Same fact, two densities.
    tag: 'STATED CONDITIONS',
    scope: 'ILLUSTRATIVE ENZYME / STATED CONDITIONS',
    form: 'sheet',
    origin: { x: 412, y: 470 },
    dock: { x: 386, y: 578 },
    tie: 'left',
    status: 'supported',
    supports: ['p-km', 'p-vmax']
  },
  {
    id: 'ev-scope',
    kind: 'evidence',
    label: 'DEMO SCOPE',
    sub: 'ENZYME CONDITIONS',
    tag: 'BOUNDED SET',
    scope: 'BOUNDED SET / NOT GENERALISED',
    form: 'shard',
    origin: { x: 412, y: 470 },
    dock: { x: 386, y: 682 },
    tie: 'left',
    status: 'supported',
    supports: ['p-vmax']
  },
  {
    id: 'ev-ode',
    kind: 'evidence',
    label: 'METHOD RECORD',
    sub: 'ODE SOLUTION',
    /* Was BROWSER ODE / BROWSER NUMERICAL INTEGRATION. The run this object
       belongs to has already routed away from the browser — the compute
       router's declared output four fields up is "Local ODE runtime" and its
       inspector record says heavier methods were routed away from the browser
       — so the evidence backing the solver tolerance cannot be browser
       integration. Caterva's ODE path is libroadrunner, which is not a
       browser. Same fact, two densities: `tag` fits the 106px channel,
       `scope` is what the inspector reads. */
    tag: 'ODE SOLVER',
    scope: 'LOCAL ODE RUNTIME / NUMERICAL INTEGRATION',
    form: 'capsule',
    origin: { x: 412, y: 470 },
    dock: { x: 614, y: 630 },
    tie: 'right',
    status: 'supported',
    supports: ['p-tol']
  }
];

/* ------------------------------------------------------------
   TIER 3 — CONFIGURATION ASSEMBLY
   Six parameter berths flanking a central core mechanism.
   ------------------------------------------------------------ */
export const ASSEMBLY = {
  id: 'configuration-assembly',
  kind: 'assembly',
  label: 'CONFIGURATION ASSEMBLY',
  box: { x: 176, y: 546, w: 648, h: 254 },
  core: { x: 500, y: 673, r: 58 },
  activeAt: 'configurationBuilt'
};

export const PARAMETERS = [
  { id: 'p-km', symbol: 'Km', name: 'Michaelis constant', value: '0.03 mM', status: 'supported', side: 'left', slot: 0, basis: 'BRENDA ref 286469 / human LDH, pyruvate' },
  { id: 'p-vmax', symbol: 'Vmax', name: 'Maximum velocity', value: '1.00 rel.', status: 'supported', side: 'left', slot: 1, basis: 'Demo source / enzyme kinetics method' },
  { id: 'p-s', symbol: '[S]', name: 'Substrate range', value: '0 \u2192 0.36 mM', status: 'user', side: 'left', slot: 2, basis: 'Example condition set by user' },
  { id: 'p-temp', symbol: 'T', name: 'Temperature', value: '37 \u00B0C', status: 'review', side: 'right', slot: 0, basis: 'Not established by sample source scope' },
  { id: 'p-time', symbol: 't', name: 'Reaction time', value: '120 s', status: 'user', side: 'right', slot: 1, basis: 'Example condition set by user' },
  { id: 'p-tol', symbol: '\u03B5', name: 'Solver tolerance', value: '1e\u22126', status: 'supported', side: 'right', slot: 2, basis: 'Method / ODE solution' }
];

/** Berth geometry: two flanking columns, docking toward the core. */
export const BERTH = { leftX: 262, rightX: 738, ys: [596, 673, 750], w: 148, h: 54 };

/* ------------------------------------------------------------
   TIER 4 — THE VERIFICATION VAULT
   ------------------------------------------------------------ */
export const VAULT = {
  id: 'verification-vault',
  kind: 'vault',
  label: 'THE VERIFICATION VAULT',
  center: { x: 500, y: 1100 },
  outer: { rx: 330, ry: 258 },
  inner: { rx: 250, ry: 190 },
  facets: 16
};

export const SENTINELS = [
  {
    id: 's-hallucination',
    kind: 'sentinel',
    index: '01',
    name: 'Hallucination Check',
    label: 'HALLUCINATION CHECK',
    short: 'TRACE',
    anchor: { x: 226, y: 964 },
    activeAt: 'hallucinationChecked',
    // 3 of 6, not 4: exactly three parameters carry `supported` status and
    // exactly three evidence objects exist to carry them. The remaining three
    // are 2 user-defined and 1 disclosed for review. A chain-of-custody
    // product cannot afford a count that does not reconcile with its own data.
    result: { label: 'TRACED', value: '3 / 6 to evidence', status: 'supported' }
  },
  {
    id: 's-correctness',
    kind: 'sentinel',
    index: '02',
    name: 'Correctness Verification',
    label: 'CORRECTNESS VERIFICATION',
    short: 'ENVELOPE',
    anchor: { x: 774, y: 964 },
    activeAt: 'correctnessChecked',
    result: { label: 'BEHAVIOUR', value: 'Within envelope', status: 'supported' }
  },
  {
    id: 's-critique',
    kind: 'sentinel',
    index: '03',
    name: 'Critique',
    label: 'CRITIQUE',
    short: 'SCOPE',
    anchor: { x: 226, y: 1236 },
    activeAt: 'critiqueCompleted',
    result: { label: 'DISCLOSED', value: '1 assumption', status: 'review' }
  },
  {
    id: 's-polish',
    kind: 'sentinel',
    index: '04',
    name: 'Polish',
    label: 'POLISH',
    short: 'RECORD',
    anchor: { x: 774, y: 1236 },
    activeAt: 'polishCompleted',
    result: { label: 'COMPOSED', value: 'Citations preserved', status: 'supported' }
  }
];

/* ------------------------------------------------------------
   TIER 5 — SIMULATION CORE
   ------------------------------------------------------------ */
export const CORE = {
  id: 'simulation-core',
  kind: 'core',
  label: 'SIMULATION CORE',
  caption: 'ILLUSTRATIVE KINETICS OUTPUT',
  box: { x: 372, y: 986, w: 256, h: 228 },
  plot: { x: 404, y: 1008, w: 196, h: 158 },
  activeAt: 'simulationExecuted',
  axes: { x: 'SUBSTRATE CONCENTRATION [S]', y: 'VELOCITY v' }
};

/** Illustrative curve model. Shape only — not a scientific claim. */
export const CURVE_MODEL = { vmax: 1, km: 0.03, sMax: 0.36, samples: 9, jitter: 0.026 };

/* ------------------------------------------------------------
   TIER 6 — VERIFIED SCIENTIFIC RECORD
   ------------------------------------------------------------ */
export const RECORD = {
  id: 'verified-record',
  kind: 'record',
  label: 'VERIFIED RUN / 0007',
  title: 'ILLUSTRATIVE MICHAELIS\u2013MENTEN KINETICS',
  box: { x: 196, y: 1394, w: 608, h: 240 },
  activeAt: 'recordReleased',
  lines: [
    { k: '6', v: 'CONFIGURATION PARAMETERS' },
    { k: '3', v: 'EVIDENCE OBJECTS' },
    { k: '4', v: 'VERIFICATION OPERATIONS' },
    { k: '1', v: 'ASSUMPTION DISCLOSED', status: 'review' }
  ]
};

/** Plain-text alternative to the visual architecture. */
export const PIPELINE_TEXT = [
  'Question',
  'Model Selection',
  'Literature Retrieval',
  'Configuration',
  'Execution Routing',
  'Hallucination Check',
  'Correctness Verification',
  'Critique',
  'Polish',
  'Verified Record'
];

export const DEMO_QUESTION = 'How does substrate concentration affect enzyme velocity?';
