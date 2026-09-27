import { describe, expect, it } from "vitest";

import { runCaterva } from "../lib/catervaRunner";
import { resolveQuery } from "../lib/queryResolver";

// The SSA golden (Stage 6 Part 2): seed 12345, a0=100, k=0.5, end=3.0.
// Pinned in Python in caterva/tests/test_gillespie_ssa_golden.py; this
// file pins the SAME trajectory through the real runner boundary so a
// drift between engine and bridge (or a changed engine) breaks here too.
const GOLDEN = {
  rows: 78,
  firstEventTime: 0.029626521616845532,
  secondEventTime: 0.052851089922515,
  final: { time: 3, a: 24, b: 76 },
};

describe("Gillespie SSA golden through the runner boundary", () => {
  it("reproduces the pinned seeded trajectory", async () => {
    const res = await runCaterva("gillespie_ssa", {
      a0: 100,
      k: 0.5,
      end: 3,
      seed: 12345,
    });

    expect(res.ok).toBe(true);
    expect(res.domain).toBe("gillespie_ssa");
    expect(res.trajectory).toHaveLength(GOLDEN.rows);
    expect(res.trajectory[0]).toEqual({ time: 0, a: 100, b: 0 });
    expect(res.trajectory[1].time).toBe(GOLDEN.firstEventTime);
    expect(res.trajectory[1].a).toBe(99);
    expect(res.trajectory[2].time).toBe(GOLDEN.secondEventTime);
    expect(res.trajectory[res.trajectory.length - 1]).toEqual(GOLDEN.final);
    expect(res.flagged).toBe(false);
    expect(res.flagReason).toBeNull();
  });

  it("reports the seeded parameters back", async () => {
    const res = await runCaterva("gillespie_ssa", {
      a0: 50,
      k: 1,
      end: 2,
      seed: 7,
    });
    expect(res.parameters).toMatchObject({ a0: 50, k: 1, end: 2, seed: 7 });
  });
});

describe("Gillespie SSA resolution (Target I-style narrowness)", () => {
  it("resolves to gillespie_ssa with a0/k/end", async () => {
    const resolved = await resolveQuery(
      "gillespie stochastic decay of molecules a0=1000 k=0.5 end=10",
    );
    expect(resolved.domain).toBe("gillespie_ssa");
    expect(resolved.parameters).toHaveProperty("a0");
    expect(resolved.parameters).toHaveProperty("k");
    expect(resolved.parameters).toHaveProperty("end");
  });

  it("forwards a numeric seed override into resolved parameters", async () => {
    const resolved = await resolveQuery(
      "gillespie stochastic decay a0=200 k=0.5 end=5 seed=9",
    );
    expect(resolved.domain).toBe("gillespie_ssa");
    expect(resolved.parameters.seed).toBe(9);
    expect(resolved.parameterProvenance.seed).toEqual({ origin: "user" });
  });

  it("has no literature resolution and no narrowness notes", async () => {
    const resolved = await resolveQuery(
      "gillespie stochastic decay of molecules a0=1000 k=0.5 end=10",
    );
    const entries = Object.entries(resolved.parameterProvenance);
    expect(entries.length).toBeGreaterThan(0);

    for (const [key, prov] of entries) {
      // No parameter may claim a literature resolution: gillespie_ssa is
      // deliberately outside RESOLVABLE_FIELDS (Stage 5 Part 5 narrowness).
      expect(prov.origin).not.toBe("resolved");
      expect(prov.citation, `${key} must not carry a citation`).toBeUndefined();
      // And because the domain has no lookup at all, no "No literature
      // lookup exists" notes either (unlike mm, where defaults carry them).
      expect(prov.note, `${key} must not carry a note`).toBeUndefined();
    }
  });
});
