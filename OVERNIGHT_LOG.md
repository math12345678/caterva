# OVERNIGHT_LOG

Unsupervised overnight loop log for Terrium. One committed change per cycle;
each entry records what was done, what it was verified against, and what's
next. See the loop task spec for the backlog.

---

## Cycle 1 — 2026-08-04 (backlog item a: dead `vmax = 5.0` fallback)

**What I did.** Deleted the dead `else: vmax = 5.0` fallback in
`run_mm()` in `Science-Agent-Pipeline/artifacts/api-server/src/lib/tellurium_runner.py`,
replacing it with an explicit `ValueError` that mirrors the zod schema
message ("mm needs a Vmax: supply vmax directly, or supply BOTH kcat and
enzyme_conc (Vmax = kcat * [E]0)").

Note on authorship: while I was running the test gates, a concurrent
process (repo owner Smyan's account) committed the identical change as
`ba01cd4` ("fix: reject any mm query with no route to a Vmax (dead vmax=5.0
fallback)", 3 files: provenance.test.ts +49, tellurium_runner.py +10/-1,
test_vmax_from_kcat.py +24). My working tree is byte-identical to that
commit (empty `git diff HEAD` for all three files), and every gate below
ran against this exact tree, so the verification stands regardless of who
typed the commit.

**Why it was dead (call-path trace).** `POST /api/simulate` ->
`runPipeline()` -> `resolveQuery()` throws `RequiredParametersMissingError`
on any default-origin vmax before the runner is ever spawned (both the LLM
and fallback branches), and `validateParameters()` (zod `mm` schema) also
requires vmax OR kcat+enzyme_conc. `runTellurium()` is only invoked from
`routes/simulate.ts` and golden tests that supply full params. So the branch
that runs with no vmax, no kcat, no enzyme_conc is unreachable from any API
query. It was also a lie: `schemas.ts` documents "the runner rejects a
request that supplies neither" — the runner silently defaulted instead.

**Verified against.**
- New TS regression test (provenance.test.ts): "simulate enzyme kinetics
  km=2 s0=10 end=10 points=51" -> `RequiredParametersMissingError` with
  `missing == ["vmax"]` exactly (s0/end/points are user-supplied, so vmax is
  the precise key the fallback would have fabricated). Plus a half-conversion
  case (kcat alone / enzyme_conc alone) still blocked.
- New Python test (test_vmax_from_kcat.py): `run_mm()` with no route to a
  Vmax raises ValueError.
- Mutation test (Rule 6, personally run): re-added `vmax = 5.0`, the new
  Python test failed with "DID NOT RAISE ValueError", reverted from backup
  (steps `;`-separated), suite green again.
- Gates: api-server `tsc --noEmit` clean; `pnpm --filter @workspace/api-server
  run test` 271/271 (was 269); `make test` engine 884 + literature 237 (was
  883 engine) — all green.

**What's next.**
- Backlog item b: spot-check 2-3 "Accepted" ADRs in docs/adr/ against the
  files they describe.
- Follow-up candidate (judgment call, not done this cycle to keep scope to
  one item): `run_mm_competitive_inhibition()` has the same dead-default
  idiom via `params.get("vmax", 5.0)`. It is equally unreachable (vmax is a
  hard-blocked default for that domain too) but uses the conventional `.get()`
  pattern shared by every domain's runner function, so I did not change it
  under item (a). A future cycle could decide whether the whole
  runner-side `.get(default)` idiom should be tightened the same way.
- Also noticed (not acted on): `.aider.chat.history.md`, `.freebuff/`, and
  `Science-Agent-Pipeline/artifacts/api-server/data/` are untracked tool/runtime
  artifacts; they predate this cycle and were left untouched.
