import { pgTable, text, timestamp, uuid, jsonb } from "drizzle-orm/pg-core";

/**
 * Persisted science-agent pipeline run.
 *
 * This table stores the input query, resolved domain/params, and the raw
 * engine output. Keeping it in the API layer (rather than the frontend) means
 * OpenCode can later add a real LLM/agent step, rerun old queries, or audit
 * provenance without touching the UI.
 */
export const simulationsTable = pgTable("simulations", {
  id: uuid("id").primaryKey().defaultRandom(),
  query: text("query").notNull(),
  domain: text("domain", {
    enum: [
      "mm",
      "sir",
      "seir",
      "pcr",
      "monte_carlo_pi",
      "wright_fisher",
      "two_locus_wright_fisher",
      "molecular_dynamics",
      "gillespie_ssa",
      "gillespie_ssa_bimolecular",
      "gillespie_ssa_replicates",
      "sbml",
    ],
  }).notNull(),
  parameters: jsonb("parameters").notNull().default({}),
  trajectory: jsonb("trajectory").notNull().default([]),
  provenance: jsonb("provenance").notNull().default({}),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
});

export type Simulation = typeof simulationsTable.$inferSelect;
export type InsertSimulation = typeof simulationsTable.$inferInsert;
