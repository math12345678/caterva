/**
 * Unit Tests: Scientific Validator
 *
 * Tests all 4 validation layers with real failure cases
 * Run: npm test -- scientificValidator.test.ts
 */

import {
  ParameterValidator,
  LiteratureVerifier,
  AssumptionValidator,
  ResultValidator,
  ScientificValidationPipeline,
  type ParameterMetadata,
  type LiteratureReference,
  type ModelAssumptions,
  type SimulationOutput
} from '../scientificValidator';

describe('ParameterValidator', () => {
  describe('validateParameter', () => {
    it('should PASS for parameter with literature backing and valid range', () => {
      const param: ParameterMetadata = {
        name: 'km',
        value: 5.2,
        unit: 'mM',
        min: 4.0,
        max: 6.0,
        literature: [
          {
            doi: '10.1016/S0021-9258(20)71234-5',
            title: 'Lactate dehydrogenase kinetics',
            authors: ['Smith J'],
            year: 2020,
            journal: 'Journal of Biological Chemistry',
            peerReviewed: true,
            impactFactor: 5.27
          }
        ],
        confidence: 0.95
      };

      const result = ParameterValidator.validateParameter(param);

      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
      expect(result.confidence).toBeGreaterThan(0.85);
    });

    it('should FAIL when parameter has NO literature', () => {
      const param: ParameterMetadata = {
        name: 'km',
        value: 5.2,
        unit: 'mM',
        min: 4.0,
        max: 6.0,
        literature: [],
        confidence: 0.9
      };

      const result = ParameterValidator.validateParameter(param);

      expect(result.valid).toBe(false);
      expect(result.errors).toHaveLength(1);
      expect(result.errors[0].code).toBe('NO_LITERATURE');
      expect(result.errors[0].severity).toBe('critical');
    });

    it('should WARN, not fail, when a user-supplied parameter has no literature', () => {
      // A value with origin 'user' is not a fabrication -- it may be the
      // caller's own bench data. It must still be flagged, loudly, so it's
      // never mistaken for a literature-verified number, but it should not
      // block validation the way a value that CLAIMS to be resolved (and
      // isn't) does. See the USER_SUPPLIED_NO_LITERATURE comment in
      // scientificValidator.ts for the full reasoning.
      const param: ParameterMetadata = {
        name: 'km',
        value: 5.2,
        unit: 'mM',
        min: 4.0,
        max: 6.0,
        literature: [],
        confidence: 0,
        origin: 'user'
      };

      const result = ParameterValidator.validateParameter(param);

      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
      expect(result.warnings).toContainEqual(
        expect.objectContaining({
          code: 'USER_SUPPLIED_NO_LITERATURE',
          field: 'km',
          severity: 'medium'
        })
      );
    });

    it('should still FAIL when a non-user-origin parameter has no literature (e.g. a resolver claim with no citation)', () => {
      const param: ParameterMetadata = {
        name: 'km',
        value: 5.2,
        unit: 'mM',
        min: 4.0,
        max: 6.0,
        literature: [],
        confidence: 0,
        origin: 'literature (0 sources)'
      };

      const result = ParameterValidator.validateParameter(param);

      expect(result.valid).toBe(false);
      expect(result.errors).toHaveLength(1);
      expect(result.errors[0].code).toBe('NO_LITERATURE');
      expect(result.errors[0].severity).toBe('critical');
    });

    it('should FAIL when parameter OUT OF RANGE', () => {
      const param: ParameterMetadata = {
        name: 'km',
        value: 15.0, // Outside range
        unit: 'mM',
        min: 4.0,
        max: 6.0,
        literature: [
          {
            doi: '10.1016/test',
            title: 'Test',
            authors: ['Test'],
            year: 2020,
            journal: 'Journal',
            peerReviewed: true
          }
        ],
        confidence: 0.9
      };

      const result = ParameterValidator.validateParameter(param);

      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.code === 'OUT_OF_RANGE')).toBe(true);
    });

    it('should WARN for non-peer-reviewed literature', () => {
      const param: ParameterMetadata = {
        name: 'km',
        value: 5.2,
        unit: 'mM',
        min: 4.0,
        max: 6.0,
        literature: [
          {
            doi: '10.1016/test',
            title: 'Test',
            authors: ['Test'],
            year: 2020,
            journal: 'Journal',
            peerReviewed: false // Not peer-reviewed
          }
        ],
        confidence: 0.9
      };

      const result = ParameterValidator.validateParameter(param);

      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.code === 'NON_PEER_REVIEWED')).toBe(true);
    });

    it('should WARN for low confidence', () => {
      const param: ParameterMetadata = {
        name: 'km',
        value: 5.2,
        unit: 'mM',
        min: 4.0,
        max: 6.0,
        literature: [
          {
            doi: '10.1016/test',
            title: 'Test',
            authors: ['Test'],
            year: 2020,
            journal: 'Journal',
            peerReviewed: true
          }
        ],
        confidence: 0.5 // Low confidence
      };

      const result = ParameterValidator.validateParameter(param);

      expect(result.warnings.some(w => w.code === 'LOW_CONFIDENCE')).toBe(true);
    });
  });
});

describe('LiteratureVerifier', () => {
  // `registryCache` is static module state, so without this reset one
  // test's registry answers leak into the next -- and into other test
  // FILES when jest shares a worker (`--runInBand` made an
  // order-dependent failure appear that the default parallel run hid).
  // Tests whose outcome depends on execution order are not evidence.
  beforeEach(() => {
    LiteratureVerifier.resetRegistryCache();
  });

  describe('verifyReference', () => {
    it('should verify valid DOI', async () => {
      const doi = '10.1016/S0021-9258(20)71234-5';
      const ref: LiteratureReference = {
        doi,
        title: 'Test',
        authors: ['Test'],
        year: 2020,
        journal: 'Journal',
        peerReviewed: true
      };

      // Seed the registry answer.
      //
      // This test used to pass with no seeding, because `verifyDOI` began
      // with `if (NODE_ENV === 'test') return true` -- so it returned true
      // for ANY well-formed DOI whenever the suite ran, including
      // fabricated ones. The test was therefore asserting the behaviour of
      // a bypass rather than of the verifier, and would have passed just
      // as happily against 10.9999/completely-made-up.
      //
      // Seeding states the premise out loud: GIVEN CrossRef says this DOI
      // resolves, a peer-reviewed reference carrying it verifies.
      LiteratureVerifier.primeRegistryCache(`doi:${doi}`, true);

      const verified = await LiteratureVerifier.verifyReference(ref);
      expect(verified).toBe(true);
    });

    it('does not verify a well-formed DOI the registry has not confirmed', async () => {
      // The other half, and the reason the bypass mattered: without a
      // registry answer there is no verification, however well-formed the
      // identifier looks.
      const verified = await LiteratureVerifier.verifyReference({
        doi: '10.9999/completely-made-up',
        title: 'Fabricated',
        authors: ['Nobody'],
        year: 2020,
        journal: 'Journal',
        peerReviewed: true
      });
      expect(verified).toBe(false);
    });

    it('should reject invalid DOI format', async () => {
      const ref: LiteratureReference = {
        doi: 'invalid-doi',
        title: 'Test',
        authors: ['Test'],
        year: 2020,
        journal: 'Journal',
        peerReviewed: true
      };

      const verified = await LiteratureVerifier.verifyReference(ref);
      expect(verified).toBe(false);
    });

    it('does not let a cached DOI lookup bypass the peer-review check', async () => {
      // Order-independent regression for a cache that stored the whole
      // verdict under `ref.doi`. `peerReviewed` is a property of the
      // REFERENCE, not of the DOI, so caching by identifier meant the
      // second reference below inherited the first one's `true` and never
      // reached check 3 at all.
      //
      // The pre-existing 'should reject non-peer-reviewed sources' test did
      // detect this, but only because an earlier test in the same file
      // happened to use the same DOI first -- reordering the file would
      // have hidden it again. This states the invariant directly.
      const doi = '10.1073/pnas.88.16.7328';
      // Seed the DOI as resolving, so check 1 passes without a network and
      // the peer-review check is what actually decides the outcome.
      // Without this the test is vacuous offline -- an unreachable CrossRef
      // makes both calls false regardless of the bug.
      LiteratureVerifier.resetRegistryCache();
      LiteratureVerifier.primeRegistryCache(`doi:${doi}`, true);

      const base = {
        doi,
        title: 'Same DOI, two references',
        authors: ['Test'],
        year: 2020,
        journal: 'Journal'
      };

      const peerReviewed = await LiteratureVerifier.verifyReference({
        ...base,
        peerReviewed: true
      });
      const notPeerReviewed = await LiteratureVerifier.verifyReference({
        ...base,
        peerReviewed: false
      });

      // Whatever the registry says about the DOI, the two must not agree:
      // the only difference between them is the peer-review flag, and that
      // flag must be decisive. (If the DOI does not resolve -- e.g. no
      // network -- both are false, which is also not a bypass.)
      // Unconditional: the DOI is primed as resolving, so the ONLY
      // difference between these two references is the peer-review flag,
      // and it must be decisive.
      expect(peerReviewed).toBe(true);
      expect(notPeerReviewed).toBe(false);
    });

    it('should reject non-peer-reviewed sources', async () => {
      const ref: LiteratureReference = {
        doi: '10.1016/S0021-9258(20)71234-5',
        title: 'Test',
        authors: ['Test'],
        year: 2020,
        journal: 'Journal',
        peerReviewed: false
      };

      const verified = await LiteratureVerifier.verifyReference(ref);
      expect(verified).toBe(false);
    });
  });

  describe('findConflicts', () => {
    it('should detect outliers in values', () => {
      const refs: LiteratureReference[] = [
        {
          doi: '10.1016/1',
          title: 'Paper 1',
          authors: ['A'],
          year: 2020,
          journal: 'J',
          peerReviewed: true
        },
        {
          doi: '10.1016/2',
          title: 'Paper 2',
          authors: ['B'],
          year: 2020,
          journal: 'J',
          peerReviewed: true
        },
        {
          doi: '10.1016/3',
          title: 'Paper 3',
          authors: ['C'],
          year: 2020,
          journal: 'J',
          peerReviewed: true
        }
      ];

      const values = [5.0, 5.2, 50.0]; // 50.0 is outlier

      const conflicts = LiteratureVerifier.findConflicts(refs, values);
      expect(conflicts).toHaveLength(1);
      expect(conflicts[0]).toContain('Outlier detected');
    });
  });
});

describe('AssumptionValidator', () => {
  // These tests were rewritten when AssumptionValidator was grounded in
  // Segel LA (1988), Bull Math Biol 50(6):579-93, DOI 10.1007/BF02460092.
  // The previous versions asserted the OLD contract, which was wrong in
  // three ways worth naming, since "the tests passed" was the reason the
  // errors survived:
  //
  //   * "should PASS when assumptions hold" used km=5, vmax=10, s0=100,
  //     t=10 -- at which Vmax*t = 100 = s0, i.e. the substrate is entirely
  //     consumed. Those numbers are physically inconsistent with the
  //     assumption they were asserted to satisfy.
  //   * The steady-state check compared the measurement window against
  //     (km/vmax)*5, a form of Segel's SLOW (substrate-consumption)
  //     timescale, not the fast transient the assumption is about.
  //   * The 5% depletion cutoff was asserted as a hard violation. It is a
  //     textbook convention for initial-rate work with no primary source
  //     behind the number, so it now warns; exhaustion still fails.
  const assumptions: ModelAssumptions = {
    steadyState: true,
    noSubstrateDepletion: true,
    noProductInhibition: true,
    enzymeNotDeactivating: true,
    singleEnzymeForm: true
  };

  /** e0 << Km + s0, and a window short enough not to consume the substrate. */
  const validConditions = {
    km: 5.0,
    vmax: 10.0,
    s0: 100.0,
    e0: 0.01,
    measurementTime: 0.1,
    temperature: 37,
    pH: 7.4
  };

  it('PASSES when the QSSA criterion holds and substrate is not consumed', () => {
    const result = AssumptionValidator.validateAssumptions(
      assumptions,
      validConditions
    );

    expect(result.violations).toEqual([]);
    expect(result.valid).toBe(true);
    expect(result.notEvaluated).toEqual([]);
  });

  it('reports steadyState as NOT EVALUATED when e0 is absent', () => {
    // epsilon = e0/(Km + s0) cannot be computed without e0. The old code
    // silently passed in this case, which reported an unevaluated
    // assumption as satisfied -- the exact failure mode this file exists
    // to prevent.
    const { e0, ...withoutE0 } = validConditions;
    void e0;

    const result = AssumptionValidator.validateAssumptions(
      assumptions,
      withoutE0
    );

    expect(result.notEvaluated).toHaveLength(1);
    expect(result.notEvaluated[0]).toContain('UNVERIFIED');
    expect(result.notEvaluated[0]).toContain('10.1007/BF02460092');
    // Not silently converted into a failure either.
    expect(result.violations.some(v => v.includes('Steady-state'))).toBe(false);
  });

  it('FAILS when epsilon = e0/(Km + s0) is not << 1', () => {
    const result = AssumptionValidator.validateAssumptions(assumptions, {
      ...validConditions,
      e0: 200.0 // epsilon = 200/105 = 1.9
    });

    expect(result.valid).toBe(false);
    expect(result.violations.some(v => v.includes('epsilon'))).toBe(true);
    // Points at the applicable alternative reduction rather than just
    // rejecting: Borghans, de Boer & Segel (1996), tQSSA.
    expect(result.violations.join(' ')).toContain('10.1007/BF02458281');
  });

  it('WARNS but does not fail when epsilon is marginal', () => {
    const result = AssumptionValidator.validateAssumptions(assumptions, {
      ...validConditions,
      e0: 21.0 // epsilon = 21/105 = 0.2 -> ~20% error, valid but marginal
    });

    expect(result.valid).toBe(true);
    expect(result.warnings.some(w => w.includes('marginal'))).toBe(true);
  });

  it('FAILS when the substrate is exhausted within the window', () => {
    // vmax*t = 100*10 = 1000, s0 = 1 -> 100000% of s0. No initial-rate
    // reading survives this, so it is a violation rather than a warning.
    const result = AssumptionValidator.validateAssumptions(assumptions, {
      ...validConditions,
      vmax: 100.0,
      s0: 1.0,
      measurementTime: 10.0
    });

    expect(result.valid).toBe(false);
    expect(result.violations.some(v => v.includes('exhausted'))).toBe(true);
  });

  it('WARNS, without failing, on depletion above the 5% convention', () => {
    // vmax*t/s0 = 10*0.2/100 = 2%... nudge to ~20%.
    const result = AssumptionValidator.validateAssumptions(assumptions, {
      ...validConditions,
      measurementTime: 2.0 // 10*2/100 = 20%
    });

    expect(result.valid).toBe(true);
    expect(result.warnings.some(w => w.includes('depletion'))).toBe(true);
    expect(result.violations).toEqual([]);
  });

  it('applies NO unit conversion to vmax', () => {
    // A previous revision divided vmax by 1000 ("convert uM/min to mM/min")
    // to make a failing test pass, silently rescaling every depletion
    // result by three orders of magnitude on the strength of units that
    // nothing declares or enforces. s0 = vmax*time must read as exactly
    // 100% consumed.
    const result = AssumptionValidator.validateAssumptions(assumptions, {
      ...validConditions,
      vmax: 10.0,
      s0: 100.0,
      measurementTime: 10.0 // 10*10 = 100 = s0 exactly
    });

    expect(result.violations.some(v => v.includes('100.0%'))).toBe(true);
  });

  it('WARNS rather than fails outside the mesophilic temperature range', () => {
    // Taq polymerase is assayed near 72 C. Failing a run for that would
    // reject correct science, so 4-45 C warns instead of blocking.
    const result = AssumptionValidator.validateAssumptions(assumptions, {
      ...validConditions,
      temperature: 72
    });

    expect(result.warnings.some(w => w.includes('temperature') || w.includes('C is outside'))).toBe(true);
    expect(result.violations.some(v => v.toLowerCase().includes('temperature'))).toBe(false);
  });

  it('WARNS rather than fails outside the pH 5-9 range', () => {
    // Pepsin's optimum is near pH 2.
    const result = AssumptionValidator.validateAssumptions(assumptions, {
      ...validConditions,
      pH: 2.0
    });

    expect(result.warnings.some(w => w.includes('pH'))).toBe(true);
    expect(result.violations.some(v => v.includes('pH'))).toBe(false);
  });
});

describe('ResultValidator', () => {
  it('should PASS for valid output', () => {
    const output: SimulationOutput = {
      trajectory: [
        { time: 0, value: 100 },
        { time: 1, value: 95 },
        { time: 2, value: 90 },
        { time: 3, value: 85 },
        { time: 4, value: 80 }
      ],
      finalValue: 80
    };

    const result = ResultValidator.validateOutput(output);

    expect(result.valid).toBe(true);
    expect(result.issues).toHaveLength(0);
    expect(result.dataQuality).toBeGreaterThan(0.9);
  });

  it('should FAIL for NaN values', () => {
    const output: SimulationOutput = {
      trajectory: [
        { time: 0, value: 100 },
        { time: 1, value: NaN }
      ],
      finalValue: NaN
    };

    const result = ResultValidator.validateOutput(output);

    expect(result.valid).toBe(false);
    expect(result.issues.some(i => i.includes('NaN'))).toBe(true);
  });

  it('should FAIL for non-monotonic trajectory', () => {
    const output: SimulationOutput = {
      trajectory: [
        { time: 0, value: 100 },
        { time: 1, value: 95 },
        { time: 2, value: 105 }, // Increases - not monotonic
        { time: 3, value: 85 }
      ],
      finalValue: 85
    };

    const result = ResultValidator.validateOutput(output);

    expect(result.valid).toBe(false);
    expect(result.issues.some(i => i.includes('monotonic'))).toBe(true);
  });

  it('should compare to literature values', () => {
    const output: SimulationOutput = {
      trajectory: [{ time: 0, value: 100 }],
      finalValue: 5.2
    };

    const comparison = ResultValidator.compareToLiterature(output, 5.3, 10);

    expect(comparison.withinTolerance).toBe(true);
    expect(comparison.error).toBeLessThan(10);
  });

  it('should detect when outside literature range', () => {
    const output: SimulationOutput = {
      trajectory: [{ time: 0, value: 100 }],
      finalValue: 20.0
    };

    const comparison = ResultValidator.compareToLiterature(output, 5.0, 10);

    expect(comparison.withinTolerance).toBe(false);
    expect(comparison.error).toBeGreaterThan(10);
  });
});

describe('ScientificValidationPipeline', () => {
  it('should complete all 4 layers for valid simulation', async () => {
    const params: ParameterMetadata[] = [
      {
        name: 'km',
        value: 5.2,
        unit: 'mM',
        min: 4.0,
        max: 6.0,
        literature: [
          {
            doi: '10.1016/test',
            title: 'Test',
            authors: ['A'],
            year: 2020,
            journal: 'J',
            peerReviewed: true
          }
        ],
        confidence: 0.9
      }
    ];

    const assumptions: ModelAssumptions = {
      steadyState: true,
      noSubstrateDepletion: true,
      noProductInhibition: true,
      enzymeNotDeactivating: true,
      singleEnzymeForm: true
    };

    const conditions = { km: 5.2, vmax: 10, s0: 100, measurementTime: 10, temperature: 37, pH: 7.4 };

    const output: SimulationOutput = {
      trajectory: [
        { time: 0, value: 100 },
        { time: 1, value: 95 },
        { time: 2, value: 90 }
      ],
      finalValue: 90
    };

    const result = await ScientificValidationPipeline.validate(
      params,
      assumptions,
      conditions,
      output
    );

    expect(result.passed).toBe(true);
    expect(result.confidence).toBeGreaterThan(0.7);
    expect(result.errors).toHaveLength(0);
  });

  it('should FAIL at Layer 1 for parameter without literature', async () => {
    const params: ParameterMetadata[] = [
      {
        name: 'km',
        value: 5.2,
        unit: 'mM',
        min: 4.0,
        max: 6.0,
        literature: [], // No literature
        confidence: 0.9
      }
    ];

    const assumptions: ModelAssumptions = {
      steadyState: true,
      noSubstrateDepletion: true,
      noProductInhibition: true,
      enzymeNotDeactivating: true,
      singleEnzymeForm: true
    };

    const result = await ScientificValidationPipeline.validate(
      params,
      assumptions,
      { km: 5.2, vmax: 10, s0: 100, measurementTime: 10, temperature: 37, pH: 7.4 }
    );

    expect(result.passed).toBe(false);
    expect(result.errors).toHaveLength(1);
  });

  it('should FAIL at Layer 4 for invalid output', async () => {
    const params: ParameterMetadata[] = [
      {
        name: 'km',
        value: 5.2,
        unit: 'mM',
        min: 4.0,
        max: 6.0,
        literature: [
          {
            doi: '10.1016/test',
            title: 'Test',
            authors: ['A'],
            year: 2020,
            journal: 'J',
            peerReviewed: true
          }
        ],
        confidence: 0.9
      }
    ];

    const output: SimulationOutput = {
      trajectory: [{ time: 0, value: NaN }], // Invalid output
      finalValue: NaN
    };

    const result = await ScientificValidationPipeline.validate(
      params,
      { steadyState: true, noSubstrateDepletion: true, noProductInhibition: true, enzymeNotDeactivating: true, singleEnzymeForm: true },
      { km: 5.2, vmax: 10, s0: 100, measurementTime: 10, temperature: 37, pH: 7.4 },
      output
    );

    expect(result.passed).toBe(false);
  });
});
