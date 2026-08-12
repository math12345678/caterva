# worktrees

Part of [**Terrium**](https://github.com/Terrium-sim/main) — scientific computing for teaching labs.

Scratch space for `git worktree add`.

**This repository is intentionally empty.** `Terrium.worktrees/` in the
monorepo tracks no files — it is where worktrees get checked out when
several agents work on the same repository at once. It is published so that
an empty repo is not mistaken for a failed push.

```bash
git worktree add ../Terrium.worktrees/feature-x -b feature-x
```

---

This repository is a submodule of [`Terrium-sim/main`](https://github.com/Terrium-sim/main). Clone the whole system with:

```bash
git clone --recursive https://github.com/Terrium-sim/main.git
```
