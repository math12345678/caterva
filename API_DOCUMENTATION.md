# Caterva API Documentation

**The API reference lives at [`docs/API.md`](docs/API.md).**

Every endpoint there is checked against the server's Express route table on
every build by `scripts/check_example_endpoints.py`, so a renamed or removed
route fails the build rather than 404-ing for a reader.

---

## What this file used to be, and why it is worth recording

Until 2026-08-11 this was 725 lines documenting a REST API that **did not
exist**: bearer-token authentication, a literature-search endpoint, a
STRENDA validation endpoint, webhooks with signed payloads, cursor
pagination, URL-path versioning with a deprecation date of 2026-12-31, an
`@caterva/sdk` npm package, a `caterva-sdk` PyPI package, an `api.` host
and a `status.` host.

None of it was real. The root `src/` tree it claimed to document is a
TypeScript library and CLI with no HTTP server at all — `package.json` had
no `dependencies` key, and no `express` or `createServer` call existed
anywhere in it. The eight endpoints it described did not match the real API
either; they were an independent invention.

Someone had already worked this out, and left a warning banner at the top
saying so — then left the 725 lines beneath it in place, tracked in git.

**That is the part worth recording.** A false document with a disclaimer is
not a corrected document. A reader who has been told "this may be
unreliable" still reads the endpoint table, because the table is specific
and the disclaimer is vague; specificity reads as authority. The fix for a
false claim is to make it true or delete it — and then to make it
mechanically checkable so it cannot rot back.

Hence `check_example_endpoints.py`, and hence the fact that `docs/API.md`
carries no banner: it does not need one, because something fails the build
if it stops being true.

### The correction to the correction

A first sweep of the repository root reported **242 of 294** endpoint
mentions as wrong. That number was itself wrong, and it is worth saying so
in the same place it was published.

The guard behind it parsed only the Express routers under
`Science-Agent-Pipeline/artifacts/api-server/`. Caterva serves a **second**
HTTP API — `src/web/server.ts`, a raw `http.createServer` dispatching on
`pathname` equality — whose nineteen routes it could not see. Measured
against the full table the real figure is **19 of 282**, and most of the
"nonexistent" endpoints — batch submission, sweeps, job comparison, a job
by id, statistics — were real all along, on the other server.

Two client examples were rewritten against the wrong service before this
surfaced. Both have been put back.

The eight endpoints removed from this file were checked against **both**
route tables and are genuinely absent: literature search, STRENDA
validation, a detailed status endpoint, webhook subscription, a top-level
jobs collection, and the three URL-versioned paths.

(Named without their URLs on purpose. A document that spells out a dead
endpoint is how the dead endpoint gets copied into the next document — and
it would trip the very guard this section is about.)

The lesson is not "be careful with regexes". It is that a guard with an
incomplete source of truth does not fail quietly — it produces confident
false accusations, and they get acted on precisely because guards are
trusted. A guard should be able to state how much of the world it looked
at, and a number it reports should be reproduced by hand before anyone
acts on it.

## Where things actually are

| What | Where |
|---|---|
| HTTP API reference | [`docs/API.md`](docs/API.md) |
| The server itself | `Science-Agent-Pipeline/artifacts/api-server/src/routes/` |
| Python client example | [`examples/python_integration.py`](examples/python_integration.py) |
| Node client example | [`examples/nodejs_integration.js`](examples/nodejs_integration.js) |
| The CLI (the root `src/` tree) | `src/cli/scientificCLI.ts`, and the "Using it" section of [`README.md`](README.md) |

Both client examples are covered by the same guard as `docs/API.md`.
