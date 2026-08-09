"""Guard that every modelCitations entry in the query resolver is lookuppable.

Stage 4 Part 4 found that 3 of 7 literature references in the resolver's
DOMAIN_DEFAULTS were wrong (fabricated or truncated titles). None of the
provenance tests could catch it: they verify the shape of the provenance
record, and a fabricated title is a perfectly well-shaped string.

This guard is the recommendation carried to Part 5 (see
Business/build-stages/STAGE_04_PART_04.md section 5): an executable check
in the same spirit as check_rng_convention.py. It cannot verify that a
paper exists, but it can require that every static modelCitations entry
carries the fields whose absence makes it unverifiable.

Scope: queryResolver.ts is the only file in the codebase holding static
modelCitations entries. llmResolver.ts's occurrence is inside the LLM
system-prompt template, and LLM-provided citations are runtime data that
cannot be statically checked.

Rules for each entry:
1. Non-empty.
2. If it contains a URL, accept it: a URL is inherently lookuppable
   (database citations such as BRENDA legitimately carry no author or
   year).
3. Otherwise require all three:
   a. a year in parentheses, e.g. (1930);
   b. at least two capitalized author-name tokens before the year;
   c. either a volume/page range (e.g. 115(772), 700-721 or 51, 263-273)
      or a publisher (book citations, e.g. Clarendon Press).

A bare title like "Physical clusters of simple liquids." fails: no year,
no volume, no pages, no publisher — the exact unverifiable shape Part 4
found in production. The guard converts "someone should look these up"
into "an unlookuppable citation cannot merge".

The stricter question of whether a *resolved* (per-parameter) citation must
satisfy a stricter format than a modelCitations entry is deliberately not
decided here; Stage 5's provenance contract owns that decision (ADR 0008).

Run directly: python3 scripts/check_citation_format.py [path]
"""

from __future__ import annotations

import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
RESOLVER_FILE = (
    REPO_ROOT
    / "Science-Agent-Pipeline"
    / "artifacts"
    / "api-server"
    / "src"
    / "lib"
    / "queryResolver.ts"
)

# A journal/volume citation looks like "Advances in Physics 20(84), 161-196"
# or "Cold Spring Harbor Symposia 51, 263-273".
VOLUME_PAGES_RE = re.compile(
    r"\b\d+\s*\(\d+\)\s*,\s*\d+\s*[-–]\s*\d+"
    r"|\b\d+\s*,\s*\d+\s*[-–]\s*\d+"
)
# A book citation names a publisher ("Oxford: Clarendon Press.").
PUBLISHER_RE = re.compile(r"\b(Press|University|Institute|Publications?)\b", re.IGNORECASE)
# Not every publisher's name contains one of those words (Williams & Wilkins,
# Wiley, Springer, Elsevier, W.H. Freeman, ...). The standard bibliographic
# "Place: Publisher." form is a general enough signal on its own: a
# capitalized place name, a colon, then a capitalized publisher name ending
# the sentence. Found missing when "Baltimore: Williams & Wilkins." (Lotka
# 1925, a real citation, not fabricated) failed this guard for lacking
# "Press/University/Institute/Publications" -- the guard's own rule 3c
# already calls this shape out as sufficient ("or a publisher"); the regex
# had just not been widened to recognize it in this form.
PLACE_PUBLISHER_RE = re.compile(r"\b[A-Z][A-Za-z.]+:\s+[A-Z][A-Za-z.,&'\s]+\.")
YEAR_RE = re.compile(r"\(((?:18|19|20)\d{2})\)")
NAME_TOKEN_RE = re.compile(r"[A-Z][A-Za-z.\-']*")
ARRAY_RE = re.compile(r'modelCitations:\s*\[(.*?)\]', re.DOTALL)
STRING_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')


def extract_entries(source: str) -> list[tuple[int, str]]:
    """Return (line, citation) pairs for every static modelCitations entry."""
    entries: list[tuple[int, str]] = []
    for match in ARRAY_RE.finditer(source):
        for string_match in STRING_RE.finditer(match.group(1)):
            line = 1 + source[: match.start(1) + string_match.start(1)].count("\n")
            entries.append((line, string_match.group(1)))
    return entries


def check_entry(line: int, citation: str) -> list[str]:
    problems: list[str] = []

    if not citation.strip():
        return [f"line {line}: empty modelCitations entry"]

    # A URL is a complete, lookuppable identifier on its own.
    if re.search(r"https?://", citation):
        return problems

    pre_year = citation.split("(", maxsplit=1)[0] if citation.find("(") != -1 else citation
    if not YEAR_RE.search(citation):
        problems.append(
            f"line {line}: missing a year in parentheses, e.g. (1930): {citation}")
    elif len(NAME_TOKEN_RE.findall(pre_year)) < 2:
        problems.append(
            f"line {line}: fewer than two author-name tokens before the year: {citation}")

    if not (VOLUME_PAGES_RE.search(citation) or PUBLISHER_RE.search(citation)
            or PLACE_PUBLISHER_RE.search(citation)):
        problems.append(
            f"line {line}: no volume/page range and no publisher; "
            f"an entry with a bare title cannot be looked up: {citation}")

    return problems


def check(path: pathlib.Path = RESOLVER_FILE) -> list[str]:
    if not path.exists():
        return [f"resolver file not found: {path}"]

    source = path.read_text(encoding="utf-8")
    violations: list[str] = []
    for line, citation in extract_entries(source):
        violations.extend(check_entry(line, citation))
    return violations


def main() -> int:
    path = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else RESOLVER_FILE
    violations = check(path)
    if not violations:
        print("OK: all modelCitations entries carry authors, a year, and "
              "volume/pages, a publisher, or a URL.")
        return 0

    print("Citation-format violations found:\n")
    for v in violations:
        print(f"  {v}")
    print("\nEvery modelCitations entry must be lookuppable: authors, a year "
          "in parentheses, and either a volume/page range or a URL. "
          "\nSee Business/build-stages/STAGE_04_PART_04.md section 5.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
