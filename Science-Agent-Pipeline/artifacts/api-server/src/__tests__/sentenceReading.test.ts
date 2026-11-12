/**
 * The API reads a sentence the way `caterva compose` does (sentenceReader.ts).
 *
 * Each query here was misread by the API's own reader in the adversarial
 * round of 2026-11-11, while compose and Studio read it right:
 *
 * - "chymotrypsin follows Michaelis-Menten kinetics" became trypsin, EC
 *   3.4.21.4, with a trypsin substrate's Km;
 * - "hexokinase Michaelis-Menten kinetics" asked for the Km of a substrate
 *   called "michaelis-menten kinetics" and refused;
 * - "competitive inhibition of xanthine oxidase by allopurinol" carried the
 *   Km of allopurinol AS A SUBSTRATE, in human, with no Ki;
 * - "xanthine oxidase inhibited by allopurinol" was refused as unrecognised;
 * - "HK2 with glucose" dropped the isoform;
 * - "acetylcholinesterase inhibited by donepezil in human" read the
 *   inhibitor clause as the substrate;
 * - no organism named was "assumed: Homo sapiens", never a stated choice.
 *
 * Offline: the reader is a stand-in answering with what the real one
 * printed for the same sentence against live BRENDA
 * (fixtures/sentence_readings.json), and the runner is mocked. The tests
 * are of what the API sends and says, given compose's reading.
 */
import path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { matchEnzyme } from "../lib/enzymes";
import { resolveQuery } from "../lib/queryResolver";
import { resolveKineticValue } from "../lib/scienceAgent";
import { parseReading } from "../lib/sentenceReader";

vi.mock("../lib/scienceAgent", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/scienceAgent")>();
  return {
    ...original,
    resolveKineticValue: vi.fn(async () => ({
      found: true,
      km: 0.0167,
      ki: 0.0018,
      unit: "mM",
      organism: "Bos taurus",
      source: "brenda_exact",
      citation: { source: "BRENDA", referenceId: "766313", url: "https://www.brenda-enzymes.org/" },
      literatureCandidates: [],
      logs: [],
    })),
  };
});

const here = path.dirname(fileURLToPath(import.meta.url));
const STANDIN = path.join(here, "fixtures", "sentence_reader_standin.py");

type Sent = {
  quantity: string;
  ecNumber?: string;
  enzymeName?: string;
  substrate?: string;
  organism: string;
  isoform?: string;
  inhibitionMode?: string;
};

const mocked = vi.mocked(resolveKineticValue);
const sent = () => mocked.mock.calls.map(([arg]) => arg as unknown as Sent);
const flagsOf = async (query: string): Promise<string[]> => {
  try {
    return (await resolveQuery(query)).provenance.flags;
  } catch (err) {
    return ((err as { flags?: string[] }).flags ?? []) as string[];
  }
};

describe("compose's reading is the API's reading", () => {
  beforeEach(() => {
    vi.stubEnv("CATERVA_SENTENCE_READER", STANDIN);
    mocked.mockClear();
  });
  afterEach(() => vi.unstubAllEnvs());

  it("reads chymotrypsin as chymotrypsin, EC 3.4.21.1", async () => {
    await flagsOf("chymotrypsin follows Michaelis-Menten kinetics");
    const calls = sent();
    expect(calls.length).toBeGreaterThan(0);
    expect(calls.every((c) => c.ecNumber === "3.4.21.1")).toBe(true);
    expect(calls[0]!.substrate).toBe("L-alanyl-L-alanyl-L-prolyl-L-phenylalanine p-nitroanilide");
  });

  it("never sends 'Michaelis-Menten' as the substrate, and states the substrate it chose", async () => {
    const flags = await flagsOf("hexokinase Michaelis-Menten kinetics");
    const km = sent().find((c) => c.quantity === "km")!;
    expect(km.substrate).toBe("D-glucose");
    expect(flags.some((f) => f.startsWith("substrate chosen: D-glucose -- "))).toBe(true);
  });

  it("models allopurinol as the inhibitor, in the organism with its Ki, said as a choice", async () => {
    for (const query of [
      "competitive inhibition of xanthine oxidase by allopurinol",
      "xanthine oxidase inhibited by allopurinol",
    ]) {
      mocked.mockClear();
      const flags = await flagsOf(query);
      const calls = sent();
      const km = calls.find((c) => c.quantity === "km")!;
      const ki = calls.find((c) => c.quantity === "ki")!;
      expect(km.substrate).toBe("xanthine");
      expect(ki.substrate).toBe("allopurinol");
      // The Ki is looked up at all only in the competitive domain.
      expect(ki.inhibitionMode).toBe("competitive");
      expect(calls.every((c) => c.organism === "Bos taurus")).toBe(true);
      const organism = flags.find((f) => f.startsWith("organism chosen: Bos taurus -- "));
      expect(organism).toMatch(/Ki for allopurinol/);
      expect(organism).toMatch(/Alternatives: /);
      expect(flags.some((f) => f.startsWith("assumed: organism"))).toBe(false);
    }
  });

  it("sends HK2 as the isoform, and says how it read it", async () => {
    const flags = await flagsOf("HK2 with glucose");
    const calls = sent();
    expect(calls.length).toBeGreaterThan(0);
    expect(calls.every((c) => c.isoform === "HK2" && c.ecNumber === "2.7.1.1")).toBe(true);
    expect(flags.some((f) => f.startsWith("read: ") && f.includes("HK2"))).toBe(true);
  });

  it("reads the donepezil clause as the inhibitor, not the substrate", async () => {
    await flagsOf("acetylcholinesterase inhibited by donepezil in human");
    const calls = sent();
    expect(calls.find((c) => c.quantity === "km")!.substrate).toBe("acetylthiocholine");
    expect(calls.find((c) => c.quantity === "ki")!.substrate).toBe("donepezil");
  });

  it("takes the lactate dehydrogenase BRENDA's rows single out, and says so", async () => {
    const flags = await flagsOf("lactate dehydrogenase with pyruvate in human");
    expect(sent().every((c) => c.ecNumber === "1.1.1.27")).toBe(true);
    expect(flags.some((f) => f.startsWith("enzyme chosen: 1.1.1.27 -- "))).toBe(true);
  });

  it("does not say 'using defaults' on a response whose Km was resolved", async () => {
    const flags = await flagsOf("hexokinase kinetics");
    expect(flags.some((f) => f.startsWith("Resolved KM="))).toBe(true);
    expect(flags.join("\n")).not.toMatch(/using defaults/);
  });
});

describe("the older reader, used when compose's is unavailable", () => {
  beforeEach(() => {
    vi.stubEnv("CATERVA_SENTENCE_READER", "off");
    mocked.mockClear();
  });
  afterEach(() => vi.unstubAllEnvs());

  it("matches a name only as whole words: chymotrypsin is not trypsin", () => {
    expect(matchEnzyme("chymotrypsin follows Michaelis-Menten kinetics")?.ecNumber).toBe("3.4.21.1");
    expect(matchEnzyme("trypsin with casein")?.ecNumber).toBe("3.4.21.4");
    expect(matchEnzyme("a headache in an episode")).toBeUndefined();
  });

  it.each([
    "hexokinase Michaelis-Menten kinetics",
    "hexokinase Michaelis Menten kinetics",
    "fumarase Michaelis-Menten kinetics",
    "chymotrypsin follows Michaelis-Menten kinetics",
  ])("reads no substrate from the model's name: %j", async (query) => {
    await flagsOf(query);
    const km = sent().find((c) => c.quantity === "km");
    expect(km).toBeDefined();
    expect(km!.substrate ?? "").not.toMatch(/michaelis|menten|kinetic|follows/i);
  });

  it("never sends the inhibitor as the Km's substrate", async () => {
    await flagsOf("competitive inhibition of xanthine oxidase by allopurinol");
    const km = sent().find((c) => c.quantity === "km");
    expect(km).toBeDefined();
    expect(km!.substrate ?? "").not.toMatch(/allopurinol/i);
    await flagsOf("acetylcholinesterase inhibited by donepezil in human");
    const km2 = sent().filter((c) => c.quantity === "km").pop();
    expect(km2!.substrate ?? "").not.toMatch(/donepezil|inhibited/i);
  });
});

describe("parseReading", () => {
  it("is null for an error or non-JSON", () => {
    expect(parseReading('{"error": "boom"}')).toBeNull();
    expect(parseReading("Traceback")).toBeNull();
  });
});
