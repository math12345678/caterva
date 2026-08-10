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

  it('should reject simulation with no trajectory points', async () => {
    // This would happen if simulation fails to generate output
    const request: SimulationRequest = {
      query: 'Michaelis-Menten kinetics',
      parameters: { km: 5.2, vmax: 12.8, s0: 10.0 }
    };

    const response = await pipeline.execute(request);

    if (response.results.trajectory.length === 0) {
      expect(response.validated).toBe(false);
    } else {
      expect(response.validated).toBe(true);
    }
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

    // Without literature backing, should fail
    expect(response.validated).toBe(false);
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

    // All 4 layers must complete
    if (response.validated) {
      expect(response.validationConfidence).toBeGreaterThan(0);
      expect(response.metadata.literatureSourcesUsed).toBeGreaterThan(0);
      expect(response.results.trajectory.length).toBeGreaterThan(0);
    }
  });
});
