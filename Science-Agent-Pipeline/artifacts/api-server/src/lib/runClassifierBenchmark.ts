/**
 * Run the domain-classifier benchmark and print both scores.
 *
 *   node <tsx> src/lib/runClassifierBenchmark.ts
 *
 * The keyword baseline always runs; it is offline. The LLM arm runs only when
 * a provider is configured, and says so plainly when it is not -- an absent
 * LLM produces "not measured", never a zero.
 */

import {
  benchmarkKeywordClassifier,
  benchmarkLLMClassifier,
  formatSummary,
} from "./classifierEval";

const keyword = benchmarkKeywordClassifier();
console.log(formatSummary(keyword));
console.log();

const pacingMs = Number.parseInt(process.env.LLM_BENCH_PACING_MS ?? "", 10);
const llm = await benchmarkLLMClassifier(
  undefined,
  Number.isNaN(pacingMs) ? {} : { pacingMs },
);
if (llm === null) {
  console.log(
    "llm: NOT MEASURED -- no provider answered.\n" +
      "  Set LLM_PROVIDER (groq | openrouter | mistral | siliconflow |\n" +
      "  tokenrouter) plus that provider's API key, or LLM_API_KEY with\n" +
      "  LLM_API_URL. This is not a score of zero: nothing was measured.",
  );
  process.exit(3);
}

console.log(formatSummary(llm));
console.log();

const unanswered = llm.outcomes.filter((o) => o.got === null).length;
if (unanswered > 0) {
  console.log(
    `NOT COMPARABLE: the LLM left ${unanswered} of ${llm.total} queries\n` +
      "unanswered after every retry. Counting those against it would report\n" +
      "the provider's rate limit as the model's accuracy. Re-run with a\n" +
      "higher pacing (LLM_BENCH_PACING_MS) or a provider with more headroom.",
  );
  process.exit(3);
}

const delta = llm.correct - keyword.correct;
const sign = delta > 0 ? "+" : "";
console.log(
  `llm - keyword = ${sign}${delta} of ${keyword.total} queries ` +
    `(${sign}${((delta / keyword.total) * 100).toFixed(1)} points)`,
);
