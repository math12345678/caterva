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

# Staging area for repos assembled from scattered files. Defined here,
# beside the other config, because the terium replay below uses it and
# `set -u` turns a late definition into a hard failure.
STAGE="${TMPDIR:-/tmp}/terrium-split"
PUSH="${1:-}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# The commit that renamed Tellurium/ -> Terium/. History for the engine
# lives under the OLD path, so its split runs from the commit before this
# one and replays the rename on top. See docs/REPO_MAP.md.
RENAME_COMMIT="$(git log --format=%H --grep='Rename Tellurium -> Terium' -n 1 || true)"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()  { printf '  \033[32m✓\033[0m %s\n' "$*"; }

# ---------------------------------------------------------------------------
# Standalone scaffolding.
#
# A split repository inherits nothing: no .gitignore, no CI, no packaging.
# Without these, `git clone && pytest` fails on a fresh machine and the
# repository is a backup rather than something anyone can use.
# ---------------------------------------------------------------------------

scaffold_terium() {
  local d="$1"

  cat > "$d/pyproject.toml" <<'TOML'
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "terium"
version = "0.1.0"
description = "Terrium's simulation engine: 15 domains, every numerical claim checked against an independent source of truth"
requires-python = ">=3.10,<3.14"
dependencies = ["libroadrunner==2.8.0", "antimony==2.14.0", "python-libsbml", "numpy", "scipy"]

[tool.setuptools.packages.find]
include = ["Terium*"]

[tool.pytest.ini_options]
testpaths = ["Terium/tests"]
TOML

  cat > "$d/requirements.txt" <<'REQ'
# Do NOT `pip install tellurium`. The umbrella package pulls in
# python-libcombine and python-libnuml, neither of which this engine uses,
# and on any platform without prebuilt wheels the install dies at the cmake
# step. See ADR 0001 in the `documents` repository.
libroadrunner==2.8.0
antimony==2.14.0
python-libsbml
numpy
scipy
pytest
hypothesis
REQ

  # Eight test modules import guard scripts from `scripts/`, which lives in
  # the `wiring-main` repository. They test the GUARDS, not the engine, and
  # in a standalone clone there is nothing for them to import.
  #
  # They are skipped here rather than deleted, and the skip ANNOUNCES itself
  # -- a silent skip is indistinguishable from a pass, which is the defect
  # `check_no_disabled_tests` exists to prevent. Under the umbrella checkout
  # `scripts/` is reachable, nothing skips, and the count stays 1,014.
  cat > "$d/conftest.py" <<'PY'
"""Standalone-clone support for the Terium engine.

Eight test modules import guard scripts that live in the `wiring-main`
repository (`scripts/check_*.py`). Cloned on its own, this repository has no
such directory, and those modules cannot be collected at all -- pytest
reports an ImportError and exits before running anything.

Rather than let a fresh clone look broken, they are skipped when `scripts/`
is absent, and the skip says so out loud. A clean skip is invisible in a CI
summary; an announced one is a fact a reader can act on.

Under the umbrella checkout (`Terrium-sim/main`, cloned --recursive) the
directory IS reachable, nothing skips, and the engine reports its full
1,014 tests.
"""
import pathlib
import sys

import pytest

_HERE = pathlib.Path(__file__).resolve().parent

# The umbrella layout puts wiring-main beside this repository.
_CANDIDATES = [_HERE / "scripts", _HERE.parent / "wiring-main", _HERE.parent / "scripts"]
_SCRIPTS = next((p for p in _CANDIDATES if p.is_dir()), None)

GUARD_BACKED_TESTS = {
    "test_citation_format.py",
    "test_dependencies_declared.py",
    "test_engine_contract.py",
    "test_forbidden_packages.py",
    "test_package_reexports.py",
    "test_plausibility_constants.py",
    "test_popgen_correctness.py",
    "test_rng_convention.py",
}

if _SCRIPTS is not None and str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
else:
    print(
        "\n[terium] The guard scripts (wiring-main) are not reachable from "
        "this checkout, so %d test module(s) that exercise them are SKIPPED, "
        "not passing. Clone the umbrella for the full suite:\n"
        "    git clone --recursive https://github.com/Terrium-sim/main.git\n"
        % len(GUARD_BACKED_TESTS)
    )


def pytest_collection_modifyitems(config, items):
    if _SCRIPTS is not None:
        return
    skip = pytest.mark.skip(
        reason="needs the guard scripts from Terrium-sim/wiring-main; "
               "clone Terrium-sim/main --recursive to run these"
    )
    for item in items:
        if pathlib.Path(str(item.fspath)).name in GUARD_BACKED_TESTS:
            item.add_marker(skip)
PY

  cat > "$d/.gitignore" <<'IGN'
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.hypothesis/
.coverage
htmlcov/
.venv/
venv/
.DS_Store
IGN

  mkdir -p "$d/.github/workflows"
  cat > "$d/.github/workflows/tests.yml" <<'YML'
name: engine

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        # The supported window. libroadrunner 2.8.0 and numpy 2.2.x publish
        # wheels through cp313 and keep the cp310 floor; the 2.9.x line drops
        # cp310. See ADR 0014 in the `documents` repository.
        python: ["3.10", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
      - run: pip install -r requirements.txt
      - run: python -m pytest Terium/tests -q
      - name: The CLI must actually run
        run: python -m Terium.cli --help
YML
}

# What each split repo is, so it gets the right CI and README.
# repo -> kind
kind_of() {
  case "$1" in
    tests)                          echo python ;;
    terrium-site|landing|backend-main|science-agent-pipeline-replit) echo node ;;
    mule)                           echo static ;;
    *)                              echo none ;;
  esac
}

# Adds .gitignore, a CI workflow and the repo's README to a split branch, as
# one commit on top of the preserved history.
#
# Without this a split repo has no CI at all -- the monorepo's workflow stays
# behind in wiring-main -- and no .gitignore, so the first `npm install` in a
# clone offers 90 MB of node_modules for commit.
add_scaffold_commit() {
  local repo="$1" path="$2"
  local wt="$STAGE/_scaffold/$repo"

  rm -rf "$wt"; mkdir -p "$wt"
  git -C "$wt" init -q -b scaffold
  git -C "$wt" fetch -q "$ROOT" "split/$repo"
  git -C "$wt" checkout -q FETCH_HEAD

  scaffold_generic "$wt" "$(kind_of "$repo")" "$repo"

  if [ -f "$ROOT/docs/readmes/$repo.md" ]; then
    cp "$ROOT/docs/readmes/$repo.md" "$wt/README.md"
  fi

  git -C "$wt" add -A
  if git -C "$wt" diff --cached --quiet; then rm -rf "$wt"; return 0; fi

  git -C "$wt" -c user.name="$(git config user.name)" \
               -c user.email="$(git config user.email)" \
               commit -q -m "Add standalone scaffolding

A split repository inherits nothing from the monorepo -- no .gitignore, no
CI, no README. This adds the minimum for it to stand on its own: the
workflow that runs its own tests, the ignore rules its toolchain needs, and
the README describing what it holds.

Cross-cutting guards stay in wiring-main and run against the umbrella
checkout, because they read across repository boundaries by design."
  git fetch -q "$wt" scaffold:"split/$repo" --force 2>/dev/null || \
    { git -C "$wt" branch -f scaffold HEAD; git fetch -q "$wt" scaffold:"split/$repo" --force; }
  rm -rf "$wt"
}

scaffold_generic() {  # dir, kind(python|node|static), name
  local d="$1" kind="$2" name="$3"
  [ "$kind" = "none" ] && { : ; }
  mkdir -p "$d/.github/workflows"

  cat > "$d/.gitignore" <<'IGN'
node_modules/
dist/
build/
coverage/
__pycache__/
*.py[cod]
.pytest_cache/
.venv/
venv/
.DS_Store
*.log
IGN

  case "$kind" in
    python)
      cat > "$d/.github/workflows/tests.yml" <<YML
name: $name

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: pip install -r requirements.txt
        if: hashFiles('requirements.txt') != ''
      - run: python -m pytest . -q
YML
      ;;
    node)
      cat > "$d/.github/workflows/tests.yml" <<YML
name: $name

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
      - run: npm ci || npm install
      - run: npm test --if-present
      - run: npx tsc --noEmit || true
YML
      ;;
    static)
      # The asset checker travels WITH the repo, because a CI step that
      # greps inline is exactly how the first version of this check produced
      # 33 false positives (data: URIs split on spaces, #anchors read as
      # files). A checker that cries wolf gets deleted, and then the real
      # 404 ships.
      mkdir -p "$d/scripts"
      cp "$ROOT/scripts/check_static_assets.py" "$d/scripts/"
      cat > "$d/.github/workflows/tests.yml" <<YML
name: $name

on: [push, pull_request]

jobs:
  assets:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - name: Every referenced asset and ES module must exist
        run: python scripts/check_static_assets.py index.html
YML
      ;;
  esac
}

# HTTPS or SSH. HTTPS is the default because the monorepo's own `origin` is
# HTTPS and pushes successfully, so those credentials are already cached --
# whereas `git@github.com` needs a key that may not exist on this machine.
# Choosing the protocol that is already known to work beats choosing the one
# that is conventional.
case "$PUSH" in
  --push-https) PROTOCOL="https"; PUSH="--push" ;;
  --push-ssh)   PROTOCOL="ssh";   PUSH="--push" ;;
  *)            PROTOCOL="https" ;;
esac

remote_for() {
  if [ "$PROTOCOL" = "ssh" ]; then
    printf 'git@github.com:%s/%s.git' "$ORG" "$1"
  else
    printf 'https://github.com/%s/%s.git' "$ORG" "$1"
  fi
}

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
mule	mule
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
  add_scaffold_commit "$repo" "$path"
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
  PRE=$(git rev-list --count split/terium)

  # The split ends in the PRE-rename state, because that is where the
  # history lives. Replay the rename on top so the branch preserves the
  # history AND lands in the state the engine is actually in -- otherwise
  # the pushed repo would be correct about the past and wrong about now.
  RTMP="$STAGE/_terium_head"
  rm -rf "$RTMP"; mkdir -p "$RTMP"
  git -C "$RTMP" init -q -b replay
  git -C "$RTMP" fetch -q "$ROOT" split/terium
  git -C "$RTMP" checkout -q FETCH_HEAD
  git -C "$RTMP" rm -rq . >/dev/null 2>&1 || true
  # Nested under Terium/, NOT flattened to the repo root.
  #
  # `git subtree split -P Terium` strips the prefix, so the split lands with
  # __init__.py, cli.py and tests/ at the top level. The package is then not
  # importable as `Terium`, and every test doing `from Terium import
  # terium_engine` fails on a fresh clone:
  #
  #     ModuleNotFoundError: No module named 'Terium'
  #
  # Verified by extracting the split branch into a temp directory and running
  # pytest: 12 collection errors. A repository whose own test suite cannot be
  # collected is not a published repository, it is a backup.
  mkdir -p "$RTMP/Terium"
  cp -R "$ROOT/Terium/." "$RTMP/Terium/"
  find "$RTMP" -maxdepth 1 -mindepth 1 \
       ! -name '.git' ! -name 'Terium' -exec rm -rf {} + 2>/dev/null || true

  # Untracked junk the monorepo's .gitignore hides but `cp -R` does not.
  find "$RTMP" \( -name '__pycache__' -o -name '.DS_Store' -o -name '.coverage' \
                  -o -name '*.pyc' -o -name '.pytest_cache' -o -name '.mypy_cache' \
                  -o -name '.hypothesis' \) \
       -not -path "$RTMP/.git/*" -prune -exec rm -rf {} + 2>/dev/null || true

  scaffold_terium "$RTMP"
  git -C "$RTMP" add -A
  git -C "$RTMP" -c user.name="$(git config user.name)" \
                 -c user.email="$(git config user.email)" \
                 commit -q -m "Rename Tellurium -> Terium

The upstream Tellurium project is unrelated to this engine: requirements.txt
has always said 'do NOT pip install tellurium' (ADR 0001), and this code
imports it nowhere, calling libroadrunner and antimony directly. The old
name implied a relationship that does not exist.

The $PRE commits before this one are the engine's real history, recovered
from the pre-rename path -- 'git subtree split -P Terium' alone returns a
single commit, because the path only exists from the rename forward."
  # `checkout FETCH_HEAD` detaches, so the commit above landed on a detached
  # HEAD and the `replay` branch never pointed at it. Name it explicitly
  # before fetching, and fetch by ref rather than by SHA -- the SHA is not an
  # object this repository has yet.
  git -C "$RTMP" branch -f replay HEAD
  git fetch -q "$RTMP" replay:split/terium --force
  ok "terium                         $(git rev-list --count split/terium) commits  <- Tellurium/ + replayed rename"
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
build_fileset frontend-main docs/readmes/frontend-main.md \
  src/web/dashboard.html src/web/dev-server.mjs src/web/frontend-package.json

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

build_fileset worktrees docs/readmes/worktrees.md Terrium.worktrees/worktree.sh
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
  say "Pushing to $ORG over $PROTOCOL"

  pushed=0
  failed=()

  push_one() {  # repo, then the git args to run
    local repo="$1"; shift
    if "$@" >/dev/null 2>&1; then
      pushed=$((pushed+1)); ok "pushed $repo"
    else
      failed+=("$repo")
      printf '  \033[31m✗\033[0m %s\n' "$repo"
    fi
  }

  for b in $(git branch --list 'split/*' --format='%(refname:short)'); do
    repo="${b#split/}"
    push_one "$repo" git push -f "$(remote_for "$repo")" "$b:main"
  done
  for d in "$STAGE"/*/; do
    [ -d "$d/.git" ] || continue
    repo="$(basename "$d")"
    push_one "$repo" git -C "$d" push -f "$(remote_for "$repo")" main
  done

  total=$((pushed + ${#failed[@]}))

  # Report what HAPPENED, not what was attempted.
  #
  # The first version ran `git push ... && ok "pushed $repo"` in a loop and
  # then printed "All 16 repositories pushed" unconditionally. On a machine
  # with no SSH key every push failed and it still printed that line -- the
  # exact success-on-failure this repository's guards exist to eliminate,
  # in the script that publishes them. `set -e` does not help: a failing
  # command on the left of `&&` is a tested condition, not an error.
  if [ ${#failed[@]} -gt 0 ]; then
    say "FAILED: $pushed of $total pushed; ${#failed[@]} failed"
    printf '  %s\n' "${failed[@]}"
    cat >&2 <<EOF

Nothing about the split branches is wrong -- they are built and correct.
This is an access problem.

  Permission denied (publickey)  ->  no SSH key on this machine.
                                     Re-run over HTTPS instead:

                                       ./scripts/split_repos.sh --push-https

                                     Your monorepo 'origin' is already HTTPS
                                     and pushes fine, so those credentials
                                     are cached and will be reused.

  Repository not found           ->  the repo does not exist under $ORG,
                                     or your account cannot write to it.
EOF
    exit 1
  fi

  say "All $pushed repositories pushed. Add submodules to main next:"
  echo "    docs/PUBLISHING.md section 3"
else
  say "Nothing was pushed (dry run). To push everything:"
  echo "    ./scripts/split_repos.sh --push         # SSH"
  echo "    ./scripts/split_repos.sh --push-https   # HTTPS"
fi
