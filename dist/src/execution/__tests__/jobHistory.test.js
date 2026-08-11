"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
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
const fs = __importStar(require("fs"));
const os = __importStar(require("os"));
const path = __importStar(require("path"));
const job_manager_1 = require("../job-manager");
let tempDir;
const originalHistory = process.env['TERRIUM_HISTORY_FILE'];
function record(jobId, overrides = {}) {
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
    }
    else {
        process.env['TERRIUM_HISTORY_FILE'] = originalHistory;
    }
});
describe('history survives a process boundary', () => {
    it('writes a run and reads it back', () => {
        expect(job_manager_1.JobManager.readHistory()).toEqual([]);
        const result = job_manager_1.JobManager.recordRun(record('job_1'));
        expect(result.ok).toBe(true);
        // Read fresh from disk -- the point is that nothing is held in memory.
        const runs = job_manager_1.JobManager.readHistory();
        expect(runs).toHaveLength(1);
        expect(runs[0].jobId).toBe('job_1');
        expect(runs[0].finalValue).toBeCloseTo(7.5395, 6);
    });
    it('finds a specific run by id, which is what `verify` needs', () => {
        job_manager_1.JobManager.recordRun(record('job_a'));
        job_manager_1.JobManager.recordRun(record('job_b'));
        expect(job_manager_1.JobManager.findRun('job_b')?.query).toBe('ldh / pyruvate');
        expect(job_manager_1.JobManager.findRun('job_missing')).toBeUndefined();
    });
    it('appends rather than overwriting', () => {
        for (const id of ['j1', 'j2', 'j3']) {
            job_manager_1.JobManager.recordRun(record(id));
        }
        expect(job_manager_1.JobManager.readHistory().map((r) => r.jobId)).toEqual(['j1', 'j2', 'j3']);
    });
    it('creates the directory if it does not exist', () => {
        process.env['TERRIUM_HISTORY_FILE'] = path.join(tempDir, 'nested', 'deeper', 'history.json');
        expect(job_manager_1.JobManager.recordRun(record('job_nested')).ok).toBe(true);
        expect(job_manager_1.JobManager.readHistory()).toHaveLength(1);
    });
    it('keeps the file bounded', () => {
        // History is a convenience, not an archive: an unbounded JSON file
        // read on every invocation gets slow.
        for (let i = 0; i < 210; i++) {
            job_manager_1.JobManager.recordRun(record(`job_${i}`));
        }
        const runs = job_manager_1.JobManager.readHistory();
        expect(runs.length).toBeLessThanOrEqual(200);
        // The NEWEST are the ones kept.
        expect(runs[runs.length - 1].jobId).toBe('job_209');
    });
    it('preserves the provenance, which is the reason to keep history at all', () => {
        job_manager_1.JobManager.recordRun(record('job_prov'));
        const stored = job_manager_1.JobManager.findRun('job_prov');
        expect(stored?.provenance).toHaveLength(2);
        expect(JSON.stringify(stored?.provenance)).toContain('BRENDA ref 1');
    });
});
describe('a broken history file cannot break the CLI', () => {
    it('treats unreadable JSON as empty rather than throwing', () => {
        fs.writeFileSync((0, job_manager_1.historyPath)(), 'this is not json', 'utf-8');
        // A corrupt convenience file must not stop a simulation from running.
        expect(() => job_manager_1.JobManager.readHistory()).not.toThrow();
        expect(job_manager_1.JobManager.readHistory()).toEqual([]);
    });
    it('treats a non-array payload as empty', () => {
        fs.writeFileSync((0, job_manager_1.historyPath)(), '{"not":"an array"}', 'utf-8');
        expect(job_manager_1.JobManager.readHistory()).toEqual([]);
    });
    it('reports a write failure instead of silently losing the run', () => {
        // Pointing at a path that cannot be created. The user was told a job
        // id; if it will not be findable later they need to know why.
        process.env['TERRIUM_HISTORY_FILE'] = path.join((0, job_manager_1.historyPath)(), 'impossible', 'history.json');
        fs.writeFileSync(path.join(tempDir, 'history.json'), '[]', 'utf-8');
        const result = job_manager_1.JobManager.recordRun(record('job_fail'));
        expect(result.ok).toBe(false);
        expect(result.reason).toBeTruthy();
    });
});
