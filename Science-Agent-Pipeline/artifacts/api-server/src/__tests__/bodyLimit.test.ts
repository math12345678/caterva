/**
 * The JSON body limit must fit the engine's largest legitimate model, and
 * an oversize body must be refused as itself (413), not reported as an
 * internal error.
 *
 * The engine's ceilings say how large a legitimate request can be:
 * `MAX_API_SBML_SOURCE_CHARS` admits a 400,000-character SBML source, and
 * the network ceilings admit 200 reactions whose rate laws may each run to
 * 1,000 characters -- a maximal model is well over 100 KB in JSON. The
 * default `express.json()` limit is 100 KB, so a model those ceilings admit
 * was refused by the transport before the engine ever saw it.
 *
 * What made that refusal dangerous was the error handler: it ignored
 * `err.status`, so body-parser's `entity.too.large` (status 413) was
 * flattened into a 500 INTERNAL_SERVER_ERROR. A caller whose model was
 * simply too big was told the server was broken.
 */
import { describe, expect, it } from "vitest";
import request from "supertest";
import { mkdtempSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

process.env["CACHE_FILE"] = join(
  mkdtempSync(join(tmpdir(), "body-limit-")),
  "cache.json",
);

const app = (await import("../app")).default;

describe("request body size", () => {
  it("parses a body above the old 100KB default when the shape is invalid", async () => {
    // ~150 KB of payload: syntactically valid JSON, wrong shape. If the
    // body made it through the parser the schema rejects it with a 400; if
    // the old 100KB default still held, body-parser would have failed first.
    const big = { network: "x".repeat(150_000) };
    const res = await request(app)
      .post("/api/simulate/parameterize")
      .send(big)
      .expect(400);
    expect(res.body.error).toBe("BAD_REQUEST");
  });

  it("refuses a body above the raised limit as 413, not 500", async () => {
    const huge = { network: "y".repeat(1_100_000) };
    const res = await request(app)
      .post("/api/simulate/parameterize")
      .send(huge);
    expect(res.status).toBe(413);
    expect(res.body.error).toBe("REQUEST_TOO_LARGE");
    expect(res.body.message).toBeTruthy();
  });
});