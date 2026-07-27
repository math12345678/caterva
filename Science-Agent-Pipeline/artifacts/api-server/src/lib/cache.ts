import { readFile, writeFile, mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { logger } from "./logger";
import type { Job, SimulationResponse } from "./queue";

const _dirname = path.dirname(fileURLToPath(import.meta.url));
const DATA_DIR = path.resolve(_dirname, "..", "data");
const CACHE_FILE = process.env["CACHE_FILE"] || path.join(DATA_DIR, "cache.json");

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

let store: CacheStore | null = null;

async function ensureDataDir(): Promise<void> {
  if (!existsSync(DATA_DIR)) {
    await mkdir(DATA_DIR, { recursive: true });
  }
}

async function loadStore(): Promise<CacheStore> {
  try {
    const raw = await readFile(CACHE_FILE, "utf-8");
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
  await writeFile(CACHE_FILE, JSON.stringify(s, null, 2), "utf-8");
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
 * Persist a completed/cancelled/failed job to disk.
 */
export async function persistJob(job: Job): Promise<void> {
  if (!job.result && !job.error) return;
  if (job.status !== "completed" && job.status !== "failed" && job.status !== "cancelled") return;

  try {
    if (!store) {
      store = await loadStore();
    }
    store.entries.push({
      schemaVersion: SCHEMA_VERSION,
      createdAt: new Date().toISOString(),
      job,
    });
    await saveStore(store);
  } catch (err) {
    logger.warn({ err, jobId: job.jobId }, "Failed to persist job to disk cache");
  }
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
export function findCachedResultByQuery(query: string): SimulationResponse | undefined {
  if (!store) return undefined;
  for (const entry of store.entries) {
    if (entry.job.status === "completed" && entry.job.result && entry.job.query === query) {
      return entry.job.result;
    }
  }
  return undefined;
}

/**
 * Reset the in-memory store and optionally delete the cache file.
 * Intended for test use.
 */
export async function resetCache(deleteFile = false): Promise<void> {
  store = emptyStore();
  if (deleteFile) {
    try {
      const { unlink } = await import("node:fs/promises");
      await unlink(CACHE_FILE);
    } catch {
      // File may not exist
    }
  }
}
