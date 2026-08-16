# `mule/` — the MuleRun landing page

A static landing page for Terrium's MuleRun listing. Ships as its own
repository, `mule`.

| path | what it holds |
|---|---|
| `index.html` | the page — self-contained, no build step |
| `assets/` | images and styles it references |
| `_shots/` | screenshots used on the page |

## Running it

Open `index.html` in a browser, or serve the directory:

```bash
python -m http.server --directory mule 8080
```

There is no bundler, no package manager and no toolchain. That is
deliberate for a one-page static site, and it means the only way to break it
is to reference a file that is not there.

## The one rule that applies here

`scripts/check_static_assets.py` fails the build when this page references an
asset that does not exist. A landing page with a broken image is a claim
about the product that the product does not meet.

The same standard as everywhere else in this repository applies to any
number printed on this page: **if it is a metric, it must be true and it must
have a source.** A marketing page is the easiest place in a project to state
a figure nobody checked — the dashboard shipped seven of them
([ADR 0042](../docs/adr/)), including an "Avg Impact Factor 19.79" that was
typed by hand and specific to two decimal places.
