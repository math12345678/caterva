# documents

Part of [**Terrium**](https://github.com/Terrium-sim/main) — scientific computing for teaching labs.

The constitution, 23 ADRs, architecture notes and the Word deliverables.
29 files.

## Start here

| document | what it settles |
|---|---|
| `CONSTITUTION.md` | the nine non-negotiable engineering rules |
| `adr/` | 23 architecture decisions, each with its context and consequences |
| `API.md` | the HTTP reference — checked against both servers on every build |
| `REPO_MAP.md` | what lives in which of the 18 repositories, and why |
| `literature-inventory.toml` | every hardcoded scientific number, and its provenance |

## The literature inventory

Worth singling out. Every number baked into a domain default declares one of
four states:

- `RESOLVED` — fetched live from a primary source, with a citation
- `VERIFIED` — a constant checked against a named source, check automated
- `UNVERIFIED` — a teaching default, and **never** to be described as
  literature-backed
- `NOT_SCIENTIFIC` — a grid size or integration window, where a citation
  would be a fabrication

Of the 40 numbers carrying a scientific claim, 10 trace to a source. The
inventory says so plainly rather than implying more rigour than exists — an
unfalsifiable claim of rigour is worth less than an honest admission of its
absence.

---

This repository is a submodule of [`Terrium-sim/main`](https://github.com/Terrium-sim/main). Clone the whole system with:

```bash
git clone --recursive https://github.com/Terrium-sim/main.git
```
