/**
 * When compose's reader gives no reading, the API says so, and an inhibitor
 * the query names is not dropped (review of the web fixes, 2026-11-12, live).
 *
 * Live, seven queries at once made the reader time out (120 s), and
 * "acetylcholinesterase inhibited by donepezil in human with 50 nM enzyme"
 * was answered by the older reader as plain Michaelis-Menten: no Ki, no
 * donepezil, and no sentence saying the question had been read another way.
 * The same run sent "... with 50 nM enzyme" to compose whole, and every
 * answer carried "No word of your description ('50 nM') is a substrate".
 *
 * Offline: the stand-in reader has no recorded reading for "... tacrine
 * ...", so it exits 1 (as a reader that failed), and the runner is mocked.
 * It does have one for the donepezil sentence without "with 50 nM enzyme":
 * the last test is that the reader is sent the sentence without it.
 */
import path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resolveQuery } from "../lib/queryResolver";
import { resolveKineticValue } from "../lib/scienceAgent";
import { textForReader } from "../lib/sentenceReader";

vi.mock("../lib/scienceAgent", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/scienceAgent")>();
  return {
    ...original,
    resolveKineticValue: vi.fn(async () => ({
      found: true,
      km: 0.11,
      ki: 0.00002,
      unit: "mM",
      organism: "Homo sapiens",
      source: "brenda_exact",
      citation: { source: "BRENDA", referenceId: "749746", url: "https://www.brenda-enzymes.org/" },
      literatureCandidates: [],
      logs: [],
    })),
  };
});

const here = path.dirname(fileURLToPath(import.meta.url));
const STANDIN = path.join(here, "fixtures", "sentence_reader_standin.py");
const mocked = vi.mocked(resolveKineticValue);

const outcome = async (query: string) => {
  try {
    const r = await resolveQuery(query);
    return { domain: r.domain as string, flags: r.provenance.flags };
  } catch (err) {
    const e = err as { flags?: string[]; domain?: string; message?: string };
    return { domain: e.domain ?? String(e.message), flags: e.flags ?? [] };
  }
};

describe("a reader that gave no reading", () => {
  beforeEach(() => {
    vi.stubEnv("CATERVA_SENTENCE_READER", STANDIN);
    mocked.mockClear();
  });
  afterEach(() => vi.unstubAllEnvs());

  it("is said, not answered around in silence", async () => {
    const { flags } = await outcome("acetylcholinesterase inhibited by tacrine in human with 50 nM enzyme");
    const said = flags.find((f) => f.startsWith("read: compose's sentence reader gave no reading"));
    expect(said).toBeDefined();
    expect(said).toMatch(/older reader/);
  });

  it("keeps the inhibitor's shape, and looks nothing up for another reader's reading", async () => {
    // Fourth round of the real-values review: the older reader answered
    // "alcohol dehydrogenase from horse liver" with a human Km. A reading
    // compose did not give is now a refusal to look values up, said on each
    // constant; the shape still keeps the inhibitor the query names.
    const { flags } = await outcome("acetylcholinesterase inhibited by tacrine in human with 50 nM enzyme");
    expect(flags.some((f) => f.startsWith("read as: competitive inhibition by tacrine"))).toBe(true);
    expect(mocked.mock.calls.length).toBe(0);
    await expect(resolveQuery("acetylcholinesterase inhibited by tacrine in human with 50 nM enzyme"))
      .rejects.toThrow(/ki: Nothing was looked up: compose's sentence reader gave no reading/);
  });

  it("is silent when the reader is off (the test configuration's older reader)", async () => {
    vi.stubEnv("CATERVA_SENTENCE_READER", "off");
    const { flags } = await outcome("hexokinase with glucose in human with 50 nM enzyme");
    expect(flags.some((f) => f.includes("sentence reader gave no reading"))).toBe(false);
  });
});

describe("the text compose is asked to read", () => {
  beforeEach(() => {
    vi.stubEnv("CATERVA_SENTENCE_READER", STANDIN);
    mocked.mockClear();
  });
  afterEach(() => vi.unstubAllEnvs());

  it("is the sentence without the enzyme concentration: compose's reading is used", async () => {
    const { domain, flags } = await outcome("acetylcholinesterase inhibited by donepezil in human with 50 nM enzyme");
    expect(domain).toBe("mm_competitive_inhibition");
    expect(flags).toContain("read: Read 'donepezil' in your description as the inhibitor.");
    expect(flags.some((f) => f.includes("'50 nM'") || f.includes("sentence reader gave no reading"))).toBe(false);
  });

  it.each([
    ["hexokinase Michaelis-Menten kinetics with 50 nM enzyme", "hexokinase Michaelis-Menten kinetics"],
    ["acetylcholinesterase inhibited by donepezil in human with 50 nM enzyme", "acetylcholinesterase inhibited by donepezil in human"],
    ["xanthine oxidase at 1.5 uM enzyme, inhibited by allopurinol", "xanthine oxidase, inhibited by allopurinol"],
    ["hexokinase with glucose km=0.1 enzyme_conc=0.00005", "hexokinase with glucose"],
    ["hexokinase with glucose and the enzyme at 50 nM", "hexokinase with glucose"],
  ])("%s -> %s", (query, read) => {
    expect(textForReader(query)).toBe(read);
  });

  it.each([
    // A substrate's concentration names the substrate: left in.
    "hexokinase with 50 nM enzyme and 10 mM glucose",
    // An enzyme whose name ends in "enzyme" keeps it.
    "angiotensin-converting enzyme at 50 nM inhibited by captopril",
  ])("keeps what names the system: %s", (query) => {
    const read = textForReader(query);
    expect(read).toContain(query.includes("glucose") ? "10 mM glucose" : "angiotensin-converting enzyme");
  });
});
