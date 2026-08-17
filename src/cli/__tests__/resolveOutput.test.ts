import { commandResolve } from '../commandResolve';
import { resolveKinetic } from '../../literature/literatureResolver';

jest.mock('../../literature/literatureResolver', () => ({
  ...jest.requireActual('../../literature/literatureResolver'),
  resolveKinetic: jest.fn(),
}));

/**
 * What the student actually sees.
 *
 * Four ADRs' worth of machinery — cross-species relatedness (0024), buffer
 * identity (0028), protein variants (0029), cofactors (0032) — computed a
 * finding, serialised it, and had it dropped by `literatureResolver.ts`,
 * whose result type had no field for it. Present, correct, unreachable.
 *
 * That is ADR 0027's defect one layer out, and it is invisible from both
 * sides: the producer sees a successful write, the consumer sees a complete
 * object. Nothing errors. The only way to notice is to look at the screen a
 * student looks at.
 *
 * So these tests assert on **rendered output**, not on the object. A field
 * plumbed through and never printed would satisfy a shape assertion and fail
 * the only thing that matters — and that is precisely the failure being
 * corrected here.
 */

const mockedResolve = resolveKinetic as jest.MockedFunction<typeof resolveKinetic>;

function captureStdout(): { output: () => string; restore: () => void } {
  const chunks: string[] = [];
  const original = process.stdout.write.bind(process.stdout);
  (process.stdout as unknown as { write: unknown }).write = (chunk: unknown) => {
    chunks.push(String(chunk));
    return true;
  };
  return {
    output: () => chunks.join(''),
    restore: () => {
      (process.stdout as unknown as { write: unknown }).write = original;
    },
  };
}

const BASE = {
  found: true as const,
  quantity: 'km' as const,
  value: 2.5,
  unit: 'mM',
  organism: 'Homo sapiens',
  source: 'brenda_exact',
  citation: { source: 'BRENDA', reference_id: '649716' },
  crossSpecies: false,
  logs: [],
};

const OPTIONS = {
  enzyme: 'lactate dehydrogenase',
  substrate: 'pyruvate',
  organism: 'Homo sapiens',
  quantity: 'km' as const,
  json: false,
};

async function render(extra: Record<string, unknown>): Promise<string> {
  mockedResolve.mockResolvedValueOnce({ ...BASE, ...extra } as never);
  const cap = captureStdout();
  try {
    await commandResolve(OPTIONS);
    return cap.output();
  } finally {
    cap.restore();
  }
}

describe('a value measured on a different protein says so (ADR 0029)', () => {
  it('names the mutation when the row is a point mutant', async () => {
    const out = await render({
      variant: {
        status: 'variant',
        kind: 'mutant',
        evidence: 'Y337A',
        reason: 'Substitutions are usually chosen because they change the kinetics.',
      },
    });
    expect(out).toContain('Y337A');
    expect(out).toMatch(/sequence variant/i);
  });

  it('distinguishes an isozyme from a mutant', async () => {
    // An isozyme is wild-type in its own right — a distinct gene product,
    // not a substitution. Calling it a mutant would be wrong, and calling
    // both "variant" without saying which is unhelpful.
    const out = await render({
      variant: {
        status: 'variant',
        kind: 'isozyme',
        evidence: 'isozyme H4',
        reason: 'A distinct gene product.',
      },
    });
    expect(out).toMatch(/named isozyme/i);
    expect(out).toContain('isozyme H4');
  });

  it('prints a line when the source did not say, which is the common case', async () => {
    // The load-bearing one. `unstated` is most of BRENDA and it is NOT
    // wild-type. Printing nothing would let a reader infer the enzyme as
    // found — absence of a warning read as a statement.
    const out = await render({
      variant: { status: 'unstated', reason: 'The commentary does not say.' },
    });
    expect(out).toMatch(/does not say whether/i);
    expect(out).toMatch(/not the same as it being wild-type/i);
  });

  it('confirms wild-type when the source states it', async () => {
    const out = await render({
      variant: {
        status: 'wild_type',
        evidence: 'wild-type enzyme',
        reason: 'Measured on the enzyme as found.',
      },
    });
    expect(out).toMatch(/enzyme as found/i);
  });

  it('mentions recombinant expression without calling it a variant', async () => {
    const out = await render({
      variant: {
        status: 'unstated',
        recombinant: true,
        reason: 'The commentary does not say.',
      },
    });
    expect(out).toMatch(/recombinant/i);
    expect(out).toMatch(/same sequence/i);
  });
});

describe('cofactors reach the reader (ADR 0032)', () => {
  it('prints what the assay contained', async () => {
    const out = await render({
      effectors: [
        {
          raw: 'in the presence of 0.2 mM NADH',
          compound_text: 'NADH',
          presence: 'present',
          concentration_text: '0.2 mM',
        },
      ],
    });
    expect(out).toContain('NADH');
    expect(out).toContain('0.2 mM');
  });

  it('prints an absence as loudly as a presence', async () => {
    // "in the absence of X" is a deliberate experimental statement, not a
    // gap in reporting. A Km measured without a required cofactor is a
    // different measurement, not a noisier one — so it must not be rendered
    // more quietly than a presence.
    const out = await render({
      effectors: [
        {
          raw: 'in the absence of fructose 1,6-bisphosphate',
          compound_text: 'fructose 1,6-bisphosphate',
          presence: 'absent',
        },
      ],
    });
    expect(out).toMatch(/without/i);
    expect(out).toContain('fructose 1,6-bisphosphate');
    expect(out).toMatch(/deliberately/i);
  });

  it('shows both sides of a present/absent pair together', async () => {
    const out = await render({
      effectors: [
        { raw: 'with Mg2+', compound_text: 'Mg2+', presence: 'present' },
        { raw: 'without EDTA', compound_text: 'EDTA', presence: 'absent' },
      ],
    });
    expect(out).toContain('Mg2+');
    expect(out).toContain('EDTA');
  });

  it('prints nothing when the source named no effectors', async () => {
    // An empty array means the commentary named none. Printing an empty
    // "Measured with" heading would imply a check found nothing when in
    // fact there was nothing to find.
    const out = await render({ effectors: [] });
    expect(out).not.toMatch(/Measured with/);
  });
});

describe('the buffer is shown as chemistry (ADR 0028)', () => {
  it('names the compound and its PubChem parent', async () => {
    const out = await render({
      assayConditions: {
        ph: 7.4,
        temperatureC: 25,
        buffer: '0.5 M Tris-HCl buffer',
        bufferIdentity: {
          raw: '0.5 M Tris-HCl buffer',
          species: 'Tris-HCl',
          cid: 93573,
          parent_cid: 6503,
          concentration_text: '0.5 M',
          status: 'resolved',
        },
      },
    });
    expect(out).toContain('Tris-HCl');
    expect(out).toContain('6503');
  });

  it('says concentration was not compared, so the limit is visible', async () => {
    const out = await render({
      assayConditions: {
        buffer: '0.5 M Tris-HCl buffer',
        bufferIdentity: {
          raw: '0.5 M Tris-HCl buffer',
          species: 'Tris-HCl',
          parent_cid: 6503,
          concentration_text: '0.5 M',
          status: 'resolved',
        },
      },
    });
    expect(out).toMatch(/not compared/i);
  });

  it('prints no compound line when the buffer could not be resolved', async () => {
    // The raw string is still shown in the conditions above. Printing a
    // resolved-looking line for an unresolved buffer would assert an
    // identity nobody established.
    //
    // The first version of this test asserted `not.toMatch(/PubChem \d/)`
    // and PASSED with the guard removed — because an unresolved identity
    // has no `parent_cid`, so the mutated code printed "PubChem undefined",
    // which the digit class does not match. The test was satisfied by the
    // worst possible output.
    //
    // So it asserts the section is absent, and separately that the word
    // `undefined` never reaches a reader.
    const out = await render({
      assayConditions: {
        buffer: 'house buffer B',
        bufferIdentity: {
          raw: 'house buffer B',
          status: 'unresolvable',
          reason: 'PubChem holds no compound named that.',
        },
      },
    });
    expect(out).not.toMatch(/PubChem/);
    expect(out).not.toContain('undefined');
  });
});

describe('the plumbing, asserted where it can be seen', () => {
  it('renders nothing extra when the resolver sends nothing extra', async () => {
    // A guard against the opposite failure: sections that appear
    // unconditionally, with empty or "undefined" content, are worse than
    // absent ones because they look like findings.
    const out = await render({});
    expect(out).not.toContain('undefined');
    expect(out).not.toMatch(/Measured with/);
    expect(out).not.toMatch(/sequence variant/i);
  });

  it('still prints the value itself', async () => {
    // The cheapest possible regression: a rendering change that throws
    // before the number reaches the screen.
    const out = await render({
      variant: { status: 'unstated', reason: 'x' },
      effectors: [{ raw: 'with NAD+', compound_text: 'NAD+', presence: 'present' }],
    });
    expect(out).toContain('2.5');
    expect(out).toContain('mM');
    expect(out).toContain('649716');
  });
});
