# What to run next

Everything below is copy-paste. Each step says what it does, what you should
see, and what to do if you see something else.

**Every command assumes you start here:**

```bash
cd ~/Desktop/Coding/Terrium
```

---

## Step 0 — Deal with your uncommitted work first (2 min)

You have **33 modified files** that I did not touch — including a change to
`PARAMETER_PATTERN` in `queryResolver.ts` that adds `seed`. My commits are
separate from these. Before running anything else, decide what happens to
them.

**See what they are:**

```bash
git status
```

**Then pick one:**

```bash
# (a) Keep them — commit to your own branch
git add -A && git commit -m "WIP: seed parameter support"

# (b) Park them — set aside, restore later with `git stash pop`
git stash

# (c) Discard them — PERMANENT, cannot be undone
git checkout -- .
```

> Do not skip this. Steps 1–3 are read-only, but it is much easier to tell
> what broke if the tree is clean when you start.

---

## Step 1 — Confirm nothing I changed broke anything (~5 min)

```bash
make test
```

**Expect:**

```
857 passed, 1 skipped      <- simulation engine
182 passed                 <- literature layer
```

Wait — **the skip should now be gone.** I converted six self-skipping tests to
assertions, so you should see:

```
858 passed                 <- no "skipped"
182 passed
```

| What you see | What it means | What to do |
|---|---|---|
| `858 passed` + `182 passed` | Everything worked | Go to Step 2 |
| any `N skipped` | A test declined to run | Paste the output — that is the bug class I have been chasing |
| any `failed` | A real regression | Paste the output |
| `No module named pytest` | venv problem | Run `rm -rf .venv && make setup`, then retry |

---

## Step 2 — Confirm the API side (~1 min)

```bash
cd Science-Agent-Pipeline && pnpm --filter @workspace/api-server run test
cd ~/Desktop/Coding/Terrium
```

**Expect:** `195 passed (195)`, 11 files, 0 failed.

If your `seed` change from Step 0 is still applied, this number may differ —
that is your change, not a regression. Paste the output either way.

---

## Step 3 — Confirm all the guards pass (~1 min)

```bash
python3 scripts/verify_build.py --quick
```

**Expect:** `✅ ALL CHECKS PASSED`

This runs six guards, two of which I fixed this session because they were
silently passing on broken input.

---

## Step 4 — THE IMPORTANT ONE: capture the kcat fixture (~1 min)

This is the only thing blocking a second literature-resolvable field, and it
needs network access, which I do not have.

```bash
cd ~/Desktop/Coding/Terrium/Tests
../.venv/bin/python brenda_kcat_capture.py
cd ~/Desktop/Coding/Terrium
```

**Then paste me the entire output**, whatever it says. There are three
possible results and all three are useful:

| Output starts with | Meaning | What I do next |
|---|---|---|
| `FOUND label=...` | Real kcat table captured | I build the whole kcat lookup path |
| `NOT FOUND` + a list of tab labels | Wrong label guessed | I read the list, pick the right one, you re-run once |
| `ERROR: could not fetch` | Network/BRENDA down | We retry later |

**Do not hand-write this fixture, and I will not either.** Every fixture in
this repo is a live capture. A hand-written one would put invented data into
the golden set — the exact failure this project has caught three times.

---

## Step 5 — One decision, no command needed

**Do you want Python 3.13/3.14 support?**

Right now the project supports Python 3.10–3.13 (the 3.13 step of ADR 0014 has
landed: `libroadrunner` 2.8.0 and `numpy` 2.1.3 publish cp313 wheels, verified
against PyPI). The remaining question is only whether to go further, to 3.14.

Getting to 3.14 means upgrading to `libroadrunner` 2.9.3 + `numpy` 2.5.x — a
**NumPy 2.x major upgrade** with breaking API changes across 1,040 tests. It
is a stage of work, not a config edit.

- **"Not now"** → nothing to do; the current pin is correct and enforced.
- **"Yes"** → say so and I will scope it as its own stage with real
  verification.

---

## Quick reference

```bash
# the full loop, all at once
cd ~/Desktop/Coding/Terrium
make test                                              # Step 1
cd Science-Agent-Pipeline && pnpm --filter @workspace/api-server run test && cd ..   # Step 2
python3 scripts/verify_build.py --quick                # Step 3
cd Tests && ../.venv/bin/python brenda_kcat_capture.py && cd ..                     # Step 4
```

**If anything breaks:** paste the output. Do not try to fix it first — the
error text is the useful part, and a partial fix makes it harder to read.

---

## What changed this session (for context)

Nine commits. The headline items:

- **`make test` was broken on a clean checkout** — it picked an interpreter by
  version alone and never checked it could run the suite. Fixed twice: once
  for the selection logic, once because my first fix made `make setup` require
  the pytest it installs.
- **A test that had never run a single assertion.** It skipped itself on every
  run for months while being counted in the suite total — and it guarded the
  contract that a flagged literature value must not become a confident number.
  Five more of the same shape found and fixed.
- **The plausibility guard never looked at the literature layer.** Setting
  BRENDA's Km ceiling to 9999 while the engine said 1000 *passed*. That is the
  precise bug ADR 0003 exists to prevent.
- **ADR 0011** — an LLM-supplied parameter is no longer labelled `default`.
  A default is a value this project chose and documented; an LLM value is one
  a model produced. Calling them the same thing was false at the API surface.
- **Stages 1–2 audited** — Wright-Fisher heterozygosity decay, Kimura's
  fixation probability, and Monte Carlo error scaling all re-derived
  independently and confirmed.

Full detail in `Business/build-stages/STAGE_08_PART_02.md`.
