/**
 * One request must not be able to kill the server.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * `GET /api/metrics` terminated the whole process. Two bugs in series:
 *
 * 1. The response cache patched `res.end` to call
 *    `res.setHeader('X-Cache', 'MISS')`. Every handler calls
 *    `res.writeHead(...)` before `res.end(...)`, so by then the headers were
 *    already sent and `setHeader` threw `ERR_HTTP_HEADERS_SENT`.
 *
 * 2. The outer `catch` responded to that by calling
 *    `res.writeHead(500, ...)` on the same already-sent response. That threw
 *    again — from inside the catch, where nothing was left to catch it — and
 *    Node terminated the process.
 *
 * So every allowlisted route (`/api/stats` and the `/api/metrics` family —
 * the ones the dashboard polls) was fatal on first request. The second
 * request would have been a cache HIT and fine; the server never lived to
 * serve it.
 *
 * WHY NO EXISTING TEST CAUGHT IT
 * ------------------------------
 * `perfAndCache.test.ts` tests `isCacheable`, `readCache` and `writeCache`
 * as functions, and they are all correct — the bug is in how the server
 * *wires* them to a real `ServerResponse`. `dashboardRoutes.test.ts` calls
 * handlers with a mock `res`, and a mock does not enforce
 * `ERR_HTTP_HEADERS_SENT`.
 *
 * The defect only exists in a real HTTP response object, which is why this
 * file starts a real server on an ephemeral port and issues real requests.
 */
import { spawn, type ChildProcess } from 'child_process';
import * as http from 'http';
import * as path from 'path';

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const SERVER = path.join(REPO_ROOT, 'src', 'web', 'server.ts');
const TS_NODE = path.join(REPO_ROOT, 'node_modules', '.bin', 'ts-node');
const PORT = 3457;

let proc: ChildProcess;

function get(pathname: string): Promise<{ status: number; headers: http.IncomingHttpHeaders }> {
  return new Promise((resolve, reject) => {
    const req = http.get(
      { host: '127.0.0.1', port: PORT, path: pathname, timeout: 15_000 },
      (res) => {
        res.resume(); // drain, or the socket stays open and the suite hangs
        res.on('end', () => resolve({ status: res.statusCode ?? 0, headers: res.headers }));
      },
    );
    req.on('timeout', () => { req.destroy(); reject(new Error(`timeout ${pathname}`)); });
    req.on('error', reject);
  });
}

/** Poll until the server answers, rather than sleeping a guessed interval. */
async function waitForReady(attempts = 60): Promise<void> {
  for (let i = 0; i < attempts; i++) {
    try {
      const { status } = await get('/api/health');
      if (status === 200) return;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error('server did not become ready');
}

beforeAll(async () => {
  proc = spawn(TS_NODE, [SERVER], {
    cwd: REPO_ROOT,
    env: { ...process.env, PORT: String(PORT) },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  await waitForReady();
}, 180_000);

afterAll(() => {
  proc?.kill('SIGKILL');
});

jest.setTimeout(300_000);

/**
 * Every route on the cache allowlist, which is where the fault lived, plus
 * the uncached observability routes as a control. Listed by hand rather than
 * imported from ALLOWLIST: the point is that these specific URLs, the ones a
 * dashboard actually polls, do not kill the server.
 */
const CACHED = ['/api/stats', '/api/metrics', '/api/metrics/by-model', '/api/metrics/reproducibility'];
const UNCACHED = ['/api/health', '/api/perf', '/api/cache/stats'];

describe('a request cannot take the server down', () => {
  it('answers every allowlisted route, and is still alive afterwards', async () => {
    for (const route of [...CACHED, ...UNCACHED]) {
      const { status } = await get(route);
      expect([200, 304]).toContain(status);
    }
    // The assertion that matters. Before the fix, the FIRST cached route
    // killed the process and everything after it failed to connect.
    const { status } = await get('/api/health');
    expect(status).toBe(200);
  });

  it('marks a cached route MISS then HIT, without a header written twice', async () => {
    // `X-Cache` is set before `writeHead` now. If it were set inside the
    // patched `end` again, this route would throw instead of answering —
    // so a plain 200 here is the regression check for bug 1.
    //
    // The query string makes the cache key unique to THIS test. Without it
    // the route had already been fetched by the test above, so the first
    // request here was a HIT and the assertion failed — a test that depended
    // on what ran before it, which is a test that will fail again the next
    // time somebody reorders the file. `cacheKey` includes the query string
    // (asserted in perfAndCache.test.ts), so this is a fresh entry.
    const route = `/api/metrics/by-model?probe=${Date.now()}`;

    const first = await get(route);
    expect(first.status).toBe(200);
    expect(first.headers['x-cache']).toBe('MISS');

    const second = await get(route);
    expect(second.status).toBe(200);
    expect(second.headers['x-cache']).toBe('HIT');
  });

  it('does not put X-Cache on routes deliberately left uncached', async () => {
    // /api/perf and /api/cache/stats are excluded on purpose: an operator
    // asking about now must not be told about ten seconds ago. A stray
    // MISS header here would mean the allowlist had quietly widened.
    for (const route of UNCACHED) {
      const { headers } = await get(route);
      expect(headers['x-cache']).toBeUndefined();
    }
  });

  it('survives a 404, which also runs the error path', async () => {
    const { status } = await get('/api/no-such-route');
    expect(status).toBe(404);
    expect((await get('/api/health')).status).toBe(200);
  });
});
