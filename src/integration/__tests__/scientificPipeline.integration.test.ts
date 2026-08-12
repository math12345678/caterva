/**
 * Integration Tests: Scientific Pipeline
 *
 * End-to-end workflow tests proving complete system works
 * Run: npm test -- scientificPipeline.integration.test.ts
 */

import ScientificPipeline from '../scientificPipeline';
import { LiteratureService } from '../../literature/literatureService';
import type { Literature } from '../../literature/literatureService';
// SimulationRequest is declared in scientificPipeline.ts; this file imported
// it from literatureService, which does not export it. The suite could never
// have compiled -- nothing type-checked this tree.
import type { SimulationRequest } from '../scientificPipeline';

// Sample literature for testing
const SAMPLE_LITERATURE: Literature[] = [
  {
    id: 'lit_001',
    doi: '10.1016/S0021-9258(20)71234-5',
    title: 'Kinetic properties of lactate dehydrogenase',
    authors: ['Smith J'],
    year: 2020,
    journal: 'Journal of Biological Chemistry',
    peerReviewed: true,
    impactFactor: 5.27,
    citationCount: 1847,
    abstract: 'High-quality study of LDH kinetics',
    domain: 'mm',
    extractedParameters: [
      {
        name: 'km',
        value: 5.2,
        unit: 'mM',
        conditions: { temperature: 37, pH: 7.4, substrate: 'lactate' }
      },
      {
        name: 'vmax',
        value: 12.8,
        unit: 'μM/min',
        conditions: { temperature: 37, pH: 7.4 }
      },
      {
        name: 's0',
        value: 10.0,
        unit: 'mM',
        conditions: { temperature: 37, pH: 7.4 }
      }
    ]
  },
  {
    id: 'lit_002',
    doi: '10.1016/S0006-3495(18)33456-7',
    title: 'Enzyme kinetics: steady-state analysis',
    authors: ['Johnson K'],
    year: 2018,
    journal: 'Biochemistry',
    peerReviewed: true,
    impactFactor: 4.15,
    citationCount: 523,
    abstract: 'Independent confirmation of LDH Km',
    domain: 'mm',
    extractedParameters: [
      {
        name: 'km',
        value: 5.1,
        unit: 'mM',
        conditions: { temperature: 37, pH: 7.4 }
      },
      {
        name: 'vmax',
        value: 12.5,
        unit: 'μM/min'
      }
    ]
  }
];

describe('ScientificPipeline Integration', () => {
  let pipeline: InstanceType<typeof ScientificPipeline>;

  beforeEach(() => {
    pipeline = new ScientificPipeline();
    pipeline.initializeLiterature(SAMPLE_LITERATURE);
  });

  // ========================================================================
  // SUCCESS CASES
  // ========================================================================

  it('should successfully execute simulation with valid parameters', async () => {
    const request: SimulationRequest = {
      query: 'Michaelis-Menten kinetics for lactate dehydrogenase',
      parameters: {
        km: 5.2,
        vmax: 12.8,
        s0: 10.0
      },
      conditions: {
        temperature: 37,
        pH: 7.4
      }
    };

    const response = await pipeline.execute(request);

    expect(response.validated).toBe(true);
    expect(response.validationConfidence).toBeGreaterThan(0.7);
    expect(response.results.trajectory).toHaveLength(101); // 0 to 10 seconds, 100 points
    expect(response.results.finalValue).toBeLessThan(10.0); // Some substrate consumed
    expect(response.metadata.literatureSourcesUsed).toBeGreaterThan(0);
  });

  it('should resolve missing parameters from literature', async () => {
    const request: SimulationRequest = {
      query: 'Michaelis-Menten for lactate dehydrogenase',
      parameters: {
        s0: 10.0 // Only substrate provided
      },
      conditions: {
        temperature: 37,
        pH: 7.4
      }
    };

    const response = await pipeline.execute(request);

    // Should resolve km and vmax from literature
    expect(response.validated).toBe(true);
    expect(response.results.trajectory.length).toBeGreaterThan(0);
  });

  it('should track reproducibility', async () => {
    const request: SimulationRequest = {
      query: 'Michaelis-Menten kinetics',
      parameters: { km: 5.2, vmax: 12.8, s0: 10.0 },
      conditions: { temperature: 37, pH: 7.4 }
    };

    const response1 = await pipeline.execute(request);
    expect(response1.reproducibilityKey).toBeDefined();
    expect(response1.dataIntegrityHash).toBeDefined();

    // Verify reproducibility
    const reproductionCheck = await pipeline.verifyReproducibility(response1.jobId);
    expect(reproductionCheck.reproduced).toBe(true);
    expect(reproductionCheck.maxError).toBeLessThan(1e-6);
  });

  it('should generate report for completed simulation', async () => {
    const request: SimulationRequest = {
      query: 'Michaelis-Menten kinetics',
      parameters: { km: 5.2, vmax: 12.8, s0: 10.0 },
      conditions: { temperature: 37, pH: 7.4 }
    };

    const response = await pipeline.execute(request);
    const report = pipeline.getReport(response.jobId);

    expect(report).toContain(response.jobId);
    expect(report).toContain('Simulation Report');
    expect(report).toContain('query');
  });

  it('should verify data integrity', async () => {
    const request: SimulationRequest = {
      query: 'Michaelis-Menten kinetics',
      parameters: { km: 5.2, vmax: 12.8, s0: 10.0 }
    };

    const response = await pipeline.execute(request);
    const integrityCheck = pipeline.checkIntegrity(response.jobId);

    expect(integrityCheck.intact).toBe(true);
    expect(integrityCheck.issues).toHaveLength(0);
  });

  // ========================================================================
  // FAILURE CASES (Should stop execution)
  // ========================================================================

  it('should FAIL when parameter completely out of range', async () => {
    const request: SimulationRequest = {
      query: 'Michaelis-Menten kinetics',
      parameters: {
        km: 500.0, // Way outside literature range [4.0, 6.0]
        vmax: 12.8,
        s0: 10.0
      }
    };

    const response = await pipeline.execute(request);

    expect(response.validated).toBe(false);
    expect(response.validationConfidence).toBe(0);
    expect(response.validationErrors.length).toBeGreaterThan(0);
  });

  it('never reports validated without a trajectory, or a trajectory without validation', async () => {
    /**
     * This was written as
     *
     *   if (trajectory.length === 0) expect(validated).toBe(false);
     *   else                         expect(validated).toBe(true);
     *
     * which has an answer ready for both outcomes and therefore states no
     * expectation about which should occur -- it could not fail. Worse, its
     * name promised the empty-trajectory case while its input (km 5.2, well
     * inside the literature range) guaranteed the opposite one, so the
     * branch it was named for never ran.
     *
     * The invariant underneath is real and worth stating: validation and a
     * trajectory travel together. A validated run with nothing to show is a
     * silent simulation failure; a trajectory from an unvalidated run is a
     * simulation that outran its own checks. Both inputs are exercised and
     * compared in one shot, so the test says which input produces which
     * outcome.
     */
    const cases: Array<[string, Record<string, number>]> = [
      ['in-range km', { km: 5.2, vmax: 12.8, s0: 10.0 }],
      ['km far outside the literature range', { km: 999.0, vmax: 12.8, s0: 10.0 }]
    ];

    const observed: Array<[string, boolean, boolean]> = [];
    for (const [label, parameters] of cases) {
      const response = await pipeline.execute({
        query: 'Michaelis-Menten kinetics',
        parameters
      });
      observed.push([
        label,
        response.validated,
        response.results.trajectory.length > 0
      ]);
    }

    // [label, validated, hasTrajectory]
    expect(observed).toEqual([
      ['in-range km', true, true],
      ['km far outside the literature range', false, false]
    ]);
  });

  // ========================================================================
  // EDGE CASES
  // ========================================================================

  it('should handle extreme but valid parameter values', async () => {
    const request: SimulationRequest = {
      query: 'Michaelis-Menten kinetics',
      parameters: {
        km: 5.2,  // Valid
        vmax: 12.8, // Valid
        s0: 0.1   // Very low substrate
      }
    };

    const response = await pipeline.execute(request);

    // Should still validate even with low substrate
    expect(response.validationConfidence).toBeGreaterThanOrEqual(0);
  });

  it('should handle missing optional conditions', async () => {
    const request: SimulationRequest = {
      query: 'Michaelis-Menten kinetics',
      parameters: { km: 5.2, vmax: 12.8, s0: 10.0 }
      // No conditions provided
    };

    const response = await pipeline.execute(request);

    // Should use defaults
    expect(response.validated).toBe(true);
  });

  it('should handle parameter from user taking precedence over literature', async () => {
    const request: SimulationRequest = {
      query: 'Michaelis-Menten kinetics',
      parameters: {
        km: 5.2, // User-provided
        // vmax will come from literature
        s0: 10.0
      }
    };

    const response = await pipeline.execute(request);

    expect(response.validated).toBe(true);
    // User parameter should be used
  });

  // ========================================================================
  // LITERATURE INTEGRATION
  // ========================================================================

  it('should cite literature sources in metadata', async () => {
    const request: SimulationRequest = {
      query: 'Michaelis-Menten kinetics',
      parameters: { s0: 10.0 } // Let pipeline resolve km and vmax
    };

    const response = await pipeline.execute(request);

    expect(response.metadata.literatureSourcesUsed).toBeGreaterThan(0);
  });

  it('should aggregate confidence from multiple literature sources', async () => {
    const request: SimulationRequest = {
      query: 'Michaelis-Menten kinetics',
      parameters: { s0: 10.0 }
    };

    const response = await pipeline.execute(request);

    // With 2 literature sources for km, confidence should be high
    expect(response.metadata.confidenceScore).toBeGreaterThan(0.7);
  });

  // ========================================================================
  // REPRODUCIBILITY
  // ========================================================================

  it('should reproduce identical results on re-execution', async () => {
    const request: SimulationRequest = {
      query: 'Michaelis-Menten kinetics',
      parameters: { km: 5.2, vmax: 12.8, s0: 10.0 },
      conditions: { temperature: 37, pH: 7.4 }
    };

    const response1 = await pipeline.execute(request);
    const response2 = await pipeline.execute(request);

    // Results should be numerically identical
    expect(response1.results.finalValue).toBeCloseTo(response2.results.finalValue, 5);
    expect(response1.results.trajectory.length).toBe(response2.results.trajectory.length);
  });

  it('should generate unique reproducibility keys', async () => {
    const request: SimulationRequest = {
      query: 'Michaelis-Menten kinetics',
      parameters: { km: 5.2, vmax: 12.8, s0: 10.0 }
    };

    const response1 = await pipeline.execute(request);
    const response2 = await pipeline.execute(request);

    // Different executions should have different reproduction keys
    expect(response1.reproducibilityKey).not.toBe(response2.reproducibilityKey);
  });

  // ========================================================================
  // CONFIDENCE SCORING
  // ========================================================================

  it('should achieve high confidence with multi-source parameters', async () => {
    const request: SimulationRequest = {
      query: 'Michaelis-Menten kinetics',
      parameters: {
        km: 5.2,   // In literature range and matches multiple sources
        vmax: 12.8,
        s0: 10.0
      }
    };

    const response = await pipeline.execute(request);

    expect(response.validationConfidence).toBeGreaterThan(0.85);
    expect(response.metadata.confidenceScore).toBeGreaterThan(0.85);
  });

  it('should reduce confidence for user-provided parameters without literature', async () => {
    const pipeline2 = new ScientificPipeline();
    // No literature loaded

    const request: SimulationRequest = {
      query: 'Michaelis-Menten kinetics',
      parameters: { km: 5.2, vmax: 12.8, s0: 10.0 }
    };

    const response = await pipeline2.execute(request);

    // A value the user typed directly is not treated as a fabrication --
    // ParameterValidator now WARNS (not errors) on an unsourced value with
    // origin 'user', so validation is not blocked outright. But nothing
    // backs it, so confidence must reflect exactly that: zero, not a
    // passing-but-unremarked score. See scientificValidator.ts's
    // USER_SUPPLIED_NO_LITERATURE comment for the reasoning.
    expect(response.validated).toBe(true);
    expect(response.validationConfidence).toBe(0);
  });
});

describe('ScientificPipeline Fail-Fast Behavior', () => {
  let pipeline: InstanceType<typeof ScientificPipeline>;

  beforeEach(() => {
    pipeline = new ScientificPipeline();
    pipeline.initializeLiterature(SAMPLE_LITERATURE);
  });

  it('should stop immediately on Layer 1 failure (no literature)', async () => {
    const request: SimulationRequest = {
      query: 'Unknown enzyme kinetics',
      parameters: { unknown_param: 999.0 }
    };

    const response = await pipeline.execute(request);

    // Should fail at layer 1
    expect(response.validated).toBe(false);
    expect(response.validationErrors.length).toBeGreaterThan(0);
    // Should not reach simulation
    expect(response.results.trajectory).toHaveLength(0);
  });

  it('should stop on parameter out of range', async () => {
    const request: SimulationRequest = {
      query: 'Michaelis-Menten kinetics',
      parameters: {
        km: 999.0, // Out of range
        vmax: 12.8,
        s0: 10.0
      }
    };

    const response = await pipeline.execute(request);

    expect(response.validated).toBe(false);
    expect(response.results.trajectory).toHaveLength(0); // No simulation
  });

  it('should NOT skip layers', async () => {
    const request: SimulationRequest = {
      query: 'Michaelis-Menten kinetics',
      parameters: { km: 5.2, vmax: 12.8, s0: 10.0 }
    };

    const response = await pipeline.execute(request);

    // All 4 layers must complete. Stated unconditionally: an
    // `if (response.validated)` guard here turned the test into "if the
    // pipeline worked, the pipeline worked" -- a Layer 1 regression that
    // rejected every request would have made it pass.
    // jest's expect() takes one argument -- it has no chai/node:assert-style
    // custom-message parameter -- so the diagnostic has to be surfaced
    // explicitly rather than passed to toBe().
    if (!response.validated) {
      throw new Error(
        `validation failed, so layers 2-4 never ran: ${JSON.stringify(response.validationErrors)}`
      );
    }
    expect(response.validated).toBe(true);
    expect(response.validationConfidence).toBeGreaterThan(0);
    expect(response.metadata.literatureSourcesUsed).toBeGreaterThan(0);
    expect(response.results.trajectory.length).toBeGreaterThan(0);
  });
});
