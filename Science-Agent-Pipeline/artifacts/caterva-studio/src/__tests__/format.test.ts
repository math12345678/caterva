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

  it("writes plain decimals from 1e-4 up to 1e6, so 0.00059 mM is never read as 5.9e-4", () => {
    expect(formatNumber(0.00059)).toBe("0.00059");
    expect(formatNumber(0.00012)).toBe("0.00012");
    expect(formatNumber(0.0001)).toBe("0.0001");
    expect(formatNumber(-0.00059)).toBe("-0.00059");
    expect(formatNumber(123456)).toBe("123500");
    expect(formatNumber(99999.5)).toBe("100000");
    expect(formatNumber(1234567 / 10)).toBe("123500");
  });

  it("switches to exponent form only outside 1e-4 to 1e6", () => {
    expect(formatNumber(0.0000999)).toBe("9.99e-5");
    expect(formatNumber(4.6e-18)).toBe("4.6e-18");
    expect(formatNumber(8353000.565)).toBe("8.353e6");
    expect(formatNumber(1e6)).toBe("1e6");
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
