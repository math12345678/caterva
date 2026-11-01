/**
 * A job id has to mean something tomorrow.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * `ReproducibilityService.records` was a bare in-memory `Map`, and the CLI is
 * a fresh process per invocation. So `scientific verify <jobId>` and
 * `scientific check-integrity <jobId>` looked the job up in a Map that had
 * been constructed empty microseconds earlier, and threw
 * `Record not found for job <jobId>` — for every job id, always, since the
 * commands existed.
 *
 * Both are advertised in `help`. The simulation itself prints
 * "Saved. Re-check it later with: scientific check-integrity <jobId>" — a
 * promise the tool could not keep. And `history` persists to
 * `~/.caterva/history.json` and lists those same ids, its help text reading:
 * "The run id printed at the end of a simulation is only useful if something
 * can resolve it later; this is that something." So the tool printed an id,
 * listed it, and then denied it existed.
 *
 * WHY NO EXISTING TEST CAUGHT IT
 * ------------------------------
 * A unit test that calls `recordExecution` and then `checkIntegrity` on the
 * same service instance passes, because the Map is populated. The defect
 * exists only ACROSS instances — which is the only way a user ever meets it.
 * So every assertion below uses a SECOND service object, standing in for the
 * second process.
 */
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

import { ReproducibilityService, legacyRecordsDir, recordsDir } from '../reproducibilityEngine';

let home: string;
let originalHome: string | undefined;

const INPUTS = {
  km: { value: 10.73, unit: 'mM', source: 'brenda_exact', confidence: 0.9 },
  s0: { value: 10, unit: 'mM', source: 'user', confidence: 1 },
};
const CONDITIONS = { temperature: 25, ph: 7.4 };
const OUTPUT = { trajectory: [{ time: 0, value: 10 }, { time: 1, value: 5.14 }] };

beforeEach(() => {
  originalHome = process.env['HOME'];
  home = fs.mkdtempSync(path.join(os.tmpdir(), 'caterva-home-'));
  process.env['HOME'] = home;
});

afterEach(() => {
  if (originalHome === undefined) delete process.env['HOME'];
  else process.env['HOME'] = originalHome;
  fs.rmSync(home, { recursive: true, force: true });
});

describe('a record written by one process is readable by the next', () => {
  it('finds the record from a service that never recorded it', () => {
    const first = new ReproducibilityService();
    first.recordExecution('job_alpha', 'ldh / pyruvate', INPUTS, CONDITIONS, OUTPUT);

    // The second process. Nothing in its Map.
    const second = new ReproducibilityService();
    const record = second.getRecord('job_alpha');

    expect(record).toBeDefined();
    expect(record!.jobId).toBe('job_alpha');
  });

  it('revives the timestamp as a Date, not a string', () => {
    // JSON.stringify writes a Date as a string. Every consumer of
    // `record.timestamp` expects the object, so leaving it a string gives a
    // record that LOOKS loaded and throws on first use — worse than not
    // loading it, because the failure surfaces far from the cause.
    const first = new ReproducibilityService();
    first.recordExecution('job_beta', 'q', INPUTS, CONDITIONS, OUTPUT);

    const record = new ReproducibilityService().getRecord('job_beta');
    expect(record!.timestamp).toBeInstanceOf(Date);
    expect(Number.isNaN(record!.timestamp.getTime())).toBe(false);
  });

  it('checks integrity across instances, and says the data is intact', () => {
    const first = new ReproducibilityService();
    first.recordExecution('job_gamma', 'q', INPUTS, CONDITIONS, OUTPUT);

    const result = new ReproducibilityService().checkIntegrity('job_gamma');
    expect(result.intact).toBe(true);
    expect(result.issues).toEqual([]);
  });
});

describe('the integrity check can actually fail', () => {
  it('detects a parameter value edited on disk', () => {
    // The whole point of storing a hash. Without this assertion the test
    // above only proves the check returns `intact: true`, which a function
    // that always returned `intact: true` would also satisfy.
    const first = new ReproducibilityService();
    first.recordExecution('job_delta', 'q', INPUTS, CONDITIONS, OUTPUT);

    const file = path.join(recordsDir(), 'job_delta.json');
    const onDisk = JSON.parse(fs.readFileSync(file, 'utf-8'));
    onDisk.inputs.parameters.km.value = 21.46; // doubled, hash untouched
    fs.writeFileSync(file, JSON.stringify(onDisk), 'utf-8');

    const result = new ReproducibilityService().checkIntegrity('job_delta');
    expect(result.intact).toBe(false);
    expect(result.issues.join(' ')).toMatch(/input/i);
  });
});

describe('missing and damaged are different', () => {
  it('reports a job that was never recorded as absent, and points at history', () => {
    expect(() => new ReproducibilityService().checkIntegrity('job_never')).toThrow(
      /no execution record/i,
    );
    // The message has to tell someone what to do next. "Record not found"
    // alone is a dead end when the id came from the tool's own output.
    expect(() => new ReproducibilityService().checkIntegrity('job_never')).toThrow(
      /history/i,
    );
  });

  it('does NOT report an unreadable record as a missing one', () => {
    // A truncated or corrupt file is not "no such job". Saying so would send
    // someone looking for a run they know they performed — the same
    // could-not-look / found-nothing conflation this project keeps apart
    // everywhere else.
    fs.mkdirSync(recordsDir(), { recursive: true });
    fs.writeFileSync(path.join(recordsDir(), 'job_torn.json'), '{"jobId": "job_t', 'utf-8');

    expect(() => new ReproducibilityService().getRecord('job_torn')).toThrow(
      /damaged record, not a missing one/i,
    );
  });
});

describe('persistence never turns a good run into a failed one', () => {
  it('records in memory even when the record cannot be written to disk', () => {
    // An unwritable home must not fail a simulation that produced a correct
    // result — that would make the exit code mean two things. The consequence
    // (verify will not find this job) is logged, not thrown.
    //
    // A REAL filesystem failure rather than a mocked one: HOME is pointed at
    // a regular file, so `mkdirSync` under it fails with ENOTDIR the way it
    // would on a read-only or full disk. Mocking `fs.writeFileSync` would
    // also have tested that jest can mock fs, which is not in question.
    const blocker = path.join(home, 'not-a-directory');
    fs.writeFileSync(blocker, 'x', 'utf-8');
    process.env['HOME'] = blocker;

    const service = new ReproducibilityService();
    expect(() =>
      service.recordExecution('job_eps', 'q', INPUTS, CONDITIONS, OUTPUT),
    ).not.toThrow();

    // Nothing was written — the failure was real, not swallowed silently by
    // a path that happened to work.
    expect(fs.existsSync(path.join(blocker, '.caterva'))).toBe(false);

    // Still usable within this process, which is what the caller needs now.
    expect(service.getRecord('job_eps')).toBeDefined();
  });
});

describe('records written under the old name still verify', () => {
  it('reads a record from ~/.terrium/records, and writes new ones to ~/.caterva', () => {
    // A job recorded before the rename. Copy a real record there by hand,
    // as an older version of Caterva would have left it.
    const writer = new ReproducibilityService();
    writer.recordExecution('job_legacy', 'ldh / pyruvate', INPUTS, CONDITIONS, OUTPUT);
    fs.mkdirSync(legacyRecordsDir(), { recursive: true });
    fs.renameSync(
      path.join(recordsDir(), 'job_legacy.json'),
      path.join(legacyRecordsDir(), 'job_legacy.json'),
    );

    const reader = new ReproducibilityService();
    expect(reader.getRecord('job_legacy')?.jobId).toBe('job_legacy');
    expect(fs.existsSync(path.join(recordsDir(), 'job_legacy.json'))).toBe(false);
  });
});
