/**
 * Turn a log of real queries into a labelled set the benchmark can score.
 *
 * The log alone answers one question without any human effort -- what
 * fraction of real queries match no keyword at all. Accuracy needs more: a
 * person has to say what each query actually meant.
 *
 * This is the part that must not be automated, and the temptation to
 * automate it is exactly why it is worth stating. Labelling the queries with
 * an LLM would produce a set on which the LLM classifier scores ~100% by
 * construction, and on which the keyword classifier's score would measure
 * agreement-with-an-LLM rather than correctness. ADR 0195 hit the shared-
 * author failure one level down; using a model as the labeller would be the
 * same mistake one level down again. So the labeller is a human, and this
 * file's job is to make that as short as possible rather than to avoid it.
 *
 * ## Usage
 *
 *   node <tsx> src/lib/labelQueryLog.ts <log.jsonl> <out.json> [--limit N]
 *
 * It prints each unlabelled query with the classifier's guess and reads a
 * verdict from stdin: Enter to accept the guess, a domain name to correct
 * it, `s` to skip a query that is ambiguous or not a simulation request, `?`
 * for the domain list, and `q` to stop and save.
 *
 * Saving on quit matters: a labelling session interrupted after forty
 * queries should leave forty labels, not nothing. Everything already
 * labelled in the output file is reloaded on the next run, so the work is
 * resumable and nobody labels the same query twice.
 */

import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { createInterface } from "node:readline";
import { classifyDomainByKeyword } from "./queryResolver";
import { DOMAIN_MEANINGS } from "./llmResolver";
import { readQueryLog } from "./queryLog";

export interface HumanLabelledQuery {
  query: string;
  /** What a person said this query means. */
  expected: string;
  /** What the keyword classifier said, recorded at labelling time so a
   *  later disagreement is visible without re-running anything. */
  keywordSaid: string;
  /** True when the labeller accepted the classifier's guess unchanged.
   *  Kept because a set where every label was an accepted guess is a set
   *  that agrees with the classifier by construction, and a reader should
   *  be able to see that rather than infer it. */
  acceptedGuess: boolean;
}

export interface LabelledSetFile {
  _source: string;
  _labelledBy: string;
  _warning: string;
  queries: HumanLabelledQuery[];
  /** Queries a person declined to label, with no reason recorded beyond the
   *  skip. Counted so the set cannot silently exclude everything hard. */
  skipped: string[];
}

const DOMAINS = Object.keys(DOMAIN_MEANINGS);

export function loadExisting(outPath: string): LabelledSetFile {
  if (existsSync(outPath)) {
    return JSON.parse(readFileSync(outPath, "utf-8")) as LabelledSetFile;
  }
  return {
    _source: "",
    _labelledBy:
      "a person, at a terminal. NOT an LLM -- see the header of labelQueryLog.ts " +
      "for why labelling these with a model would make the set worthless.",
    _warning:
      "`expected` is one person's reading of what each query meant. It is a " +
      "judgement, not ground truth, and a second labeller would disagree " +
      "somewhere.",
    queries: [],
    skipped: [],
  };
}

/** Queries in the log that nobody has labelled or skipped yet. */
export function unlabelled(
  logQueries: string[],
  done: LabelledSetFile,
): string[] {
  const seen = new Set([
    ...done.queries.map((q) => q.query.trim().toLowerCase()),
    ...done.skipped.map((q) => q.trim().toLowerCase()),
  ]);
  const out: string[] = [];
  for (const q of logQueries) {
    const key = q.trim().toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key); // also deduplicates within the log itself
    out.push(q);
  }
  return out;
}

/**
 * Interpret one keystroke of labeller input.
 *
 * Extracted so the decision logic is testable without a terminal. A function
 * whose behaviour can only be checked by driving stdin is a function nothing
 * checks.
 */
export type LabelAction =
  | { kind: "accept" }
  | { kind: "label"; domain: string }
  | { kind: "skip" }
  | { kind: "help" }
  | { kind: "quit" }
  | { kind: "unknown"; input: string };

export function interpret(input: string): LabelAction {
  const trimmed = input.trim();
  if (trimmed === "") return { kind: "accept" };
  if (trimmed === "s") return { kind: "skip" };
  if (trimmed === "?") return { kind: "help" };
  if (trimmed === "q") return { kind: "quit" };

  // Accept an unambiguous prefix, so nobody types
  // "two_locus_wright_fisher" forty times.
  const matches = DOMAINS.filter((d) => d.startsWith(trimmed));
  if (matches.length === 1) return { kind: "label", domain: matches[0]! };

  // An ambiguous prefix is NOT a label. Guessing which domain was meant
  // would put a label nobody chose into a set whose whole value is that a
  // person chose every label.
  return { kind: "unknown", input: trimmed };
}

async function main(): Promise<void> {
  const [logPath, outPath] = process.argv.slice(2);
  if (!logPath || !outPath) {
    console.error(
      "usage: labelQueryLog.ts <log.jsonl> <out.json> [--limit N]\n" +
        "  <log.jsonl>  a query log written by queryLog.ts\n" +
        "  <out.json>   labelled set; reloaded and appended to if it exists",
    );
    process.exit(2);
  }

  const limitFlag = process.argv.indexOf("--limit");
  const limit =
    limitFlag === -1 ? Infinity : Number.parseInt(process.argv[limitFlag + 1] ?? "", 10);

  const entries = readQueryLog(logPath);
  if (entries.length === 0) {
    console.error(
      `${logPath} holds no queries. Nothing to label -- this is an empty\n` +
        "input, not an empty result. Check TERRIUM_QUERY_LOG was set on the\n" +
        "deployment that served the queries.",
    );
    process.exit(3);
  }

  const done = loadExisting(outPath);
  done._source = logPath;
  const todo = unlabelled(entries.map((e) => e.query), done).slice(0, limit);

  console.log(
    `${entries.length} logged, ${done.queries.length} already labelled, ` +
      `${todo.length} to go.\n` +
      "Enter = accept the guess · <domain> = correct it · s = skip · ? = list · q = save and quit\n",
  );

  const rl = createInterface({ input: process.stdin, output: process.stdout });
  const ask = (prompt: string) =>
    new Promise<string>((resolve) => rl.question(prompt, resolve));

  const save = () => writeFileSync(outPath, `${JSON.stringify(done, null, 2)}\n`);

  for (const [index, query] of todo.entries()) {
    const guess = classifyDomainByKeyword(query);
    const guessed = guess.defaults.domain;
    const tag = guess.matched ? guessed : `${guessed} (FALLBACK -- matched nothing)`;

    console.log(`\n[${index + 1}/${todo.length}] ${query}`);
    let answered = false;
    while (!answered) {
      const action = interpret(await ask(`  guess: ${tag}\n  > `));
      switch (action.kind) {
        case "accept":
          done.queries.push({
            query,
            expected: guessed,
            keywordSaid: guessed,
            acceptedGuess: true,
          });
          answered = true;
          break;
        case "label":
          done.queries.push({
            query,
            expected: action.domain,
            keywordSaid: guessed,
            acceptedGuess: false,
          });
          answered = true;
          break;
        case "skip":
          done.skipped.push(query);
          answered = true;
          break;
        case "help":
          for (const d of DOMAINS) console.log(`    ${d} -- ${DOMAIN_MEANINGS[d]}`);
          break;
        case "quit":
          save();
          console.log(`\nsaved ${done.queries.length} labels to ${outPath}`);
          rl.close();
          return;
        case "unknown":
          console.log(
            `    "${action.input}" is not one domain (? for the list). ` +
              "Not guessing which you meant.",
          );
          break;
      }
      // Save after every decision. A session that dies at query 40 should
      // leave 40 labels behind, not nothing.
      if (answered) save();
    }
  }

  save();
  console.log(
    `\ndone: ${done.queries.length} labelled, ${done.skipped.length} skipped -> ${outPath}`,
  );
  rl.close();
}

if (process.argv[1]?.endsWith("labelQueryLog.ts")) {
  await main();
}
