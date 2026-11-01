/* ============================================================
   caterva — EVIDENCE MICROSCOPE data

   Six nested levels of one illustrative parameter. The reader
   starts at the number and descends until the number has stopped
   being a number and become a chain of custody.

   Each level declares its own `figure`, because the point of the
   microscope is that these are six different kinds of fact — a
   value, a decision, a source, a boundary, a check, a record —
   and six identical text panels would say they are the same kind.

   Everything here is illustrative. There is no real citation,
   DOI, PMID, journal, author or measurement.
   ============================================================ */

export const PARAM = {
  name: 'Km',
  value: '0.42',
  unit: 'mM',
  badge: 'ILLUSTRATIVE EXAMPLE'
};

export const DISCLAIMER =
  'This is an interface demonstration. It is not a research-ready parameter recommendation.';

/* ------------------------------------------------------------
   THE SIX LEVELS
   `key` is the level word the reader navigates by. `figure` selects
   the drawing. `rows` are the inspectable facts at that depth.
   ------------------------------------------------------------ */
export const LEVELS = [
  {
    id: 'parameter',
    index: '01',
    key: 'PARAMETER',
    figure: 'value',
    title: 'A number on its own',
    lede: 'This is what most tools show you. It is the least useful thing about the parameter.',
    rows: [
      { k: 'Parameter', v: 'Km' },
      { k: 'Value', v: '0.42 mM' },
      { k: 'Status', v: 'Illustrative example', tone: 'review' }
    ],
    descend: 'Why this value?'
  },
  {
    id: 'decision',
    index: '02',
    key: 'CONFIGURATION DECISION',
    figure: 'equation',
    title: 'The role it plays',
    lede: 'Km is not a free number. It is the half-saturation constant of a specific model form, and it only means anything inside it.',
    rows: [
      { k: 'Role', v: 'Illustrative Michaelis\u2013Menten configuration value' },
      { k: 'Applied by', v: 'Configuration agent' },
      { k: 'Model form', v: 'v = Vmax \u00B7 S / (Km + S)' }
    ],
    descend: 'On what basis?'
  },
  {
    id: 'basis',
    index: '03',
    key: 'ILLUSTRATIVE SOURCE BASIS',
    figure: 'source',
    title: 'Where it came from',
    lede: 'A value with no basis is a guess with good typography. This one is bound to the demonstration record that supplied it.',
    rows: [
      { k: 'Source basis', v: 'Demo source / kinetics method record' },
      { k: 'Reference', v: 'DEMO-02', mono: true },
      { k: 'Binding', v: 'Attached to the parameter, not to the run' }
    ],
    descend: 'Where does it hold?'
  },
  {
    id: 'scope',
    index: '04',
    key: 'SOURCE SCOPE',
    figure: 'scope',
    title: 'The conditions it is true under',
    lede: 'Every source declares a boundary. Outside that boundary the value is not wrong \u2014 it is simply unsupported, which is a different and more dangerous thing.',
    rows: [
      { k: 'Scope', v: 'Illustrative enzyme conditions / example temperature context' },
      { k: 'Inside scope', v: 'Substrate range 0 \u2013 5.0 mM', tone: 'supported' },
      { k: 'Outside scope', v: 'Temperature condition not established', tone: 'review' }
    ],
    descend: 'Who checked it?'
  },
  {
    id: 'verification',
    index: '05',
    key: 'VERIFICATION ACTION',
    figure: 'check',
    title: 'What was done about it',
    lede: 'The scope gap was not resolved by assumption. It was routed to a check, and the check reported what it found.',
    rows: [
      { k: 'Checked by', v: 'Hallucination Check' },
      { k: 'Claim', v: 'Km has a relevant evidence basis' },
      { k: 'Result', v: 'Supported within stated scope', tone: 'supported' },
      { k: 'Critique result', v: 'No unsupported claim shown, parameter remains explicitly illustrative', tone: 'review' }
    ],
    descend: 'What reaches the record?'
  },
  {
    id: 'record',
    index: '06',
    key: 'FINAL NOTEBOOK RECORD',
    figure: 'record',
    title: 'The parameter as it is delivered',
    lede: 'Nothing above was summarised away. The record carries the value and everything that qualifies it, on the same page.',
    /* The complete record, exactly the field set the brief specifies. */
    record: [
      { k: 'PARAMETER', v: 'Km / 0.42 mM' },
      { k: 'ROLE', v: 'Illustrative Michaelis\u2013Menten configuration value' },
      { k: 'SOURCE BASIS', v: 'Demo source / kinetics method record' },
      { k: 'SCOPE', v: 'Illustrative enzyme conditions / example temperature context' },
      { k: 'APPLIED BY', v: 'Configuration agent' },
      { k: 'CHECKED BY', v: 'Hallucination Check' },
      { k: 'CRITIQUE RESULT', v: 'No unsupported claim shown, parameter remains explicitly illustrative', tone: 'review' },
      { k: 'FINAL OUTPUT STATUS', v: 'Included in illustrated scientific record', tone: 'supported' }
    ],
    descend: null
  }
];

/** The equation drawn at level 02, split so Km can be marked in place. */
export const EQUATION = [
  { t: 'v', role: 'sym' },
  { t: '=', role: 'op' },
  { t: 'Vmax', role: 'sym' },
  { t: '\u00B7', role: 'op' },
  { t: 'S', role: 'sym' },
  { t: '/', role: 'op' },
  { t: '(', role: 'op' },
  { t: 'Km', role: 'focus' },
  { t: '+', role: 'op' },
  { t: 'S', role: 'sym' },
  { t: ')', role: 'op' }
];

/** Scope band geometry for level 04, in the figure's own units. */
export const SCOPE_BAND = { sMin: 0, sMax: 5, km: 0.42, supported: [0, 5] };
