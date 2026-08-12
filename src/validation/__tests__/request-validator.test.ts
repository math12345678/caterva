/**
 * Request Validator Tests
 */

import {
  validateSimulationRequest,
  validateSweepRequest,
  validateBatchRequest,
  validateComparisonRequest,
  validateJobComparisonRequest
} from '../request-validator';

describe('Request Validators', () => {
  describe('validateSimulationRequest', () => {
    it('accepts valid simulation request', () => {
      const data = {
        query: 'michaelis-menten',
        parameters: { km: 5.2, vmax: 12.8, s0: 10 },
        enzyme: 'lactate dehydrogenase',
        substrate: 'lactate'
      };

      const result = validateSimulationRequest(data);
      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
    });

    it('rejects missing query', () => {
      const data = {
        parameters: { km: 5.2, vmax: 12.8, s0: 10 }
      };

      const result = validateSimulationRequest(data);
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field === 'query')).toBe(true);
    });

    it('rejects invalid query type', () => {
      const data = {
        query: 123, // Wrong type
        parameters: { km: 5.2, vmax: 12.8, s0: 10 }
      };

      const result = validateSimulationRequest(data);
      expect(result.valid).toBe(false);
    });

    it('rejects unknown query model', () => {
      const data = {
        query: 'unknown-model',
        parameters: { km: 5.2, vmax: 12.8, s0: 10 }
      };

      const result = validateSimulationRequest(data);
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field === 'query')).toBe(true);
    });

    it('rejects missing parameters object', () => {
      const data = {
        query: 'michaelis-menten'
      };

      const result = validateSimulationRequest(data);
      expect(result.valid).toBe(false);
    });

    it('rejects missing parameter values', () => {
      const data = {
        query: 'michaelis-menten',
        parameters: { km: 5.2, vmax: 12.8 } // Missing s0
      };

      const result = validateSimulationRequest(data);
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field === 'parameters.s0')).toBe(true);
    });

    it('rejects non-positive parameter values', () => {
      const data = {
        query: 'michaelis-menten',
        parameters: { km: -5.2, vmax: 12.8, s0: 10 }
      };

      const result = validateSimulationRequest(data);
      expect(result.valid).toBe(false);
    });

    it('rejects non-number parameter values', () => {
      const data = {
        query: 'michaelis-menten',
        parameters: { km: 'five', vmax: 12.8, s0: 10 }
      };

      const result = validateSimulationRequest(data);
      expect(result.valid).toBe(false);
    });
  });

  describe('validateSweepRequest', () => {
    it('accepts valid sweep request', () => {
      const data = {
        query: 'michaelis-menten',
        baseParameters: { vmax: 12.8, s0: 10 },
        sweepParameters: [{ name: 'km', spec: '1:10:0.5' }]
      };

      const result = validateSweepRequest(data);
      expect(result.valid).toBe(true);
    });

    it('rejects missing sweepParameters', () => {
      const data = {
        query: 'michaelis-menten',
        baseParameters: { vmax: 12.8, s0: 10 }
      };

      const result = validateSweepRequest(data);
      expect(result.valid).toBe(false);
    });

    it('rejects empty sweepParameters array', () => {
      const data = {
        query: 'michaelis-menten',
        baseParameters: { vmax: 12.8, s0: 10 },
        sweepParameters: []
      };

      const result = validateSweepRequest(data);
      expect(result.valid).toBe(false);
    });

    it('rejects invalid spec format', () => {
      const data = {
        query: 'michaelis-menten',
        baseParameters: { vmax: 12.8, s0: 10 },
        sweepParameters: [{ name: 'km', spec: '1-10-0.5' }] // Wrong format
      };

      const result = validateSweepRequest(data);
      expect(result.valid).toBe(false);
    });

    it('rejects invalid spec range (min >= max)', () => {
      const data = {
        query: 'michaelis-menten',
        baseParameters: { vmax: 12.8, s0: 10 },
        sweepParameters: [{ name: 'km', spec: '10:1:0.5' }]
      };

      const result = validateSweepRequest(data);
      expect(result.valid).toBe(false);
    });

    it('rejects non-positive step', () => {
      const data = {
        query: 'michaelis-menten',
        baseParameters: { vmax: 12.8, s0: 10 },
        sweepParameters: [{ name: 'km', spec: '1:10:-0.5' }]
      };

      const result = validateSweepRequest(data);
      expect(result.valid).toBe(false);
    });
  });

  describe('validateBatchRequest', () => {
    it('accepts valid batch request', () => {
      const data = {
        query: 'michaelis-menten',
        baseParameters: { s0: 10 },
        parameterSets: [
          { km: 1, vmax: 10 },
          { km: 2, vmax: 12 }
        ]
      };

      const result = validateBatchRequest(data);
      expect(result.valid).toBe(true);
    });

    it('rejects empty parameterSets', () => {
      const data = {
        query: 'michaelis-menten',
        baseParameters: { s0: 10 },
        parameterSets: []
      };

      const result = validateBatchRequest(data);
      expect(result.valid).toBe(false);
    });

    it('rejects missing required parameters', () => {
      const data = {
        query: 'michaelis-menten',
        baseParameters: { s0: 10 },
        parameterSets: [
          { km: 1 } // Missing vmax, s0
        ]
      };

      const result = validateBatchRequest(data);
      expect(result.valid).toBe(false);
    });

    it('validates concurrency bounds', () => {
      const data = {
        query: 'michaelis-menten',
        baseParameters: { s0: 10 },
        parameterSets: [{ km: 1, vmax: 10 }],
        concurrency: 0 // Invalid
      };

      const result = validateBatchRequest(data);
      expect(result.valid).toBe(false);
    });

    it('accepts valid concurrency', () => {
      const data = {
        query: 'michaelis-menten',
        baseParameters: { s0: 10 },
        parameterSets: [{ km: 1, vmax: 10 }],
        concurrency: 5
      };

      const result = validateBatchRequest(data);
      expect(result.valid).toBe(true);
    });

    it('validates the merged set, so baseParameters can supply a required value', () => {
      // The validator used to check each parameterSet in isolation while
      // createMultiParamBatchJobs runs `{ ...baseParameters, ...params }`
      // (batch-processor.ts:197). It therefore rejected requests the engine
      // would have run, and named a parameter the caller had supplied.
      // Nothing covered the merge, which is how the two drifted apart.
      const result = validateBatchRequest({
        query: 'michaelis-menten',
        baseParameters: { s0: 10, vmax: 12.8 },
        parameterSets: [{ km: 1 }, { km: 2 }]
      });

      expect(result.errors).toEqual([]);
      expect(result.valid).toBe(true);
    });

    it('lets a parameter set override a base value, and validates the override', () => {
      const result = validateBatchRequest({
        query: 'michaelis-menten',
        baseParameters: { km: 1, vmax: 10, s0: 10 },
        parameterSets: [{ km: -5 }] // the override is what runs, so it is what is checked
      });

      expect(result.valid).toBe(false);
      expect(result.errors.map(e => e.field)).toContain('parameterSets[0].km');
    });

    it('points at baseParameters when that is where the bad value lives', () => {
      const result = validateBatchRequest({
        query: 'michaelis-menten',
        baseParameters: { s0: -1 },
        parameterSets: [{ km: 1, vmax: 10 }]
      });

      expect(result.valid).toBe(false);
      // Naming `parameterSets[0].s0` would send the caller to a field they
      // never wrote.
      expect(result.errors.map(e => e.field)).toContain('baseParameters.s0');
    });

    it('rejects non-finite values', () => {
      // NaN and Infinity are numbers and pass `> 0` in the case of Infinity;
      // both make the integrator produce a trajectory of NaN rather than an
      // error, which is the worst available outcome.
      const result = validateBatchRequest({
        query: 'michaelis-menten',
        baseParameters: { s0: 10 },
        parameterSets: [{ km: Number.NaN, vmax: Number.POSITIVE_INFINITY }]
      });

      expect(result.valid).toBe(false);
      expect(result.errors.map(e => e.field).sort()).toEqual([
        'parameterSets[0].km',
        'parameterSets[0].vmax'
      ]);
    });
  });

  describe('validateComparisonRequest', () => {
    it('accepts valid comparison request', () => {
      const data = {
        parameters: { km: 5.2, vmax: 12.8, s0: 10 }
      };

      const result = validateComparisonRequest(data);
      expect(result.valid).toBe(true);
    });

    it('rejects missing parameters', () => {
      const data = {};

      const result = validateComparisonRequest(data);
      expect(result.valid).toBe(false);
    });

    it('rejects invalid parameter values', () => {
      const data = {
        parameters: { km: -5.2, vmax: 12.8, s0: 10 }
      };

      const result = validateComparisonRequest(data);
      expect(result.valid).toBe(false);
    });
  });

  describe('validateJobComparisonRequest', () => {
    it('accepts valid job comparison request', () => {
      const data = {
        jobIds: ['job_1', 'job_2', 'job_3']
      };

      const result = validateJobComparisonRequest(data);
      expect(result.valid).toBe(true);
    });

    it('rejects less than 2 jobs', () => {
      const data = {
        jobIds: ['job_1']
      };

      const result = validateJobComparisonRequest(data);
      expect(result.valid).toBe(false);
    });

    it('rejects empty job IDs', () => {
      const data = {
        jobIds: []
      };

      const result = validateJobComparisonRequest(data);
      expect(result.valid).toBe(false);
    });

    it('rejects non-string job IDs', () => {
      const data = {
        jobIds: ['job_1', 123]
      };

      const result = validateJobComparisonRequest(data);
      expect(result.valid).toBe(false);
    });

    it('rejects empty string job IDs', () => {
      const data = {
        jobIds: ['job_1', '']
      };

      const result = validateJobComparisonRequest(data);
      expect(result.valid).toBe(false);
    });
  });
});
