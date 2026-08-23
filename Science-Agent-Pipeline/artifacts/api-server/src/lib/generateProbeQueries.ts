/**
 * Generate a test set the benchmark's author did not phrase.
 *
 * Why this exists. The `heldout` set in `classifierQueries.ts` was written
 * before any classifier tuning, which is the usual precaution -- and it was
 * not enough. The same person then widened the keyword vocabulary from the
 * same source those queries came from (each domain's definition), so the
 * vocabulary matched the phrasing by construction and the set scored 100%.
 * A hundred percent is not a result; it is a warning that the test and the
 * thing under test share an author.
 *
 * So this asks an LLM to write the questions instead. It is shown only
 * `DOMAIN_MEANINGS[domain]` -- one sentence, the same sentence the resolver
 * is shown -- and never the keyword table. The phrasing that comes back is
 * not the benchmark author's, which is the only property that matters here.
 *
 * What the label means, precisely: it is the domain this generator *asked*
 * for. That is a real assumption and it can be wrong -- a model asked for a
 * `seir` question may write one better answered by `sir`. The set is
 * therefore noisy in a way a human-curated set is not, and a score on it
 * should be read as "agreement with the domain the query was commissioned
 * for", not as ground truth. It is committed as a fixture so the scoring is
 * reproducible offline and so a reader can judge the queries themselves
 * rather than trust this description of them.
 */

import { writeFileSync } from "node:fs";
import { DOMAIN_MEANINGS } from "./llmResolver";
import { logger } from "./logger";

/** Domains the resolver exposes. Engine-internal domains are excluded. */
const GENERATED_DOMAINS = Object.keys(DOMAIN_MEANINGS);

export interface GeneratedQuery {
  query: string;
  /** The domain this query was commissioned for. See the note above on what
   *  this does and does not assert. */
  expected: string;
}

export interface ProbeSet {
  /** Provenance, written into the fixture so it travels with the data. */
  _generatedBy: string;
  _model: string;
  _promptShownToTheModel: string;
  _labelMeans: string;
  queries: GeneratedQuery[];
}

const INSTRUCTION = (domain: string, meaning: string, n: number) =>
  `A student is using a simulation tool for a teaching lab. One thing it can simulate is:\n\n` +
  `  ${meaning}\n\n` +
  `Write ${n} different questions a student might type to ask for that simulation.\n\n` +
  `Rules:\n` +
  `- Write the way a student actually types: plain language, not jargon from a textbook index.\n` +
  `- Vary the phrasing a lot between the ${n}. Different verbs, different framings, different lengths.\n` +
  `- Do NOT use the identifier "${domain}" anywhere.\n` +
  `- Do not include any numbers or parameter values.\n` +
  `- Return ONLY a JSON array of ${n} strings. No prose, no markdown fences.`;

async function askForQueries(
  domain: string,
  meaning: string,
  n: number,
): Promise<string[]> {
  const apiKey =
    process.env.LLM_API_KEY ||
    process.env.OPENAI_API_KEY ||
    process.env[`${(process.env.LLM_PROVIDER ?? "").toUpperCase()}_API_KEY`];
  if (!apiKey) throw new Error("no LLM API key; cannot generate a probe set");

  const url =
    process.env.LLM_API_URL ??
    "https://api.groq.com/openai/v1/chat/completions";
  const model = process.env.LLM_MODEL ?? "openai/gpt-oss-120b";

  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      model,
      temperature: 1,
      messages: [{ role: "user", content: INSTRUCTION(domain, meaning, n) }],
    }),
  });

  if (!response.ok) {
    throw new Error(`${domain}: HTTP ${response.status} ${await response.text()}`);
  }

  const data = (await response.json()) as {
    choices?: { message?: { content?: string } }[];
  };
  const content = data.choices?.[0]?.message?.content ?? "";
  const start = content.indexOf("[");
  const end = content.lastIndexOf("]");
  if (start === -1 || end === -1) {
    throw new Error(`${domain}: no JSON array in response`);
  }
  const parsed: unknown = JSON.parse(content.slice(start, end + 1));
  if (!Array.isArray(parsed)) throw new Error(`${domain}: not an array`);
  return parsed.filter((q): q is string => typeof q === "string" && q.length > 0);
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export async function generateProbeSet(
  perDomain: number,
  pacingMs: number,
): Promise<ProbeSet> {
  const queries: GeneratedQuery[] = [];
  for (const domain of GENERATED_DOMAINS) {
    const meaning = DOMAIN_MEANINGS[domain]!;
    try {
      const written = await askForQueries(domain, meaning, perDomain);
      for (const q of written) queries.push({ query: q, expected: domain });
      logger.info({ domain, count: written.length }, "generated probe queries");
    } catch (err) {
      // A domain that could not be generated is dropped and said so. It is
      // not silently replaced with a hand-written query, which would put the
      // author's phrasing back into the one set that exists to exclude it.
      logger.warn({ domain, err }, "probe generation failed for domain");
    }
    await sleep(pacingMs);
  }

  return {
    _generatedBy:
      "scripts: src/lib/generateProbeQueries.ts -- queries written by an LLM, " +
      "not by the benchmark author, to break the shared-author bias described " +
      "in that file's header.",
    _model: process.env.LLM_MODEL ?? "openai/gpt-oss-120b",
    _promptShownToTheModel:
      "one line from DOMAIN_MEANINGS per domain; the keyword table was never shown",
    _labelMeans:
      "the domain the query was commissioned for, NOT independently verified ground truth",
    queries,
  };
}

const outPath = process.argv[2];
if (outPath) {
  const perDomain = Number.parseInt(process.argv[3] ?? "6", 10);
  const set = await generateProbeSet(perDomain, 7_000);
  writeFileSync(outPath, `${JSON.stringify(set, null, 2)}\n`);
  console.log(
    `wrote ${set.queries.length} queries across ` +
      `${new Set(set.queries.map((q) => q.expected)).size} domains to ${outPath}`,
  );
}
