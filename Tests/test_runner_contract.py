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


def run_main(monkeypatch, fake_resolve, payload):
    monkeypatch.setattr(fallback_logic, "resolve_kinetic_value", fake_resolve)
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setattr(sys, "stdout", stdout)
    science_agent_runner.main()
    return json.loads(stdout.getvalue())


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
        # one the caller ASKED about. None here because this test stubs the
        # resolver and does not stub NCBI -- and None is the honest report
        # of a lookup that did not happen. It is emphatically NOT a default:
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
        "literatureCandidates": [],
        "logs": ["BRENDA exact: 1.1.1.27, Homo sapiens, lactate"],
    }


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
