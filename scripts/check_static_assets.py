"""Guard that every asset a static page references actually exists.

A stylesheet or script that 404s is the commonest way a static site rots,
and it is invisible until someone opens the page: the browser renders the
unstyled fallback without complaining, and a screenshot in a PR looks
plausible if you have not seen the intended design.

WHAT IT SKIPS, AND WHY THAT MATTERS

The first version of this check was three lines of shell:

    for f in $(grep -ohE '(href|src)="[^"]*"' index.html | sed ...); do
      [ -e "$f" ] || echo "missing: $f"
    done

It reported 33 missing assets on a page whose assets were all present.
Every one was a false positive:

  * `data:image/svg+xml,...` inline favicons — split on the spaces inside
    the SVG, so `viewBox='0`, `32'`, `fill='none'` each became a "file".
  * `#pipeline-summary`, `#atlas` — in-page anchors, not files.

A checker that cries wolf gets deleted, and then the real 404 ships. So the
rule is narrow on purpose: only same-document relative paths are checked,
and everything else is reported as skipped rather than silently dropped, so
the counts can be reconciled by hand.

Usage:
    python scripts/check_static_assets.py mule/index.html [more.html ...]
"""

from __future__ import annotations

import pathlib
import re
import sys
from urllib.parse import unquote, urlparse

#: `href="..."` / `src="..."` with either quote style. Deliberately does not
#: try to parse HTML: the failure mode of a regex here is a missed asset,
#: which the count line makes visible, rather than a wrong verdict.
REF_RE = re.compile(r"""\b(?:href|src)\s*=\s*(["'])(.*?)\1""", re.IGNORECASE | re.DOTALL)

#: Not files on disk. Each is a real thing a page does, not an oversight.
SKIP_SCHEMES = ("data:", "http:", "https:", "mailto:", "tel:", "javascript:", "//")

#: `import x from './y.js'`, `export * from '../z.js'`, `import('./w.js')`.
#:
#: Following these matters more than it looks. `index.html` references ONE
#: script -- `assets/js/main.js` -- which imports the other 27 modules. A
#: checker that read only the HTML would report "13 assets, all present" on a
#: page where 27 of 28 JavaScript files could be deleted without complaint.
#: The reassuring number would have been the problem.
IMPORT_RE = re.compile(
    r"""(?:^|\s)(?:import|export)\s[^;'"]*?from\s*(["'])(.*?)\1"""
    r"""|(?:^|\s)import\s*\(\s*(["'])(.*?)\3\s*\)""",
    re.MULTILINE,
)


def references(html: pathlib.Path) -> tuple[list[str], list[str]]:
    """(local paths to check, references deliberately skipped)."""
    text = html.read_text(encoding="utf-8", errors="replace")
    local: list[str] = []
    skipped: list[str] = []

    for _quote, raw in REF_RE.findall(text):
        ref = raw.strip()
        if not ref or ref.startswith("#"):
            skipped.append(ref or "(empty)")
            continue
        if ref.lower().startswith(SKIP_SCHEMES):
            skipped.append(ref[:40] + ("…" if len(ref) > 40 else ""))
            continue
        # Strip the query/fragment: `style.css?v=2` is still style.css.
        path = unquote(urlparse(ref).path)
        if path:
            local.append(path)
        else:
            skipped.append(ref)

    return local, skipped


def check(pages: list[pathlib.Path]) -> list[str]:
    violations: list[str] = []
    checked = 0

    for page in pages:
        if not page.is_file():
            violations.append(f"{page} does not exist")
            continue

        local, skipped = references(page)
        if not local:
            violations.append(
                f"{page}: no local asset references found at all. Either the "
                "page stopped linking its own stylesheets or REF_RE stopped "
                "matching; both are worth knowing, and neither is a pass."
            )
            continue

        base = page.parent
        js_entrypoints: list[pathlib.Path] = []

        for ref in local:
            checked += 1
            target = (base / ref).resolve()
            if not target.exists():
                violations.append(f"{page}:  {ref}  ->  no such file")
            elif target.suffix == ".js":
                js_entrypoints.append(target)

        # Walk the ES module graph from every script the page loads.
        seen: set[pathlib.Path] = set()
        queue = list(js_entrypoints)
        while queue:
            module = queue.pop()
            if module in seen:
                continue
            seen.add(module)
            try:
                source = module.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for m in IMPORT_RE.finditer(source):
                spec = m.group(2) or m.group(4) or ""
                if not spec.startswith("."):
                    continue  # bare specifier: a CDN or import map, not a file
                checked += 1
                target = (module.parent / spec).resolve()
                if target.exists():
                    queue.append(target)
                else:
                    rel = module.relative_to(base) if base in module.parents else module
                    violations.append(f"{rel}:  {spec}  ->  no such module")

        print(
            f"  {page}: {len(local)} local asset(s) + {max(len(seen) - len(js_entrypoints), 0)} "
            f"imported module(s) checked, {len(skipped)} skipped "
            "(data:/http:/anchors)"
        )

    if not violations:
        print(f"OK: all {checked} referenced asset(s) exist.")
    return violations


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__.strip().splitlines()[-2].strip())
        return 2

    pages = [pathlib.Path(a) for a in argv[1:]]
    violations = check(pages)
    if not violations:
        return 0

    print(f"\nMissing assets ({len(violations)}):\n")
    for violation in violations:
        print(f"  {violation}")
    print(
        "\nA 404 on a stylesheet renders as an unstyled page, which looks "
        "like a design decision rather than a broken link."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
