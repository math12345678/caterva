/**
 * A model may propose an EC number, never supply one (ADR 0011).
 *
 * THE DEFECT
 * ----------
 * `SYSTEM_PROMPT` asked the model for an "EC number if known or inferable"
 * and an "organism if mentioned, else Homo sapiens", and `normalizeEntities`
 * forwarded both under the same keys a person's own input travels under. A
 * supplied `ecNumber` makes the runner skip its enzyme finder entirely --
 * the finder that refuses to choose between EC 1.1.1.27 and EC 1.1.1.28 for
 * "lactate dehydrogenase" (ADR 0126/0127). So a model that wrote 1.1.1.27
 * made that choice silently, and every query that named no organism was
 * answered about humans with nothing in the response saying so.
 *
 * ADR 0011's amendment hard-blocked the model's VALUES and kept it
 * "extracting entities". An EC number is not a value; it is the identity of
 * the protein every citation downstream refers to, which is why it slipped
 * through, and why the fix is the rule the ADR already states: the model
 * proposes, the query and the finder decide.
 *
 * THE RULE, IN THREE PLACES
 * -------------------------
 *   llmResolver.parseLLMResponse   keeps an EC number only when the query
 *                                  text contains it; records the drop
 *   queryResolver                  decides the organism once (query wording,
 *                                  then the model's, then the documented
 *                                  default -- reported as an assumption)
 *   science_agent_runner           refuses `ec_mismatch` when a name and a
 *                                  number sent together are two enzymes
 *                                  (Tests/test_science_agent_runner.py)
 *
 * The resolver is driven for real here -- a mocked `fetch` plays the model
 * -- so the prompt and the parse are the ones a deployment uses; only the
 * Python runner is replaced, as llmOrigin.test.ts does.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

import { parseLLMResponse, resolveQueryWithLLM } from "../lib/llmResolver";
import {
  resolveQuery,
  buildUnresolvedKineticProvenanceForTest as build,
} from "../lib/queryResolver";
import { RequiredParametersMissingError } from "../lib/provenance";
import { resolveKineticValue } from "../lib/scienceAgent";

vi.mock("../lib/scienceAgent", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/scienceAgent")>();
  return {
    ...original,
    resolveKineticValue: vi.fn(),
  };
});

const ENV_KEYS = [
  "LLM_PROVIDER",
  "LLM_API_KEY",
  "LLM_API_URL",
  "LLM_MODEL",
  "LLM_FORCE_JSON",
  "OPENAI_API_KEY",
  "OPENAI_API_URL",
  "OPENAI_MODEL",
  "GROQ_API_KEY",
  "OPENROUTER_API_KEY",
  "MISTRAL_API_KEY",
  "SILICONFLOW_API_KEY",
  "TOKENROUTER_API_KEY",
] as const;

let savedEnv: Record<string, string | undefined>;

beforeEach(() => {
  savedEnv = {};
  for (const k of ENV_KEYS) {
    savedEnv[k] = process.env[k];
    delete process.env[k];
  }
  vi.mocked(resolveKineticValue).mockReset();
});

afterEach(() => {
  for (const k of ENV_KEYS) {
    if (savedEnv[k] === undefined) delete process.env[k];
    else process.env[k] = savedEnv[k];
  }
  vi.restoreAllMocks();
});

/** The model's reply, as the configured provider would return it. */
function modelReplies(body: unknown) {
  process.env.OPENAI_API_KEY = "fake-openai-key";
  return vi.spyOn(global, "fetch").mockResolvedValue({
    ok: true,
    json: async () => ({
      choices: [{ message: { content: JSON.stringify(body) } }],
    }),
  } as Response);
}

function reply(entities: Record<string, unknown>) {
  return JSON.stringify({
    domain: "mm",
    parameters: {},
    reasoning: "identified an enzyme-kinetics question",
    modelCitations: [],
    entities,
  });
}

/** The golden G1 record, as the runner emits it (scienceAgent.test.ts). */
const FOUND = {
  found: true,
  km: 10.73,
  unit: "mM",
  organism: "Homo sapiens",
  source: "brenda_exact",
  crossSpecies: false,
  citation: {
    source: "BRENDA",
    referenceId: "740253",
    url: "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
  },
  literatureCandidates: [],
  logs: [],
};

const TAIL = "vmax=5 s0=10 end=10 points=51";

function runnerPayload(): Record<string, unknown> {
  const calls = vi.mocked(resolveKineticValue).mock.calls;
  expect(calls.length).toBeGreaterThan(0);
  return calls[0]![0] as unknown as Record<string, unknown>;
}

describe("parseLLMResponse keeps an EC number only when the query states it", () => {
  it("drops a number the query text does not contain, and says so", () => {
    const resolved = parseLLMResponse(
      reply({ enzymeName: "lactate dehydrogenase", organism: "Homo sapiens", ecNumber: "1.1.1.27" }),
      "simulate lactate dehydrogenase with pyruvate",
    );
    expect(resolved).not.toBeNull();
    expect(resolved!.entities!.ecNumber).toBeUndefined();
    // The name still travels: the finder decides from it.
    expect(resolved!.entities!.enzymeName).toBe("lactate dehydrogenase");
    expect(resolved!.ecNumberDropped).toBe(true);
    expect(resolved!.ecNumberDroppedReason).toContain("1.1.1.27");
    expect(resolved!.ecNumberDroppedReason).toContain("never supply");
  });

  it("keeps a number the query text contains", () => {
    const resolved = parseLLMResponse(
      reply({ enzymeName: "lactate dehydrogenase", ecNumber: "1.1.1.27" }),
      "simulate EC 1.1.1.27 with pyruvate",
    );
    expect(resolved!.entities!.ecNumber).toBe("1.1.1.27");
    expect(resolved!.ecNumberDropped).toBeUndefined();
  });

  it("reads the model's 'EC 1.1.1.27' as 1.1.1.27", () => {
    const resolved = parseLLMResponse(
      reply({ ecNumber: "EC 1.1.1.27" }),
      "simulate 1.1.1.27 with pyruvate",
    );
    expect(resolved!.entities!.ecNumber).toBe("1.1.1.27");
  });

  it("a number inside a longer number is not present in the query", () => {
    // Substring matching would pass 1.1.1.27 against a query about
    // 1.1.1.270. Present means present as a whole EC number.
    const resolved = parseLLMResponse(
      reply({ ecNumber: "1.1.1.27" }),
      "simulate EC 1.1.1.270 with something",
    );
    expect(resolved!.entities!.ecNumber).toBeUndefined();
    expect(resolved!.ecNumberDropped).toBe(true);
  });

  it("something that is not an EC number is not an EC number", () => {
    const resolved = parseLLMResponse(
      reply({ ecNumber: "lactate dehydrogenase" }),
      "simulate lactate dehydrogenase",
    );
    expect(resolved!.entities!.ecNumber).toBeUndefined();
    expect(resolved!.ecNumberDroppedReason).toContain("not one");
  });

  it("applies no organism default: none named is empty, not Homo sapiens", () => {
    for (const organism of [undefined, null, "", "null", "none", "unknown"]) {
      const resolved = parseLLMResponse(
        reply({ enzymeName: "hexokinase", organism }),
        "simulate hexokinase with glucose",
      );
      expect(resolved!.entities!.organism, String(organism)).toBe("");
    }
  });

  it("keeps the organism the model read out of the query", () => {
    const resolved = parseLLMResponse(
      reply({ enzymeName: "hexokinase", organism: "Mus musculus" }),
      "simulate mouse hexokinase with glucose",
    );
    expect(resolved!.entities!.organism).toBe("Mus musculus");
  });

  it("still returns null for a domain the resolver does not offer", () => {
    const resolved = parseLLMResponse(
      JSON.stringify({ domain: "sir", parameters: {}, reasoning: "", modelCitations: [] }),
      "model an outbreak",
    );
    expect(resolved).toBeNull();
  });
});

describe("the prompt asks only for what the query states", () => {
  it("no longer invites an inferred EC number or a default organism", async () => {
    const fetchSpy = modelReplies({
      domain: "mm",
      parameters: {},
      reasoning: "test",
      modelCitations: [],
      entities: { enzymeName: "lactate dehydrogenase", ecNumber: "1.1.1.27" },
    });

    const resolved = await resolveQueryWithLLM("simulate lactate dehydrogenase with pyruvate");

    const [, init] = fetchSpy.mock.calls[0]!;
    const body = JSON.parse(init!.body as string) as { messages: Array<{ content: string }> };
    const prompt = body.messages[0]!.content;
    expect(prompt).not.toContain("else Homo sapiens");
    expect(prompt).not.toContain("inferable");
    expect(prompt).toContain("copied verbatim");
    expect(prompt).toContain("only if the query names one");
    // And the parse applies the same rule to what came back.
    expect(resolved!.entities!.ecNumber).toBeUndefined();
    expect(resolved!.ecNumberDropped).toBe(true);
    expect(resolved!.entities!.organism).toBe("");
  });
});

describe("the response says what was decided for the person", () => {
  it("reports the organism assumed when neither the query nor the model named one", async () => {
    modelReplies(JSON.parse(reply({ enzymeName: "lactate dehydrogenase", organism: null })));
    vi.mocked(resolveKineticValue).mockResolvedValue(FOUND as never);

    const resolved = await resolveQuery(`simulate lactate dehydrogenase with pyruvate ${TAIL}`);

    expect(runnerPayload().organism).toBe("Homo sapiens");
    const assumed = resolved.provenance.flags.filter((f) => f.startsWith("assumed: organism = Homo sapiens"));
    expect(assumed).toHaveLength(1);
    expect(assumed[0]).toContain("name the organism in the query to choose it yourself");
    expect(resolved.parameterProvenance["km"]!.origin).toBe("resolved");
  });

  it("the query's own wording names the organism, with no assumption to report", async () => {
    // The model returned none; the query said E. coli. The deterministic
    // path's rule applies here too: the organism the query NAMES wins.
    modelReplies(JSON.parse(reply({ enzymeName: "lactate dehydrogenase", organism: null })));
    vi.mocked(resolveKineticValue).mockResolvedValue({ ...FOUND, organism: "Escherichia coli" } as never);

    const resolved = await resolveQuery(`simulate lactate dehydrogenase in E. coli with pyruvate ${TAIL}`);

    expect(runnerPayload().organism).toBe("Escherichia coli");
    expect(resolved.provenance.flags.some((f) => f.startsWith("assumed: organism"))).toBe(false);
  });

  it("an organism the model read out of the query is used, with no assumption to report", async () => {
    modelReplies(JSON.parse(reply({ enzymeName: "lactate dehydrogenase", organism: "Mus musculus" })));
    vi.mocked(resolveKineticValue).mockResolvedValue({ ...FOUND, organism: "Mus musculus" } as never);

    const resolved = await resolveQuery(`simulate lactate dehydrogenase with pyruvate ${TAIL}`);

    expect(runnerPayload().organism).toBe("Mus musculus");
    expect(resolved.provenance.flags.some((f) => f.startsWith("assumed: organism"))).toBe(false);
  });

  it("a proposed EC number never reaches the runner, and the response says it was dropped", async () => {
    modelReplies(JSON.parse(reply({ enzymeName: "lactate dehydrogenase", organism: "Homo sapiens", ecNumber: "1.1.1.27" })));
    vi.mocked(resolveKineticValue).mockResolvedValue(FOUND as never);

    const resolved = await resolveQuery(`simulate lactate dehydrogenase with pyruvate ${TAIL}`);

    const payload = runnerPayload();
    expect(payload.ecNumber).toBeUndefined();
    expect(payload.enzymeName).toBe("lactate dehydrogenase");
    const dropped = resolved.provenance.flags.filter((f) => f.startsWith("dropped: The model proposed EC 1.1.1.27"));
    expect(dropped).toHaveLength(1);
  });

  it("an EC number the query states does reach the runner", async () => {
    modelReplies(JSON.parse(reply({ enzymeName: "lactate dehydrogenase", organism: "Homo sapiens", ecNumber: "1.1.1.27" })));
    vi.mocked(resolveKineticValue).mockResolvedValue(FOUND as never);

    const resolved = await resolveQuery(`simulate lactate dehydrogenase EC 1.1.1.27 with pyruvate ${TAIL}`);

    expect(runnerPayload().ecNumber).toBe("1.1.1.27");
    expect(resolved.provenance.flags.some((f) => f.startsWith("dropped:"))).toBe(false);
  });

  it("the runner's ec_mismatch refusal reaches the person with both numbers", async () => {
    modelReplies(JSON.parse(reply({ enzymeName: "hexokinase", organism: "Homo sapiens", ecNumber: "1.1.1.27" })));
    const refusal =
      "The enzyme name and the EC number given are not the same enzyme: " +
      "'hexokinase' is EC 2.7.1.1 hexokinase by nomenclature's reading " +
      "(accepted name matches exactly), and ecNumber 1.1.1.27 was given. " +
      "Re-run with ecNumber 2.7.1.1 for 'hexokinase', or with the name of the enzyme EC 1.1.1.27 is.";
    vi.mocked(resolveKineticValue).mockResolvedValue({
      found: false,
      source: "ec_mismatch",
      ecCandidates: ["2.7.1.1"],
      ecCandidateNames: [{ ec: "2.7.1.1", name: "hexokinase", label: "EC 2.7.1.1 hexokinase", why: "accepted name matches exactly" }],
      ecRefusal: refusal,
      literatureCandidates: [],
      logs: [refusal],
    } as never);

    const error = await resolveQuery(`simulate hexokinase EC 1.1.1.27 with glucose ${TAIL}`).catch((e) => e);

    expect(error).toBeInstanceOf(RequiredParametersMissingError);
    const message = String(error.message);
    expect(message).toContain(refusal);
    expect(message).toContain("never asked");
    expect(message).not.toContain("Could not resolve a real KM value from");
  });
});

describe("the deterministic path reports its documented default the same way", () => {
  // No API key: resolveQueryWithLLM returns null without a request, and the
  // enzymes.ts table supplies the entities.
  it("names the assumption when the query names no organism", async () => {
    vi.mocked(resolveKineticValue).mockResolvedValue(FOUND as never);

    const resolved = await resolveQuery(`simulate hexokinase with glucose ${TAIL}`);

    expect(runnerPayload().organism).toBe("Homo sapiens");
    expect(resolved.provenance.flags.filter((f) => f.startsWith("assumed: organism = Homo sapiens"))).toHaveLength(1);
  });

  it("stays silent when the query names one", async () => {
    vi.mocked(resolveKineticValue).mockResolvedValue({ ...FOUND, organism: "Escherichia coli" } as never);

    const resolved = await resolveQuery(`simulate hexokinase in E. coli with glucose ${TAIL}`);

    expect(runnerPayload().organism).toBe("Escherichia coli");
    expect(resolved.provenance.flags.some((f) => f.startsWith("assumed: organism"))).toBe(false);
  });
});

describe("the ec_mismatch note names the stage that failed", () => {
  it("forwards the runner's refusal and does not blame BRENDA", () => {
    const refusal = "'hexokinase' is EC 2.7.1.1 hexokinase, and ecNumber 1.1.1.27 was given. Re-run with ecNumber 2.7.1.1 for 'hexokinase'.";
    const note = build("km", "ec_mismatch", undefined, undefined, undefined, ["2.7.1.1"], undefined, refusal).note ?? "";
    expect(note).toContain(refusal);
    expect(note).toContain("never asked");
    expect(note).toContain("wrong protein");
    expect(note).not.toContain("Could not resolve a real KM value from");
  });

  it("still works when neither the candidates nor the refusal travelled", () => {
    const note = build("km", "ec_mismatch").note ?? "";
    expect(note).toContain("a different EC number");
    expect(note).toContain("Re-run with the EC number you meant");
    expect(note).not.toContain("()");
  });

  it("keeps the stages apart", () => {
    const note = build("km", "ec_mismatch", undefined, undefined, undefined, ["3.2.1.1"]).note ?? "";
    expect(note).toContain("3.2.1.1");
    expect(note).not.toContain("allowCrossSpecies");
    expect(note).not.toContain("(S)-lactate");
  });
});
