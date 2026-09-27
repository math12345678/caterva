# Publishing to Terrium-sim

Everything is prepared. These are the commands to run **on your machine** —
the sandbox this was built in has no GitHub credentials, so nothing has been
pushed.

## Before anything: `make publish-check`

```bash
make publish-check
```

Runs every check that can be made without credentials — the split-repo
READMEs, LICENSE and NOTICE travelling with each repository, the
non-affiliation notice, BRENDA's CC BY attribution, dependency licences,
documented counts, investor-facing figures, doc links. It prints either
"the only thing left is the push" or exactly what is not ready and what
would ship wrong if you pushed anyway.

It is honest about its limits and lists them: it cannot see GitHub, so it
cannot tell you whether the eighteen repositories exist — an anonymous probe
gets the same 404 for "private" and "does not exist", and guessing between
them is the mistake this project has recorded nine times.

The sections below are the steps it cannot do for you.

## 0. Get the prepared work

```bash
cd ~/Desktop/Coding/Caterva
git pull origin main          # make sure you have the latest split script
git push origin main          # push the rename + split machinery
```

### If git says `index.lock: File exists`

```bash
rm -f .git/index.lock
```

A previous git process crashed and left the lock behind. Check nothing is
actually running first (`ps aux | grep git`); if the answer is nothing, the
file is stale and safe to delete. It contains no work of yours — git rebuilds
it on the next command.

## 1. Build the split branches

```bash
./scripts/split_repos.sh
```

Takes about a minute. It creates 11 local `split/*` branches with preserved
history and stages 6 assembled repositories in `$TMPDIR/caterva-split`. It
pushes nothing, and it refuses to run on a dirty tree.

Expected output:

| repo | commits | from |
|---|---|---|
| `caterva` | 72 | `Tellurium/` + replayed rename |
| `science-agent-pipeline-replit` | 80 | `Science-Agent-Pipeline/` |
| `business` | 77 | `Business/` |
| `wiring-main` | 67 | `scripts/` |
| `documents` | 51 | `docs/` |
| `tests` | 37 | `Tests/` |
| `backend-main` | 17 | `src/` |
| `caterva-site` | 10 | `caterva-site/` |
| `landing` | 5 | `landing/` |
| `advanced-analysis` | 2 | `advanced_analysis/` |
| `benchmark-results` | 1 | `benchmark_results/` |

plus `main` (23 files), `archive` (68), `miscellaneous` (8),
`frontend-main` (2), `worktrees` and `mule`.

## 2. Push everything

```bash
./scripts/split_repos.sh --push
```

Pushes over **HTTPS** by default, because this repository's own `origin` is
HTTPS and pushes successfully — so those credentials are already cached.
`git@github.com` needs an SSH key that may not exist on the machine, and
choosing the protocol already known to work beats choosing the conventional
one.

```bash
./scripts/split_repos.sh --push-ssh     # force SSH instead
```

The 18 repositories already exist, so nothing needs creating.

### If a push fails

The script counts outcomes and reports them:

```
FAILED: 0 of 17 pushed; 17 failed
```

It does **not** print "all repositories pushed" and exit 0, which is what an
earlier version did when every push failed with `Permission denied
(publickey)`. A failing command on the left of `&&` is a tested condition,
not an error, so `set -e` never fired. Fixed, and mutation-tested with
deliberately failing pushes.

| symptom | cause |
|---|---|
| `Permission denied (publickey)` | no SSH key — use the HTTPS default |
| `Repository not found` | repo missing under the org, or no write access |
| `Updates were rejected` | shouldn't happen; the script force-pushes |

A failed push says nothing about the split branches. They are built and
correct in your local repository either way — re-running is free.

## 3. Wire up the submodules

`main` is an umbrella. After everything else is pushed:

```bash
cd "$TMPDIR/caterva-split/main"

for r in caterva tests backend-main frontend-main wiring-main \
         science-agent-pipeline-replit documents business \
         caterva-site landing advanced-analysis benchmark-results; do
  git submodule add "https://github.com/Terrium-sim/$r.git" "$r"
done

git commit -m "Add the twelve code submodules"
git push
```

Then a full checkout is:

```bash
git clone --recursive https://github.com/math12345678/caterva.git
```

## 4. Point the old repo at the new home

`math12345678/caterva` holds all 218 commits and stays as the archive of
record. Worth adding a line at the top of its README:

> Development moved to [github.com/Terrium-sim](https://github.com/Terrium-sim).
> This repository is the pre-split history.

## If something needs redoing

The script is re-runnable — every branch is deleted and rebuilt each time,
and the monorepo is only ever read. Nothing here is destructive to your
working tree.

## What I could not do from here

- **Push.** No credentials in the sandbox.
- **`mule`.** You said you would add the MuleRun page; it is created with a
  placeholder README.
- **`demo-repository`.** Left untouched — it is GitHub's demo repo.
- **`worktrees`.** Genuinely empty: `Caterva.worktrees/` tracks no files. It
  gets a README so an empty repo is not mistaken for a failed push.
