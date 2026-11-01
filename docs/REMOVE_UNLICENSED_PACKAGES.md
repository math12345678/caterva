# Removing the four unlicensed @replit packages

**Run this on a machine with pnpm.** It could not be done in the agent
sandbox: there is no pnpm store matching the committed lockfile, and forcing
a reinstall risks breaking `pnpm install --frozen-lockfile` in CI for
everyone.

`scripts/check_dependency_licenses.py` fails the build until this is done.
That is the correct state — an unlicensed dependency should hold a build —
so **do not delete or downgrade the guard to go green.**

## What is wrong

Four packages ship **no `license` field and no LICENSE file**. Not a
permissive licence, not an unusual one: no grant of permission to use them
at all. Everything else in a tree of 494 packages has one.

| package | declared in | used? |
|---|---|---|
| `@replit/connectors-sdk` | `Science-Agent-Pipeline/package.json` | **no** — imported by no source file |
| `@replit/vite-plugin-cartographer` | `artifacts/mockup-sandbox`, `artifacts/caterva-landing` | call sites already removed |
| `@replit/vite-plugin-dev-banner` | `artifacts/caterva-landing` | call sites already removed |
| `@replit/vite-plugin-runtime-error-modal` | `artifacts/mockup-sandbox`, `artifacts/caterva-landing` | call sites already removed |

The three vite plugins were Replit editor conveniences — an error overlay, a
dev banner, a source mapper. Two were gated on the `REPL_ID` environment
variable; **the error overlay was not, so it ran on every build including
production ones.** Those call sites are already gone. What remains is the
manifest entries and the lockfile.

## The commands

Requires `pnpm@11.20.0` (the version in `Science-Agent-Pipeline/package.json`'s
`packageManager` field). If you do not have it:

```bash
corepack enable
corepack prepare pnpm@11.20.0 --activate
```

Then, from the repository root:

```bash
cd Science-Agent-Pipeline

# 1. The unused one, declared at the workspace root.
pnpm remove @replit/connectors-sdk

# 2. The three vite plugins, in each workspace that declares them.
pnpm --filter ./artifacts/mockup-sandbox remove \
  @replit/vite-plugin-cartographer \
  @replit/vite-plugin-runtime-error-modal

pnpm --filter ./artifacts/caterva-landing remove \
  @replit/vite-plugin-cartographer \
  @replit/vite-plugin-dev-banner \
  @replit/vite-plugin-runtime-error-modal
```

### Also remove the catalog entries

The vite plugins are declared as `catalog:` references, so
`Science-Agent-Pipeline/pnpm-workspace.yaml` carries their versions
separately. `pnpm remove` does **not** clean these up. Delete these three
lines (around line 44):

```yaml
  '@replit/vite-plugin-cartographer': ^0.5.21
  '@replit/vite-plugin-dev-banner': ^0.1.1
  '@replit/vite-plugin-runtime-error-modal': ^0.0.6
```

There is also a minimum-release-age exclusion around line 31 listing
`'@replit/*'`. Leave it or remove it — it governs nothing once no `@replit`
package is declared, but removing it means the next person does not wonder
which `@replit` packages it was protecting.

### Regenerate and verify

```bash
pnpm install                       # regenerates pnpm-lock.yaml
pnpm install --frozen-lockfile     # must pass, or CI will fail
```

## Confirm it worked

From the repository root:

```bash
python scripts/check_dependency_licenses.py
```

Expected: `Explicitly forbidden: 0` and a zero exit code.

Then confirm nothing broke:

```bash
cd Science-Agent-Pipeline
pnpm --filter @workspace/api-server run test
```

## Do not

- **Edit `package.json` by hand.** The lockfile would no longer match and
  `pnpm install --frozen-lockfile` fails in CI — a green local tree and a red
  PR, with the cause two steps removed from the symptom.
- **Add them to `PERMISSION` in the guard.** That registry records what a
  licence file *says*. There is no licence file. An entry would be a claim
  about a document that does not exist, in the guard whose whole purpose is
  that claims match documents.
- **Downgrade the guard to a warning.** The build should be red while an
  unlicensed dependency is declared. That is the guard working.

## If you decide to keep them anyway

That is a legitimate call — they are small Replit editor conveniences and the
practical risk is low. But make it explicitly:

1. Ask Replit to publish a licence, or find one in the published tarball that
   the metadata does not declare (`exit` is a package in this same tree that
   declares nothing and ships `LICENSE-MIT`, so it is worth looking).
2. If a licence turns up, add it to `PERMISSION` with a quote from the
   shipped file.
3. If it does not, add them to `NO_GRANT` with a note saying the risk was
   accepted, by whom, and on what date.

What should not happen is the third state: still declared, still unlicensed,
and nobody remembering why the build is red.

---

This is not legal advice. See
[ADR 0061](adr/0061-gpl-out-of-the-default-install.md) for the full
dependency-licence audit and `Business/INCORPORATION_CHECKLIST.md` for the
items that need actual counsel.
