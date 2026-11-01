/** The bundle is asked for with paths redacted and no traceback unless the reader asks for diagnostics. */
import { afterEach, describe, expect, it, vi } from "vitest";

import { downloadBundle } from "@/api/runs";

import { mockServer, setSessionToken } from "./helpers";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("downloadBundle", () => {
  it("asks for the defaults with no query, and for diagnostics or raw paths only when told to", async () => {
    setSessionToken("token");
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    vi.stubGlobal("URL", Object.assign(Object.create(URL), { createObjectURL: () => "blob:x", revokeObjectURL: () => {} }));
    const { seen } = mockServer(() => ({ status: 200, body: {} }));
    const id = "20260930-141502-compose-3f9a0c1d";
    await downloadBundle(id);
    await downloadBundle(id, { diagnostics: true });
    await downloadBundle(id, { redactPaths: false });
    const urls = seen.map((r) => r.url);
    expect(urls).toEqual([
      `/api/runs/${id}/bundle`,
      `/api/runs/${id}/bundle?diagnostics=true`,
      `/api/runs/${id}/bundle?redact_paths=false`,
    ]);
  });
});
