import { describe, it, expect, beforeEach } from "vitest";
import * as queue from "../lib/queue";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

beforeEach(() => {
  queue.reset();
});

describe("createJob", () => {
  it("creates a job with pending status and uuid jobId", () => {
    const job = queue.createJob("test query");
    expect(job.jobId).toBeDefined();
    expect(job.jobId.length).toBe(36);
    expect(job.query).toBe("test query");
    expect(job.status).toBe("pending");
    expect(job.progress).toBe(0);
    expect(job.createdAt).toBeDefined();
    expect(job.updatedAt).toBeDefined();
    expect(job.result).toBeUndefined();
    expect(job.error).toBeUndefined();
  });

  it("creates unique jobIds for successive calls", () => {
    const a = queue.createJob("a");
    const b = queue.createJob("b");
    expect(a.jobId).not.toBe(b.jobId);
  });
});

describe("getJob", () => {
  it("returns undefined for unknown jobId", () => {
    expect(queue.getJob("nonexistent")).toBeUndefined();
  });

  it("returns the job after creation", () => {
    const created = queue.createJob("find me");
    const fetched = queue.getJob(created.jobId);
    expect(fetched).toBeDefined();
    expect(fetched!.jobId).toBe(created.jobId);
    expect(fetched!.query).toBe("find me");
  });
});

describe("updateJob", () => {
  it("updates status and progress", () => {
    const job = queue.createJob("update test");
    const updated = queue.updateJob(job.jobId, { status: "resolving" });
    expect(updated!.status).toBe("resolving");
    expect(updated!.progress).toBe(15);
  });

  it("does not modify createdAt", () => {
    const job = queue.createJob("createdAt test");
    const updated = queue.updateJob(job.jobId, { status: "running" });
    expect(updated!.createdAt).toBe(job.createdAt);
  });

  it("updates updatedAt on each call", () => {
    const job = queue.createJob("updatedAt test");
    const first = queue.updateJob(job.jobId, { status: "resolving" });
    const second = queue.updateJob(job.jobId, { status: "running" });
    expect(new Date(second!.updatedAt).getTime()).toBeGreaterThanOrEqual(
      new Date(first!.updatedAt).getTime(),
    );
  });

  it("returns undefined for unknown jobId", () => {
    expect(queue.updateJob("nope", { status: "completed" })).toBeUndefined();
  });

  it("propagates result to subscribers", () => {
    return new Promise<void>((done) => {
      const job = queue.createJob("subscriber test");
      const unsub = queue.subscribe(job.jobId, (updated) => {
        expect(updated.status).toBe("completed");
        expect(updated.result).toBeDefined();
        expect(updated.result!.domain).toBe("mm");
        unsub();
        // reset queue after test
        done();
      });
      queue.setJobResult(job.jobId, {
        runId: "r1",
        domain: "mm",
        parameters: {},
        trajectory: [],
        provenance: { reasoning: "test", modelCitations: [], flags: [] },
        parameterProvenance: {},
        completedAt: new Date().toISOString(),
      });
    });
  });
});

describe("setJobResult", () => {
  it("marks job as completed with result", () => {
    const job = queue.createJob("result test");
    const result = {
      runId: "r1",
      domain: "mm" as const,
      parameters: { km: 5 },
      trajectory: [
        { t: 0, S: 100 },
        { t: 1, S: 50 },
      ],
      provenance: { reasoning: "test", modelCitations: [], flags: [] },
      parameterProvenance: {},
      completedAt: new Date().toISOString(),
    };
    const updated = queue.setJobResult(job.jobId, result);
    expect(updated!.status).toBe("completed");
    expect(updated!.progress).toBe(100);
    expect(updated!.result).toEqual(result);
  });
});

describe("setJobError", () => {
  it("marks job as failed with error", () => {
    const job = queue.createJob("error test");
    const err = { error: "TEST_ERROR", message: "something broke" };
    const updated = queue.setJobError(job.jobId, err);
    expect(updated!.status).toBe("failed");
    expect(updated!.progress).toBe(100);
    expect(updated!.error).toEqual(err);
  });
});

describe("listJobs", () => {
  it("returns empty array initially", () => {
    const jobs = queue.listJobs();
    expect(jobs).toBeInstanceOf(Array);
    expect(jobs.length).toBe(0);
  });

  it("returns all created jobs in reverse chronological order", async () => {
    const j1 = queue.createJob("first");
    await sleep(2);
    const j2 = queue.createJob("second");
    await sleep(2);
    const j3 = queue.createJob("third");
    const jobs = queue.listJobs();
    expect(jobs.length).toBe(3);
    expect(jobs[0]!.jobId).toBe(j3.jobId);
    expect(jobs[1]!.jobId).toBe(j2.jobId);
    expect(jobs[2]!.jobId).toBe(j1.jobId);
  });
});

describe("subscribe / unsubscribe", () => {
  it("unsubscribe stops receiving updates", () => {
    const job = queue.createJob("unsub test");
    let callCount = 0;
    const unsub = queue.subscribe(job.jobId, () => {
      callCount++;
    });
    unsub();
    queue.updateJob(job.jobId, { status: "completed" });
    expect(callCount).toBe(0);
  });

  it("multiple subscribers all receive updates", () => {
    const job = queue.createJob("multi sub");
    let count1 = 0;
    let count2 = 0;
    const u1 = queue.subscribe(job.jobId, () => {
      count1++;
    });
    const u2 = queue.subscribe(job.jobId, () => {
      count2++;
    });
    queue.updateJob(job.jobId, { status: "resolving" });
    expect(count1).toBe(1);
    expect(count2).toBe(1);
    u1();
    u2();
  });
});

describe("cancelJob", () => {
  it("cancels a pending job", () => {
    const job = queue.createJob("cancel me");
    const updated = queue.cancelJob(job.jobId);
    expect(updated!.status).toBe("cancelled");
    expect(updated!.progress).toBe(100);
  });

  it("cancels a running job", () => {
    const job = queue.createJob("cancel running");
    queue.updateJob(job.jobId, { status: "running" });
    const updated = queue.cancelJob(job.jobId);
    expect(updated!.status).toBe("cancelled");
  });

  it("returns existing job for terminal statuses", () => {
    const job = queue.createJob("already done");
    queue.setJobResult(job.jobId, {
      runId: "r1",
      domain: "mm",
      parameters: {},
      trajectory: [],
      provenance: { reasoning: "x", modelCitations: [], flags: [] },
      parameterProvenance: {},
      completedAt: new Date().toISOString(),
    });
    const updated = queue.cancelJob(job.jobId);
    expect(updated!.status).toBe("completed");
  });

  it("returns undefined for unknown jobId", () => {
    expect(queue.cancelJob("unknown")).toBeUndefined();
  });

  it("notifies subscribers on cancel", () => {
    return new Promise<void>((done) => {
      const job = queue.createJob("cancel notify");
      const unsub = queue.subscribe(job.jobId, (updated) => {
        expect(updated.status).toBe("cancelled");
        unsub();
        done();
      });
      queue.cancelJob(job.jobId);
    });
  });

  it("registers abort controller and aborts on cancel", () => {
    const job = queue.createJob("abort test");
    const ctrl = new AbortController();
    queue.registerAbortController(job.jobId, ctrl);
    expect(ctrl.signal.aborted).toBe(false);
    queue.cancelJob(job.jobId);
    expect(ctrl.signal.aborted).toBe(true);
  });
});

describe("acquireRunnerSlot / releaseRunnerSlot", () => {
  it("allows up to MAX_CONCURRENT runners", async () => {
    const a = queue.acquireRunnerSlot();
    const b = queue.acquireRunnerSlot();
    // Both should resolve immediately since max is 2
    await a;
    await b;
    queue.releaseRunnerSlot();
    queue.releaseRunnerSlot();
  });

  it("queues excess runners", async () => {
    const a = queue.acquireRunnerSlot();
    const b = queue.acquireRunnerSlot();
    await a;
    await b;

    // Third should NOT resolve until we release
    let thirdResolved = false;
    const c = queue.acquireRunnerSlot().then(() => {
      thirdResolved = true;
    });
    await sleep(10);
    expect(thirdResolved).toBe(false);

    queue.releaseRunnerSlot();
    await sleep(10);
    expect(thirdResolved).toBe(true);

    queue.releaseRunnerSlot();
    queue.releaseRunnerSlot();
  });

  it("rejects queued runners when the queue is reset", async () => {
    const a = queue.acquireRunnerSlot();
    const b = queue.acquireRunnerSlot();
    await a;
    await b;

    const queued = queue.acquireRunnerSlot();
    queue.reset();

    await expect(queued).rejects.toThrow("Runner queue reset");
    queue.releaseRunnerSlot();
    queue.releaseRunnerSlot();

    const next = queue.acquireRunnerSlot();
    await expect(next).resolves.toBeUndefined();
    queue.releaseRunnerSlot();
  });
});
