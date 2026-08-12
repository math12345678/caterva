# mule

Part of [**Terrium**](https://github.com/Terrium-sim/main) — scientific
computing for teaching labs.

The MuleRun-designed product site. A static build: no framework, no
bundler, no install step.

```bash
python3 -m http.server 8000
open http://localhost:8000
```

## What it is

A long-form scrolling explanation of what Terrium does, built as eleven
independent CSS modules over a shared token layer, with the interactive
sections driven by small ES modules.

```
index.html
assets/
  css/
    tokens.css        colour, type scale, spacing — everything else builds on this
    base.css          reset and primitives
    hero.css          the opening
    cathedral.css     the architecture section
    inspector.css     the provenance inspector
    atlas.css         the domain atlas
    console.css       the run console
    microscope.css    the drill-down view
    chapters.css      section framing
    manifest.css      the run manifest
    pilot.css         the closing call to action
    modes.css         failure/success mode switching
  js/
    cathedral/        render, choreograph, inspector
    modes/            mode switching
_shots/               13 screenshots used as section imagery
```

## Editing it

`assets/css/tokens.css` first. Every other stylesheet reads from it, so a
colour or spacing change made there propagates; a change made in a section
file does not, and will drift out of step with the rest.

## What CI checks

That every `href` and `src` in `index.html` resolves to a file that exists.

A stylesheet or script that 404s is the most common way a static site rots,
and it is invisible until someone opens the page — the browser renders the
unstyled fallback without complaining. The check is cheap and catches the
whole class.

It does **not** check that the page looks right. Nothing automated here
does, and claiming otherwise would be worse than the gap.

## Relationship to the other front ends

Three sites, three audiences, deliberately not merged:

| repo | audience |
|---|---|
| `mule` | the product story — this one |
| [`terrium-site`](https://github.com/Terrium-sim/terrium-site) | the marketing site (React + Vite) |
| [`frontend-main`](https://github.com/Terrium-sim/frontend-main) | the in-app dashboard |

They share no code. Folding them together would produce one repository with
three unrelated toolchains and nothing gained.

---

This repository is a submodule of
[`Terrium-sim/main`](https://github.com/Terrium-sim/main). Clone the whole
system with:

```bash
git clone --recursive https://github.com/Terrium-sim/main.git
```
