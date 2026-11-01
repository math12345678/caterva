/**
 * Database module.
 *
 * The database client is lazy in every respect: importing this module does
 * no work and loads no heavy dependency. The Postgres driver (`pg`), the
 * node-postgres Drizzle adapter, and the table schema are only imported on
 * the first call to `getDb()`/`isDbAvailable()`, so a process that never
 * queries the database (tests, a server booted without DATABASE_URL) never
 * pays to evaluate them. Callers must use `getDb()` or check
 * `isDbAvailable()` before querying. This lets the API server start without
 * a DATABASE_URL and degrade gracefully when the database is unavailable.
 *
 * The schema is reachable at the `@workspace/db/schema` entry point for
 * consumers that need the table object; load it lazily too so the Drizzle
 * query builder is not evaluated at module load.
 */
import type { NodePgDatabase } from "drizzle-orm/node-postgres";

type Db = NodePgDatabase<typeof import("./schema")>;

let dbInstance: Db | null = null;
let connectionError: Error | null = null;

async function initializeDb(): Promise<Db | null> {
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
    const [drizzleModule, pgModule, schema] = await Promise.all([
      import("drizzle-orm/node-postgres"),
      import("pg"),
      import("./schema"),
    ]);
    const { Pool } = pgModule.default ?? pgModule;
    const pool = new Pool({ connectionString: url });
    dbInstance = drizzleModule.drizzle(pool, { schema });
    return dbInstance;
  } catch (err) {
    connectionError = err instanceof Error ? err : new Error(String(err));
    return null;
  }
}

/**
 * Returns the Drizzle database client, or null if the database is not
 * configured. This is lazy: the first call loads the driver, the adapter,
 * and the schema, creates the client and caches it; subsequent calls reuse
 * it.
 *
 * Keeping the client lazy lets the API server start without a DATABASE_URL
 * and degrade gracefully when the database is unavailable.
 */
export async function getDb(): Promise<Db | null> {
  return initializeDb();
}

/**
 * Returns true if the database is configured and can be initialized.
 *
 * Like `getDb()`, this loads the driver and schema on first use rather than
 * at module import.
 */
export async function isDbAvailable(): Promise<boolean> {
  return (await initializeDb()) !== null;
}
