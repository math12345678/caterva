---
name: caterva
description: Enzyme kinetics and molecular dynamics, every number cited
colors:
  paper: "#FDF8EE"
  paper-raised: "#F6F0E3"
  ink: "#2A2D35"
  signal: "#5D7F8D"
  signal-deep: "#46626E"
  caution: "#946522"
  danger: "#A63D35"
  muted-ink: "#6A6E78"
  on-ink-signal: "#9DB8C4"
  on-ink-caution: "#D9AD6A"
  on-ink-danger: "#E08A80"
typography:
  display:
    fontFamily: "Spectral, Georgia, serif"
    fontWeight: 300
    lineHeight: 0.98
  wordmark:
    fontFamily: "Spectral, Georgia, serif"
    fontWeight: 400
    letterSpacing: "0.32em"
  body:
    fontFamily: "Atkinson Hyperlegible Next, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.6
  code:
    fontFamily: "DM Mono, Cascadia Code, monospace"
    fontSize: "13px"
    fontWeight: 400
rounded:
  slab: "8px"
components:
  terminal-window:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    rounded: "{rounded.slab}"
  section-header:
    textColor: "{colors.ink}"
    typography: "{typography.display}"
  badge-live:
    backgroundColor: "{colors.signal}"
    textColor: "{colors.paper}"
---

# Design System: caterva

## 1. Overview

**The mark sets the rule.** caterva's logo is a C of eight dots on paper:
seven ink, one signal. The page is built the same way. Paper is the
ground; ink carries the text and the few solid shapes; signal marks the
one thing in a view that matters (a verified value, a cited number, a live
capability), and it stays as rare as that one dot.

**Scene.** A principal investigator deciding whether to adopt this, on a
laptop in a daylit office between meetings, reading the page the way they
read a methods section. That forces a light, printed-paper ground rather
than a dark console, and a calm, unhurried pace.

**The one solid shape.** Terminal windows, the playground and every
command's output are *ink slabs*: solid `#2A2D35` blocks on paper, the way
the dots are. They keep the "built by people who write the code" signal
the audience respects, and they are the only heavy shapes on the page, so
the eye lands where the evidence is.

Explicitly not: glows, blurred colour blobs, gradient text, glass panels,
drifting particle backgrounds, word-by-word entrance animations, or
anything that would make a skeptical academic reviewer's first reaction be
"this is overselling something." All of these existed in the dark system
and were removed with it.

## 2. Colour

Tokens are CSS variables (`--fg`, `--surface`, `--signal`, `--caution`,
`--danger`, `--muted-ink`) exposed to Tailwind as `fg`, `surface`,
`signal`, `caution`, `danger`, `muted`. Inside `.ink-surface` they flip, so
the same class reads correctly on paper and on an ink slab:

| token | on paper | on ink | role |
|---|---|---|---|
| `fg` | ink `#2A2D35` | paper `#FDF8EE` | text, rules, solid shapes |
| `surface` | paper `#FDF8EE` | ink `#2A2D35` | the ground |
| `signal` | `#5D7F8D` | `#9DB8C4` | verified, cited, live, the primary action |
| `caution` | `#946522` | `#D9AD6A` | read twice: a default, a flag, money |
| `danger` | `#A63D35` | `#E08A80` | failure only |
| `muted` | `#6A6E78` | `#A9ACB3` | secondary marks, never meaning on its own |

**Contrast floor.** Text is never lighter than `text-fg/66` (about 4.5:1 on
paper). The scale in use is three tiers: 66 (tertiary), 70-76 (secondary),
80+ (primary); hierarchy beyond that comes from size and weight.

## 3. Typography

- **Spectral** Light for the display headline and section headers, Regular
  for the wordmark (lowercase, tracked 0.32 em). A restrained transitional
  serif, close to the drawing of the logo's wordmark.
- **Atkinson Hyperlegible Next** for body and UI text: designed for
  legibility, which suits readers who check every figure.
- **DM Mono** for every command, flag and output line.

## 4. Elevation

Flat. Depth comes from the ink slabs and from hairline rules
(`border-fg/[0.08-0.12]`), not shadows. No glows.

## 5. Components

- **Mark / Lockup** (`src/components/brand/Mark.tsx`): the measured dot
  geometry. Ink follows `currentColor`; the signal dot follows `--signal`.
  Use it in the header, the footer and anywhere the brand appears; never
  redraw the dots.
- **TerminalWindow**: an `.ink-surface` slab with a title bar of three dots,
  the last one signal, echoing the mark.
- **Section label + rule**: a small monospace number or label, a hairline,
  then a Spectral header in solid ink.
- **Status**: dot plus text label, colour carrying the semantic role above
  and never the meaning on its own.
- **Buttons**: tinted outline in the role's colour; a solid fill only where
  a single action must lead, with paper text on it.

## 5b. The run chapters (merged from the MuleRun page)

`src/mule/` holds the Evidence Cathedral, the system atlas, the
orchestration console, the evidence rail, the evidence microscope, the
separated trust layer and the runtimes, merged on 2026-09-28. They are
plain JavaScript modules and static markup, mounted once by
`MuleChapters.tsx`; their stylesheet (`mule.css`) is scoped under `.mule`
by `brand/scope_css.py`, so it cannot restyle the page around it. On paper
they read as one full-width ink chapter, in the brand's on-ink palette.

Their content follows the page's rule: the microscope, the evidence rail
and the Cathedral carry the real LDH Km (0.03 mM, BRENDA ref 286469) with
its 13.3-fold disagreement, and the "real output" panel quotes a recorded
`scripts/cite.py` run verbatim. What is illustrative (the agent
choreography) says so. `MergedChapters.test.ts` keeps archived domains and
the old 0.42 example out.

## 6. Do's and Don'ts

**Do:**
- Keep signal rare. If more than about one element in eight is signal, one
  of them is not the thing that matters.
- Put evidence in ink slabs; keep everything else light.
- Derive every number from its source (test counts from `testResults.ts`,
  capabilities from `lib/domains.ts`), never retype it.
- Pair every colour-coded status with a text label.

**Don't:**
- Add glows, blurs, gradients, particle fields or entrance choreography.
- Put body text below the contrast floor to make it "subtle".
- Introduce a colour without a role from Section 2.
- Claim anything the codebase cannot back with a real number, citation
  or test.
