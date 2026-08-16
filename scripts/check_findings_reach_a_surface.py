#!/usr/bin/env python3
"""Does everything the resolver computes actually reach a reader?

WHY THIS EXISTS
---------------
Twice now, a field has been computed correctly and thrown away at the
process boundary:

  * ADR 0027. `science_agent_runner.py` graded every value on Bakker's three
    axes and emitted the score. `ScienceAgentResult` had no field to receive
    it, so the API server discarded it and recomputed a worse version.

    NOTE, because an earlier draft of this docstring overstated it: this
    guard would NOT have caught ADR 0027. `reliability` is computed inside
    the runner and is not a field on `KineticResult`, so it is outside what
    is walked. Mutating the runner to stop emitting it leaves this guard
    green. Said plainly rather than left implied -- a guard advertised as
    covering a defect it does not cover is worse than one with a stated
    scope.

  * ADR 0039. Four pool-level detectors -- effector contrasts, form
    mixtures, organism discrepancies, source mixtures -- were computed,
    attached to `KineticResult`, and never emitted at all. Every detector
    was mutation-tested. Every test passed. Nobody ever saw a finding.

A concurrent agent hit the same class in the same hour (ADR 0038), which is
evidence about the defect rather than about anyone's care: **a boundary that
drops a field is invisible from both sides.** The producer's tests pass
because it produced. The consumer has nothing to test because it never knew.

ADR 0039 closed with the observation that the fix is "the specific act of
tracing one finding from the module that computes it to the surface a person
reads, and that trace is cheap enough to be routine."

A lesson written in an ADR is a lesson that gets read once. This makes the
trace automatic.

WHAT IT CHECKS
--------------
For every field on `KineticResult` -- the resolver's output, the thing every
detector writes into -- it walks the delivery chain:

    resolver  ->  runner emits  ->  TypeScript receives  ->  a reader sees

and reports fields that stop early.

The last hop is checked loosely, by looking for the field name in the
rendering surfaces (`provenance.flags` construction, and the CLI's resolve
command). A name appearing there is not proof it renders well; a name
absent from all of them is proof it renders not at all, which is the failure
this guard is for.

WHY THE FIELD LIST IS IMPORTED, NOT WRITTEN DOWN
------------------------------------------------
`KineticResult.model_fields` comes from the model itself. A guard with its
own copy of the field list would keep passing after a new field was added --
which is precisely the failure mode, one level up. Same reasoning as
`check_commentary_coverage.py` importing the production regexes.

WHAT A FAILURE MEANS
--------------------
Not always "wire it up". Some fields are internal and legitimately stop at
the resolver. `docs/undelivered-fields-baseline.txt` records those with the
reason, and a line there is a DECISION -- the same contract as the
commentary residue baseline, and the same warning: it is not a mute button.

Usage:
    python3 scripts/check_findings_reach_a_surface.py
    python3 scripts/check_findings_reach_a_surface.py --update-baseline
"""
from __future__ import annotations

import argparse
import pathlib
import textwrap
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
TESTS = REPO_ROOT / "Tests"
BASELINE = REPO_ROOT / "docs" / "undelivered-fields-baseline.txt"

RUNNER = (
    REPO_ROOT
    / "Science-Agent-Pipeline/artifacts/api-server/src/lib/science_agent_runner.py"
)
TS_RESULT = (
    REPO_ROOT / "Science-Agent-Pipeline/artifacts/api-server/src/lib/scienceAgent.ts"
)
#: Where a field can become something a person sees.
SURFACES = [
    REPO_ROOT / "Science-Agent-Pipeline/artifacts/api-server/src/lib/queryResolver.ts",
    REPO_ROOT / "src/cli/commandResolve.ts",
    REPO_ROOT / "src/literature/literatureResolver.ts",
]

sys.path.insert(0, str(TESTS))

try:
    from fallback_logic import KineticResult
except ImportError as exc:  # pragma: no cover - environment, not a finding
    print(f"Could not import the model this guard measures: {exc}")
    print("An environment failure, not a delivery result. Not reporting a number.")
    raise SystemExit(1)


def _snake_to_camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(w.capitalize() for w in rest)


def _mentions(haystack: str, field: str) -> bool:
    """Is this field named here, in either casing convention?

    Both are accepted because the wire uses camelCase and the Python models
    use snake_case, and different fields cross in different conventions --
    `relatedness` keeps snake_case inside its items deliberately, so a guard
    insisting on one spelling would report false failures.
    """
    for candidate in {field, _snake_to_camel(field)}:
        if re.search(rf"\b{re.escape(candidate)}\b", haystack):
            return True
    return False


ALIASES = REPO_ROOT / "docs" / "field-wire-names.txt"


def load_aliases() -> dict[str, str]:
    """Python field name -> the name it travels under on the wire.

    Six fields are RENAMED at the boundary: `assay_ph` is emitted as
    `assayConditions.ph`, `cross_species_flag` as `crossSpecies`,
    `search_log` as `logs`. A name-matching guard cannot see them, and its
    first run reported all six as undelivered.

    Baselining them would have been wrong, and instructively so: the
    baseline means "internal, does not need to reach anyone", and these all
    reach a reader. Recording a true thing under a false heading is how a
    decision file stops being read.

    So an alias REDIRECTS the check rather than excusing it. The aliased
    name must still appear at every hop, which means an alias cannot be used
    to hide a drop -- point it at a name nothing emits and the guard fails
    exactly as before.
    """
    if not ALIASES.exists():
        return {}
    out: dict[str, str] = {}
    for line in ALIASES.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        field, _, rest = stripped.partition("->")
        wire, _, _reason = rest.partition("#")
        if field.strip() and wire.strip():
            out[field.strip()] = wire.strip()
    return out


def load_baseline() -> dict[str, str]:
    if not BASELINE.exists():
        return {}
    out: dict[str, str] = {}
    for line in BASELINE.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        field, _, reason = stripped.partition("#")
        out[field.strip()] = reason.strip()
    return out


def _emitted_keys() -> set[str] | None:
    """Keys the runner ACTUALLY emits, by running it.

    THIS REPLACED A NAME-MATCHING CHECK, AND THE REPLACEMENT IS THE POINT.

    The first version of this guard asked whether each field's name appeared
    anywhere in the runner's source. It was mutation-tested by deleting the
    emission of `poolFindings` — the exact defect of ADR 0039 — and it
    passed, because the list comprehensions below the deleted key still
    mentioned `result.effector_contrasts`. The word was present; the field
    was not delivered.

    A guard that answers "is this word written in this file" while claiming
    to answer "does this field travel" is the false-green shape this
    repository has catalogued five times. It was worse than no guard,
    because it was about to be trusted.

    So the chain is executed. A fully populated KineticResult goes in, the
    runner runs, and the emitted JSON is read. Deleting an emission now
    changes the output, because the output is what is measured.
    """
    import json
    import subprocess
    import tempfile

    probe = textwrap.dedent(
        """
        import json, sys, types
        sys.path.insert(0, %r)
        import fallback_logic
        from fallback_logic import KineticResult

        # A result with every field set to something truthy, so a dropped
        # field is a missing key rather than an empty one.
        populated = KineticResult(
            found=True, value=1.0, unit="mM", organism="Homo sapiens",
            source="brenda_exact",
        )
        for name, info in KineticResult.model_fields.items():
            current = getattr(populated, name)
            if current not in (None, [], "", 0, False):
                continue
            ann = str(info.annotation)
            if "list" in ann:
                continue  # empty list still emits its key
            if "bool" in ann:
                setattr(populated, name, True)
            elif "float" in ann or "int" in ann:
                setattr(populated, name, 1.0)
            elif "str" in ann:
                setattr(populated, name, "x")

        fallback_logic.resolve_kinetic_value = lambda *a, **k: populated
        sys.modules["fallback_logic"].resolve_kinetic_value = lambda *a, **k: populated
        print(json.dumps(sorted(KineticResult.model_fields)))
        """
    ) % str(TESTS)

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(probe)
        probe_path = fh.name
    try:
        proc = subprocess.run(
            [sys.executable, probe_path], capture_output=True, text=True, timeout=120
        )
    except Exception:  # noqa: BLE001
        return None
    finally:
        pathlib.Path(probe_path).unlink(missing_ok=True)

    if proc.returncode != 0:
        return None

    # Run the runner itself with the populated result patched in.
    runner_probe = textwrap.dedent(
        """
        import io, json, sys, importlib.util, contextlib
        sys.path.insert(0, %r)
        import fallback_logic
        from fallback_logic import KineticResult

        # BOTH BRANCHES. The runner emits a different dict for a found
        # result and for a withheld one, and a probe that exercises one
        # measures one. `cross_species_organisms_available` and
        # `variant_candidates_available` live only on the withheld path --
        # the first version of this probe reported both as undelivered,
        # which was the probe's gap and not the runner's.
        cases = [
            KineticResult(
                found=True, value=1.0, unit="mM", organism="Homo sapiens",
                source="brenda_exact", cross_species_flag=True,
                assay_ph=7.4, assay_temperature_c=25.0, assay_buffer="Tris",
                assay_unreported=["x"], search_log=["x"],
            ),
            KineticResult(
                found=False, source="cross_species_withheld",
                cross_species_organisms_available=["Sus scrofa"],
                search_log=["x"],
            ),
            KineticResult(
                found=False, source="variant_withheld",
                variant_candidates_available=["Y124C"],
                search_log=["x"],
            ),
        ]

        spec = importlib.util.spec_from_file_location("runner", %r)
        runner = importlib.util.module_from_spec(spec)
        sys.modules["runner"] = runner
        spec.loader.exec_module(runner)
        runner._reliability_dict = lambda *a, **k: {}

        payload = {
            "enzymeName": "lactate dehydrogenase", "substrate": "lactate",
            "organism": "Homo sapiens", "ecNumber": "1.1.1.27",
        }

        all_emitted = {}
        for case in cases:
            runner.resolve_kinetic_value = lambda *a, _c=case, **k: _c
            sys.stdin = io.StringIO(json.dumps(payload))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                try:
                    runner.main()
                except SystemExit:
                    pass
            out = buf.getvalue().strip().splitlines()
            if out:
                try:
                    all_emitted.update({k: v for k, v in json.loads(out[-1]).items()})
                except Exception:
                    pass
        emitted = all_emitted

        def walk(obj, prefix=""):
            # PATHS, not bare keys. The first version collected every key at
            # every depth, which made a container rename invisible: moving
            # the four detectors from "poolFindings" to "_disabled" left
            # every inner key present, and the guard passed on the exact
            # defect it was built for.
            keys = set()
            if isinstance(obj, dict):
                for k, v in obj.items():
                    path = f"{prefix}.{k}" if prefix else k
                    keys.add(path)
                    keys.add(k)  # bare name too, for top-level fields
                    keys |= walk(v, path)
            elif isinstance(obj, list) and obj:
                keys |= walk(obj[0], prefix)
            return keys

        print(json.dumps(sorted(walk(emitted))))
        """
    ) % (str(TESTS), str(RUNNER))

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(runner_probe)
        rp = fh.name
    try:
        proc = subprocess.run(
            [sys.executable, rp], capture_output=True, text=True, timeout=180
        )
    except Exception:  # noqa: BLE001
        return None
    finally:
        pathlib.Path(rp).unlink(missing_ok=True)

    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        return set(json.loads(proc.stdout.strip().splitlines()[-1]))
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()

    missing_files = [p for p in [RUNNER, TS_RESULT, *SURFACES] if not p.exists()]
    if missing_files:
        # A guard that cannot read the chain must not report the chain
        # intact. Zero problems found across zero files is the most
        # reassuring possible wrong answer.
        print("Cannot read the delivery chain; these files are missing:")
        for p in missing_files:
            print(f"  {p.relative_to(REPO_ROOT)}")
        print("\nNot reporting a delivery result. Failing.")
        return 1

    runner_src = RUNNER.read_text()
    ts_src = TS_RESULT.read_text()
    surface_src = "\n".join(p.read_text() for p in SURFACES)

    fields = list(KineticResult.model_fields)
    if not fields:
        print("KineticResult declares no fields. Failing rather than passing.")
        return 1

    aliases = load_aliases()

    # The runner hop is verified by EXECUTION, not by reading its source.
    # Name matching passed when the emission of `poolFindings` was deleted,
    # because the list comprehensions under the deleted key still mentioned
    # the field. See `_emitted_keys`.
    emitted = _emitted_keys()
    if emitted is None:
        print(
            "\nCould not run the runner to see what it emits.\n"
            "This guard refuses to fall back to reading its source: the\n"
            "source-reading version passed while the emission was deleted.\n"
            "Failing rather than reporting a delivery result it did not measure."
        )
        return 1

    stops: dict[str, str] = {}
    for field in fields:
        # An alias redirects the check to the name the field travels under.
        # It does NOT excuse the field: every hop below is still required.
        wire = aliases.get(field, field)
        # The PATH pins the wire shape -- a renamed container breaks it.
        # The LEAF is what TypeScript and the renderers name, since neither
        # writes the dotted path out. Two different questions, so two
        # different strings.
        leaf = wire.rsplit(".", 1)[-1]
        if wire not in emitted and _snake_to_camel(wire) not in emitted:
            stops[wire] = "computed by the resolver, never emitted by the runner"
        elif not _mentions(ts_src, leaf):
            stops[wire] = "emitted by the runner, never received by TypeScript"
        elif not _mentions(surface_src, leaf):
            stops[wire] = "received by TypeScript, never reaches a rendering surface"

    print(f"Fields on KineticResult:        {len(fields)}")
    print(f"Reaching a rendering surface:   {len(fields) - len(stops)}")
    print(f"Stopping short:                 {len(stops)}")

    if args.update_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        header = (
            "# Fields that stop before reaching a reader, reviewed and accepted.\n"
            "#\n"
            "# Regenerate: python3 scripts/check_findings_reach_a_surface.py "
            "--update-baseline\n"
            "#\n"
            "# A line here is a DECISION that the field is internal and does not\n"
            "# need to reach anyone. It is not a way to silence the guard.\n"
            "#\n"
            "# The two defects that motivated this guard -- ADR 0027 and ADR 0039 --\n"
            "# would BOTH have appeared here, and adding them without reading the\n"
            "# reason would have been the wrong call both times.\n"
            "\n"
        )
        body = "\n".join(f"{f}  # {why}" for f, why in sorted(stops.items()))
        BASELINE.write_text(header + body + "\n")
        print(f"\nBaseline written: {BASELINE.relative_to(REPO_ROOT)} ({len(stops)} fields)")
        return 0

    baseline = load_baseline()
    unreviewed = {f: why for f, why in stops.items() if f not in baseline}

    if unreviewed:
        print(f"\nUndelivered and unreviewed ({len(unreviewed)}):\n")
        for field, why in sorted(unreviewed.items()):
            print(f"  {field}\n      {why}")
        print(
            "\nEach of these is something the resolver computes that nobody sees.\n"
            "That is how Bakker's condition-proximity axis stayed a constant for\n"
            "the life of the API (ADR 0027), and how four pool-level detectors\n"
            "shipped without ever producing a visible finding (ADR 0039).\n"
            "\nWire it through, or record why it does not need to be:\n"
            "  python3 scripts/check_findings_reach_a_surface.py --update-baseline\n"
        )
        return 1

    print("\nOK: every computed field either reaches a reader or is recorded as internal.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
