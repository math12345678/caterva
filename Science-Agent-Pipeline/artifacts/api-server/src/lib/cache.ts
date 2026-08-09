import { readFile, writeFile, mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { logger } from "./logger";
import type { Job, SimulationResponse } from "./queue";

const _dirname = path.dirname(fileURLToPath(import.meta.url));
const DATA_DIR = path.resolve(_dirname, "..", "data");

/** Resolve this lazily so tests and embedders can configure CACHE_FILE before use. */
function cacheFile(): string {
  return process.env["CACHE_FILE"] || path.join(DATA_DIR, "cache.json");
}

const SCHEMA_VERSION = 1;

interface CacheEntry {
  schemaVersion: number;
  createdAt: string;
  job: Job;
}

interface CacheStore {
  entries: CacheEntry[];
}

function emptyStore(): CacheStore {
  return { entries: [] };
}

function normalizeQuery(query: string): string {
  return query.trim().toLowerCase().replace(/\s+/g, " ");
}

/**
 * Ensure store is loaded into memory before operations.
 * Idempotent: safe to call multiple times.
 */
async function ensureStoreLoaded(): Promise<CacheStore> {
  if (store !== null) {
    return store;
  }
  store = await loadStore();
  return store;
}

let store: CacheStore | null = null;
// Persist operations are serialized so concurrent jobs cannot load the same
// snapshot and overwrite one another's entries.
let mutationQueue: Promise<void> = Promise.resolve();

async function ensureDataDir(): Promise<void> {
  const directory = path.dirname(cacheFile());
  if (!existsSync(directory)) {
    await mkdir(directory, { recursive: true });
  }
}

async function loadStore(): Promise<CacheStore> {
  try {
    const raw = await readFile(cacheFile(), "utf-8");
    const parsed = JSON.parse(raw) as CacheStore;
    if (Array.isArray(parsed.entries)) {
      return parsed;
    }
  } catch {
    return emptyStore();
  }
  return emptyStore();
}

async function saveStore(s: CacheStore): Promise<void> {
  await ensureDataDir();
  await writeFile(cacheFile(), JSON.stringify(s, null, 2), "utf-8");
}

/**
 * Load all cached jobs from disk into memory. Call once at startup.
 * Returns the number of restored jobs.
 */
export async function restoreCache(): Promise<number> {
  try {
    store = await loadStore();
    const count = store.entries.length;
    if (count > 0) {
      logger.info({ count }, "Restored simulation jobs from disk cache");
    }
    return count;
  } catch (err) {
    logger.warn({ err }, "Failed to restore cache; starting fresh");
    store = emptyStore();
    return 0;
  }
}

/**
 * Terminal job statuses that are safe to persist.
 */
const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled"]);

/**
 * Check if a job is in a persistable state (terminal status with result or error).
 */
function isPersistable(job: Job): boolean {
  return TERMINAL_STATUSES.has(job.status) && (!!job.result || !!job.error);
}

/**
 * Persist a completed/cancelled/failed job to disk.
 */
export function persistJob(job: Job | undefined): Promise<void> {
  if (!job || !isPersistable(job)) return Promise.resolve();

  const operation = mutationQueue.then(async () => {
    try {
      const s = await ensureStoreLoaded();
      s.entries.push({
        schemaVersion: SCHEMA_VERSION,
        createdAt: new Date().toISOString(),
        job,
      });
      await saveStore(s);
    } catch (err) {
      logger.warn(
        { err, jobId: job.jobId },
        "Failed to persist job to disk cache",
      );
    }
  });
  mutationQueue = operation;
  return operation;
}

/**
 * Return all cached jobs (oldest first).
 */
export function getCachedJobs(): Job[] {
  if (!store) return [];
  return store.entries.map((e) => e.job);
}

/**
 * Find a cached job by jobId.
 */
export function findCachedJob(jobId: string): Job | undefined {
  if (!store) return undefined;
  return store.entries.find((e) => e.job.jobId === jobId)?.job;
}

/**
 * Find a completed result by normalized query (for cache hit).
 */
export function findCachedResultByQuery(
  query: string,
): SimulationResponse | undefined {
  if (!store) return undefined;
  // Persisted entries are append-only; the newest result must win when a
  // query has been rerun with different explicit parameters such as a seed.
  for (let i = store.entries.length - 1; i >= 0; i--) {
    const entry = store.entries[i];
    if (
      entry &&
      entry.job.status === "completed" &&
      entry.job.result &&
      normalizeQuery(entry.job.query) === normalizeQuery(query)
    ) {
      return entry.job.result;
    }
  }
  return undefined;
}

/**
 * Reset the in-memory store and optionally delete the cache file.
 * Intended for test use.
 */
export function resetCache(deleteFile = false): Promise<void> {
  const operation = mutationQueue.then(async () => {
    store = emptyStore();
    if (deleteFile) {
      try {
        const { unlink } = await import("node:fs/promises");
        await unlink(cacheFile());
      } catch {
        // File may not exist
      }
    }
  });
  mutationQueue = operation;
  return operation;
}
