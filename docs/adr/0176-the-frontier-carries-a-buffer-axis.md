# ADR 0176: The frontier carries a buffer axis — a condition mismatch is not permanently non-actionable.

**Status:** Accepted

**Date:** 2026-09-08

**Relates to:** ADR 0171 (constraint-propagating search whose frontier is
`ensemble_candidates`), ADR 0172 (the assay window, whose final sentence
this supersedes: *"Buffer gaps stay permanently non-actionable: the frontier
carries no buffer axis"*), ADR 0027 (the model judge's condition rules,
whose buffer comparison this shares), ADR 0028 (a check that fires too
broadly stops being read).

## Context

ADR 0172 turned a pH / temperature mismatch into a search: it gave the
frontier rows a second life as answers. It ended by conceding the buffer
gap — *"the frontier carries no buffer axis"* — and called it permanent.

It was not. The resolver already reads the buffer. `Tests/brenda_client.py`
parses every row's conditions with `parse_assay_conditions` and writes
`assay_buffer = parsed_conditions.buffer`, and `_parse_buffer` extracts real
buffer text from the commentary. Measured on the committed fixtures:

- AChE, `'in 0.1 M MOPS buffer (pH 7.4), at 37°C'` → buffer
  `0.1 M MOPS buffer`, pH 7.4, 37 °C;
- Trypsin, `'in 10 mM Tris, 20 mM CaCl2, pH 7.4, at 37°C'` → buffer
  `10 mM Tris` (four rows).

And a live resolve of AChE acetylcholine returns value 0.0714 mM with
`assay_buffer = "0.1 M MOPS buffer"` — but `ensemble_candidates[0]["buffer"]`
is `None`. The winner already knew the buffer; `_score_frontier` threw it
away before any row reached the window machinery.

Meanwhile `model_compatibility` has reported `buffer_mismatch` as a serious
finding all along — a row really measured in a *different* buffer is judged
incompatible — and the coherence critic can only turn a finding into a
search when some agent can act on it. With no buffer axis on the frontier,
a buffer mismatch was exactly ADR 0171's *"a pH requirement would be a
demand nothing can satisfy"*: true of the resolver's one-row answer, and
false of the frontier, whose rows carry the buffer the finding is about.

Two candidate fixes:

**(a) Keep the buffer a permanent finding** and enrich the judge's wording.
Rejected. The one-place value of ADR 0171 is that a *reported* incompatibility
is either acted on or explicitly out of reach; declaring a whole condition
axis permanently out of reach hides re-searches that the frontier provably
contains — the identical structural gap ADR 0172 closed for the numeric
axes. The only thing the frontier lacked was the key.

**(b) Carry the buffer on each frontier row and let the window name the
reference's buffer**, exactly the ADR 0172 mechanism with one more axis.

## Decision

Option (b). Four pieces:

**1. The frontier carries the buffer.** `_score_frontier` emits
`"buffer": getattr(entry, "assay_buffer", None)` per row, so every actor
downstream re-selects from a row's parsed buffer without a second parse.

**2. One buffer rule, shared with the judge.** `Tests/assay_conditions.py`
gains `buffers_equivalent(a, b)`: strip, casefold, full-string equality, and
`None` is never equal to anything — including `None`. This is deliberately
the comparison `model_compatibility` already uses to report a
`buffer_mismatch`, so the window and the judge can never disagree about
whether a row could remove a mismatch the judge reported. It is deliberately
NOT molarity-aware chemical identity: `buffer_identity.py` already resolves
buffers to PubChem CIDs and dedupes `"500 mM Tris"` vs `"0.5 M Tris-HCl"`,
but it needs live PubChem and normalises *more* than the judge, so a window
built on it could "resolve" a mismatch the judge still sees — the drift
ADR 0027 exists to prevent. The molarity-unaware strictness is the safe
direction: it can only miss a match, which leaves the mismatch standing as
a finding; it can never accept a wrong row.

**3. Buffer is a categorical gate, not a distance.** `within_window`
keeps the per-axis normalised Chebyshev distance for pH and temperature and
adds a hard gate: when the reference states a buffer, the row MUST state an
equivalent one; when it states none, the window demands none. Two deliberate
differences from the numeric axes, both demanded by the thing being
measured:

- **Silence is not compliance.** For pH, a row that states no pH just
  stands at the edge of the distance; for an *identity*, silence under a
  demanded buffer would let any row claim proximity to the demanded buffer
  with no evidence — reporting silence as proximity, the error this module
  exists to refuse. A row silent on a demanded buffer is simply outside.
- **There is no half-width.** Two buffers are the same identity or they
  are not; closeness on the numbers (`distance 0`, exactly the reference's
  pH and temperature) is still outside when the buffer differs. The module
  docstring says it in caps: *THE BUFFER AXIS IS CATEGORICAL, AND SILENCE
  IS NOT COMPLIANCE*.

The window text learns the axis: `pH 7.4; temperature 37; buffer 0.1 M MOPS
buffer`, rendered with whitespace runs collapsed so two spellings of one
buffer deduplicate in the constraint store; `parse_window_requirement`
returns `(ph, temperature_c, buffer)`.

**4. The rest of the machinery, unchanged in shape.** The critic routes
`buffer_mismatch` through the same `_condition_constraint` gate as pH and
temperature — a window is emitted only when exactly one side can move, and
its requirement names the *anchor's* buffer; both movable stays a finding,
neither movable keeps the *"no re-search could remove"* refusal. The scout
re-selects under `within_window` including the gate, carries the chosen
row's OWN buffer (never the replaced default's — the provenance rule of
ADR 0172), and names the chosen row's buffer in the note. The
actionability guard (`scripts/check_constraints_are_actionable.py`) needed
no edit — the `assay_window` kind literal is unchanged — and its selftest
was re-run green before these edits landed.

## Mutation verification

The intended assertions were checked against a green baseline in both
directions by six source mutations (three pairs):

- **Delete the frontier `buffer` key**, and **carry a fabricated buffer
  (`"Tris"`)**: the real-chain sensor
  `test_a_real_buffer_survives_to_the_result_and_the_frontier` fails when
  the AChE row's `0.1 M MOPS buffer` is absent or wrong. Both caught.
- **Delete the gate from `within_window` (buffer always satisfied)**, and
  **force the gate on always (every row demanded a buffer even when the
  reference names none)**: the first fails the silence, different-buffer,
  critic-window and scout tests (six tests) — including the pH flagship and
  the scout's nearest-row test, which must NOT fire on the buffer axis; the
  second fails the no-buffer-required window, the scout, and the original
  pH whole-loop flagship — proving the gate is not permitted to leak into
  windows that state no buffer. Both caught.
- **Drop the chosen row's buffer** (`buffer=None`), and **forward-copy the
  replaced default's buffer into the new row**: both fail the scout's
  buffer selection test and the whole-loop buffer flagship; the second
  catches exactly the provenance error ADR 0172's design note forbids.
- **Remove `buffer_mismatch` from the critic's constraint route** (back to
  the notes-only behaviour): fails the two critic buffer tests and the
  whole-loop buffer flagship.

Each restore was checked against the working tree.

## Consequences

- Buffer gaps are no longer permanent: when the frontier holds a row really
  measured in the reference's buffer, the mismatch becomes a search and the
  report converges with the re-selection named. The committed AChE fixture
  grounds the whole path for real (a 0.0714 mM acetylcholine Km in
  `0.1 M MOPS buffer`), so the feature is exercised by the pipeline, not by
  a fabricated example.
- The window and the judge now share one buffer identity rule by
  construction; a window can never claim to have fixed a `buffer_mismatch`
  the judge would still report.
- The constraint store deduplicates buffers spelled differently but the
  same (whitespace), while the identity rule itself stays strict
  (case-fold and strip only) — so deduplication is about the store's
  canonical text, never about calling different buffers equal.
- What this does NOT do: it does not molarity-normalise (`500 mM Tris` and
  `0.5 M Tris-HCl` still look different, deliberately), it does not
  interpolate or average between buffers, it does not change what the judge
  counts as a *stated* condition (`conditions_stated` remains pH and
  temperature), and a buffer mismatch whose frontier offers no matching row
  still stands as a finding with the reason stated.