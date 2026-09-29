/**
 * Report what real queries did, with no labelling required.
 *
 *   node <tsx> src/lib/runQueryLogSummary.ts [path]
 *
 * Defaults to $TERRIUM_QUERY_LOG. Exits 3 when logging was never switched on
 * or the file holds nothing -- "no queries have been collected" and "queries
 * were collected and none fell back" are different facts, and a summary that
 * printed 0% for both would be worse than no summary.
 */

import {
  formatQueryLogSummary,
  queryLogPath,
  readQueryLog,
  summariseQueryLog,
} from "./queryLog";

const path = process.argv[2] ?? queryLogPath();

if (path === null) {
  console.error(
    "NOT MEASURED: query logging is off and no path was given.\n" +
      "Set TERRIUM_QUERY_LOG to a file on the deployment students use, or\n" +
      "pass a log path as an argument. Nothing is collected by default.",
  );
  process.exit(3);
}

const entries = readQueryLog(path);
if (entries.length === 0) {
  console.error(
    `NOT MEASURED: ${path} holds no queries.\n` +
      "That is an absent measurement, not a fallback rate of zero.",
  );
  process.exit(3);
}

console.log(formatQueryLogSummary(summariseQueryLog(entries)));
console.log(
  "\nNext: label a sample to turn this into an accuracy --\n" +
    `  node <tsx> src/lib/labelQueryLog.ts ${path} real-queries.json --limit 50\n` +
    "Label them yourself. Labelling with an LLM would produce a set the LLM\n" +
    "classifier scores ~100% on by construction, measuring agreement rather\n" +
    "than correctness.",
);
