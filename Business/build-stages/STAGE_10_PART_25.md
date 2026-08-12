# Stage 10, Part 25 — closing a literature question by proving it cannot be answered

Stage: 10 · Part: 25 · 2026-08-11

## 1. The endpoint guard now covers 85 files instead of 4

Part 24 left this open: `check_example_endpoints` checked 4 files, and
widening it to the root documents needed prose understanding, or it would
produce exactly the false positives Part 24 was about.

Now globbed, not listed — **568 endpoint claims across 2 examples and 83
documents**, against the 39 routes of both servers. A list is precisely the
mechanism by which the 24th document arrives unchecked.

Five prose forms are classified and excluded, each with the real line that
earned the rule:

| form | example |
|---|---|
| family, not an address | `/api/jobs/*` |
| nginx prefix routing | `location /api/ {` |
| a tutorial on *adding* an endpoint | `if (pathname === '/api/custom')` |
| a roadmap item | ``- Add `/api/jobs/:id/export` `` |
| a banner *warning* a route is fake | `lists non-existent /api/literature/search` |

The last is the sharpest: flagging a correction banner punishes a document
for telling the truth, and the obvious way to go green would be to delete
the warning.

**The ordering matters and was wrong at first.** Classifying before
route-matching excused 52 mentions, most of them naming routes that *do*
exist — silent coverage loss, ready to hide a future edit. Inverted, so
classification only ever runs on a mention the route table failed to
resolve: a loose rule can now cost a missed defect on an absent endpoint,
but can never narrow coverage of a present one.

**A hole the mutation test found:** the fake endpoint used to prove the
guard was named `/api/zzzfabricated/status`, and it was waved through —
"fabricated" is a negation keyword, so the endpoint excused *itself*. Any
route called `/api/removed-items` or `/api/add-job` had the same free pass.
Keyword rules now blank every `/api/...` token before reading the line.

Genuine defects found across all 83 documents: **zero**. The two real ones
were fixed in Part 24.

## 2. σ for SEIR: the answer is "no", and now it is a cited "no"

`seir.sigma = 0.2` has been an UNVERIFIED teaching default for a 5-day
latent period. A search on 2026-08-09 left it open. I searched again
(PubMed + Consensus) and closed it — in the negative, with evidence.

### Three quantities, routinely conflated

| quantity | measures | what uses it |
|---|---|---|
| incubation period | infection → **symptoms** | case definitions, isolation |
| serial interval | symptoms → symptoms | R0 estimation, generation-time proxy |
| **latent period** | infection → **infectiousness** | **σ in SEIR** |

Almost everything published measures the first two. σ needs the third.

### The substitution is directionally wrong, not merely imprecise

Alene et al. (2021), *BMC Infect Dis* 21:257 — pooled **serial interval
5.2 d**, pooled **incubation 6.5 d**, from 23 and 14 studies.

A serial interval *shorter* than the incubation period is the signature of
**presymptomatic transmission**: infectiousness begins before symptoms.
Therefore the latent period is **strictly shorter** than the incubation
period. Feeding an incubation figure into σ would overstate the latent
period and **under-predict how fast an epidemic takes off** — the error
makes the model look reassuring, which is the worst direction available.

Two further meta-analyses report incubation only, never latent:

- Elias et al. (2021), *Int J Infect Dis* 104:708–710 — 99 studies, pooled
  6.38 d (95% CI 5.79–6.97).
- Wu et al. (2022), *JAMA Netw Open* 5(8):e2228008 — 142 studies, pooled
  6.57 d.

### Two candidates, both rejected, for different reasons

**Hou et al. (2020)** was already rejected: a single-city SEIR fit whose own
abstract says other parameters were "suppose as unchanged". It *assumes* a
latent period rather than measuring one — citing it would launder an
assumption into a citation.

**Kang et al. (2022)**, *Eurosurveillance* 27(10), is new and better: a
directly **measured** mean latent period of **3.9 d**. Rejected anyway,
because it is the **Delta** variant while this registry entry is the
**ancestral strain** — and the two are not interchangeable. Delta's serial
interval is 3.9 d (Madewell et al. 2023) against ancestral 5.45 d (Hussein
et al., the registry's own source). Pairing a Delta latent period with an
ancestral serial interval is exactly the cross-study stitching the
registry's same-source rule forbids.

Wu et al. quantify how variant-dependent this is: incubation of **5.00 d
(Alpha), 4.50 (Beta), 4.41 (Delta), 3.42 (Omicron)**. A single COVID-19 σ
is not a well-defined quantity; the honest future fix is a per-variant
registry, and that is now recorded as the promotion criterion.

### The guard that keeps σ from acquiring a source by accident

`TestNoLatentPeriodIsOffered` asserts `EpidemiologyResult` exposes no
`latent_period_days`, `incubation_period_days` or `sigma` field, and that
`infectious_period_measure` still says "serial interval" out loud.
Mutation-verified: adding a `latent_period_days` field fails with the
reason and the pointer to the inventory entry.

This is the part worth generalising. **A negative literature result is a
result**, and it decays the same way a positive one does — the previous
note said a search "did not close it", which invites the next person to
repeat the search and, on a tired day, to accept Kang et al. without
noticing the variant mismatch. A rejection is only durable if it records
*what was rejected and why*.

## 3. What was NOT added, and why that is the finding

Measles was an obvious registry candidate: R0 is famously quoted as 12–18.

Guerra et al. (2017), *Lancet Infect Dis* — a systematic review of 18
studies giving 58 R0 estimates — concludes the range is **wider** than
12–18 and that estimates must be locally derived. Fu et al. (2026), *PLOS
Glob Public Health*, fitted 172 serosurveys across 57 countries and found
R0 from 0.93 to 147, with **fewer than 13% of studies falling in 12–18 at
all**.

So the widely-cited number is not a measurement of measles; it is a range
that most measurements fall outside. Adding `measles.r0 = 15` with a Lancet
citation would have produced the most convincing wrong number in the
repository — a real DOI, a real systematic review, attached to a figure its
own authors argue against.

`TestUnknownDiseaseNeverFabricates` already names measles as a disease that
must *not* resolve. It now has a second, stronger reason on the record.

## 4. Verification

| check | result |
|---|---|
| Python suites | **277 passed, 1 skipped** |
| api-server provenance/citation suites | **129 / 129** |
| `tsc --noEmit`, both trees | 0 errors |
| static guards | **21 / 21** |
| `check_example_endpoints` | 568 claims, 85 files, 39 routes, 0 defects |
| documented counts | updated 1,289 → **1,291** (1,014 engine + 277 literature) |

Mutation tests this part: a fabricated endpoint in a curl, in a table row,
a self-excusing endpoint name, and a `latent_period_days` field appearing
on the resolver — all four caught.

## 5. Open

- σ remains UNVERIFIED, correctly. Promotion needs R0 **and** a measured
  latent period for the same disease *and* variant under compatible
  methodology; a per-variant registry is the likely shape.
- 29 other UNVERIFIED entries remain. Most are genuinely uncitable —
  `s0`, `i0`, `a0`, `n0` are experimental conditions the user chooses, and
  citing them would be the category error this project already refuses.
  The remaining citable candidates are the Lennard-Jones reduced-unit
  conventions (`molecular_dynamics.density/temperature/timestep`) and
  `pcr.efficiency`, none of which are in PubMed's scope — they need a
  physics/chemistry source, not a biomedical one.
