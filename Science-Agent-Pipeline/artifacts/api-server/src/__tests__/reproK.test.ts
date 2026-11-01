import { describe, it, expect } from "vitest";
import { extractParameterOverrides } from "../lib/queryResolver";
describe("repro", () => {
  it("shows the leak", () => {
    for (const q of [
      "gillespie decay of CDK1 a0=100 end=10 seed=1",
      "gillespie decay of ERK2 a0=100 end=10 seed=1",
      "simulate backend2 gillespie a0=10",
      "gillespie decay of protein a0=100 end=10 seed=1",
    ]) console.log(q, "->", JSON.stringify(extractParameterOverrides(q)));
  });
});
