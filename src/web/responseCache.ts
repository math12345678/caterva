/**
 * A small TTL cache for read endpoints, and the stats behind
 * `GET /api/cache/stats`.
 *
 * WHY IT EXISTS
 * -------------
 * API_PERFORMANCE_GUIDE.md documented `/api/cache/stats` in seven places
 * and a caching layer that made metrics endpoints "98.8% faster", and
 * neither existed. This implements what was already promised.
 *
 * WHAT IT WILL NOT CACHE
 * ----------------------
 * Only endpoints on ALLOWLIST are cached, and it holds read-only aggregate
 * routes exclusively.
 *
 * A deny-list would be the wrong shape. Getting a deny-list wrong caches
 * something it should not have, silently, and the failure surfaces as a
 * user seeing another user's data — the worst outcome in the system. Getting
 * an allow-list wrong just fails to cache something, which is slow and
 * correct. When one direction of error is invisible and the other is merely
 * inefficient, the default belongs on the inefficient side.
 *
 * Cache keys include the full query string. A cache keyed on pathname alone
 * would serve `?limit=10` results to a caller asking for `?limit=1000`.
 */

export interface CacheStats {
  entries: number;
  hits: number;
  misses: number;
  /** null, not 0, when nothing has been looked up yet: an untouched cache
   * has no hit rate, and reporting 0% would read as "the cache is useless"
   * rather than "the cache has not been asked anything". */
  hitRate: number | null;
  evictions: number;
  expirations: number;
  ttlSeconds: number;
  maxEntries: number;
  cachedEndpoints: string[];
  notes: string[];
}

interface Entry {
  body: string;
  expiresAt: number;
}

export const DEFAULT_TTL_MS = 10_000;
export const MAX_ENTRIES = 200;

/**
 * Read-only aggregate endpoints. Every one of these recomputes the same
 * answer from the same in-memory state on each call, which is exactly what
 * a short TTL is for.
 *
 * Deliberately absent: anything under `/api/jobs`, `/api/sweeps` or
 * `/api/batches` that addresses a single record, because those change as a
 * job progresses and a stale one shows a finished run as still pending.
 * Also absent: `/api/perf` and `/api/cache/stats` themselves — a cached
 * metrics endpoint reports the state of the system as it was, which is the
 * one moment an operator is not asking about.
 */
export const ALLOWLIST: ReadonlySet<string> = new Set([
  "/api/metrics",
  "/api/metrics/by-model",
  "/api/metrics/reproducibility",
  "/api/metrics/failed-queries",
  "/api/metrics/sweeps",
  "/api/metrics/sweeps-by-query",
  "/api/metrics/batches",
  "/api/metrics/batches-by-query",
  "/api/stats",
]);

const store = new Map<string, Entry>();
let hits = 0;
let misses = 0;
let evictions = 0;
let expirations = 0;

export function isCacheable(pathname: string, method: string): boolean {
  return method === "GET" && ALLOWLIST.has(pathname);
}

export function cacheKey(pathname: string, search: string): string {
  return search ? `${pathname}${search}` : pathname;
}

export function readCache(key: string, now = Date.now()): string | null {
  const entry = store.get(key);
  if (!entry) {
    misses += 1;
    return null;
  }
  if (entry.expiresAt <= now) {
    store.delete(key);
    expirations += 1;
    misses += 1;
    return null;
  }
  hits += 1;
  return entry.body;
}

export function writeCache(
  key: string,
  body: string,
  now = Date.now(),
  ttlMs = DEFAULT_TTL_MS,
): void {
  // Evict the oldest insertion when full. Map preserves insertion order, so
  // this is FIFO rather than LRU — chosen because these entries all expire
  // within seconds anyway, and an LRU's bookkeeping would cost more than
  // the imprecision saves.
  if (store.size >= MAX_ENTRIES && !store.has(key)) {
    const oldest = store.keys().next();
    if (!oldest.done) {
      store.delete(oldest.value);
      evictions += 1;
    }
  }
  store.set(key, { body, expiresAt: now + ttlMs });
}

export function getCacheStats(): CacheStats {
  const lookups = hits + misses;
  return {
    entries: store.size,
    hits,
    misses,
    hitRate: lookups === 0 ? null : (hits / lookups) * 100,
    evictions,
    expirations,
    ttlSeconds: DEFAULT_TTL_MS / 1000,
    maxEntries: MAX_ENTRIES,
    cachedEndpoints: [...ALLOWLIST].sort(),
    notes: [
      "Only read-only aggregate endpoints are cached, by allowlist. A " +
        "deny-list would fail invisibly in the direction that shows one " +
        "caller another caller's data.",
      "Per-record routes (/api/jobs/:id, /api/sweeps/:id, /api/batches/:id) " +
        "are never cached: a stale entry would show a finished run as " +
        "pending.",
      "/api/perf and /api/cache/stats are not cached — an operator asking " +
        "about now should not be told about ten seconds ago.",
    ],
  };
}

/** Test seam. */
export function resetCache(): void {
  store.clear();
  hits = 0;
  misses = 0;
  evictions = 0;
  expirations = 0;
}
