/**
 * Record the questions people actually ask, so the classifier can be
 * measured against them instead of against sets its author wrote.
 *
 * Five labelled sets exist and no student wrote a line of any of them. Three
 * consecutive records (ADR 0191, 0169, 0170) end by saying so, and ADR 0170
 * closed off the last route that did not need real queries: vocabulary
 * proposed by a model is fluent invention, and 97% of it never matched
 * anything. The measured accuracy of the keyword classifier ranges from 57%
 * to 90% depending only on who phrased the questions, so *which end of that
 * range a real student experiences is unknown*, and no amount of further
 * generation will settle it.
 *
 * This is the smallest thing that would.
 *
 * ## What is recorded, and what is deliberately not
 *
 * One line per query: the query text, what the keyword classifier made of
 * it, whether any keyword matched at all, and a coarse timestamp. That is
 * enough to compute the one number that needs no human labelling at all --
 * the **fallback rate on real questions** -- which is the single most useful
 * fact nobody currently has.
 *
 * Not recorded: any user, session or request identifier, IP address, or
 * header. Not because those are hard to strip later, but because a log that
 * never held them cannot leak them, and a teaching lab asked to turn this on
 * should be able to read this file and see that.
 *
 * ## Off unless switched on
 *
 * Logging happens only when `TERRIUM_QUERY_LOG` names a file. There is no
 * default path and no implicit location, so a deployment that has not made a
 * decision records nothing. A tool whose whole argument is that it refuses to
 * invent data should not quietly start collecting it either.
 */

import { appendFileSync, existsSync, readFileSync } from "node:fs";
import { logger } from "./logger";

export interface LoggedQuery {
  /** The query as typed. */
  query: string;
  /** What the offline keyword classifier returned for it. */
  keywordDomain: string;
  /** False when no keyword matched and the `mm` fallback was substituted --
   *  the third state, and the reason this log is worth keeping. */
  keywordMatched: boolean;
  /** Date only, no time of day: enough to bucket a term's worth of queries,
   *  not enough to correlate one person's session by timing. */
  date: string;
  /** Free-text note about where the queries came from, e.g. a course code.
   *  Set once per deployment via TERRIUM_QUERY_LOG_SOURCE. */
  source?: string;
}

/**
 * Patterns that make a query unsafe to keep verbatim.
 *
 * A student typing into a science tool should not be able to accidentally
 * commit their own email address to a file somebody later shares. These are
 * crude and will not catch everything -- which is why the redaction is
 * reported rather than silent, and why the log's documentation tells a lab to
 * read what they collected before passing it on.
 */
const REDACTIONS: { name: string; pattern: RegExp }[] = [
  { name: "email", pattern: /[\w.+-]+@[\w-]+\.[\w.-]+/g },
  { name: "url", pattern: /https?:\/\/\S+/g },
  { name: "long-number", pattern: /\b\d{7,}\b/g },
];

export interface RedactionResult {
  text: string;
  redacted: string[];
}

/**
 * Strip the patterns above, naming what was removed.
 *
 * Returns the list rather than a boolean so a caller can say *what* it
 * dropped. "Something was redacted" and "an email address was redacted" are
 * different facts, and only the second lets a lab judge whether their
 * students are pasting things they should not.
 */
export function redact(text: string): RedactionResult {
  let out = text;
  const redacted: string[] = [];
  for (const { name, pattern } of REDACTIONS) {
    if (pattern.test(out)) {
      redacted.push(name);
      out = out.replace(pattern, `[redacted:${name}]`);
    }
    pattern.lastIndex = 0;
  }
  return { text: out, redacted };
}

/** Where the log goes, or null when logging is switched off. */
export function queryLogPath(): string | null {
  const configured = process.env.TERRIUM_QUERY_LOG;
  return configured && configured.trim().length > 0 ? configured : null;
}

export interface RecordOutcome {
  /** "off" is not a failure. It is the default, and the caller should be
   *  able to tell it apart from a write that was attempted and failed. */
  state: "written" | "off" | "failed";
  redacted: string[];
  detail?: string;
}

/**
 * Append one query to the log, if logging is on.
 *
 * Never throws. A teaching lab's simulation must not fail because a log file
 * is unwritable -- but the failure is returned rather than swallowed, so a
 * caller that cares can report it and an unwritable path does not read as
 * "logging is working".
 */
export function recordQuery(
  entry: Omit<LoggedQuery, "date" | "source">,
  now: Date,
): RecordOutcome {
  const path = queryLogPath();
  if (path === null) return { state: "off", redacted: [] };

  const { text, redacted } = redact(entry.query);
  const line: LoggedQuery = {
    query: text,
    keywordDomain: entry.keywordDomain,
    keywordMatched: entry.keywordMatched,
    date: now.toISOString().slice(0, 10),
    ...(process.env.TERRIUM_QUERY_LOG_SOURCE
      ? { source: process.env.TERRIUM_QUERY_LOG_SOURCE }
      : {}),
  };

  try {
    appendFileSync(path, `${JSON.stringify(line)}\n`, "utf-8");
    return { state: "written", redacted };
  } catch (err) {
    logger.warn({ err, path }, "query log append failed");
    return {
      state: "failed",
      redacted,
      detail: err instanceof Error ? err.message : String(err),
    };
  }
}

export function readQueryLog(path: string): LoggedQuery[] {
  if (!existsSync(path)) return [];
  return readFileSync(path, "utf-8")
    .split("\n")
    .filter((line) => line.trim().length > 0)
    .map((line) => JSON.parse(line) as LoggedQuery);
}

export interface QueryLogSummary {
  total: number;
  /** Queries where no keyword matched. The number this log exists for. */
  fallbacks: number;
  fallbackRate: number;
  byDomain: Record<string, number>;
  /** Distinct queries, since a class of students often asks near-identical
   *  things and a raw count would overstate the sample. */
  distinct: number;
  sources: string[];
}

export function summariseQueryLog(entries: LoggedQuery[]): QueryLogSummary {
  const byDomain: Record<string, number> = {};
  const seen = new Set<string>();
  const sources = new Set<string>();
  let fallbacks = 0;

  for (const e of entries) {
    byDomain[e.keywordDomain] = (byDomain[e.keywordDomain] ?? 0) + 1;
    seen.add(e.query.trim().toLowerCase());
    if (e.source) sources.add(e.source);
    if (!e.keywordMatched) fallbacks++;
  }

  return {
    total: entries.length,
    fallbacks,
    // A rate over zero queries is not zero, and reporting it as zero would
    // read as "no query ever fell back".
    fallbackRate: entries.length === 0 ? Number.NaN : fallbacks / entries.length,
    byDomain,
    distinct: seen.size,
    sources: [...sources].sort(),
  };
}

/**
 * How many queries make the fallback rate worth quoting.
 *
 * Not a statistical bound -- it is a floor below which a percentage invites
 * more confidence than the sample supports. Three fallbacks out of five is
 * not "a 60% fallback rate".
 */
export const MINIMUM_QUERIES_TO_QUOTE_A_RATE = 30;

export function formatQueryLogSummary(s: QueryLogSummary): string {
  const lines = [
    `real queries logged: ${s.total} (${s.distinct} distinct)`,
    `  sources: ${s.sources.length > 0 ? s.sources.join(", ") : "unlabelled"}`,
  ];

  if (s.total < MINIMUM_QUERIES_TO_QUOTE_A_RATE) {
    lines.push(
      `  fallbacks: ${s.fallbacks} of ${s.total}`,
      `  NOT QUOTING A RATE: fewer than ${MINIMUM_QUERIES_TO_QUOTE_A_RATE} queries.`,
      "  A percentage over a handful of queries claims more than the sample supports.",
    );
  } else {
    lines.push(
      `  fallbacks: ${s.fallbacks} of ${s.total} (${(s.fallbackRate * 100).toFixed(1)}%)`,
      "  A fallback is a query no keyword matched, answered `mm` regardless.",
      "  This number needs no human labelling, which is why it comes first.",
    );
  }

  lines.push("  classified as:");
  for (const [domain, n] of Object.entries(s.byDomain).sort((a, b) => b[1] - a[1])) {
    lines.push(`    ${String(n).padStart(4)}  ${domain}`);
  }
  lines.push(
    "",
    "  Domain counts are what the CLASSIFIER said, not what the queries meant.",
    "  Turning these into an accuracy needs a human to label them; see",
    "  labelQueryLog.ts. Reading this table as accuracy would measure the",
    "  classifier against its own opinion.",
  );
  return lines.join("\n");
}
