# ADR 0096: KEGG is opt-in until somebody holds a licence

**Status:** Accepted, implemented

**Date:** 2026-08-16

**Relates to:** ADR 0068 (a source queried live is a source whose terms
apply — which identified this and did not act on it), ADR 0061 (stdpopsim
moved out of the default install for a comparable reason), `NOTICE`,
`docs/LICENSING.md`

## What was already known, and not acted on

ADR 0068 and `NOTICE` both record KEGG as **UNRESOLVED**. `NOTICE` states
the inconsistency in the project's own position plainly:

> SABIO-RK is recorded below as deliberately NOT integrated because its
> terms are non-commercial only. KEGG's terms are comparable, and KEGG was
> integrated anyway — not by a decision that weighed them, but because
> nobody read them.

KEGG's terms (https://www.kegg.jp/kegg/legal.html, 1 October 2024):

> KEGG is an original database product, copyright Kanehisa Laboratories.
>
> Academic users who utilize KEGG for providing services are requested to
> obtain an academic service provider license […]
>
> Non-academic users must understand that KEGG is not a public database,
> nor is it a publicly funded database. Non-academic use of KEGG requires a
> commercial license.

Terrium provides a service. This repository contains an incorporation
checklist, a cap table and a fundraising tracker. Either reading points at a
licence from Pathway Solutions. Nobody has obtained one.

**And the call was still being made.** `resolve_substrate_from_kegg()` hit
`rest.kegg.jp` live, server-side, on every resolution where the caller
supplied no substrate — which is every enzyme resolved from free text rather
than the bundled list. Documenting an exposure is not closing it, and three
documents describing a problem is not a decision.

## Decision

**The KEGG lookup is off unless `TERRIUM_ENABLE_KEGG` is set.**

Setting it is the operator stating that their own licence position permits
the call. Terrium makes no KEGG request on anyone's behalf by default.

This is the project's own precedent applied consistently rather than a new
policy:

| source | terms | what was done |
|---|---|---|
| SABIO-RK | non-commercial only | declined; never integrated |
| stdpopsim | GPL-3.0-or-later | moved to `requirements-popgen.txt`, opt-in (ADR 0061) |
| CORE | API excluded from the ODC-By grant | already refuses without `CORE_API_KEY` — and obtaining that key *is* engaging CORE's licensing process |
| **KEGG** | not a public database; service use needs a licence | **now opt-in, this ADR** |

CORE is worth noting: it turned out to be adequately gated already, by
accident of needing an API key. The gate exists for a different reason than
licensing and happens to serve both. That is luck, not design, and it is
recorded so nobody removes the key requirement thinking it is merely
configuration.

## What this does NOT claim

It does not assert that using KEGG would be unlawful. Terrium's founder may
well qualify as an academic user, and KEGG may well grant a licence for the
asking — their own page says many users are eligible.

It asserts something narrower and checkable: **Terrium does not currently
know that the call is licensed, and a tool whose central claim is
traceability should not make an unexamined request on a user's behalf.**
The switch converts an unexamined default into a stated choice by someone
who is in a position to know.

## Degrading, not crashing

`resolve_substrate_from_kegg()` catches `httpx.HTTPError` only — narrowly and
on purpose, because `test_programming_error_is_not_swallowed` exists to stop
that clause being widened into a bug-swallower.

A new exception type from the gate would therefore have propagated and
crashed the whole resolution, which that function's docstring says must
never happen. So `KeggLicenceNotConfigured` is caught **by name**, next to
the HTTP clause, and returns `None`.

`None` is already the designed answer for "KEGG gave us no substrate", and
the unfiltered BRENDA fallback handles it. The user sees a broader BRENDA
result set — measurably worse filtering, which is a real cost — not a
failure.

`KeggLicenceNotConfigured` is a distinct type rather than a bare
`RuntimeError` so a caller can tell *we chose not to ask* from *KEGG did not
answer*. That is the same distinction the resolver keeps everywhere else,
and collapsing it here would report a deliberate abstention as a network
fault.

## Consequences

- **The substrate filter is weaker by default.** `brenda_client.py` filters
  BRENDA rows by substrate name, and `enzyme_lookup.py`'s docstring explains
  why: without it, an enzyme page's Km data is dominated by every inhibitor
  and assay surrogate anyone ever tested. Free-text-resolved enzymes now
  reach that fallback more often. This is a real quality cost, accepted
  knowingly, and reversible in one environment variable by anyone entitled
  to make the call.
- `Tests/test_kegg_is_opt_in.py` asserts no HTTP request is attempted when
  the switch is unset — checked by counting calls to `retry_get`, not by
  catching the exception, because an exception raised *after* the request
  would satisfy a type check and still have contacted KEGG.
- It also asserts the refusal message names the switch and the terms. A
  refusal a reader cannot act on is the defect this project fixes elsewhere.
- Parsing is strict: `TERRIUM_ENABLE_KEGG=0` means off. An env var truthy
  merely by being present is how a switch gets flipped by a stray `export`
  in a CI file.
- Mutation-tested: removing the gate fails two of thirteen tests — the two
  that assert no call is made and that the message is actionable.

## Still open

A licence enquiry to Pathway Solutions (https://www.pathway.jp/) has not
been sent. That is a decision for whoever is willing to state Terrium's
academic-or-commercial status, which is not a question code can answer.
`docs/LICENSING.md` carries the action item.
