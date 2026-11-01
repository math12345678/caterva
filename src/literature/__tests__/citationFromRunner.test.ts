/**
 * The runner's citation keeps its reference id across the boundary.
 *
 * science_agent_runner.py's `_citation_to_dict` writes `referenceId`; this
 * tree read `reference_id`, the spelling of the runner's docstring and of the
 * offline stub. Against the real runner the identifier was dropped, and
 * `simulate --resolve` printed "BRENDA ref ?" for every resolved value.
 *
 * The citation below is the one the real runner returned on 2026-09-30 for
 * human LDH (EC 1.1.1.27), the quinoline sulfonamide of BRENDA ref 739793,
 * asked for a noncompetitive Ki versus pyruvate: found 0.00252 mM.
 */
import { mapFoundResult } from '../literatureResolver';

const RUNNER_CITATION = {
  source: 'BRENDA',
  referenceId: '739793',
  url: 'https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27',
  title: null,
  organism: 'Homo sapiens',
  notes: null,
};

describe('the citation the runner writes', () => {
  it('carries referenceId on as reference_id', () => {
    const result = mapFoundResult(
      { source: 'brenda_exact', organism: 'Homo sapiens', citation: RUNNER_CITATION },
      'ki',
      0.00252,
      'mM',
      [],
    );
    expect(result.citation?.reference_id).toBe('739793');
    // Everything else the runner sent is kept as it was.
    expect(result.citation?.source).toBe('BRENDA');
    expect(result.citation?.url).toBe(RUNNER_CITATION.url);
  });

  it('still reads the snake_case spelling the offline stub writes', () => {
    const result = mapFoundResult(
      { source: 'brenda_exact', citation: { source: 'BRENDA', reference_id: '740253' } },
      'km',
      10.73,
      'mM',
      [],
    );
    expect(result.citation?.reference_id).toBe('740253');
  });

  it('is no citation when the runner sent none', () => {
    const result = mapFoundResult({ source: 'brenda_exact', citation: null }, 'km', 1, 'mM', []);
    expect(result.citation).toBeNull();
  });
});
