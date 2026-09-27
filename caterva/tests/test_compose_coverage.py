"""What the composer covers of the twenty questions, measured.

WHY THIS FILE EXISTS
--------------------
`frontDoorCoverage.test.ts` measures the catalogue against twenty questions a
teaching lab actually types, and records 3/20. That number is the reason the
composer was written. Until this file there was no committed way to reproduce
the composer's own half of the answer, so "it builds eleven" was a claim in a
commit message -- exactly the kind of unverifiable number this project exists
to refuse.

The twenty queries are the same twenty, copied deliberately rather than
imported: the TypeScript harness is in another package and another language,
and a Python test that could only run with a node toolchain present would be
skipped on the machines that most need it. `test_the_twenty_queries_match_the`
`_typescript_harness` reads the .ts file and fails if the two drift apart, so
the copy cannot rot silently.

WHAT IS AND IS NOT CLAIMED
--------------------------
That the composer BUILDS a mechanism, not that the mechanism is right for the
asker's system, and not that it is parameterised. Every model built here is
`structure_only`: no enzyme was named, so nothing was looked up, and the
constants are the motif library's illustrative values. A built model with
placeholder constants answers "what can this mechanism do", which is a real
question and a different one from "what does this enzyme do".

No threshold is asserted on the count, for the same reason the TypeScript
harness asserts none: a pass/fail bar turns a measurement into a target and
invites tuning the harness until it passes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from caterva.compose.grammar import UnrecognisedShape
from caterva.compose.pipeline import compose

#: The same twenty questions `frontDoorCoverage.test.ts` measures the
#: catalogue against. Ten are squarely in the catalogue; ten are real biology
#: it does not contain.
QUERIES = (
    "michaelis menten kinetics for hexokinase",
    "enzyme kinetics with a competitive inhibitor",
    "SIR model of a measles outbreak in a school",
    "SEIR epidemic with an exposed class",
    "genetic drift in a small population",
    "predator prey population cycles",
    "stochastic simulation of a chemical reaction",
    "PCR amplification over 30 cycles",
    "repressilator oscillations",
    "cell cycle oscillator dynamics",
    "three step phosphorylation cascade",
    "glycolysis in yeast",
    "a MAP kinase cascade with negative feedback",
    "reversible binding of a ligand to a receptor",
    "substrate inhibition at high substrate concentration",
    "two enzymes competing for the same substrate",
    "a toggle switch between two repressors",
    "sequential feedback inhibition in amino acid synthesis",
    "an open system with constant substrate inflow",
    "allosteric activation of an enzyme by its product",
)

#: Where the TypeScript harness keeps its copy, for the drift check.
_TS_HARNESS = (
    Path(__file__).resolve().parents[2]
    / "Science-Agent-Pipeline/artifacts/api-server/src/__tests__"
    / "frontDoorCoverage.test.ts"
)

#: The eight the composer does not build, and why each is correct.
#:
#: "michaelis menten kinetics for hexokinase" left this list on 2026-09-24,
#: when plain Michaelis-Menten got a rule: it is one reaction motif, not a
#: catalogue domain, and the command line (which has no catalogue) was
#: refusing it. On the web the catalogue still answers it first.
#:
#: Seven are the catalogue's OWN domains -- an epidemic, genetic drift, a
#: Gillespie run, PCR. Those are not compositions of reaction motifs and the
#: composer has no business claiming them; the catalogue answers them or
#: nothing does. The ninth is glycolysis, refused because a named pathway
#: needs a pathway database (ADR 0173): a plausible wrong glycolysis is worse
#: than a refusal that names KEGG.
EXPECTED_REFUSALS = {
    "SIR model of a measles outbreak in a school": "catalogue domain",
    "SEIR epidemic with an exposed class": "catalogue domain",
    "genetic drift in a small population": "catalogue domain",
    "predator prey population cycles": "catalogue domain",
    "stochastic simulation of a chemical reaction": "catalogue domain",
    "PCR amplification over 30 cycles": "catalogue domain",
    "cell cycle oscillator dynamics": "catalogue domain",
    "glycolysis in yeast": "a named pathway, which needs a pathway database",
}


def _attempt(query: str):
    try:
        return compose(query)
    except UnrecognisedShape:
        return None


@pytest.fixture(scope="module")
def outcomes():
    return {query: _attempt(query) for query in QUERIES}


class TestCoverage:
    def test_the_composer_builds_every_query_it_should(self, outcomes) -> None:
        built = {q for q, model in outcomes.items() if model is not None}
        expected = set(QUERIES) - set(EXPECTED_REFUSALS)
        assert built == expected

    def test_it_refuses_the_catalogue_s_own_domains(self, outcomes) -> None:
        """Not a gap. A composer that answered "SIR model of a measles
        outbreak" by assembling reaction motifs would be inventing an
        epidemiological model out of chemistry, and the confident wrong
        answer is worse than the refusal.
        """
        for query, why in EXPECTED_REFUSALS.items():
            assert outcomes[query] is None, f"{query} ({why})"

    def test_every_built_model_is_structure_only(self, outcomes) -> None:
        # Nothing was searched for, because no enzyme was named. A built
        # model here answers "what can this mechanism do", never "what does
        # this enzyme do".
        built = [m for m in outcomes.values() if m is not None]
        assert built
        for model in built:
            assert model.structure_only
            assert model.resolvable, "a model with nothing to resolve is suspect"

    def test_the_count_is_reported(self, outcomes, tmp_path) -> None:
        """The report is the point, as in the TypeScript harness.

        Written to a file as well as returned, because the one number this
        file exists to produce should be readable without scrolling a test
        log.
        """
        rows = []
        built = 0
        for query in QUERIES:
            model = outcomes[query]
            if model is not None:
                built += 1
                rows.append(
                    f"BUILT    {query[:48]:50s} -> {model.recognition.rule}"
                )
            else:
                rows.append(
                    f"REFUSED  {query[:48]:50s} -> "
                    f"{EXPECTED_REFUSALS.get(query, 'unexpected')}"
                )

        report = "\n".join([
            "",
            "COMPOSER COVERAGE (no LLM, no key, no network)",
            "=" * 78,
            *rows,
            "=" * 78,
            f"built {built}/{len(QUERIES)}",
            "",
        ])
        (tmp_path / "composer-coverage.txt").write_text(report)
        print(report)

        # No threshold asserted, for the same reason the TypeScript harness
        # asserts none: a bar turns a measurement into a target.
        assert len(QUERIES) == 20


class TestTheHarnessCannotDriftFromTheTypescriptOne:
    """Two copies of twenty strings, in two languages, is a rot risk.

    If someone adds a twenty-first query over there and not here, this
    file's number stops being about the same question and silently starts
    being about a different one.
    """

    def test_the_typescript_harness_holds_the_same_queries(self) -> None:
        if not _TS_HARNESS.exists():  # pragma: no cover - split checkout
            pytest.skip(f"{_TS_HARNESS} is not in this checkout")

        source = _TS_HARNESS.read_text()
        found = set(re.findall(r'\{ query: "([^"]+)"', source))
        assert found == set(QUERIES), (
            "the two harnesses have drifted: "
            f"only in TypeScript {sorted(found - set(QUERIES))}, "
            f"only here {sorted(set(QUERIES) - found)}"
        )

    def test_the_typescript_harness_still_holds_exactly_twenty(self) -> None:
        # A drift check that passed on an empty parse would be worthless --
        # a renamed field would make `found` empty and the set comparison
        # above would fail loudly, but only if this file's own count is
        # also pinned.
        if not _TS_HARNESS.exists():  # pragma: no cover - split checkout
            pytest.skip(f"{_TS_HARNESS} is not in this checkout")

        source = _TS_HARNESS.read_text()
        assert len(re.findall(r'\{ query: "([^"]+)"', source)) == 20
