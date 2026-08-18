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
#: The TypeScript that RECEIVES the runner's JSON.
#:
#: This was `scienceAgent.ts` alone, and that file does not declare the
#: shapes -- it imports them:
#:
#:     import type { BufferIdentity, Effector } from "./provenance";
#:
#: So `Effector.raw`, `.compound_text`, `.presence`, `.concentration_text`
#: and `.identity` are all fully declared, in the other file, and the guard
#: reported seven of them as **never received by TypeScript**. A false
#: accusation, and the second one found in this pass: a matcher whose scope
#: is narrower than the thing it measures does not report "I could not
#: see", it reports "it is not there".
TS_RESULT_FILES = [
    REPO_ROOT / "Science-Agent-Pipeline/artifacts/api-server/src/lib/scienceAgent.ts",
    REPO_ROOT / "Science-Agent-Pipeline/artifacts/api-server/src/lib/provenance.ts",
]
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


def _nested_models(annotation) -> list:
    """Every pydantic model reachable from a type annotation.

    Unwraps the shapes these fields actually use -- `X | None`,
    `list[X]`, `list[X] | None` -- rather than only bare `X`. A matcher that
    handled just the bare case would miss every list-valued finding, which
    is most of them.
    """
    import typing

    from pydantic import BaseModel

    found = []
    stack = [annotation]
    seen_ann = []
    while stack:
        current = stack.pop()
        if current in seen_ann:
            continue
        seen_ann.append(current)
        if isinstance(current, type) and issubclass(current, BaseModel):
            found.append(current)
            continue
        stack.extend(typing.get_args(current) or [])
    return found


def walk_fields(model, prefix: str = "", seen: frozenset = frozenset()) -> list[str]:
    """Dotted paths for every field, descending into nested models.

    WHY THIS EXISTS
    ---------------
    This guard reported **26 of 26 fields reaching a reader** while asking
    only about `KineticResult`'s own attributes. `selection_tie` counted as
    delivered because a surface named `selectionTie` -- and `SelectionTie`
    carries `low`, `high`, `fold_range`, `candidates` and `reason`, none of
    which the guard had any opinion about.

    That is **the presence of a container taken as evidence about its
    contents**, which is the same half-check found in ADR 0090's baseline
    (a matcher that could not see classes) and in ADR 0098's set-file
    validation (`test` and `mutations` present, entries never inspected).
    Third location, same shape.

    A cycle would loop forever, so `seen` carries the models already opened
    on this path. Not defensive decoration: `KineticResult` is built from
    modules that import each other.
    """
    paths: list[str] = []
    for name, info in model.model_fields.items():
        path = f"{prefix}.{name}" if prefix else name
        paths.append(path)
        for inner in _nested_models(info.annotation):
            if inner in seen or inner is model:
                continue
            paths.extend(walk_fields(inner, path, seen | {inner, model}))
    return paths


def is_measurable(field: str, aliases: dict, measurable_parents: set) -> bool:
    """Only fields the nested descent ADDED can be excused. Never an original.

    THE FIRST VERSION OF THIS FUNCTION BROKE THE GUARD, and the mutation set
    caught it within a minute: ADR 0039's original defect -- the runner stops
    emitting `poolFindings` -- went from caught to **NOT CAUGHT**.

    The bug was testing the WIRE path instead of the MODEL path.
    `effector_contrasts` is a top-level field whose alias is the dotted
    `poolFindings.effectorContrasts`; deleting that emission emptied
    `measurable_parents`, so the field was reclassified "not measurable" and
    quietly skipped. **The new third state excused the exact defect the guard
    was built for**, and the excuse grew STRONGER the more thoroughly the
    emission was deleted.

    A third state that can swallow a real failure is worse than two states.
    Nesting is therefore decided by the model path -- a fact about the schema,
    which breaking the runner cannot change.

    Lifted out of `main` so the invariant can be asserted directly. As a
    closure it was only reachable through a full runner execution, and the
    weakness is CONDITIONAL: reverting this line alone changes no output, so
    no single mutation can express it. That is why it is a self-test case and
    not a mutation -- recording a no-op mutation as "caught" would be a
    result the harness never established.
    """
    if "." not in field:
        return True
    parent = aliases.get(field, field).rsplit(".", 1)[0]
    # Both sides normalised here rather than trusting the caller to have
    # done it. The self-test passes `{"selectionTie"}` -- the name a reader
    # would write -- and a classifier that only worked on pre-normalised
    # input would make the test a statement about the caller's bookkeeping
    # instead of about the rule.
    return _normalise_path(parent) in {_normalise_path(p) for p in measurable_parents}


#: Where one function begins in a TypeScript surface file. Crude on purpose:
#: it only has to chop the file into units small enough that co-occurrence
#: means something, and it produces 46 of them across the three surfaces.
_BLOCK_START = re.compile(
    r"^(?:export\s+)?(?:async\s+)?(?:function\s+\w+|const\s+\w+\s*[:=])", re.M
)


def _blocks(src: str) -> list[str]:
    starts = [m.start() for m in _BLOCK_START.finditer(src)]
    if not starts:
        return [src]
    return [
        src[s : (starts[i + 1] if i + 1 < len(starts) else len(src))]
        for i, s in enumerate(starts)
    ]


def _member_reference(leaf: str, block: str) -> bool:
    """Is `leaf` READ here, rather than merely spelled here?

    `c.reference_id`, `x["title"]`, `{ title: ... }` count. The bare word
    `title` in a comment or an unrelated identifier does not. Without this,
    incidental co-occurrence inside a long function resolves an ambiguity
    that was never resolved -- swapping an over-confident file-wide match
    for an over-confident block-wide one.
    """
    return bool(
        re.search(rf"[.\[]\s*['\"]?{re.escape(leaf)}\b", block)
        or re.search(rf"\b{re.escape(leaf)}\s*:", block)
    )


def reaches_surface_in_scope(wire: str, surface_blocks: list[str]) -> bool:
    """A leaf shared by several fields, pinned to the right parent.

    THE PROBLEM THIS SOLVES
    -----------------------
    The last hop was decided by looking for a bare leaf name anywhere in the
    rendering surfaces. Descending into nested models made twelve leaf names
    ambiguous, and wiring `citation.title` silently ACQUITTED
    `literature_candidates.title` -- a different field, on a different code
    path, cleared because the word now appeared (ADR 0104).

    THE EVIDENCE THIS ACCEPTS, STATED HONESTLY
    ------------------------------------------
    A block that both names the parent and reads the leaf as a member is
    stronger evidence than the same two words somewhere in a 2,000-line
    file. It is **not proof**: nothing here understands scope, and a
    function handling two findings at once could still satisfy both halves
    for the wrong one.

    So this can only ever move a field from "unknown" to "delivered", never
    from "undelivered" to anything. A field no surface mentions at all stays
    undelivered regardless.
    """
    leaf = wire.rsplit(".", 1)[-1]
    parent_leaf = _normalise_path(wire.rsplit(".", 1)[0].rsplit(".", 1)[-1])
    return any(
        _member_reference(leaf, block) and parent_leaf in _normalise_path(block)
        for block in surface_blocks
    )


def _normalise_path(path: str) -> str:
    """A dotted path with its casing convention removed.

    THE WIRE MIXES CONVENTIONS, WHICH NAIVE MATCHING CANNOT SURVIVE.

    The runner camelCases the keys it writes by hand (`selectionTie`), and
    `model_dump()` under them preserves the model's snake_case
    (`reference_id`). So the real emitted path is

        selectionTie.candidates.reference_id

    which is neither `selection_tie.candidates.reference_id` nor its
    all-camel conversion `selectionTie.candidates.referenceId`. Testing
    those two forms reported the field as **never emitted by the runner**
    when the runner emits it faithfully -- a false accusation, and the one
    outcome this guard must never produce (ADR 0051, ADR 0056).

    Comparing without underscores or case answers the question actually
    being asked: is there a value at this position, whatever the two sides
    chose to call their capitals?
    """
    return path.replace("_", "").lower()


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

        # WHAT THIS PROBE IS, STATED HONESTLY.
        #
        # It is an IMPORT CHECK. Only its exit status is consulted by the
        # caller -- whatever it prints is thrown away, and for a while it
        # also built a fully populated `KineticResult` and monkeypatched
        # `resolve_kinetic_value` with it, in a subprocess that then exited.
        # Computed, and consumed by nobody: ADR 0039's defect class, living
        # inside the guard written to detect ADR 0039's defect class.
        #
        # The fixture that matters is `cases` in the runner probe below,
        # which is the one whose output is actually read.
        KineticResult(found=True, value=1.0, unit="mM", source="brenda_exact")
        print("import ok")
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
        import io, json, sys, importlib.util, contextlib, typing
        sys.path.insert(0, %r)
        import fallback_logic
        from fallback_logic import KineticResult
        from pydantic import BaseModel

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

        # THE NESTED FINDINGS, POPULATED.
        #
        # The runner forwards these faithfully -- `[c.model_dump() for c in
        # result.effector_contrasts]` -- so an emitted `[]` is a statement
        # about the FIXTURE, not about the runner. Every finding this
        # project built for Jeske's and Bakker's feedback is a nested
        # object, and all of them arrived here empty, so the guard could
        # only ever measure the container.
        #
        # `model_construct` skips validation on purpose: this measures
        # SHAPE, and a validator rejecting a dummy string would turn a
        # question about delivery into a question about plausibility.
        def _models(ann):
            found, stack, seen = [], [ann], []
            while stack:
                cur = stack.pop()
                if cur in seen:
                    continue
                seen.append(cur)
                if isinstance(cur, type) and issubclass(cur, BaseModel):
                    found.append(cur)
                    continue
                stack.extend(typing.get_args(cur) or [])
            return found

        def _fill(model_cls, depth=0):
            # Depth-capped rather than cycle-tracked: a self-referential
            # model would otherwise recurse until the stack ends, and a
            # probe that crashes reports nothing at all.
            if depth > 4:
                return None
            values = {}
            for fname, finfo in model_cls.model_fields.items():
                text = str(finfo.annotation)
                inner = _models(finfo.annotation)
                if inner:
                    built = _fill(inner[0], depth + 1)
                    values[fname] = [built] if "list" in text.lower() else built
                elif "list" in text.lower():
                    values[fname] = ["x"]
                elif "dict" in text.lower():
                    values[fname] = {"x": "y"}
                elif "bool" in text:
                    values[fname] = True
                elif "float" in text or "int" in text:
                    values[fname] = 1.0
                else:
                    values[fname] = "x"
            return model_cls.model_construct(**values)

        # Only fields that arrived EMPTY are filled. The three cases encode
        # which branch of the runner each exercises (found / cross-species
        # withheld / variant withheld), and overwriting their values would
        # silently collapse three probes into one.
        for case in cases:
            for fname, finfo in KineticResult.model_fields.items():
                inner = _models(finfo.annotation)
                if not inner or getattr(case, fname, None) not in (None, [], ""):
                    continue
                built = _fill(inner[0])
                is_list = "list" in str(finfo.annotation).lower()
                object.__setattr__(case, fname, [built] if is_list else built)

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


def selftest() -> int:
    """The invariant no mutation can express.

    `is_measurable` gates whether a field is checked at all, so a bug here
    is silent by construction: the field is not reported undelivered, it is
    not reported delivered, it simply stops being asked about. That is the
    "check that cannot fail" shape sitting inside the check.

    Case 1 is the historical failure, reduced to its smallest form. The rest
    pin the behaviour the third state is FOR, so a fix that simply deleted
    the state would not pass.
    """
    failures = []
    aliases = {"effector_contrasts": "poolFindings.effectorContrasts"}

    # The worst case: a runner emitting nothing nested at all. Every
    # top-level field must still be measured. Under the wire-path version
    # this returned False and ADR 0039's defect went unreported.
    for field in ("effector_contrasts", "value", "citation", "selection_tie"):
        if not is_measurable(field, aliases, set()):
            failures.append(
                f"{field!r} (top-level) was excused as 'not measurable' with no "
                "nested emissions. A deleted emission would make the guard "
                "quieter instead of louder."
            )

    # A genuinely nested field IS excused when its parent produced nothing...
    if is_measurable("selection_tie.low", {}, set()):
        failures.append(
            "'selection_tie.low' was called measurable with no emitted parent; "
            "the guard would report a false accusation."
        )
    # ...and is NOT excused once the parent is there to measure against.
    if not is_measurable("selection_tie.low", {}, {"selectionTie"}):
        failures.append(
            "'selection_tie.low' stayed excused even though 'selectionTie' was "
            "emitted with contents. The third state would then be permanent, "
            "which is a way of never checking."
        )

    print("Self-test: the classifier that decides what gets checked at all.\n")
    for line in failures:
        print(f"  [FAIL] {line}")
    if failures:
        print(f"\nFAIL: {len(failures)} case(s).", file=sys.stderr)
        return 1
    print("  [ok] no top-level field is excused, whatever the runner emits")
    print("  [ok] a nested field is excused only while its parent is unmeasured")
    print("\nOK: the 'not measurable' state cannot swallow an original field.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return selftest()

    missing_files = [p for p in [RUNNER, *TS_RESULT_FILES, *SURFACES] if not p.exists()]
    if missing_files:
        # A guard that cannot read the chain must not report the chain
        # intact. Zero problems found across zero files is the most
        # reassuring possible wrong answer.
        print("Cannot read the delivery chain; these files are missing:")
        for p in missing_files:
            print(f"  {p.relative_to(REPO_ROOT)}")
        print("\nNot reporting a delivery result. Failing.")
        return 1

    # NOTE: the runner is deliberately NOT read here. It used to be --
    # `runner_src = RUNNER.read_text()` sat on this line and was never
    # consulted, the fossil of the v1/v2 name-matching approach that ADR
    # 0045 records as having FAILED: it passed while the emission of
    # `poolFindings` was deleted. The read outlived the method by two
    # rewrites, and a guard that opens a file it does not consult is a
    # small lie about what it checks.
    #
    # Found by ruff F841, which is exactly what that rule is for: an
    # unused binding is often the residue of a superseded approach.
    ts_src = "\n".join(p.read_text() for p in TS_RESULT_FILES)
    surface_src = "\n".join(p.read_text() for p in SURFACES)

    fields = walk_fields(KineticResult)
    top_level = len(KineticResult.model_fields)
    if not fields:
        print("KineticResult declares no fields. Failing rather than passing.")
        return 1
    if len(fields) <= top_level:
        # Every finding on this model is a nested object -- `SelectionTie`,
        # `Relatedness`, `EffectorContrast`. If the descent returns nothing
        # extra it has stopped working, and the guard would go back to
        # reporting a confident number about the shallow question while
        # looking like it asks the deep one.
        print(
            f"FAIL: descent into nested models found nothing ({len(fields)} paths "
            f"for {top_level} top-level fields). The findings on this model are "
            "nested objects; a flat result means the walk broke.",
            file=sys.stderr,
        )
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

    # A nested field can only be judged if the probe actually produced
    # content at its parent. The runner REBUILDS its lists rather than
    # passing them through -- `poolFindings.effectorContrasts` comes out `[]`
    # even when the fixture holds an element -- so for those paths the
    # emitted JSON contains the container and nothing inside it.
    #
    # Reporting those as "never emitted" would be 71 FALSE ACCUSATIONS, the
    # exact failure ADR 0051 and ADR 0056 record: a patch that did not apply,
    # read as a test that did not catch. A false accusation costs more than
    # silence, because it teaches people the guard is wrong.
    #
    # So they are a third state. Not delivered, not undelivered: **not
    # measurable by this probe**, counted and named rather than folded into
    # either answer.
    emitted_normalised = {_normalise_path(k) for k in emitted}
    measurable_parents = {
        _normalise_path(k.rsplit(".", 1)[0]) for k in emitted if "." in k
    }

    unmeasured = [
        f for f in fields if not is_measurable(f, aliases, measurable_parents)
    ]
    fields = [f for f in fields if is_measurable(f, aliases, measurable_parents)]

    # LEAF NAMES COLLIDE, AND A COLLISION IS A FALSE ACQUITTAL.
    #
    # The last hop is checked by looking for the field's leaf name in the
    # rendering surfaces. That was defensible while the walk was flat and
    # `KineticResult`'s own attributes are near-unique. Descending into
    # nested models made `title`, `reason`, `raw`, `status`, `url` and `cid`
    # each belong to several different fields.
    #
    # Caught in the act: wiring `citation.title` to a surface (ADR 0103)
    # made `literature_candidates.title` stop being reported as
    # undelivered -- a completely different field, on a different code
    # path, silently acquitted because the word "title" now appeared.
    #
    # A false ACQUITTAL is worse than the false accusations found last
    # pass. An accusation gets investigated and corrected; an acquittal is
    # the blind spot restored, with the guard's blessing on it.
    #
    # So an ambiguous leaf cannot produce a "delivered" verdict. It is
    # reported as its own state, because the honest answer is that this
    # method cannot tell these two fields apart -- not that the field
    # arrived.
    leaf_owners: dict[str, set[str]] = {}
    for candidate in fields:
        candidate_wire = aliases.get(candidate, candidate)
        leaf_owners.setdefault(candidate_wire.rsplit(".", 1)[-1], set()).add(candidate)
    ambiguous_leaves = {leaf for leaf, owners in leaf_owners.items() if len(owners) > 1}

    surface_blocks = [b for p in SURFACES for b in _blocks(p.read_text())]
    if len(surface_blocks) < 2:
        # One block means the splitter matched nothing and every ambiguity
        # would "resolve" against the whole file -- the file-wide match this
        # replaces, wearing the new name.
        print(
            f"FAIL: the surface splitter produced {len(surface_blocks)} block(s). "
            "Scope-based resolution would be file-wide matching under another "
            "name, so no verdict is trustworthy.",
            file=sys.stderr,
        )
        return 1

    ambiguous: dict[str, str] = {}
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
        if _normalise_path(wire) not in emitted_normalised:
            stops[wire] = "computed by the resolver, never emitted by the runner"
        elif not _mentions(ts_src, leaf):
            stops[wire] = "emitted by the runner, never received by TypeScript"
        elif not _mentions(surface_src, leaf):
            stops[wire] = "received by TypeScript, never reaches a rendering surface"
        elif leaf in ambiguous_leaves and not reaches_surface_in_scope(
            wire, surface_blocks
        ):
            # Reached only when every hop above PASSED -- so this is a
            # would-be "delivered" verdict, downgraded rather than trusted.
            # A stop is never reclassified as ambiguous: a field the surface
            # does not mention at all is undelivered regardless of who else
            # shares its name.
            others = sorted(leaf_owners[leaf] - {field})
            ambiguous[wire] = (
                f"leaf name {leaf!r} is shared with {', '.join(others)}, and no "
                "surface function both names the parent and reads it"
            )

    total = len(fields) + len(unmeasured)
    print(f"Fields on KineticResult:        {total}  "
          f"({top_level} top-level, {total - top_level} nested)")
    print(
        f"Reaching a rendering surface:   {len(fields) - len(stops) - len(ambiguous)}"
    )
    if ambiguous:
        print(f"Verdict not trustworthy:        {len(ambiguous)}  (leaf name shared)")
        print(
            "\n  Every hop passed for these, and the last one rests on a leaf\n"
            "  name several fields answer to. No surface function both names\n"
            "  the parent and reads the leaf as a member, so which field a\n"
            "  mention refers to cannot be decided from the text.\n"
            "\n  These are candidates for being genuinely undelivered -- the\n"
            "  scope check clears a field, it never condemns one -- so each\n"
            "  needs its renderer read by a person before it is called either."
        )
        for wire, why in sorted(ambiguous.items()):
            print(f"    {wire}\n        {why}")
    # Split, because "Stopping short: 12" sitting above "OK" is the same
    # mismatch between a number and a verdict that this guard exists to
    # find. A reader must be able to see at a glance whether anything is
    # unreviewed without reading to the bottom.
    reviewed = sum(1 for f in stops if f in load_baseline())
    print(
        f"Stopping short:                 {len(stops)}"
        + (f"  ({reviewed} reviewed, {len(stops) - reviewed} not)" if stops else "")
    )
    print(f"Not measurable by this probe:   {len(unmeasured)}")
    if unmeasured:
        containers = sorted({f.rsplit('.', 1)[0] for f in unmeasured})
        print(
            "\n  The runner rebuilds these lists rather than forwarding them, so\n"
            "  the probe's populated fixture reaches the container and not its\n"
            "  contents. Reporting them as undelivered would be a false\n"
            "  accusation (ADR 0051/0056); reporting them as delivered would be\n"
            "  the blind spot this descent was written to remove. Neither.\n"
            f"  Containers: {', '.join(containers)}"
        )

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

    # The summary must not be wider than what was measured. "Every computed
    # field" was true of the shallow question and is not true now that 71
    # nested fields are known to exist and known to be unmeasurable here --
    # and a guard whose OK line overclaims is the shape this whole file
    # exists to catch.
    if unmeasured:
        print(
            f"\nOK: all {len(fields)} MEASURABLE fields reach a reader or are recorded "
            f"as internal.\n    {len(unmeasured)} nested field(s) were not measured; "
            "see above. This is not a\n    statement that they are delivered."
        )
    else:
        print(
            "\nOK: every computed field either reaches a reader or is recorded as internal."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
