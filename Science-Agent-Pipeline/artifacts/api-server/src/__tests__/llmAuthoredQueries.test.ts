/**
 * The classifier scored against queries its author did not phrase.
 *
 * The `heldout` split in `classifierQueries.ts` was written before tuning,
 * which is the usual precaution, and it was not enough: the same person then
 * widened the keyword vocabulary from the same source those queries came
 * from, so the vocabulary matched the phrasing by construction and the split
 * scored 100%. That number measured a shared author, not a classifier.
 *
 * This fixture was written by an LLM shown one sentence per domain -- the
 * same sentence the resolver is shown -- and never the keyword table. On it
 * the classifier scores 79.5%, not 100%, which is the number ADR 0167
 * reports.
 *
 * The label is the domain each query was *commissioned* for, not verified
 * ground truth: a model asked for a `seir` question can write one better
 * answered by `sir`. Some of the misses below are probably that rather than
 * classifier error, and no attempt is made here to separate the two. The
 * score is a floor on classifier quality, not a measurement of it.
 *
 * The fixture is committed, so this test is offline and reproducible. It is
 * regenerated -- deliberately rarely -- with:
 *
 *   node <tsx> src/lib/generateProbeQueries.ts \
 *     src/__tests__/fixtures/llm-authored-queries.json 6
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { classifyDomainByKeyword } from "../lib/queryResolver";

const FIXTURE = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "fixtures",
  "llm-authored-queries.json",
);

interface ProbeFixture {
  _generatedBy: string;
  _model: string;
  _labelMeans: string;
  queries: { query: string; expected: string }[];
}

const fixture: ProbeFixture = JSON.parse(readFileSync(FIXTURE, "utf-8"));

/**
 * What the classifier this replaced scored on this same fixture: 54 of 78.
 * Measured, not chosen -- it is the committed first-match-wins classifier
 * over the original keyword table, run over this file.
 *
 * It is used as the floor instead of a round number because a round number
 * is an invitation to tune until it passes. "Must beat what it replaced" is
 * a claim that means something; "must exceed 70%" is not.
 */
const PREVIOUS_CLASSIFIER_CORRECT = 54;

function scoreFixture() {
  let correct = 0;
  let fallbacks = 0;
  const confusions = new Map<string, number>();
  for (const q of fixture.queries) {
    const { defaults, matched } = classifyDomainByKeyword(q.query);
    if (!matched) fallbacks++;
    if (defaults.domain === q.expected) correct++;
    else {
      const key = `${q.expected} -> ${defaults.domain}`;
      confusions.set(key, (confusions.get(key) ?? 0) + 1);
    }
  }
  return { correct, fallbacks, total: fixture.queries.length, confusions };
}

describe("the LLM-authored fixture", () => {
  it("covers every domain the resolver exposes", () => {
    expect(new Set(fixture.queries.map((q) => q.expected)).size).toBe(13);
  });

  it("records how it was made and what its labels mean", () => {
    // Provenance travels with the data or it is lost. A fixture of plain
    // strings, six months on, is indistinguishable from a hand-written one
    // -- which is the exact bias it exists to rule out.
    expect(fixture._generatedBy).toContain("LLM");
    expect(fixture._model.length).toBeGreaterThan(0);
    expect(fixture._labelMeans).toContain("NOT independently verified");
  });

  it("is not phrased by the same hand as the keyword table", () => {
    // A weak but checkable proxy: the fixture should not be dominated by
    // exact domain identifiers, which is what a hand-written set drifts
    // toward.
    const selfNaming = fixture.queries.filter((q) =>
      q.query.toLowerCase().includes(q.expected.replace(/_/g, " ")),
    );
    expect(selfNaming.length).toBeLessThan(fixture.queries.length / 4);
  });
});

describe("the keyword classifier on queries it did not author", () => {
  it("beats the classifier it replaced", () => {
    const { correct } = scoreFixture();
    expect(correct).toBeGreaterThan(PREVIOUS_CLASSIFIER_CORRECT);
  });

  it("does not score perfectly, which would mean the set shares its author", () => {
    // Not a joke assertion. The previous held-out split scored 100% and that
    // was the symptom that led here. If this ever reaches 100%, the fixture
    // has stopped being independent -- most likely because somebody tuned
    // the vocabulary against it -- and that should fail loudly.
    const { correct, total } = scoreFixture();
    expect(correct).toBeLessThan(total);
  });

  it("leaves few queries matching nothing at all", () => {
    // The original classifier fell back on 11 of 78. The fallback is the
    // state where the classifier knows nothing and answers `mm` anyway, so
    // it is the one worth bounding.
    const { fallbacks } = scoreFixture();
    expect(fallbacks).toBeLessThan(11);
  });

  it("still reports its confusions rather than only a score", () => {
    const { confusions } = scoreFixture();
    // There are misses, and each is attributable to a domain pair. A score
    // with no confusion structure cannot be acted on.
    expect(confusions.size).toBeGreaterThan(0);
    for (const key of confusions.keys()) {
      expect(key).toContain(" -> ");
    }
  });
});
