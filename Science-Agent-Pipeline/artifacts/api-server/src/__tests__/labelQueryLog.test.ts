/**
 * The labelling tool's decisions, tested without a terminal.
 *
 * `interpret` and `unlabelled` are separated from the readline loop so they
 * can be checked directly. A function whose behaviour can only be exercised
 * by driving stdin is a function nothing checks -- and the thing being
 * checked here is precisely that the tool never puts a label into the set
 * that a person did not choose.
 */

import { describe, expect, it } from "vitest";
import {
  interpret,
  loadExisting,
  unlabelled,
  type LabelledSetFile,
} from "../lib/labelQueryLog";

const empty = (): LabelledSetFile => loadExisting("/nonexistent/path.json");

describe("interpreting labeller input", () => {
  it("treats a bare Enter as accepting the guess", () => {
    expect(interpret("")).toEqual({ kind: "accept" });
    expect(interpret("   ")).toEqual({ kind: "accept" });
  });

  it("accepts an unambiguous prefix as a label", () => {
    // Nobody should type "mm_competitive_inhibition" forty times.
    expect(interpret("mm_")).toEqual({
      kind: "label",
      domain: "mm_competitive_inhibition",
    });
    expect(interpret("gillespie_ssa_b")).toEqual({
      kind: "label",
      domain: "gillespie_ssa_bimolecular",
    });
  });

  it("accepts a full domain name", () => {
    expect(interpret("mm_competitive_inhibition")).toEqual({
      kind: "label",
      domain: "mm_competitive_inhibition",
    });
  });

  it("refuses an ambiguous prefix rather than guessing", () => {
    // "mm" prefixes both mm and mm_competitive_inhibition. Picking one would
    // put a label nobody chose into a set whose entire value is that a person
    // chose every label.
    expect(interpret("mm")).toEqual({ kind: "unknown", input: "mm" });
    expect(interpret("gillespie_ssa")).toEqual({
      kind: "unknown",
      input: "gillespie_ssa",
    });
  });

  it("refuses an unrecognised word rather than guessing", () => {
    expect(interpret("epidemic")).toEqual({ kind: "unknown", input: "epidemic" });
  });

  it("has distinct skip, help and quit actions", () => {
    expect(interpret("s")).toEqual({ kind: "skip" });
    expect(interpret("?")).toEqual({ kind: "help" });
    expect(interpret("q")).toEqual({ kind: "quit" });
  });
});

describe("choosing what still needs labelling", () => {
  it("skips queries already labelled", () => {
    const done = empty();
    done.queries.push({
      query: "model a flu outbreak",
      expected: "sir",
      keywordSaid: "sir",
      acceptedGuess: true,
    });
    expect(unlabelled(["model a flu outbreak", "something else"], done)).toEqual([
      "something else",
    ]);
  });

  it("skips queries a person deliberately skipped", () => {
    // A skipped query is a decision, not an omission. Re-presenting it would
    // ask the same person the same unanswerable question every session.
    const done = empty();
    done.skipped.push("what is this tool");
    expect(unlabelled(["what is this tool", "model drift"], done)).toEqual([
      "model drift",
    ]);
  });

  it("matches case- and whitespace-insensitively", () => {
    const done = empty();
    done.queries.push({
      query: "Model A Flu Outbreak",
      expected: "sir",
      keywordSaid: "sir",
      acceptedGuess: true,
    });
    expect(unlabelled(["  model a flu outbreak  "], done)).toEqual([]);
  });

  it("deduplicates repeats within the log itself", () => {
    // A class of students asks near-identical things; labelling the same
    // sentence twenty times would inflate the set without adding evidence.
    expect(unlabelled(["same query", "SAME QUERY", "other"], empty())).toEqual([
      "same query",
      "other",
    ]);
  });
});

describe("the labelled set records how it was made", () => {
  it("says a person labelled it, and why that matters", () => {
    const set = empty();
    expect(set._labelledBy).toContain("NOT an LLM");
  });

  it("warns that a label is a judgement rather than ground truth", () => {
    expect(empty()._warning).toContain("judgement");
  });

  it("keeps room for skipped queries so nothing is silently excluded", () => {
    // A set that dropped every hard query without recording it would look
    // easier than the real distribution.
    expect(empty().skipped).toEqual([]);
  });
});
