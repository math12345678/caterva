# ADR 0140: The step named "Install pnpm" installed no pnpm

**Status:** Accepted, implemented

**Date:** 2026-08-20

**Context:** `.github/workflows/tests.yml`, `scripts/check_ci_toolchain.py`

**Supersedes the diagnosis in:** the libroadrunner pin change, which was
wrong and is described below rather than quietly dropped.

## The failure

CI had been red on every push for two days. The `api-server` job read:

```yaml
- name: Install pnpm
  run: corepack prepare pnpm@11.4.0 --activate

- name: Install workspace dependencies
  working-directory: Science-Agent-Pipeline
  run: pnpm install --frozen-lockfile
```

`corepack prepare --activate` **exits 0 and writes no `pnpm` onto PATH.**
`corepack enable` is the command that writes the shims. So the step named
"Install pnpm" reported success, and every later step died on
`pnpm: command not found`.

That is this project's own rule turned on its own build file. A step that
cannot fail, named after the thing it does not do, sitting one line above the
step it was supposed to make work.

## Reproduced, not inferred — and the difference is the whole ADR

The **previous** attempt on this same red build read `pip install` output,
concluded `libroadrunner==2.8.0` did not exist, and changed the pin, the
numpy version, and dropped Python 3.13 from the matrix. All of it was wrong:
2.8.0 exists with cp310–cp313 **x86_64** wheels, the sandbox is aarch64, and
GitHub's runners are x86_64. A local observation was generalised to a machine
it did not describe. `scripts/check_pins_resolve.py` exists because of it and
deliberately refuses to check local resolution.

So this diagnosis was held to a standard the last one failed. On Node
v22.23.2 with corepack 0.34.6 — **the runner's own Node major** — in a clean
`COREPACK_HOME`:

```
$ which pnpm
(nothing)
$ corepack prepare pnpm@11.4.0 --activate
Preparing pnpm@11.4.0 for immediate activation...
$ echo $?
0
$ which pnpm
(nothing)                       <- the next step is already dead

$ corepack enable --install-directory /tmp/shims
$ ls /tmp/shims
pnpm  pnpx  yarn  yarnpkg
$ pnpm --version
11.20.0
```

Nothing here is a claim about wheels, interpreters, or CPUs. Whether
`corepack prepare` writes a shim is identical on every architecture. **That
is the only reason a local result was permitted to settle it.**

I also checked the thing I would otherwise have assumed: both `pnpm@11.4.0`
and `pnpm@11.20.0` are real published versions. The obvious guess — "11.4.0
doesn't exist" — was wrong, and would have been the libroadrunner mistake
again in a different registry.

## The version was a fiction too

`Science-Agent-Pipeline/package.json` declares `"packageManager":
"pnpm@11.20.0"`. Corepack's shim reads that field and runs **that** version
whatever `prepare` named. The last line of the reproduction is the proof:
with `packageManager: pnpm@11.20.0` in scope, the shim ran `11.20.0`.

So `11.4.0` was never going to run even in the world where the step worked.
Two people reading the workflow would disagree about which pnpm CI uses, and
both would be wrong. The replacement therefore **names no version at all** —
a version written in the workflow can only agree with the manifest or lie
about it, and there is no third option worth having.

## The guard

`check_ci_toolchain.py`, with `--selftest`:

1. A job that runs `pnpm` must run `corepack enable` in an **earlier** step.
2. `corepack prepare pnpm@X --activate` standing in for enabling is reported
   and named for what it is: a no-op that exits 0.
3. A pnpm version written into a workflow must equal the `packageManager`
   field that actually decides.

Mutation-tested against the specific historical failure, which is the only
evidence this project accepts that a guard works. With the original line
restored the guard exits 1; restored to `corepack enable`, it exits 0.

It cannot determine the deciding version, it says **"could not be
determined"** and reports it — never "the versions agree". Same three-state
discipline as everywhere else: "could not check" must not render as "checked
and fine". PyYAML missing exits **3**, not 0, for the same reason.

It runs in the **Python** job, not the job it describes. A guard living
inside the broken job reports the breakage after the breakage.

## What is still unknown, stated plainly

**This fixes the `api-server` job. It does not explain the `test` job.**

The `test` job never invokes pnpm, so nothing above touches it. I could not
determine its cause:

- GitHub Actions logs are not readable from this sandbox.
- `check_env.py` and the engine suites need libroadrunner, which has no
  aarch64 wheel — so a local failure there is **uninformative**, which is
  precisely the trap of two days ago.
- What I could run is green: `check_pins_resolve` (15 pins, all published),
  `check_guard_wiring` (67 guards), `check_forbidden_packages`,
  `check_adr_index`, `check_doc_links`, `check_documented_counts`,
  `check_both_front_ends_read_it`, `check_findings_reach_a_surface`.

The honest verdict on the `test` job is **INDETERMINATE**, not "probably the
same thing". Recorded as such rather than closed. Task #14 stays open with
its scope narrowed to one job.

## Consequences

- A red badge on an open-source repository tells a visiting professor the
  project's claims about checking things are decoration. This was the most
  expensive broken thing in the tree and it was four words of YAML.
- Guard count 66 → 67.
- The nearest lesson, recorded a fifth time: **a check that reports success
  without doing its work is worse than no check, because it is trusted.** It
  had never before been applied to the build file itself.

## Related

- `scripts/check_pins_resolve.py` — written after the wrong diagnosis of
  this same build
- [ADR 0130](0130-green-was-a-local-opinion.md) — the last time a local
  result was mistaken for a general one
