// orval APPENDS to this file on every codegen run rather than replacing it,
// so duplicate `export *` lines accumulate. A duplicated `export *` is a
// no-op, which is why it went unnoticed for several runs -- but the file
// grows every regeneration and eventually the noise hides a real export
// that got dropped.
//
// Deduped by hand, order preserved. The `custom-fetch` exports below are
// HAND-WRITTEN and are not regenerated: a future dedupe must not assume
// everything in this file came from orval.
export * from "./generated/api";
export * from "./generated/api.schemas";
export { setBaseUrl, setAuthTokenGetter } from "./custom-fetch";
export type { AuthTokenGetter } from "./custom-fetch";
