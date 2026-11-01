# Product

## Register

brand

## Users

Professors running teaching labs, research-lab PIs and their students, and
self-directed learners who want to run a real, literature-backed
simulation without setting up a computational-biology toolchain. They are
scientifically literate and skeptical of anything that oversells itself;
they will check a citation before they trust it. Context of use: evaluating
whether to adopt this for a course or a lab, often side-by-side with
established tools (Tellurium/COPASI/MATLAB), during limited attention on a
laptop, frequently pre-coffee or between meetings.

## Product Purpose

Caterva resolves a plain-language scientific question into a real,
literature-cited simulation: it finds the actual Km/Vmax/etc. from BRENDA,
KEGG, or PubMed rather than inventing a plausible number, then runs the
simulation and shows the full provenance trail. Success looks like a
professor trusting a number enough to put it in front of a class, and a
research lab trusting it enough to use in a real analysis. This repository
is pre-launch (private, waitlist-only) as of 2026-08-31; the design must
read as credible and substantial regardless of that fact, not compensate
for it with hype.

## Brand Personality

Rigorous, quiet, unhurried. Think "a well-run instrument, not a pitch
deck." Three words: precise, trustworthy, unflashy. The existing terminal/
CLI aesthetic (monospace prompts, `$` command lines, real command syntax)
is a deliberate, correct choice for this audience — it signals "built by
people who also write the code," which the target user respects. Emotion
to evoke: the calm of a well-instrumented lab bench, not the urgency of a
funnel.

## Anti-references

- Generic SaaS landing pages: hero-metric templates, gradient-text logos,
  "trusted by" logo walls of companies that were never customers.
- Crypto/AI-hype visual language: excessive glow, aggressive motion,
  countdown urgency, inflated claims of scale.
- Anything that would make a skeptical academic reviewer's first reaction
  be "this looks like it's overselling something." This project's own
  history includes shipping and then removing fabricated testimonials
  (ADR 0071) and a fabricated release history (fixed this session) —
  the design must never recreate that impression visually even where the
  copy is now accurate.

## Design Principles

1. **Show the mechanism, don't just claim it.** A citation, a real test
   count, a real DOI beats an adjective. Where the page makes a claim, the
   proof should be one click or one hover away, not a separate page.
2. **Terminal-native, not terminal-costume.** The CLI aesthetic should
   look like a tool the reader could actually run, using real flags and
   real output shapes, not decorative ASCII-art dressing.
3. **Quiet urgency, not manufactured urgency.** No countdown timers, no
   "only 3 spots left." The waitlist framing is honest (pre-launch, real),
   and the design should let that read as confidence, not scarcity theater.
4. **Density over decoration.** This audience reads fast and skims for
   substance; prefer one more real data point over one more animation.
5. **Every accent color should mean something.** The existing per-section
   tint system (teal/blue/amber/purple backgrounds) should map to a
   consistent semantic role across the page, not be decorative variety.

## Accessibility & Inclusion

WCAG AA as the floor: text contrast, focus-visible states on every
interactive element, keyboard reachability for the command palette and
all modals (several focus-trap and ARIA gaps were already found and
fixed this session in CommandPalette, backend-health, and WaitlistForm).
Respect `prefers-reduced-motion` given how much of this page relies on
scroll-triggered and hover motion. No information conveyed by color alone
(the domain "live" vs "planned" status, pass/fail indicators, etc. already
pair color with a text label — keep that pattern for any new indicator).
