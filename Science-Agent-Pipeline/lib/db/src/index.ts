/**
 * Database module.
 *
 * The database client is lazy: callers must use `getDb()` or check
 * `isDbAvailable()` before querying. This lets the API server start without
 * a DATABASE_URL and degrade gracefully when the database is unavailable.
 */
import { drizzle } from "drizzle-orm/node-postgres";
import pg from "pg";
import * as schema from "./schema";

const { Pool } = pg;

let dbInstance: ReturnType<typeof drizzle<typeof schema>> | null = null;
let connectionError: Error | null = null;

function initializeDb() {
  if (dbInstance) return dbInstance;
  if (connectionError) return null;

  const url = process.env.DATABASE_URL;
  if (!url) {
    connectionError = new Error(
      "DATABASE_URL must be set. Did you forget to provision a database?",
    );
    return null;
  }

  try {
    const pool = new Pool({ connectionString: url });
    dbInstance = drizzle(pool, { schema });
    return dbInstance;
  } catch (err) {
    connectionError = err instanceof Error ? err : new Error(String(err));
    return null;
  }
}

/**
 * Returns the Drizzle database client, or null if the database is not
 * configured. This is lazy: the first call creates the client; subsequent
 * calls reuse it.
 *
 * Keeping the connection lazy lets the API server start without a
 * DATABASE_URL and degrade gracefully when the database is unavailable.
 */
export function getDb(): ReturnType<typeof drizzle<typeof schema>> | null {
  return initializeDb();
}

/**
 * Returns true if the database is configured and can be initialized.
 */
export function isDbAvailable(): boolean {
  return initializeDb() !== null;
}

export * from "./schema";
