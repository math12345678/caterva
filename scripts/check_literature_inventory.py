"""Guard: every scientific number in Terrium must declare its provenance.

The project's central claim is that nothing is hardcoded and everything is
backed by literature. That claim was, until this guard existed,
unfalsifiable — and therefore worth nothing. Three things were true at the
same time:

  * `RESOLVABLE_FIELDS` resolves exactly five parameters live (km, ki,
    kcat/vmax, mutation_rate, beta/gamma-from-R0). Real, cited, verified.
  * `DOMAIN_DEFAULTS` in queryResolver.ts contains 64 hardcoded numbers
    across 14 domains — km=2, vmax=5, beta=0.3, gamma=0.1 — none of which
    is checked against any source. (The first count taken by hand said
    "39 across 15"; both figures were wrong, because the hand-rolled regex
    that produced them mis-parsed inline `parameters: { ... }` entries.
    Recorded here because a guard against unchecked numbers reporting an
    unchecked number of its own would be a poor joke.)
  * `domain-literature.ts` attaches a `defaultJustification` to those
    numbers reading "per Lehninger (2008)" and "per Kermack & McKendrick
    (1927)", which no test, guard, or human ever verified. Five of that
    file's DOIs turned out to be wrong (Stage 9 Part 6) — two of them
    resolving cleanly to entirely unrelated papers.

So the repository asserted literature backing in prose while the numbers
underneath were chosen by hand. That is precisely the failure this project
exists to refuse in *other* people's science code.

This guard does not demand that every number be literature-derived. Some
legitimately cannot be: `points=51` is a plotting resolution, `end=10` is a
time window. Demanding a citation for those would produce fake citations,
which is worse than none.

What it demands is that every number be **declared**, in
`docs/literature-inventory.toml`, as exactly one of:

  RESOLVED       - not a constant at all; fetched live from a primary
                   source per query, with a citation attached to the value
                   (BRENDA, stdpopsim, the ADR 0017 registry).
  VERIFIED       - a constant whose value was checked against a named
                   primary source, with the check itself automated.
  UNVERIFIED     - a teaching default chosen for pedagogy, not derived from
                   any source. Permitted, but it must SAY so, and it must
                   never be described as literature-backed anywhere.
  NOT_SCIENTIFIC - a numerical/presentational parameter (grid points,
                   integration window). Carries no scientific claim.

A number present in the code but absent from the inventory is a hard
failure. That is the whole mechanism: you cannot add an unexplained
constant without the build telling on you.

The guard then prints the honest split. If the answer is "30 of 64 are
teaching defaults", the project says that out loud instead of implying
otherwise.

Run directly: python scripts/check_literature_inventory.py
"""

from __future__ import annotations

import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
INVENTORY = REPO_ROOT / "docs" / "literature-inventory.toml"
QUERY_RESOLVER = (
    REPO_ROOT
    / "Science-Agent-Pipeline/artifacts/api-server/src/lib/queryResolver.ts"
)

VALID_STATUSES = {"RESOLVED", "VERIFIED", "UNVERIFIED", "NOT_SCIENTIFIC"}

#: Statuses that constitute a scientific claim, and therefore require a
#: `source` naming where the value came from.
REQUIRE_SOURCE = {"RESOLVED", "VERIFIED"}


def domain_defaults() -> dict[str, dict[str, str]]:
    """Every hardcoded number in DOMAIN_DEFAULTS, as {domain: {param: value}}.

    Parsed from source rather than imported, so the guard keeps working when
    the TypeScript toolchain is what is broken.
    """
    if not QUERY_RESOLVER.is_file():
        return {}
    text = QUERY_RESOLVER.read_text(encoding="utf-8")
    block = re.search(
        r"const DOMAIN_DEFAULTS: DomainDefaults\[\] = \[(.*?)\n\];",
        text,
        re.DOTALL,
    )
    if not block:
        return {}

    body = block.group(1)
    found: dict[str, dict[str, str]] = {}

    # Entries declare `parameters` either inline (`parameters: { km: 2, ... }`)
    # or spread over lines. An earlier version of this matched only the
    # multi-line form, so for an inline entry the non-greedy scan ran on to
    # the NEXT entry's block -- reporting SIR's parameters under `mm`. A
    # guard whose extraction is silently wrong is worse than no guard, so
    # the braces are matched by counting rather than by pattern.
    for entry in re.finditer(r'domain:\s*"([a-z0-9_]+)"', body):
        domain = entry.group(1)
        start = body.find("parameters:", entry.end())
        if start == -1:
            continue
        open_brace = body.find("{", start)
        if open_brace == -1:
            continue
        depth, index = 0, open_brace
        while index < len(body):
            if body[index] == "{":
                depth += 1
            elif body[index] == "}":
                depth -= 1
                if depth == 0:
                    break
            index += 1
        params = body[open_brace + 1 : index]
        numbers = {
            pair.group(1): pair.group(2)
            for pair in re.finditer(
                r"([a-z0-9_]+):\s*(-?[0-9][0-9.e+-]*)\s*(?:,|$)", params
            )
        }
        if numbers:
            found[domain] = numbers
    return found


def _parse_inventory(text: str) -> dict[str, dict[str, str]]:
    """Minimal TOML-subset reader: [section] then key = "value" lines.

    Deliberately not `tomllib`: this must run on the pinned 3.10 floor
    (ADR 0014), where tomllib does not exist, and adding a dependency to a
    guard would make the guard the thing that breaks the build.
    """
    sections: dict[str, dict[str, str]] = {}
    current: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1].strip()
            sections[current] = {}
            continue
        if current is None or "=" not in line:
            continue
        key, _, value = line.partition("=")
        sections[current][key.strip()] = value.strip().strip('"')
    return sections


def check() -> tuple[list[str], dict[str, int]]:
    violations: list[str] = []
    tally: dict[str, int] = {s: 0 for s in VALID_STATUSES}

    defaults = domain_defaults()
    if not defaults:
        return (
            [
                "parsed ZERO domains out of DOMAIN_DEFAULTS in queryResolver.ts. "
                "The declaration's shape has probably changed; this guard "
                "cannot verify provenance until its extraction is updated. "
                "Refusing to report success."
            ],
            tally,
        )

    if not INVENTORY.is_file():
        return (
            [
                f"missing {INVENTORY.relative_to(REPO_ROOT)}. Every scientific "
                "number must declare its provenance there."
            ],
            tally,
        )

    inventory = _parse_inventory(INVENTORY.read_text(encoding="utf-8"))

    for domain in sorted(defaults):
        for param in sorted(defaults[domain]):
            key = f"{domain}.{param}"
            entry = inventory.get(key)
            if entry is None:
                violations.append(
                    f"{key} = {defaults[domain][param]} is hardcoded in "
                    f"DOMAIN_DEFAULTS but absent from the inventory. Declare "
                    f"it as RESOLVED / VERIFIED / UNVERIFIED / NOT_SCIENTIFIC "
                    f"in docs/literature-inventory.toml."
                )
                continue

            status = entry.get("status", "")
            if status not in VALID_STATUSES:
                violations.append(
                    f"{key} has status {status!r}, which is not one of "
                    f"{sorted(VALID_STATUSES)}."
                )
                continue
            tally[status] += 1

            if status in REQUIRE_SOURCE and not entry.get("source"):
                violations.append(
                    f"{key} claims status {status} but names no source. A "
                    "verification nobody can re-check is not a verification."
                )

            declared = entry.get("value")
            actual = defaults[domain][param]
            if declared and float(declared) != float(actual):
                violations.append(
                    f"{key} is {actual} in the code but the inventory "
                    f"records {declared}. The inventory has drifted from "
                    "reality — one of them is a lie."
                )

    # An inventory entry for a number that no longer exists is stale and
    # will quietly rot into a false claim of coverage.
    live_keys = {f"{d}.{p}" for d in defaults for p in defaults[d]}
    for key in sorted(inventory):
        if key not in live_keys:
            violations.append(
                f"inventory declares {key}, which no longer exists in "
                "DOMAIN_DEFAULTS. Remove it rather than leaving a claim "
                "about nothing."
            )

    return violations, tally


def main() -> int:
    violations, tally = check()
    total = sum(tally.values())

    if violations:
        print("Literature provenance violations found:\n")
        for violation in violations:
            print(f"  {violation}")
        print(
            "\nEvery scientific number must declare where it came from. "
            "UNVERIFIED is an acceptable answer; silence is not."
        )
        return 1

    scientific = tally["RESOLVED"] + tally["VERIFIED"]
    claimable = scientific + tally["UNVERIFIED"]
    print(f"OK: all {total} DOMAIN_DEFAULTS numbers declare their provenance.")
    print(f"    RESOLVED (live from a primary source) : {tally['RESOLVED']}")
    print(f"    VERIFIED (checked against a source)   : {tally['VERIFIED']}")
    print(f"    UNVERIFIED (teaching default)         : {tally['UNVERIFIED']}")
    print(f"    NOT_SCIENTIFIC (grid/window)          : {tally['NOT_SCIENTIFIC']}")
    if claimable:
        pct = 100.0 * scientific / claimable
        print(
            f"\n    Of the {claimable} numbers that carry a scientific claim, "
            f"{scientific} ({pct:.0f}%) trace to a source."
        )
        if tally["UNVERIFIED"]:
            print(
                f"    {tally['UNVERIFIED']} are teaching defaults and must "
                "never be described as literature-backed."
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
