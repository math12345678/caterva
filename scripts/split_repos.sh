#!/usr/bin/env bash
#
# Split the Terrium monorepo into the 18 repositories under
# github.com/Terrium-sim, preserving per-folder history.
#
# Run this from a clean checkout of the monorepo. It only creates local
# branches under `split/*` — it pushes nothing. Review, then run the push
# commands it prints at the end.
#
# Re-runnable: every branch is deleted and rebuilt each time.
#
#   ./scripts/split_repos.sh          # build the split branches
#   ./scripts/split_repos.sh --push   # build, then push to Terrium-sim
#
set -euo pipefail

ORG="Terrium-sim"
PUSH="${1:-}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# The commit that renamed Tellurium/ -> Terium/. History for the engine
# lives under the OLD path, so its split runs from the commit before this
# one and replays the rename on top. See docs/REPO_MAP.md.
RENAME_COMMIT="$(git log --format=%H --grep='Rename Tellurium -> Terium' -n 1 || true)"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()  { printf '  \033[32m✓\033[0m %s\n' "$*"; }

if [ -n "$(git status --porcelain)" ]; then
  echo "FAIL: working tree is dirty. Commit or stash first — a split of a" >&2
  echo "      dirty tree silently omits the uncommitted files." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# 1. Directory-backed repos: split with full history.
# ---------------------------------------------------------------------------
# repo<TAB>path
DIRECT_SPLITS=$(cat <<'MAP'
tests	Tests
business	Business
advanced-analysis	advanced_analysis
benchmark-results	benchmark_results
landing	landing
terrium-site	terrium-site
science-agent-pipeline-replit	Science-Agent-Pipeline
backend-main	src
wiring-main	scripts
documents	docs
MAP
)

say "Splitting directory-backed repos (history preserved)"
while IFS=$'\t' read -r repo path; do
  [ -z "$repo" ] && continue
  if [ ! -d "$path" ]; then
    echo "  ! $path missing — skipping $repo" >&2
    continue
  fi
  git branch -D "split/$repo" >/dev/null 2>&1 || true
  git subtree split -P "$path" -b "split/$repo" >/dev/null 2>&1
  ok "$(printf '%-30s' "$repo") $(git rev-list --count "split/$repo") commits  <- $path/"
done <<< "$DIRECT_SPLITS"

# ---------------------------------------------------------------------------
# 2. terium: the engine, whose path was renamed.
# ---------------------------------------------------------------------------
say "Splitting terium (two-step: pre-rename history + replayed rename)"
git branch -D split/terium >/dev/null 2>&1 || true
if [ -n "$RENAME_COMMIT" ]; then
  TMPWT="$(mktemp -d)/prerename"
  git worktree add -f --detach "$TMPWT" "$RENAME_COMMIT^" >/dev/null 2>&1
  ( cd "$TMPWT" && git subtree split -P Tellurium -b split/terium >/dev/null 2>&1 )
  git worktree remove --force "$TMPWT" >/dev/null 2>&1
  ok "terium                         $(git rev-list --count split/terium) commits  <- Tellurium/ (pre-rename)"
  echo "    NOTE: replay the rename in the pushed repo, or push Terium/ as a"
  echo "          follow-up commit — see docs/REPO_MAP.md."
else
  git subtree split -P Terium -b split/terium >/dev/null 2>&1
  echo "  ! rename commit not found; split Terium/ directly ($(git rev-list --count split/terium) commits)"
fi

# ---------------------------------------------------------------------------
# 3. File-set repos: assembled from scattered root files, so there is no
#    single path to split. Built as orphan branches with one commit, and
#    their README says where the history lives.
# ---------------------------------------------------------------------------
# Built in a staging directory, NOT as an orphan branch in this worktree.
#
# The first version used `git checkout --orphan` here. That leaves every
# tracked file staged in the live working tree, and switching back to main
# then aborts on "untracked files would be overwritten" -- leaving the
# checkout parked on a half-built branch. Recoverable, but it edits the tree
# you are working in to produce a repo that has nothing to do with it.
#
# A staging directory cannot do that: the monorepo is only ever read.
STAGE="${TMPDIR:-/tmp}/terrium-split"

build_fileset() {
  local repo="$1"; shift
  local readme_file="$1"; shift
  local dest="$STAGE/$repo"

  rm -rf "$dest"; mkdir -p "$dest"

  local staged=0
  for f in "$@"; do
    if [ -e "$ROOT/$f" ]; then
      mkdir -p "$dest/$(dirname "$f")"
      cp -R "$ROOT/$f" "$dest/$f"
      staged=$((staged+1))
    fi
  done

  cp "$ROOT/$readme_file" "$dest/README.md"

  git -C "$dest" init -q -b main
  git -C "$dest" add -A
  git -C "$dest" -c user.name="$(git config user.name)" \
                 -c user.email="$(git config user.email)" \
                 commit -q -m "Initial import: $repo

Assembled from files at the monorepo root, which have no single directory to
split, so this repository starts with one commit rather than a partial
history. The full history is in Terrium-sim/main."
  ok "$(printf '%-30s' "$repo") $staged file(s)  -> $dest"
}

say "Building file-set repos (no single path to split; history noted in README)"
rm -rf "$STAGE"; mkdir -p "$STAGE"

# The 14 documents that are current stay in `main`; everything else at the
# root is a superseded status report. Classification in docs/ARCHIVE_TRIAGE.md.
KEEP_AT_ROOT='^(README|CHANGELOG|CONTRIBUTING|SECURITY|CODE_OF_CONDUCT|API_DOCUMENTATION|API_QUICK_REFERENCE|COMPREHENSIVE_GUIDE|EXPORT_AND_ANALYSIS_GUIDE|FEATURE_MODEL_COMPARISON|PHASE_5A_INTEGRATION_GUIDE|REFACTOR_STATUS|START_HERE|WEB_INTERFACE)\.md$'

ARCHIVE_DOCS=()
while IFS= read -r f; do ARCHIVE_DOCS+=("$f"); done < <(
  git ls-files | grep -v / | grep '\.md$' | grep -vE "$KEEP_AT_ROOT"
)
build_fileset archive docs/readmes/archive.md "${ARCHIVE_DOCS[@]}"

build_fileset miscellaneous docs/readmes/miscellaneous.md \
  Logo.png terrium_ai_architecture.png terrium_pitch_deck.pptx \
  FINAL_STATUS.txt lr_probe.js test-real-data.js e2e-test.js

# The dashboard the web server serves. Split from server.ts, which stays in
# backend-main -- see docs/REPO_MAP.md for why, and for the guard that keeps
# the two from drifting apart.
build_fileset frontend-main docs/readmes/frontend-main.md src/web/dashboard.html

# The umbrella: top-level docs, container/compose, licence, and the
# submodule wiring. No source file, so nothing here can drift from a repo
# that also holds it.
KEEP_DOCS=()
while IFS= read -r f; do KEEP_DOCS+=("$f"); done < <(
  git ls-files | grep -v / | grep -E "$KEEP_AT_ROOT"
)
build_fileset main docs/readmes/main.md "${KEEP_DOCS[@]}" \
  LICENSE CITATION.cff Dockerfile docker-compose.yml .dockerignore \
  .editorconfig .gitignore docs/REPO_MAP.md docs/ARCHIVE_TRIAGE.md

build_fileset worktrees docs/readmes/worktrees.md
build_fileset mule docs/readmes/mule.md

# ---------------------------------------------------------------------------
# 4. Report.
# ---------------------------------------------------------------------------
say "Split branches in this repo (history preserved)"
for b in $(git branch --list 'split/*' --format='%(refname:short)'); do
  printf "  %-34s %4s commits\n" "${b#split/}" "$(git rev-list --count "$b")"
done

say "Staged repos in $STAGE (single initial commit)"
for d in "$STAGE"/*/; do
  [ -d "$d" ] || continue
  printf "  %-34s %4s file(s)\n" "$(basename "$d")" "$(git -C "$d" ls-files | wc -l | tr -d ' ')"
done

if [ "$PUSH" = "--push" ]; then
  say "Pushing to $ORG"
  for b in $(git branch --list 'split/*' --format='%(refname:short)'); do
    repo="${b#split/}"
    git push -f "git@github.com:$ORG/$repo.git" "$b:main" && ok "pushed $repo"
  done
  for d in "$STAGE"/*/; do
    repo="$(basename "$d")"
    git -C "$d" push -f "git@github.com:$ORG/$repo.git" main && ok "pushed $repo"
  done
  say "All 16 repositories pushed. Add submodules to main next:"
  echo "    see the 'Submodules' section of docs/REPO_MAP.md"
else
  say "Nothing was pushed (dry run). To push everything:"
  echo "    ./scripts/split_repos.sh --push"
fi
