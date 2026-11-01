# Caterva landing — verification console

Hand-written core for the landing page. This directory is **not** part of the
100-stage engine build and has no dependency on it.

## What's here

    src/lib/drift.ts                  Wright-Fisher drift + closed form, seeded
    src/lib/pipeline.ts               build architecture + evidence ledger, as data
    src/components/VerificationConsole.tsx   the console UI

## Why this part is hand-written

Two rounds of generated landing pages regressed to the same dark-SaaS
template. The failure was in the instruction, not the tool: aesthetic
adjectives ("dense", "instrument-like") resolve toward the mean. The
interactive core also carries real numerical constraints that are easy to get
subtly wrong. So this piece is written by hand and handed over fixed; the
surrounding page is built around it.

## Verified before shipping

- `tsc --strict --noUnusedLocals --noUnusedParameters` — clean.
- `prepare()` runs in ~343ms, deterministic (identical across runs).
- Correct model: max deviation 0.0054 vs tolerance 0.02 — PASS, 3.7x margin.
- Bugged model (2N -> N): max deviation 0.1211 — FAIL, exceeds by 6.1x.

## One non-obvious constraint

`CONFIG.replicates` is 2000 and must not be lowered casually. Sampling noise
on mean heterozygosity at lower counts: 200 -> 0.0294, 500 -> 0.0234,
1000 -> 0.0140, 2000 -> 0.0054. The tolerance is 0.02, so **at 200 replicates
the CORRECT implementation displays FAIL** — the demo inverts and the page
argues against itself. 2000 is the first value with real margin.

## Rules for whatever builds around this

- Treat these three files as fixed. Import, don't rewrite.
- Never hard-code a number that the code computes at runtime.
- No test-count claim anywhere on the page. It has already gone stale twice.
