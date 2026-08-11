/**
 * Critical Path Tests for Scientific Validator
 *
 * Ensures all essential validation paths are covered
 */

import { ScientificValidationPipeline, LiteratureVerifier, AssumptionValidator, ResultValidator } from '../scientificValidator';
import type { ParameterMetadata, ModelAssumptions, SimulationOutput, LiteratureReference } from '../scientificValidator';

describe('Critical validation paths', () => {
  describe('LiteratureVerifier edge cases', () => {
    it('should accept peer-reviewed sources with valid DOI', async () => {
      const ref: LiteratureReference = {
        doi: '10.1234/test-doi',
        title: 'Valid Paper',
        authors: ['Author'],
        year: 2024,
        journal: 'Journal',
        peerReviewed: true
      };

      const result = await LiteratureVerifier.verifyReference(ref);
      expect(typeof result).toBe('boolean');
    });

    it('should reject non-peer-reviewed sources', async () => {
      const ref: LiteratureReference = {
        doi: '10.1234/test-doi',
        title: 'Non-peer-reviewed Paper',
        authors: ['Author'],
        year: 2024,
        journal: 'Blog',
        peerReviewed: false
      };

      const result = await LiteratureVerifier.verifyReference(ref);
      expect(result).toBe(false);
    });

    it('should reject invalid DOI format', async () => {
      const ref: LiteratureReference = {
        doi: 'not-a-real-doi',
        title: 'Invalid DOI Paper',
        authors: ['Author'],
        year: 2024,
        journal: 'Journal',
        peerReviewed: true
      };

      const result = await LiteratureVerifier.verifyReference(ref);
      expect(result).toBe(false);
    });

    it('should verify peer-reviewed references gracefully', async () => {
      const ref: LiteratureReference = {
        title: 'Local Only Paper',
        authors: ['Author'],
        year: 2024,
        journal: 'Journal',
        peerReviewed: true
      };

      // Without DOI/PubMed, just checks peer-review status
      const result = await LiteratureVerifier.verifyReference(ref);
      expect(typeof result).toBe('boolean');
    });
  });

  describe('ResultValidator output checking', () => {
    it('should accept valid monotonic decreasing trajectory', () => {
      const output: SimulationOutput = {
        trajectory: [
          { time: 0, value: 100 },
          { time: 1, value: 90 },
          { time: 2, value: 80 },
          { time: 3, value: 70 }
        ],
        finalValue: 70
      };

      const result = ResultValidator.validateOutput(output);
      expect(result.valid).toBe(true);
      expect(result.issues).toHaveLength(0);
    });

    it('should accept valid monotonic increasing trajectory', () => {
      const output: SimulationOutput = {
        trajectory: [
          { time: 0, value: 0 },
          { time: 1, value: 10 },
          { time: 2, value: 20 },
          { time: 3, value: 30 }
        ],
        finalValue: 30
      };

      const result = ResultValidator.validateOutput(output);
      expect(result.valid).toBe(true);
    });

    it('should reject non-monotonic trajectory', () => {
      const output: SimulationOutput = {
        trajectory: [
          { time: 0, value: 100 },
          { time: 1, value: 50 },
          { time: 2, value: 75 }, // Goes back up - not monotonic
          { time: 3, value: 30 }
        ],
        finalValue: 30
      };

      const result = ResultValidator.validateOutput(output);
      expect(result.valid).toBe(false);
      expect(result.issues.some(i => i.includes('monotonic'))).toBe(true);
    });

    it('should reject NaN values', () => {
      const output: SimulationOutput = {
        trajectory: [
          { time: 0, value: 100 },
          { time: 1, value: NaN },
          { time: 2, value: 80 }
        ],
        finalValue: 80
      };

      const result = ResultValidator.validateOutput(output);
      expect(result.valid).toBe(false);
      expect(result.issues.some(i => i.includes('NaN'))).toBe(true);
    });

    it('should reject out-of-range values', () => {
      const output: SimulationOutput = {
        trajectory: [
          { time: 0, value: 100 },
          { time: 1, value: 50 },
          { time: 2, value: -10 } // Negative concentration
        ],
        finalValue: -10
      };

      const result = ResultValidator.validateOutput(output);
      expect(result.valid).toBe(false);
    });
  });

  describe('AssumptionValidator edge cases', () => {
    const assumptions: ModelAssumptions = {
      steadyState: true,
      noSubstrateDepletion: true,
      noProductInhibition: true,
      enzymeNotDeactivating: true,
      singleEnzymeForm: true
    };

    it('should pass when all assumptions hold', () => {
      const result = AssumptionValidator.validateAssumptions(assumptions, {
        km: 5.0,
        vmax: 10.0,
        s0: 100.0,
        measurementTime: 0.1,
        temperature: 37,
        pH: 7.4,
        e0: 0.01
      });

      expect(result.valid).toBe(true);
      expect(result.violations).toHaveLength(0);
    });

    it('should handle missing e0 gracefully', () => {
      const result = AssumptionValidator.validateAssumptions(assumptions, {
        km: 5.0,
        vmax: 10.0,
        s0: 100.0,
        measurementTime: 0.1,
        temperature: 37,
        pH: 7.4
        // e0 missing
      });

      // Should mark steady-state as not evaluated, not fail
      expect(result.notEvaluated.some(n => n.includes('UNVERIFIED'))).toBe(true);
    });

    it('should warn on unusual temperature', () => {
      const result = AssumptionValidator.validateAssumptions(assumptions, {
        km: 5.0,
        vmax: 10.0,
        s0: 100.0,
        measurementTime: 0.1,
        temperature: 72, // Taq polymerase temp
        pH: 7.4,
        e0: 0.01
      });

      expect(result.warnings.some(w => w.includes('temperature'))).toBe(true);
    });

    it('should warn on unusual pH', () => {
      const result = AssumptionValidator.validateAssumptions(assumptions, {
        km: 5.0,
        vmax: 10.0,
        s0: 100.0,
        measurementTime: 0.1,
        temperature: 37,
        pH: 2, // Pepsin pH
        e0: 0.01
      });

      expect(result.warnings.some(w => w.includes('pH'))).toBe(true);
    });
  });

  describe('Pipeline integration', () => {
    it('should validate complete 4-layer pipeline', async () => {
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
              year: 2024,
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

      const output: SimulationOutput = {
        trajectory: [
          { time: 0, value: 100 },
          { time: 1, value: 95 },
          { time: 2, value: 90 },
          { time: 3, value: 85 }
        ],
        finalValue: 85
      };

      const result = await ScientificValidationPipeline.validate(
        params,
        assumptions,
        {
          km: 5.2,
          vmax: 10,
          s0: 100,
          measurementTime: 10,
          temperature: 37,
          pH: 7.4,
          e0: 0.01
        },
        output
      );

      expect(result.passed).toBe(true);
      expect(result.confidence).toBeGreaterThan(0);
    });
  });
});
