import {
  parseSweepParameter,
  generateSweepPoints,
  countSweepSimulations,
  runSweep,
  analyzeSweep,
  SweepParameter,
  SweepResults
} from '../parameter-sweep';

describe('Parameter Sweep Engine', () => {
  describe('parseSweepParameter', () => {
    it('should parse valid sweep spec', () => {
      const param = parseSweepParameter('km', '1:10:0.5');
      expect(param.name).toBe('km');
      expect(param.min).toBe(1);
      expect(param.max).toBe(10);
      expect(param.step).toBe(0.5);
    });

    it('should reject invalid spec format', () => {
      expect(() => parseSweepParameter('km', '1:10')).toThrow(
        /Invalid sweep spec/
      );
    });

    it('should reject non-numeric values', () => {
      expect(() => parseSweepParameter('km', 'a:10:1')).toThrow(/Non-numeric/);
    });

    it('should reject zero step', () => {
      expect(() => parseSweepParameter('km', '1:10:0')).toThrow(
        /Step must be positive/
      );
    });

    it('should reject min >= max', () => {
      expect(() => parseSweepParameter('km', '10:10:1')).toThrow(
        /Min must be less than max/
      );
    });
  });

  describe('generateSweepPoints', () => {
    it('should generate correct number of points', () => {
      const param: SweepParameter = { name: 'km', min: 1, max: 10, step: 1 };
      const points = generateSweepPoints(param);
      expect(points).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
    });

    it('should handle fractional steps', () => {
      const param: SweepParameter = { name: 'km', min: 1, max: 2, step: 0.5 };
      const points = generateSweepPoints(param);
      expect(points).toEqual([1, 1.5, 2]);
    });

    it('should handle small ranges', () => {
      const param: SweepParameter = { name: 'km', min: 1, max: 1.2, step: 0.1 };
      const points = generateSweepPoints(param);
      expect(points.length).toBeGreaterThan(0);
      expect(points[0]).toBe(1);
      expect(points[points.length - 1]).toBeCloseTo(1.2, 1);
    });

    it('should include boundary values', () => {
      const param: SweepParameter = { name: 'km', min: 0, max: 100, step: 25 };
      const points = generateSweepPoints(param);
      expect(points[0]).toBe(0);
      expect(points[points.length - 1]).toBeCloseTo(100, 0);
    });
  });

  describe('countSweepSimulations', () => {
    it('should count single parameter sweep', () => {
      const params: SweepParameter[] = [
        { name: 'km', min: 1, max: 10, step: 1 }
      ];
      const count = countSweepSimulations(params);
      expect(count).toBe(10);
    });

    it('should count multi-parameter sweep (Cartesian product)', () => {
      const params: SweepParameter[] = [
        { name: 'km', min: 1, max: 10, step: 1 }, // 10 points
        { name: 'vmax', min: 5, max: 15, step: 5 } // 3 points
      ];
      const count = countSweepSimulations(params);
      expect(count).toBe(30); // 10 × 3
    });

    it('should handle fractional steps in count', () => {
      const params: SweepParameter[] = [
        { name: 'km', min: 1, max: 2, step: 0.5 } // [1, 1.5, 2] = 3 points
      ];
      const count = countSweepSimulations(params);
      expect(count).toBe(3);
    });

    it('should handle large sweep spaces', () => {
      const params: SweepParameter[] = [
        { name: 'km', min: 1, max: 10, step: 0.1 }, // 91 points
        { name: 'vmax', min: 5, max: 20, step: 1 } // 16 points
      ];
      const count = countSweepSimulations(params);
      expect(count).toBe(91 * 16);
    });
  });

  describe('analyzeSweep', () => {
    it('should handle empty results', () => {
      const sweepResults: SweepResults = {
        query: 'michaelis-menten',
        sweptParameters: [{ name: 'km', min: 1, max: 10, step: 1 }],
        baseParameters: { vmax: 10, s0: 5 },
        results: [],
        totalSimulations: 0,
        completedSimulations: 0,
        totalTimeMs: 100,
        successRate: 0
      };

      const analysis = analyzeSweep(sweepResults);
      expect(analysis.meanFinalValue).toBe(0);
      expect(analysis.optimalValue).toBe(0);
    });

    it('should calculate basic statistics', () => {
      const results = [
        {
          parameters: { km: 1 },
          finalValue: 5,
          confidence: 0.9,
          validated: true,
          executionTimeMs: 100
        },
        {
          parameters: { km: 2 },
          finalValue: 10,
          confidence: 0.8,
          validated: true,
          executionTimeMs: 100
        },
        {
          parameters: { km: 3 },
          finalValue: 7,
          confidence: 0.85,
          validated: true,
          executionTimeMs: 100
        }
      ];

      const sweepResults: SweepResults = {
        query: 'michaelis-menten',
        sweptParameters: [{ name: 'km', min: 1, max: 3, step: 1 }],
        baseParameters: { vmax: 10, s0: 5 },
        results,
        totalSimulations: 3,
        completedSimulations: 3,
        totalTimeMs: 300,
        successRate: 1
      };

      const analysis = analyzeSweep(sweepResults);
      expect(analysis.meanFinalValue).toBeCloseTo((5 + 10 + 7) / 3, 1);
      expect(analysis.minFinalValue).toBe(5);
      expect(analysis.maxFinalValue).toBe(10);
      expect(analysis.optimalValue).toBe(5); // Minimum substrate
    });

    it('should identify optimal parameters', () => {
      const results = [
        { parameters: { km: 2 }, finalValue: 3, confidence: 0.8, validated: true, executionTimeMs: 100 },
        {
          parameters: { km: 5 },
          finalValue: 1,
          confidence: 0.9,
          validated: true,
          executionTimeMs: 100
        }, // Best
        { parameters: { km: 8 }, finalValue: 4, confidence: 0.75, validated: true, executionTimeMs: 100 }
      ];

      const sweepResults: SweepResults = {
        query: 'michaelis-menten',
        sweptParameters: [{ name: 'km', min: 2, max: 8, step: 3 }],
        baseParameters: { vmax: 10, s0: 5 },
        results,
        totalSimulations: 3,
        completedSimulations: 3,
        totalTimeMs: 300,
        successRate: 1
      };

      const analysis = analyzeSweep(sweepResults);
      expect(analysis.optimalValue).toBe(1);
      expect(analysis.optimalParams.km).toBe(5);
    });

    it('should calculate parameter sensitivity', () => {
      const results = [
        { parameters: { km: 1 }, finalValue: 2, confidence: 0.9, validated: true, executionTimeMs: 100 },
        { parameters: { km: 10 }, finalValue: 5, confidence: 0.9, validated: true, executionTimeMs: 100 }
      ];

      const sweepResults: SweepResults = {
        query: 'michaelis-menten',
        sweptParameters: [{ name: 'km', min: 1, max: 10, step: 9 }],
        baseParameters: { vmax: 10, s0: 5 },
        results,
        totalSimulations: 2,
        completedSimulations: 2,
        totalTimeMs: 200,
        successRate: 1
      };

      const analysis = analyzeSweep(sweepResults);
      expect(analysis.parameterSensitivity['km']).toBeGreaterThan(0);
      // Sensitivity = |5 - 2| / |10 - 1| = 3/9 = 0.333...
      expect(analysis.parameterSensitivity['km']).toBeCloseTo(0.333, 2);
    });
  });

  describe('runSweep', () => {
    it('should run single-parameter sweep', async () => {
      const params: SweepParameter[] = [
        { name: 'km', min: 1, max: 3, step: 1 }
      ];

      const sweepResults = await runSweep(
        'michaelis-menten',
        { vmax: 10, s0: 5 },
        params
      );

      expect(sweepResults.results.length).toBeGreaterThan(0);
      expect(sweepResults.totalTimeMs).toBeGreaterThan(0);
      expect(sweepResults.successRate).toBeGreaterThanOrEqual(0);
    }, 30000); // 30s timeout

    it('should provide progress callback', async () => {
      const params: SweepParameter[] = [
        { name: 'km', min: 1, max: 2, step: 1 }
      ];

      let progressCalls = 0;
      const onProgress = () => {
        progressCalls++;
      };

      await runSweep(
        'michaelis-menten',
        { vmax: 10, s0: 5 },
        params,
        onProgress
      );

      expect(progressCalls).toBeGreaterThan(0);
    }, 30000);
  });
});
