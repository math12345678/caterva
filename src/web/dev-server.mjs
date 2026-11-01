#!/usr/bin/env node
/**
 * Dev server for the Caterva dashboard.
 *
 * The dashboard is normally served by `src/web/server.ts`, which lives in
 * the `backend-main` repository. Cloned on its own, `frontend-main` would
 * be one HTML file with no way to open it against a running API — and
 * opening it from `file://` fails, because the browser blocks the fetch
 * calls as cross-origin.
 *
 * This serves the page and proxies `/api/*` to wherever the backend is
 * running, so the front end can be worked on without the backend repo
 * checked out beside it.
 *
 *   node dev-server.mjs                       # :5173, API on :3000
 *   PORT=8080 API=http://localhost:4000 node dev-server.mjs
 *
 * No dependencies — Node's built-in http and fs only.
 */

import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = fileURLToPath(new URL(".", import.meta.url));
const PORT = Number(process.env.PORT ?? 5173);
const API = process.env.API ?? "http://localhost:3000";

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
};

const server = createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", `http://localhost:${PORT}`);

  // Proxy the API rather than mocking it. A mock would drift from the real
  // server, and this project has spent a lot of effort removing exactly that
  // kind of second source of truth.
  if (url.pathname.startsWith("/api/")) {
    try {
      const upstream = await fetch(`${API}${url.pathname}${url.search}`, {
        method: req.method,
        headers: { "content-type": req.headers["content-type"] ?? "application/json" },
        body: ["GET", "HEAD"].includes(req.method ?? "GET") ? undefined : req,
        duplex: "half",
      });
      res.writeHead(upstream.status, {
        "content-type": upstream.headers.get("content-type") ?? "application/json",
      });
      res.end(Buffer.from(await upstream.arrayBuffer()));
    } catch (err) {
      // Say which address failed. "fetch failed" with no target is the
      // least useful error a proxy can produce.
      res.writeHead(502, { "content-type": "application/json" });
      res.end(
        JSON.stringify({
          error: "UPSTREAM_UNREACHABLE",
          message:
            `Could not reach the Caterva API at ${API}${url.pathname}. ` +
            `Start it with \`npm run web\` in the backend-main repository, ` +
            `or point this proxy elsewhere with API=<url>.`,
          cause: String(err?.cause?.code ?? err?.message ?? err),
        }),
      );
    }
    return;
  }

  const file = url.pathname === "/" ? "dashboard.html" : url.pathname.slice(1);
  try {
    const body = await readFile(join(HERE, file));
    res.writeHead(200, { "content-type": TYPES[extname(file)] ?? "application/octet-stream" });
    res.end(body);
  } catch {
    res.writeHead(404, { "content-type": "text/plain" });
    res.end(`Not found: ${file}`);
  }
});

server.listen(PORT, () => {
  console.log(`Caterva dashboard   http://localhost:${PORT}`);
  console.log(`proxying /api/*  ->  ${API}`);
  console.log(`\nIf calls return 502, the backend is not running. In backend-main:`);
  console.log(`    npm run web`);
});
