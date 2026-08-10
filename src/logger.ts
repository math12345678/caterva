/**
 * Structured logger for the root scientific-validation tree.
 *
 * This module did not exist. `scientificPipeline.ts`,
 * `literatureService.ts`, `reproducibilityEngine.ts` and
 * `scientificValidator.ts` all opened with `import { logger } from
 * '../logger'` against a file nobody had written, so every one of them
 * failed to resolve at compile time and at require time. The consequence
 * was not cosmetic: `package.json` advertises a `bin` entry
 * (`scientific` -> `src/cli/scientificCLI.ts`) and an `example` script,
 * and both crashed on startup with TS2307. Nothing in this tree had ever
 * run. It went unnoticed because the tree had no tsconfig.json, so the
 * `type-check` and `build` scripts pointed at a compiler with no inputs
 * and no guard in scripts/ covered the region.
 *
 * The call sites use pino's object-first signature -- `logger.info({ jobId
 * }, 'Simulation started')` -- so that shape is what this implements.
 *
 * It is NOT pino, deliberately. The api-server workspace uses pino
 * (Science-Agent-Pipeline/artifacts/api-server/src/lib/logger.ts) but this
 * tree is a separate package whose `dependencies` are `{}`. Adding a
 * runtime dependency to un-break an import would mean this tree cannot be
 * built or run without a network fetch, and the point here is to make it
 * work with what is already present. The exported surface is a strict
 * subset of pino's, so swapping in real pino later requires changing this
 * file only.
 */

/** Severity levels, ordered least to most severe (syslog-style ordering,
 *  matching pino's numeric levels so LOG_LEVEL values transfer). */
const LEVELS = ["trace", "debug", "info", "warn", "error", "fatal"] as const;

export type Level = (typeof LEVELS)[number];

/** Arbitrary structured fields merged into the emitted record. */
export type Bindings = Record<string, unknown>;

export interface Logger {
  trace(bindings: Bindings, message?: string): void;
  trace(message: string): void;
  debug(bindings: Bindings, message?: string): void;
  debug(message: string): void;
  info(bindings: Bindings, message?: string): void;
  info(message: string): void;
  warn(bindings: Bindings, message?: string): void;
  warn(message: string): void;
  error(bindings: Bindings, message?: string): void;
  error(message: string): void;
  fatal(bindings: Bindings, message?: string): void;
  fatal(message: string): void;
  /** The active threshold, exposed so tests can assert on it. */
  readonly level: Level;
}

function resolveLevel(): Level {
  // Silent by default under test: a logger that writes to stderr during a
  // test run buries the assertion output that matters. `LOG_LEVEL` still
  // wins if set explicitly, so a failing test can be re-run verbosely.
  const configured = process.env["LOG_LEVEL"];
  if (configured && (LEVELS as readonly string[]).includes(configured)) {
    return configured as Level;
  }
  if (process.env["NODE_ENV"] === "test") {
    return "fatal";
  }
  return "info";
}

const activeLevel = resolveLevel();
const activeRank = LEVELS.indexOf(activeLevel);

/**
 * `Error` does not serialise through `JSON.stringify` -- its `message` and
 * `stack` are non-enumerable, so an error field logs as `{}` and the one
 * piece of information worth capturing is lost. Errors are unwrapped
 * explicitly.
 */
function serialise(value: unknown): unknown {
  if (value instanceof Error) {
    return {
      type: value.name,
      message: value.message,
      stack: value.stack,
    };
  }
  return value;
}

function emit(level: Level, first: Bindings | string, second?: string): void {
  if (LEVELS.indexOf(level) < activeRank) {
    return;
  }

  const record: Record<string, unknown> = {
    level,
    time: new Date().toISOString(),
  };

  if (typeof first === "string") {
    record["msg"] = first;
  } else {
    for (const [key, value] of Object.entries(first)) {
      record[key] = serialise(value);
    }
    if (second !== undefined) {
      record["msg"] = second;
    }
  }

  // One JSON object per line, to stderr. stderr rather than stdout so that
  // a CLI in this tree can write machine-readable results to stdout
  // without log lines corrupting them -- `src/cli/scientificCLI.ts` is an
  // advertised bin entry, so that separation matters.
  let line: string;
  try {
    line = JSON.stringify(record);
  } catch {
    // Circular structures must not take down the caller: a logger that
    // throws converts a recoverable problem into an outage.
    line = JSON.stringify({
      level,
      time: record["time"],
      msg: typeof first === "string" ? first : second,
      logError: "bindings were not serialisable",
    });
  }
  process.stderr.write(`${line}\n`);
}

export const logger: Logger = {
  trace: (first: Bindings | string, second?: string) =>
    emit("trace", first, second),
  debug: (first: Bindings | string, second?: string) =>
    emit("debug", first, second),
  info: (first: Bindings | string, second?: string) =>
    emit("info", first, second),
  warn: (first: Bindings | string, second?: string) =>
    emit("warn", first, second),
  error: (first: Bindings | string, second?: string) =>
    emit("error", first, second),
  fatal: (first: Bindings | string, second?: string) =>
    emit("fatal", first, second),
  level: activeLevel,
};

export default logger;
