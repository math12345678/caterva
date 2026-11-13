"""What a BRENDA row measured, beyond its value: the facts that decide
whether it may stand for the enzyme's own constant.

WHY THIS EXISTS
---------------
The adversarial round of 2026-11-11 read every carried row back against
BRENDA, as a professor would, and found numbers that were real rows and still
the wrong ones to carry:

- an apparent Km measured with an inhibitor in the assay (xanthine oxidase,
  ref 766313: 0.0167 mM "in the presence of 0.0005 mM (E)-5-(3-nitrophenyl)-
  ...", while the same paper's "in the absence of inhibitor" row is 0.01208);
- a K0.5 with a Hill coefficient of 1.8 (glucokinase, ref 739603) put into a
  hyperbolic Michaelis-Menten law as if it were a Km;
- constants of constructs: ACE's isolated C-domain (ref 650001), a chimeric
  ACE (ref 678511), a benzoate-modified glucose oxidase (ref 742144), an
  immobilised LDH (ref 741355), trypsin in 20% methanol (ref 95437);
- the minus-K+ control of pyruvate kinase (ref 674499, kcat 3.2 1/s against
  1182 with K+, its essential activator) taken because K+ looked "added";
- a glucokinase row (UniProt P35557) carried for HK2, and a CYP3A5/CYP3A43
  row (P20815, Q9HB55) for CYP2B6, because only the commentary was read.

Each function here reads one of those facts from the row and says it in
words a reader can check against the row. None changes a value; the
resolver (fallback_logic._best_evidenced) decides what to prefer.
"""
from __future__ import annotations

import functools
import re
from typing import Iterable, Optional

# -- K0.5 / Hill ---------------------------------------------------------------

_HALF_SATURATION = re.compile(
    r"\b[KS]\s*\(?\s*0\.5\s*\)?(?=[\s,;:)]|$)|\b[KS]0\.5\b|\[S\]\s*0\.5|\bS50\b"
    r"|\bHill\s+(?:coefficient|constant|value|number)\b|\bnH\s*[=:]?\s*\d"
    r"|\bhalf[- ]saturation\b|\bsigmoid(?:al)?\s+kinetics\b",
    re.IGNORECASE,
)
_HILL_VALUE = re.compile(r"\bHill\s+coefficient\s*(?:of|=|:)?\s*(\d+(?:\.\d+)?)", re.IGNORECASE)


def half_saturation(commentary: Optional[str]) -> Optional[str]:
    """How the row says its constant is a K0.5 (cooperative half-saturation
    constant) rather than a Michaelis-Menten Km, or None. "K0.5 value, Hill
    coefficient 1.8" gives "a K0.5 with a Hill coefficient of 1.8"."""
    text = commentary or ""
    if not _HALF_SATURATION.search(text):
        return None
    hill = _HILL_VALUE.search(text)
    if hill:
        return f"a K0.5 with a Hill coefficient of {hill.group(1)}"
    return "a K0.5 (half-saturation constant of cooperative kinetics)"


# -- Constructs and preparations -------------------------------------------------

_NEGATED = re.compile(r"\b(?:without|absence\s+of|no)\b[^,;]*$", re.IGNORECASE)

_COSOLVENTS = (r"methanol|ethanol|DMSO|dimethyl\s*sulfoxide|dimethylsulfoxide|glycerol|acetonitrile"
               r"|(?:iso)?propanol|dioxane|acetone|trifluoroethanol|dimethylformamide|DMF|formamide"
               r"|ethylene\s+glycol|sucrose|trehalose|urea|guanidin\w*")

#: (pattern, what the row measured). First match decides.
_CONSTRUCTS = (
    (re.compile(r"\bchimer(?:a|ic)\w*|\bdomain[- ]swap\w*|\b\w+dom-\w+", re.IGNORECASE),
     "a chimeric construct"),
    (re.compile(r"\b(?:[NC]|carboxyl|amino)-?(?:terminal\s+)?(?:half|domain)\b|\b[NC]dom\b|\b(?:isolated|catalytic|catalyctic|single)"
                r"\s+domain\b|\bdomain\s+(?:construct|only)\b", re.IGNORECASE),
     "an isolated domain"),
    (re.compile(r"\b[NC]-terminal\b[^,;]{0,30}\b(?:addition|extension|deletion|truncation)\b|\btruncat\w+|\bdeletion\s+(?:mutant|construct|variant)\b", re.IGNORECASE),
     "a truncated or extended construct"),
    # "recombinant wild-type enzyme in fusion with Aga2" (glucose oxidase,
    # ref 743744): yeast surface display, the enzyme tethered to a protein.
    (re.compile(r"\bfusion\s+(?:protein|enzyme|construct)\b|\bfused\s+(?:to|with)\b"
                r"|\bin\s+fusion\s+with\b|\bfusion\s+with\b|\bsurface[- ]displayed\b", re.IGNORECASE),
     "a fusion construct"),
    # "in complex with monomer from Trypanosoma cruzi, pH 7.4, 25°C"
    # (triosephosphate isomerase, T. brucei, ref 682787, beside the same
    # paper's "wild-type, pH 7.4, 25°C"): an interspecies heterodimer, carried
    # as T. brucei TIM in the review of the second round (2026-11-12). A
    # complex with a ligand or a regulatory protein is not one.
    (re.compile(r"\bin\s+complex\s+with\s+(?:an?\s+|the\s+)?(?:intact\s+|wild[- ]type\s+"
                r"|mutant\s+\S+\s+(?:of\s+)?)?(?:monomer|subunit|protomer)s?\b"
                r"|\bin\s+complex\s+with\s+(?:an?\s+|the\s+)?(?:mutant\s+\S+\s+)?of\s+"
                r"[A-Z][a-z]+\s+[a-z]+\b|\bhybrid\s+(?:enzyme|dimer|tetramer|protein)\b"
                r"|\b(?:interspecies|hybrid)\s+heterodimer\b", re.IGNORECASE),
     "a hybrid enzyme (subunits of two proteins)"),
    (re.compile(r"\bimmobi(?:li[sz]|iz)ed\b|\bimmobili[sz]ation\b|\bcross[- ]?linked\s+"
                r"(?:enzyme|crystal|aggregate)", re.IGNORECASE),
     "an immobilised enzyme"),
    (re.compile(r"\b[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*-modified\b|\bchemically\s+modified\b"
                r"|\bmodified\s+enzyme\b|\bpegylat\w+|\bglycated\b|\bacetylated\s+enzyme\b"
                # "enzyme with O-carboxymethyl-poly-beta-cyclodextrin attached
                # to surface" (bovine trypsin and BAEE, ref 668032, beside its
                # "wild-type" row): a polymer conjugate.
                r"|\battached\s+to\s+(?:the\s+)?(?:enzyme\s+|protein\s+)?surface\b"
                # The enzyme conjugated, not a substrate: "glycine-conjugated
                # bile acid" and "bile acids conjugated to taurine" are
                # substrates (review, 2026-11-12).
                r"|\b(?:enzyme|protein)\s+(?:was\s+|is\s+)?conjugated\s+(?:to|with)\b"
                r"|\b(?:enzyme|protein)[- ]conjugates?\b"
                r"|\bgrafted\s+(?:to|onto|with)\b|\bencapsulated\b|\bentrapped\b",
                re.IGNORECASE),
     "a chemically modified enzyme"),
    # "human serum albumin-bound enzyme, pH 5.2, 37°C" (hen lysozyme, ref
    # 718362, beside the same paper's "free enzyme"): the enzyme bound to a
    # carrier protein or surface (third round's review).
    (re.compile(r"\b[\w-]*albumin[- ]bound\b|\b(?:antibody|heparin|matrix|bead|resin|support|surface"
                r"|nanoparticle|polymer|chitosan|silica)s?-bound\b"
                r"|\b(?:enzyme|protein)\s+(?:was\s+|is\s+)?adsorbed\s+(?:to|on|onto)\b"
                r"|\bbound\s+to\s+(?:\w+\s+){0,2}(?:albumin|nanoparticles?"
                r"|beads?|resin|support|matrix)\b", re.IGNORECASE),
     "an enzyme bound to a carrier"),
    # "uncleaved enzyme, nonsulfated" (human trypsin-2, ref 772843: four
    # rows, cleaved or not by autolysis, sulfated or not), beside the same
    # compound's "wild type enzyme" rows (refs 678332, 682760): a paper's
    # series over modification states, not the enzyme as isolated.
    (re.compile(r"\b(?:un)?cleaved\s+(?:enzyme|form|protein)\b|\b(?:non|un|de)?-?sulfated\b(?!\s+(?!enzyme\b|form\b|protein\b)[A-Za-z])"
                r"|\bautolys(?:ed|is)\s+(?:enzyme|form)\b", re.IGNORECASE),
     "a modification state of the enzyme"),
    (re.compile(rf"\b\d+(?:\.\d+)?\s*%\s*(?:\(?[vw]/[vw]\)?\s*)?(?:{_COSOLVENTS})\b"
                rf"|\b\d+(?:\.\d+)?\s*M\s+(?:urea|guanidin\w*)\b", re.IGNORECASE),
     "an assay with a cosolvent or denaturant added"),
    # "addition of aluminium lactate during measurement of activity" (mouse
    # AChE, ref 650742, beside plain native rows): a compound added to the
    # assay, an apparent constant (fifth round of the real-values review).
    (re.compile(r"\b(?:addition|presence)\s+of\s+[^,;]{1,60}?\s+(?:during|in)\s+(?:the\s+)?"
                r"(?:measurement|assay|activity\s+(?:measurement|assay)|reaction\s+mixture)\b"
                r"|\b[^,;\s]+\s+added\s+(?:during|to)\s+(?:the\s+)?(?:measurement|assay)\b",
                re.IGNORECASE),
     "an assay with a compound added"),
    # "Co-ADH", "Cu-ADH" (yeast ADH, ref 655741): the zinc enzyme with its
    # metal replaced, counted among native rows (fifth round's review).
    (re.compile(r"\b(?:Co|Cu|Cd|Ni|Hg)(?:\(II\)|2\+)?-(?:substituted\s+)?(?:ADH|[A-Z]{2,6}|enzyme)\b"
                r"|\b(?:metal|cobalt|copper|cadmium|nickel|apo)[- ]substituted\b"
                r"|\b(?:cobalt|copper|cadmium|nickel)[- ](?:enzyme|reconstituted)\b", 0),
     "a metal-substituted enzyme"),
    # "after treatment with NaCl for 3 months" (the same paper): the enzyme
    # of animals treated in vivo, not the native enzyme.
    (re.compile(r"\bafter\s+(?:in\s+vivo\s+)?treatment\s+(?:of\s+(?:the\s+)?(?:animals|mice|rats)\s+)?"
                r"with\s+[^,;]{1,60}?\s+for\s+\d+\s*(?:days?|weeks?|months?)\b"
                r"|\b(?:animals|mice|rats)\s+(?:were\s+)?treated\s+with\b", re.IGNORECASE),
     "the enzyme of animals treated in vivo"),
    # "recombinant His12-tagged wild type enzyme" (Streptomyces xylose
    # isomerase, ref 728730) beside the same paper's "native wild type
    # enzyme", whose kcat is 7-fold higher: a tagged construct (fifth
    # round, R5V1-12).
    (re.compile(r"\b(?:His|histidine|hexahistidine|GST|MBP|FLAG|Strep|SUMO)\d*[- ]?(?:tag(?:ged)?)\b"
                r"|\b(?:N|C)-terminal(?:ly)?\s+(?:His|histidine)\d*[- ]?tag", re.IGNORECASE),
     "a tagged construct"),
    (re.compile(r"\bsubtype\s+[A-Z0-9]{1,3}\b|\bclade\s+[A-Z]\b|\bdrug[- ]resistant\b"
                r"|\bmultidrug[- ]resistant\b", re.IGNORECASE),
     "a named subtype or variant of the enzyme"),
)


def construct_of(commentary: Optional[str]) -> Optional[str]:
    """What non-native form of the enzyme, or what added cosolvent, the row
    names, with the words that say so: "an isolated domain ('C-domain')".
    None for a row naming none. A mention after "without" / "absence of"
    ("without addition of methanol") is the control, not the construct."""
    text = commentary or ""
    for pattern, what in _CONSTRUCTS:
        for m in pattern.finditer(text):
            if _NEGATED.search(text[max(0, m.start() - 40):m.start()]):
                continue
            return f"{what} ({m.group(0).strip()!r})"
    return None


#: A value computed, not measured: "predicted Ki value" (zanamivir and
#: influenza neuraminidase, ref 699433, 0.000133 mM beside measured rows
#: 1000-fold lower, counted as a literature value; fifth round's review).
_PREDICTED = re.compile(
    r"\b(?:predicted|(?:calculated|computed|estimated)\s+(?:by|from|with)\s+(?:molecular\s+)?"
    r"(?:docking|modell?ing|simulations?)|in\s+silico|docking|molecular\s+dynamics|QSAR)\b",
    re.IGNORECASE)


def predicted(commentary: Optional[str]) -> Optional[str]:
    """The words saying a row's value was computed rather than measured
    ("predicted Ki value", "docking"), or None. A kcat "calculated" from a
    measured Vmax is a measurement, and is not read as one."""
    m = _PREDICTED.search(commentary or "")
    return m.group(0) if m else None


# -- Ions --------------------------------------------------------------------------

_ION = re.compile(
    r"^(?:\(?NH4\)?\d?\+?|[A-Z][a-z]?\d?[+-]|[A-Z][a-z]?\d*\+{1,3}|[A-Z][a-z]?(?:Cl|Br|I|F)\d?"
    r"|[A-Z][a-z]?\d?\(?(?:SO4|NO3|PO4|CO3|OAc|acetate)\)?\d?|\(NH4\)2SO4|NH4Cl"
    r"|(?:potassium|sodium|lithium|rubidium|caesium|cesium|ammonium|magnesium|manganese|calcium"
    r"|zinc|cobalt|nickel|iron|copper)(?:\s+(?:ions?|chloride|sulfate|acetate|nitrate))?)$",
    re.IGNORECASE,
)


#: A salt whose cation is a stand-in for an activating one: thrombin's
#: Na+-free slow form is measured in choline chloride at the ionic strength
#: of the NaCl rows (BRENDA ref 709074). A row naming one is the paper's
#: minus-cation control.
_CATION_STAND_IN = re.compile(
    r"\b(?:choline|tetramethylammonium|tetraethylammonium|tetrabutylammonium|TMA|"
    r"N-methyl-D-glucamine)\s*(?:chloride|Cl|acetate|bromide)?\b", re.IGNORECASE)


def cation_stand_in(commentary: Optional[str]) -> Optional[str]:
    """The stand-in salt a row was measured in, or None."""
    m = _CATION_STAND_IN.search(commentary or "")
    return m.group(0) if m else None


def is_ion(compound: Optional[str]) -> bool:
    """A metal or inorganic ion, or its simple salt: K+, Mg2+, NaCl, MgCl2,
    (NH4)2SO4, potassium. These are cofactors and activators (K+ for pyruvate
    kinase, Na+ for thrombin's fast form, Zn2+ for carbonic anhydrase); a row
    measured without one is a minus-activator control, never the enzyme's
    physiological constant."""
    return bool(compound and _ION.match(compound.strip()))


# -- Isoform from the UniProt column ----------------------------------------------

_ACCESSION = re.compile(r"\b(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})\b")


def accessions(cell: Optional[str]) -> tuple:
    """The UniProt accessions a row's own accession cell lists, in order."""
    return tuple(dict.fromkeys(_ACCESSION.findall(cell or "")))


@functools.lru_cache(maxsize=512)
def _labels_of_ec(ec: str) -> tuple:
    """((accession, label, organism code), ...) the enzyme index files under
    `ec`, or () where the caterva package (and its index) is not importable."""
    try:
        from caterva.enzymes.index import load_index
    except ImportError:
        return ()
    try:
        entry = load_index().get(ec)
    except Exception:  # an index that cannot be read names nothing
        return ()
    if entry is None:
        return ()
    return tuple((p.accession, p.label, code)
                 for code, proteins in entry.proteins.items() for p in proteins)


def isoforms_of_accessions(ec: Optional[str], cell: Optional[str]) -> tuple:
    """The gene symbols (as the enzyme index labels them) of the proteins a
    row's own UniProt cell names under `ec`, or () when any accession is not
    one the index files under that EC (then the column cannot say which
    protein the row measured) or the cell names none.

    P35557 under EC 2.7.1.1 is ("GCK",); "P20815,Q9HB55" under 1.14.14.1 is
    ("CYP3A5", "CYP3A43")."""
    found = accessions(cell)
    if not ec or not found:
        return ()
    labels = {acc: label for acc, label, _ in _labels_of_ec(ec)}
    if not all(a in labels for a in found):
        return ()
    return tuple(dict.fromkeys(labels[a] for a in found))


def sole_protein(ec: Optional[str], organism: Optional[str]) -> Optional[str]:
    """The gene symbol of the one protein the enzyme index files under `ec`
    in `organism`, or None when it files none or several (or the index is
    not importable).

    "isoform CELA1, at pH 8.0 and 22°C" (pig pancreatic elastase, ref
    754151) names CELA1, the only pig protein of EC 3.4.21.36: the row is
    the enzyme, not an isozyme of it, and was withheld as "a named isozyme"
    while 4-nitrophenyl acetate's esterase rows were modelled (fourth round
    of the real-values review)."""
    if not ec or not organism:
        return None
    try:
        from caterva.enzymes.index import load_index, organism_code
    except ImportError:  # pragma: no cover - the flat layout
        return None
    code = organism_code(organism)
    entry = load_index().get(ec) if code else None
    proteins = (entry.proteins.get(code, ()) if entry else ())
    return proteins[0].symbol if len(proteins) == 1 else None


def is_sole_protein(ec: Optional[str], organism: Optional[str], reading: Optional[str]) -> bool:
    """Whether an isoform `reading` names the only protein of `ec` in
    `organism` (`sole_protein`), by the isoform reader's comparison."""
    sole = sole_protein(ec, organism)
    if not (sole and reading):
        return False
    try:
        from caterva.bind.core import same_isoform
    except ImportError:  # pragma: no cover
        return False
    return same_isoform(reading, sole)


def proteins_in_organism_of(ec: Optional[str], cell: Optional[str]) -> int:
    """How many proteins the index files under `ec` in the organism of the
    row's first accession: a row naming GCK is worth naming when the EC is
    five human proteins."""
    found = accessions(cell)
    if not ec or not found:
        return 0
    entries = _labels_of_ec(ec)
    code = next((c for acc, _, c in entries if acc == found[0]), None)
    return sum(1 for _, _, c in entries if c == code) if code else 0


#: A subunit gene symbol: a family and one subunit letter ("frdA", "sdhB",
#: "SDHA").
_SUBUNIT_SYMBOL = re.compile(r"^([A-Za-z]{3})([A-Z])$")


@functools.lru_cache(maxsize=512)
def _enzyme_name_of(ec: str) -> str:
    try:
        from caterva.enzymes.index import load_index
        entry = load_index().get(ec)
    except Exception:  # noqa: BLE001 - no index, no name
        return ""
    return (getattr(entry, "name", None) or "") if entry else ""


def other_enzyme(ec: Optional[str], cell: Optional[str]) -> Optional[str]:
    """The gene symbol of the protein a row's own UniProt cell names when it
    is a subunit of ANOTHER enzyme filed under `ec`, else None.

    EC 1.3.5.1 holds four E. coli entries, frdA and frdB (fumarate
    reductase) and sdhA and sdhB (succinate dehydrogenase). A malonate Ki
    row naming P00363 (FrdA, ref 674532) was carried beside succinate:quinone
    reductase's Km and kcat as "the row measured isoform frdA", and made E.
    coli the organism that "covers 3 of 3" constants (fifth round of the
    real-values review). Read only where the organism's entries under the EC
    are two or more subunit families ("frd", "sdh") and exactly one family's
    letters begin the initials of the EC's name ("succinate dehydrogenase":
    "sd"); a row of another family is another enzyme's, not an isoform."""
    found = accessions(cell)
    if not ec or not found:
        return None
    entries = _labels_of_ec(ec)
    labels = {acc: (label, code) for acc, label, code in entries}
    if not all(a in labels for a in found):
        return None
    code = labels[found[0]][1]
    families = {}
    for _, label, c in entries:
        m = _SUBUNIT_SYMBOL.match(label or "")
        if c == code and m:
            families.setdefault(m.group(1).lower(), []).append(label)
    if len(families) < 2:
        return None
    words = re.findall(r"[a-z]+", _enzyme_name_of(ec).lower())
    initials = "".join(w[0] for w in words)
    own = [f for f in families if initials and (f.startswith(initials) or initials.startswith(f))]
    if len(own) != 1:
        return None
    mine = {(_SUBUNIT_SYMBOL.match(labels[a][0]) or [None, None])[1] for a in found}
    mine = {f.lower() for f in mine if f}
    if mine and own[0] not in mine:
        return " and ".join(dict.fromkeys(labels[a][0] for a in found))
    return None


#: The isoforms of an EC that a tissue names: "muscle" pyruvate kinase is
#: PKM. `caterva compose` reads a description's tissue word by this table,
#: and the resolver a row's ("heart phosphorylase").
TISSUE_ISOFORMS = {
    "2.7.1.40": {"muscle": ("PKM", " (PKM1 and PKM2 are its splice forms)"),
                 "liver": ("PKLR", " (the L form)"), "erythrocyte": ("PKLR", " (the R form)"),
                 "red cell": ("PKLR", " (the R form)")},
    "4.1.2.13": {"muscle": ("ALDOA", " (aldolase A)"), "liver": ("ALDOB", " (aldolase B)"),
                 "brain": ("ALDOC", " (aldolase C)")},
    "1.1.1.27": {"muscle": ("LDHA", " (the M subunit, LDH-5 as the tetramer)"),
                 "heart": ("LDHB", " (the H subunit, LDH-1 as the tetramer)")},
    "2.7.3.2": {"muscle": ("CKM", " (CK-M)"), "brain": ("CKB", " (CK-B)")},
    "2.4.1.1": {"muscle": ("PYGM", ""), "liver": ("PYGL", ""), "brain": ("PYGB", "")},
    "2.7.1.11": {"muscle": ("PFKM", ""), "liver": ("PFKL", ""), "platelet": ("PFKP", "")},
}

_ROW_TISSUE = re.compile(
    r"\b(skeletal\s+muscle|muscle|liver|heart|cardiac|brain|erythrocyte|red\s+cell|platelet|kidney)"
    r"\s+(?:\w+\s+){0,1}?(?:enzyme|isozymes?|isoenzymes?|isoforms?|form|phosphorylases?|kinases?"
    r"|aldolases?|dehydrogenases?)\b", re.IGNORECASE)


def tissue_isoform_of_row(ec: Optional[str], commentary: Optional[str]) -> Optional[str]:
    """The isoform a row's commentary names by its tissue ("heart
    phosphorylase I and III", "liver enzyme"), for an EC whose tissue
    isoforms are listed: the listed isoform, or "the <tissue> form" for a
    tissue the table does not list. None for a row naming no tissue's
    enzyme, or an EC with no listed tissue isoforms.

    Rabbit glycogen phosphorylase, asked for as "from rabbit muscle" (PYGM):
    the Km carried was 6.0 mM, "heart phosphorylase I and III" (ref 488283),
    said to name no isoform (fifth round of the real-values review)."""
    table = TISSUE_ISOFORMS.get(ec or "")
    if not table:
        return None
    m = _ROW_TISSUE.search(commentary or "")
    if not m:
        return None
    tissue = " ".join(m.group(1).lower().split())
    tissue = {"skeletal muscle": "muscle", "cardiac": "heart"}.get(tissue, tissue)
    if tissue in table:
        return table[tissue][0]
    return f"the {tissue} form"


# -- Isoform from the paper's other entries -------------------------------------------

#: The tables of a BRENDA page whose rows say which protein one reference
#: studied: the synonyms a paper used, the organism table's accessions, and
#: the commentary of its other measurements.
_PAPER_TABLES = ("Synonyms", "Organisms", "KM Values", "Turnover Numbers", "kcat/KM Values",
                 "Ki Values", "IC50 Values", "Specific Activity", "Protein Variants")
_REFERENCES = re.compile(r"^\d{1,7}(?:\s*,\s*\d{1,7})*$")
_BINOMIAL = re.compile(r"[A-Z][a-z]+ [a-z][a-z.-]+(?: [a-z.-]+)?")


#: Mutations that mark a paper as one isoform's, per EC number: a paper
#: whose rows study them measured that protein. Human trypsin refs 678332
#: and 682760 hold the R193G/A/F/Y series, Arg193 being what sets
#: mesotrypsin (PRSS3) apart (cationic trypsin has Gly193), and their
#: wild-type row was carried under --isoform PRSS1 (fifth round, S5-01).
#: Ref 672188's "mutant enzyme Y214C" is a glucokinase (GCK) mutation, and
#: its wild-type kcat was paired with HK1's Km (R5V1-3).
ISOFORM_MUTATIONS = {
    "3.4.21.4": ((re.compile(r"\bR193[A-Z]\b"), "PRSS3"),),
    "2.7.1.1": ((re.compile(r"\b(?:Y214C|T228M|V455M|A456V|G261R|E300K|R186X|W99R)\b"), "GCK"),),
}


def paper_isoforms(ec: Optional[str], html: str) -> dict:
    """{(organism, reference): (isoform, ...)}: the isoforms each reference's
    rows name anywhere among `_PAPER_TABLES` of the page, by their words
    (caterva's isoform reader) or by their own UniProt cell, one organism at
    a time (the organism lower-cased as its row cell spells it).

    A row naming no isoform is not thereby of unknown protein: BRENDA's
    "67.6 | D-glucose | Homo sapiens | - | wild-type, 37°C | 722237" names
    none, and the same paper's synonyms ("hGK", "glucokinase") and its
    mutants (T228M, the MODY mutation) are glucokinase's. That row was
    carried as HK1's and HK2's kcat with "names no isoform" (the second
    adversarial round's review, 2026-11-12). {} where the page or caterva's
    isoform reader cannot be read."""
    try:
        from bs4 import BeautifulSoup
        from caterva.bind.core import read_isoform
        from brenda_client import _find_table_container
    except ImportError:
        return {}
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return {}
    found: dict = {}
    for label in _PAPER_TABLES:
        table = _find_table_container(soup, label)
        if table is None:
            continue
        for row in table.find_all("div", id=re.compile(r"r\d+(?:sr\d+)?$")):
            cells = [c.get_text(" ", strip=True) for c in row.find_all("div", recursive=False)]
            refs_cell = next((c for c in reversed(cells) if _REFERENCES.match(c or "")), None)
            if not refs_cell:
                continue
            refs = [r.strip() for r in refs_cell.split(",") if r.strip()]
            organism = next((c for c in cells if _BINOMIAL.fullmatch(c or "")), None)
            if organism is None:
                continue
            readings = []
            cell = next((c for c in cells if accessions(c) and not _REFERENCES.match(c)), None)
            if cell and len(accessions(cell)) == 1 and proteins_in_organism_of(ec, cell) > 1:
                readings.extend(isoforms_of_accessions(ec, cell))
            texts = [c for c in cells if c not in (refs_cell, organism, cell)]
            if label not in ("Synonyms", "Organisms"):
                # The commentary only: a kinetic row's first cells are its
                # value and its compound.
                texts = texts[2:]
            for text in texts:
                try:
                    reading = read_isoform(text)
                except Exception:
                    reading = None
                if reading:
                    readings.append(reading)
                for marker, isoform in ISOFORM_MUTATIONS.get(ec or "", ()):
                    if marker.search(text or "") and isoform not in readings:
                        readings.append(isoform)
            for ref in refs:
                kept = found.setdefault((organism.lower(), ref), [])
                for reading in readings:
                    if reading not in kept:
                        kept.append(reading)
    return {key: tuple(value) for key, value in found.items()}


def distinct_isoforms(readings, same) -> list:
    """`readings` with each isoform once, by `same` (an isoform comparison),
    in the order first named."""
    distinct: list = []
    for reading in readings or ():
        if not any(reading == kept or same(reading, kept) for kept in distinct):
            distinct.append(reading)
    return distinct


def one_isoform(readings, same) -> Optional[str]:
    """The one isoform `readings` name, by `same` (an isoform comparison),
    or None when they name none or several."""
    distinct = distinct_isoforms(readings, same)
    return distinct[0] if len(distinct) == 1 else None


# -- Matching a Km row with a kcat row ---------------------------------------------

_WORD = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")
#: Words that say which table a row is in, not what was measured.
_TABLE_WORDS = frozenset({"km", "kcat", "value", "values", "turnover", "number", "numbers",
                          "s", "mm", "min", "sec", "the", "for", "of", "and", "at", "in", "c",
                          "degrees", "a", "an", "with", "constant", "michaelis",
                          # "enzyme ALDH-2, pH 9.5" and "enzyme form ALDH-2, pH
                          # 9.5" (ref 348688) are one assay (fifth round).
                          "form"})


_HALF_SATURATION_STATEMENT = re.compile(
    r"\b[ks]\s*\(?\s*0\.5\s*\)?(?:\s+values?)?(?![\w.])"
    r"|\bhill\s+coefficient\s*(?:of|=|:)?\s*\d+(?:\.\d+)?|\bnh\s*[=:]?\s*\d+(?:\.\d+)?")
#: A name and its number written apart ("Adh 1"), not a pH or a temperature.
_NAME_NUMBER = re.compile(r"\b(?!pH\b)([A-Z][A-Za-z]+)\s+(\d+)\b(?![.\d])")


def condition_words(conditions: Optional[str], substrate: Optional[str] = None) -> frozenset:
    """The words of a row's commentary that say what was measured, for
    comparing a Km row with a kcat row of one paper: "pH 8, 25°C, 200 mM NaCl"
    and "pH 8, 25°C, 200 mM choline chloride" differ (thrombin's fast and slow
    forms, ref 709074); "recombinant enzyme, pH 7.5" and "pH 7.5, recombinant
    enzyme" do not."""
    # "Adh 1" and "Adh1" are one name (horse liver ADH, ref 285647): a
    # capitalised name and its number written apart.
    text = _NAME_NUMBER.sub(r"\1\2", conditions or "")
    text = text.lower().replace("°", " ")
    # How the constant is reported is not what was measured: BRENDA copies
    # "K0.5 value, Hill coefficient 1.8" onto only some of a paper's rows of
    # one assay (glucokinase, ref 739603).
    text = _HALF_SATURATION_STATEMENT.sub(" ", text)
    words = set(_WORD.findall(text)) - _TABLE_WORDS
    if substrate:
        words -= set(_WORD.findall(substrate.lower()))
    return frozenset(words)


#: A pH BRENDA printed with a typo in its decimal ("pH 4.u", HIV-1 protease,
#: ref 648156): the units digit is read, the decimal is not.
_GARBLED_PH = re.compile(r"\bpH\s*(\d{1,2})\.(?![\d\s])[^\s,;]*", re.IGNORECASE)
_STATED_PH = re.compile(r"\bpH\s*\d{1,2}(?:\.\d+)?", re.IGNORECASE)


def garbled_ph(conditions: Optional[str]) -> Optional[int]:
    """The units digit of a pH whose decimal is unreadable ("pH 4.u" is 4),
    or None when the commentary states none so garbled."""
    m = _GARBLED_PH.search(conditions or "")
    return int(m.group(1)) if m else None


def same_measurement(a: dict, b: dict, substrate: Optional[str] = None) -> bool:
    """Whether two rows (dicts with conditions, ph, temperature_c) were
    measured under one set of stated conditions: the same pH and temperature
    (both stated alike, or both unstated) and the same remaining words.

    A pH whose decimal BRENDA printed unreadably ("pH 4.u") is unknown, not
    different: it matches a stated pH with the same units digit when the
    remaining words agree. HIV-1 protease, ref 648156: Km 0.0152 mM "pH 4.u,
    0.1 M NaCl" and kcat 5.8 1/s "pH 4.8, 0.1 M NaCl" were never paired, and
    the 1.0 M NaCl pair was carried (fifth round of the real-values review)."""
    def close(x, y, tol):
        if x is None or y is None:
            return x is None and y is None
        return abs(float(x) - float(y)) <= tol
    ph_a, ph_b = a.get("ph"), b.get("ph")
    words_a, words_b = a.get("conditions"), b.get("conditions")
    for theirs, text, other in ((ph_b, words_a, words_b), (ph_a, words_b, words_a)):
        # The parser may read "pH 4.u" as 4.0 or as nothing: either way the
        # garbled row's own pH is not compared.
        digit = garbled_ph(text)
        if (digit is not None and theirs is not None and garbled_ph(other) is None
                and int(float(theirs)) == digit):
            ph_a = ph_b = theirs
            words_a = _STATED_PH.sub("pH", _GARBLED_PH.sub("pH", words_a or ""))
            words_b = _STATED_PH.sub("pH", _GARBLED_PH.sub("pH", words_b or ""))
            break
    return (close(ph_a, ph_b, 0.05)
            and close(a.get("temperature_c"), b.get("temperature_c"), 0.5)
            and condition_words(words_a, substrate)
            == condition_words(words_b, substrate))


def distinct_values(rows: Iterable[dict]) -> set:
    return {float(r["value"]) for r in rows}


__all__ = [
    "accessions", "condition_words", "construct_of", "half_saturation", "is_ion",
    "isoforms_of_accessions", "proteins_in_organism_of", "same_measurement",
]
