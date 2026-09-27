# Caterva's legal position

**Not legal advice.** This records what the licence files in this tree
actually say, checked mechanically so it cannot drift. Anything that
matters commercially should go past a lawyer.

Last verified 2026-08-15 by `scripts/check_dependency_licenses.py`, which
runs in CI and fails when a dependency has no recorded grant of permission.

## The short version

Caterva's own code is Apache 2.0. Every software dependency it uses grants
permission to use it, in writing, including commercially. Four packages
that granted nothing have been removed from the code.

**Two data sources are unresolved: KEGG and CORE.** Both are queried live,
neither is a free-for-any-use database, and both say so in their own terms.
Each needs a licence enquiry or removal. See "Data, not code" below.

## "I don't want to use things I don't have permission for"

That is the requirement this document answers, and the answer is that a
licence **is** permission. MIT, BSD, ISC, Apache 2.0 and LGPL are not
warnings to stay away; they are grants, written by the authors, saying what
you may do. Using software under them is the intended use, not a risk being
tolerated.

The risk is the opposite case: software with **no** licence. Silence is not
permission. Nobody has said you may use it, so by default you may not.

That distinction drove every decision below.

## The simulation engine, and why it stays

Caterva runs on **libRoadRunner** (Apache 2.0, © 2012–2018 University of
Washington) and generates **Antimony** (MIT). Both come from the Sauro lab
at UW — the same group behind Tellurium.

There was a question of whether to remove them. The answer is no, and not
because it would be inconvenient. libRoadRunner's own licence file spells
the permission out in plain English:

> You CAN freely download and use this software, in whole or in part, for
> personal, company internal, or commercial purposes;
>
> You CAN use the software in packages or distributions that you create.

Removing software whose authors have explicitly invited you to use it would
not make Caterva safer. It would cost the ODE integrator underneath all 15
domains, invalidate the closed-form and independent-integrator correctness
tests that ADR-level rigour depends on, and buy nothing legally.

What the licence *does* require is attribution, which is now in `NOTICE`.

### What was actually checked

- **No copied source.** No file in the repository carries a University of
  Washington, Caltech, Sauro or Analog Machine copyright header.
- **No vendored tree.** No `vendor/`, `third_party/`, `external/`.
- **Import only.** All 218 references across 25 files go through the public
  Python APIs of separately-installed packages.
- **No `tellurium` dependency.** Prohibited by Constitution Rule 7,
  enforced by `check_forbidden_packages.py`, verified absent from all three
  dependency manifests.

Two vestigial references were removed: a dead `TELLURIUM_DIR` constant in
`verify_build.py` pointing at a directory that has never existed, and a
comment in `metrics-collector.ts` describing the engine as
"Tellurium/libRoadRunner", which was simply false and is the kind of
sentence that creates an impression of affiliation on its own.

## What was removed, and why

Four `@replit/*` packages. Each ships **no `license` field, no LICENSE
file, and no repository URL** — no grant of permission of any kind.

| package | status |
|---|---|
| `@replit/connectors-sdk` | Declared in `Science-Agent-Pipeline/package.json`, imported by no source file. Never used. |
| `@replit/vite-plugin-runtime-error-modal` | Ran on **every** build of `mockup-sandbox` and `caterva-landing`, including production — it was not gated. Call sites removed. |
| `@replit/vite-plugin-cartographer` | Gated on `REPL_ID`. Call sites removed. |
| `@replit/vite-plugin-dev-banner` | Gated on `REPL_ID`. Call sites removed. |

No unlicensed code now executes. What remains is four manifest entries,
which need a lockfile regeneration that cannot be done by editing
`package.json` alone without breaking `pnpm install --frozen-lockfile`:

```bash
cd Science-Agent-Pipeline
pnpm remove @replit/connectors-sdk \
            @replit/vite-plugin-runtime-error-modal \
            @replit/vite-plugin-cartographer \
            @replit/vite-plugin-dev-banner
```

Until that is run, `check_dependency_licenses.py` fails and names them.
**This is one of two outstanding action items; the other is KEGG, below.**

These are almost certainly meant to be freely usable — they are Replit's
own editor tooling, published to npm for public consumption. The problem is
that "almost certainly" is not a licence, and this project does not accept
"almost certainly" anywhere else.

## Dependencies with a condition worth knowing

**libSBML — LGPL 2.1.** The condition is that a recipient can replace the
library. From the wheel and sdist, Caterva installs it as an ordinary Python
package, does not vendor it, does not modify it and does not statically
link it, so replacement is a `pip install` away and nothing is conveyed. The
downloadable app folder (since v0.3.0, ADR 0177) is different: it contains
libSBML, so it conveys it. The folder is a one-directory freeze in which
libSBML's extension stays a single separate file a recipient can swap, and
it carries libSBML's own terms and the LGPL text beside it; NOTICE states
the position artifact by artifact and `scripts/build_app.py` refuses to
write a folder that does not match it. No source-disclosure obligation
attaches to Caterva's own code in either case.

**stdpopsim — GPL 3.0.** Optional and never redistributed. Imported at
runtime only if the user installed it themselves; the population-genetics
tests skip when absent. Since no stdpopsim code ships with Caterva, no GPL
obligation attaches to Caterva's distribution. **This changes if it ever
becomes a hard requirement or is bundled** — revisit then.

**Hypothesis — MPL 2.0.** File-level copyleft, triggered by modifying the
covered files. Caterva does not modify them.

**caniuse-lite — CC BY 4.0.** Build-time browser-support data in the JS
tree. Attribution satisfied by `NOTICE`.

## Data, not code

`NOTICE` covers this in full. In summary:

**BRENDA — CC BY 4.0.** Attribution and indication of modifications
required, both present. This repository was in breach on two counts until
2026-08-13, and `NOTICE` records the breach and the cure rather than
quietly fixing it — a project claiming every number is traceable should not
have an untraceable moment in its own compliance history.

**NCBI Taxonomy and PubMed.** US Government works, public domain in the
US. Citation requested, not required.

**KEGG — GATED 2026-08-16 (ADR 0096); licence still unobtained.**
The live call is now off unless `CATERVA_ENABLE_KEGG` is set, so Caterva no
longer queries KEGG on a user's behalf by default. The licence question
below is unchanged and unanswered — gating removes the exposure, it does not
resolve the entitlement. Anyone setting that variable is asserting their own
position. The remaining action is unchanged: contact Pathway Solutions.

The original assessment, which is what someone should read before enabling
it:


`resolve_substrate_from_kegg()` calls `https://rest.kegg.jp/get/ec:<ec>`
live, server-side, on the resolution path. KEGG's terms
(https://www.kegg.jp/kegg/legal.html, 1 October 2024) state that KEGG is
"not a public database", that non-academic use "requires a commercial
license", and that even academic users "providing services" are asked to
obtain an academic service-provider licence.

Caterva provides a service and this repository contains an incorporation
checklist, a cap table and a fundraising tracker. Either reading points at
a licence from Pathway Solutions (https://www.pathway.jp/).

Note the inconsistency in the project's own position: SABIO-RK was
evaluated and declined for having non-commercial-only terms. KEGG's terms
are comparable and KEGG was integrated anyway — not after weighing them,
but without reading them.

**CORE — the second unresolved item, and the clearer of the two.**
`Tests/core_fulltext.py` calls `https://api.core.ac.uk/v3/search/works`.
CORE's terms (https://core.ac.uk/terms) grant commercial use of their
**ODC-By datasets** but explicitly exclude **the API**: "you need to obtain
a licence to use other CORE datasets as well as the CORE API."

They then list three conditions under which you should contact them, and
Caterva meets all three: it might be monetised, it uses CORE data in a
service, and that service is literature search and discovery — CORE's own
listed example of "functionality provided by one of CORE's existing
services."

This is the clearer case because CORE state the requirement directly rather
than by implication. It is also the easier one: CORE say many users qualify
for a **free** licence and ask to be contacted either way. The action is an
email, most likely followed by a form.

**The deck presents it as an asset.** `caterva_pitch_deck.pptx`, slide 11,
under the heading "Product proof is done", lists as a completed item:

> ✓ Live GitHub repo — **BRENDA/KEGG scraper** + simulation engine, CI
> running, 1,852 tests passing

Two things are wrong with that line, and neither is the number.

First, it offers to investors as a built asset an integration whose licence
position is unresolved. On KEGG's stated terms this is either the academic
service-provider case or the commercial one, and both require a licence
from Pathway Solutions. An asset that may be a liability is exactly what
diligence is for, and it is much cheaper to resolve now than to be asked
about later.

Second, "scraper". Lisa Jeske of the BRENDA team, replying to this
project's own outreach, advised using the bulk CSV downloads rather than
scraping. Describing the integration that way to investors advertises a
mode of access the data provider discouraged.

**This paragraph is deliberately not a change to the deck.** The number on
that slide was a plain factual error and has been corrected; the KEGG line
is not a wording problem. Editing it out would hide a live risk from the
audience most entitled to know about it. Resolve the licence, then say so.

**What to do, in order:**

1. Decide whether Caterva is academic or commercial. It is currently both
   on paper.
2. Contact Pathway Solutions about the appropriate licence, or
3. Remove the dependency. The cost is bounded and small: KEGG supplies a
   substrate *name* when the caller did not give one, and the code already
   degrades to an unfiltered BRENDA fallback when the lookup fails
   (`resolve_substrate_from_kegg` returns `None` on any error and never
   guesses). Deleting it makes that fallback the only path rather than the
   error path — a quality regression on free-text enzyme queries, not a
   correctness one.

Until one of those happens this is a live exposure, and it is recorded here
rather than in a TODO so that it is findable by someone asking the question
you asked.

**SABIO-RK.** Evaluated and deliberately **not** integrated: its terms are
non-commercial only, materially different from BRENDA's CC BY. If it is
ever added it must be opt-in and must not be committed as fixtures.

## Not licensing, but next door: data protection

The site loads web fonts from Google's CDN on every page, which transmits
visitor IP addresses to a third party, and the cookie banner said "no
tracking" while it did so. The fonts themselves are OFL/Apache and
self-hosting is permitted — this is a data-protection question, not a
licensing one. It has its own document: `docs/DATA_PROTECTION.md`, which
also covers the waitlist's email collection and the absent privacy notice.

## The name

The trademark question — Caterva against Tellurium, in the same field, on
the same ecosystem — is **not resolved by anything in this document**, and
it is the largest remaining exposure. It has already produced one concrete
incident: a researcher read a cold outreach email as a false claim of
credit.

See `docs/RENAME_PLAN.md`. That is a decision for a person, and if the
project is going to be commercial it is a decision for a trademark
attorney.

## How this stays true

`scripts/check_dependency_licenses.py` holds a table of every direct
dependency and the grant it rests on, read from the licence text shipped in
the installed distribution rather than from a package-index summary. A
dependency with no entry **fails** — the default is "go and look it up",
not "assume it's fine", because a dependency added without checking its
terms is precisely what this is for.

It distinguishes three states rather than two: permission on record,
installed but declaring nothing, and not installed here so unverifiable.
Collapsing the last two would have accused `autoprefixer` — plainly MIT —
of the same defect as the `@replit` packages, which genuinely declare
nothing. Reporting a gap in evidence as a finding is how a guard loses the
credibility it needs to be believed when it is right.
