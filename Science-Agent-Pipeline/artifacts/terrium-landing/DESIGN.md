---
name: Terrium
description: A scientific-simulation tool that resolves plain-language questions into literature-cited, verifiable results
colors:
  primary-teal: "#1D8A72"
  primary-teal-deep: "#0D6B5A"
  info-blue: "#3B82F6"
  caution-amber: "#F59E0B"
  experimental-violet: "#8B5CF6"
  rare-accent-pink: "#EC4899"
  destructive-red: "#EF4444"
  bg-void: "#0A0E0C"
  bg-void-deep: "#050807"
  neutral-fg: "#E5E7E4"
typography:
  display:
    fontFamily: "Space Grotesk, system-ui, sans-serif"
    fontWeight: 500
    lineHeight: 1.1
  editorial:
    fontFamily: "Newsreader, Georgia, serif"
    fontWeight: 400
    lineHeight: 1.3
  body:
    fontFamily: "Space Grotesk, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
  code:
    fontFamily: "DM Mono, Cascadia Code, monospace"
    fontSize: "11px"
    fontWeight: 400
rounded:
  none: "0px"
components:
  terminal-window:
    backgroundColor: "{colors.bg-void}"
    rounded: "{rounded.none}"
    padding: "16px"
  section-label:
    textColor: "{colors.primary-teal}"
    typography: "{typography.code}"
  badge-live:
    backgroundColor: "{colors.primary-teal}"
    textColor: "{colors.bg-void}"
---

# Design System: Terrium

## 1. Overview

**Creative north star: The Lab Terminal.** Not a dashboard, not a SaaS
funnel — a real terminal window a scientist would actually open, showing
real commands, real output, real citations. Every section frames its
content as a `$ terrium <command>` invocation inside a `TerminalWindow`,
which is the system's one recurring structural device instead of the
generic "card grid."

The mood is a well-run lab bench at night: dark, quiet, precise, nothing
wasted. Sharp corners everywhere (`radius: 0`) reinforce "instrument," not
"app." Motion is subdued and functional (reveal-on-scroll, count-up
stats, gentle hover states), never decorative or attention-grabbing —
this audience distrusts flash.

Explicitly not: gradient-text logos, glassmorphic hero cards, countdown
urgency, "trusted by" logo walls, or anything that would make a skeptical
academic reviewer's first reaction be "this is overselling something."
The typography mixes a technical sans (Space Grotesk) and monospace (DM
Mono) for the terminal register with a literary serif (Newsreader) used
sparingly for a handful of longer-form, editorial moments — the serif is
the one place the design allows itself to feel unhurried and read like
a paper abstract rather than a product screen.

## 2. Colors: The Instrument Panel

The background is not black — `hsl(160 40% 3.5%)`, a near-black tinted
toward the primary teal hue, per the project's own CSS custom properties
(`src/index.css`). Every neutral in the system carries that same green
tint rather than sitting at true gray or true black.

- **Primary — Teal (`#1D8A72`)**: the identity color. Verified/live
  status, the `$` prompt, primary actions, "this is true and checked."
  Used at high frequency (the single most common accent color in the
  codebase) — it should read as *the* Terrium color, the way a lab's
  safety-green reads as "go."
- **Info — Blue (`#3B82F6`)**: system/architecture context — status,
  metrics, structural information. Cooler and more neutral than teal on
  purpose: this is "here is a fact," not "here is a result."
- **Caution — Amber (`#F59E0B`)**: money, warnings, flagged values,
  anything the user should read twice before trusting (an unverified
  default, a pricing tier, a plausibility-bound flag).
- **Experimental — Violet (`#8B5CF6`)**: people, community, roadmap,
  forward-looking or exploratory content — the one color reserved for
  "not yet settled science."
- **Destructive — Red (`#EF4444`)**: failure states only. Used sparingly
  and never decoratively.
- **Rare accent — Pink (`#EC4899`)**: a single specific domain marker
  (population genetics) in the Roadmap list. Not a general-purpose fifth
  color; don't reach for it casually.

Each landing-page section already carries one of these as a subtle
background tint (`.section-bg-teal/blue/amber/purple`) to differentiate
long-scroll sections without adding chrome. Keep new sections mapped to
the semantic role above, not chosen for visual variety alone.

## 3. Typography

Three families, each with a distinct job — this is a "full palette"
typographic strategy, not a single default:

- **Space Grotesk** (sans): the workhorse. All UI chrome, labels, body
  copy, headings. Geometric and slightly technical without being cold.
- **DM Mono** (monospace): the terminal register. Every `$ command`,
  every code block, every piece of output that should read as "real
  machine output," every numeric readout (`tabular-nums`).
- **Newsreader** (serif, optically sized `6..72`): used sparingly for
  the handful of places the page wants to read like a paper or an essay
  rather than a tool — long-form claims, not UI labels. If a new section
  is mostly prose making an argument, this is the family to reach for;
  if it's showing a result or a control, it isn't.

Scale contrast comes from size + weight, not a single flat 14px-everywhere
system — section headers, terminal body text, and micro-labels (10-11px
uppercase tracked-wide) are all visually distinct tiers.

## 4. Elevation

Flat by design, not layered. There is no shadow vocabulary to speak of —
depth comes from `border-white/[0.04-0.08]` hairlines and very low-opacity
white overlays (`bg-white/[0.01-0.03]`) instead of drop shadows. This is
correct for the "instrument panel" mood: a real terminal doesn't cast a
shadow on itself. The one exception is the `glow` prop on `TerminalWindow`,
a soft `box-shadow` in the teal primary used deliberately, and sparingly,
to mark the terminal that currently has the user's attention — not a
default treatment for every panel.

## 5. Components

- **TerminalWindow**: the system's one true "card." A dark
  (`bg-[#0A0E0C]`) panel with a faux title bar (three dots + a `path`
  breadcrumb) and sharp corners. Every section's primary content lives
  inside one of these rather than a generic rounded card — this is the
  component that IS the brand.
- **Section label + rule**: every section opens with a small monospace
  label in that section's accent color (`text-[11px] font-mono`) followed
  by a thin gradient rule fading to transparent. Cheap, consistent,
  reinforces "instrument readout" over "marketing header."
- **Status badges**: colored dot + short uppercase label, color carries
  the same semantic meaning as the palette above (teal = live/true, amber
  = caution, never color alone — always paired with a text label).
- **Buttons**: sharp corners, low-opacity tinted background
  (`bg-[color]/[0.06-0.14]`) with a matching low-opacity border, text in
  the full-strength accent color. No solid-fill primary buttons; even the
  "featured" pricing CTA stays in this tinted-outline register rather
  than becoming a filled button. Restraint here is intentional: a solid
  block of saturated color would break the instrument-panel mood.
- **Inputs**: dark, low-opacity background, hairline border, teal focus
  ring/shadow. No visible chrome beyond that.

## 6. Do's and Don'ts

**Do:**
- Frame new content as a real, plausible terminal invocation and output.
- Keep every color choice mapped to the semantic roles in Section 2.
- Use sharp corners (`radius: 0`) everywhere; this is load-bearing for
  the aesthetic, not an oversight to "fix."
- Pair every color-coded status with a text label.
- Reach for the serif only for prose that argues something, never for UI.

**Don't:**
- Introduce a new accent color without a semantic reason (see Section 2).
- Use a solid-filled, high-saturation button. Stay in the tinted-outline
  register established across every CTA on the page.
- Add drop shadows or glassmorphism as a default card treatment; flat +
  hairline borders is the system, `glow` is the rare exception.
- Add a hero-metric template (big number / small label / gradient
  accent) — the existing terminal-framed stat rows already do this job
  without the cliché.
- Claim anything the codebase can't currently back with a real number,
  a real citation, or a real test count. This is not a style rule so
  much as the whole point of the product; treat it as one anyway.
