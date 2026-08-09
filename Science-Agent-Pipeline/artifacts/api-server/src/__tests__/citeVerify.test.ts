import { describe, expect, it } from "vitest";

import {
  buildCitationLocators,
  citationConsistentWithLocators,
  isValidLocator,
  locatorsFromCitationString,
  primaryDeepLink,
  verificationFor,
} from "../lib/citeVerify";

describe("buildCitationLocators", () => {
  it("BRENDA citation: ref id + enzyme page -> brenda_ref and brenda_ec", () => {
    const locators = buildCitationLocators({
      source: "BRENDA",
      referenceId: "740253",
      url: "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
    });
    expect(locators).toContainEqual({
      kind: "brenda_ref",
      value: "740253",
    });
    expect(locators).toContainEqual({
      kind: "brenda_ec",
      value: "1.1.1.27",
      deepLink: "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
    });
  });

  it("brenda_ref never carries a deep link (per-ref links are broken)", () => {
    const locators = buildCitationLocators({
      source: "BRENDA",
      referenceId: "740253",
      url: "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
    });
    const ref = locators.find((l) => l.kind === "brenda_ref");
    expect(ref?.deepLink).toBeUndefined();
  });

  it("a numeric ref id with no EC number still yields a brenda_ref (id, not a fake link)", () => {
    const locators = buildCitationLocators({
      source: "BRENDA",
      referenceId: "740253",
    });
    expect(locators).toEqual([{ kind: "brenda_ref", value: "740253" }]);
  });

  it("a PMID url yields a pubmed locator", () => {
    const locators = buildCitationLocators({
      source: "PubMed",
      referenceId: "34962677",
      url: "https://pubmed.ncbi.nlm.nih.gov/34962677/",
    });
    expect(locators).toContainEqual({
      kind: "pubmed",
      value: "34962677",
      deepLink: "https://pubmed.ncbi.nlm.nih.gov/34962677/",
    });
  });

  it("a numeric ref id under a non-BRENDA source is treated as a PMID", () => {
    const locators = buildCitationLocators({
      source: "PubMed",
      referenceId: "34962677",
    });
    expect(locators).toContainEqual({
      kind: "pubmed",
      value: "34962677",
      deepLink: "https://pubmed.ncbi.nlm.nih.gov/34962677/",
    });
  });

  it("a DOI (bare or from a doi.org url) yields a doi locator", () => {
    const bare = buildCitationLocators({
      source: "stdpopsim",
      referenceId: "10.1038/ng.3141",
    });
    expect(bare).toContainEqual({
      kind: "doi",
      value: "10.1038/ng.3141",
      deepLink: "https://doi.org/10.1038/ng.3141",
    });

    const fromUrl = buildCitationLocators({
      source: "stdpopsim",
      referenceId: "10.1038/ng.3141",
      url: "https://doi.org/10.1038/ng.3141",
    });
    expect(fromUrl).toContainEqual({
      kind: "doi",
      value: "10.1038/ng.3141",
      deepLink: "https://doi.org/10.1038/ng.3141",
    });
  });

  it("the 'n/a' placeholder produces no locator (Stage 5 Part 1)", () => {
    expect(
      buildCitationLocators({ source: "BRENDA", referenceId: "n/a" }),
    ).toEqual([]);
    expect(
      buildCitationLocators({ source: "BRENDA", referenceId: null, url: null }),
    ).toEqual([]);
  });

  it("deduplicates a ref id that is also carried by its url", () => {
    const locators = buildCitationLocators({
      source: "BRENDA",
      referenceId: "1.1.1.27",
      url: "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
    });
    const ecCount = locators.filter((l) => l.kind === "brenda_ec").length;
    expect(ecCount).toBe(1);
  });
});

describe("locatorsFromCitationString", () => {
  it("round-trips a display citation string", () => {
    const locators = locatorsFromCitationString(
      "BRENDA (ref 740253) — https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
    );
    expect(locators).toContainEqual({ kind: "brenda_ref", value: "740253" });
    expect(locators).toContainEqual({
      kind: "brenda_ec",
      value: "1.1.1.27",
      deepLink: "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
    });
  });

  it("a doi.org url in the string is recovered as a doi locator", () => {
    const locators = locatorsFromCitationString(
      "stdpopsim (ref 10.1038/ng.3141) — https://doi.org/10.1038/ng.3141",
    );
    expect(locators).toContainEqual({
      kind: "doi",
      value: "10.1038/ng.3141",
      deepLink: "https://doi.org/10.1038/ng.3141",
    });
  });
});

describe("isValidLocator / verificationFor / primaryDeepLink", () => {
  it("validates locator shape", () => {
    expect(isValidLocator({ kind: "brenda_ref", value: "740253" })).toBe(true);
    expect(
      isValidLocator({ kind: "brenda_ec", value: "1.1.1.27", deepLink: "ftp://x" }),
    ).toBe(false);
    expect(
      isValidLocator({ kind: "nonsense" as never, value: "x" }),
    ).toBe(false);
  });

  it("verification is locator_valid when at least one well-formed locator exists", () => {
    expect(
      verificationFor([{ kind: "brenda_ref", value: "740253" }]),
    ).toBe("locator_valid");
    expect(verificationFor([])).toBe("unresolvable");
  });

  it("primaryDeepLink prefers the working BRENDA enzyme page", () => {
    expect(
      primaryDeepLink([
        { kind: "brenda_ref", value: "740253" },
        {
          kind: "brenda_ec",
          value: "1.1.1.27",
          deepLink: "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
        },
      ]),
    ).toBe("https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27");
  });

  it("primaryDeepLink is undefined for a bare brenda_ref", () => {
    expect(primaryDeepLink([{ kind: "brenda_ref", value: "740253" }])).toBeUndefined();
  });
});

describe("citationConsistentWithLocators", () => {
  it("accepts locators justified by the ref id and url in the string", () => {
    const citation =
      "BRENDA (ref 740253) — https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27";
    const locators = buildCitationLocators({
      source: "BRENDA",
      referenceId: "740253",
      url: "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
    });
    expect(citationConsistentWithLocators(citation, locators)).toBe(true);
  });

  it("rejects a locator with no counterpart in the citation string", () => {
    const locators = [
      { kind: "brenda_ref" as const, value: "740253" },
      { kind: "brenda_ref" as const, value: "999999" },
    ];
    expect(
      citationConsistentWithLocators("BRENDA (ref 740253)", locators),
    ).toBe(false);
  });
});
