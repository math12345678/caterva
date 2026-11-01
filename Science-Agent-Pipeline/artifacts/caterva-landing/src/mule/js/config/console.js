/* ============================================================
   caterva — LIVE ORCHESTRATION CONSOLE data

   Nine agents, each with a distinct responsibility, a visible
   input, a visible output and its own structural identity. The
   `glyph` field is what gives each agent a unique mark in the
   timeline: they are drawn differently because they do different
   work, not decorated differently.

   Status vocabulary is fixed and shared with the architecture:
     QUEUED / ACTIVE / ROUTING / CHECKING / SUPPORTED /
     REVIEW REQUIRED / COMPLETE / WITHHELD

   Every value below is illustrative. No real citation, DOI,
   PMID, journal, author, customer or benchmark appears.
   ============================================================ */

export const SCENARIO = {
  question: 'How does substrate concentration affect enzyme velocity?',
  label: 'DEMONSTRATION SCENARIO',
  note: 'Illustrative interface demonstration. Not a scientific result.'
};

/** Console status words, with the glyph that carries them without colour. */
export const CSTATUS = {
  queued:    { word: 'QUEUED',          glyph: '\u25CB', tone: 'pending' },
  active:    { word: 'ACTIVE',          glyph: '\u25D4', tone: 'active' },
  routing:   { word: 'ROUTING',         glyph: '\u25B8', tone: 'active' },
  checking:  { word: 'CHECKING',        glyph: '\u25CE', tone: 'active' },
  supported: { word: 'SUPPORTED',       glyph: '\u25C6', tone: 'supported' },
  review:    { word: 'REVIEW REQUIRED', glyph: '\u25B2', tone: 'review' },
  complete:  { word: 'COMPLETE',        glyph: '\u25C6', tone: 'supported' },
  withheld:  { word: 'WITHHELD',        glyph: '\u2715', tone: 'blocked' }
};

/* ------------------------------------------------------------
   THE NINE AGENTS
   `working` is the status while the agent runs; `settled` is its
   status once finished. `terminal` is the exact status word the
   brief specifies for the finished stage.
   ------------------------------------------------------------ */
export const AGENTS = [
  {
    id: 'model-picker', index: '01', name: 'MODEL PICKER',
    glyph: 'lens',
    working: 'active', settled: 'complete', terminal: 'MODEL CLASSIFIED',
    input: 'Plain-language question',
    output: 'Michaelis\u2013Menten kinetics selected',
    duration: 420,
    detail: 'Mass-action and Hill kinetics were considered and set aside. The choice is stated so a reviewer can disagree with it.',
    emits: null
  },
  {
    id: 'literature-retrieval', index: '02', name: 'LITERATURE RETRIEVAL',
    glyph: 'stack',
    working: 'routing', settled: 'complete', terminal: 'EVIDENCE ROUTED',
    input: 'Model + parameter needs',
    output: '3 illustrative evidence objects located',
    duration: 760,
    detail: 'Each evidence object is bound to the parameter it supports and carries its own scope. All three are demonstration records.',
    emits: 'evidence'
  },
  {
    id: 'configuration', index: '03', name: 'CONFIGURATION',
    glyph: 'assembly',
    working: 'active', settled: 'complete', terminal: 'CONFIGURATION BUILT',
    input: 'Selected model + evidence objects',
    output: 'Parameter schema and assumptions assembled',
    duration: 640,
    detail: 'Every value arrives with its basis and scope attached. Nothing is filled in with a typical value.',
    emits: 'params'
  },
  {
    id: 'execution-router', index: '04', name: 'EXECUTION ROUTER',
    glyph: 'switch',
    working: 'routing', settled: 'complete', terminal: 'EXECUTION ENVIRONMENT SELECTED',
    input: 'Method requirements',
    output: 'Local ODE runtime selected',
    duration: 380,
    detail: 'Browser runtime was insufficient for the integration. Caterva routes to real capability rather than appearing capable.',
    emits: null
  },
  {
    id: 'execution', index: '05', name: 'EXECUTION',
    glyph: 'core',
    working: 'active', settled: 'complete', terminal: 'ILLUSTRATIVE RUN COMPLETE',
    input: 'Configured model',
    output: 'Illustrative saturation curve generated',
    duration: 980,
    detail: 'The curve demonstrates the shape of the method. It is not a measurement and it is not a scientific result.',
    emits: 'plot'
  },
  {
    id: 'hallucination-check', index: '06', name: 'HALLUCINATION CHECK',
    glyph: 'sieve',
    working: 'checking', settled: 'supported', terminal: 'CLAIM TRACE COMPLETE',
    input: 'Claims and constants',
    output: 'Evidence trace complete',
    duration: 700,
    detail: 'Does not silently invent a source. Any claim without a relevant basis is marked for review.',
    emits: 'trail'
  },
  {
    id: 'correctness', index: '07', name: 'CORRECTNESS VERIFICATION',
    glyph: 'gauge',
    working: 'checking', settled: 'supported', terminal: 'SANITY CHECK COMPLETE',
    input: 'Execution output',
    output: 'Expected illustrative saturation behavior observed',
    duration: 620,
    detail: 'Code that ran is not science that holds. A failed check withholds the execution from the record.',
    emits: 'verify'
  },
  {
    id: 'critique', index: '08', name: 'CRITIQUE',
    glyph: 'fracture',
    working: 'checking', settled: 'review', terminal: 'REVIEW POINT ADDED',
    input: 'Configuration + scope',
    output: 'One temperature assumption disclosed',
    duration: 660,
    /* Verbatim from the brief. This sentence is the product's position on
       honesty, and paraphrasing it would soften exactly the thing it says. */
    disclosure: 'Temperature condition is visible in the final record because the illustrative source scope does not establish it.',
    detail: 'A disclosure is not suppressed because the run otherwise succeeded.',
    emits: 'assumption'
  },
  {
    id: 'polish', index: '09', name: 'POLISH',
    glyph: 'plate',
    working: 'active', settled: 'complete', terminal: 'RECORD FORMATTED',
    input: 'All validated and flagged outputs',
    output: 'Source-preserving notebook record',
    duration: 520,
    detail: 'Presentation may change. Provenance may not. No flag is tidied away to make the record read more cleanly.',
    emits: 'record'
  }
];

/* ------------------------------------------------------------
   THE FAILURE CASE
   The same scenario with a source gap, so the console can show
   the system declining rather than only succeeding. Only the
   agents that behave differently are overridden.
   ------------------------------------------------------------ */
export const FAILURE_CASE = {
  label: 'FAILURE CASE / SOURCE GAP',
  note: 'The same question, where the illustrative evidence does not establish a required constant.',
  overrides: {
    'literature-retrieval': {
      output: '1 evidence object located / 1 parameter unmatched',
      settled: 'review', terminal: 'EVIDENCE GAP FOUND',
      detail: 'A gap is returned as a gap. No plausible-looking source is substituted to fill it.',
      emits: 'evidence-gap'
    },
    configuration: {
      output: 'Schema assembled with 1 required value unmet',
      settled: 'review', terminal: 'CONFIGURATION INCOMPLETE',
      detail: 'The missing parameter is marked required and unmet rather than filled with a typical value.',
      emits: 'params-gap'
    },
    /* Execution is overridden as well, and this is the point of the case: a
       configuration with an unmet required value has nothing legitimate to
       integrate. A run that produced a curve here would be the exact failure
       the rest of the architecture exists to prevent. */
    execution: {
      output: 'Withheld / required constant unmet',
      settled: 'withheld', terminal: 'EXECUTION WITHHELD',
      detail: 'Caterva does not integrate a model with a missing required constant in order to have something to show.',
      emits: null
    },
    'hallucination-check': {
      output: 'Unsupported-claim flag raised',
      settled: 'withheld', terminal: 'UNSUPPORTED CLAIM FLAGGED',
      detail: 'The constant has no relevant evidence basis in this scenario, so it is flagged rather than reported.',
      emits: 'flags'
    },
    correctness: {
      output: 'Not run / configuration incomplete',
      settled: 'withheld', terminal: 'CHECK NOT RUN',
      detail: 'A check that did not run is listed as not run. It is never omitted from the record.',
      emits: 'verify-not-run'
    },
    critique: {
      output: 'Unsupported constant disclosed as blocking',
      settled: 'review', terminal: 'REVIEW POINT ADDED',
      disclosure: 'The run does not proceed to a final result, because a required constant has no source basis in the illustrative evidence scope.',
      detail: 'Caterva states the blocker instead of producing a number that looks finished.',
      emits: 'blocking'
    },
    polish: {
      output: 'Clarification request prepared',
      settled: 'review', terminal: 'RETURNED TO USER',
      detail: 'The output is a request for a source or a user-supplied value, not a result.',
      emits: 'clarification'
    }
  }
};

/* ------------------------------------------------------------
   OUTPUT WORKSPACE
   What the right-hand panel builds, in order. Each key matches an
   agent's `emits`, so the workspace assembles as a consequence of
   the timeline rather than on a separate schedule.
   ------------------------------------------------------------ */
export const WORKSPACE = {
  evidence: {
    title: 'Evidence trail',
    kind: 'evidence',
    items: [
      { ref: 'DEMO-01', role: 'Kinetics method record', scope: 'Illustrative enzyme conditions' },
      { ref: 'DEMO-02', role: 'Parameter basis', scope: 'Example substrate range' },
      { ref: 'DEMO-03', role: 'Method commentary', scope: 'Illustrative context' }
    ]
  },
  params: {
    title: 'Parameters',
    kind: 'params',
    items: [
      { name: 'Vmax', value: '1.00', unit: 'rel.', status: 'supported' },
      { name: 'Km', value: '0.03', unit: 'mM', status: 'supported' },
      { name: 'S range', value: '0 \u2013 0.36', unit: 'mM', status: 'user' },
      { name: 'Temperature', value: 'assumed', unit: '\u2014', status: 'review' }
    ]
  },
  plot: { title: 'Illustrative saturation curve', kind: 'plot' },
  verify: {
    title: 'Verification',
    kind: 'verify',
    items: [
      { check: 'Monotonic increase', result: 'Observed' },
      { check: 'Saturating plateau', result: 'Observed' },
      { check: 'Half-maximal at Km', result: 'Consistent' }
    ]
  },
  trail: { title: 'Claim trace', kind: 'trail', items: [
    { claim: 'Km value', basis: 'DEMO-02 / parameter basis' },
    { claim: 'Model form', basis: 'DEMO-01 / kinetics method record' }
  ] },
  assumption: {
    title: 'Disclosed assumption',
    kind: 'assumption',
    text: 'Temperature condition is visible in the final record because the illustrative source scope does not establish it.'
  },
  record: {
    title: 'Verified run',
    kind: 'record',
    lines: [
      'Model identified and stated',
      'Parameters carry source scope',
      'Execution environment recorded',
      'Claims traced to basis',
      '1 assumption disclosed'
    ]
  },

  /* ---- failure-case blocks ----------------------------------
     The failure workspace is not the success workspace with items
     removed. It assembles its own record: what was found, what was
     unmet, what was withheld, and what is being asked of the user. */
  'evidence-gap': {
    title: 'Evidence trail / 1 gap',
    kind: 'evidence',
    items: [
      { ref: 'DEMO-01', role: 'Kinetics method record', scope: 'Illustrative enzyme conditions' },
      { ref: 'NO MATCH', role: 'Km parameter basis', scope: 'No illustrative source in scope', status: 'blocked' }
    ]
  },
  'params-gap': {
    title: 'Parameters / 1 required value unmet',
    kind: 'params',
    items: [
      { name: 'Vmax', value: '1.00', unit: 'rel.', status: 'supported' },
      { name: 'Km', value: 'UNMET', unit: 'required', status: 'blocked' },
      { name: 'S range', value: '0 \u2013 0.36', unit: 'mM', status: 'user' },
      { name: 'Temperature', value: 'assumed', unit: '\u2014', status: 'review' }
    ]
  },
  flags: {
    title: 'Unsupported claim',
    kind: 'verify',
    items: [
      { check: 'Km has a relevant evidence basis', result: 'No basis', status: 'blocked' },
      { check: 'Model form has a basis', result: 'Supported', status: 'supported' }
    ]
  },
  'verify-not-run': {
    title: 'Verification',
    kind: 'verify',
    items: [
      { check: 'Monotonic increase', result: 'Not run', status: 'pending' },
      { check: 'Saturating plateau', result: 'Not run', status: 'pending' },
      { check: 'Half-maximal at Km', result: 'Not run', status: 'pending' }
    ]
  },
  blocking: {
    title: 'Blocking disclosure',
    kind: 'assumption',
    tone: 'blocked',
    text: 'The run does not proceed to a final result, because a required constant has no source basis in the illustrative evidence scope.'
  },
  clarification: {
    title: 'Returned to user',
    kind: 'record',
    tone: 'review',
    lines: [
      'No final result was produced',
      'Km requires a source or a user-supplied value',
      'Execution was withheld, not estimated',
      '1 unsupported claim flagged',
      '1 assumption disclosed'
    ]
  }
};

/** Illustrative curve shape for the console plot. */
export const CURVE = { vmax: 1, km: 0.03, sMax: 0.36, samples: 9, jitter: 0.03 };
