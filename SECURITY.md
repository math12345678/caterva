# Security Policy

> **⚠️ CORRECTION (2026-08-12):** the "What's actually in scope" section describes `Science-Agent-Pipeline/` as "(landing page)" with concerns limited to XSS in a waitlist form and npm supply-chain issues. That undersells the actual directory: `Science-Agent-Pipeline/artifacts/` contains **two** separate things — `terrium-landing` (the actual landing page) **and** `api-server`, a full backend with routes for `simulate`, `pipeline`, `enzymes`, `metrics`, `dashboard`, `health`, and `waitlist` (`Science-Agent-Pipeline/artifacts/api-server/src/routes/`). The API server spawns Python subprocesses directly (`spawn(pythonExecutable, [SCRIPT_PATH], ...)` in `src/lib/scienceAgent.ts:189` and `src/lib/teriumRunner.ts:118`) and calls out to external LLM providers with an API key (`Science-Agent-Pipeline/artifacts/api-server/src/lib/llmResolver.ts`) — neither subprocess/command-injection risk nor LLM-API-key handling is mentioned anywhere in this scope section, and both are more security-relevant than the XSS/waitlist framing given. This is a scope gap, not a fabricated statistic.

## Before you deploy this anywhere: there is no authentication

**`src/web/server.ts` has no authentication of any kind.** Not a login, not
an API key, not an allowlist. Every endpoint is open to anyone who can reach
the port.

That includes `GET /api/jobs/history`, which returns the **last 50 jobs** —
the query text somebody typed, the parameters, and the results — to any
caller. There is no per-user separation because there are no users; the
database has one shared job table.

So on a shared instance, **every student can read every other student's
queries.** On a public one, so can everybody else.

### What is stored

| stored | not stored |
|---|---|
| the query string as typed | IP addresses |
| parameters, results, timing | user agents |
| a generated job id | cookies or sessions |
| | accounts, names, emails |

No cookies, no `localStorage`, no analytics, no telemetry, no third-party
trackers. The only personal data that can end up in the database is whatever
somebody types into the query box — which is why the query box is the thing
to be careful about.

### What this means in practice

> **Correction (2026-08-15).** This section previously said the Docker image
> was a localhost configuration. **That was wrong, and it was written here
> without checking.** `docker-compose.yml` published `"3000:3000"`, which
> Docker binds to `0.0.0.0` — every interface — so the shipped configuration
> exposed this no-authentication server to the whole local network, and on a
> cloud host to the internet. With `NODE_ENV=production` and
> `restart: unless-stopped` beside it.
>
> Now `127.0.0.1:3000:3000`, and guarded. The claim below is true of the
> current file; it was not true of the one it described.

- **Run it on localhost.** That is what `make web` and the Docker image are
  for, and it is the only configuration anyone here has treated as safe.
- **Do not expose it to a shared network or the public internet as-is.** Put
  it behind authentication first, and understand that nobody has designed or
  reviewed that.
- **If a class shares one instance, tell the students.** They should know
  their queries are visible to the room before they type anything.
- **Do not type anything identifying into the query box.** Names, student
  IDs, anything from a real dataset.

### If a school is involved

Terrium is aimed at teaching labs, so this needs saying: a school deploying
this for students — particularly students under 18 — is processing data
about minors, and the obligations that attach (FERPA in the US, UK GDPR and
the ICO's Age Appropriate Design Code in the UK, and their equivalents
elsewhere) are the school's and the operator's, not something this software
handles for them.

Nothing here has been designed for that, reviewed for it, or assessed
against it. **This is not legal advice and no part of this project is a
substitute for the school's own data-protection assessment.** If somebody is
proposing a school deployment, that is the point to involve the school's
data-protection officer and a lawyer, before rather than after.

### Why this is documented rather than fixed

Adding authentication is a product decision with real design questions —
accounts or per-class tokens, where credentials live, what happens to
existing job history — and making that choice quietly inside a security
document would be the wrong way to make it.

What was wrong until now was not the absence of auth. It was that **nothing
said so.** A reader could open the dashboard, see a working simulation tool,
and have no reason to suspect that the history panel was showing them
somebody else's work. Stating a limitation is cheap; discovering it is not.

`scripts/check_deployment_warning.py` fails the build if this section
disappears while the server still has no authentication.

## The two risks the correction banner named, now assessed

The banner at the top of this file has said since 2026-08-12 that the scope
section missed two things. Both have now been looked at properly, and the
answers are different from each other.

**Subprocess spawning — checked, and clean.** The API server runs Python
with `spawn(pythonExecutable, [SCRIPT_PATH], {...})`: the argv form, so
nothing is shell-parsed. There is no `shell: true`, no `execSync` and no
`child_process.exec` anywhere in the server. User data reaches Python over
**stdin as JSON** (`proc.stdin.write(JSON.stringify(payload))`), so it never
appears on a command line at all, and the interpreter path is resolved from
`TERRIUM_PYTHON` / `VIRTUAL_ENV` / `PATH` — operator-controlled environment,
not request input.

So there is no command injection. `scripts/check_subprocess_safety.py` keeps
it that way, because `shell: true` is twelve characters and, on a server with
no authentication, would be remote code execution reachable by anyone who can
open the port. It does **not** check how the Python side handles that stdin
once parsed — a different language and a different check.

**LLM API key handling — checked, and it needed a disclosure.** Keys are read
from environment variables and none is committed (`.env`, `.env.*` and
`*.env` are gitignored; only `.env.example` templates are tracked). But the
resolver sends the query text somebody typed to an external provider, and
`docs/PRIVACY.md` had described this as "no third-party requests **from the
page itself**" — a qualifier that made a misleading sentence technically
true. Corrected there, and guarded by
`scripts/check_llm_disclosure.py`.

Recording the clean result matters as much as the correction. An unassessed
risk in a security document invites the next reader to re-derive it from
scratch, and the honest resolution of "nobody checked" is "somebody checked,
here is what they found".

## Reporting a vulnerability

If you find a security issue in Terrium -- the simulation engine, the
literature-scraping layer, or the landing page -- please report it
privately rather than opening a public GitHub issue.

**Email admin.terrium@gmail.com** with:

- A description of the vulnerability and its potential impact
- Steps to reproduce it
- Any relevant logs, screenshots, or proof-of-concept code

You should get an acknowledgment within a few days. This is a small,
pre-launch, mostly-one-person-plus-a-small-team project right now, so
please have reasonable expectations about response time compared to a
company with a dedicated security team -- but security reports are taken
seriously regardless of team size.

## What's actually in scope right now

Given the current state of the project:

- **Terium/** (simulation engine): the main risk surface here is
  something that causes incorrect scientific output to be presented as
  correct without being flagged -- see `terium_engine.py`'s
  `ParameterValidation` / flagging system. A bug that lets an implausible
  or dangerous parameter slip through unflagged is a real security-relevant
  bug for this project, even though it's not a classic memory-safety or
  injection vulnerability.
- **Tests/** (BRENDA/KEGG/PubMed scraping layer): this makes outbound HTTP
  requests to third-party services. Anything that could turn scraped
  content into unintended code execution (e.g., unsafe deserialization of
  fetched HTML/XML) is in scope.
- **Science-Agent-Pipeline/** (landing page): standard web-app concerns --
  XSS via unsanitized user input in the waitlist form, dependency
  vulnerabilities in the npm supply chain (see `pnpm-workspace.yaml`'s
  `minimumReleaseAge` setting, which already exists specifically to guard
  against supply-chain attacks).

## Supported versions

Releases are tagged `vX.Y.Z` and published by `.github/workflows/release.yml`
(ADR 0177). Security fixes go into the newest minor version only, as a
patch release; there is no long-term-support line. As of 2026-09-21 that
is 0.3.x. Earlier tags (v0.1.0, a source archive; v0.2.0, a wheel never
attached to a Release) receive no fixes; upgrade. `main` between tags is
unsupported in the same sense as any unreleased commit.

## Disclosure

Please give us a reasonable window to fix a reported issue before any
public disclosure. Given the team size, "reasonable" should be discussed
directly with us rather than assumed -- email first and we'll agree on a
timeline together.
