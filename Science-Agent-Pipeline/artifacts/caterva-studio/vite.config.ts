/**
 * Vite for Caterva Studio.
 *
 * Two modes, one page:
 *
 * - `vite build` writes the page into caterva/studio/static at the
 *   repository root, where `caterva studio` serves it and replaces the
 *   session-token placeholder in index.html (docs/studio/CONTRACT.md,
 *   "Static serving"). That directory is built at release time and is not
 *   committed.
 * - `vite` (development) serves the page itself and proxies /api to the
 *   backend named by STUDIO_API, which must have been started with
 *   `--dev-origin <this server's origin>`. The token the backend minted is
 *   fetched from its /api/dev/session when index.html is served, and written
 *   into the same meta tag, so the page reads it the same way in both modes.
 */
import path from "node:path";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig, type Plugin } from "vite";

const TOKEN_PLACEHOLDER = "__CATERVA_SESSION_TOKEN__";
const studioApi = process.env.STUDIO_API;
const rawPort = process.env.PORT;
const port = rawPort ? Number(rawPort) : undefined;

if (rawPort && (Number.isNaN(port) || (port ?? 0) <= 0)) {
  throw new Error(`Invalid PORT value: "${rawPort}"`);
}

/** Writes the backend's session token into index.html while developing. */
function studioDevSession(): Plugin {
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
        return html.replace(TOKEN_PLACEHOLDER, body.token);
      } catch {
        // The backend is not running yet. The page says so (it finds the
        // placeholder still in place) instead of this server failing.
        return html;
      }
    },
  };
}

export default defineConfig({
  base: "/",
  plugins: [react(), tailwindcss(), studioDevSession()],
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
    fs: { strict: true },
    proxy: studioApi
      ? {
          "/api": { target: studioApi, changeOrigin: true, ws: false },
        }
      : undefined,
  },
  preview: { host: "127.0.0.1", port, strictPort: true },
});
