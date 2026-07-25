# Security Policy

## Reporting a vulnerability

If you find a security issue in Terrium -- the simulation engine, the
literature-scraping layer, or the landing page -- please report it
privately rather than opening a public GitHub issue.

**Email mathlete.world@gmail.com** with:

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

- **Tellurium/** (simulation engine): the main risk surface here is
  something that causes incorrect scientific output to be presented as
  correct without being flagged -- see `tellurium_engine.py`'s
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

There are no released/versioned builds yet -- `main` is the only branch
that matters right now. Once there's an actual release process (see
`CHANGELOG.md`), this section should specify which versions receive
security fixes.

## Disclosure

Please give us a reasonable window to fix a reported issue before any
public disclosure. Given the team size, "reasonable" should be discussed
directly with us rather than assumed -- email first and we'll agree on a
timeline together.
