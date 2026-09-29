/**
 * The query log: off by default, redacted, and honest about small samples.
 *
 * This is the first thing in the repository that records what a person
 * typed, so the tests that matter most are the ones asserting it does not do
 * that unless somebody switched it on.
 */

import { mkdtempSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  MINIMUM_QUERIES_TO_QUOTE_A_RATE,
  formatQueryLogSummary,
  queryLogPath,
  readQueryLog,
  recordQuery,
  redact,
  summariseQueryLog,
  type LoggedQuery,
} from "../lib/queryLog";

let dir: string;
let saved: Record<string, string | undefined>;

const VARS = ["TERRIUM_QUERY_LOG", "TERRIUM_QUERY_LOG_SOURCE"];

beforeEach(() => {
  dir = mkdtempSync(path.join(tmpdir(), "terrium-querylog-"));
  saved = {};
  for (const v of VARS) {
    saved[v] = process.env[v];
    delete process.env[v];
  }
});

afterEach(() => {
  for (const v of VARS) {
    if (saved[v] === undefined) delete process.env[v];
    else process.env[v] = saved[v];
  }
});

const AT = new Date("2026-08-23T14:31:07Z");

describe("logging is off unless switched on", () => {
  it("reports off, not written, when TERRIUM_QUERY_LOG is unset", () => {
    const outcome = recordQuery(
      { query: "how fast does LDH work", keywordDomain: "mm", keywordMatched: true },
      AT,
    );
    expect(outcome.state).toBe("off");
  });

  it("writes nothing to disk when off", () => {
    // The assertion that matters. A tool whose argument is that it refuses to
    // invent data should not quietly start collecting it either.
    const wouldBe = path.join(dir, "queries.jsonl");
    recordQuery(
      { query: "how fast does LDH work", keywordDomain: "mm", keywordMatched: true },
      AT,
    );
    expect(existsSync(wouldBe)).toBe(false);
  });

  it("treats an empty or whitespace path as off, not as a filename", () => {
    process.env.TERRIUM_QUERY_LOG = "   ";
    expect(queryLogPath()).toBeNull();
    expect(
      recordQuery({ query: "x", keywordDomain: "mm", keywordMatched: true }, AT).state,
    ).toBe("off");
  });

  it("writes when a path is given", () => {
    const file = path.join(dir, "queries.jsonl");
    process.env.TERRIUM_QUERY_LOG = file;
    expect(
      recordQuery(
        { query: "model a flu outbreak", keywordDomain: "sir", keywordMatched: true },
        AT,
      ).state,
    ).toBe("written");
    const written = readQueryLog(file);
    expect(written).toHaveLength(1);
    expect(written[0]!.query).toBe("model a flu outbreak");
    expect(written[0]!.keywordDomain).toBe("sir");
  });
});

describe("what is written", () => {
  it("records the date but not the time of day", () => {
    const file = path.join(dir, "q.jsonl");
    process.env.TERRIUM_QUERY_LOG = file;
    recordQuery({ query: "x", keywordDomain: "mm", keywordMatched: true }, AT);
    const [entry] = readQueryLog(file);
    expect(entry!.date).toBe("2026-08-23");
    // Time of day would let sessions be correlated by timing, which is the
    // kind of identifier this log exists without.
    expect(JSON.stringify(entry)).not.toContain("14:31");
  });

  it("carries no user, session, request or address field", () => {
    const file = path.join(dir, "q.jsonl");
    process.env.TERRIUM_QUERY_LOG = file;
    recordQuery({ query: "x", keywordDomain: "mm", keywordMatched: true }, AT);
    const keys = Object.keys(readQueryLog(file)[0] as object);
    for (const forbidden of ["user", "userId", "session", "sessionId", "ip", "requestId", "headers"]) {
      expect(keys).not.toContain(forbidden);
    }
  });

  it("records the fallback state, which is the reason the log exists", () => {
    const file = path.join(dir, "q.jsonl");
    process.env.TERRIUM_QUERY_LOG = file;
    recordQuery({ query: "x", keywordDomain: "mm", keywordMatched: false }, AT);
    expect(readQueryLog(file)[0]!.keywordMatched).toBe(false);
  });

  it("includes a source label only when one is configured", () => {
    const file = path.join(dir, "q.jsonl");
    process.env.TERRIUM_QUERY_LOG = file;
    recordQuery({ query: "a", keywordDomain: "mm", keywordMatched: true }, AT);
    process.env.TERRIUM_QUERY_LOG_SOURCE = "BIOL201";
    recordQuery({ query: "b", keywordDomain: "mm", keywordMatched: true }, AT);
    const [first, second] = readQueryLog(file);
    expect(first!.source).toBeUndefined();
    expect(second!.source).toBe("BIOL201");
  });
});

describe("redaction", () => {
  it.each([
    ["email me at ada@example.com about kinetics", "email"],
    ["see https://example.com/notes for the assay", "url"],
    ["my student id is 20315567 running LDH", "long-number"],
  ])("removes %j and names what it removed", (input, expected) => {
    const { text, redacted } = redact(input);
    expect(redacted).toContain(expected);
    expect(text).toContain(`[redacted:${expected}]`);
  });

  it("leaves an ordinary scientific query untouched", () => {
    // The half that stops "redact" meaning "mangle". Small numbers are
    // parameters, not identifiers.
    const query = "run michaelis menten with km=0.03 and s0=10 for 51 points";
    const { text, redacted } = redact(query);
    expect(text).toBe(query);
    expect(redacted).toEqual([]);
  });

  it("redacts before anything reaches the file", () => {
    const file = path.join(dir, "q.jsonl");
    process.env.TERRIUM_QUERY_LOG = file;
    recordQuery(
      { query: "ping me at ada@example.com", keywordDomain: "mm", keywordMatched: false },
      AT,
    );
    expect(readFileSync(file, "utf-8")).not.toContain("ada@example.com");
  });
});

describe("a failed write is not a silent success", () => {
  it("reports failed, not written, when the path is unwritable", () => {
    process.env.TERRIUM_QUERY_LOG = path.join(dir, "no-such-dir", "q.jsonl");
    const outcome = recordQuery(
      { query: "x", keywordDomain: "mm", keywordMatched: true },
      AT,
    );
    expect(outcome.state).toBe("failed");
    expect(outcome.detail).toBeTruthy();
  });
});

describe("the summary", () => {
  const entries = (n: number, fallbacks: number): LoggedQuery[] =>
    Array.from({ length: n }, (_, i) => ({
      query: `query number ${i}`,
      keywordDomain: i < fallbacks ? "mm" : "sir",
      keywordMatched: i >= fallbacks,
      date: "2026-08-23",
    }));

  it("counts distinct queries separately from total", () => {
    const s = summariseQueryLog([
      { query: "same", keywordDomain: "mm", keywordMatched: true, date: "2026-08-23" },
      { query: "SAME ", keywordDomain: "mm", keywordMatched: true, date: "2026-08-23" },
    ]);
    expect(s.total).toBe(2);
    // A class asking near-identical things would otherwise overstate the
    // sample size.
    expect(s.distinct).toBe(1);
  });

  it("refuses to quote a rate below the minimum sample", () => {
    const text = formatQueryLogSummary(summariseQueryLog(entries(5, 3)));
    expect(text).toContain("NOT QUOTING A RATE");
    expect(text).not.toContain("60.0%");
  });

  it("quotes a rate once there are enough queries", () => {
    const n = MINIMUM_QUERIES_TO_QUOTE_A_RATE;
    const text = formatQueryLogSummary(summariseQueryLog(entries(n, n / 2)));
    expect(text).not.toContain("NOT QUOTING A RATE");
    expect(text).toContain("50.0%");
  });

  it("gives NaN, not zero, for the rate over an empty log", () => {
    // Zero would read as "no query ever fell back", which is a claim. There
    // is no rate over no queries.
    expect(summariseQueryLog([]).fallbackRate).toBeNaN();
  });

  it("says the domain counts are the classifier's opinion, not accuracy", () => {
    const text = formatQueryLogSummary(summariseQueryLog(entries(40, 10)));
    expect(text).toContain("what the CLASSIFIER said, not what the queries meant");
  });
});

describe("reading a log", () => {
  it("returns nothing for a file that does not exist", () => {
    expect(readQueryLog(path.join(dir, "absent.jsonl"))).toEqual([]);
  });

  it("ignores blank lines rather than failing on them", () => {
    const file = path.join(dir, "q.jsonl");
    writeFileSync(
      file,
      '{"query":"a","keywordDomain":"mm","keywordMatched":true,"date":"2026-08-23"}\n\n',
    );
    expect(readQueryLog(file)).toHaveLength(1);
  });
});
