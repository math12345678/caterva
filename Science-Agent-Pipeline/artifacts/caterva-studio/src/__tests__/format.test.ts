import { describe, expect, it } from "vitest";

import fixture from "@/__fixtures__/api/contract/michaelis-menten-parameters.json";
import type { SourcedValue } from "@/api/types";
import { formatNumber, formatValue, fullValue } from "@/lib/format";

describe("formatNumber", () => {
  it("keeps four significant figures and drops zeros the value does not have", () => {
    expect(formatNumber(40.1)).toBe("40.1");
    expect(formatNumber(6)).toBe("6");
    expect(formatNumber(0.03)).toBe("0.03");
    expect(formatNumber(1.23456)).toBe("1.235");
  });

  it("switches to exponent form outside 1e-3 to 1e5", () => {
    expect(formatNumber(0.00059)).toBe("5.9e-4");
    expect(formatNumber(8353000.565)).toBe("8.353e6");
  });
});

describe("a SourcedValue from the real contract fixture", () => {
  const values = fixture.searched.parameters as SourcedValue[];

  it("draws the measured Km as the CLI's report does, and keeps the full value", () => {
    const km = values.find((v) => v.id === "reaction_Km");
    expect(km).toBeDefined();
    expect(formatValue(km!)).toBe("6");
    expect(fullValue(km!)).toBe("6");
    expect(km!.provenance.citation?.text).toBe("BRENDA ref 641068");
  });
});
