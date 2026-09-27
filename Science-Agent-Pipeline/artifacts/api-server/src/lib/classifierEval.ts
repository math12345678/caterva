/**
 * Does the LLM classifier actually beat the keyword table?
 *
 * Terrium's resolver picks a simulation domain two ways: an LLM when one is
 * configured, and an ordered keyword table when one is not. The LLM path has
 * existed for a long time and nobody has ever measured whether it earns the
 * API call. That is the whole question this file exists to answer, and it is
 * answerable only by running both over the same queries and counting.
 *
 * Two measurement rules this file follows, both learned the hard way in this
 * repository:
 *
 * 1. It calls `classifyDomainByKeyword` -- the function `resolveQuery`
 *    itself calls -- rather than reimplementing the keyword loop. A second
 *    copy of the classification would drift from the first, and the
 *    benchmark would then be scoring the copy.
 *
 * 2. It reports the keyword baseline's *fallback* separately from its hits.
 *    First-match-wins over an ordered table always returns a domain: a query
 *    matching nothing still comes back `mm`. Scoring that as an ordinary
 *    answer credits the baseline for every query it did not understand, and
 *    inflates it exactly where it is weakest. `matched: false` is the third
 *    state, and it is counted on its own.
 *
 * The labelled set below is authored, not drawn from a corpus. Each label is
 * the domain the query unambiguously describes, and the justification says
 * why. That provenance matters: these are the benchmark's own opinion of the
 * right answer, and the numbers mean nothing without it. They are not
 * literature values and are not presented as any.
 */

import { classifyDomainByKeyword } from "./queryResolver";
import { resolveQueryWithLLM } from "./llmResolver";
import type { SimulationDomain } from "./catervaRunner";
import {
  LABELLED_QUERIES,
  DEV_QUERIES,
  HELDOUT_QUERIES,
  type LabelledQuery,
} from "./classifierQueries";

export { LABELLED_QUERIES, DEV_QUERIES, HELDOUT_QUERIES };
export type { LabelledQuery };

export interface ClassifierOutcome {
  query: string;
  expected: SimulationDomain;
  got: SimulationDomain | null;
  correct: boolean;
  /** Keyword classifier only: false when the mm fallback was substituted. */
  matched?: boolean;
  orderingTrap: boolean;
}

export interface BenchmarkSummary {
  label: string;
  total: number;
  correct: number;
  /** Queries the classifier could not answer at all. For the keyword table
   *  this is the fallback count; for the LLM it is a null return. */
  undetermined: number;
  /** Correct answers that were only correct because the fallback happens to
   *  be the right domain. Credited nowhere, reported here. */
  correctByFallback: number;
  accuracy: number;
  outcomes: ClassifierOutcome[];
}

function summarise(
  label: string,
  outcomes: ClassifierOutcome[],
): BenchmarkSummary {
  const correct = outcomes.filter((o) => o.correct).length;
  return {
    label,
    total: outcomes.length,
    correct,
    undetermined: outcomes.filter((o) => o.matched === false || o.got === null)
      .length,
    correctByFallback: outcomes.filter((o) => o.correct && o.matched === false)
      .length,
    accuracy: outcomes.length === 0 ? 0 : correct / outcomes.length,
    outcomes,
  };
}

/** Run the keyword table over the labelled set. Pure and offline. */
export function benchmarkKeywordClassifier(
  queries: LabelledQuery[] = LABELLED_QUERIES,
): BenchmarkSummary {
  const outcomes = queries.map<ClassifierOutcome>((q) => {
    const { defaults, matched } = classifyDomainByKeyword(q.query);
    return {
      query: q.query,
      expected: q.expected,
      got: defaults.domain,
      correct: defaults.domain === q.expected,
      matched,
      orderingTrap: q.orderingTrap === true,
    };
  });
  return summarise("keyword table", outcomes);
}

const sleep = (ms: number) =>
  new Promise<void>((resolve) => setTimeout(resolve, ms));

export interface LLMBenchmarkOptions {
  /** Pause between calls. Free provider tiers are token-per-minute capped,
   *  and an un-paced run measures the rate limiter instead of the model. */
  pacingMs?: number;
  /** Attempts per query before it is recorded as undetermined. */
  attempts?: number;
}

/**
 * Ask the LLM once, retrying a null with backoff.
 *
 * `resolveQueryWithLLM` returns null for every failure alike: no API key, a
 * 429, a malformed body, an unsupported domain. In production that is a
 * deliberate fall-through to the keyword table. In a benchmark it is a trap:
 * scoring a rate-limited call as a wrong answer measures the provider's
 * billing tier and reports it as the model's accuracy. This retries first,
 * and only calls a query undetermined when it stays null.
 */
async function classifyWithRetry(
  query: string,
  attempts: number,
  pacingMs: number,
): Promise<{ domain: SimulationDomain | null; exhausted: boolean }> {
  for (let attempt = 0; attempt < attempts; attempt++) {
    const result = await resolveQueryWithLLM(query);
    if (result !== null) return { domain: result.domain, exhausted: false };
    // Backoff grows so a token-per-minute window has time to roll over.
    await sleep(pacingMs * (attempt + 1));
  }
  return { domain: null, exhausted: true };
}

/**
 * Run the configured LLM over the labelled set.
 *
 * Returns null when no LLM is reachable at all, rather than a zero score. A
 * score of zero and "there was nothing to score" are different facts, and
 * only one of them is a statement about the classifier.
 */
export async function benchmarkLLMClassifier(
  queries: LabelledQuery[] = LABELLED_QUERIES,
  options: LLMBenchmarkOptions = {},
): Promise<BenchmarkSummary | null> {
  const pacingMs = options.pacingMs ?? 6_000;
  const attempts = options.attempts ?? 4;

  // A first call that never succeeds across every attempt means no provider
  // answered -- report "not measured" rather than scoring the whole set zero.
  const probe = await classifyWithRetry(queries[0]!.query, attempts, pacingMs);
  if (probe.exhausted) return null;

  const outcomes: ClassifierOutcome[] = [];
  for (const [index, q] of queries.entries()) {
    const got =
      index === 0
        ? probe.domain
        : (await classifyWithRetry(q.query, attempts, pacingMs)).domain;
    outcomes.push({
      query: q.query,
      expected: q.expected,
      got,
      correct: got === q.expected,
      orderingTrap: q.orderingTrap === true,
    });
    if (index < queries.length - 1) await sleep(pacingMs);
  }
  return summarise("llm", outcomes);
}

export function formatSummary(s: BenchmarkSummary): string {
  const pct = (n: number, d: number) =>
    d === 0 ? "n/a" : `${((n / d) * 100).toFixed(1)}%`;
  const determined = s.total - s.outcomes.filter((o) => o.got === null).length;
  const lines = [
    `${s.label}: ${s.correct}/${s.total} correct (${pct(s.correct, s.total)})`,
    `  could not determine: ${s.undetermined}`,
    `  correct only via fallback: ${s.correctByFallback}`,
  ];
  if (determined !== s.total) {
    lines.push(
      `  accuracy over the ${determined} it answered: ${pct(s.correct, determined)}` +
        ` -- the ${s.total - determined} it did not answer are excluded here,` +
        ` because an unanswered query is not a wrong answer.`,
    );
  }
  const misses = s.outcomes.filter((o) => !o.correct);
  if (misses.length > 0) {
    lines.push("  misses:");
    for (const m of misses) {
      const tag = m.orderingTrap ? " [ordering trap]" : "";
      const fell = m.matched === false ? " (fallback)" : "";
      lines.push(
        `    expected ${m.expected}, got ${m.got ?? "nothing"}${fell}${tag}`,
      );
      lines.push(`      "${m.query}"`);
    }
  }
  return lines.join("\n");
}
