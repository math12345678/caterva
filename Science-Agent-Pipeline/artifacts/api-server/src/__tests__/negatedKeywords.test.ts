/**
 * A query that rules something out must not be routed to it.
 *
 * Four real queries from the LLM-authored fixtures were classified as
 * competitive inhibition:
 *
 *   "...as I add more substrate, no inhibitor involved."
 *   "...the typical hyperbolic curve for an enzyme without any inhibitors?"
 *   "Can you run a kinetic assay without any inhibitors present?"
 *   "What's the velocity curve like when no inhibitor is blocking the enzyme?"
 *
 * Each says there is no inhibitor. Each was given the inhibitor model,
 * because substring matching saw the word and had no way to see the "no" in
 * front of it. The student who took the trouble to be explicit got the
 * worst answer -- mentioning a thing to exclude it made it more likely, not
 * less.
 *
 * These tests pin both halves: that a negated mention no longer counts, and
 * that an ordinary mention still does. The second half matters as much as
 * the first, because the cheapest way to pass the first is to stop counting
 * the keyword at all.
 */

import { describe, expect, it } from "vitest";
import { classifyDomainByKeyword } from "../lib/queryResolver";

const domainOf = (q: string) => classifyDomainByKeyword(q).defaults.domain;

describe("a keyword the query denies", () => {
  it.each([
    "I want to see how the reaction speed changes as I add more substrate, no inhibitor involved.",
    "Could you run a model that displays the typical hyperbolic curve for an enzyme without any inhibitors?",
    "What's the velocity curve like when no inhibitor is blocking the enzyme?",
  ])("does not route %j to the inhibitor model", (query) => {
    expect(domainOf(query)).not.toBe("mm_competitive_inhibition");
  });

  it.each([
    "Run it with no inhibitor.",
    "Run it without an inhibitor.",
    "Run it in the absence of an inhibitor.",
    "Run it free of inhibitor.",
    "Run it lacking an inhibitor.",
    "Run it excluding the inhibitor.",
    "Run it, never an inhibitor.",
  ])("counts no keyword at all in %j", (query) => {
    // Asserting `matched`, not the domain.
    //
    // The first version of this test asserted `domainOf(...) === "mm"` over
    // phrasings like "enzyme kinetics in the absence of an inhibitor". It
    // passed whether or not negation worked, twice over: "enzyme kinetics"
    // outscores "inhibitor" anyway, and where it does not, the `mm` fallback
    // returns "mm" regardless. The mutation harness caught it -- shrinking
    // the negator list to the two words the bug was reported with left every
    // test green.
    //
    // These queries carry no keyword except the negated one, so `matched`
    // is exactly the question: did anything count? A negator that stops
    // working flips it to true and the assertion fails.
    const { matched } = classifyDomainByKeyword(query);
    expect(matched).toBe(false);
  });
});

describe("a keyword the query actually asserts", () => {
  it("still routes a real inhibitor question to the inhibitor model", () => {
    // The half that stops "fix" from meaning "ignore this keyword".
    expect(
      domainOf(
        "How does adding an inhibitor that competes for the active site change the rate?",
      ),
    ).toBe("mm_competitive_inhibition");
  });

  it("counts a later unnegated mention of the same word when the first is negated", () => {
    // "no inhibitor first, then with an inhibitor" -- the same keyword,
    // denied once and asserted once. Checking only the first occurrence
    // drops the assertion and the query falls through to the `mm` fallback.
    //
    // The earlier version of this test negated one word and asserted a
    // *different* one, so the first occurrence of the keyword under test was
    // never the negated one and the mutation sailed through. It has to be
    // the same word twice for this to check anything.
    const query = "With no inhibitor first, then with an inhibitor.";
    const { defaults, matched } = classifyDomainByKeyword(query);
    expect(matched).toBe(true);
    expect(defaults.domain).toBe("mm_competitive_inhibition");
  });

  it("does not treat a negator further back in the sentence as negating", () => {
    // The window is deliberately short. A "not" four clauses away is not
    // about this keyword, and treating it as though it were would silently
    // drop real matches.
    expect(
      domainOf(
        "I am not sure which model I need, but the enzyme has a competitive inhibitor bound at the active site.",
      ),
    ).toBe("mm_competitive_inhibition");
  });
});

describe("what this mechanism cannot do", () => {
  it("is fooled by a negator that does not scope over the keyword", () => {
    // Asserted, not hidden. "not sure how the inhibitor works" is a question
    // about an inhibitor that is present, and this reads it as absence.
    // Recording the limit as a test means a future reader finds it here
    // rather than rediscovering it from a misrouted query -- and if somebody
    // later implements real scope handling, this test fails and tells them
    // the limitation is gone.
    const query = "I am not sure how the inhibitor changes things";
    expect(domainOf(query)).not.toBe("mm_competitive_inhibition");
  });
});
