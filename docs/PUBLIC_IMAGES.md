# Images on public pages

**Every guard in this repository reads text. None of them can read a
picture.**

`check_public_claims.py` scans the landing pages for claims that contradict
the code, and its file filter ends:

```python
and not rel.endswith((".png", ".svg", ".ico"))
```

That line is mine. It is correct — a PNG is not source — and it means a
number baked into a screenshot is the most unchecked claim this project can
publish. `check_documented_counts.py`, `check_public_claims.py`,
`check_investor_claims.py` and `check_no_fabricated_endorsements.py` would
all pass a page whose hero image said "10,000 universities trust Caterva".

This file is the compensating control. It is not clever: a human looks at
each image and writes down what it depicts, and a hash makes it fail when
the picture changes.

## How it works

`scripts/check_public_images_reviewed.py` fails when a public-surface image
has no entry here, or when its content hash no longer matches. **Editing an
image to add a claim therefore fails**, which is the case that matters — a
new file is obvious, a changed one is not.

Three states, not two, and the difference is recorded per row:

| state | meaning |
|---|---|
| `reviewed` | somebody opened the image and read it |
| `hashed` | recorded and change-detected, **but nobody has looked** |
| `absent` | in the tree, not in this file — fails the build |

`hashed` exists so this file cannot quietly claim more than was done.
**All fourteen are now `reviewed`** — every image below has been opened
and read. The state stays in the schema because the next image added
starts unreviewed, and without somewhere to say so it would read as
audited from the moment it landed.

This paragraph has been wrong three times: it said ten when the answer
was eleven, then eleven when four had been reviewed, then seven when
the rest were done. Each time the guard's own output caught it. A
document about unchecked numbers is exactly where a stale number
hides best.

## The register

<!-- PUBLIC-IMAGES-START
e8605d3ff345900f  reviewed  Science-Agent-Pipeline/artifacts/caterva-landing/public/favicon.svg
790805bf4a0ac4cb  reviewed  mule/_shots/01-hero.png
6737793581a7406d  reviewed  mule/_shots/02-atlas-system.png
2925ce1e7d0348b4  reviewed  mule/_shots/02b-atlas-natural.png
4704ab03f0a8cc80  reviewed  mule/_shots/03-atlas-inspector.png
7386e6ef06f9d02d  reviewed  mule/_shots/04-atlas-failure.png
a039badcb77086c6  reviewed  mule/_shots/05-console-running.png
9d59ba1e5c9ccb93  reviewed  mule/_shots/06-console-complete.png
ecc1ad2db83e7d84  reviewed  mule/_shots/07-microscope-l1.png
213ef47ffee96dd1  reviewed  mule/_shots/08-microscope-l5.png
25f420cb85ce4c5e  reviewed  mule/_shots/09-microscope-record.png
9619c95dd0e18a0b  reviewed  mule/_shots/10-manifest.png
d42dfd5902b61a88  reviewed  mule/_shots/11-dock-open.png
b5f414e5928e0b8f  reviewed  mule/_shots/12-mode-failure-atlas.png
PUBLIC-IMAGES-END -->

## What the reviewed ones actually show

**`01-hero.png`** — the Caterva landing hero, Caterva's own UI. Carries, in
the image itself: *"ILLUSTRATIVE DEMO / NOT AN EXPERIMENTAL RESULT."*

**`10-manifest.png`** — five principles ("Caterva does not silently choose a
constant"), no numbers, no results.

**`06-console-complete.png`** — the one that could have gone wrong, and did
not. It shows a completed run with a Km value, a claim trace and a
verification panel, and every element is marked as a demonstration:

- header: *"ILLUSTRATIVE INTERFACE DEMONSTRATION. NOT A SCIENTIFIC RESULT."*
- execution mode: *"Illustrative"*
- Km value → *"DEMO-02 / parameter basis"*, not a citation
- model form → *"DEMO-01 / kinetics method record"*
- verification → *"Expected illustrative saturation behavior observed"*

That is a mockup built by somebody who refused to let fake data look real.
It is worth saying plainly, because the same repository shipped five
fabricated testimonials (ADR 0071) at the same time. The care was available;
it just was not applied everywhere.

**`05-console-running.png`** — a run in progress, and the first image with
real-looking numbers on it: Vmax 1.00, Km 0.42 mM, S range 0–5.0 mM. Every
one traces to `DEMO-01/02/03` in the evidence panel — *"Illustrative enzyme
conditions"*, *"Example substrate range"* — and temperature is flagged
`assumed` in amber rather than silently defaulted. A plausible Km attributed
to a demo source, not to a citation.

**`09-microscope-record.png`** — the most careful of the set. A parameter
record badged **ILLUSTRATIVE**, with `SOURCE BASIS: Demo source`,
`CRITIQUE RESULT: No unsupported claim shown, parameter remains explicitly
illustrative`, and a footer reading *"THIS IS AN INTERFACE DEMONSTRATION.
IT IS NOT A RESEARCH-READY PARAMETER."*

**`04-atlas-failure.png` and `12-mode-failure-atlas.png`** — the architecture
atlas, in failure mode. Both label the page *"ILLUSTRATIVE V1
ARCHITECTURE"*.

**`07-microscope-l1.png` and `08-microscope-l5.png`** — the same Km 0.42 mM
at two depths. L1 shows the bare number with `STATUS: Illustrative example`
and *"NO BASIS SHOWN AT THIS DEPTH"*; L5 shows it checked, with
`BASIS: DEMO-02`, *"Scope narrower than the run — disclosed, not resolved"*,
and `CRITIQUE RESULT: No unsupported claim shown, parameter remains
explicitly illustrative`. Both footer *"THIS IS AN INTERFACE
DEMONSTRATION."*

**`02-atlas-system.png`, `02b-atlas-natural.png`, `03-atlas-inspector.png`,
`11-dock-open.png`** — the atlas at rest, the atlas with an agent panel
open, and the mode dock. No results, no counts. `02b` reads *"SEVEN
REGIONS. EIGHT DECLARED ROUTES."* — a statement about the diagram, not
about the software.

**`favicon.svg`** — hand-written SVG: a cream rounded square and eleven
circles forming a C, the Caterva mark (replaced the teal "T" tile on
2026-09-27; re-reviewed then). No text, no embedded fonts, no traced
artwork, nothing licensed from anywhere.

### A wording tension worth noting

`02` and `03` are headed **"LIVE SYSTEM MAP / ILLUSTRATIVE ARCHITECTURE"**.
Those two halves pull against each other: "LIVE SYSTEM MAP" suggests a view
of the running system, "ILLUSTRATIVE ARCHITECTURE" says it is a drawing.
The second half is doing the honest work and the first half undercuts it.

Not a fabrication and not urgent — but if one half of a caption has to
survive a crop, it should be the one that constrains the claim.

### One thing worth knowing about the atlas images

They show five literature sources as nodes: **PubMed, Semantic Scholar,
OpenAlex, CrossRef, arXiv.** Checked against the code:

| source | in the codebase |
|---|---|
| PubMed | 53 files — real, queried live |
| CrossRef | comments only, about DOIs verified by hand |
| arXiv | one citation URL in a comment, one `arxivId?` type field |
| Semantic Scholar | **zero files** |
| OpenAlex | **zero files** |

**This is not being called a defect.** Every node is captioned
`CONCEPTUAL SOURCE` and the page is captioned `ILLUSTRATIVE V1
ARCHITECTURE` — that is a design diagram honestly labelled, not a
capability claim.

It is recorded because the framing is the only thing making it honest. Crop
those captions out, drop the image into a deck, and it becomes a claim that
Caterva queries five literature sources when it queries one of them. The
caption is load-bearing, and nothing mechanical can check that it stayed.

**No third-party content** in any of the three: no other product's UI, no
stock photography, no institutional logos. That was the licensing question
that prompted the look, and on these three the answer is clean.

## What is owed

Zero images are `hashed`. The last seven were described in the previous
pass as "near variants of shots already read, which is a reason to
expect them to be fine and not a reason to record that they are" —
so they were read rather than assumed. They were fine, and now that is
recorded instead of expected.

The count in this sentence is pinned by
`test_the_register_prose_matches_the_register`, which failed when this
paragraph still said eleven after four had been reviewed. A document
about unchecked numbers going stale is the one that should be hardest to
leave stale.

The check is also structurally weaker than the text guards: it detects
*change*, not *content*. A reviewer is what reads the picture. If the
project ever puts a metric in an image, the honest fix is to stop doing
that — text can be checked and a screenshot cannot.
