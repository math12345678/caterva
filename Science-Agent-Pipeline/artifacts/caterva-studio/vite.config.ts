/**
 * Vite for Caterva Studio.
 *
 * Two modes, one page:
 *
 * - `vite build` writes the page into caterva/studio/static at the
 *   repository root, where `caterva studio` serves it. index.html holds no
 *   session token: it arrives in the URL fragment of the address the server
 *   prints (docs/studio/CONTRACT.md, "Static serving"). That directory is
 *   built at release time and is not committed.
 * - `vite` (development) serves the page itself and proxies /api to the
 *   backend named by STUDIO_API, which must have been started with
 *   `--dev-origin <this server's origin>`. The token the backend minted is
 *   fetched from its /api/dev/session when index.html is served and written
 *   into a development-only meta tag, which the page reads only in
 *   development builds.
 *
 * Development only, and only while the backend at STUDIO_API does not
 * answer (a worktree whose `caterva studio` is still the contract's
 * skeleton): `/api/health` is answered here, with the checkout's version,
 * so the shell can be seen; every other /api/ path answers 503 saying the
 * server is not running. It never answers a science question and is not
 * part of the build (`apply: "serve"`).
 */
import { randomBytes } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig, type Plugin, searchForWorkspaceRoot } from "vite";

const DEV_TOKEN_META = "caterva-dev-session";
const studioApi = process.env.STUDIO_API;
const rawPort = process.env.PORT;
const port = rawPort ? Number(rawPort) : undefined;

if (rawPort && (Number.isNaN(port) || (port ?? 0) <= 0)) {
  throw new Error(`Invalid PORT value: "${rawPort}"`);
}

/** While developing only: puts the backend's session token in a meta tag of
 * the page the Vite server serves. A build never has it (apply: "serve"). */
function devMeta(token: string): string {
  return `<meta name="${DEV_TOKEN_META}" content="${token}" />`;
}

function studioDevSession(stub: DevStub): Plugin {
  return {
    name: "caterva-studio-dev-session",
    apply: "serve",
    async transformIndexHtml(html) {
      if (!studioApi) return html;
      try {
        const response = await fetch(`${studioApi}/api/dev/session`);
        if (!response.ok) return html;
        const body = (await response.json()) as { token?: unknown };
        if (typeof body.token !== "string" || !/^[A-Za-z0-9_-]+$/.test(body.token)) return html;
        stub.active = false;
        return html.replace("</head>", `${devMeta(body.token)}</head>`);
      } catch {
        // The backend is not running. The health-only stub below answers
        // instead, under a token minted for this development server.
        stub.active = true;
        return html.replace("</head>", `${devMeta(stub.token)}</head>`);
      }
    },
  };
}

interface DevStub {
  active: boolean;
  token: string;
  startedAt: string;
}

function checkoutVersion(): string {
  const init = path.resolve(import.meta.dirname, "..", "..", "..", "caterva", "__init__.py");
  const match = /__version__\s*=\s*"([^"]+)"/.exec(readFileSync(init, "utf8"));
  if (!match) throw new Error(`no __version__ in ${init}`);
  return match[1];
}

/** /api/health only, while the backend does not answer; see the header. */
function studioDevStub(stub: DevStub): Plugin {
  return {
    name: "caterva-studio-dev-health-stub",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = req.url ?? "";
        if (!stub.active || !(url === "/api" || url.startsWith("/api/"))) return next();
        const send = (status: number, body: unknown) => {
          res.statusCode = status;
          res.setHeader("Content-Type", "application/json");
          res.setHeader("Cache-Control", "no-store");
          res.end(JSON.stringify(body));
        };
        if (req.headers["x-caterva-session"] !== stub.token) {
          send(401, { error: { code: "unauthorized", message: "this request does not carry this development server's session token" } });
        } else if (req.method === "GET" && url === "/api/health") {
          send(200, { ok: true, version: checkoutVersion(), api_version: 1, started_at: stub.startedAt });
        } else {
          send(503, {
            error: {
              code: "unavailable",
              message: `The studio server at ${studioApi} is not running, so only /api/health is answered (by the development server). Start \`caterva studio --port 18740 --dev-origin <this origin>\` and reload.`,
            },
          });
        }
      });
    },
  };
}

const devStub: DevStub = {
  active: false,
  token: randomBytes(24).toString("base64url"),
  startedAt: new Date().toISOString().replace(/\.\d+Z$/, "Z"),
};

export default defineConfig({
  base: "/",
  plugins: [react(), tailwindcss(), studioDevSession(devStub), studioDevStub(devStub)],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "src") },
    dedupe: ["react", "react-dom"],
  },
  root: path.resolve(import.meta.dirname),
  build: {
    // Science-Agent-Pipeline/artifacts/caterva-studio -> <repo>/caterva/studio/static
    outDir: path.resolve(import.meta.dirname, "..", "..", "..", "caterva", "studio", "static"),
    emptyOutDir: true,
    assetsDir: "assets",
    target: "es2022",
    sourcemap: false,
    rollupOptions: {
      output: {
        // Only React is split by hand. Charts and the 3D viewer are reached
        // through lazy screens, so Rollup splits them where they are used;
        // naming them here would create chunks the first paint preloads.
        manualChunks: { react: ["react", "react-dom"] },
      },
    },
  },
  server: {
    host: "127.0.0.1",
    port,
    strictPort: true,
    // The workspace, plus the one file outside it the page imports: About
    // reads docs/data-sources.json, the attribution table the exports use.
    fs: {
      strict: true,
      allow: [
        searchForWorkspaceRoot(import.meta.dirname),
        path.resolve(import.meta.dirname, "..", "..", "..", "docs", "data-sources.json"),
      ],
    },
    proxy: studioApi
      ? {
          "/api": { target: studioApi, changeOrigin: true, ws: false },
        }
      : undefined,
  },
  preview: { host: "127.0.0.1", port, strictPort: true },
});
