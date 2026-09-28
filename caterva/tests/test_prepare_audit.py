"""`caterva prepare`: the audit finds what a setup would silently get wrong.

Fixtures are real entries, trimmed (atom records for the chains the tests
read; every other category intact) and gzipped:

  1I10  human LDH-A, 8 chains. Chain D's catalytic Arg105 is truncated at
        CB; chain G's is not modelled at all, inside a disordered stretch
        of the active-site loop; chain A is complete.
  1L63  T4 lysozyme "pseudo-wild-type", C54T/C97A. The depositors label
        both substitutions 'conflict', not 'engineered mutation' -- which
        is exactly why the audit must not filter on the label.
"""
from __future__ import annotations

import gzip
import json
import pathlib

import pytest

from caterva.prepare import __main__ as cli
from caterva.prepare.align import BLOSUM62, align
from caterva.prepare.audit import MIN_TRANSFER_IDENTITY, audit, choose_reference, load_mcsa
from caterva.prepare.cif import parse

FIX = pathlib.Path(__file__).parent / "fixtures" / "prepare"


def cif(pid: str) -> str:
    with gzip.open(FIX / f"{pid}.trimmed.cif.gz", "rt") as fh:
        return fh.read()


def sequence_of(acc: str) -> str:
    text = (FIX / f"{acc}.fasta").read_text()
    return "".join(l.strip() for l in text.splitlines() if not l.startswith(">"))


@pytest.fixture(scope="module")
def ldh():
    return audit(cif("1I10"), sequence_of)


@pytest.fixture(scope="module")
def t4l():
    return audit(cif("1L63"), sequence_of)


# --- the reader ---------------------------------------------------------------

def test_reader_handles_the_three_quoting_forms_and_both_shapes():
    text = """data_x
_entry.id 1ABC
_struct.title 'a title with spaces'
loop_
_thing.a
_thing.b
1 "two words"
3 plain
_note.text
;first line
second line
;
"""
    c = parse(text)
    assert c["entry"][0]["id"] == "1ABC"
    assert c["struct"][0]["title"] == "a title with spaces"
    assert c["thing"] == [{"a": "1", "b": "two words"}, {"a": "3", "b": "plain"}]
    assert c["note"][0]["text"] == "first line\nsecond line"


def test_an_apostrophe_inside_a_quoted_value_does_not_end_it():
    c = parse("data_x\n_a.b 'O'Neil lab'\n")
    assert c["a"][0]["b"] == "O'Neil lab"


# --- the alignment ------------------------------------------------------------

def test_blosum62_is_symmetric_and_has_the_textbook_diagonal():
    assert all(BLOSUM62[(a, b)] == BLOSUM62[(b, a)] for a, b in BLOSUM62)
    assert BLOSUM62[("W", "W")] == 11 and BLOSUM62[("C", "C")] == 9 and BLOSUM62[("A", "A")] == 4


def test_an_insertion_shifts_the_mapping_rather_than_mismatching_through_it():
    ref = "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQ"
    target = ref[:10] + "GGGG" + ref[10:]
    a = align(ref, target)
    assert a.target_of(5) == 5
    assert a.target_of(11) == 15  # every residue after the insertion moves by 4
    assert a.identity == 1.0


def test_the_dogfish_catalytic_histidine_lands_on_the_human_one():
    # M-CSA's LDH reference is dogfish (P00341) His194. Human LDH-A's is
    # His193 in UniProt numbering; 1I10 omits Met1, so it is 192 there.
    raw = parse(cif("1I10"))["entity_poly"][0]["pdbx_seq_one_letter_code_can"]
    human = "".join(raw.split())
    a = align(sequence_of("P00341"), human)
    assert a.target_of(194) == 192 and human[191] == "H"
    assert a.identity > 0.75


# --- choosing the M-CSA mechanism ---------------------------------------------

def test_the_snapshot_is_the_cited_source():
    snap = load_mcsa()
    assert "10.1093/nar/gkx1012" in snap["source"]
    assert len(snap["entries"]) > 900
    for e in snap["entries"]:
        assert e["uniprot"] and all(isinstance(r["resid"], int) for r in e["residues"])


def test_same_accession_wins_outright(t4l):
    assert t4l.reference.mcsa_id == 921
    assert t4l.reference.how == "same UniProt accession"


def test_without_an_accession_every_mechanism_for_the_ec_is_tried_and_the_losers_named():
    # EC 3.2.1.17 is three unrelated lysozyme families in M-CSA. Chosen by
    # alignment alone, T4 lysozyme must pick its own family and name the
    # other two rather than silently dropping them.
    t4 = sequence_of("P00720")
    unrelated = "KVFERCELARTLKRLGMDGYRGISLANWMCLAKWESGYNTRATNYNAGDRSTDYGIFQINSRYWCNDGKTPGAVNACHLSCSALLQDNIADAVACAKRVVRDPQGIRAWVAWRNRCQNRDVRQYVQGCGV"

    def seq_of(acc: str) -> str:
        return t4 if acc == "P00720" else unrelated

    entry, ref, _, why = choose_reference([], "3.2.1.17", t4, seq_of, load_mcsa())
    assert entry is not None and entry["mcsa_id"] == 921, why
    assert ref.how.startswith("best of 3")
    assert {mid for mid, _, _ in ref.rejected} == {203, 774}


def test_a_twilight_zone_alignment_transfers_nothing():
    entry, ref, _, why = choose_reference([], "1.1.1.27", "GS" * 150,
                                          lambda acc: sequence_of("P00341"), load_mcsa())
    assert entry is None and ref is None
    assert f"{MIN_TRANSFER_IDENTITY:.0%}" in why


# --- 1L63: mutations the label would hide ---------------------------------------

def test_substitutions_labelled_conflict_are_still_blocking(t4l):
    subs = [f for f in t4l.findings if f.check == "sequence differs from UniProt"]
    assert sorted(f.residues[0] for f in subs) == ["54", "97"]
    assert all(f.severity == "blocks" and "'conflict'" in f.what for f in subs)


def test_the_only_chain_is_not_clean(t4l):
    assert [s.blocks for s in t4l.chain_summary] == [2]


def test_catalytic_residues_are_found_and_placed(t4l):
    assert {(c.expected, c.auth_seq_id) for c in t4l.catalytic} == {("GLU", "11"), ("ASP", "20")}
    for f in t4l.findings:
        if f.check == "sequence differs from UniProt":
            assert f.distance is not None and f.distance > 5


# --- 1I10: the active-site loop -------------------------------------------------

def test_catalytic_residues_are_mapped_onto_every_chain(ldh):
    his = {c.chain: c for c in ldh.catalytic if c.expected == "HIS"}
    assert set(his) >= {"A", "D", "G"}
    assert all(c.auth_seq_id == "192" and c.found == "HIS" for c in his.values())


def test_a_truncated_catalytic_side_chain_blocks_and_says_so(ldh):
    f = next(f for f in ldh.findings if f.chain == "D" and f.residues == ["105"])
    assert f.severity == "blocks" and f.catalytic and f.distance == 0.0
    assert f.what.startswith("CATALYTIC RESIDUE Arg105")


def test_a_catalytic_residue_inside_a_gap_puts_the_gap_on_the_active_site(ldh):
    gap = next(f for f in ldh.findings if f.chain == "G" and f.check == "unmodelled residues")
    assert gap.residues == ["101-106"] and gap.distance == 0.0 and gap.catalytic
    assert any(f.chain == "G" and f.check == "catalytic residue" for f in ldh.findings)


def test_the_chain_summary_says_where_to_start(ldh):
    s = {c.chain: c for c in ldh.chain_summary}
    assert s["A"].blocks == 0 and s["A"].catalytic_intact
    assert not s["D"].catalytic_intact and not s["G"].catalytic_intact


def test_the_assembly_is_a_decision_not_a_default(ldh):
    f = next(f for f in ldh.findings if f.check == "biological assembly")
    assert f.severity == "decide" and "tetrameric" in f.what


def test_what_it_did_not_check_is_said(ldh):
    assert any("protonation" in n for n in ldh.not_checked)


# --- the command ------------------------------------------------------------------

def _local(tmp_path, pid: str) -> str:
    p = tmp_path / f"{pid}.cif"
    p.write_text(cif(pid))
    return str(p)


def _fetch(url: str) -> str:
    acc = url.rsplit("/", 1)[-1].split(".")[0]
    return (FIX / f"{acc}.fasta").read_text()


def test_exit_0_when_a_clean_chain_exists(tmp_path, capsys):
    assert cli.main([_local(tmp_path, "1I10")], fetch=_fetch) == 0
    out = capsys.readouterr().out
    assert "Chains with no blocking defect: A" in out
    assert "10.1093/nar/gkx1012" in out


def test_exit_4_when_every_chain_is_blocked(tmp_path, capsys):
    assert cli.main([_local(tmp_path, "1L63")], fetch=_fetch) == cli.EXIT_BLOCKS
    assert "Every chain has at least one blocking defect" in capsys.readouterr().out


def test_exit_3_for_something_that_is_not_an_entry(capsys):
    assert cli.main(["not-an-entry"], fetch=_fetch) == 3


def test_json_output_round_trips(tmp_path):
    out = tmp_path / "a.json"
    cli.main([_local(tmp_path, "1L63"), "--json", str(out)], fetch=_fetch)
    data = json.loads(out.read_text())
    assert data["pdb_id"] == "1L63" and data["reference"]["mcsa_id"] == 921
