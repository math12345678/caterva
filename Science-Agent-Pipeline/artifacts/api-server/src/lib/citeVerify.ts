/**
 * citeVerify.ts
 *
 * Machine-checkable citation evidence for resolved parameter values.
 *
 * A `resolved` provenance entry carries a display citation string such as
 *
 *   "BRENDA (ref 740253) — https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27"
 *
 * That string is *locatable* (Stage 5 Part 1) but not machine-checkable: a
 * consumer has to parse it, and a test cannot assert the locator's shape.
 * This module turns a citation into structured locators — `(kind, value,
 * deepLink)` triples — so a human or a tool can re-find the exact source of
 * a number with one click, and a validation rule can hold every resolved
 * citation to a verifiable shape.
 *
 * Deep-link reality (live-checked 2026-07; see Tests/citation.py):
 * BRENDA has NO working per-reference deep link. `literature.php?refid=...`
 * returns the identical generic template for every id, so that pattern must
 * never be presented as a real citation link. The only confirmed-working
 * page that genuinely carries a reference is the parent enzyme page
 * (`enzyme.php?ecno=...`). Therefore a `brenda_ref` locator carries the
 * reference id WITHOUT a deep link, and — when an EC number is known — the
 * deep link lives on a separate `brenda_ec` locator. No citation URL is
 * better than a fake one.
 */

export type CitationLocatorKind =
  | "brenda_ref" // BRENDA reference id (no deep link; per-ref links are broken)
  | "brenda_ec" // BRENDA enzyme page (enzyme.php?ecno=...)
  | "pubmed" // PubMed PMID
  | "doi" // DOI, deep-linked via doi.org
  | "url"; // any other http(s) URL

export const CITATION_LOCATOR_KINDS: ReadonlySet<CitationLocatorKind> =
  new Set(["brenda_ref", "brenda_ec", "pubmed", "doi", "url"]);

export interface CitationLocator {
  /** What kind of locator this is. */
  kind: CitationLocatorKind;
  /** The locator's value: a BRENDA ref id, EC number, PMID, DOI, or URL. */
  value: string;
  /**
   * Canonical URL that re-finds this locator, when one exists. Absent for
   * `brenda_ref` because BRENDA has no working per-reference deep link.
   */
  deepLink?: string;
}

export type CitationVerification = "locator_valid" | "unresolvable";

/** A citation as produced by the science agent (ScienceAgentResult.citation). */
export interface StructuredCitation {
  source?: string;
  referenceId?: string | null;
  url?: string | null;
}

const BRENDA_ENZYME_URL_RE =
  /^https?:\/\/www\.brenda-enzymes\.org\/enzyme\.php\?.*ecno=([0-9.]+)/;
const PUBMED_URL_RE =
  /^https?:\/\/pubmed\.ncbi\.nlm\.nih\.gov\/(\d+)\/?/;
const DOI_URL_RE = /^https?:\/\/(?:doi\.org|dx\.doi\.org)\/(10\.[^\s/?#]+)/;
const DOI_RE = /^10\.\d{4,9}\/[-._;()/:A-Z0-9]+$/i;
const NUMERIC_RE = /^\d+$/;

function doiFromUrl(url: string): string | undefined {
  return url.match(DOI_URL_RE)?.[1];
}

/**
 * Helper to add a locator to a set, deduplicating on (kind, value).
 */
function addLocator(
  locators: CitationLocator[],
  locator: CitationLocator,
): void {
  if (
    !locators.some(
      (existing) =>
        existing.kind === locator.kind && existing.value === locator.value,
    )
  ) {
    locators.push(locator);
  }
}

/**
 * Build the machine-checkable locators for a structured citation.
 *
 * Order of preference when a URL carries several signals: a BRENDA enzyme
 * URL yields a `brenda_ec` locator; a PubMed URL yields a `pubmed` locator;
 * a doi.org URL yields a `doi` locator; anything else http(s) is a generic
 * `url` locator. A reference id adds its own locator: a DOI id becomes a
 * `doi` locator, a numeric id under a BRENDA source becomes `brenda_ref`,
 * and a numeric id under any other source is treated as a PMID.
 */
export function buildCitationLocators(
  citation?: StructuredCitation,
): CitationLocator[] {
  if (!citation) return [];

  const locators: CitationLocator[] = [];

  const url = citation.url ?? undefined;
  if (url) {
    // Try BRENDA enzyme page first (highest precedence)
    const ecMatch = url.match(BRENDA_ENZYME_URL_RE);
    if (ecMatch) {
      addLocator(locators, {
        kind: "brenda_ec",
        value: ecMatch[1]!,
        deepLink: url,
      });
    } else {
      // Then PubMed
      const pmidMatch = url.match(PUBMED_URL_RE);
      if (pmidMatch) {
        addLocator(locators, {
          kind: "pubmed",
          value: pmidMatch[1]!,
          deepLink: url,
        });
      } else {
        // Then DOI
        const doi = doiFromUrl(url);
        if (doi) {
          addLocator(locators, { kind: "doi", value: doi, deepLink: url });
        } else if (/^https?:\/\//.test(url)) {
          // Finally generic URL
          addLocator(locators, { kind: "url", value: url, deepLink: url });
        }
      }
    }
  }

  const refId = citation.referenceId ?? undefined;
  if (refId !== undefined && refId !== "" && refId !== "n/a") {
    if (DOI_RE.test(refId)) {
      addLocator(locators, {
        kind: "doi",
        value: refId,
        deepLink: `https://doi.org/${refId}`,
      });
    } else if (NUMERIC_RE.test(refId)) {
      const isBrenda = (citation.source ?? "").toLowerCase().includes("brenda");
      if (isBrenda) {
        addLocator(locators, { kind: "brenda_ref", value: refId });
      } else {
        addLocator(locators, {
          kind: "pubmed",
          value: refId,
          deepLink: `https://pubmed.ncbi.nlm.nih.gov/${refId}/`,
        });
      }
    }
  }

  return locators;
}

/**
 * Recover structured locators from a display citation string (e.g. the
 * `citation` field of a provenance entry). The source label, `(ref <id>)`
 * and the first http(s) URL are extracted and re-run through
 * `buildCitationLocators`. Used for validating that a provenance entry's
 * locators match its citation string.
 */
export function locatorsFromCitationString(
  citation: string,
): CitationLocator[] {
  const source = citation.split(/\s+\(ref/)[0]?.trim() || undefined;
  const refMatch = citation.match(/\(ref ([^)]*)\)/);
  const refId = refMatch ? refMatch[1]!.trim() : undefined;
  const urls = citation.match(/https?:\/\/\S+/g);
  return buildCitationLocators({
    source,
    referenceId: refId,
    url: urls?.[0],
  });
}

/** Whether a single locator is well-formed. */
export function isValidLocator(locator: CitationLocator): boolean {
  if (!CITATION_LOCATOR_KINDS.has(locator.kind)) return false;
  if (!locator.value || locator.value.length === 0) return false;
  if (locator.deepLink !== undefined && !/^https?:\/\//.test(locator.deepLink)) {
    return false;
  }
  return true;
}

/**
 * Static verification: at least one well-formed locator exists. "Locator
 * valid" means a human or a tool can act on it — it does not claim the URL
 * resolves (live checks are a separate, opt-in capability).
 */
export function verificationFor(
  locators: CitationLocator[],
): CitationVerification {
  return locators.length > 0 && locators.every(isValidLocator)
    ? "locator_valid"
    : "unresolvable";
}

/**
 * The single best URL to click for a set of locators: the working BRENDA
 * enzyme page first, then PubMed, then the DOI resolver, then any URL.
 * Returns undefined when there is nothing clickable (a bare `brenda_ref`).
 */
export function primaryDeepLink(
  locators: CitationLocator[],
): string | undefined {
  const preference: CitationLocatorKind[] = [
    "brenda_ec",
    "pubmed",
    "doi",
    "url",
    "brenda_ref",
  ];
  for (const kind of preference) {
    const found = locators.find(
      (locator) => locator.kind === kind && locator.deepLink !== undefined,
    );
    if (found?.deepLink) return found.deepLink;
  }
  return undefined;
}

/**
 * Whether the locators are justified by the display citation string they
 * were recorded against. Every locator's value must equal the `(ref <id>)`
 * in the string, or one of the string's URLs must carry the locator (its
 * deepLink or its raw value). This keeps locators from drifting away from
 * the citation a human reads — the ADR Stage 5 Part 4 pairing rule,
 * applied at the citation level.
 */
export function citationConsistentWithLocators(
  citation: string,
  locators: CitationLocator[],
): boolean {
  if (locators.length === 0) return true;
  const refMatch = citation.match(/\(ref ([^)]*)\)/);
  const refId = refMatch ? refMatch[1]!.trim() : undefined;
  const urls: string[] = citation.match(/https?:\/\/\S+/g) ?? [];
  return locators.every((locator) => {
    if (refId !== undefined && locator.value === refId) return true;
    if (locator.deepLink !== undefined && urls.includes(locator.deepLink)) {
      return true;
    }
    return urls.includes(locator.value);
  });
}
