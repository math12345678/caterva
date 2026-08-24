#!/usr/bin/env python3
"""Guard the wire keys that have no `KineticResult` origin.

READ THIS FIRST: THERE ARE TWO BOUNDARY GUARDS, AND THEY ARE NOT THE SAME
------------------------------------------------------------------------
`check_findings_reach_a_surface.py` (ADR 0045) is the stronger and more
general one, and it is authoritative for anything on `KineticResult`. It
EXECUTES the runner, records key *paths* rather than names, and walks all
three output branches. Prefer it. This file does not duplicate it.

What it cannot see, by construction, is a key the runner emits that is **not
a field of `KineticResult`** -- because its field list comes from
`KineticResult.model_fields`. `reliability` is exactly that: graded inside
the runner, emitted, and never carried on the result.

**That is ADR 0027's defect, the one both guards were written for.** Deleting
`reliability` from `ScienceAgentResult` passes
`check_findings_reach_a_surface.py` cleanly. Verified by replaying it.

So the division is:

    check_findings_reach_a_surface.py   every KineticResult field reaches a
                                        reader (executed, path-aware)
    check_runner_boundary.py (this)     every EMITTED key has a receiver,
                                        including the runner-only ones

Neither is sufficient alone, which is worth stating because two agents built
these independently within an hour and each assumed the other was a
duplicate.

WHY THIS EXISTS
---------------
Six ADRs record the same defect. Every one of them was a field computed
correctly on one side of this boundary and never received on the other, and
every one was invisible because the tests sat on either side of the boundary
and never on the boundary itself.

  ADR 0027  the runner emitted `reliability`; ScienceAgentResult had no
            field for it, so the API server discarded it and recomputed a
            worse copy. A parity test asserted the two implementations
            agreed -- truthfully, and uselessly.
  ADR 0038  `effectors` was nearly declared inside `assayConditions`, where
            it reads naturally and the runner does not emit it. It would
            have type-checked and been `undefined` forever.
  ADR 0039  four pool detectors attached findings to KineticResult and the
            runner emitted none of them. Every detector's own tests passed.
  ADR 0041  an opt-in the route never read, travelling the other way.

The lesson has now been written down five times and re-learned a sixth. A
lesson that needs remembering is not a fix, so this makes it mechanical.

WHAT IT CHECKS
--------------
1. Every field on `KineticResult` has an explicit entry in `EMITTED_AS`.
   A new field with no entry FAILS. That is the point: adding a field forces
   a decision about whether it crosses, rather than letting it default to
   silently not crossing -- which is exactly what happened four times in
   ADR 0039.

2. Every field mapped to a wire key is actually emitted by the runner.
   Catches ADR 0039's shape: computed, attached, never serialised.

3. Every key the runner emits has a receiving field on `ScienceAgentResult`.
   Catches ADR 0027's and ADR 0038's shape: sent, and nothing catches it.

WHAT IT DOES NOT CHECK
----------------------
It compares NAMES, not types or semantics. A field that crosses under the
right name carrying the wrong content passes here, and a wire test is what
catches that. Saying so plainly because the risk of adding a check is that
its existence gets read as an endorsement of whatever survives it.

It also cannot see the second half of ADR 0041 -- an HTTP route that fails
to read a request field -- because that is a different boundary. That one is
covered by `allowVariantsReachesResolver.test.ts`, which posts real bodies.

Usage:
    python3 scripts/check_runner_boundary.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TESTS = REPO_ROOT / "Tests"
RUNNER = (
    REPO_ROOT
    / "Science-Agent-Pipeline/artifacts/api-server/src/lib/science_agent_runner.py"
)
SCIENCE_AGENT_TS = (
    REPO_ROOT / "Science-Agent-Pipeline/artifacts/api-server/src/lib/scienceAgent.ts"
)

sys.path.insert(0, str(TESTS))

#: KineticResult field -> the wire key the runner emits it as, or None with
#: a reason when it deliberately does not cross.
#:
#: `None` is a DECISION, not a default. Each one says why, because "this
#: does not need to cross" is exactly the judgement that was made silently
#: and wrongly four times in ADR 0039.
EMITTED_AS: dict[str, str | None] = {
    # --- the value itself -------------------------------------------------
    "found": "found",
    "value": "*quantity*",  # emitted under km / ki / kcat, chosen at runtime
    "unit": "unit",
    "organism": "organism",
    "source": "source",
    "citation": "citation",
    # --- assay conditions, grouped ---------------------------------------
    "assay_ph": "assayConditions",
    "assay_temperature_c": "assayConditions",
    "assay_buffer": "assayConditions",
    "assay_unreported": "assayConditions",
    # --- policy and provenance -------------------------------------------
    "cross_species_flag": "crossSpecies",
    "cross_species_organisms_available": "crossSpeciesOrganismsAvailable",
    "variant_candidates_available": "variantCandidatesAvailable",
    "variant": "variant",
    # ADR 0092. Crosses as `preparation`, beside `variant`: the same
    # question one category over -- ADR 0029 asks whether the row measured
    # the enzyme's SEQUENCE, this asks whether it measured the FREE enzyme.
    # A tag, a covalent modification and immobilisation are invisible to the
    # variant filter, and the human LDH Ki was resolving to a His-tagged
    # construct with nothing in the response saying so.
    "preparation": "preparation",
    "relatedness": "relatedness",
    "effectors": "effectors",
    "selection_tie": "selectionTie",
    "selected_form": "selectedForm",
    # --- pool-level findings, grouped (ADR 0039) --------------------------
    "effector_contrasts": "poolFindings",
    "form_mixtures": "poolFindings",
    "organism_discrepancies": "poolFindings",
    "source_mixtures": "poolFindings",
    "source_check_unavailable": "poolFindings",
    # --- deliberately internal -------------------------------------------
    "literature_candidates": "literatureCandidates",
    "search_log": "logs",
    # Added 2026-08-24. All three were undeclared, which this guard reports
    # rather than letting them default to "does not cross" -- the exact
    # silence ADR 0039 found four times. Each verdict below was established
    # by reading science_agent_runner.py and the TypeScript that consumes it,
    # not by inferring from the name.
    #
    # Emitted at science_agent_runner.py:825; read in queryResolver.ts as
    # `ScienceAgentResult["ensembleCandidates"]` and by
    # `ensembleCandidateFlags`.
    "ensemble_candidates": "ensembleCandidates",
    # Emitted at science_agent_runner.py:930; read in queryResolver.ts at
    # :436 and used at :567 to tell a "not_found" refusal which substrates
    # the enzyme DOES have rows for.
    "substrates_available": "substratesAvailable",
    # Internal. The runner never serialises it and no TypeScript field
    # receives it -- checked by name across the runner and lib/.
    #
    # It carries the rows behind a cross-species refusal, shaped as
    # `TiedCandidate` so `spread_consequence` can consume them unchanged
    # (ADR 0111). The organisms themselves already cross, as
    # `crossSpeciesOrganismsAvailable`; these are the VALUES, and they feed
    # the ensemble on the Python side rather than travelling to a client.
    #
    # If a client ever needs to draw the cross-species band itself, this
    # becomes a wire key and this comment is the thing to delete.
    "cross_species_candidates": None,
}

#: Wire keys the runner emits that have no KineticResult origin.
#:
#: THESE STILL NEED A RECEIVER. The first version of this file used one list
#: for "no Python-side origin" and treated it as "needs no TypeScript-side
#: receiver" -- two different things, conflated. The consequence was that
#: deleting `reliability` from `ScienceAgentResult`, which is ADR 0027's
#: defect exactly and the reason this guard exists, passed cleanly.
#:
#: Found by replaying the six defects against the guard rather than by
#: reading it. A guard's exemption list is where its own blind spots live,
#: and this one was excusing the case it was written for.
RUNNER_ONLY: dict[str, str] = {
    "km": "the quantity-specific value key; see `value` above",
    "ki": "the quantity-specific value key; see `value` above",
    "kcat": "the quantity-specific value key; see `value` above",
    "vmax": "bridged in the runner from kcat + caller enzyme_conc (ADR 0019)",
    "vmaxValidation": "the bridge's own validation result (ADR 0019)",
    "disease": "epidemiology path, resolved outside KineticResult (ADR 0017)",
    "r0": "epidemiology path (ADR 0017)",
    "infectiousPeriodDays": "epidemiology path (ADR 0017)",
    "beta": "epidemiology bridge (ADR 0020)",
    "gamma": "epidemiology bridge (ADR 0020)",
    "betaGammaValidation": "epidemiology bridge (ADR 0020)",
    "reliability": "graded in the runner from the result, not carried on it",
}

#: The only keys that genuinely need no receiver: the envelope itself.
#: Kept deliberately tiny -- every addition here is a hole in check 3.
NO_RECEIVER_NEEDED: dict[str, str] = {
    "ok": "envelope flag; the TypeScript side branches on it before parsing",
    "error": "error envelope; carried by PythonError, not ScienceAgentResult",
}

_TS_FIELD_RE = re.compile(r"^\s{2}([A-Za-z][A-Za-z0-9_]*)\??:", re.M)
_TS_NESTED_RE = re.compile(r"^\s{4}([A-Za-z][A-Za-z0-9_]*)\??:", re.M)


def kinetic_result_fields() -> set[str]:
    from fallback_logic import KineticResult  # noqa: PLC0415

    return set(KineticResult.model_fields)


def runner_emitted_keys() -> set[str]:
    """Every `"key":` the runner puts in an output dict.

    Deliberately over-inclusive: it reads the whole file rather than one
    branch, because a key emitted on ANY path needs a receiver. A false
    positive here costs a `RUNNER_ONLY` entry with a reason, which is cheap;
    a false negative is the defect this guard exists for.
    """
    text = RUNNER.read_text()
    return set(re.findall(r'"([A-Za-z][A-Za-z0-9_]*)":\s', text))


def science_agent_result_fields() -> set[str]:
    """Fields declared on the TypeScript `ScienceAgentResult`, including the
    nested `assayConditions` members."""
    text = SCIENCE_AGENT_TS.read_text()
    start = text.index("export interface ScienceAgentResult {")
    end = text.index("\n}", start)
    block = text[start:end]
    return set(_TS_FIELD_RE.findall(block)) | set(_TS_NESTED_RE.findall(block))


def main() -> int:
    problems: list[str] = []

    try:
        fields = kinetic_result_fields()
    except Exception as exc:  # noqa: BLE001
        print(f"Could not import KineticResult: {exc}")
        print("This is an environment failure, not a boundary result.")
        return 1

    emitted = runner_emitted_keys()
    received = science_agent_result_fields()

    # 1. Every KineticResult field must have a decision recorded.
    undeclared = sorted(fields - set(EMITTED_AS))
    for name in undeclared:
        problems.append(
            f"`KineticResult.{name}` has no entry in EMITTED_AS, so nothing "
            f"says whether it crosses the boundary. Add one -- either the "
            f"wire key it is emitted as, or None with a reason it stays "
            f"internal. Four fields defaulted to 'does not cross' silently "
            f"in ADR 0039 and none of their tests noticed."
        )

    stale = sorted(set(EMITTED_AS) - fields)
    for name in stale:
        problems.append(
            f"EMITTED_AS names `{name}`, which is not a field of "
            f"KineticResult any more. A stale mapping hides a real gap: the "
            f"count looks complete while a live field goes unchecked."
        )

    # 2. Everything mapped to a wire key must actually be emitted.
    for name, wire in sorted(EMITTED_AS.items()):
        if wire is None or wire.startswith("*") or name not in fields:
            continue
        if wire not in emitted:
            problems.append(
                f"`KineticResult.{name}` is mapped to wire key `{wire}`, "
                f"which the runner never emits. This is ADR 0039's defect: "
                f"computed, attached to the result, and dropped at the "
                f"process boundary."
            )

    # 3. Everything emitted must have a receiver.
    known_wire_keys = set(EMITTED_AS.values()) | set(RUNNER_ONLY)
    for key in sorted(emitted):
        if key in NO_RECEIVER_NEEDED or key in received:
            continue
        # Nested payload keys (inside citation, relatedness, ...) are not
        # top-level wire keys. Only keys this file claims are top-level are
        # checked -- `RUNNER_ONLY` included, because having no Python origin
        # says nothing about whether the receiver needs a field.
        if key not in known_wire_keys:
            continue
        problems.append(
            f"The runner emits `{key}` and `ScienceAgentResult` declares no "
            f"field for it, so it is discarded on arrival. This is ADR "
            f"0027's defect -- a value computed correctly, sent correctly, "
            f"and thrown away by the receiver."
        )

    if problems:
        print("Process-boundary findings:\n")
        for p in problems:
            print(f"  - {p}\n")
        print(
            "The boundary between the Python resolver and the TypeScript API\n"
            "server has now leaked six times (ADR 0027, 0038, 0039, 0041).\n"
            "Every occurrence had passing tests on both sides."
        )
        return 1

    internal = sum(1 for v in EMITTED_AS.values() if v is None)
    print(
        f"OK: {len(fields)} KineticResult field(s) all have a recorded "
        f"boundary decision ({internal} deliberately internal); every mapped "
        f"field is emitted by the runner; every emitted key has a receiver "
        f"on ScienceAgentResult."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
