"""
Stage 5 Part 4: the runner-boundary contract, Python side.

Runs the real science_agent_runner.main() in-process with a golden
KineticResult substituted for the lookup, and pins the exact JSON the
runner emits. Together with the TS-side contract test
(api-server/src/lib/scienceAgent.test.ts) the boundary is pinned from
both directions: a field renamed or dropped on either side fails
immediately, so the value and its citation cannot silently drift apart.
"""

import io
import json
import os
import sys

import pytest

LIB_DIR = os.path.join(
    os.path.dirname(__file__),
    "..",
    "Science-Agent-Pipeline",
    "artifacts",
    "api-server",
    "src",
    "lib",
)
if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

import taxonomy
import enzyme_lookup  # noqa: E402
import fallback_logic  # noqa: E402
import science_agent_runner  # noqa: E402
from citation import Citation  # noqa: E402
from fallback_logic import KineticResult  # noqa: E402



class _AnyReliability:
    """Matches any well-formed reliability block.

    Structural rather than literal: the three grades are the contract and
    are pinned by the shared case file, but the reasons are prose that
    should be improvable without breaking a wire test. What IS asserted
    here is that all three axes are present with a grade and a non-empty
    reason -- an axis that silently vanished would otherwise pass.
    """

    def __eq__(self, other) -> bool:
        if not isinstance(other, dict):
            return False
        for axis in ("assayCompleteness", "conditionProximity", "organismMatch"):
            entry = other.get(axis)
            if not isinstance(entry, dict):
                return False
            if not isinstance(entry.get("grade"), str) or not entry["grade"]:
                return False
            if not isinstance(entry.get("reason"), str) or len(entry["reason"]) < 20:
                return False
        return isinstance(other.get("noAggregateReason"), str)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<any well-formed reliability block>"


ANY_RELIABILITY = _AnyReliability()


def golden_result(cross_species: bool = False) -> KineticResult:
    """The golden G1 record, as the Python layer hands it to the runner."""
    return KineticResult(
        found=True,
        value=10.73,
        unit="mM",
        organism="Sus scrofa" if cross_species else "Homo sapiens",
        source="brenda_cross_species" if cross_species else "brenda_exact",
        citation=Citation(
            source="BRENDA",
            reference_id="740001" if cross_species else "740253",
            url="https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
            organism="Sus scrofa" if cross_species else "Homo sapiens",
            notes=None,
        ),
        cross_species_flag=cross_species,
        search_log=["BRENDA exact: 1.1.1.27, Homo sapiens, lactate"],
    )


def run_main(monkeypatch, fake_resolve, payload, taxon_id=None):
    """Run the real runner with the kinetic lookup stubbed.

    NCBI is stubbed too, and that is not a detail. `taxon_id_for` calls
    `enzyme_lookup.fetch_taxon_id`, which is a live HTTP GET to NCBI
    Taxonomy -- so a test that stubs only the resolver still reaches the
    network, and its result depends on whether the machine can get there.
    Measured: this file's shape assertion PASSED with the network blocked
    and FAILED with it available, because "Homo sapiens" really does
    resolve to 9606. A contract test that green-lights the shape only
    while NCBI is unreachable is not pinning the contract; it is
    reporting the weather.

    `taxon_id` is what the stubbed lookup returns: None for "the lookup
    found nothing", a string for a resolved id. It is a parameter rather
    than a fixed None so the emitted-id path is reachable too -- with a
    hardcoded None, no test in this file could ever see a taxon id
    actually reach the output, and the two keys could stop being emitted
    without anything going red.
    """
    monkeypatch.setattr(fallback_logic, "resolve_kinetic_value", fake_resolve)
    monkeypatch.setattr(enzyme_lookup, "fetch_taxon_id", lambda *a, **k: taxon_id)
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setattr(sys, "stdout", stdout)
    science_agent_runner.main()
    return json.loads(stdout.getvalue())


def test_a_resolved_taxon_reaches_the_output(monkeypatch):
    """The other side of the two taxon keys.

    Every other test here runs with the NCBI lookup returning nothing, so
    the emitted ids are None in all of them. That pins "absent stays
    absent" and nothing else: delete the two assignments in the runner and
    the whole file would still pass. This is the case where the lookup
    succeeds, so a resolved id has to travel from the lookup to the JSON.
    """
    result = run_main(
        monkeypatch,
        lambda *a, **k: golden_result(),
        {"enzymeName": "lactate dehydrogenase", "substrate": "lactate",
         "organism": "Homo sapiens", "ecNumber": "1.1.1.27"},
        taxon_id="9606",
    )
    assert result["taxonId"] == "9606"
    assert result["requestedTaxonId"] == "9606"


def test_golden_found_output_shape(monkeypatch):
    result = run_main(
        monkeypatch,
        lambda *a, **k: golden_result(),
        {"enzymeName": "lactate dehydrogenase", "substrate": "lactate",
         "organism": "Homo sapiens", "ecNumber": "1.1.1.27"},
    )
    assert result == {
        "ok": True,
        "found": True,
        # An empty list means the commentary named no cofactor. Distinct
        # from a clause that WAS found and could not be resolved, which
        # would arrive carrying an identity with status "unresolvable".
        "effectors": [],
        # None means the evidence resolved the choice -- there was one
        # candidate, or every surviving candidate reported the same value.
        # Distinct from a tie with no candidates, which cannot occur.
        "selectionTie": None,
        # Empty because `golden_result()` is built by hand and carries no
        # frontier -- not because a resolution has none. A real resolution
        # attaches every surviving row with its reliability grades, which is
        # what the ensemble samples by (ADR 0137). Asserted explicitly rather
        # than omitted: this contract test exists to fail when the emitted
        # shape changes, and a key left out of the expectation would let the
        # field disappear without anyone noticing.
        "ensembleCandidates": [],
        # None means the returned value is not one of the named forms the
        # pool mixed. That is the good outcome, and it is the outcome in
        # every fixture today -- see ADR 0052, and the corpus test in
        # test_selected_form.py that pins it.
        "selectedForm": None,
        "km": 10.73,
        "unit": "mM",
        "organism": "Homo sapiens",
        # The taxon of the organism the value was MEASURED in, and of the
        # one the caller ASKED about. None here because `run_main` stubs
        # the NCBI lookup to find nothing -- None is the honest report of a
        # lookup that came back empty. The earlier version of this comment
        # said the lookup "did not happen" because the test did not stub
        # NCBI; that was exactly backwards. Not stubbing it meant the
        # lookup DID happen, over the network, and this assertion held only
        # on a machine that could not reach NCBI. See run_main's docstring.
        # It is emphatically NOT a default:
        # `enzyme_lookup.DEFAULT_TAXON_ID` used to turn exactly this
        # situation into a confident "9606" (see
        # Tests/test_no_default_organism.py).
        #
        # Both keys are present-and-null rather than absent, so a consumer
        # never has to tell "the runner is too old to emit this" from "the
        # lookup found nothing".
        "taxonId": None,
        "requestedTaxonId": None,
        # A recombinant His-tagged preparation is not the wild-type enzyme
        # (ADR 0092). Emitted by the runner since 2026-08-17; the contract
        # test was not updated with it, so this shape assertion has been
        # red across two passes.
        #
        # Added here rather than left for its author: the field is settled
        # (ADR written, runner shipped), the omission is mechanical, and a
        # shared suite that stays red stops being a signal. Same reasoning
        # as the twentieth pass applied to `stdpopsim`.
        #
        # None because this golden fixture's commentary names no
        # preparation -- absence of a finding, not a finding of absence.
        "preparation": None,
        "source": "brenda_exact",
        "crossSpecies": False,
        # Relatedness verdicts for every cross-species candidate,
        # including rejected ones (ADR 0024). Empty on an exact match:
        # nothing was compared, so there is nothing to report.
        "relatedness": [],
        # Pool-level findings (ADR 0039). Always present on a found result,
        # empty when the candidate pool held nothing worth saying -- emitted
        # unconditionally so a consumer never has to distinguish "absent"
        # from "empty", and so this exact-equality test keeps failing if the
        # shape changes again.
        "poolFindings": {
            "effectorContrasts": [],
            "formMixtures": [],
            "organismDiscrepancies": [],
            "sourceMixtures": [],
            # "nothing found" vs "nothing checked" (ADR 0039). None when
            # classification worked; a report when every token was
            # unresolvable and the pool was therefore not checked at all.
            "sourceCheckUnavailable": None,
        },
        # Bakker's three axes. Asserted structurally below rather than
        # inline: the reasons are prose and pinning them here would make
        # every wording improvement a contract break, while the GRADES are
        # the contract and are pinned in Tests/reliability_cases.json.
        "reliability": ANY_RELIABILITY,
        "citation": {
            "source": "BRENDA",
            "referenceId": "740253",
            "url": "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
            "title": None,
            "organism": "Homo sapiens",
            "notes": None,
        },
        # STRENDA assay conditions (ADR 0010). This golden KineticResult
        # carries none, so every field crosses as null -- absence is
        # transmitted as absence. The TypeScript side reads that as
        # "incomplete" and degrades the citation to flagged, which is the
        # honest outcome for a value whose conditions were never reported.
        "assayConditions": {
            "ph": None,
            "temperatureC": None,
            "buffer": None,
            # No buffer reported means no lookup was attempted -- distinct
            # from an "unresolvable" identity, which would claim a check ran
            # and failed.
            "bufferIdentity": None,
            "unreported": [],
        },
        # Which protein the winning row measured (ADR 0029). Present on
        # FOUND results, not only withheld ones: `unstated` is the majority
        # case in BRENDA and it is not the same as wild-type.
        "variant": None,
        # The chosen row's commentary, verbatim, and what it says was
        # measured. None because `golden_result()` carries no commentary;
        # the populated case is test_row_scope_crosses_the_boundary.
        "commentary": None,
        "rowScope": None,
        # A row that is evidence against the model's mechanism, for a Ki
        # asked for by mode and model substrate. None here: this is a Km,
        # asked for with neither. The populated case, on the committed LDH
        # page, is test_evidence_against_the_mechanism_crosses_the_boundary.
        "mechanismEvidence": None,
        "literatureCandidates": [],
        "logs": ["BRENDA exact: 1.1.1.27, Homo sapiens, lactate"],
    }


def test_row_scope_crosses_the_boundary(monkeypatch):
    """A row's commentary and its parsed scope must reach the JSON.

    The null golden case cannot tell "transmitted" from "dropped", so this
    carries the gossypol row BRENDA returns for human LDH (ref 711801):
    LDH-B, and no inhibition mode stated.
    """
    row = golden_result()
    row.commentary = ("LDH-B, pH not specified in the publication, "
                      "temperature not specified in the publication")
    result = run_main(
        monkeypatch,
        lambda *a, **k: row,
        {"enzymeName": "lactate dehydrogenase", "substrate": "gossypol",
         "organism": "Homo sapiens", "ecNumber": "1.1.1.27", "quantity": "ki"},
    )
    assert result["commentary"] == row.commentary
    assert result["rowScope"] == {"isoform": "LDH-B", "inhibitionMode": "unstated", "versus": None,
                                  "kitzWilson": False}


def test_a_kitz_wilson_row_says_what_it_is(monkeypatch):
    """BRENDA ref 702238's MAO-B phenylhydrazine row, as the committed page
    (Tests/fixtures/ki_mode/brenda_1.4.3.4.html.gz) serves it. It states no
    mode, and it is not a reversible Ki: the K_I of an irreversible
    inactivation. `inhibitionMode` alone would call it only unstated."""
    row = golden_result()
    row.commentary = ("pH 7.5, MAO-B, determined from Kitz-Wilson plots of the hydrazine "
                      "concentration dependence on rates in enzyme inhibition at 15°C")
    result = run_main(
        monkeypatch,
        lambda *a, **k: row,
        {"enzymeName": "monoamine oxidase", "substrate": "phenylhydrazine",
         "organism": "Homo sapiens", "ecNumber": "1.4.3.4", "quantity": "ki"},
    )
    assert result["rowScope"] == {"isoform": "MAO-B", "inhibitionMode": "unstated",
                                  "versus": None, "kitzWilson": True}


def _ldh_page_resolver():
    """The real resolver, reading the committed, unmodified BRENDA LDH page
    (Tests/fixtures/ki_mode/brenda_1.1.1.27.html.gz, errors="replace" as
    its README says) with UniProt stubbed and no literature search, as
    Tests/test_ki_mode_resolution.py reads it. Built once per test, before
    `run_main` replaces `fallback_logic.resolve_kinetic_value`: built after,
    it would capture the replacement and call itself."""
    import gzip
    from pathlib import Path

    page = gzip.decompress(
        (Path(__file__).parent / "fixtures" / "ki_mode" / "brenda_1.1.1.27.html.gz").read_bytes()
    ).decode("utf-8", errors="replace")
    real = fallback_logic.resolve_kinetic_value

    def resolve(*a, **k):
        return real(*a, **k, html_provider=lambda ec: page,
                    uniprot_provider=lambda ec, organism: None,
                    taxon_id_provider={"Homo sapiens": "9606"}.get,
                    search_literature=False)
    return resolve


QUINOLINE = "3-[7-(2,4-dimethoxypyrimidin-5-yl)-3-sulfamoylquinolin-4-yl]aminobenzoic acid"


def test_evidence_against_the_mechanism_crosses_the_boundary(monkeypatch):
    """BRENDA ref 739793, human LDH and the quinoline sulfonamide, through
    the real resolver and the real runner. A competitive pyruvate model
    carries 0.00059 mM "competitive versus NADH", the only row of its mode;
    the same paper's 0.00252 mM "noncompetitive versus pyruvate" says that
    against pyruvate the inhibitor is not competitive. `caterva compose`
    notes it; this is the same finding, on the wire."""
    payload = {"enzymeName": "lactate dehydrogenase", "organism": "Homo sapiens",
               "ecNumber": "1.1.1.27", "quantity": "ki", "substrate": QUINOLINE,
               "inhibitionMode": "competitive", "modelSubstrate": "pyruvate"}
    resolve = _ldh_page_resolver()
    result = run_main(monkeypatch, resolve, payload)
    assert result["found"] is True and result["ki"] == 0.00059
    assert result["rowScope"]["inhibitionMode"] == "competitive"
    assert result["rowScope"]["versus"] == "NADH"
    assert result["mechanismEvidence"] == {
        "value": 0.00252,
        "unit": "mM",
        "organism": "Homo sapiens",
        "referenceId": "739793",
        "inhibitionMode": "noncompetitive",
        "versus": "pyruvate",
        "conditions": ("pH 7.5, 37°C, recombinant His-tagged enzyme, pyruvate reduction, "
                       "noncompetitive versus pyruvate"),
        "modelMode": "competitive",
        "modelSubstrate": "pyruvate",
    }

    # The noncompetitive model carries the pyruvate row itself: the row of
    # its own mode and substrate, which nothing contradicts.
    result = run_main(monkeypatch, resolve, {**payload, "inhibitionMode": "noncompetitive"})
    assert result["ki"] == 0.00252 and result["mechanismEvidence"] is None


def _hexokinase_page_resolver():
    """`_ldh_page_resolver` for the recorded hexokinase page
    (Tests/fixtures/recorded/brenda_2.7.1.1.html.gz), which holds
    Trypanosoma cruzi's four ADP Ki rows."""
    import gzip
    from pathlib import Path

    page = gzip.decompress(
        (Path(__file__).parent / "fixtures" / "recorded" / "brenda_2.7.1.1.html.gz").read_bytes()
    ).decode("utf-8")
    real = fallback_logic.resolve_kinetic_value

    def resolve(*a, **k):
        return real(*a, **k, html_provider=lambda ec: page,
                    uniprot_provider=lambda ec, organism: None,
                    taxon_id_provider={"Trypanosoma cruzi": "5693"}.get,
                    search_literature=False)
    return resolve


@pytest.mark.parametrize("make_resolver, payload, motif, model_substrate, carried", [
    (_hexokinase_page_resolver,
     {"enzymeName": "hexokinase", "organism": "Trypanosoma cruzi", "ecNumber": "2.7.1.1",
      "quantity": "ki", "substrate": "ADP"},
     ("competitive_inhibition", "competitive"), "glucose", (1.3, "640265")),
    (_ldh_page_resolver,
     {"enzymeName": "lactate dehydrogenase", "organism": "Homo sapiens", "ecNumber": "1.1.1.27",
      "quantity": "ki", "substrate": QUINOLINE},
     ("noncompetitive_inhibition", "noncompetitive"), "pyruvate", (0.00059, "739793")),
])
def test_with_no_mode_the_runner_returns_the_row_compose_any_mode_carries(
        monkeypatch, make_resolver, payload, motif, model_substrate, carried):
    """The parity `caterva compose --any-mode` claims: the API and the
    TypeScript CLI, sending no `inhibitionMode`, get from the runner the row
    compose carries with `--any-mode`, which asks the same resolver for no
    mode with the model's mode to compare (`compare_mode`). Both through the
    real resolver on committed pages; compose's side is the selection its
    command runs (`narrowed.select_for_model`)."""
    from types import SimpleNamespace

    from caterva.agents.adapters import to_parameter_source
    from caterva.compose.narrowed import select_for_model

    resolve = make_resolver()
    motif_name, mode = motif
    answer = resolve(payload["ecNumber"], payload["organism"], payload["substrate"],
                     quantity="ki", compare_mode=mode, model_substrate=model_substrate)
    source, _ = to_parameter_source("reaction_Ki", answer)
    chosen = select_for_model(
        SimpleNamespace(resolutions={"reaction_Ki": SimpleNamespace(source=source)}),
        {"reaction_Ki": (motif_name, "ki")}, substrate=model_substrate, isoform=None,
        any_mode=True)
    composed = chosen.measured["reaction_Ki"]

    result = run_main(monkeypatch, resolve, payload)
    assert result["found"] is True
    assert (result["ki"], result["citation"]["referenceId"]) == carried
    assert (composed.value, composed.commentary) == (result["ki"], result["commentary"])
    assert f"BRENDA ref {carried[1]}" in composed.citation


def test_mode_withheld_output_shape(monkeypatch):
    """A refusal by mode must name what the rows state.

    The rows are BRENDA ref 739793's for human LDH and the quinoline
    sulfonamide, as the resolver refuses them for an uncompetitive model
    (Tests/test_ki_mode_resolution.py, on the committed page)."""
    stated = ["competitive inhibition versus NADH", "noncompetitive inhibition versus pyruvate"]

    def withheld(*a, **k):
        return KineticResult(found=False, source="mode_withheld", modes_available=stated,
                             search_log=["Every candidate row states an inhibition mode other "
                                         "than uncompetitive"])

    result = run_main(
        monkeypatch,
        withheld,
        {"enzymeName": "lactate dehydrogenase", "organism": "Homo sapiens",
         "ecNumber": "1.1.1.27", "quantity": "ki", "inhibitionMode": "uncompetitive",
         "substrate": "3-[7-(2,4-dimethoxypyrimidin-5-yl)-3-sulfamoylquinolin-4-yl]"
                      "aminobenzoic acid", "modelSubstrate": "pyruvate"},
    )
    assert result["found"] is False
    assert result["source"] == "mode_withheld"
    assert result["modesAvailable"] == stated


def test_the_mode_and_the_models_substrate_reach_the_resolver(monkeypatch):
    """Payload -> runner -> resolver, the two new keys. A mode accepted and
    never applied would carry the lower of two mechanisms' constants under a
    model that asked for one."""
    seen = {}

    def spy(*a, **k):
        seen.update(k)
        return KineticResult(found=False, source="not_found", search_log=[])

    base = {"enzymeName": "lactate dehydrogenase", "substrate": "gossypol",
            "organism": "Homo sapiens", "ecNumber": "1.1.1.27", "quantity": "ki"}
    run_main(monkeypatch, spy, {**base, "inhibitionMode": "competitive",
                                "modelSubstrate": "pyruvate"})
    assert (seen["inhibition_mode"], seen["model_substrate"]) == ("competitive", "pyruvate")
    # The inhibitor is still what the Ki is looked up under.
    assert seen["substrate"] == "gossypol"

    seen.clear()
    run_main(monkeypatch, spy, base)
    assert (seen["inhibition_mode"], seen["model_substrate"]) == (None, None)



@pytest.mark.parametrize("key", ["inhibitionMode", "modelSubstrate"])
def test_a_mode_or_substrate_that_is_not_a_string_is_an_error(monkeypatch, key):
    """Read as absent, ["competitive"] would choose the Ki with no mode
    while the caller believes it was chosen by one. The resolver is never
    reached."""
    def unreachable(*a, **k):
        raise AssertionError("the resolver was called")

    payload = {"enzymeName": "lactate dehydrogenase", "substrate": "gossypol",
               "organism": "Homo sapiens", "ecNumber": "1.1.1.27", "quantity": "ki",
               "inhibitionMode": "competitive", key: ["competitive"]}
    monkeypatch.setattr(fallback_logic, "resolve_kinetic_value", unreachable)
    monkeypatch.setattr(enzyme_lookup, "fetch_taxon_id", lambda *a, **k: None)
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setattr(sys, "stdout", stdout)
    with pytest.raises(SystemExit):
        science_agent_runner.main()
    result = json.loads(stdout.getvalue())
    assert result == {"ok": False, "error": f"{key} must be a string; got ['competitive']"}


def test_a_mode_no_model_is_of_is_an_error_not_a_request_dropped(monkeypatch):
    """The real resolver, unstubbed: it refuses the mode before it fetches
    anything, and the runner reports the refusal as an error."""
    monkeypatch.setattr(enzyme_lookup, "fetch_taxon_id", lambda *a, **k: None)
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(
        {"enzymeName": "lactate dehydrogenase", "substrate": "gossypol",
         "organism": "Homo sapiens", "ecNumber": "1.1.1.27", "quantity": "ki",
         "inhibitionMode": "mixed"})))
    monkeypatch.setattr(sys, "stdout", stdout)
    with pytest.raises(SystemExit):
        science_agent_runner.main()
    result = json.loads(stdout.getvalue())
    assert result["ok"] is False
    assert "inhibition_mode must be one of competitive, noncompetitive, uncompetitive" in \
        result["error"]


def test_assay_conditions_cross_the_boundary(monkeypatch):
    """A populated set of conditions must survive the JSON boundary.

    The null-valued golden case above cannot distinguish "transmitted
    correctly" from "dropped and defaulted to null", so it is paired with
    a populated case that can.
    """
    populated = golden_result()
    populated.assay_ph = 8.5
    populated.assay_temperature_c = 25.0
    populated.assay_buffer = "phosphate buffer"
    populated.assay_unreported = []

    # Buffer identity resolution is stubbed. A contract test that reached
    # PubChem would be a live-network test wearing a unit test's name: slow,
    # flaky, and green for reasons unrelated to the boundary it claims to
    # check. The point here is that the field CROSSES, not what it contains.
    import buffer_identity

    monkeypatch.setattr(
        buffer_identity,
        "resolve_identity",
        lambda raw, *a, **k: buffer_identity.BufferIdentity(
            raw=raw, species="phosphate", cid=1061, parent_cid=1061,
            status="resolved",
        ),
    )

    result = run_main(
        monkeypatch,
        lambda *a, **k: populated,
        {"enzymeName": "lactate dehydrogenase", "substrate": "lactate",
         "organism": "Homo sapiens", "ecNumber": "1.1.1.27"},
    )
    assert result["assayConditions"] == {
        "ph": 8.5,
        "temperatureC": 25.0,
        "buffer": "phosphate buffer",
        "bufferIdentity": {
            "raw": "phosphate buffer",
            "species": "phosphate",
            "cid": 1061,
            "parent_cid": 1061,
            "concentration_text": None,
            "status": "resolved",
            "reason": None,
        },
        "unreported": [],
    }
    assert result["variant"] is None


def test_explicitly_unreported_field_crosses_the_boundary(monkeypatch):
    """BRENDA stating "temperature not specified in the publication" is a
    fact about the literature, not a parse failure, and must reach the
    API distinguishable from a silent absence."""
    partial = golden_result()
    partial.assay_ph = 8.0
    partial.assay_temperature_c = None
    partial.assay_unreported = ["temperature"]

    result = run_main(
        monkeypatch,
        lambda *a, **k: partial,
        {"enzymeName": "lactate dehydrogenase", "substrate": "lactate",
         "organism": "Homo sapiens", "ecNumber": "1.1.1.27"},
    )
    assert result["assayConditions"]["ph"] == 8.0
    assert result["assayConditions"]["temperatureC"] is None
    assert result["assayConditions"]["unreported"] == ["temperature"]


def test_cross_species_flag_crosses_the_boundary(monkeypatch):
    result = run_main(
        monkeypatch,
        lambda *a, **k: golden_result(cross_species=True),
        {"enzymeName": "lactate dehydrogenase", "substrate": "lactate",
         "organism": "Mus musculus", "ecNumber": "1.1.1.27"},
    )
    assert result["crossSpecies"] is True
    assert result["source"] == "brenda_cross_species"
    assert result["citation"]["referenceId"] == "740001"
    assert result["organism"] == "Sus scrofa"


def test_ki_quantity_emits_ki_key(monkeypatch):
    """quantity="ki" must flow to the resolver and the value must be
    emitted under the "ki" key (never "km"), so the TypeScript side can
    never mistake a resolved Ki for a Km."""
    captured = {}

    def fake_resolve(enzyme_ec, organism, substrate, enzyme_name=None, **kwargs):
        captured["quantity"] = kwargs.get("quantity")
        result = golden_result()
        result.value = 0.0014
        return result

    result = run_main(
        monkeypatch,
        fake_resolve,
        {"enzymeName": "lactate dehydrogenase", "substrate": "gossypol",
         "organism": "Homo sapiens", "ecNumber": "1.1.1.27", "quantity": "ki"},
    )
    assert captured["quantity"] == "ki"
    assert result["ok"] is True
    assert result["found"] is True
    assert result["ki"] == 0.0014
    assert "km" not in result


def test_quantity_defaults_to_km(monkeypatch):
    """A payload with no quantity keeps the Km contract intact: the value
    is emitted under "km" and the resolver is told quantity="km"."""
    captured = {}

    def fake_resolve(enzyme_ec, organism, substrate, enzyme_name=None, **kwargs):
        captured["quantity"] = kwargs.get("quantity", "km")
        return golden_result()

    result = run_main(
        monkeypatch,
        fake_resolve,
        {"enzymeName": "lactate dehydrogenase", "substrate": "lactate",
         "organism": "Homo sapiens", "ecNumber": "1.1.1.27"},
    )
    assert captured["quantity"] == "km"
    assert result["km"] == 10.73
    assert "ki" not in result


def test_not_found_output_shape(monkeypatch):
    def not_found(*a, **k):
        return KineticResult(
            found=False,
            source="literature_candidates",
            literature_candidates=[
                fallback_logic.LiteratureCandidate(
                    pmid="34962677",
                    title="Some paper",
                    url="https://pubmed.ncbi.nlm.nih.gov/34962677/",
                )
            ],
            search_log=["genuine gap"],
        )

    result = run_main(
        monkeypatch,
        not_found,
        {"enzymeName": "lactate dehydrogenase", "substrate": "x",
         "organism": "Homo sapiens", "ecNumber": "1.1.1.27"},
    )
    assert result == {
        "ok": True,
        "found": False,
        "source": "literature_candidates",
        # Always present on the not-found branch, empty unless the miss was
        # a withheld cross-species value (ADR 0024). Emitted unconditionally
        # so a consumer never has to distinguish "absent" from "empty" --
        # and so this exact-equality assertion keeps failing if the shape
        # changes again, which is how this key got noticed at all.
        "crossSpeciesOrganismsAvailable": [],
        # Always present on the not-found branch, empty unless the miss was
        # a withheld variant (ADR 0029). Emitted unconditionally so a
        # consumer never distinguishes "absent" from "empty".
        "variantCandidatesAvailable": [],
        # The isoforms the rows measured, when an isoform was asked for and
        # none of them is it (source "isoform_withheld"). Empty otherwise.
        "isoformsAvailable": [],
        # What the Ki rows state, when the model's inhibition mode was asked
        # for and every row states another (source "mode_withheld").
        "modesAvailable": [],
        "substratesAvailable": [],
        "relatedness": [],
        "literatureCandidates": [
            {"pmid": "34962677", "title": "Some paper",
             "url": "https://pubmed.ncbi.nlm.nih.gov/34962677/",
             "source": "pubmed", "doi": None}
        ],
        "logs": ["genuine gap"],
    }


def test_core_candidate_output_shape(monkeypatch):
    """A CORE-sourced candidate (fallback_logic.py's open-access search,
    added alongside PubMed -- see ADR 0017) must reach the JSON boundary
    with pmid=null and doi populated -- the exact opposite null pattern
    from a PubMed candidate. If scienceAgent.ts's LiteratureCandidate
    interface (pmid: string | null, doi: string | null) ever drifted from
    this shape, this is the test that would catch it, from the Python
    side of the boundary."""
    def not_found(*a, **k):
        return KineticResult(
            found=False,
            source="literature_candidates",
            literature_candidates=[
                fallback_logic.LiteratureCandidate(
                    title="An open-access CORE result",
                    url="https://core.ac.uk/download/99999999.pdf",
                    source="core",
                    doi="10.1000/core.example",
                )
            ],
            search_log=["genuine gap"],
        )

    result = run_main(
        monkeypatch,
        not_found,
        {"enzymeName": "lactate dehydrogenase", "substrate": "x",
         "organism": "Homo sapiens", "ecNumber": "1.1.1.27"},
    )
    assert result == {
        "ok": True,
        "found": False,
        "source": "literature_candidates",
        # Always present on the not-found branch, empty unless the miss was
        # a withheld cross-species value (ADR 0024). Emitted unconditionally
        # so a consumer never has to distinguish "absent" from "empty" --
        # and so this exact-equality assertion keeps failing if the shape
        # changes again, which is how this key got noticed at all.
        "crossSpeciesOrganismsAvailable": [],
        # Always present on the not-found branch, empty unless the miss was
        # a withheld variant (ADR 0029). Emitted unconditionally so a
        # consumer never distinguishes "absent" from "empty".
        "variantCandidatesAvailable": [],
        # The isoforms the rows measured, when an isoform was asked for and
        # none of them is it (source "isoform_withheld"). Empty otherwise.
        "isoformsAvailable": [],
        # What the Ki rows state, when the model's inhibition mode was asked
        # for and every row states another (source "mode_withheld").
        "modesAvailable": [],
        "substratesAvailable": [],
        "relatedness": [],
        "literatureCandidates": [
            {"pmid": None, "title": "An open-access CORE result",
             "url": "https://core.ac.uk/download/99999999.pdf",
             "source": "core", "doi": "10.1000/core.example"}
        ],
        "logs": ["genuine gap"],
    }


def test_missing_ec_and_name_reports_an_error(monkeypatch):
    """With neither an EC number nor an enzyme name, there is nothing to
    search for -- this must still be a hard error, not a network attempt."""
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"substrate": "x"})))
    monkeypatch.setattr(sys, "stdout", stdout)
    with pytest.raises(SystemExit):
        science_agent_runner.main()
    result = json.loads(stdout.getvalue())
    assert result["ok"] is False
    assert "enzymeName or ecNumber is required" in result["error"]


def test_missing_ec_number_resolves_it_live_via_uniprot(monkeypatch):
    """The behaviour this replaces: previously, any query without an
    explicit EC number was an unrecoverable error, which meant only the
    hardcoded pattern list in enzymes.ts could ever reach a real lookup.
    Now, an enzyme name with no EC number attempts a live UniProt
    name search first (mocked here to stay offline) and, if that
    succeeds, proceeds through the normal BRENDA chain using the
    resolved EC number."""
    import enzyme_lookup

    monkeypatch.setattr(enzyme_lookup, "fetch_taxon_id", lambda organism: "9606")
    monkeypatch.setattr(
        enzyme_lookup,
        "fetch_ec_numbers_by_name",
        lambda name, taxon_id: ["3.2.1.1"] if name == "alpha-amylase" else [],
    )

    result = run_main(
        monkeypatch,
        lambda *a, **k: golden_result(),
        {"enzymeName": "alpha-amylase", "substrate": "starch", "organism": "Homo sapiens"},
    )
    assert result["ok"] is True
    assert result["found"] is True
    assert result["km"] == 10.73
    # The live resolution step's own log line must survive alongside
    # whatever fallback_logic.resolve_kinetic_value itself logged.
    assert any("Resolved EC 3.2.1.1" in line for line in result["logs"])


def test_missing_ec_number_also_resolves_substrate_via_kegg(monkeypatch):
    """A live-resolved enzyme has no substrate name from the (unused)
    enzymes.ts entry, and BRENDA's Km table is dominated by noise without
    one (see enzyme_lookup.py's module docstring). This confirms the
    KEGG substrate lookup actually reaches fallback_logic.resolve_kinetic_value,
    not just that the runner doesn't crash without one."""
    import enzyme_lookup

    monkeypatch.setattr(enzyme_lookup, "fetch_taxon_id", lambda organism: "9606")
    monkeypatch.setattr(
        enzyme_lookup, "fetch_ec_numbers_by_name", lambda name, taxon_id: ["3.2.1.1"]
    )
    monkeypatch.setattr(
        enzyme_lookup,
        "fetch_kegg_enzyme_text",
        lambda ec_number: "SUBSTRATE   starch [CPD:C00369]",
    )

    captured_args = {}

    def fake_resolve(enzyme_ec, organism, substrate, enzyme_name=None, **kwargs):
        captured_args["substrate"] = substrate
        captured_args["enzyme_ec"] = enzyme_ec
        captured_args["quantity"] = kwargs.get("quantity", "km")
        return golden_result()

    result = run_main(
        monkeypatch,
        fake_resolve,
        {"enzymeName": "alpha-amylase", "organism": "Homo sapiens"},
    )
    assert result["ok"] is True
    assert captured_args["substrate"] == "starch"
    assert captured_args["enzyme_ec"] == "3.2.1.1"
    assert any(
        "Resolved substrate 'starch'" in line for line in result["logs"]
    )


def test_missing_ec_number_exhausted_uniprot_lookup_reports_not_found(monkeypatch):
    """When UniProt has nothing indexed under the given name, this must be
    an honest 'not found' -- never a fabricated EC number or Km, and never
    a crash."""
    import enzyme_lookup

    monkeypatch.setattr(enzyme_lookup, "fetch_taxon_id", lambda organism: None)
    monkeypatch.setattr(
        enzyme_lookup, "fetch_ec_numbers_by_name", lambda name, taxon_id: []
    )

    stdout = io.StringIO()
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(json.dumps({"enzymeName": "not a real enzyme name"})),
    )
    monkeypatch.setattr(sys, "stdout", stdout)
    science_agent_runner.main()
    result = json.loads(stdout.getvalue())
    assert result == {
        "ok": True,
        "found": False,
        "source": "ec_not_resolved",
        "literatureCandidates": [],
        "logs": [
            ("Could not resolve an EC number for 'not a real enzyme name' via "
             "UniProt; no BRENDA/KEGG/PubMed lookup is possible without one.")
        ],
    }


def test_cross_species_withheld_output_shape(monkeypatch):
    """The withheld shape must cross the JSON boundary intact.

    This is the only test on the Python side that checks the *wire*, and it
    matters more than the resolver tests do: the resolver can be perfectly
    correct while the runner drops `cross_species_organisms_available` on
    the floor, and the result would be a refusal that names nothing --
    which is exactly the failure ADR 0024's opt-in is supposed to avoid.
    The refusal would still look right in every log.
    """
    def withheld(*a, **k):
        return KineticResult(
            found=False,
            source="cross_species_withheld",
            cross_species_organisms_available=["Oryctolagus cuniculus", "Sus scrofa"],
            search_log=["Cross-species value(s) found in Oryctolagus cuniculus, "
                        "Sus scrofa but withheld: allow_cross_species=False"],
        )

    result = run_main(
        monkeypatch,
        withheld,
        {"enzymeName": "lactate dehydrogenase", "substrate": "lactate",
         "organism": "Mus musculus", "ecNumber": "1.1.1.27"},
    )
    assert result == {
        "ok": True,
        "found": False,
        "source": "cross_species_withheld",
        "crossSpeciesOrganismsAvailable": ["Oryctolagus cuniculus", "Sus scrofa"],
        # Always present on the not-found branch, empty unless the miss was
        # a withheld variant (ADR 0029). Emitted unconditionally so a
        # consumer never distinguishes "absent" from "empty".
        "variantCandidatesAvailable": [],
        # The isoforms the rows measured, when an isoform was asked for and
        # none of them is it (source "isoform_withheld"). Empty otherwise.
        "isoformsAvailable": [],
        # What the Ki rows state, when the model's inhibition mode was asked
        # for and every row states another (source "mode_withheld").
        "modesAvailable": [],
        "substratesAvailable": [],
        # Empty here because the opt-in was never given, so no relatedness
        # check ran. Populated on the too_distant path, where it carries the
        # reason each candidate was rejected.
        "relatedness": [],
        "literatureCandidates": [],
        "logs": ["Cross-species value(s) found in Oryctolagus cuniculus, "
                 "Sus scrofa but withheld: allow_cross_species=False"],
    }


def test_allow_cross_species_reaches_the_resolver(monkeypatch):
    """The opt-in has to survive the payload -> runner -> resolver hop.

    Without this, `allowCrossSpecies: true` could be accepted by the API,
    logged as accepted, and silently never applied -- a switch that does
    nothing is worse than no switch, because the user believes they made a
    choice.
    """
    seen = {}

    def spy(*a, **k):
        seen.update(k)
        return KineticResult(found=False, source="not_found", search_log=[])

    base = {"enzymeName": "lactate dehydrogenase", "substrate": "lactate",
            "organism": "Mus musculus", "ecNumber": "1.1.1.27"}

    run_main(monkeypatch, spy, {**base, "allowCrossSpecies": True})
    assert seen.get("allow_cross_species") is True

    seen.clear()
    run_main(monkeypatch, spy, base)
    assert seen.get("allow_cross_species") is False, (
        "absent flag must read as False; a permissive default is how the "
        "automatic fallback would come back"
    )

    seen.clear()
    run_main(monkeypatch, spy, {**base, "allowCrossSpecies": "yes"})
    assert seen.get("allow_cross_species") is False, (
        "a truthy non-boolean must not enable cross-species"
    )


def test_cross_species_too_distant_output_shape(monkeypatch):
    """The opt-in was given and the relatedness check still refused.

    This is the shape that must NOT read like the withheld one. A user who
    ticked the box and gets an identical-looking wall back has no way to
    tell that their action was registered at all, and the natural
    conclusion is that the flag does nothing.
    """
    verdict = taxonomy.Relatedness(
        status="too_distant",
        shared_rank="domain",
        shared_name="Eukaryota",
        query_organism="Mus musculus",
        candidate_organism="Plasmodium falciparum",
        reason="diverge above the class level",
    )

    def too_distant(*a, **k):
        return KineticResult(
            found=False,
            source="cross_species_too_distant",
            cross_species_organisms_available=["Plasmodium falciparum"],
            relatedness=[verdict],
            search_log=["every cross-species candidate failed"],
        )

    result = run_main(
        monkeypatch,
        too_distant,
        {"enzymeName": "lactate dehydrogenase", "substrate": "gossypol",
         "organism": "Mus musculus", "ecNumber": "1.1.1.27",
         "allowCrossSpecies": True},
    )
    assert result["source"] == "cross_species_too_distant"
    assert result["crossSpeciesOrganismsAvailable"] == ["Plasmodium falciparum"]

    # The REASON must survive the wire. Without it the client can say a
    # candidate was rejected but not why, and "why" is the only part a
    # student learns anything from.
    assert len(result["relatedness"]) == 1
    crossed = result["relatedness"][0]
    assert crossed["status"] == "too_distant"
    assert crossed["candidate_organism"] == "Plasmodium falciparum"
    assert crossed["shared_name"] == "Eukaryota"
    assert "class level" in crossed["reason"]


def test_variant_withheld_output_shape(monkeypatch):
    """The withheld shape must cross the JSON boundary intact.

    Same argument as the cross-species version: the resolver can be
    perfectly correct while the runner drops `variant_candidates_available`
    on the floor, producing a refusal that names nothing. The refusal would
    still look right in every log.
    """
    def withheld(*a, **k):
        return KineticResult(
            found=False,
            source="variant_withheld",
            variant_candidates_available=["Y124C", "isozyme H4"],
            search_log=["All 2 candidate row(s) measured a protein variant "
                        "(Y124C, isozyme H4); withheld: allow_variants=False"],
        )

    result = run_main(
        monkeypatch,
        withheld,
        {"enzymeName": "acetylcholinesterase", "substrate": "acetylthiocholine",
         "organism": "Mus musculus", "ecNumber": "3.1.1.7"},
    )
    assert result["found"] is False
    assert result["source"] == "variant_withheld"
    assert result["variantCandidatesAvailable"] == ["Y124C", "isozyme H4"]


def test_allow_variants_reaches_the_resolver(monkeypatch):
    """The opt-in has to survive payload -> runner -> resolver.

    A switch that is accepted, logged, and never applied is worse than no
    switch, because the user believes they made a choice.
    """
    seen = {}

    def spy(*a, **k):
        seen.update(k)
        return KineticResult(found=False, source="not_found", search_log=[])

    base = {"enzymeName": "acetylcholinesterase", "substrate": "acetylthiocholine",
            "organism": "Mus musculus", "ecNumber": "3.1.1.7"}

    run_main(monkeypatch, spy, {**base, "allowVariants": True})
    assert seen.get("allow_variants") is True

    seen.clear()
    run_main(monkeypatch, spy, base)
    assert seen.get("allow_variants") is False, (
        "absent flag must read as False; a permissive default is how the old "
        "behaviour returns silently"
    )

    seen.clear()
    run_main(monkeypatch, spy, {**base, "allowVariants": "yes"})
    assert seen.get("allow_variants") is False, (
        "a truthy non-boolean must not enable variants"
    )


def test_effectors_cross_the_boundary_with_presence_intact(monkeypatch):
    """The presence flag is the field that must survive.

    Two rows naming the same compound with opposite presence are the case
    ADR 0032 exists for. If `presence` were dropped in transit, the
    TypeScript side would compare two identical compounds and report
    agreement -- a confident wrong answer produced by a serialisation bug,
    with the resolver's judgement entirely correct upstream of it.
    """
    import effector as effector_module

    populated = golden_result()
    populated.effectors = [
        effector_module.Effector(
            raw="in absence of fructose 1,6-bisphosphate",
            compound_text="fructose 1,6-bisphosphate",
            presence="absent",
        )
    ]

    # Stubbed: a contract test that reached PubChem would be a live-network
    # test wearing a unit test's name.
    monkeypatch.setattr(
        effector_module,
        "resolve_effectors",
        lambda effs, *a, **k: effs,
    )

    result = run_main(
        monkeypatch,
        lambda *a, **k: populated,
        {"enzymeName": "lactate dehydrogenase", "substrate": "lactate",
         "organism": "Homo sapiens", "ecNumber": "1.1.1.27"},
    )

    assert len(result["effectors"]) == 1
    crossed = result["effectors"][0]
    assert crossed["presence"] == "absent"
    assert crossed["compound_text"] == "fructose 1,6-bisphosphate"
    # The raw clause travels too, so a reader can disagree with the parse.
    assert crossed["raw"] == "in absence of fructose 1,6-bisphosphate"


def test_pool_findings_cross_the_boundary_populated(monkeypatch):
    """A populated pool finding must survive the JSON boundary.

    The empty-shape case above cannot distinguish "transmitted correctly"
    from "dropped and defaulted to empty" -- which is precisely the failure
    that hid four detectors for four ADRs. So it is paired with a populated
    case that can.
    """
    from effector_presence import EffectorContrast
    from form_mixture import FormMixture
    from source_context import OrganismDiscrepancy, SourceMixture

    populated = golden_result()
    populated.effector_contrasts = [
        EffectorContrast(
            compound="fructose 1,6-bisphosphate",
            present_values=[21.1],
            absent_values=[327.2],
            reason="both arms present in the pool",
        )
    ]
    populated.form_mixtures = [
        FormMixture(base="LDH", values_by_form={"B": [142.0], "1": [1500.0]},
                    reason="two forms in the pool")
    ]
    populated.organism_discrepancies = [
        OrganismDiscrepancy(
            value=6670.0, column_organism="Drosophila melanogaster",
            commentary_organism="human", column_taxon="7227",
            commentary_taxon="9606", reason="the column and the commentary disagree",
        )
    ]
    populated.source_mixtures = [
        SourceMixture(organism="Gallus gallus",
                      values_by_source={"heart": [60.0], "muscle": [1.1]},
                      reason="two sources in one species")
    ]

    result = run_main(
        monkeypatch,
        lambda *a, **k: populated,
        {"enzymeName": "lactate dehydrogenase", "substrate": "lactate",
         "organism": "Homo sapiens", "ecNumber": "1.1.1.27"},
    )
    findings = result["poolFindings"]

    assert findings["effectorContrasts"][0]["compound"] == "fructose 1,6-bisphosphate"
    assert findings["effectorContrasts"][0]["present_values"] == [21.1]
    assert findings["formMixtures"][0]["base"] == "LDH"
    assert findings["organismDiscrepancies"][0]["commentary_organism"] == "human"
    assert findings["organismDiscrepancies"][0]["column_organism"] == "Drosophila melanogaster"
    assert findings["sourceMixtures"][0]["organism"] == "Gallus gallus"
    # The reasons are the deliverable -- a finding without its sentence is a
    # field a client has to invent prose for.
    #
    # `sourceCheckUnavailable` is a dict-or-None rather than a list, so the
    # groups are iterated by kind. Writing this as `for group in
    # findings.values()` broke the moment that key was added, which is the
    # contract test earning its place a second time in one pass.
    for key in (
        "effectorContrasts", "formMixtures",
        "organismDiscrepancies", "sourceMixtures",
    ):
        for item in findings[key]:
            assert item["reason"], key
    assert "sourceCheckUnavailable" in findings


def test_an_ambiguous_enzyme_name_is_refused_and_the_candidates_named(monkeypatch):
    """The third outcome, which used to be silently folded into the first.

    `resolve_ec_number` took `candidates[0]` and said nothing. EC 1.1.1.27
    is L-lactate dehydrogenase and EC 1.1.1.28 is D-lactate dehydrogenase —
    different proteins on different stereoisomers, one common name, and
    that name is the example in this project's own CLI help.

    An EC number is not a parameter; it is the identity of the protein
    every citation downstream refers to. Picking one silently produces a
    correctly formatted reference to the wrong enzyme (ADR 0126).

    This must NOT be reported as `ec_not_resolved`: UniProt resolved it
    fine, to more than one thing. Saying "could not resolve" would deny the
    existence of the answer instead of asking which one was meant, which is
    a worse message than the silent pick it replaces.
    """
    import enzyme_lookup

    monkeypatch.setattr(enzyme_lookup, "fetch_taxon_id", lambda organism: None)
    monkeypatch.setattr(
        enzyme_lookup,
        "fetch_ec_numbers_by_name",
        lambda name, taxon_id: ["1.1.1.27", "1.1.1.28"],
    )

    stdout = io.StringIO()
    monkeypatch.setattr(
        sys, "stdin", io.StringIO(json.dumps({"enzymeName": "lactate dehydrogenase"}))
    )
    monkeypatch.setattr(sys, "stdout", stdout)
    science_agent_runner.main()
    result = json.loads(stdout.getvalue())

    assert result["ok"] is True
    assert result["found"] is False
    assert result["source"] == "ec_ambiguous", (
        "an ambiguity reported as ec_not_resolved denies the answer exists"
    )
    assert result["ecCandidates"] == ["1.1.1.27", "1.1.1.28"]

    logs = " ".join(result["logs"])
    assert "1.1.1.27" in logs and "1.1.1.28" in logs, (
        "a refusal that cannot name what it refused leaves the choice "
        "unexercisable"
    )
    assert "citation for the wrong enzyme" in logs


def test_one_candidate_is_not_an_ambiguity(monkeypatch):
    """The common case must stay silent, or the refusal is worthless.

    Most enzyme names map to exactly one EC number, and a tool that asked
    for confirmation every time would be ignored by the second query
    (ADR 0028).
    """
    import enzyme_lookup

    monkeypatch.setattr(enzyme_lookup, "fetch_taxon_id", lambda organism: None)
    monkeypatch.setattr(
        enzyme_lookup, "fetch_ec_numbers_by_name", lambda name, taxon_id: ["3.2.1.1"]
    )

    stdout = io.StringIO()
    monkeypatch.setattr(
        sys, "stdin", io.StringIO(json.dumps({"enzymeName": "alpha-amylase"}))
    )
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(
        science_agent_runner, "resolve_substrate_from_kegg", lambda ec: None
    )
    monkeypatch.setattr(
        fallback_logic, "resolve_kinetic_value", lambda *a, **k: golden_result()
    )
    science_agent_runner.main()
    result = json.loads(stdout.getvalue())

    assert result.get("source") != "ec_ambiguous"
