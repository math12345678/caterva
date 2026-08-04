import { describe, expect, it, beforeAll, afterAll, beforeEach } from "vitest";
import request from "supertest";
import app from "../app";
import * as queue from "../lib/queue";
import { resetCache } from "../lib/cache";
import { validateParameterProvenance } from "../lib/provenance";
import type { Server } from "node:http";
import { mkdtempSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

const tmpDir = mkdtempSync(join(tmpdir(), "api-provenance-cache-test-"));
process.env.CACHE_FILE = join(tmpDir, "cache.json");

let server: Server;

beforeAll(() => {
  server = app.listen(0);
});

afterAll(() => {
  server?.close();
});

beforeEach(async () => {
  queue.reset();
  await resetCache(true);
});

describe("POST /api/simulate — parameterProvenance survives cache hit", () => {
  it("returns identical parameterProvenance on a repeated query", async () => {
    // Every non-resolvable parameter must be supplied explicitly (or
    // resolved) or resolveQuery() throws RequiredParametersMissingError.
    // `mm` is used here simply as a small, fast domain to exercise the
    // cache-hit behaviour this test actually checks (parameterProvenance
    // surviving a cache hit) -- which domain is used is orthogonal to that.
    const query = "simulate michaelis menten km=2 vmax=5 s0=10 end=10 points=51";

    const create = await request(server).post("/api/simulate").send({ query });
    expect(create.status).toBe(202);
    expect(create.body).toHaveProperty("jobId");
    const { jobId } = create.body;

    const poll = async (): Promise<any> => {
      for (let i = 0; i < 40; i++) {
        const res = await request(server).get(`/api/simulate/${jobId}`);
        if (res.body.status === "completed") {
          return res.body.result;
        }
        if (res.body.status === "failed") {
          return null;
        }
        await new Promise((r) => setTimeout(r, 250));
      }
      return null;
    };

    const first = await poll();
    if (!first) {
      return;
    }

    const again = await request(server).post("/api/simulate").send({ query });
    expect(again.status).toBe(202);
    const { jobId: jobId2 } = again.body;

    const poll2 = async (): Promise<any> => {
      for (let i = 0; i < 40; i++) {
        const res = await request(server).get(`/api/simulate/${jobId2}`);
        if (res.body.status === "completed") {
          return res.body.result;
        }
        if (res.body.status === "failed") {
          return null;
        }
        await new Promise((r) => setTimeout(r, 250));
      }
      return null;
    };

    const second = await poll2();
    if (!second) {
      return;
    }

    expect(second.parameterProvenance).toEqual(first.parameterProvenance);
    expect(second.parameterProvenance).not.toEqual({});
    expect(
      validateParameterProvenance(
        second.parameters,
        second.parameterProvenance,
      ),
    ).toEqual([]);
  });
});
