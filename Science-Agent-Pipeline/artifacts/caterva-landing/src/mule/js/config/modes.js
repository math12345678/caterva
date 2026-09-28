/* ============================================================
   caterva — SYSTEM MODE definitions

   Four modes, and the point of them is that they are not four
   labels. Each one changes what the whole page *does*: which
   sections are running, whether hovering reveals a path, whether
   the ambient motion is a slow pulse or an active sweep, and what
   the reader is being shown about the architecture.

   The behaviour lives in the controllers; what lives here is the
   contract — what each mode is for, what it says while it is on,
   and which stage is the one worth looking at while it runs.
   ============================================================ */

export const MODES = [
  {
    id: 'observe',
    index: '01',
    word: 'OBSERVE',
    glyph: '\u25CB',
    /* Shown in the dock under the mode list. */
    cue: 'Calm. Ambient signal only.',
    note: 'Best for reading and inspecting.',
    /* Read to a screen reader on switch. */
    say: 'Observe mode. The system is at rest. Nothing is running; ambient signal only. Best for reading and inspecting.',
    /* No stage is privileged: observe is the mode for reading whatever
       the reader happens to be looking at. */
    stage: null
  },
  {
    id: 'trace',
    index: '02',
    word: 'TRACE',
    glyph: '\u25B8',
    cue: 'Hover to follow a path.',
    note: 'Upstream sources, downstream consequences, related agents.',
    say: 'Trace mode. Hovering any module or agent reveals its upstream sources, its downstream consequences, and the agents related to it.',
    stage: '#atlas'
  },
  {
    id: 'run',
    index: '03',
    word: 'RUN',
    glyph: '\u25C6',
    cue: 'Sample pipeline executing.',
    note: 'The kinetics scenario, orchestrated across the system.',
    say: 'Run mode. The illustrative kinetics pipeline is executing across the system map and the orchestration console at once.',
    stage: '#orchestration'
  },
  {
    id: 'failure',
    index: '04',
    word: 'FAILURE',
    glyph: '\u25B2',
    cue: 'Boundaries and refusals.',
    /* Not the list of kinds — that is printed above this line in the dock,
       and saying it twice makes the dock look like it is padding. This says
       what the mode is claiming instead. */
    note: 'Every route shown here ends in a refusal rather than a result.',
    say: 'Failure mode. The system is showing its boundaries: question ambiguity, source gap, compute boundary, sanity-check problem, and disclosed assumption.',
    stage: '#orchestration'
  }
];

export const MODE = Object.fromEntries(MODES.map((m) => [m.id, m]));

export const DEFAULT_MODE = 'observe';

/* The five things failure mode is disclosing, listed in the dock so the
   reader knows what they are looking for before they go looking. */
export const FAILURE_KINDS = [
  'Question ambiguity',
  'Source gap',
  'Compute boundary',
  'Sanity-check problem',
  'Disclosed assumption'
];

export const DOCK = {
  label: 'SYSTEM MODE',
  hint: 'Changes how the whole page behaves.'
};
