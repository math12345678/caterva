import { describe, expect, it } from "vitest";

import { runCaterva } from "../lib/catervaRunner";
import { resolveQuery } from "../lib/queryResolver";

// The bimolecular SSA golden (Stage 7): seed 12345, a0=60, b0=40, k=0.01,
// end=5.0. Pinned in Python in
// caterva/tests/test_gillespie_ssa_bimolecular_golden.py; this pins the
// SAME trajectory through the real runner boundary.
const GOLDEN = {
  rows: 38,
  firstEventTime: 0.06172192003509486,
  final: { time: 5, a: 24, b: 4, c: 36 },
};

describe("Bimolecular SSA golden through the runner boundary", () => {
  it("reproduces the pinned seeded trajectory", async () => {
    const res = await runCaterva("gillespie_ssa_bimolecular", {
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

  // This asserted /Caterva runner exited with code 1/ and passed for as long
  // as the boundary threw the engine's explanation away. The engine has
  // always written "a0+b0=1100000 exceeds API runtime ceiling
  // (MAX_API_SSA_POPULATION) 1000000" to stdout; runCaterva checked the exit
  // status first and rejected with the status instead. Pinning the exit code
  // made the information loss look like the specification.
  //
  // The assertion is on the ceiling's name and the offending total, because
  // those are what a user needs to act: which limit, and by how much.
  // ONE spawn, two assertions about the SAME error.
  //
  // This used to call runCaterva twice, once per regex. That doubled the
  // cost of the most expensive test in the file -- each call spawns a
  // Python interpreter -- and under shard contention the pair exceeded
  // vitest's default 5s timeout and failed. Passing alone and failing in
  // parallel is the worst failure mode a suite can have: it teaches people
  // to re-run rather than investigate.
  //
  // It was also weaker as a test. Two spawns assert that two SEPARATE
  // errors each match one pattern, which quietly assumes the two runs
  // produced the same error. Capturing one error and asserting both
  // properties of it is what the test meant to say.
  //
  // The explicit timeout is generous rather than tuned: a slow machine
  // should report "too slow" rather than something that reads like a
  // behaviour change.
  it(
    "rejects an over-budget initial population before simulating, and says why",
    async () => {
      const error = await runCaterva("gillespie_ssa_bimolecular", {
        a0: 600_000,
        b0: 500_000,
      }).then(
        () => {
          throw new Error(
            "expected the runner to reject an over-budget population, but it resolved",
          );
        },
        (err: unknown) => err as Error,
      );

      // Which limit, and by how much -- the two things a user needs to act.
      expect(error.message).toMatch(/MAX_API_SSA_POPULATION/);
      expect(error.message).toMatch(/1100000/);
    },
    30_000,
  );
});

describe("Bimolecular SSA resolution (Target I-style narrowness)", () => {
  it("resolves to gillespie_ssa_bimolecular with a0/b0/k/end", async () => {
    const resolved = await resolveQuery(
      "bimolecular association reaction a0=100 b0=100 k=0.005 end=10",
    );
    expect(resolved.domain).toBe("gillespie_ssa_bimolecular");
    expect(resolved.parameters).toHaveProperty("a0");
    expect(resolved.parameters).toHaveProperty("b0");
    expect(resolved.parameters).toHaveProperty("k");
    expect(resolved.parameters).toHaveProperty("end");
  });

  it("has no literature resolution and no narrowness notes", async () => {
    const resolved = await resolveQuery(
      "bimolecular association reaction a0=100 b0=100 k=0.005 end=10",
    );
    for (const [key, prov] of Object.entries(resolved.parameterProvenance)) {
      expect(prov.origin).not.toBe("resolved");
      expect(prov.citation, `${key} must not carry a citation`).toBeUndefined();
      expect(prov.note, `${key} must not carry a note`).toBeUndefined();
    }
  });
});
