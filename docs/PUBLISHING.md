# Publishing to Terrium-sim

Everything is prepared. These are the commands to run **on your machine** —
the sandbox this was built in has no GitHub credentials, so nothing has been
pushed.

## 0. Get the prepared work

```bash
cd ~/Desktop/Coding/Terrium
git push origin main          # push the rename + split machinery first
```

## 1. Build the split branches

```bash
./scripts/split_repos.sh
```

Takes about a minute. It creates 11 local `split/*` branches with preserved
history and stages 6 assembled repositories in `$TMPDIR/terrium-split`. It
pushes nothing, and it refuses to run on a dirty tree.

Expected output:

| repo | commits | from |
|---|---|---|
| `terium` | 72 | `Tellurium/` + replayed rename |
| `science-agent-pipeline-replit` | 80 | `Science-Agent-Pipeline/` |
| `business` | 77 | `Business/` |
| `wiring-main` | 67 | `scripts/` |
| `documents` | 51 | `docs/` |
| `tests` | 37 | `Tests/` |
| `backend-main` | 17 | `src/` |
| `terrium-site` | 10 | `terrium-site/` |
| `landing` | 5 | `landing/` |
| `advanced-analysis` | 2 | `advanced_analysis/` |
| `benchmark-results` | 1 | `benchmark_results/` |

plus `main` (23 files), `archive` (68), `miscellaneous` (8),
`frontend-main` (2), `worktrees` and `mule`.

## 2. Push everything

```bash
./scripts/split_repos.sh --push
```

This force-pushes each branch to `main` on its repository. The 18 repos
already exist, so nothing needs creating.

If you prefer HTTPS over SSH, edit the `git push` lines in the script, or
push individually:

```bash
git push -f git@github.com:Terrium-sim/terium.git split/terium:main
git push -f git@github.com:Terrium-sim/tests.git  split/tests:main
# ...etc

cd "$TMPDIR/terrium-split/main" && git push -f git@github.com:Terrium-sim/main.git main
```

## 3. Wire up the submodules

`main` is an umbrella. After everything else is pushed:

```bash
cd "$TMPDIR/terrium-split/main"

for r in terium tests backend-main frontend-main wiring-main \
         science-agent-pipeline-replit documents business \
         terrium-site landing advanced-analysis benchmark-results; do
  git submodule add "https://github.com/Terrium-sim/$r.git" "$r"
done

git commit -m "Add the twelve code submodules"
git push
```

Then a full checkout is:

```bash
git clone --recursive https://github.com/Terrium-sim/main.git
```

## 4. Point the old repo at the new home

`math12345678/terrium` holds all 218 commits and stays as the archive of
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
- **`worktrees`.** Genuinely empty: `Terrium.worktrees/` tracks no files. It
  gets a README so an empty repo is not mistaken for a failed push.
