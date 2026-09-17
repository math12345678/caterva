# ADR 0174: The empty-organism lookup reported a cross-species minimum — an unnamed organism now means "any organism".

**Status:** Accepted

**Date:** 2026-09-07

**Relates to:** ADR 0171 (constraint-propagating search, whose scout passes
`organism or ""` when no organism was named), ADR 0024 (the cross-species
flagged tier), ADR 0010 / STRENDA (assay conditions and what `verified`
means), ADR 0008 (parameter provenance), ADR 0013 (Vmax = kcat x [E]0),
ADR 0028 (a check that fires too broadly stops being read).

## Context

The scout chain in ADR 0171 resolves a constant with the organism the
request named, and an unnamed-organism request falls through to
`resolve_kinetic_value(e, ..., organism="", ...)`. The exact-tier BRENDA
parser treated that empty string as a real organism filter:

    if target_organism is not None:
        if target_organism not in full_text:
            continue
        row_organism = target_organism

An empty string is a substring of *every* row, so the first check matched
everything — and then `row_organism = target_organism` overwrote every
row's real organism label with `""`. The minimum value on the page came
back wearing a `brenda_exact` badge, `organism=""`, and no flag at all.

The result was a cross-species minimum reported as an exact value with no
subject. A reader cannot tell whether it was measured on the enzyme at all,
and the provenance line says nothing about the animal it came from. The
loss looked as though it had happened "between parse and result" — the
report simply lacked an organism — but the parser had thrown it away
before the resolver saw the rows. This is the organism twin of the already
documented empty-substrate pitfall in the same family
(`require_substrate_match = bool(substrate)`): the boolean check reads the
string's truthiness, not the search it actually performs, so `""` silently
means "match everything" instead of "match nothing".

`model_compatibility` could not notice. It can only judge a source that
*has* an organism; when the resolver hands it `organism=""`, the best it
can do is mark the set `unassessable` — a complaint about which organism a
value describes, issued about a value that describes none. The value was
genuinely unassessable, and the report said so only because the parser had
made it so.

Two candidate fixes:

**(a) Refuse an unnamed-organism exact-tier search** and list the organisms
the page actually offers, so nobody reads a cross-species minimum as exact.
Rejected. The branch machinery this subsystem is built on would starve:
`_observed_organisms` skips falsy organisms, so every quantity would land
in `missing` and the resolver would report "not found" for a value that is
sitting on the page. It would regress ADR 0171's own committed real-chain
tests — the kcat pH-gap re-selection and the named-organism runs — and it
would turn the commonest query a student types into a refusal. Refusing is
the right move when a *named* organism has no data (the existing broad tier
already does that); it is the wrong move when no organism was named at all.

**(b) Treat a falsy `target_organism` as "any organism"**, exactly like
`None`, and let each row keep the organism its cell actually says.

## Decision

Option (b). The parser gate becomes `if target_organism:`, so a falsy
target — `""` or `None` — both mean "scan the whole table and take the
rows as they are", and the per-row organism label is either the requested
one (when a real one was named) or the one extracted from the row itself.
Nothing is overwritten in the any-organisms case.

The resolved values do not move: `km org=""` is still 10.73 mM, only now
it names **Homo sapiens** (pH 8); the Ki is still 0.0116, only now it
names **Cryptosporidium parvum** (pH 5.5); the kcat minimum 21.1 at pH 6.0
is still there but the frontier's 32.0 at pH 8.0 / 25 still re-selects it
under ADR 0172. The fix is about attribution, not about picking a
different number from a different row.

The `brenda_exact` taxonomy stays honest, because it is now again true for
an unnamed-organism call: the value IS exact, from a specific row, by a
specific publisher, and it carries that row's organism. The
`cross_species_flag` stays `False`: the flag exists to say "a requested
organism was replaced by another organism's value", and here no organism
was requested — the page was searched, and the answer names what it found.

Two pinned tests had to change, and why:

- `test_an_unnamed_organism_yields_values_attributed_to_nothing` could not
  fail: it asserted the defect (`organism == ""` on the returned Ki). It is
  renamed and rewritten as `test_unnamed_organism_values_carry_their_own_organism`,
  which asserts the two values come back with `{"Homo sapiens",
  "Cryptosporidium parvum"}`, that `organism_unattributed` no longer
  appears, that `organism_mismatch` blocks on `{Km, Ki}` (two animals were
  really measured), and that the architecture responds as designed:
  `len(search.branches) == 3` — one unconstrained pass plus one run inside
  each organism the literature actually offered.
- `test_naming_the_organism_changes_which_value_is_returned` asserted the
  unconstrained Ki came back `organism == ""`. It now asserts
  `"Cryptosporidium parvum"`. The value (0.0116) is unchanged; the
  organism is now the one the row actually carries.

The `organism_unattributed` finding stays in the judge
(`tests/test_model_compatibility.py` remains green): it remains the
defense-in-depth verdict for a source that genuinely reports no organism
and cannot be assessed. The resolver simply no longer feeds it. `adapters.py`
now states this case in the `brenda_exact` line itself.

## Mutation verification

Both opposite mutations are caught by the sensor test
`test_unnamed_organism_values_carry_their_own_organism`:

- **Revert the gate** (`is not None` restored): the any-organism call
  becomes an exact-organism call matching every row and blanking every
  label again — FAIL, as it must, because the bug's behavior is exactly
  what the rewritten test asserts against.
- **Delete the per-row extraction** (rows keep no organism in the
  any-organism branch): every row loses its label again, and the set's
  organisms collapse to nothing — FAIL.

Both restores were diff-checked against the committed fix.

## Consequences

- The commonest query — an enzyme named, no organism — now returns a value
  with a named subject, and the cross-constant coherence judge can do its
  real job: when Km and Ki genuinely come from two animals, that is a
  blocking `organism_mismatch` instead of a silent agreement between two
  values that "agreed" by having no organism at all.
- The empty-string-as-filter trap is now documented at both occurrences
  (substrate and organism), so the pattern is recognisable when the third
  twin appears.
- What this does NOT do: it does not make the cross-species flag lie, it
  does not interpolate, average, or correct anything, and it does not
  decide between two organisms when one was genuinely requested. Those
  paths keep their refusals.