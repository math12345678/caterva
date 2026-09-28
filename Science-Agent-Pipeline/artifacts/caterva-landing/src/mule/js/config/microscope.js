/* ============================================================
   caterva — EVIDENCE MICROSCOPE data

   Six nested levels of one REAL parameter: the Km of human lactate
   dehydrogenase for pyruvate, as Caterva's resolver returns it. The
   reader starts at the number and descends until the number has
   stopped being a number and become a chain of custody.

   Every fact below is recorded in the repository, not written for the
   page: the BRENDA row is in Tests/fixtures/brenda_ldh_fixture.html
   (0.03 mM, pyruvate, Homo sapiens, no UniProt accession, no assay
   comment, ref 286469), and the disagreement with ref 286442 (0.398 mM,
   13.3-fold) is the resolver's own report (CHANGELOG, v0.3.4). No paper
   title, author or condition is stated that the record does not give.
   ============================================================ */

export const PARAM = {
  name: 'Km',
  value: '0.03',
  unit: 'mM',
  badge: 'BRENDA REF 286469'
};

export const DISCLAIMER =
  'A real value, shown with everything that qualifies it. Where the record is silent, the page says so.';

export const LEVELS = [
  {
    id: 'parameter',
    index: '01',
    key: 'PARAMETER',
    figure: 'value',
    title: 'A number on its own',
    lede: 'This is what most tools show you. It is the least useful thing about the parameter.',
    rows: [
      { k: 'Parameter', v: 'Km, pyruvate' },
      { k: 'Value', v: '0.03 mM' },
      { k: 'Enzyme', v: 'Lactate dehydrogenase, EC 1.1.1.27' }
    ],
    descend: 'Why this value?'
  },
  {
    id: 'decision',
    index: '02',
    key: 'ROLE IN THE MODEL',
    figure: 'equation',
    title: 'The role it plays',
    lede: 'Km is not a free number. It is the half-saturation constant of a specific model form, and it only means anything inside it.',
    rows: [
      { k: 'Role', v: 'Michaelis–Menten half-saturation constant' },
      { k: 'Model form', v: 'v = Vmax · S / (Km + S)' },
      { k: 'Not supplied by it', v: 'Vmax, which needs an enzyme concentration', tone: 'review' }
    ],
    descend: 'On what basis?'
  },
  {
    id: 'basis',
    index: '03',
    key: 'SOURCE',
    figure: 'source',
    title: 'Where it came from',
    lede: 'A value with no basis is a guess with good typography. This one is a measured row, and the row is cited.',
    rows: [
      { k: 'Database', v: 'BRENDA' },
      { k: 'Reference', v: '286469', mono: true },
      { k: 'Organism', v: 'Homo sapiens', tone: 'supported' },
      { k: 'Match', v: 'Exact: same organism, same substrate', tone: 'supported' }
    ],
    descend: 'Where does it hold?'
  },
  {
    id: 'scope',
    index: '04',
    key: 'SOURCE SCOPE',
    figure: 'scope',
    title: 'What the source does not say',
    lede: 'A value is true under the conditions it was measured in. This record states none, and a second human paper disagrees by 13-fold. Both facts travel with the number.',
    rows: [
      { k: 'Assay conditions', v: 'Not stated in the record', tone: 'review' },
      { k: 'Isoform', v: 'Not identified (no UniProt accession)', tone: 'review' },
      { k: 'Other human value', v: '0.398 mM, BRENDA ref 286442', tone: 'review' }
    ],
    descend: 'What was done about it?'
  },
  {
    id: 'verification',
    index: '05',
    key: 'WHAT CATERVA DID',
    figure: 'check',
    title: 'Named, not averaged',
    lede: 'Two papers disagree. Caterva does not split the difference or hide the second one: it carries the resolver’s pick, says it is a pick, and prints the spread beside it.',
    rows: [
      { k: 'Carried', v: '0.03 mM, the resolver’s pick, not a verdict' },
      { k: 'Reported', v: '2 sources, 2 values, 13.3-fold spread', tone: 'review' },
      { k: 'Conditions', v: 'Left unknown, never assumed', tone: 'review' }
    ],
    descend: 'What reaches the record?'
  },
  {
    id: 'record',
    index: '06',
    key: 'FINAL RECORD',
    figure: 'record',
    title: 'The parameter as it is delivered',
    lede: 'Nothing above was summarised away. The record carries the value and everything that qualifies it, on the same page.',
    record: [
      { k: 'PARAMETER', v: 'Km (pyruvate) / 0.03 mM' },
      { k: 'ENZYME', v: 'Lactate dehydrogenase, EC 1.1.1.27, Homo sapiens' },
      { k: 'SOURCE', v: 'BRENDA ref 286469 (exact organism match)' },
      { k: 'CONDITIONS', v: 'Not stated by the source', tone: 'review' },
      { k: 'DISAGREEMENT', v: '0.398 mM, BRENDA ref 286442: 13.3-fold', tone: 'review' },
      { k: 'STATUS', v: 'Cited, with its spread shown', tone: 'supported' }
    ],
    descend: null
  }
];

/** The equation drawn at level 02, split so Km can be marked in place. */
export const EQUATION = [
  { t: 'v', role: 'sym' },
  { t: '=', role: 'op' },
  { t: 'Vmax', role: 'sym' },
  { t: '·', role: 'op' },
  { t: 'S', role: 'sym' },
  { t: '/', role: 'op' },
  { t: '(', role: 'op' },
  { t: 'Km', role: 'focus' },
  { t: '+', role: 'op' },
  { t: 'S', role: 'sym' },
  { t: ')', role: 'op' }
];

/** Level 04's axis: the two human values the literature reports, in mM. */
export const SCOPE_BAND = { sMin: 0, sMax: 0.45, km: 0.03, other: 0.398, fold: '13.3' };
