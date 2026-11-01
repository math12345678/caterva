# ADR 0084: One request could kill the server

**Status:** Accepted, implemented

**Date:** 2026-08-16

**Relates to:** ADR 0025 (the merged collector and cache this wires up), ADR
0070/0066/0059/0049 (the same method — running the product — finding the
previous four)

## What was found

Starting the server and issuing a GET to each of its 25 routes, the way a
client would. The second request took the process down.

```
$ curl localhost:3000/api/health     -> 200
$ curl localhost:3000/api/metrics    -> (connection reset)
$ curl localhost:3000/api/health     -> (connection refused)
```

```
Error: Cannot write headers after they are sent to the client
    at ServerResponse.writeHead (node:_http_server:354:11)
    at Server.<anonymous> (src/web/server.ts:1104:9)
```

**Two bugs in series.**

### 1. The cache set a header after the response had started

```ts
const capturingEnd = res.end.bind(res);
(res as any).end = function cachingEnd(chunk?, ...rest) {
  if (res.statusCode === 200 && typeof chunk === 'string') writeCache(key, chunk);
  res.setHeader('X-Cache', 'MISS');        // <- throws
  return capturingEnd.apply(this, [chunk, ...rest]);
};
```

Every handler calls `res.writeHead(...)` and then `res.end(body)`. By the
time the patched `end` runs, the headers are on the wire, and `setHeader`
throws `ERR_HTTP_HEADERS_SENT`.

### 2. The error handler could not handle that error

```ts
} catch (error) {
  res.writeHead(500, ...);    // <- throws again, from inside the catch
  ...
}
```

A handler that fails *after* it has begun responding cannot be sent a 500 —
the status line has already gone. `writeHead` threw a second time, from
inside the `catch`, where nothing remained to catch it, and Node terminated
the process.

So **every route on the cache allowlist was fatal on first request** —
`/api/stats` and the whole `/api/metrics` family, which is exactly what the
dashboard polls. The second request would have been a cache HIT and perfectly
fine. The server never lived to serve it.

## Decision

**`X-Cache: MISS` is set when the miss is known, not when the response
ends.** The code is already inside `if (cached === null)`, so the miss is
established there, nothing has been written yet, and a header set before
`writeHead` survives the merge — verified with a scratch server rather than
assumed from the docs.

**The catch checks `res.headersSent` first.** If the response has started,
nothing useful can be sent, so the connection is destroyed: the client sees a
truncated response and retries, instead of hanging until timeout on a request
that will never complete. Logging moved to the top of the block — it used to
come last, so when the recovery threw, the original error was never recorded
and the operator got a dead process and a silent log.

**An error handler that can crash the process is worse than no error
handler**, because it converts one failed request into a total outage. That
is the same shape as this project's rule about checks: the artifact meant to
contain a fault instead amplified it.

## The two fixes are independent, and both are needed

Demonstrated by reintroducing bug 1 while keeping the guarded catch:

| | request | server afterwards |
|---|---|---|
| both bugs (original) | connection reset | **dead** |
| bug 1 only, catch fixed | connection reset | **alive** |
| both fixed | 200 with `X-Cache: MISS` | alive |

The middle row is the point: the catch fix does not hide bug 1 — that request
still fails — it stops one bad request from ending the service for everyone.

## Why no existing test caught it

`perfAndCache.test.ts` exercises `isCacheable`, `readCache` and `writeCache`
as functions, and all three are correct. The fault is in how `server.ts`
*wires* them to a real `ServerResponse`. `dashboardRoutes.test.ts` calls
handlers with a mock `res`, and a mock does not enforce
`ERR_HTTP_HEADERS_SENT`.

The defect exists only in a real HTTP response object, so
`serverSurvivesItsRoutes.test.ts` spawns the real server on port 3457 and
issues real requests. It polls `/api/health` until the server answers rather
than sleeping a guessed interval — during this investigation a 30-second
sleep was not enough under load, and the resulting "server is dead" reading
was actually "server had not started", which nearly produced a false
conclusion about which fix mattered.

## Consequences

- Mutation-tested: reintroducing both bugs fails all four tests in the new
  file.
- The MISS→HIT test uses a unique query string so it does not depend on
  cache state left by an earlier test. Its first version asserted MISS on a
  route the preceding test had already fetched and failed on a HIT — a test
  coupled to file order, which is a test that breaks the next time somebody
  reorders it.
- A control assertion checks `X-Cache` is *absent* from `/api/perf` and
  `/api/cache/stats`, which are excluded on purpose: an operator asking about
  now must not be told about ten seconds ago. A stray MISS there would mean
  the allowlist had quietly widened.
