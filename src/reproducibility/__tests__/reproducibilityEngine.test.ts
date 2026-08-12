/**
 * Unit Tests: Reproducibility Engine
 *
 * Tests execution recording, reproduction verification, and data integrity
 * Run: npm test -- reproducibilityEngine.test.ts
 */

import {
  ExecutionRecorder,
  ReproducibilityVerifier,
  DataIntegrityChecker,
  ReproducibilityService,
  type ExecutionRecord
} from '../reproducibilityEngine';

describe('ExecutionRecorder', () => {
  it('should create record with all required fields', () => {
    const record = ExecutionRecorder.createRecord(
      'job_001',
      'Test query',
      { km: { value: 5.2, unit: 'mM', source: 'literature', confidence: 0.95 } },
      { temperature: 37, pH: 7.4 },
      { trajectory: [{ time: 0, value: 100 }], metrics: {} }
    );

    expect(record.jobId).toBe('job_001');
    expect(record.inputs.query).toBe('Test query');
    expect(record.hashes.inputHash).toBeDefined();
    expect(record.hashes.outputHash).toBeDefined();
    expect(record.hashes.reproductionKey).toBeDefined();
    expect(record.environment).toBeDefined();
    expect(record.gitState).toBeDefined();
  });

  it('should create consistent hashes for same input', () => {
    const input1 = { test: 'data' };
    const input2 = { test: 'data' };

    const record1 = ExecutionRecorder.createRecord(
      'job_001',
      'Query',
      input1,
      {},
      { trajectory: [], metrics: {} }
    );

    const record2 = ExecutionRecorder.createRecord(
      'job_002',
      'Query',
      input2,
      {},
      { trajectory: [], metrics: {} }
    );

    // Both records used same parameters, so input hashes should be equal
    // (even though job IDs and timestamps differ)
    expect(record1.hashes.inputHash).toBe(record2.hashes.inputHash);
  });

  it('should produce different hashes for different outputs', () => {
    const record1 = ExecutionRecorder.createRecord(
      'job_001',
      'Query',
      {},
      {},
      { trajectory: [{ time: 0, value: 100 }], metrics: {} }
    );

    const record2 = ExecutionRecorder.createRecord(
      'job_002',
      'Query',
      {},
      {},
      { trajectory: [{ time: 0, value: 200 }], metrics: {} }
    );

    expect(record1.hashes.outputHash).not.toBe(record2.hashes.outputHash);
  });

  it('should add execution phases', () => {
    const record = ExecutionRecorder.createRecord(
      'job_001',
      'Query',
      {},
      {},
      { trajectory: [], metrics: {} }
    );

    ExecutionRecorder.addPhase(record, 'validation', 100, undefined, []);
    ExecutionRecorder.addPhase(record, 'simulation', 500, 100);
    ExecutionRecorder.addPhase(record, 'verification', 50, undefined, ['warning1']);

    expect(record.executionTrace).toHaveLength(3);
    expect(record.executionTrace[0].phase).toBe('validation');
    expect(record.executionTrace[1].durationMs).toBe(500);
    expect(record.executionTrace[2].warnings).toContain('warning1');
  });
});

describe('ReproducibilityVerifier', () => {
  const mockReproducer = async (inputs: any) => ({
    trajectory: [
      { time: 0, value: 100 },
      { time: 1, value: 95 },
      { time: 2, value: 90 }
    ],
    metrics: { finalValue: 90 }
  });

  it('should verify reproducible outputs', async () => {
    const originalRecord = ExecutionRecorder.createRecord(
      'job_001',
      'Query',
      { param: 'value' },
      {},
      {
        trajectory: [
          { time: 0, value: 100 },
          { time: 1, value: 95 },
          { time: 2, value: 90 }
        ],
        metrics: { finalValue: 90 }
      }
    );

    const result = await ReproducibilityVerifier.verify(originalRecord, mockReproducer);

    expect(result.verification.passed).toBe(true);
    expect(result.verification.maxRelativeError).toBeLessThan(0.01);
    expect(result.verification.outputsIdentical).toBe(true);
  });

  it('should detect output differences', async () => {
    const originalRecord = ExecutionRecorder.createRecord(
      'job_001',
      'Query',
      {},
      {},
      {
        trajectory: [
          { time: 0, value: 100 },
          { time: 1, value: 95 }
        ],
        metrics: {}
      }
    );

    const differentReproducer = async () => ({
      trajectory: [
        { time: 0, value: 100 },
        { time: 1, value: 90 } // Different value
      ],
      metrics: {}
    });

    const result = await ReproducibilityVerifier.verify(
      originalRecord,
      differentReproducer
    );

    expect(result.verification.maxRelativeError).toBeGreaterThan(0);
  });

  it('should identify possible causes of differences', async () => {
    const record = ExecutionRecorder.createRecord(
      'job_001',
      'Query',
      {},
      {},
      { trajectory: [{ time: 0, value: 100 }], metrics: {} }
    );

    const reproducer = async () => ({
      trajectory: [{ time: 0, value: 100.0001 }],
      metrics: {}
    });

    const result = await ReproducibilityVerifier.verify(record, reproducer);

    // `if (result.differences)` made this pass whenever no differences were
    // reported -- which is the one outcome that would mean the diagnosis code
    // never ran. A 1e-6 relative discrepancy is exactly the case it exists to
    // explain, so the presence of `differences` is part of the claim.
    // jest's expect() takes one argument -- no chai/node:assert-style
    // custom-message parameter -- so state the expectation in a comment
    // instead of passing it to toBeDefined().
    // A 100 vs 100.0001 discrepancy must produce a differences report.
    expect(result.differences).toBeDefined();
    expect(result.differences!.possibleCauses).toContain(
      'Different floating-point implementations'
    );
  });
});

describe('DataIntegrityChecker', () => {
  it('should PASS for intact data', () => {
    const record = ExecutionRecorder.createRecord(
      'job_001',
      'Query',
      { param: 'value' },
      {},
      { trajectory: [{ time: 0, value: 100 }], metrics: {} }
    );

    const result = DataIntegrityChecker.verify(record);

    expect(result.intact).toBe(true);
    expect(result.issues).toHaveLength(0);
  });

  it('should FAIL if input hash mismatches', () => {
    const record = ExecutionRecorder.createRecord(
      'job_001',
      'Query',
      { param: 'value' },
      {},
      { trajectory: [{ time: 0, value: 100 }], metrics: {} }
    );

    // Tamper with input
    (record.inputs as any).param = 'different_value';

    const result = DataIntegrityChecker.verify(record);

    expect(result.intact).toBe(false);
    expect(result.issues.some(i => i.includes('Input data'))).toBe(true);
  });

  it('should FAIL if output hash mismatches', () => {
    const record = ExecutionRecorder.createRecord(
      'job_001',
      'Query',
      {},
      {},
      { trajectory: [{ time: 0, value: 100 }], metrics: {} }
    );

    // Tamper with output
    record.output.trajectory[0].value = 200;

    const result = DataIntegrityChecker.verify(record);

    expect(result.intact).toBe(false);
    expect(result.issues.some(i => i.includes('Output data'))).toBe(true);
  });

  it('should FAIL if output contains NaN', () => {
    const record = ExecutionRecorder.createRecord(
      'job_001',
      'Query',
      {},
      {},
      { trajectory: [{ time: 0, value: NaN }], metrics: {} }
    );

    const result = DataIntegrityChecker.verify(record);

    expect(result.intact).toBe(false);
    expect(result.issues.some(i => i.includes('invalid values'))).toBe(true);
  });

  it('should generate integrity report', () => {
    const record = ExecutionRecorder.createRecord(
      'job_001',
      'Query',
      {},
      {},
      { trajectory: [{ time: 0, value: 100 }], metrics: {} }
    );

    const report = DataIntegrityChecker.generateReport(record);

    expect(report).toContain('Data Integrity Report');
    expect(report).toContain('INTACT');
    expect(report).toContain(record.jobId);
    expect(report).toContain('No issues detected');
  });
});

describe('ReproducibilityService', () => {
  it('should record and retrieve execution', () => {
    const service = new ReproducibilityService();

    const record = service.recordExecution(
      'job_001',
      'Query',
      { param: 'value' },
      { condition: 'value' },
      { trajectory: [], metrics: {} }
    );

    expect(record).toBeDefined();
    expect(record.jobId).toBe('job_001');

    const retrieved = service.getRecord('job_001');
    expect(retrieved).toEqual(record);
  });

  it('should track execution phases', () => {
    const service = new ReproducibilityService();

    service.recordExecution('job_001', 'Query', {}, {}, { trajectory: [], metrics: {} });
    service.addPhase('job_001', 'phase1', 100);
    service.addPhase('job_001', 'phase2', 200);

    const record = service.getRecord('job_001');
    expect(record?.executionTrace).toHaveLength(2);
  });

  it('should verify reproducibility', async () => {
    const service = new ReproducibilityService();

    service.recordExecution(
      'job_001',
      'Query',
      { param: 'value' },
      {},
      {
        trajectory: [
          { time: 0, value: 100 },
          { time: 1, value: 95 }
        ],
        metrics: {}
      }
    );

    const reproducer = async () => ({
      trajectory: [
        { time: 0, value: 100 },
        { time: 1, value: 95 }
      ],
      metrics: {}
    });

    const result = await service.verifyReproducibility('job_001', reproducer);

    expect(result.verification.passed).toBe(true);
  });

  it('should check data integrity', () => {
    const service = new ReproducibilityService();

    service.recordExecution('job_001', 'Query', {}, {}, { trajectory: [], metrics: {} });

    const result = service.checkIntegrity('job_001');

    expect(result.intact).toBe(true);
    expect(result.issues).toHaveLength(0);
  });

  it('should get all records', () => {
    const service = new ReproducibilityService();

    service.recordExecution('job_001', 'Query1', {}, {}, { trajectory: [], metrics: {} });
    service.recordExecution('job_002', 'Query2', {}, {}, { trajectory: [], metrics: {} });

    const all = service.getAllRecords();

    expect(all).toHaveLength(2);
    expect(all.map(r => r.jobId)).toContain('job_001');
    expect(all.map(r => r.jobId)).toContain('job_002');
  });

  it('should perform nightly verification', async () => {
    const service = new ReproducibilityService();

    // Record recent simulations
    const now = Date.now();
    service.recordExecution('job_001', 'Query1', {}, {}, { trajectory: [], metrics: {} });
    service.recordExecution('job_002', 'Query2', {}, {}, { trajectory: [], metrics: {} });

    const reproducer = async () => ({ trajectory: [], metrics: {} });

    const result = await service.nightly_verification(reproducer);

    expect(result.totalChecked).toBeGreaterThanOrEqual(0);
    expect(result.passed + result.failed).toBeLessThanOrEqual(result.totalChecked);
  });

  it('should throw error for non-existent record', () => {
    const service = new ReproducibilityService();

    expect(() => service.checkIntegrity('non_existent')).toThrow();
    expect(() => service.getIntegrityReport('non_existent')).toThrow();
  });
});
