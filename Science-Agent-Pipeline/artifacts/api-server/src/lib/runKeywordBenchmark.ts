/**
 * Score the keyword domain classifier over every labelled set, offline.
 *
 *   node <tsx> src/lib/runKeywordBenchmark.ts
 *
 * No API key, no network. Every set is either committed source
 * (`classifierQueries.ts`) or a committed fixture, so the numbers in
 * ADR 0191 are reproducible by anyone who checks the repository out.
 *
 * It prints one row per set rather than one aggregate number, and refuses to
 * print an aggregate at all. That is the finding ADR 0191 landed on: the
 * keyword table scored 79.5% against one model's phrasing and 51.4% against
 * another's, on the same 13 domains. A mean over those would be a number
 * describing no situation any reader is in. The spread is the result.
 */

import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { classifyDomainByKeyword } from "./queryResolver";
import { DEV_QUERIES, HELDOUT_QUERIES } from "./classifierQueries";

interface Scored {
  label: string;
  provenance: string;
  correct: number;
  total: number;
  fallbacks: number;
  confusions: Map<string, number>;
}

function score(
  label: string,
  provenance: string,
  queries: { query: string; expected: string }[],
): Scored {
  let correct = 0;
  let fallbacks = 0;
  const confusions = new Map<string, number>();
  for (const q of queries) {
    const { defaults, matched } = classifyDomainByKeyword(q.query);
    if (!matched) fallbacks++;
    if (defaults.domain === q.expected) correct++;
    else {
      const key = `${q.expected} -> ${defaults.domain}`;
      confusions.set(key, (confusions.get(key) ?? 0) + 1);
    }
  }
  return { label, provenance, correct, total: queries.length, fallbacks, confusions };
}

const FIXTURE_DIR = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "__tests__",
  "fixtures",
);

const sets: Scored[] = [
  score(
    "dev (hand-written, after reading the keyword table)",
    "CONTAMINATED -- diagnostic only, not evidence of accuracy",
    DEV_QUERIES,
  ),
  score(
    "heldout (hand-written, before tuning)",
    "SHARED AUTHOR -- same person wrote these and the vocabulary",
    HELDOUT_QUERIES,
  ),
];

const empty: string[] = [];

for (const file of readdirSync(FIXTURE_DIR).sort()) {
  if (!file.endsWith("-authored-queries.json")) continue;
  const raw = JSON.parse(readFileSync(path.join(FIXTURE_DIR, file), "utf-8"));

  // A fixture with no queries is not a set that scored badly, it is the
  // absence of a measurement. Scoring it produced `0/0` and `NaN%`, which
  // printed as a row like any other -- five rows where three measurements
  // existed. Named and excluded instead.
  if (!Array.isArray(raw.queries) || raw.queries.length === 0) {
    empty.push(file);
    continue;
  }

  sets.push(
    score(
      `${file.replace("-authored-queries.json", "")} (LLM-authored)`,
      `model: ${raw._model}`,
      raw.queries,
    ),
  );
}

const pct = (n: number, d: number) => `${((n / d) * 100).toFixed(1)}%`;
const width = Math.max(...sets.map((s) => s.label.length));

console.log("keyword domain classifier, per labelled set\n");
for (const s of sets) {
  console.log(
    `  ${s.label.padEnd(width)}  ${String(s.correct).padStart(3)}/${String(s.total).padEnd(3)}` +
      `  ${pct(s.correct, s.total).padStart(6)}   fallbacks ${s.fallbacks}`,
  );
  console.log(`  ${" ".repeat(width)}  ${s.provenance}`);
}

// The independent sets are the only ones that can settle anything; the two
// hand-written ones are printed for continuity with ADR 0190 and labelled
// with why they cannot be used as evidence.
const independent = sets.filter((s) => s.label.includes("LLM-authored"));
if (independent.length >= 2) {
  const rates = independent.map((s) => s.correct / s.total);
  const spread = Math.max(...rates) - Math.min(...rates);
  console.log(
    `\n  spread across ${independent.length} independent sets: ` +
      `${(spread * 100).toFixed(1)} points ` +
      `(${pct(Math.min(...rates) * 100, 100)} to ${pct(Math.max(...rates) * 100, 100)})`,
  );
  console.log(
    "  No aggregate is printed on purpose: a mean over these describes no\n" +
      "  reader's situation. The spread is the result.",
  );
}

if (empty.length > 0) {
  // Printed after the table, loudly, because the failure mode being guarded
  // against is a reader counting rows.
  console.log(
    `\n  ${empty.length} fixture(s) contained no queries and were EXCLUDED, not scored:`,
  );
  for (const f of empty) console.log(`    ${f}`);
  console.log(
    "  These are absent measurements, not bad ones. Regenerate or delete them.",
  );
}

const allConfusions = new Map<string, number>();
for (const s of independent) {
  for (const [k, v] of s.confusions) {
    allConfusions.set(k, (allConfusions.get(k) ?? 0) + v);
  }
}
if (allConfusions.size > 0) {
  console.log("\n  confusions across the independent sets:");
  for (const [k, v] of [...allConfusions].sort((a, b) => b[1] - a[1]).slice(0, 8)) {
    console.log(`    ${String(v).padStart(3)}x  ${k}`);
  }
}
