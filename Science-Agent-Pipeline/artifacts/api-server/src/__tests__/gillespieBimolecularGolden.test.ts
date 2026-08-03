import { describe, expect, it } from "vitest";

import { runTellurium } from "../lib/telluriumRunner";
import { resolveQuery } from "../lib/queryResolver";

// The bimolecular SSA golden (Stage 7): seed 12345, a0=60, b0=40, k=0.01,
// end=5.0. Pinned in Python in
// Tellurium/tests/test_gillespie_ssa_bimolecular_golden.py; this pins the
// SAME trajectory through the real runner boundary.
const GOLDEN = {
  rows: 38,
  firstEventTime: 0.06172192003509486,
  final: { time: 5, a: 24, b: 4, c: 36 },
};

describe("Bimolecular SSA golden through the runner boundary", () => {
  it("reproduces the pinned seeded trajectory", async () => {
    const res = await runTellurium("gillespie_ssa_bimolecular", {
      a0: 60,
      b0: 40,
      k: 0.01,
      end: 5,
      seed: 12345,
    });

    expect(res.ok).toBe(true);
    expect(res.domain).toBe("gillespie_ssa_bimolecular");
    expect(res.trajectory).toHaveLength(GOLDEN.rows);
    expect(res.trajectory[0]).toEqual({ time: 0, a: 60, b: 40, c: 0 });
    expect(res.trajectory[1].time).toBe(GOLDEN.firstEventTime);
    expect(res.trajectory[1]).toEqual({
      time: GOLDEN.firstEventTime,
      a: 59,
      b: 39,
      c: 1,
    });
    expect(res.trajectory[res.trajectory.length - 1]).toEqual(GOLDEN.final);
    expect(res.flagged).toBe(false);
    expect(res.flagReason).toBeNull();
  });

  it("rejects an over-budget initial population before simulating", async () => {
    await expect(
      runTellurium("gillespie_ssa_bimolecular", { a0: 600_000, b0: 500_000 }),
    ).rejects.toThrow(/Tellurium runner exited with code 1/);
  });
});

describe("Bimolecular SSA resolution (Target I-style narrowness)", () => {
  it("resolves to gillespie_ssa_bimolecular with a0/b0/k/end", async () => {
    const resolved = await resolveQuery("bimolecular association reaction");
    expect(resolved.domain).toBe("gillespie_ssa_bimolecular");
    expect(resolved.parameters).toHaveProperty("a0");
    expect(resolved.parameters).toHaveProperty("b0");
    expect(resolved.parameters).toHaveProperty("k");
    expect(resolved.parameters).toHaveProperty("end");
  });

  it("has no literature resolution and no narrowness notes", async () => {
    const resolved = await resolveQuery("bimolecular association reaction");
    for (const [key, prov] of Object.entries(resolved.parameterProvenance)) {
      expect(prov.origin).not.toBe("resolved");
      expect(prov.citation, `${key} must not carry a citation`).toBeUndefined();
      expect(prov.note, `${key} must not carry a note`).toBeUndefined();
    }
  });
});
