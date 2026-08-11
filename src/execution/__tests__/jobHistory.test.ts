/**
 * Run history that survives the process.
 *
 * `job-manager.ts` was 369 lines that nothing imported. It had a queue, a
 * status model and statistics — all in memory, which is exactly the wrong
 * lifetime for a CLI. A CLI process exits after every command, so an
 * in-memory job store is empty on the next invocation. That is why
 * `scientific verify <jobId>` and `check-integrity <jobId>` could never
 * work: `simulate` printed a job id and the next process had no record of
 * it.
 *
 * Rather than delete the module, it was given the one thing that made it
 * useful: persistence. These tests cover that.
 */
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

import { JobManager, historyPath, type RunRecord } from '../job-manager';

let tempDir: string;
const originalHistory = process.env['TERRIUM_HISTORY_FILE'];

function record(jobId: string, overrides: Partial<RunRecord> = {}): RunRecord {
  return {
    jobId,
    at: new Date().toISOString(),
    query: 'ldh / pyruvate',
    provenance: [{ name: 'km', citation: 'BRENDA ref 1' }, { name: 's0' }],
    reproducibilityKey: 'abc123',
    dataIntegrityHash: 'def456',
    finalValue: 7.5395,
    validated: true,
    ...overrides,
  };
}

beforeEach(() => {
  tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'terrium-hist-'));
  process.env['TERRIUM_HISTORY_FILE'] = path.join(tempDir, 'history.json');
});

afterEach(() => {
  fs.rmSync(tempDir, { recursive: true, force: true });
  if (originalHistory === undefined) {
    delete process.env['TERRIUM_HISTORY_FILE'];
  } else {
    process.env['TERRIUM_HISTORY_FILE'] = originalHistory;
  }
});

describe('history survives a process boundary', () => {
  it('writes a run and reads it back', () => {
    expect(JobManager.readHistory()).toEqual([]);

    const result = JobManager.recordRun(record('job_1'));
    expect(result.ok).toBe(true);

    // Read fresh from disk -- the point is that nothing is held in memory.
    const runs = JobManager.readHistory();
    expect(runs).toHaveLength(1);
    expect(runs[0]!.jobId).toBe('job_1');
    expect(runs[0]!.finalValue).toBeCloseTo(7.5395, 6);
  });

  it('finds a specific run by id, which is what `verify` needs', () => {
    JobManager.recordRun(record('job_a'));
    JobManager.recordRun(record('job_b'));

    expect(JobManager.findRun('job_b')?.query).toBe('ldh / pyruvate');
    expect(JobManager.findRun('job_missing')).toBeUndefined();
  });

  it('appends rather than overwriting', () => {
    for (const id of ['j1', 'j2', 'j3']) {
      JobManager.recordRun(record(id));
    }
    expect(JobManager.readHistory().map((r) => r.jobId)).toEqual(['j1', 'j2', 'j3']);
  });

  it('creates the directory if it does not exist', () => {
    process.env['TERRIUM_HISTORY_FILE'] = path.join(
      tempDir,
      'nested',
      'deeper',
      'history.json',
    );
    expect(JobManager.recordRun(record('job_nested')).ok).toBe(true);
    expect(JobManager.readHistory()).toHaveLength(1);
  });

  it('keeps the file bounded', () => {
    // History is a convenience, not an archive: an unbounded JSON file
    // read on every invocation gets slow.
    for (let i = 0; i < 210; i++) {
      JobManager.recordRun(record(`job_${i}`));
    }
    const runs = JobManager.readHistory();
    expect(runs.length).toBeLessThanOrEqual(200);
    // The NEWEST are the ones kept.
    expect(runs[runs.length - 1]!.jobId).toBe('job_209');
  });

  it('preserves the provenance, which is the reason to keep history at all', () => {
    JobManager.recordRun(record('job_prov'));
    const stored = JobManager.findRun('job_prov');
    expect(stored?.provenance).toHaveLength(2);
    expect(JSON.stringify(stored?.provenance)).toContain('BRENDA ref 1');
  });
});

describe('a broken history file cannot break the CLI', () => {
  it('treats unreadable JSON as empty rather than throwing', () => {
    fs.writeFileSync(historyPath(), 'this is not json', 'utf-8');
    // A corrupt convenience file must not stop a simulation from running.
    expect(() => JobManager.readHistory()).not.toThrow();
    expect(JobManager.readHistory()).toEqual([]);
  });

  it('treats a non-array payload as empty', () => {
    fs.writeFileSync(historyPath(), '{"not":"an array"}', 'utf-8');
    expect(JobManager.readHistory()).toEqual([]);
  });

  it('reports a write failure instead of silently losing the run', () => {
    // Pointing at a path that cannot be created. The user was told a job
    // id; if it will not be findable later they need to know why.
    process.env['TERRIUM_HISTORY_FILE'] = path.join(
      historyPath(),
      'impossible',
      'history.json',
    );
    fs.writeFileSync(path.join(tempDir, 'history.json'), '[]', 'utf-8');

    const result = JobManager.recordRun(record('job_fail'));
    expect(result.ok).toBe(false);
    expect(result.reason).toBeTruthy();
  });
});
