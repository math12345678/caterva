"""Which isoform a BRENDA row measured, read the same way everywhere.

`caterva.bind.core.read_isoform` is the one reader: `caterva bind
--isoform`, `caterva compose --isoform` (isoform.py, ki_mode.py), the
literature layer's resolver (Tests/fallback_logic.py, `_partition_isoform`)
and the runner's `rowScope` all read a row's commentary with it.

It read "isoform MAO B" as "MAO" and "MAO B", "monoamine oxidase B", "HK I"
and "hexokinase II" as naming no isoform, so a request for one isoform could
refuse that isoform's own row as another protein's, or take a row it could
not read as a fallback. Found by reading every Km, Ki and kcat row of every
committed BRENDA page; this file holds that audit.

THE AUDIT
---------
Every committed BRENDA page (`find Tests/fixtures caterva/tests/fixtures
-name '*brenda*'`, the .html and .html.gz pages; the bulk TSV excerpt is not
a page) is parsed with the literature layer's parser for each of the three
tables, "KM Values", "Ki Values" and "Turnover Numbers", every organism and
every compound (`parse_brenda_km_html(..., target_organism=None,
require_substrate_match=False)`). On 2026-09-30 that is 14 pages, 2,798 rows
and 615 distinct commentaries. The seven small trimmed fixtures without
BRENDA's table navigation are parsed whole for each label, so their rows
count three times; the reading is a function of the commentary alone, so
that changes no reading.

`EXPECTED` below is every commentary that names an isoform, with the reading
it must have: 166 of the 615. It was built by printing every commentary the
new reader reads, and every commentary holding an isoform-like word it does
not ("isoform", "isozyme", "isoenzyme", "form", "type", "HK", "LDH", "MAO",
"glucokinase", a Roman numeral, a letter-digit code), and checking each by
hand against the row. Every other commentary must read as naming none.
`NOT_ISOFORMS` below lists the ones checked and deliberately read as none,
with why.

The expected readings spell each isoform one way (an abbreviation, a hyphen,
the code), so that rows naming one isoform read alike; they do not equate
two numberings of one protein ("HK-I" and "HK-1", "glucokinase" and "HK-IV",
"H4" and "LDH-B4"). caterva/bind/core.py says why.
"""
from __future__ import annotations

import gzip
import re
from collections import Counter
from pathlib import Path

import pytest

from caterva.bind.core import isoform_key, isoform_names, read_isoform, same_isoform, target

REPO = Path(__file__).resolve().parents[2]

#: The reader before 2026-09-30, kept here only to show what changed.
OLD_PATTERN = (r"\b(?:isozyme|isoenzyme|isoform)\s+([A-Za-z0-9-]+)"
               r"|\b([A-Z]{2,5}-[A-Z0-9]{1,2})\b")

#: commentary -> the isoform it names, for every commentary in the corpus
#: that names one, grouped by the first page it appears on.
EXPECTED = {
    # Tests/fixtures/brenda_aggregate_row_fixture.html
    'pH 8.5, 25°C, isozyme H4': 'H4',
    'pH 8.5, 25°C, isozyme H2M2': 'H2M2',
    'pH 8.5, 25°C, isozyme M4': 'M4',
    # Tests/fixtures/brenda_hexokinase_fixture.html
    'hexokinase I, at 37°C, pH 8.1': 'HK-I',
    'hexokinase Ib, at 37°C, pH 7.2': 'HK-Ib',
    'hexokinase Ia, at 37°C, pH 7.2': 'HK-Ia',
    # Tests/fixtures/brenda_ldh_kcat_fixture.html
    'isoform LDHL2, pH 7, 40°C': 'LDHL2',
    'isoform LDHL1, pH 7, 45°C': 'LDHL1',
    'LDHB, in the presence of 0.125 mM NADH': 'LDH-B',
    'LDHB, in the presence of 0.15 mM NADH': 'LDH-B',
    'LDHB, in the presence of 0.2 mM NADH': 'LDH-B',
    'LDHB, in the presence of 0.25 mM NADH': 'LDH-B',
    'pH 7.5, temperature not specified in the publication, wild-type LDH-2, with 3 mM fructose-1,6-bisphosphate': 'LDH-2',
    'pH 7.5, temperature not specified in the publication, LDH-1, with 3 mM fructose-1,6-bisphosphate': 'LDH-1',
    'pH 5.5, temperature not specified in the publication, LDH-1, with 3 mM fructose-1,6-bisphosphate': 'LDH-1',
    'pH 5.5, temperature not specified in the publication, wild-type and mutant D241N LDH-2, with 3 mM fructose-1,6-bisphosphate': 'LDH-2',
    'pH 7.5, temperature not specified in the publication, mutant D241N LDH-2, with 3 mM fructose-1,6-bisphosphate': 'LDH-2',
    # Tests/fixtures/brenda_ldh_ki_fixture.html
    'LDH-B, pH not specified in the publication, temperature not specified in the publication': 'LDH-B',
    'LDH-A, pH not specified in the publication, temperature not specified in the publication': 'LDH-A',
    'LDH-C, pH not specified in the publication, temperature not specified in the publication': 'LDH-C',
    # Tests/fixtures/ki_mode/brenda_1.1.1.27.html.gz
    'pH 8.2, isoenzyme II': 'II',
    'pH 8.8, isoenzyme I': 'I',
    'LDHB, in the presence of 3.75 mM NAD+': 'LDH-B',
    'pH 7.3, isoenzyme I and isoenzyme II': 'I and II',
    'pH 6.0, 30°C, isozyme LDH': 'LDH',
    'pH 7.0, 30°C, isozyme LDH': 'LDH',
    'pH 6.0, 30°C, isozyme LDHB': 'LDH-B',
    'pH 5.5, temperature not specified in the publication, mutant D241N LDH-2, with 3 mM fructose-1,6-bisphosphate': 'LDH-2',
    'pH 7.0, 30°C, isozyme LDHB': 'LDH-B',
    'pH 5.5, temperature not specified in the publication, wild-type LDH-2, with 3 mM fructose-1,6-bisphosphate': 'LDH-2',
    'pH 5.5, temperature not specified in the publication, mutant D241N LDH-2, without fructose-1,6-bisphosphate': 'LDH-2',
    'pH 7.2, 25°C, isoenzyme LDH-A2B2': 'LDH-A2B2',
    'pH 7.6, 25°C, isoenzyme LDH-B4': 'LDH-B4',
    'pH 7.1, 25°C, isoenzyme LDH-A4': 'LDH-A4',
    'pH 7.3, isoenzyme I': 'I',
    'pH 7.3, isoenzyme II': 'II',
    'pH 6.5, isoenzyme II': 'II',
    'above, LDH-A, pH not specified in the publication, temperature not specified in the publication': 'LDH-A',
    'LDHB': 'LDH-B',
    # Tests/fixtures/ki_mode/brenda_1.4.3.4.html.gz
    'pH not specified in the publication, temperature not specified in the publication, MAO-B': 'MAO-B',
    'MAO-A': 'MAO-A',
    'isoform MAO A, in 50 mM potassium phosphate assay buffer (pH 7.5), at 25°C': 'MAO-A',
    'isoform MAO B, at pH 7.4 and 37°C': 'MAO-B',
    'isoform MAO A, at pH 7.4 and 37°C': 'MAO-A',
    'pH 8.5, 20°C, MAO A': 'MAO-A',
    'wild type isoform MAO B, at 25°C in 50 mM phosphate buffer (pH 7.5)': 'MAO-B',
    'pH 7.5, 25°C, MAO-A': 'MAO-A',
    'pH not specified in the publication, temperature not specified in the publication, MAO-A': 'MAO-A',
    'pH 7.4, 37°C, MAO-B': 'MAO-B',
    'pH 7.5, MAO-A incorporated into phospholipid nanodisks': 'MAO-A',
    'pH 9.0, 20°C, MAO A': 'MAO-A',
    'pH 7.5, 20°C, MAO A': 'MAO-A',
    'pH 7.4, 37°C, MAO-A': 'MAO-A',
    'pH 7.5, detergent solubilized MAO-A': 'MAO-A',
    'pH 7.5, 37°C, soluble enzyme, monoamine oxidase A': 'MAO-A',
    'pH 7.5, 37°C, immobilized enzyme, monoamine oxidase A': 'MAO-A',
    'pH 7.5, 37°C, soluble enzyme, monoamine oxidase B': 'MAO-B',
    'pH 7.5, 37°C, immobilized enzyme, monoamine oxidase B': 'MAO-B',
    'monoamine oxidase A': 'MAO-A',
    'pH 7.4, 37°C, cerebral MAO-B': 'MAO-B',
    'monoamine oxidase B wild-type enzyme': 'MAO-B',
    'monoamine oxidase B mutant D123A': 'MAO-B',
    'monoamine oxidase B mutant Y398F': 'MAO-B',
    'monoamine oxidase B mutant Y435F': 'MAO-B',
    'monoamine oxidase A wild-type enzyme': 'MAO-A',
    'monoamine oxidase A mutant Y407F': 'MAO-A',
    'monoamine oxidase A mutant D132A': 'MAO-A',
    'monoamine oxidase B': 'MAO-B',
    'isoform MAO-B, at pH 8.0 and 37°C': 'MAO-B',
    'pH 7.6, 37°C, selective for MAO-A, no preincubation': 'MAO-A',
    'pH 7.6, 37°C, MAO-B, selective for MAO-B': 'MAO-B',
    'pH 7.6, 37°C, selective for MAO-B': 'MAO-B',
    'inhibition of MAO-B': 'MAO-B',
    'MAO-B': 'MAO-B',
    'inhibition of MAO-A': 'MAO-A',
    'above, pH 7.5, 25°C, MAO-B': 'MAO-B',
    'inhibition of MAO-B mutant I199A': 'MAO-B',
    'above, MAO-B': 'MAO-B',
    'pH 7.5, 25°C, MAO-B': 'MAO-B',
    'above, pH 7.4, 37°C, MAO-A': 'MAO-A',
    'above, pH 7.4, 37°C, MAO-B': 'MAO-B',
    'pH 7.4, 38°C, MAO-A': 'MAO-A',
    'pH 7.4, 38°C, MAO-B': 'MAO-B',
    'pH 7.5, MAO-B, determined from competitive inhibition data of substrate oxidation at 25°C': 'MAO-B',
    'pH 7.5, MAO-B, determined from Kitz-Wilson plots of the hydrazine concentration dependence on rates in enzyme inhibition at 15°C': 'MAO-B',
    'pH 7.5, MAO-A, determined from Kitz-Wilson plots of the hydrazine concentration dependence on rates in enzyme inhibition at 15°C': 'MAO-A',
    'pH 7.5, MAO-A, determined from competitive inhibition data of substrate oxidation at 25°C': 'MAO-A',
    'pH 7.4, 37°C, monoamine oxidase A': 'MAO-A',
    'MAO B': 'MAO-B',
    'MAO A': 'MAO-A',
    'pH 7.4, 37°C, monoamine oxidase B': 'MAO-B',
    'recombinant MAO-B': 'MAO-B',
    # Tests/fixtures/recorded/brenda_2.7.1.1.html.gz
    'hexokinase III, at 30°C, pH 8.1': 'HK-III',
    'rat brain enzyme, hexokinase I': 'HK-I',
    'bovine heart enzyme, hexokinase II': 'HK-II',
    'HKI, at 25°C, pH 7.4': 'HK-I',
    'HKII, at 25°C, pH 7.4': 'HK-II',
    'hexokinase Ia': 'HK-Ia',
    'hexokinase Ic, at 37°C, pH 7.2': 'HK-Ic',
    'hexokinase Ib': 'HK-Ib',
    'rat liver enzyme, hexokinase IV': 'HK-IV',
    'MgATP2-, bound mitochondrial HK I, at pH 7.5': 'HK-I',
    'HK1': 'HK-1',
    'mutant enzyme V182L, glutathione S-transferase glucokinase B fusion protein': 'glucokinase B',
    'MgATP2-, solubilized mitochondrial HK I, at pH 7.5': 'HK-I',
    'recombinant HXK1, at 30°C, pH 8': 'HXK-1',
    'mutant enzyme Y61S, glutathione S-transferase glucokinase B fusion protein': 'glucokinase B',
    'HK2': 'HK-2',
    'recombinant TbHK1': 'TbHK-1',
    'recombinant hexokinase I expressed in Escherichia coli': 'HK-I',
    'hexokinase II, at 30°C, pH 8.1': 'HK-II',
    'hexokinase B': 'HK-B',
    'mutant enzyme E265K, glutathione S-transferase glucokinase B fusion protein': 'glucokinase B',
    'mutant enzyme K420E, glutathione S-transferase glucokinase B fusion protein': 'glucokinase B',
    'hexokinase II': 'HK-II',
    'wild-type glutathione S-transferase glucokinase B fusion protein': 'glucokinase B',
    'reticulocyte hexokinase Ia and Ib, at 37°C, pH 8.1': 'HK-Ia and HK-Ib',
    'HK3': 'HK-3',
    'hexokinase C': 'HK-C',
    'MgATP, hexokinase I, at 37°C, pH 8.1': 'HK-I',
    'recombinant HXK2, at 30°C, pH 8': 'HXK-2',
    'mutant enzyme A379V, glutathione S-transferase glucokinase B fusion protein': 'glucokinase B',
    'hexokinase III': 'HK-III',
    'wild type hexokinase II': 'HK-II',
    'hexokinase III from lymphocytes, at 37°C, pH 8.1': 'HK-III',
    'catalytically active recombinant carboxyl-domain of hexokinase III, at 37°C, pH 8.1': 'HK-III',
    'MgCTP2-, hexokinase I, at 37°C, pH 8.1': 'HK-I',
    'pH 8.4, 30°C, recombinant isozyme hexokinase 2': 'HK-2',
    'hexokinases PI and PII': 'HK-PI and HK-PII',
    'hexokinases Ib and Ic, at 37°C, pH 7.2': 'HK-Ib and HK-Ic',
    'HK I, at 25°C, pH 7.4': 'HK-I',
    'reticulocyte hexokinase Ia': 'HK-Ia',
    'glucokinase': 'glucokinase',
    'reticulocyte hexokinase Ib': 'HK-Ib',
    'hexokinase IV': 'HK-IV',
    '31°C and pH 7.7, fetal glucokinase': 'glucokinase',
    '31°C and pH 7.7, adult glucokinase': 'glucokinase',
    'hexokinase I': 'HK-I',
    'MgITP2-, hexokinase Ib': 'HK-Ib',
    'MgITP2-, hexokinase Ia': 'HK-Ia',
    'MgITP2-, hexokinase I, at 37°C, pH 8.1': 'HK-I',
    'MgUTP2-, hexokinase I, at 37°C, pH 8.1': 'HK-I',
    'hexokinase III, at 30°C, pH 7.2': 'HK-III',
    'recombinant wild-type hexokinase I': 'HK-I',
    'recombinant D84E mutant hexokinase I': 'HK-I',
    'recombinant D84K mutant hexokinase I': 'HK-I',
    'recombinant D84A mutant hexokinase I': 'HK-I',
    'nonaggregating interface mutant hexokinase I, pH 7.8': 'HK-I',
    'HK I': 'HK-I',
    'wild-type hexokinase I, pH 7.8': 'HK-I',
    'D84A mutant of HK I': 'HK-I',
    'hexokinase 1': 'HK-1',
    'hexokinase 2': 'HK-2',
    'uncomplexed ATP4-, hexokinase III, at 30°C, pH 7.2': 'HK-III',
    'catalytically active recombinant carboxyl-domain of hexokinase III, at 37°C, pH 7.2': 'HK-III',
    'hexokinase C, versus ATP, at 0.2 mM glucose': 'HK-C',
    'hexokinase III from lymphocytes, at 37°C, pH 7.2': 'HK-III',
    'pH 7, hexokinase 1': 'HK-1',
    'HK1, at pH 7': 'HK-1',
    'hexokinase PI': 'HK-PI',
    'hexokinase PII': 'HK-PII',
    'uncomplexed, hexokinase III, at 30°C, pH 7.2': 'HK-III',
    'recombinant HK I, a truncate HK I form lacking the first 11 amino acids named HK-11aa, and the 50 kDa C-terminal half of HK I, at 37°C, pH 7.2': 'HK-I',
    'intact hexokinase I': 'HK-I',
    'glucokinase with C-terminal 5 alanine addition': 'glucokinase',
    'glucokinase with C-terminal 10 alanine addition': 'glucokinase',
}

#: Commentaries with an isoform-like word that name no isoform, and why.
NOT_ISOFORMS = [
    # A drug named after the protein it activates, not the protein measured
    # (human glucokinase, ref 721735).
    ("wild-type in the presence of 20 microM glucokinase activator drug (GKA), pH and "
     "temperature not specified in the publication", "a drug's name"),
    # A cloning strain; the old hyphen code read "XL-1".
    ("recombinant hexokinase expressed in Escherichia coli XL-1 Blue, at pH 7.5",
     "a strain"),
    # An activator's code name; the old hyphen code read "RO-28".
    ("in presence of activator RO-28-1675", "a compound code"),
    # Tissue sources. In LDH they correspond to the H4 and M4 isozymes, but
    # that is nomenclature, which the reader does not assert.
    ("enzyme form heart and muscle", "tissue names"),
    ("enzyme from heart", "a tissue"),
    ("enzyme from muscle", "a tissue"),
    # Oligomeric states and construct names.
    ("octameric enzyme form", "an oligomeric state"),
    ("tetrameric enzyme form", "an oligomeric state"),
    ("catalytically active 51 kDa C fragment of hexokinase, versus ATP", "a fragment"),
    # Subcellular forms of maize hexokinase, named by location, not by name.
    ("cytosolic hexokinase from root", "a location"),
    ("non-cytosolic hexokinase from root", "a location"),
    # The gene family, not an isoform of it.
    ("measured without D-fructose 1,6-bisphosphate, hybrid enzyme constructed from fragments "
     "of the LDH genes from Bacillus stearothermophilus (coding for aa 15-100) and Bacillus "
     "megaterium (coding for aa 101-331)", "a gene family"),
]


def _pages():
    found = []
    for root in (REPO / "Tests" / "fixtures", REPO / "caterva" / "tests" / "fixtures"):
        found += [p for p in root.rglob("*brenda*") if p.name.endswith((".html", ".html.gz"))]
    return sorted(found)


@pytest.fixture(scope="module")
def corpus():
    """(page, table, commentary) for every row of every committed page."""
    from caterva.checkout import LiteratureLayerUnavailable, literature_module

    try:
        brenda_client = literature_module("brenda_client")
    except LiteratureLayerUnavailable:  # pragma: no cover - the wheel
        pytest.skip("the literature layer is not installed")
    rows = []
    for page in _pages():
        raw = page.read_bytes()
        # errors="replace", as `requests` decodes the live page: the LDH page
        # carries six bytes that are not UTF-8 (Tests/fixtures/ki_mode/README.md).
        html = (gzip.decompress(raw) if page.suffix == ".gz" else raw).decode(
            "utf-8", errors="replace")
        for label in (brenda_client.KM_TABLE_LABEL, brenda_client.KI_TABLE_LABEL,
                      brenda_client.TURNOVER_TABLE_LABEL):
            for row in brenda_client.parse_brenda_km_html(
                    html, "audit", [], target_organism=None, require_substrate_match=False,
                    table_label=label):
                rows.append((page.relative_to(REPO).as_posix(), label, row.conditions))
    return rows


class TestTheWholeCorpus:
    def test_it_is_the_corpus_the_audit_read(self, corpus):
        """The figures the audit was made on. A new page, or a parser change,
        changes them; the expected table then needs the new rows checked."""
        assert len({page for page, _, _ in corpus}) == 14
        assert len(corpus) == 2798
        assert len({c for _, _, c in corpus if c}) == 615

    def test_every_row_reads_as_checked_by_hand(self, corpus):
        wrong = {}
        for _, _, commentary in corpus:
            if commentary and read_isoform(commentary) != EXPECTED.get(commentary):
                wrong[commentary] = (read_isoform(commentary), EXPECTED.get(commentary))
        assert wrong == {}

    def test_every_expected_reading_is_of_a_real_row(self, corpus):
        commentaries = {c for _, _, c in corpus}
        assert set(EXPECTED) <= commentaries
        assert {c for c, _ in NOT_ISOFORMS} <= commentaries

    def test_every_expected_reading_is_in_the_rows_own_words(self):
        """A check on EXPECTED that does not run the reader. The table was
        made by printing the reader's output and checking it by hand, so the
        whole-corpus test above pins it; this asks something the reader's
        output cannot answer for itself: that each isoform code in a reading
        is written in its row, as a word of its own or right after the
        abbreviation it is run into ("LDHB", "HK2", "TbHK1"). An invented
        code, or one taken from the wrong place, fails here."""
        attached = r"(?:(?<![A-Za-z0-9])|(?<=HK)|(?<=HXK)|(?<=LDH)|(?<=MAO))"
        missing = {}
        for commentary, reading in EXPECTED.items():
            for name in isoform_names(reading):
                code = name.rsplit("-", 1)[-1] if "-" in name else name.split()[-1]
                if not re.search(attached + re.escape(code) + r"(?![A-Za-z0-9])", commentary):
                    missing[commentary] = (reading, code)
        assert missing == {}

    def test_what_changed_from_the_old_reader(self, corpus):
        """On the three full pages (LDH and monoamine oxidase in
        Tests/fixtures/ki_mode/, hexokinase in Tests/fixtures/recorded/), the
        old reader missed the isoform of 192 rows, cut 45 short or misread
        them, read one as a strain's and one as a compound's, and spelled 4
        differently (the same isoform: "LDHB" now reads "LDH-B")."""
        old = re.compile(OLD_PATTERN)

        def before(text):
            m = old.search(text or "")
            return (m.group(1) or m.group(2)) if m else None

        kinds = Counter()
        for page, _, commentary in corpus:
            if not page.endswith(".html.gz"):
                continue
            was, now = before(commentary), read_isoform(commentary)
            if was == now:
                kinds["same"] += 1
            elif was is None:
                kinds["missed"] += 1
            elif now is None:
                kinds["not an isoform"] += 1
            elif isoform_key(was) == isoform_key(now):
                kinds["respelled"] += 1
            else:
                kinds["cut short or misread"] += 1
        assert kinds == {"same": 1897, "missed": 192, "cut short or misread": 45,
                         "respelled": 4, "not an isoform": 2}


class TestThePhrases:
    """Anchored on the rows' own words, each with what the old reader made
    of it."""

    @pytest.mark.parametrize("commentary, before, now", [
        # Monoamine oxidase, ref 742446 (isatin, clorgyline) and ref 724966.
        ("isoform MAO B, at pH 7.4 and 37\u00b0C", "MAO", "MAO-B"),
        ("isoform MAO A, at pH 7.4 and 37\u00b0C", "MAO", "MAO-A"),
        ("wild type isoform MAO B, at 25\u00b0C in 50 mM phosphate buffer (pH 7.5)", "MAO", "MAO-B"),
        ("MAO B", None, "MAO-B"),
        ("pH 7.5, 20\u00b0C, MAO A", None, "MAO-A"),
        ("monoamine oxidase B wild-type enzyme", None, "MAO-B"),
        ("pH 7.4, 37\u00b0C, monoamine oxidase A", None, "MAO-A"),
        ("isoform MAO-B, at pH 8.0 and 37\u00b0C", "MAO-B", "MAO-B"),
        # Hexokinase, the recorded page.
        ("HK I, at 25\u00b0C, pH 7.4", None, "HK-I"),
        ("HKII, at 25\u00b0C, pH 7.4", None, "HK-II"),
        ("rat brain enzyme, hexokinase I", None, "HK-I"),
        ("rat liver enzyme, hexokinase IV", None, "HK-IV"),
        ("pH 8.4, 30\u00b0C, recombinant isozyme hexokinase 2", "hexokinase", "HK-2"),
        ("HK1, at pH 7", None, "HK-1"),
        ("recombinant HXK1, at 30\u00b0C, pH 8", None, "HXK-1"),
        ("recombinant TbHK1", None, "TbHK-1"),
        ("hexokinase PII", None, "HK-PII"),
        ("reticulocyte hexokinase Ia and Ib, at 37\u00b0C, pH 8.1", None, "HK-Ia and HK-Ib"),
        ("31\u00b0C and pH 7.7, fetal glucokinase", None, "glucokinase"),
        ("wild-type glutathione S-transferase glucokinase B fusion protein", None, "glucokinase B"),
        # Lactate dehydrogenase, the committed page.
        ("LDHB, in the presence of 0.2 mM NADH", None, "LDH-B"),
        ("pH 7.0, 30\u00b0C, isozyme LDHB", "LDHB", "LDH-B"),
        ("pH 7.3, isoenzyme I and isoenzyme II", "I", "I and II"),
        ("pH 7.2, 25\u00b0C, isoenzyme LDH-A2B2", "LDH-A2B2", "LDH-A2B2"),
        ("pH 8.5, 25\u00b0C, isozyme H4", "H4", "H4"),
        ("isoform LDHL1, pH 7, 45\u00b0C", "LDHL1", "LDHL1"),
        ("pH 7.0, 30\u00b0C, isozyme LDH", "LDH", "LDH"),
        ("LDH-B, pH not specified in the publication, temperature not specified in the "
         "publication", "LDH-B", "LDH-B"),
    ])
    def test_reads(self, commentary, before, now):
        m = re.search(OLD_PATTERN, commentary)
        assert ((m.group(1) or m.group(2)) if m else None) == before
        assert read_isoform(commentary) == now
        assert EXPECTED[commentary] == now

    @pytest.mark.parametrize("commentary, what", NOT_ISOFORMS)
    def test_names_no_isoform(self, commentary, what):
        assert read_isoform(commentary) is None, what

    @pytest.mark.parametrize("text", [
        # Not in the corpus; the shapes a looser reader would take.
        "treated with an MAOI", "in presence of NAD-H", "EC-3 class", "strain XL-1 Blue",
        "isoform of the enzyme", "hexokinase activity", "type II collagen", "pH-7",
        # A plural keyword followed by the sentence going on: before the
        # token had to be shaped like a name, these read "tested",
        # "present" and "specific".
        "all isozymes tested", "isozymes present in extract", "isoform specific inhibitor",
        # A strain spelled like an abbreviation and its code: the strain
        # rule held only for the generic hyphen code, so these read "HK-1".
        "enzyme from strain HK-1", "expressed in Escherichia coli HK1",
    ])
    def test_invents_no_isoform(self, text):
        assert read_isoform(text) is None

    @pytest.mark.parametrize("text, reading", [
        # Not in the corpus, so the whole-corpus table cannot hold them. A
        # capital A is a code: the keyword's token was lower-cased and
        # checked against a list of function words that held "a", so
        # "isoform A" read as none while "isoform B" read "B", and a row so
        # written became the fallback for a request for any isoform.
        ("isoform A", "A"), ("isozyme A, pH 7.5", "A"), ("isoform B", "B"),
        ("isoenzyme A and B", "A and B"), ("isoforms I and II", "I and II"),
        # Greek letters written out, which the old reader read too.
        ("isoform alpha", "alpha"),
        # A lower-case article after the keyword is still not a name.
        ("an isoform a novel inhibitor binds", None),
    ])
    def test_reads_a_name_after_a_keyword_by_its_shape(self, text, reading):
        assert read_isoform(text) == reading


class TestTheComparison:
    @pytest.mark.parametrize("a, b", [
        ("MAO B", "MAO-B"), ("MAOB", "MAO-B"), ("mao_b", "MAO B"), ("LDH-A", "ldh a"),
        ("LDHB", "LDH-B"),
        # A row naming two is either.
        ("I and II", "II"), ("HK-Ib and HK-Ic", "hk-ic"),
    ])
    def test_one_isoform(self, a, b):
        assert same_isoform(a, b) and same_isoform(b, a)

    @pytest.mark.parametrize("row, request_", [
        # A request is read as a row is read, and a code alone is that code
        # after an abbreviation. Potato's rows on the recorded hexokinase
        # page read "HK-1", "HK-2", "HK-3" ("HK2", ref 640239); a request
        # for "2" or "hexokinase 2" was compared as typed and missed them
        # (Tests/test_isoform_resolution.py has the resolver's side).
        ("HK-2", "2"), ("HK-2", "hexokinase 2"), ("HK-2", "isozyme 2"), ("HK-2", "HK2"),
        ("HK-II", "hexokinase II"), ("HK-II", "II"),
        ("MAO-B", "B"), ("MAO-B", "b"), ("MAO-B", "monoamine oxidase isoform B"),
        ("MAO-B", "isoform MAO B"), ("MAO-A", "monoamine oxidase A"),
        ("HK-Ib and HK-Ic", "Ic"), ("TbHK-1", "1"),
        # And a row whose keyword left the code alone ("isoenzyme II",
        # "isoform 2 (HK-2)") is the request spelled with an abbreviation.
        ("II", "HK-II"), ("2", "HK-2"),
    ])
    def test_a_request_is_read_as_the_rows_are(self, row, request_):
        assert same_isoform(row, request_) and same_isoform(request_, row)

    @pytest.mark.parametrize("a, b", [
        ("MAO-A", "MAO-B"), ("I and II", "III"), (None, "LDH-A"), (None, None),
        # Two numberings are not one spelling (caterva/bind/core.py).
        ("HK-I", "HK-1"), ("glucokinase", "HK-IV"), ("H4", "LDH-B4"),
        # A code alone is not another numbering's code either, nor another
        # letter's.
        ("HK-2", "II"), ("HK-II", "2"), ("MAO-A", "B"),
        # Two abbreviations with one code stay two names.
        ("HK-1", "HXK-1"),
        # An enzyme name with no code names no isoform.
        ("HK-2", "hexokinase"),
    ])
    def test_different(self, a, b):
        assert not same_isoform(a, b)

    def test_one_function_for_compose_and_the_resolver(self):
        from caterva.compose import isoform
        from caterva.checkout import literature_module

        assert isoform.same_isoform is same_isoform
        fallback_logic = literature_module("fallback_logic")
        for a, b in [("MAO B", "MAO-B"), ("I and II", "II"), ("HK-I", "HK-1"), ("HK-2", "2"),
                     ("HK-2", "hexokinase 2"), ("HK-2", "II")]:
            assert fallback_logic._same_isoform(a, b) == same_isoform(a, b)

    def test_names(self):
        assert isoform_names("HK-PI and HK-PII") == ("HK-PI", "HK-PII")
        assert isoform_names("MAO-B") == ("MAO-B",) and isoform_names(None) == ()


class TestCatervaBind:
    """`caterva bind --isoform` compared with `.lower()`: "LDH A" and "LDH-A"
    were two isoforms, and so were a row naming "I and II" and a simulation
    of II."""

    @staticmethod
    def _row(commentary):
        from caterva.bind.core import measurement
        return measurement(0.0014, "gossypol", "Homo sapiens", "711801", commentary, None, None)

    def test_a_row_spelled_otherwise_is_not_excluded(self):
        t = target([self._row("isoform MAO B, at pH 7.4 and 37\u00b0C")], "free", "MAOB")
        assert t.excluded == [] and len(t.used) == 1

    def test_a_row_naming_two_is_kept_for_either(self):
        t = target([self._row("pH 7.3, isoenzyme I and isoenzyme II")], "free", "II")
        assert t.excluded == []

    def test_a_code_alone_keeps_the_row_it_names(self):
        # Potato HK2's ADP row (recorded hexokinase page, ref 640239), asked
        # for as "2" and as "hexokinase 2".
        for asked in ("2", "hexokinase 2"):
            t = target([self._row("HK2")], "free", asked)
            assert t.excluded == [] and len(t.used) == 1

    def test_another_isoform_is_still_excluded(self):
        t = target([self._row("LDH-B, pH not specified in the publication")], "free", "LDH-A")
        assert [m.excluded for m in t.excluded] == ["measured on LDH-B; the simulation is of LDH-A"]
