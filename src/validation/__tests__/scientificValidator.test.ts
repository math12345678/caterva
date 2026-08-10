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
  describe('verifyReference', () => {
    it('should verify valid DOI', async () => {
      const ref: LiteratureReference = {
        doi: '10.1016/S0021-9258(20)71234-5',
        title: 'Test',
        authors: ['Test'],
        year: 2020,
        journal: 'Journal',
        peerReviewed: true
      };

      const verified = await LiteratureVerifier.verifyReference(ref);
      expect(verified).toBe(true);
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
  const assumptions: ModelAssumptions = {
    steadyState: true,
    noSubstrateDepletion: true,
    noProductInhibition: true,
    enzymeNotDeactivating: true,
    singleEnzymeForm: true
  };

  it('should PASS when assumptions hold', () => {
    const result = AssumptionValidator.validateAssumptions(assumptions, {
      km: 5.0,
      vmax: 10.0,
      s0: 100.0,
      measurementTime: 10.0,
      temperature: 37,
      pH: 7.4
    });

    expect(result.valid).toBe(true);
    expect(result.violations).toHaveLength(0);
  });

  it('should FAIL when measurement time too short for steady-state', () => {
    const result = AssumptionValidator.validateAssumptions(assumptions, {
      km: 5.0,
      vmax: 10.0,
      s0: 100.0,
      measurementTime: 0.01, // Too short
      temperature: 37,
      pH: 7.4
    });

    expect(result.valid).toBe(false);
    expect(result.violations.some(v => v.includes('Steady-state'))).toBe(true);
  });

  it('should FAIL when substrate depleted > 5%', () => {
    const result = AssumptionValidator.validateAssumptions(assumptions, {
      km: 5.0,
      vmax: 100.0, // Very high
      s0: 1.0, // Very low
      measurementTime: 10.0,
      temperature: 37,
      pH: 7.4
    });

    expect(result.valid).toBe(false);
    expect(result.violations.some(v => v.includes('depletion'))).toBe(true);
  });

  it('should WARN for unusual temperature', () => {
    const result = AssumptionValidator.validateAssumptions(assumptions, {
      km: 5.0,
      vmax: 10.0,
      s0: 100.0,
      measurementTime: 10.0,
      temperature: 50, // Unusual
      pH: 7.4
    });

    expect(result.violations.some(v => v.includes('temperature'))).toBe(true);
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
