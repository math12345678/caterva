/**
 * The model proposes structure; it may not propose numbers.
 *
 * This is the security boundary of the open path. Letting a language model
 * construct a network is what makes arbitrary systems expressible; letting
 * it construct the CONSTANTS in that network would hand it the one thing
 * Terrium exists to refuse.
 *
 * The split cannot rest on the model's cooperation, so it does not: a value
 * survives only if the model quoted the span of the USER's text that states
 * it, and the quote is checked against the query. Fabricating an attribution
 * therefore requires fabricating a substring of a text the model did not
 * write -- much harder to get right by accident than a plausible number.
 *
 * These tests exercise that rule directly rather than through a network
 * call. A rule reachable only via an API key is a rule nobody runs.
 */
import { describe, expect, it } from "vitest";

import {
  describeWhatIsNeeded,
  resolveConstructedModel,
  stripUnstatedValues,
  type ConstructedModel,
} from "../lib/networkResolver";

const QUERY =
  "Simulate a two-step decay A -> B -> C starting from 100 nM of A, " +
  "with a first rate constant of 0.4 per second. Run for 30 seconds.";

/** What a well-behaved model returns for that query. */
const REPLY: ConstructedModel = {
  network: {
    name: "two_step_decay",
    species: [
      { id: "A", initial: 1 },
      { id: "B", initial: 1 },
      { id: "C", initial: 1 },
    ],
    parameters: [
      { id: "k1", value: 1 },
      { id: "k2", value: 1 },
    ],
    reactions: [
      { id: "R1", reactants: { A: 1 }, products: { B: 1 }, rateLaw: "k1 * A" },
      { id: "R2", reactants: { B: 1 }, products: { C: 1 }, rateLaw: "k2 * B" },
    ],
    rateRules: [],
    assignmentRules: [],
  },
  reasoning: "Two sequential first-order steps.",
  values: [
    { quantity: "A", value: 100, quotedFrom: "100 nM of A" },
    { quantity: "k1", value: 0.4, quotedFrom: "a first rate constant of 0.4 per second" },
  ],
};

describe("values the query supports are kept", () => {
  it("accepts a value whose quotation appears in the query", () => {
    const { sources, applied, discarded } = stripUnstatedValues(QUERY, REPLY);
    expect(discarded).toEqual([]);
    expect(applied).toEqual({ A: 100, k1: 0.4 });
    expect(sources["A"]!.origin).toBe("user");
    // The note carries the evidence, so a reader can check the attribution
    // without re-reading the query.
    expect(sources["A"]!.note).toContain("100 nM of A");
  });

  it("matches across case and whitespace differences", () => {
    // A model re-wrapping or re-casing the user's words is not fabricating.
    const reply: ConstructedModel = {
      ...REPLY,
      values: [{ quantity: "A", value: 100, quotedFrom: "100  NM   of a" }],
    };
    const { applied, discarded } = stripUnstatedValues(QUERY, reply);
    expect(discarded).toEqual([]);
    expect(applied).toEqual({ A: 100 });
  });
});

describe("values the query does not support are discarded", () => {
  it("drops a value attributed to text the user never wrote", () => {
    // The failure this whole design exists to prevent: a plausible constant
    // presented as though the user had supplied it.
    const reply: ConstructedModel = {
      ...REPLY,
      values: [
        ...REPLY.values,
        {
          quantity: "k2",
          value: 0.12,
          quotedFrom: "a second rate constant of 0.12 per second",
        },
      ],
    };
    const { sources, applied, discarded } = stripUnstatedValues(QUERY, reply);

    expect(applied).not.toHaveProperty("k2");
    expect(sources).not.toHaveProperty("k2");
    expect(discarded).toHaveLength(1);
    expect(discarded[0]!.quantity).toBe("k2");
  });

  it("drops an empty or whitespace quotation", () => {
    const reply: ConstructedModel = {
      ...REPLY,
      values: [{ quantity: "k2", value: 0.12, quotedFrom: "   " }],
    };
    const { applied, discarded } = stripUnstatedValues(QUERY, reply);
    expect(applied).toEqual({});
    expect(discarded).toHaveLength(1);
  });

  it("a value is not smuggled in by naming a quantity the network lacks", () => {
    const reply: ConstructedModel = {
      ...REPLY,
      values: [{ quantity: "NOT_IN_MODEL", value: 5, quotedFrom: "100 nM of A" }],
    };
    const resolved = resolveConstructedModel(QUERY, reply)!;
    // It becomes a source for a quantity that does not exist, which the
    // engine reports as a mismatch -- and it changes no number in the model.
    expect(resolved.network.parameters.map((p) => p.value)).toEqual([1, 1]);
  });
});

describe("resolving a whole reply", () => {
  it("applies accepted values and leaves placeholders elsewhere", () => {
    const resolved = resolveConstructedModel(QUERY, REPLY)!;
    expect(resolved.network.species.find((s) => s.id === "A")!.initial).toBe(100);
    expect(resolved.network.parameters.find((p) => p.id === "k1")!.value).toBe(0.4);
    // k2 was never stated, so it keeps the placeholder AND is reported as
    // needed -- the placeholder must never reach a trajectory.
    expect(resolved.network.parameters.find((p) => p.id === "k2")!.value).toBe(1);
    expect(resolved.needed).toContain("k2");
  });

  it("reports every unsourced quantity, species initials included", () => {
    const resolved = resolveConstructedModel(QUERY, REPLY)!;
    // A and k1 are stated; B, C and k2 are not.
    expect(resolved.needed.sort()).toEqual(["B", "C", "k2"]);
  });

  it("returns null for a reply that is not a model at all", () => {
    expect(resolveConstructedModel(QUERY, { nonsense: true })).toBeNull();
    expect(resolveConstructedModel(QUERY, "a sentence")).toBeNull();
  });

  it("returns null for a network with no reactions and no rate rules", () => {
    const reply = {
      ...REPLY,
      network: { ...REPLY.network, reactions: [], rateRules: [] },
    };
    expect(resolveConstructedModel(QUERY, reply)).toBeNull();
  });

  it("names the missing quantities in the message a user sees", () => {
    const resolved = resolveConstructedModel(QUERY, REPLY)!;
    const message = describeWhatIsNeeded(resolved);
    for (const quantity of ["B", "C", "k2"]) {
      expect(message).toContain(quantity);
    }
    // The refusal states the reason, not just the fact.
    expect(message).toMatch(/nobody measured/i);
  });

  it("says nothing is needed when the query supplied everything", () => {
    const complete: ConstructedModel = {
      ...REPLY,
      values: [
        { quantity: "A", value: 100, quotedFrom: "100 nM of A" },
        { quantity: "B", value: 0, quotedFrom: "100 nM of A" },
        { quantity: "C", value: 0, quotedFrom: "100 nM of A" },
        { quantity: "k1", value: 0.4, quotedFrom: "0.4 per second" },
        { quantity: "k2", value: 0.1, quotedFrom: "30 seconds" },
      ],
    };
    const resolved = resolveConstructedModel(QUERY, complete)!;
    expect(resolved.needed).toEqual([]);
    expect(describeWhatIsNeeded(resolved)).toBe("");
  });
});

describe("the prompt states the rule it depends on", () => {
  it("tells the model not to supply numbers from its own knowledge", async () => {
    // The stripping above does not trust the prompt -- but a prompt that
    // asked for numbers would make every run produce discards, and the
    // signal that something is wrong would be lost in the noise.
    const { NETWORK_SYSTEM_PROMPT } = await import("../lib/networkResolver");
    expect(NETWORK_SYSTEM_PROMPT).toMatch(/NOT supply numeric values/i);
    expect(NETWORK_SYSTEM_PROMPT).toMatch(/quotedFrom/);
    expect(NETWORK_SYSTEM_PROMPT).toMatch(/gamma_rate/);
  });
});
