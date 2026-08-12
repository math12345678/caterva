#!/usr/bin/env bash
#
# Worktree helper for Terrium's concurrent-agent workflow.
#
# Several AI agents commit to this repository at once. Running them in the
# same checkout means they overwrite each other's uncommitted work and fight
# over `.git/index.lock` -- which has already happened here, producing three
# consecutive failed git commands and a stale lock file.
#
# A worktree per agent gives each one its own working directory and branch
# against one shared object store: no duplicated clone, no cross-talk.
#
#   ./worktree.sh new  <name>     create ../Terrium.worktrees/<name> on branch agent/<name>
#   ./worktree.sh list            show every worktree and what it is doing
#   ./worktree.sh done <name>     remove it, refusing if work would be lost
#   ./worktree.sh clean           prune worktrees whose directory is gone
#
set -euo pipefail

ROOT="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
TREES="$ROOT/Terrium.worktrees"
cd "$ROOT"

usage() { sed -n '2,16p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

case "${1:-}" in

new)
  name="${2:-}"
  [ -z "$name" ] && { echo "need a name: ./worktree.sh new <name>" >&2; exit 1; }
  dest="$TREES/$name"
  branch="agent/$name"

  [ -e "$dest" ] && { echo "$dest already exists" >&2; exit 1; }

  mkdir -p "$TREES"
  git worktree add -b "$branch" "$dest"

  # A fresh worktree has no venv and no node_modules. Say so rather than
  # letting the agent discover it as a confusing import error.
  cat <<EOF

  Created $dest on branch $branch

  It shares this repository's git objects but has its own working tree.
  Before running anything in it:

      cd $dest
      make setup      # or: pip install -r requirements.txt && npm install

  When finished:

      ./worktree.sh done $name
EOF
  ;;

list)
  printf '%-28s %-26s %s\n' WORKTREE BRANCH STATE
  git worktree list --porcelain | awk -v RS='' '
    { path=""; branch=""; det=""
      for (i = 1; i <= NF; i++) {
        if ($i == "worktree") path = $(i+1)
        if ($i == "branch")   branch = $(i+1)
        if ($i == "detached") det = "detached"
      }
      n = split(path, parts, "/"); short = parts[n]
      sub("refs/heads/", "", branch)
      printf "%-28s %-26s %s\n", short, (branch ? branch : det), path
    }'

  # Uncommitted work is the thing worth knowing before removing anything.
  echo
  for d in "$TREES"/*/; do
    [ -d "$d" ] || continue
    dirty="$(git -C "$d" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
    [ "$dirty" != "0" ] && echo "  ! $(basename "$d"): $dirty uncommitted change(s)"
  done
  ;;

done)
  name="${2:-}"
  [ -z "$name" ] && { echo "need a name: ./worktree.sh done <name>" >&2; exit 1; }
  dest="$TREES/$name"
  [ -d "$dest" ] || { echo "$dest does not exist" >&2; exit 1; }

  # Refuse rather than use --force. `git worktree remove --force` discards
  # uncommitted work silently, and the whole point of running agents in
  # parallel is that their work is not interchangeable.
  dirty="$(git -C "$dest" status --porcelain | wc -l | tr -d ' ')"
  if [ "$dirty" != "0" ]; then
    echo "REFUSING: $name has $dirty uncommitted change(s)." >&2
    git -C "$dest" status --short >&2
    echo >&2
    echo "Commit them, or remove it deliberately:" >&2
    echo "    git worktree remove --force $dest" >&2
    exit 1
  fi

  git worktree remove "$dest"
  echo "Removed $name. Its branch agent/$name still exists:"
  echo "    git branch -D agent/$name    # if you are finished with it"
  ;;

clean)
  git worktree prune -v
  ;;

*)
  usage
  exit 1
  ;;
esac
