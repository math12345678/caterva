/**
 * Logger
 *
 * Structured logging
 */

const LOG_LEVEL = process.env.LOG_LEVEL || 'info';

const levels = { debug: 0, info: 1, warn: 2, error: 3, fatal: 4 };
const currentLevel = levels[LOG_LEVEL as keyof typeof levels] ?? 1;

/**
 * `Error` does not survive `JSON.stringify`: `message` and `stack` are
 * non-enumerable, so an error field serialises to `{}` and the only
 * information worth capturing is destroyed.
 *
 * This is not theoretical for this tree. `scientificPipeline.ts` logs
 * `logger.error({ jobId, error }, 'Simulation error')` in its top-level
 * catch, which produced literally
 *
 *     {"level":"error","jobId":"j1","error":{},"msg":"Simulation error"}
 *
 * -- a failure report with the failure removed. Errors are unwrapped
 * explicitly, and nested ones (`{ cause }`) are handled too.
 */
function serialise(value: unknown): unknown {
  if (value instanceof Error) {
    const out: Record<string, unknown> = {
      type: value.name,
      message: value.message,
      stack: value.stack
    };
    if (value.cause !== undefined) {
      out['cause'] = serialise(value.cause);
    }
    return out;
  }
  return value;
}

function log(level: string, data: Record<string, any>, msg: string) {
  const levelNum = levels[level as keyof typeof levels] ?? 1;
  if (levelNum < currentLevel) {
    return;
  }

  const record: Record<string, unknown> = {
    level,
    time: new Date().toISOString()
  };
  for (const [key, value] of Object.entries(data)) {
    record[key] = serialise(value);
  }
  record['msg'] = msg;

  let line: string;
  try {
    line = JSON.stringify(record);
  } catch {
    // A circular structure must not take down the caller: a logger that
    // throws turns a recoverable problem into an outage.
    line = JSON.stringify({
      level,
      time: record['time'],
      msg,
      logError: 'bindings were not serialisable'
    });
  }

  // stderr, not stdout (`console.log`). `package.json` advertises a bin
  // entry -- `scientific` -> `src/cli/scientificCLI.ts` -- so anything the
  // CLI prints for a caller to consume goes to stdout, and log lines
  // interleaved there would corrupt it. Diagnostics belong on stderr.
  process.stderr.write(`${line}\n`);
}

export const logger = {
  debug: (data: Record<string, any> | string, msg?: string) => {
    if (typeof data === 'string') {
      log('debug', {}, data);
    } else {
      log('debug', data, msg || '');
    }
  },
  info: (data: Record<string, any> | string, msg?: string) => {
    if (typeof data === 'string') {
      log('info', {}, data);
    } else {
      log('info', data, msg || '');
    }
  },
  warn: (data: Record<string, any> | string, msg?: string) => {
    if (typeof data === 'string') {
      log('warn', {}, data);
    } else {
      log('warn', data, msg || '');
    }
  },
  error: (data: Record<string, any> | string, msg?: string) => {
    if (typeof data === 'string') {
      log('error', {}, data);
    } else {
      log('error', data, msg || '');
    }
  },
  fatal: (data: Record<string, any> | string, msg?: string) => {
    if (typeof data === 'string') {
      log('fatal', {}, data);
    } else {
      log('fatal', data, msg || '');
    }
  }
};
