/**
 * Check every configured LLM provider and say which ones actually work.
 *
 *   node <tsx> src/lib/runLLMDoctor.ts
 *
 * Makes one small completion request per provider that has a key. Exits 0 if
 * any provider works, 1 if all configured ones are broken, and 3 if none is
 * configured -- because "nothing was checked" is not "everything is fine".
 */

import {
  exitCodeFor,
  formatReports,
  probeAllProviders,
} from "./llmDoctor";

const reports = await probeAllProviders({
  fetch: globalThis.fetch,
  now: () => Date.now(),
  env: process.env,
});

console.log("LLM providers\n");
console.log(formatReports(reports));

process.exit(exitCodeFor(reports));
