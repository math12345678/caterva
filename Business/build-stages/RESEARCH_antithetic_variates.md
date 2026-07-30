# Research grounding — antithetic variates (for future Monte Carlo variance-reduction work)

Status: grounding only, not yet part of any active spec. Monte Carlo's
Stage 1 spec (`STAGE_01_PART_02.md`, Section 3) explicitly listed variance
reduction as out of scope for the first implementation. This file exists so
the grounding isn't lost between now and whenever that scope actually gets
picked up — per `Business/BUILD_PIPELINE.md`, research output becomes input
to a future spec, not something implemented directly from.

## Cross-check note

Both Kimi and Perplexity were asked the same three questions independently.
They agree on every substantive claim: the pairing construction (`X` and
`1-U`/`-Z` complement), the variance formula
`Var(AV) = (σ²/2n)(1+ρ)`, the monotonicity sufficient condition
(Hammersley & Morton 1956), and the exact same failure mode (drawing an
independent second sample instead of the true complement, which silently
degrades to plain Monte Carlo with wasted compute). Agreement between two
independently-queried tools on a checkable mathematical claim is a real,
if informal, cross-check — not proof, but more grounding than either
answer alone.

## What a future spec's Verification Target (Section 6) can use directly

**Test case with a known, checkable variance-reduction factor:**
`h(u) = sqrt(u)` on `Uniform(0,1)`, true mean `2/3`. Monotone, so the
Hammersley–Morton condition applies and `Cov(h(U), h(1-U)) < 0` is
guaranteed, not just expected. Pass criterion: the empirical variance
ratio `R = Var(antithetic) / Var(plain MC, same total evals)` should come
in meaningfully below 1 (order 0.2–0.6 per both sources) and be stable
across repeated macro-replications. `R ≈ 1` or `R > 1` means the pairing is
broken.

**Direct correlation check**, independent of the variance-ratio test above
(both sources called this out as the sharper diagnostic): compute
`Corr(h(U_i), h(1-U_i))` across pairs and assert it's negative. If it's
≈0, the implementation almost certainly drew an independent second sample
instead of the true complement — the exact mistake both sources flagged as
the realistic failure mode, and the one worth a dedicated mutation test
when this domain gets built (mutate `1 - u` into a fresh independent draw,
confirm the correlation-sign test catches it).

**Primary sources cited by both, worth pulling if a written ADR ever
references this:** Hammersley & Morton (1956), *A New Monte Carlo
Technique: Antithetic Variates*, Proc. Cambridge Philos. Soc.; Glasserman,
*Monte Carlo Methods in Financial Engineering* (2003), the antithetic
variates section.

## What this does NOT do

This does not authorize starting antithetic-variates implementation now.
The base Monte Carlo spec scoped it out deliberately, and per
`Business/ROADMAP.md`'s own scope-discipline note, adding scope beyond
what's been deliberately chosen is exactly the failure mode that note
warns against. This file is grounding banked for later, not a green light.
