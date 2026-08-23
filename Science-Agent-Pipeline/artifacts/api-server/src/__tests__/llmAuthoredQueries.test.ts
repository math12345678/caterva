/**
 * The classifier scored against queries its author did not phrase.
 *
 * The `heldout` split in `classifierQueries.ts` was written before tuning,
 * which is the usual precaution, and it was not enough: the same person then
 * widened the keyword vocabulary from the same source those queries came
 * from, so the vocabulary matched the phrasing by construction and the split
 * scored 100%. That number measured a shared author, not a classifier.
 *
 * These fixtures were written by LLMs shown one sentence per domain -- the
 * same sentence the resolver is shown -- and never the keyword table. The
 * classifier scores 79.5% on the Groq-authored set and 51.4% on the
 * Mistral-authored one. That 28-point spread is the finding: this classifier
 * has no single accuracy, only an accuracy against a particular way of
 * asking. Quoting either number alone would misdescribe it.
 *
 * The label is the domain each query was *commissioned* for, not verified
 * ground truth: a model asked for a `seir` question can write one better
 * answered by `sir`. Some of the misses are that rather than classifier
 * error, and no attempt is made here to separate the two.
 *
 * Both fixtures are committed, so these tests are offline and reproducible.
 * They are regenerated -- deliberately rarely -- with:
 *
 *   node <tsx> src/lib/generateProbeQueries.ts <out.json> 6
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { classifyDomainByKeyword } from "../lib/queryResolver";

const FIXTURE_DIR = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "fixtures",
);

interface ProbeFixture {
  _generatedBy: string;
  _model: string;
  _labelMeans: string;
  queries: { query: string; expected: string }[];
}

const load = (name: string): ProbeFixture =>
  JSON.parse(readFileSync(path.join(FIXTURE_DIR, name), "utf-8"));

/**
 * Two fixtures, from two different models.
 *
 * The second exists because the first left a confound: it was written by the
 * same model the LLM arm was then scored on, so that arm was classifying its
 * own phrasing while the keyword table was not. The Mistral fixture settles
 * it -- and the answer was that the confound was worth about 0.2 points,
 * while the *keyword* table swung 28 points between the two sources.
 *
 * `previousCorrect` is what the classifier this replaced scored on that same
 * fixture. Measured, not chosen: a round-number threshold is an invitation to
 * tune until it passes, whereas "must beat what it replaced" is a claim.
 */
const FIXTURES = [
  {
    name: "groq",
    fixture: load("llm-authored-queries.json"),
    domains: 13,
    previousCorrect: 54,
  },
  {
    name: "openrouter",
    fixture: load("openrouter-authored-queries.json"),
    domains: 13,
    previousCorrect: 48,
  },
  {
    name: "mistral",
    fixture: load("mistral-authored-queries.json"),
    // 12, not 13: generation failed for one domain and the generator dropped
    // it with a warning rather than substituting a hand-written query, which
    // would have put the author's phrasing back into the one set that exists
    // to exclude it.
    domains: 12,
    previousCorrect: 30,
  },
] as const;

describe.each(FIXTURES)(
  "the $name-authored fixture",
  ({ fixture: fx, domains, previousCorrect }) => {
    const score = () => {
      let correct = 0;
      let fallbacks = 0;
      const confusions = new Map<string, number>();
      for (const q of fx.queries) {
        const { defaults, matched } = classifyDomainByKeyword(q.query);
        if (!matched) fallbacks++;
        if (defaults.domain === q.expected) correct++;
        else {
          const key = `${q.expected} -> ${defaults.domain}`;
          confusions.set(key, (confusions.get(key) ?? 0) + 1);
        }
      }
      return { correct, fallbacks, total: fx.queries.length, confusions };
    };

    it("covers the domains it was generated for", () => {
      expect(new Set(fx.queries.map((q) => q.expected)).size).toBe(domains);
    });

    it("records how it was made and what its labels mean", () => {
      // Provenance travels with the data or it is lost. A fixture of plain
      // strings, six months on, is indistinguishable from a hand-written one
      // -- the exact bias it exists to rule out.
      expect(fx._generatedBy).toContain("LLM");
      expect(fx._model.length).toBeGreaterThan(0);
      expect(fx._labelMeans).toContain("NOT independently verified");
    });

    it("is not phrased by the same hand as the keyword table", () => {
      // A weak but checkable proxy: a hand-written set drifts toward exact
      // domain identifiers, so the fixture should not be dominated by them.
      const selfNaming = fx.queries.filter((q) =>
        q.query.toLowerCase().includes(q.expected.replace(/_/g, " ")),
      );
      expect(selfNaming.length).toBeLessThan(fx.queries.length / 4);
    });

    it("beats the classifier it replaced", () => {
      expect(score().correct).toBeGreaterThan(previousCorrect);
    });

    it("does not score perfectly, which would mean the set shares its author", () => {
      // Not a joke assertion. The hand-written held-out split scored 100%,
      // and that was the symptom that led here. If this ever reaches 100%,
      // the fixture has stopped being independent -- most likely because
      // somebody tuned the vocabulary against it -- and it should fail loudly
      // rather than read as success.
      const { correct, total } = score();
      expect(correct).toBeLessThan(total);
    });

    it("reports its confusions rather than only a score", () => {
      const { confusions } = score();
      expect(confusions.size).toBeGreaterThan(0);
      for (const key of confusions.keys()) expect(key).toContain(" -> ");
    });
  },
);

describe("across the two fixtures", () => {
  it("shows the keyword table is sensitive to who phrased the question", () => {
    // The finding that matters more than either number: this classifier has
    // no single accuracy. Asserting the spread is real keeps a future reader
    // from quoting one figure as "the" accuracy.
    const rate = (fx: ProbeFixture) => {
      let c = 0;
      for (const q of fx.queries) {
        if (classifyDomainByKeyword(q.query).defaults.domain === q.expected) c++;
      }
      return c / fx.queries.length;
    };
    // Across every fixture, not two of them by index. The first version
    // compared FIXTURES[0] against FIXTURES[1]; adding a third fixture in
    // the middle silently changed which pair was being compared and the
    // test failed for a reason that had nothing to do with the classifier.
    const rates = FIXTURES.map((f) => rate(f.fixture));
    const spread = Math.max(...rates) - Math.min(...rates);
    expect(spread).toBeGreaterThan(0.15);
  });
});
