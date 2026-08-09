"""Guard that every layer agrees on which simulation domains exist.

A domain has to be declared in four places to actually work:

  1. ``tellurium_runner.py``'s ``DISPATCH``      (domain -> engine function)
  2. ``telluriumRunner.ts``'s ``SimulationDomain`` union
  3. ``schemas.ts``'s ``SimulationParameterSchemas``
  4. the engine's ``__all__`` (checked by DISPATCH's own contract test)

``Tellurium/tests/test_boundary_contract.py`` (ADR 0007) already pins 1
against 4. Nothing pinned 2 or 3 against anything, and on 2026-08-09 that
cost real money in two opposite directions on the same day:

  * Three domains -- ``lotka_volterra``, ``cell_cycle_oscillator``,
    ``repressilator`` -- were declared in 2 and 3, given Zod schemas, test
    fixtures, DISPATCH entries and ``run_*`` handlers, while
    ``simulate_lotka_volterra`` and friends **did not exist in the engine
    at all**. The handlers called an attribute that had never been
    defined; any request routed to those domains would have raised
    ``AttributeError`` at runtime. A fully type-checked, schema-validated
    contract for a capability the project does not have.

  * Simultaneously, two domains that DO exist and work -- ``monte_carlo_pi``
    and ``gillespie_ssa_replicates``, both in the engine's ``__all__``,
    both with working handlers, Monte Carlo being in the README's
    documented domain list -- were **deleted from DISPATCH** with the note
    "not part of the TypeScript API contract". That inverts ADR 0007: the
    engine's surface is the contract and the TypeScript side follows it,
    not the reverse. It broke five boundary-contract tests.

Two agents fixing the same drift in opposite directions, neither checking
which side was authoritative. This guard removes the ambiguity by refusing
to let the four lists differ at all, in either direction.

Parsing note: this reads the TypeScript as text rather than running ``tsc``
to extract the types. That is deliberate -- a guard that needs a working
Node toolchain to tell you your domains disagree is useless in exactly the
situation where the toolchain is what broke. The extraction is pinned by
its own sanity check: if a list comes back empty, that is reported as a
failure rather than silently passing an empty-vs-empty comparison.

Run directly: python scripts/check_domain_parity.py
"""

from __future__ import annotations

import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
API_LIB = (
    REPO_ROOT
    / "Science-Agent-Pipeline"
    / "artifacts"
    / "api-server"
    / "src"
    / "lib"
)
RUNNER_PY = API_LIB / "tellurium_runner.py"
LLM_RESOLVER_TS = API_LIB / "llmResolver.ts"
RUNNER_TS = API_LIB / "telluriumRunner.ts"
SCHEMAS_TS = API_LIB / "schemas.ts"

#: `sbml` is the raw-SBML escape hatch, not a teaching domain. It is
#: dispatched and typed like the others, so it participates in parity;
#: named here only so the failure messages can say what it is.
ESCAPE_HATCH = "sbml"


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def dispatch_domains() -> set[str]:
    """Keys of DISPATCH in tellurium_runner.py."""
    source = _read(RUNNER_PY)
    match = re.search(
        r"^DISPATCH:\s*Dict\[str,\s*str\]\s*=\s*\{(.*?)^\}",
        source,
        re.DOTALL | re.MULTILINE,
    )
    if not match:
        return set()
    return set(re.findall(r'^\s*"([a-z0-9_]+)"\s*:', match.group(1), re.MULTILINE))


def simulation_domain_union() -> set[str]:
    """Members of the SimulationDomain union in telluriumRunner.ts."""
    source = _read(RUNNER_TS)
    match = re.search(
        r"export type SimulationDomain\s*=(.*?);", source, re.DOTALL
    )
    if not match:
        return set()
    # Strip // comments so a domain named inside prose (this file has some)
    # cannot be mistaken for a union member.
    body = re.sub(r"//[^\n]*", "", match.group(1))
    return set(re.findall(r'"([a-z0-9_]+)"', body))


def schema_domains() -> set[str]:
    """Keys of SimulationParameterSchemas in schemas.ts.

    Matches only keys at the object's top indentation level (two spaces),
    so nested z.object({...}) field names are not mistaken for domains.
    """
    source = _read(SCHEMAS_TS)
    match = re.search(
        r"export const SimulationParameterSchemas:.*?=\s*\{(.*?)^\};",
        source,
        re.DOTALL | re.MULTILINE,
    )
    if not match:
        return set()
    return set(
        # `z` and `.object` are frequently split across lines by the
        # formatter (`mm: z\n    .object({`), so allow whitespace between
        # them -- requiring adjacency silently under-counted domains.
        re.findall(
            r"^  ([a-z0-9_]+):\s*z\s*\.\s*object", match.group(1), re.MULTILINE
        )
    )


def llm_supported_domains() -> set[str]:
    """SUPPORTED_DOMAINS -- the allowlist inside resolveQueryWithLLM.

    This is a deliberate SUBSET of DISPATCH, not an equal set: `sbml` is an
    internal escape hatch, and `monte_carlo_pi` / `gillespie_ssa_replicates`
    are engine-internal and not offered to the LLM. So it is checked for
    containment rather than parity -- but it must never name a domain that
    does not exist, which is exactly how `lotka_volterra` reached it.
    """
    source = _read(LLM_RESOLVER_TS)
    match = re.search(
        r"const SUPPORTED_DOMAINS\s*=\s*\[(.*?)\]\s*as const", source, re.DOTALL
    )
    if not match:
        return set()
    body = re.sub(r"//[^\n]*", "", match.group(1))
    return set(re.findall(r'"([a-z0-9_]+)"', body))


def _layers() -> dict[str, set[str]]:
    """The three declaration sites, by human-readable name."""
    return {
        "DISPATCH (tellurium_runner.py)": dispatch_domains(),
        "SimulationDomain (telluriumRunner.ts)": simulation_domain_union(),
        "SimulationParameterSchemas (schemas.ts)": schema_domains(),
    }


def check() -> list[str]:
    violations: list[str] = []

    for path in (RUNNER_PY, RUNNER_TS, SCHEMAS_TS):
        if not path.is_file():
            violations.append(f"missing file: {path.relative_to(REPO_ROOT)}")
    if violations:
        return violations

    layers = _layers()

    # An empty extraction means the parse broke, not that a layer is empty.
    # Reported loudly: a silently-empty list would make every comparison
    # below trivially pass, which is the failure mode this guard exists to
    # prevent in the first place.
    for name, domains in layers.items():
        if not domains:
            violations.append(
                f"parsed ZERO domains out of {name}. The file's shape has "
                "probably changed; this guard cannot verify parity until "
                "its extraction is updated. Refusing to report success."
            )
    if violations:
        return violations

    union = set().union(*layers.values())
    for domain in sorted(union):
        present = [name for name, doms in layers.items() if domain in doms]
        missing = [name for name, doms in layers.items() if domain not in doms]
        if missing:
            label = f"{domain!r}"
            if domain == ESCAPE_HATCH:
                label += " (the raw-SBML escape hatch)"
            violations.append(
                f"{label} is declared in {len(present)} of {len(layers)} layers."
                f"\n      present in: {', '.join(present)}"
                f"\n      MISSING from: {', '.join(missing)}"
            )

    # SUPPORTED_DOMAINS is a subset by design, so it gets a containment
    # check rather than joining the parity set above. Without this,
    # llmResolver.ts was a fourth place a nonexistent domain could be
    # advertised -- `lotka_volterra` reached it and was only caught by a
    # test that happened to iterate the list.
    llm_domains = llm_supported_domains()
    if not llm_domains:
        violations.append(
            "parsed ZERO domains out of SUPPORTED_DOMAINS (llmResolver.ts). "
            "Refusing to report success."
        )
    else:
        dispatch = layers["DISPATCH (tellurium_runner.py)"]
        for domain in sorted(llm_domains - dispatch):
            violations.append(
                f"{domain!r} is advertised to the LLM in SUPPORTED_DOMAINS "
                "(llmResolver.ts) but is NOT in DISPATCH -- the LLM can "
                "return a domain the engine cannot run."
            )

    return violations


def main() -> int:
    violations = check()
    if not violations:
        layers = _layers()
        teaching = sorted(d for d in dispatch_domains() if d != ESCAPE_HATCH)
        print(
            f"OK: all {len(layers)} layers agree on {len(teaching)} "
            f"simulation domain(s) + the {ESCAPE_HATCH} escape hatch."
        )
        return 0

    print("Domain parity violations found:\n")
    for violation in violations:
        print(f"  {violation}")
    print(
        "\nEvery domain must be declared in ALL layers, and no layer may "
        "declare one the others do not."
        "\nADR 0007: the ENGINE's surface is the contract -- if a domain is "
        "not implemented in the engine, remove it from the API layers "
        "rather than adding a handler for a function that does not exist."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
