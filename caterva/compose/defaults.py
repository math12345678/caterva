"""When a sentence names an enzyme and stops, choose the best-measured rest of it, out loud.

WHY THIS EXISTS
---------------
On 2026-11-11 fifty-six descriptions a professor would type were run
through `caterva compose` on main. Seven came back fully measured. Twenty-six
of the rest named an enzyme and nothing else -- "hexokinase Michaelis-Menten
kinetics in human", "acetylcholinesterase from human" -- and every one was
refused before a single table was read, because a Km is per-substrate and no
substrate was named (ADR 0178). The data was there each time: D-glucose has
25 human Km rows and 61 kcat rows on BRENDA's hexokinase page, and the
refusal itself listed it. A person reading "placeholder, placeholder,
placeholder" under a report that names the substrate with 25 measurements
concludes the tool never uses real data, and they are not wrong.

ADR 0182 changes the rule: when the user names an enzyme and not its
substrate, inhibitor or organism, Caterva CHOOSES the best-measured real
option BRENDA holds, runs with real cited values, and says in the report
what it chose, why, and what else was there with its row counts, so the
choice is the reader's to overturn with one flag.

WHAT A CHOICE MAY AND MAY NOT DO
--------------------------------
It picks which question to answer; it never changes an answer. Every value
the search then cites is a real BRENDA row for exactly the compound and
organism named beside it, because the choice is made BEFORE the search and
handed to it as if the user had typed the flag: the resolver matches rows to
that name as it always has, and nothing here relabels a neighbour's row
(ADR 0076). A flag or a compound the sentence named always wins over a
choice. An organism the user NAMED is never switched for a better-measured
one: when it has no rows, the report says the organism is the blocker and
lists the organisms that have rows, instead of advising a substrate that
would not help.

HOW EACH IS RANKED
------------------
All three are read from the one BRENDA page the search reads anyway
(`fetch_brenda_html`, memoised in-process by the literature layer's
http_retry), parsed by the same functions the resolver uses, in permissive
mode (`require_substrate_match=False`).

A COUNT IS A COUNT OF ROWS THE SEARCH CAN USE (`_usable`), by the
resolver's own steps in its order: never a flagged row; with an isoform
(--isoform, or a gene symbol read as one), the rows naming it, or where none
does the rows naming no isoform (and not one whose single UniProt accession
is another protein); then no variant's row (an isozyme row only when it is
the isoform asked for); then, for a Ki, not a row of another inhibition mode
than the model's. Until 2026-11-12 every row was counted, and the choice
fell on options whose every row the search then withheld: "3',5'-cGMP" for
PDE5 (its one row PDE6C's), 7-ethoxyresorufin for CYP3A4 (CYP1A1's), a
PTP1B inhibitor whose seven Ki rows were all an engineered mutant's, and a
granzyme B substrate "with the most rows" of which two were mutants'.

- Substrate: cosubstrates and cofactors (ATP, NAD+, CoA, water, metal ions
  ...) are set aside unless nothing else has rows, because "hexokinase on
  ATP" is not what anyone means by hexokinase kinetics, though ATP has the
  most rows. Then one with a usable Km row; then, with an isoform, one whose
  rows name it; then one the search can be asked for without also taking a
  neighbour's rows ("Luciferin" takes D-luciferin's, and the value it then
  returns is withheld as another compound's, `neighbour_of`); then one
  with BOTH a Km and a kcat row (when the model needs a kcat), then one
  BRENDA files as a natural substrate (or a stereo form of one it names
  loosely), then the most Km + kcat rows, then the most BRENDA references,
  then the name -- and a tie that only the name broke is said to be one.
- Inhibitor: compounds with usable Ki rows in the organism, the chosen
  substrate excluded; a substrate or product of the reaction (D-glucose
  6-phosphate for hexokinase is product inhibition) is set aside when any
  other compound has a row, and so is a cofactor; then, with an isoform,
  one whose rows name it; then one without neighbours; then the most Ki
  rows, the most references, the name.
- Organism (none named): Homo sapiens when it has rows for every constant
  the model needs; otherwise the organism covering the most of them, then
  the most rows, then the name. Never one with no row for the substrate
  named or chosen. An organism BRENDA writes as no binomial ("influenza A
  virus H1N1") is counted under its own cell (`_unlabelled_rows`).

ONE COMPOUND, SEVERAL SPELLINGS (`_group_key`): case, whitespace and a
counter-ion aside (as the resolver compares names), a hyphen before a stereo
descriptor ("2-nitrophenyl-beta-D-galactopyranoside"), a letter locant
("p-nitrophenyl phosphate" is 4-nitrophenyl phosphate), and a cyclic
nucleotide's 3',5' locants ("3',5'-cGMP" is cGMP) are one compound, counted
together and searched under the spelling with the most usable rows; the
note names the other spellings. Anything subtler ("Z-" and
"N-benzyloxycarbonyl-") is left as BRENDA wrote it, because merging names is
a chemical judgement this module cannot make.
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

#: The roles a choice is made for, in the order compose makes them.
ROLES = ("enzyme", "organism", "substrate", "inhibitor")

#: How many alternatives a choice names. Enough to switch, few enough to read.
ALTERNATIVES_NAMED = 5

#: The table each constant is read from, by the name the report uses for it.
TABLE_NAMES = {"km": "Km", "kcat": "kcat", "ki": "Ki"}

#: The organism a choice prefers when it covers every constant the model
#: needs: most readers of a kinetics report are asking about a human enzyme,
#: and the one tie-break that is not a row count is stated in every note.
PREFERRED_ORGANISM = "Homo sapiens"

#: An enzyme name that is a few enzymes is taken as the one with rows only
#: when it has at least this many times the rows of every other candidate.
DOMINANCE = 5

#: At most this many candidates for an ambiguous name are looked up.
ENZYME_CANDIDATES_CONSIDERED = 4

#: Cosubstrates, cofactors and small ions, compared after casefolding and
#: with an alpha-/beta- prefix set aside. Not a judgement that they are not
#: substrates (they are), only that "the kinetics of hexokinase" is not a
#: question about its ATP.
COFACTORS = frozenset({
    "atp", "adp", "amp", "gtp", "gdp", "gmp", "ctp", "cdp", "utp", "udp", "ttp",
    "mgatp", "mg-atp", "mgatp2-", "mgadp", "mg-adp", "mgadp-",
    "nad+", "nad", "nadh", "nadp+", "nadp", "nadph", "fad", "fadh2", "fmn", "fmnh2",
    "coa", "coenzyme a", "h2o", "water", "h+", "proton", "phosphate", "orthophosphate",
    "diphosphate", "pyrophosphate", "s-adenosyl-l-methionine", "s-adenosylmethionine",
    # O2 is an oxidase's cosubstrate; CO2 is deliberately absent, because
    # it is carbonic anhydrase's substrate.
    "s-adenosyl-l-homocysteine", "o2",
})
_METAL_ION = re.compile(
    r"^(?:mg|mn|ca|zn|fe|co|ni|cu|k|na|li|cd|ba|sr|cl|hco3)(?:\d?[+-])+$", re.IGNORECASE)
_PREFIX = re.compile(r"^(?:alpha|beta|α|β)-", re.IGNORECASE)
#: The every-organism parse's own test of an organism cell
#: (brenda_client.GENERIC_ORGANISM_PATTERN), restated so this module reads it
#: without importing the literature layer.
_BINOMIAL = re.compile(r"[A-Z][a-z]{2,}(?:\s[a-z]{2,}){1,2}")

#: An EC number as BRENDA files one: four fields, the last possibly
#: preliminary ("n3") or unassigned ("-").
EC_NUMBER = re.compile(r"\d{1,2}\.\d{1,3}\.\d{1,3}\.(?:n?\d{1,4}|-)")

#: Words in a Ki row's commentary that state an inhibition mode, longest first.
_MODE = re.compile(r"\b(non-?competitive|un-?competitive|mixed(?:-type)?|competitive)\b",
                   re.IGNORECASE)


#: An option whose rows the search cannot use, in a note.
USABLE_NONE = "no usable row"


@dataclass(frozen=True)
class Option:
    """One thing that could have been chosen, with the rows behind it."""

    name: str
    #: table -> row count ({"km": 25, "kcat": 61} or {"ki": 7}).
    rows: Dict[str, int] = field(default_factory=dict)
    #: What the note says when every count is zero: a substrate or
    #: inhibitor counts only rows the search can use, so it has "no usable
    #: row" while BRENDA may list rows for it.
    none_said: str = "no rows"

    def describe(self) -> str:
        parts = [f"{n} {TABLE_NAMES.get(t, t)}" for t, n in self.rows.items() if n]
        return f"{self.name} ({', '.join(parts) if parts else self.none_said})"


@dataclass(frozen=True)
class Choice:
    """What Caterva chose for something the user did not name, and why."""

    #: "substrate" | "inhibitor" | "organism" | "enzyme".
    role: str
    chosen: str
    #: The reason, as a clause: "of the 10 substrates BRENDA lists ...".
    why: str
    #: The next-best options, best first, each with its row counts.
    alternatives: Tuple[Option, ...] = ()
    #: How many options were weighed in all, the chosen one included.
    considered: int = 0
    #: The row counts behind the chosen option, for the note's parenthesis.
    rows: Dict[str, int] = field(default_factory=dict)
    #: When the user DID name something and it could not be used, the
    #: clause that says so ("'glucose 6-phosphate' in your description is
    #: not a substrate BRENDA lists ..."): the note then opens with it
    #: instead of "No substrate was named", which would be false.
    instead: Optional[str] = None

    def to_json(self) -> dict:
        return {
            "role": self.role,
            "chosen": self.chosen,
            "why": self.why,
            "alternatives": [{"name": o.name, "rows": dict(o.rows)} for o in self.alternatives],
            "considered": self.considered,
            # The chosen option's own usable rows, and the clause saying a
            # word the user typed was set aside (None when nothing was):
            # a page shows both without parsing the note.
            "rows": dict(self.rows),
            "instead": self.instead,
        }

    def note(self) -> str:
        """The plain-English note the report carries for this choice."""
        flag = {"enzyme": "--subject EC", "organism": "--organism NAME",
                "substrate": "--substrate NAME", "inhibitor": "--inhibitor NAME"}[self.role]
        if self.role == "enzyme":
            head = f"Caterva used EC {self.chosen}: {self.why}."
        elif self.instead:
            head = f"{self.instead}, so Caterva used {self.chosen}: {self.why}."
        else:
            head = f"No {self.role} was named, so Caterva used {self.chosen}: {self.why}."
        if self.alternatives:
            head += " Others: " + "; ".join(o.describe() for o in self.alternatives)
            more = self.considered - 1 - len(self.alternatives)
            head += f"; and {more} more." if more > 0 else "."
        return head + f" Pass {flag} to model another."


# ---------------------------------------------------------------------------
# Reading the page: one fetch, each table parsed once
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Row:
    compound: str
    organism: Optional[str]
    conditions: str
    #: The row's value and BRENDA reference, so a value the search returned
    #: can be traced back to the row, and the compound, it came from
    #: (`neighbour_of`).
    value: Optional[float] = None
    reference_id: Optional[str] = None
    #: BRENDA's UniProt cell ("O76074"; several comma-separated, or None).
    uniprot: Optional[str] = None
    #: The literature layer's variant verdict: True when the commentary says
    #: the row measured a variant (`protein_variant.classify`), and whether
    #: that variant is an isozyme. The resolver withholds such rows
    #: (`fallback_logic._partition_variants`) unless an isozyme row is the
    #: isoform asked for.
    variant: bool = False
    isozyme: bool = False
    #: A row the parser flagged as implausible; the resolver never uses one.
    flagged: bool = False
    #: The row measured the native enzyme's own constant: not a construct or
    #: altered preparation, not with an inhibitor or effector its commentary
    #: names present, and (for a Km) not a K0.5. The resolver passes the
    #: others over when a compound has such a row (fallback_logic
    #: `_best_evidenced`, row_form.py, ADR 0182's second round), so a
    #: compound with none ranks after one with some (`_own`).
    own: bool = True


#: (client, page digest, ec, table, organism) -> rows. A page fetched again
#: (a new process, or the memo cleared) is a new digest, so a stale parse is
#: never served for a page that changed; the client is in the key so a test
#: that serves a page through another client never reads this one's parse.
_PARSED: Dict[Tuple[int, str, str, str, Optional[str]], Tuple[_Row, ...]] = {}
_PARSED_MAX = 64


def _client():
    from caterva.checkout import literature_module

    return literature_module("brenda_client")


def _page(ec: str) -> str:
    return _client().fetch_brenda_html(ec)


def _digest(html: str) -> str:
    return hashlib.sha1(html.encode("utf-8", "replace")).hexdigest()


def table_rows(ec: str, table: str, organism: Optional[str]) -> Tuple[_Row, ...]:
    """Every row of BRENDA's `table` ("km", "kcat", "ki") for `ec`, for
    `organism` (or every organism, None). Raises when the page cannot be
    read; a page without that table gives no rows.

    Only rows found inside the table's own container count: when the
    container is absent the parser scans the whole page and returns rows of
    other tables (580 "kcat" rows for EC 2.7.10.1, which has no Turnover
    Numbers table), and counting those would choose a substrate for
    measurements that do not exist.

    Every organism (None) includes the rows whose organism cell is not a
    binomial ("influenza A virus H1N1"), labelled with that cell
    (`_unlabelled_rows`): the parser's every-organism mode drops them, and
    "neuraminidase inhibited by oseltamivir" was then modelled in Homo
    sapiens, with no oseltamivir Ki, while BRENDA holds influenza rows for
    Km, kcat and the oseltamivir Ki (2026-11-11).
    """
    client = _client()
    html = _page(ec)
    key = (id(client), _digest(html), ec, table, organism)
    if key in _PARSED:
        return _PARSED[key]
    # An organism's rows are the every-organism parse filtered, when that
    # parse is already made: one parse per table instead of two. Only for a
    # plain binomial: the every-organism parse labels a row only when its
    # organism cell is one ("Human immunodeficiency virus 1" is not), while
    # the organism's own parse matches the name anywhere in the row.
    every = (id(client), _digest(html), ec, table, None)
    if organism and every in _PARSED and _BINOMIAL.fullmatch(organism):
        out = tuple(r for r in _PARSED[every] if r.organism == organism)
    else:
        parse = {"km": client.parse_brenda_km_html,
                 "kcat": getattr(client, "parse_brenda_turnover_html", None),
                 "ki": getattr(client, "parse_brenda_ki_html", None)}[table]
        if parse is None:
            raise LookupError(f"this literature layer cannot read BRENDA's {table} table")
        parsed = parse(html, ec, [], organism, require_substrate_match=False)
        out = tuple(
            _Row(str(r.substrate), getattr(r, "organism", None) or organism,
                 str(getattr(r, "conditions", "") or ""),
                 _number(getattr(r, "km_value", None)),
                 None if getattr(r, "reference_id", None) is None else str(r.reference_id),
                 getattr(r, "uniprot", None) or None,
                 *_variant_of(getattr(r, "variant", None)),
                 bool(getattr(r, "flagged", False)),
                 _own(table, str(getattr(r, "conditions", "") or ""), getattr(r, "effectors", None)))
            for r in parsed
            if getattr(r, "table_scoped", True) and getattr(r, "substrate", None)
            and str(r.substrate) != "unknown compound"
        )
        if organism is None:
            out = out + _unlabelled_rows(html, ec, table, client)
        elif not _BINOMIAL.fullmatch(organism):
            # A name that is no binomial is matched anywhere in the row, so
            # "influenza A virus" also took the rows of "influenza A virus
            # H1N1", another organism to the search: oseltamivir was chosen
            # for influenza A virus on an H1N1 row, and the search, finding
            # its Ki in two organisms, settled on none (2026-11-12).
            out = tuple(r for r in out if r.organism == organism)
        out = tuple(r for r in out if _is_compound(r.compound, r.conditions))
    if len(_PARSED) >= _PARSED_MAX:
        _PARSED.clear()
    _PARSED[key] = out
    return out


def _own(table: str, conditions: str, effectors: object = None) -> bool:
    """Whether a row measured the native enzyme's own constant, read as the
    resolver reads it (row_form.construct_of, row_form.half_saturation, and
    the effectors the commentary names present as an inhibitor, activator
    or effector: fallback_logic `_inhibited`). True where the literature
    layer's readers are not importable: then nothing is set aside here that
    the resolver would not set aside too."""
    try:
        from caterva.checkout import literature_module

        row_form = literature_module("row_form")
        if effectors is None:
            effectors = literature_module("effector").extract_effectors(conditions)
    except Exception:  # noqa: BLE001 - a preference, never a requirement
        return True
    if row_form.construct_of(conditions):
        return False
    if table == "km" and row_form.half_saturation(conditions):
        return False
    return not any(getattr(x, "presence", None) == "present" and getattr(x, "named", False)
                   and getattr(x, "role", None) in ("inhibitor", "activator", "effector")
                   and not row_form.is_ion(getattr(x, "compound_text", ""))
                   for x in (effectors or []))


def _variant_of(verdict: object) -> Tuple[bool, bool]:
    """(is a variant, is an isozyme) from a `protein_variant` verdict."""
    if verdict is None or getattr(verdict, "status", None) != "variant":
        return False, False
    return True, getattr(verdict, "kind", None) == "isozyme"


def _text(cell: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", cell).split())


def _unlabelled_rows(html: str, ec: str, table: str, client: object) -> Tuple[_Row, ...]:
    """The rows of `table` whose organism cell the every-organism parse
    cannot label (no cell of the row is a binomial), labelled with the
    organism cell as BRENDA writes it.

    Read cell by cell (`id="tab<N>r<row>[sr<sub>]c<cell>"`: value, compound,
    organism, UniProt, commentary, reference) by a regular expression, the
    way `_organisms_on_page` reads the organism cells: a parse of a
    four-megabyte page per virus would cost seconds each, and the
    neuraminidase page has ten such organisms. These rows rank organisms;
    once one is chosen its rows are parsed by name like any other's.
    """
    match = re.search(r"showTable\('(tab\d+)'\)\">" + re.escape(_TABLE_LABELS[table]) + "<", html)
    if not match:
        return ()
    pattern = getattr(client, "GENERIC_ORGANISM_PATTERN", _BINOMIAL)
    classify = getattr(client, "classify_variant", None)
    cells: Dict[str, Dict[int, str]] = {}
    for row_id, index, cell in re.findall(
            r'<div id="(' + match.group(1) + r'r\d+(?:sr\d+)?)c(\d+)"[^>]*>(.*?)</div>', html, flags=re.S):
        cells.setdefault(row_id, {})[int(index)] = _text(cell)
    out = []
    for row in cells.values():
        texts = [row.get(i, "") for i in range(max(row) + 1)]
        if len(texts) < 3 or not re.fullmatch(r"\d+\.?\d*", texts[0]):
            continue
        if any(pattern.fullmatch(t) for t in texts):
            continue  # the parser labelled this row itself
        compound, organism = texts[1], texts[2]
        if not compound or compound == "-" or not organism or organism == "-" \
                or re.fullmatch(r"\d+ entries", organism):
            continue
        conditions = texts[4] if len(texts) > 4 and texts[4] != "-" else ""
        reference = re.match(r"\d+", texts[5]) if len(texts) > 5 else None
        uniprot = texts[3] if len(texts) > 3 and texts[3] not in ("", "-") else None
        verdict = classify(conditions) if callable(classify) else None
        value = float(texts[0])
        out.append(_Row(compound, organism, conditions, value,
                        reference.group(0) if reference else None, uniprot, *_variant_of(verdict),
                        _implausible(client, table, value, conditions), _own(table, conditions)))
    return tuple(out)


#: The parser's plausibility bounds per table (brenda_client), by name.
_BOUNDS = {"km": ("KM_PLAUSIBLE_MIN_MM", "KM_PLAUSIBLE_MAX_MM"),
           "ki": ("KM_PLAUSIBLE_MIN_MM", "KM_PLAUSIBLE_MAX_MM"),
           "kcat": ("KCAT_PLAUSIBLE_MIN_PER_S", "KCAT_PLAUSIBLE_MAX_PER_S")}


def _implausible(client: object, table: str, value: float, conditions: str) -> bool:
    """Whether the parser would flag this row (brenda_client's checks: a
    value outside its plausible range, a Km whose commentary names kcat),
    so a row read cell by cell is withheld as the search withholds it. The
    zanamivir Ki of "influenza A virus" (6e-08 mM, below the parser's floor)
    was counted, that organism chosen for it, and the search then found no
    usable row and left the Ki a placeholder (2026-11-12)."""
    low, high = (getattr(client, name, None) for name in _BOUNDS.get(table, ("", "")))
    if isinstance(low, (int, float)) and value < low:
        return True
    if isinstance(high, (int, float)) and value > high:
        return True
    return table == "km" and bool(re.search(r"\bkcat\b", conditions or "", re.IGNORECASE))


#: A compound cell that is commentary: the parser, finding a row's compound
#: cell empty, takes the next text, and "pH and temperature not specified in
#: the publication" was offered as an HDAC8 inhibitor with 3 Ki rows
#: (2026-11-12). Such a row is no compound's and is not counted.
_COMMENTARY = re.compile(r"not specified in the publication|^(?:pH|temperature)\b", re.IGNORECASE)


def _is_compound(name: str, conditions: str) -> bool:
    text = " ".join((name or "").split())
    return bool(text) and not _COMMENTARY.search(text) \
        and text.casefold() != " ".join((conditions or "").split()).casefold()


def _number(value: object) -> Optional[float]:
    try:
        return None if value is None else float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _key(name: str) -> str:
    """Spellings that differ only in case or spacing are one compound:
    "acetyl thiocholine" and "acetylthiocholine" (human AChE's 6500 1/s row,
    ref 649716, was counted as another compound's)."""
    return "".join(name.split()).casefold()


_COFACTOR_KEYS = frozenset(_key(c) for c in COFACTORS)


#: Counter-ions BRENDA writes after a name: the literature layer's own list
#: (brenda_client._COUNTER_ION), restated so this module reads it without
#: importing that layer. The resolver takes "acetylthiocholine iodide" as
#: acetylthiocholine, so the chooser counts it as one compound too.
_COUNTER_ION = re.compile(
    r"\s+(?:iodide|chloride|bromide|perchlorate|hydrochloride|sulfate|"
    r"(?:mono|di|tri)?sodium salt|potassium salt|lithium salt)$", re.IGNORECASE)
#: A hyphen written before a stereo or anomer descriptor, which BRENDA
#: writes with or without: "2-nitrophenyl-beta-D-galactopyranoside" and
#: "2-nitrophenyl beta-D-galactopyranoside" (once the space is gone).
_HYPHEN_BEFORE_DESCRIPTOR = re.compile(
    r"-(?=(?:alpha|beta|gamma|delta|[αβγδ]|[dl]{1,2}|\([0-9a-z,+\-]+\))-)")
#: A 3',5'-cyclic nucleotide written with or without its locants:
#: "3',5'-cGMP" is cGMP. (2',3'-cGMP is another compound and is not this.)
_CYCLIC_NUCLEOTIDE = re.compile(r"(?:3',5'-?)?(?:c|cyclic-?)([agcuti])mp")
#: The same cyclic nucleotide by its nucleoside's name: "adenosine
#: 3',5'-cyclic phosphate" is cAMP, and PDE4 in human listed it beside cAMP
#: as another substrate with 7 Km rows of its own (2026-11-12).
_CYCLIC_NUCLEOSIDE = re.compile(
    r"(adenosine|guanosine|cytidine|uridine|thymidine|inosine)3',5'-?"
    r"(?:cyclic-?(?:mono)?phosphate|cyclicmonophosphate|cyclic-?mono-?phosphate)")
_PRIMES = str.maketrans({"’": "'", "′": "'", "‘": "'"})
#: An ortho-, meta- or para- locant written as a letter ("p-nitrophenyl
#: phosphate") or a number ("4-nitrophenyl phosphate"): one compound, which
#: BRENDA files under both. Lower case only, before case is folded: "O-" is
#: an oxygen substituent ("O-acetyl"), not ortho.
_LETTER_LOCANT = re.compile(r"(?<![A-Za-z0-9])([pom])-(?=[a-z])")
_LOCANT_NUMBER = {"o": "2", "m": "3", "p": "4"}


def _search_key(name: str) -> str:
    """A name as the resolver compares names (brenda_client._substrate_key):
    case, whitespace and a counter-ion aside. The rows one spelling reaches."""
    text = _COUNTER_ION.sub("", " ".join((name or "").split()))
    return re.sub(r"\s+", "", text).casefold()


def _group_key(name: str) -> str:
    """The key spellings of one compound share: case, whitespace and a
    counter-ion aside (as the resolver compares names,
    brenda_client._substrate_key), a hyphen before a stereo descriptor, an
    o-/m-/p- locant written as 2-/3-/4-, and a cyclic nucleotide's 3',5'
    locants. Nothing chemical beyond that:
    "Z-" and "N-benzyloxycarbonyl-" stay two names."""
    text = _COUNTER_ION.sub("", " ".join((name or "").translate(_PRIMES).split()))
    text = _LETTER_LOCANT.sub(lambda m: _LOCANT_NUMBER[m.group(1)] + "-", text)
    key = re.sub(r"\s+", "", text).casefold()
    key = _HYPHEN_BEFORE_DESCRIPTOR.sub("", key)
    cyclic = _CYCLIC_NUCLEOTIDE.fullmatch(key)
    if cyclic:
        return f"c{cyclic.group(1)}mp"
    nucleoside = _CYCLIC_NUCLEOSIDE.fullmatch(key)
    return f"c{nucleoside.group(1)[0]}mp" if nucleoside else key


def _matches(compound: str, target: str) -> bool:
    """Whether the resolver, asked for `target`, takes a row of `compound`
    (brenda_client.substrate_matches: the name whole, a counter-ion aside,
    and a stereo form of a target that names none)."""
    try:
        match = getattr(_client(), "substrate_matches", None)
    except Exception:  # noqa: BLE001 - no literature layer: compare spellings
        match = None
    if match is None:
        return _group_key(compound) == _group_key(target)
    return bool(match(compound, target))


def is_cofactor(name: str) -> bool:
    """True for a cosubstrate, cofactor or small ion (COFACTORS)."""
    key = _PREFIX.sub("", _key(name))
    return key in _COFACTOR_KEYS or bool(_METAL_ION.match(key))


# ---------------------------------------------------------------------------
# Which rows the search can use: the resolver's own steps, in its order
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=8192)
def _isoform_read(conditions: str) -> Optional[str]:
    try:
        from caterva.bind.core import read_isoform
    except ImportError:  # pragma: no cover - flat layout
        return None
    return read_isoform(conditions)


def _same_isoform(a: Optional[str], b: Optional[str]) -> bool:
    from caterva.bind.core import same_isoform

    return same_isoform(a, b)


@functools.lru_cache(maxsize=4096)
def _accession_says(uniprot: Optional[str], isoform: str) -> Optional[bool]:
    """Whether a row's one UniProt accession is the protein `isoform` names
    (True), another protein UniProt knows (False), or cannot tell (None: no
    accession, several, or one this build has no names for)."""
    if not uniprot or "," in uniprot:
        return None
    try:
        from caterva.enzymes.protein_names import info
    except ImportError:  # pragma: no cover
        return None
    found = info(uniprot.strip())
    if found is None or not found.names:
        return None
    return any(_same_isoform(name, isoform) for name in found.names)


@dataclass
class _Usable:
    """What the search can use of one compound's rows in one table."""

    rows: List[_Row]
    #: Some usable row names the isoform asked for, in its commentary or by
    #: its one UniProt accession.
    names_isoform: bool = False
    #: Why rows were not counted: "a variant", "another isoform", "another
    #: inhibition mode" -> how many.
    set_aside: Counter = field(default_factory=Counter)


def _usable(rows: Sequence[_Row], isoform: Optional[str] = None, mode: Optional[str] = None,
            substrate: Optional[str] = None) -> _Usable:
    """The rows of one compound the resolver would choose among, by its own
    steps in its order (fallback_logic.resolve_kinetic_value): flagged rows
    never; with an isoform, the rows naming it, or failing those the rows
    naming none (`_partition_isoform`); then variants removed, an isozyme
    row kept only when it is the isoform asked for (`_partition_variants`);
    then, for a Ki asked for by mode, rows of another mode removed
    (`ki_mode.rank`).

    A row naming no isoform whose one UniProt accession is ANOTHER protein
    (PDE6C's, for a PDE5A model) is not counted, since it is that protein's
    row whatever its commentary omits; the resolver reads the row's own
    UniProt cell the same way (fallback_logic `_row_isoform`).
    """
    out = _Usable([])
    pool = [r for r in rows if not r.flagged]
    matched = False
    if isoform:
        named = [(r, _isoform_read(r.conditions)) for r in pool]
        mine = [r for r, iso in named if iso and _same_isoform(iso, isoform)]
        pool_unnamed = [r for r, iso in named if iso is None
                        and _accession_says(r.uniprot, isoform) is not False]
        out.set_aside["another isoform"] += len(pool) - len(mine) - len(pool_unnamed)
        kept, matched = (mine, True) if mine else (pool_unnamed, False)
    else:
        kept, pool_unnamed = pool, []

    def wild(rs: Sequence[_Row], keep_isozymes: bool) -> List[_Row]:
        return [r for r in rs if not (r.variant and not (keep_isozymes and r.isozyme))]

    usable = wild(kept, matched)
    isozymes = sum(1 for r in kept if r.variant and r.isozyme and not matched)
    out.set_aside["a named isozyme (taken only when --isoform asks for it)"] += isozymes
    out.set_aside["a variant"] += len(kept) - len(usable) - isozymes
    if mode:
        try:
            from caterva.compose import ki_mode
        except ImportError:  # pragma: no cover
            ki_mode = None
        if ki_mode is not None:
            def fits(rs: Sequence[_Row]) -> List[_Row]:
                return [r for r in rs if ki_mode.rank(ki_mode.read_row(r.conditions), mode,
                                                      substrate, isoform) is not None]
            moded = fits(usable)
            if not moded and matched:
                # The resolver puts the rows naming no isoform back behind
                # the isoform's own for the mode step (_naming_no_isoform).
                moded = fits(wild(pool_unnamed, False))
                matched = False if moded else matched
            out.set_aside["another inhibition mode"] += max(0, len(usable) - len(moded))
            usable = moded
    out.rows = usable
    if isoform and usable:
        out.names_isoform = matched or any(_accession_says(r.uniprot, isoform) for r in usable)
    out.set_aside = Counter({k: n for k, n in out.set_aside.items() if n > 0})
    return out


class _Counts:
    """Rows per compound, spellings merged by `_group_key`, with what the
    search can use of them (`_usable`)."""

    def __init__(self, isoform: Optional[str] = None, mode: Optional[str] = None,
                 substrate: Optional[str] = None) -> None:
        self.isoform, self.mode, self.substrate = isoform, mode, substrate
        self.by_table: Dict[str, Dict[str, List[_Row]]] = {}
        self.spellings: Dict[str, Counter] = {}
        self._usable: Dict[Tuple[str, str], _Usable] = {}

    def add(self, table: str, rows: Iterable[_Row]) -> None:
        groups = self.by_table.setdefault(table, {})
        for row in rows:
            k = _group_key(row.compound)
            groups.setdefault(k, []).append(row)
            self.spellings.setdefault(k, Counter())[row.compound] += 1

    def usable(self, key: str, table: str) -> _Usable:
        """What the search can use of one compound's rows, summed over its
        spellings. Each spelling is judged as the search judges the rows it
        reaches when asked for that spelling (`_search_key`), so rows naming
        the isoform under one spelling do not set aside rows naming none
        under another."""
        found = self._usable.get((key, table))
        if found is None:
            found = _Usable([])
            for rows in self._by_spelling(key, table).values():
                part = _usable(rows, self.isoform, self.mode if table == "ki" else None,
                               self.substrate)
                found.rows.extend(part.rows)
                found.set_aside.update(part.set_aside)
            self._usable[(key, table)] = found
        return found

    def _by_spelling(self, key: str, table: str) -> Dict[str, List[_Row]]:
        out: Dict[str, List[_Row]] = {}
        for row in self.by_table.get(table, {}).get(key, []):
            out.setdefault(_search_key(row.compound), []).append(row)
        return out

    def name(self, key: str) -> str:
        """The spelling the search is asked for: the one with the most usable
        rows (the resolver reaches a spelling's own rows), then the
        commonest, then the first alphabetically."""
        spellings = self.spellings[key]

        def reach(spelling: str) -> int:
            target = _search_key(spelling)
            return sum(1 for t in self.by_table for r in self.usable(key, t).rows
                       if _search_key(r.compound) == target)
        return sorted(spellings, key=lambda s: (-reach(s), -spellings[s], s))[0]

    def other_spellings(self, key: str) -> List[str]:
        chosen = self.name(key)
        return sorted({s for s in self.spellings[key] if _search_key(s) != _search_key(chosen)})

    def reached(self, key: str, tables: Sequence[str]) -> Dict[str, int]:
        """Usable rows per table under the spelling the search is asked for
        (`name`): the rows its value is taken from."""
        target = _search_key(self.name(key))
        return {t: sum(1 for r in self.usable(key, t).rows if _search_key(r.compound) == target)
                for t in tables}

    def spelled_clause(self, key: str, tables: Sequence[str]) -> str:
        """"; BRENDA also spells it X, counted as the same compound; the
        search takes the rows spelled Y (n Km)" -- empty for one spelling."""
        spelled = self.other_spellings(key)
        if not spelled:
            return ""
        out = f"; BRENDA also spells it {', '.join(spelled[:3])}, counted as the same compound"
        reached, total = self.reached(key, tables), self.rows(key, tables)
        if reached != total:
            labels = {"km": "Km", "kcat": "kcat", "ki": "Ki"}
            out += (f"; the search is asked for {self.name(key)} and takes the rows spelled so ("
                    + ", ".join(f"{n} {labels.get(t, t)}" for t, n in reached.items()) + ")")
        return out

    def rows(self, key: str, tables: Sequence[str]) -> Dict[str, int]:
        """Usable rows per table: what a count in a note means."""
        return {t: len(self.usable(key, t).rows) for t in tables}

    def papers(self, key: str, tables: Sequence[str]) -> int:
        """How many BRENDA references the usable rows come from."""
        return len({r.reference_id for t in tables for r in self.usable(key, t).rows
                    if r.reference_id})

    def own(self, key: str, table: str) -> int:
        """Usable rows of `table` that measured the native enzyme's own
        constant (`_Row.own`)."""
        return sum(1 for r in self.usable(key, table).rows if r.own)

    def raw(self, key: str, tables: Sequence[str]) -> Dict[str, int]:
        return {t: len(self.by_table.get(t, {}).get(key, [])) for t in tables}

    def set_aside(self, key: str, tables: Sequence[str]) -> Counter:
        out: Counter = Counter()
        for t in tables:
            out.update(self.usable(key, t).set_aside)
        return out

    def names_isoform(self, key: str, tables: Sequence[str]) -> bool:
        """Whether the rows the search reaches under the spelling it is asked
        for (`name`) name the isoform."""
        spelling = _search_key(self.name(key))
        return any(_usable(self._by_spelling(key, t).get(spelling, []), self.isoform,
                           self.mode if t == "ki" else None, self.substrate).names_isoform
                   for t in tables)

    def keys(self, table: str) -> List[str]:
        return list(self.by_table.get(table, {}))

    def neighbours(self, key: str, tables: Sequence[str]) -> List[str]:
        """Other compounds whose rows the search, asked for this one's name,
        would also take (a stereo form of a name that names none:
        "D-luciferin" for "Luciferin"); its value could then be theirs, and
        is withheld (`neighbour_of`)."""
        spelling = self.name(key)
        out = set()
        for t in tables:
            for other, rows in self.by_table.get(t, {}).items():
                if other != key and _matches(rows[0].compound, spelling):
                    out.add(self.name(other))
        return sorted(out)


def _reaction_compounds(ec: str) -> Tuple[frozenset, frozenset]:
    """(natural substrates, substrates and products of any listed reaction)
    as `_key`s, read from the page's "Natural Substrates" and
    "Substrates/Products" tables. Empty when the page has neither.

    Read by a regular expression over the two tables' cells rather than a
    second full parse of a page that can be four megabytes: the cells are
    `id="tab<N>r<row>c0"` (substrate side) and `c1` (product side), and
    each side is compounds joined by " + ".
    """
    html = _page(ec)
    natural, reaction = set(), set()
    for label, into in (("Natural Substrates", natural), ("Substrates/Products", reaction)):
        match = re.search(r"showTable\('(tab\d+)'\)\">" + re.escape(label) + "<", html)
        if not match:
            continue
        tab = match.group(1)
        for side, text in re.findall(
                r'id="' + tab + r'r[0-9a-z]*?c([01])"[^>]*>([^<]*)<', html):
            for compound in text.split(" + "):
                compound = compound.strip()
                if compound and compound != "?" and compound != "-":
                    key = _key(compound)
                    reaction.add(key)
                    if into is natural and side == "0":
                        natural.add(key)
    return frozenset(natural), frozenset(reaction)


def _in(name: str, key: str, listed: frozenset) -> bool:
    """Whether a compound is one of `listed` (the page's natural substrates,
    or its reaction's compounds): the same compound spelled another way, or
    a stereo form of one listed without ("D-luciferin" for "luciferin")."""
    groups = {_group_key(k) for k in listed}
    return key in groups or any(_matches(name, k) for k in listed)


def _where(ec: str, organism: Optional[str]) -> str:
    return f"EC {ec} in {organism}" if organism else f"EC {ec} (every organism)"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _not_counted(aside: Counter) -> str:
    """"; 2 rows of a variant not counted" -- the rows a count leaves out."""
    if not aside:
        return ""
    parts = [f"{_plural(n, 'row')} of {why}" for why, n in sorted(aside.items())]
    return "; not counted, because the search cannot use them: " + ", ".join(parts)


def _tied(ranked: Sequence[str], rank, drop: int = 1) -> List[str]:
    """The options after the first whose rank equals its in all but the
    last `drop` places (the name; with 2, the papers too)."""
    if len(ranked) < 2:
        return []
    head = rank(ranked[0])[:-drop]
    return [k for k in ranked[1:] if rank(k)[:-drop] == head]


def _shown(names: Sequence[str]) -> str:
    return ", ".join(names[:3]) + (f" and {len(names) - 3} more" if len(names) > 3 else "")


def _tie_clause(names: Sequence[str]) -> str:
    if not names:
        return ""
    return (f"; it is tied on every count with {_shown(names)}, and was taken first by name "
            f"(alphabetically), not by its data")


def _ties(ranked: Sequence[str], rank, papers, name, elsewhere=None,
          where: str = "") -> Tuple[bool, str]:
    """(tied on rows, the clause saying how the tie was broken). The rank's
    last places are -papers, then (with `elsewhere`) -rows under the EC in
    every organism, then the name: rows first, then the number of BRENDA
    references the rows come from, then how widely the compound is measured
    under the EC, then the name."""
    extra = 1 if elsewhere else 0
    on_rows = _tied(ranked, rank, drop=2 + extra)
    if not on_rows:
        return False, ""
    on_papers = _tied(ranked, rank, drop=1 + extra) if extra else []
    on_all = _tied(ranked, rank, drop=1)
    clause = _tie_clause([name(k) for k in on_all])
    if extra:
        wider = [k for k in on_papers if k not in on_all]
        if wider:
            clause = (f"; it ties on rows and references with {_shown([name(k) for k in wider])}, "
                      f"and has more Ki rows under {where} counting every organism "
                      f"({elsewhere(ranked[0])} against at most "
                      f"{max(elsewhere(k) for k in wider)})") + clause
    beaten = [k for k in on_rows if k not in on_papers and k not in on_all]
    if beaten:
        clause = (f"; it ties on rows with {_shown([name(k) for k in beaten])}, and is reported by "
                  f"more BRENDA references ({papers(ranked[0])} against at most "
                  f"{max(papers(k) for k in beaten)})") + clause
    return True, clause


def _isoform_clause(isoform: Optional[str]) -> str:
    return (f", counting the rows the search can use for {isoform} (rows naming it, or where none "
            f"does, rows naming no isoform)" if isoform else "")


# ---------------------------------------------------------------------------
# Substrate
# ---------------------------------------------------------------------------


def choose_substrate(ec: str, organism: Optional[str], *, needs_kcat: bool = True,
                     strict: bool = False, among: Optional[Sequence[str]] = None,
                     isoform: Optional[str] = None) -> Optional[Choice]:
    """The best-measured substrate BRENDA lists Km rows for, for `ec` in
    `organism` (any organism when None); None when it lists none, or the
    page cannot be read (`strict` lets that error out instead, so a caller
    can tell the two apart). `among` limits the choice to those names
    (the listed substrates a word of the description matched, when it
    matched several): the user's word decides the field, the rows decide
    within it. `isoform` is the one the model is of (--isoform, or read
    from a gene symbol): only rows the search can use for it are counted."""
    try:
        return _choose_substrate(ec, organism, needs_kcat, among, isoform)
    except Exception:  # noqa: BLE001 - a choice that cannot be made is no choice
        if strict:
            raise
        return None


def _choose_substrate(ec: str, organism: Optional[str], needs_kcat: bool,
                      among: Optional[Sequence[str]] = None,
                      isoform: Optional[str] = None) -> Optional[Choice]:
    counts = _Counts(isoform)
    counts.add("km", table_rows(ec, "km", organism))
    tables = ["km"]
    if needs_kcat:
        counts.add("kcat", table_rows(ec, "kcat", organism))
        tables.append("kcat")
    candidates = counts.keys("km")
    if among:
        allowed = {_group_key(n) for n in among}
        candidates = [k for k in candidates if k in allowed]
    if not candidates:
        return None
    try:
        natural_listed, _ = _reaction_compounds(ec)
    except Exception:  # noqa: BLE001 - natural is a preference, not a requirement
        natural_listed = frozenset()
    natural = {k for k in candidates if _in(counts.name(k), k, natural_listed)}

    def rows(k: str) -> Dict[str, int]:
        return counts.rows(k, tables)

    def total(k: str) -> int:
        return sum(rows(k).values())

    def has_both(k: str) -> bool:
        return not needs_kcat or rows(k).get("kcat", 0) > 0

    neighbours = {k: counts.neighbours(k, tables) for k in candidates}

    def rank(k: str) -> tuple:
        return (is_cofactor(counts.name(k)), rows(k)["km"] == 0,
                bool(isoform) and not counts.names_isoform(k, tables), bool(neighbours[k]),
                not has_both(k), rows(k)["km"] > 0 and counts.own(k, "km") == 0,
                k not in natural, -total(k), -counts.papers(k, tables),
                counts.name(k).casefold())

    ranked = sorted(candidates, key=rank)
    best = ranked[0]
    name = counts.name(best)
    r = rows(best)
    tied, tie_clause = _ties(ranked, rank, lambda k: counts.papers(k, tables), counts.name)
    most = "as many as any other" if tied else "the most"
    measured = (f"{r['km']} Km, {r['kcat']} kcat" if needs_kcat else _plural(r["km"], "Km row"))
    if r["km"] == 0:
        how = ("none has a Km row the search can use"
               + (f" for {isoform}" if isoform else "")
               + ", so this, the most measured, will stay a placeholder unless the search finds "
                 "another row")
    elif needs_kcat and has_both(best):
        how = f"it has {most} Km and kcat rows"
        if any(not has_both(k) and total(k) > total(best) and not is_cofactor(counts.name(k))
               for k in candidates):
            how = f"it has {most} rows of those with both a Km and a kcat row"
    elif needs_kcat:
        how = (f"none has both a Km and a kcat row there, and it has {most} Km rows, so its kcat "
               "stays a placeholder unless the search finds one")
    else:
        how = f"it has {most} Km rows"
    if r["km"] and best in natural and any(
            k not in natural and total(k) > total(best) and has_both(k) == has_both(best)
            and not is_cofactor(counts.name(k)) and not neighbours[k] for k in candidates):
        how = ("it is the natural substrate (BRENDA's Natural Substrates table) with the most rows; "
               "better-measured assay substrates rank after it")
    if isoform and r["km"] and counts.names_isoform(best, tables) and any(
            not counts.names_isoform(k, tables) and total(k) > total(best) for k in candidates):
        how += f"; substrates whose rows do not name {isoform} rank after it"
    passed = [counts.name(k) for k in candidates if neighbours[k] and total(k) > total(best)
              and not is_cofactor(counts.name(k))]
    if passed and r["km"]:
        how += ("; " + ", ".join(passed[:3]) + (" was" if len(passed) == 1 else " were")
                + " passed over because the search, asked for that name, also takes the rows of "
                + ", ".join(sorted({n for k in candidates if counts.name(k) in passed[:3]
                                    for n in neighbours[k]})[:3])
                + ", and a value that turns out to be another compound's is withheld")
    altered = [counts.name(k) for k in candidates if rows(k)["km"] and counts.own(k, "km") == 0
               and total(k) > total(best) and has_both(k) == has_both(best)
               and not is_cofactor(counts.name(k)) and not neighbours[k]]
    if altered and r["km"]:
        how += ("; " + ", ".join(altered[:3]) + (" has" if len(altered) == 1 else " have")
                + " more rows, but each measured a construct or altered preparation, an apparent "
                  "constant with an inhibitor or effector present, or a K0.5, which the search "
                  "passes over for the enzyme's own constant")
    aside = [counts.name(k) for k in ranked if is_cofactor(counts.name(k)) and total(k) >= total(best)]
    if is_cofactor(name):
        aside = []
        how += "; only cosubstrates and cofactors have rows here, so one of them was used"
    clause = f"; the cosubstrate{'s' if len(aside) > 1 else ''} {', '.join(aside[:3])} set aside" \
        if aside else ""
    spelled_clause = counts.spelled_clause(best, tables)
    which = " that your word matches" if among else ""
    why = (f"of the {_plural(len(candidates), 'substrate')}{which} BRENDA lists Km rows for under "
           f"{_where(ec, organism)}{_isoform_clause(isoform)}, {how} ({measured}{spelled_clause}"
           f"{clause}{_not_counted(counts.set_aside(best, tables))}){tie_clause}")
    alternatives = tuple(Option(counts.name(k), rows(k), USABLE_NONE)
                         for k in ranked[1:1 + ALTERNATIVES_NAMED])
    return Choice("substrate", name, why, alternatives, len(candidates), dict(r))


# ---------------------------------------------------------------------------
# Inhibitor
# ---------------------------------------------------------------------------


def ki_compounds(ec: str, organism: Optional[str]) -> Dict[str, int]:
    """Compound -> Ki row count for `ec` in `organism`, spellings merged."""
    counts = _Counts()
    counts.add("ki", table_rows(ec, "ki", organism))
    return {counts.name(k): len(counts.by_table["ki"][k]) for k in counts.keys("ki")}


def ki_modes(ec: str, organism: Optional[str], inhibitor: str) -> Counter:
    """Mode word -> how many of the inhibitor's Ki rows state it; "no mode"
    for a row whose commentary names none."""
    out: Counter = Counter()
    for row in table_rows(ec, "ki", organism):
        if _group_key(row.compound) != _group_key(inhibitor):
            continue
        found = _MODE.search(row.conditions)
        out[found.group(1).lower().replace("-", "") if found else "no mode"] += 1
    return out


def choose_inhibitor(ec: str, organism: Optional[str], substrate: Optional[str] = None, *,
                     strict: bool = False, isoform: Optional[str] = None,
                     mode: Optional[str] = None) -> Optional[Choice]:
    """The best-measured inhibitor BRENDA lists Ki rows for; None when it
    lists none (or the page cannot be read, unless `strict`). Only rows the
    search can use are counted: not a variant's, not another isoform's than
    `isoform`, and not another inhibition mode's than `mode` (the model's)."""
    try:
        return _choose_inhibitor(ec, organism, substrate, isoform, mode)
    except Exception:  # noqa: BLE001
        if strict:
            raise
        return None


def _choose_inhibitor(ec: str, organism: Optional[str], substrate: Optional[str],
                      isoform: Optional[str] = None, mode: Optional[str] = None) -> Optional[Choice]:
    counts = _Counts(isoform, mode, substrate)
    counts.add("ki", table_rows(ec, "ki", organism))
    excluded = _group_key(substrate) if substrate else None
    candidates = [k for k in counts.keys("ki") if k != excluded]
    if not candidates:
        return None
    try:
        _, reaction_listed = _reaction_compounds(ec)
    except Exception:  # noqa: BLE001
        reaction_listed = frozenset()
    reaction = {k for k in candidates if k in {_group_key(x) for x in reaction_listed}}

    def n(k: str) -> int:
        return counts.rows(k, ["ki"])["ki"]

    neighbours = {k: counts.neighbours(k, ["ki"]) for k in candidates}
    # Compounds tied on rows and references here are told apart by how
    # widely BRENDA measured them under the EC, before their names: 23 Ki
    # compounds of influenza A virus neuraminidase tie at one row and one
    # paper, and the first alphabetically was a triazole analogue (Ki 0.06
    # mM) where oseltamivir carboxylate and zanamivir stood (2026-11-12).
    try:
        everywhere = Counter(_group_key(r.compound) for r in table_rows(ec, "ki", None)
                             if not r.flagged)
    except Exception:  # noqa: BLE001 - the tie then falls to the name
        everywhere = Counter()

    def elsewhere(k: str) -> int:
        return everywhere.get(k, 0)

    def rank(k: str) -> tuple:
        return (n(k) == 0, k in reaction, is_cofactor(counts.name(k)),
                bool(isoform) and not counts.names_isoform(k, ["ki"]), bool(neighbours[k]),
                -n(k), -counts.papers(k, ["ki"]), -elsewhere(k), counts.name(k).casefold())

    ranked = sorted(candidates, key=rank)
    best = ranked[0]
    name = counts.name(best)
    tied, tie_clause = _ties(ranked, rank, lambda k: counts.papers(k, ["ki"]), counts.name,
                             elsewhere, f"EC {ec}")
    usable_for = []
    if isoform:
        usable_for.append(isoform)
    if mode:
        usable_for.append(f"a {mode} model")
    scope = (f", counting the rows the search can use for {' and '.join(usable_for)}"
             if usable_for else "")
    if n(best) == 0:
        how = ("none has a Ki row the search can use, so this, the most measured, will stay a "
               "placeholder unless the search finds another row")
    else:
        how = (f"it has {'as many as any other' if tied else 'the most'} "
               f"({_plural(n(best), 'Ki row')})")
    why = (f"of the {_plural(len(candidates), 'compound')} with Ki rows under "
           f"{_where(ec, organism)}"
           + (f" (the substrate {substrate} aside)" if excluded in counts.keys("ki") else "")
           + f"{scope}, {how}")
    aside = [k for k in ranked if k in reaction and n(k) >= n(best) and k != best and n(k)]
    if best in reaction and n(best):
        why += ("; it is a substrate or product of the reaction itself, so this is product or "
                "substrate inhibition: no other compound has a Ki row here")
    elif aside:
        why += ("; " + ", ".join(f"{counts.name(k)} ({_plural(n(k), 'Ki row')})" for k in aside[:3])
                + (" is" if len(aside) == 1 else " are")
                + " a substrate or product of the reaction (product inhibition), so "
                + ("it was" if len(aside) == 1 else "they were") + " set aside")
    cof = [k for k in ranked if is_cofactor(counts.name(k)) and n(k) > n(best) and k not in reaction]
    if cof and not is_cofactor(name):
        why += "; the cofactor " + ", ".join(counts.name(k) for k in cof[:3]) + " set aside"
    unusable = [k for k in candidates if n(k) == 0 and len(counts.by_table["ki"][k]) > n(best)]
    if unusable and n(best):
        top = max(unusable, key=lambda k: (len(counts.by_table["ki"][k]), counts.name(k)))
        why += (f"; {counts.name(top)} has more Ki rows ({len(counts.by_table['ki'][top])}) but none "
                f"the search can use" + _not_counted(counts.set_aside(top, ["ki"])).replace(
                    "; not counted, because the search cannot use them:", " --"))
    why += tie_clause
    spelled = counts.spelled_clause(best, ["ki"])
    if spelled:
        why += f" ({spelled[2:]})"
    why += _not_counted(counts.set_aside(best, ["ki"]))
    alternatives = tuple(Option(counts.name(k), {"ki": n(k)}, USABLE_NONE)
                         for k in ranked[1:1 + ALTERNATIVES_NAMED])
    return Choice("inhibitor", name, why, alternatives, len(candidates), {"ki": n(best)})


# ---------------------------------------------------------------------------
# A value the search returned, traced back to the compound of its row
# ---------------------------------------------------------------------------


def neighbour_of(ec: str, table: str, compound: str, organism: Optional[str],
                 value: float, reference_id: str) -> Optional[Tuple[str, ...]]:
    """The compound(s) whose BRENDA row the search's value actually is, when
    that row is NOT `compound`'s; None when it is, or when this cannot tell.

    WHY THIS EXISTS. The resolver finds a compound's rows by looking for its
    name INSIDE each row's compound cell. Asked for "L-alanyl-L-alanyl-
    L-prolyl-L-phenylalanine p-nitroanilide" (the substrate chosen for
    chymotrypsin in Homo sapiens, 2026-11-11) it also took every row of
    "N-succinyl-L-alanyl-L-alanyl-L-prolyl-L-phenylalanine p-nitroanilide",
    and carried 0.219 mM from ref 769319 -- a row of the succinyl compound,
    which the choice's own note listed as the ALTERNATIVE -- as the chosen
    substrate's Km. "D-glucose" likewise takes 2-deoxy-D-glucose's rows on
    the hexokinase page. That is a neighbour's value under another
    compound's name (ADR 0076), and a choice made automatically must never
    be what produces one.

    "The same compound" is one `_group_key`: a counter-ion ("acetylthiocholine
    iodide", which the resolver itself takes as acetylthiocholine) or a
    spelling is not a neighbour; a stereo form ("D-luciferin" for
    "Luciferin") is. Before 2026-11-12 the iodide row was withheld as
    another compound's, and acetylcholinesterase in Electrophorus electricus
    lost a Km BRENDA holds.

    Applied only when `compound` is a name BRENDA's table itself lists
    (case and spacing aside), because only then is "the row is another
    compound's" decidable: a name typed loosely ("lactate", which BRENDA
    files as "(S)-lactate") is found ONLY inside other names, and that is
    the resolver's documented courtesy, not a relabel. The row is found by
    its BRENDA reference and value among the organism's rows; when none
    matches, nothing can be said and None is returned.
    """
    if not compound or reference_id is None or value is None:
        return None
    want = _group_key(compound)
    rows = table_rows(ec, table, organism)
    listed = any(_group_key(r.compound) == want for r in rows) or any(
        _group_key(r.compound) == want for r in table_rows(ec, table, None))
    if not listed:
        return None
    ref = str(reference_id)
    same = [r for r in rows if r.reference_id == ref and r.value is not None
            and abs(r.value - float(value)) <= 1e-9 * max(1.0, abs(float(value)))]
    if not same or any(_group_key(r.compound) == want for r in same):
        return None
    return tuple(sorted({r.compound for r in same}))


# ---------------------------------------------------------------------------
# Organism
# ---------------------------------------------------------------------------


#: BRENDA's navigation label for each table, as brenda_client names them.
_TABLE_LABELS = {"km": "KM Values", "kcat": "Turnover Numbers", "ki": "Ki Values"}


def _organisms_on_page(ec: str, table: str) -> Counter:
    """Organism -> row count in BRENDA's `table`, read from the organism
    cell (`c2`) of each row by a regular expression, for organisms the
    every-organism parse cannot label.

    That parse labels a row only when its organism cell looks like a
    binomial ("Homo sapiens"), so a page whose every organism is a virus
    ("Human immunodeficiency virus 1", EC 3.4.23.16) gave no organism and,
    with none named, "BRENDA lists no substrate" -- about a page with 164 Km
    rows. An aggregate row's cell reads "N entries" and is skipped; its
    entries are sub-rows with their own cells.
    """
    html = _page(ec)
    match = re.search(r"showTable\('(tab\d+)'\)\">" + re.escape(_TABLE_LABELS[table]) + "<", html)
    out: Counter = Counter()
    if not match:
        return out
    for cell in re.findall(r'id="' + match.group(1) + r'r\d+(?:sr\d+)?c2"[^>]*>(.*?)</div>', html,
                           flags=re.S):
        text = " ".join(re.sub(r"<[^>]+>", " ", cell).split())
        if text and not re.fullmatch(r"\d+ entries", text):
            out[text] += 1
    return out


def km_organisms(ec: str, substrate: Optional[str] = None) -> Dict[str, int]:
    """Organism -> Km row count for `ec` (for `substrate` when given, as the
    search matches it), including organisms that are not binomials
    (`table_rows` labels those by their cell)."""
    out: Counter = Counter()
    for row in table_rows(ec, "km", None):
        if row.organism and (substrate is None or _matches(row.compound, substrate)):
            out[row.organism] += 1
    return dict(out)


#: At most this many organisms the every-organism parse cannot label are
#: read one by one when it labels none (each is a parse of the page).
UNLABELLED_ORGANISMS_READ = 4


def choose_organism(ec: str, substrate: Optional[str] = None, inhibitor: Optional[str] = None, *,
                    needs: Sequence[str] = ("km", "kcat"), strict: bool = False) -> Optional[Choice]:
    """The organism whose rows cover the most of what the model needs
    (`needs`: "km", "kcat", "ki"), for `substrate` and `inhibitor` when they
    are named; None when no organism has a row for the first of `needs`
    (or the page cannot be read, unless `strict`)."""
    try:
        return _choose_organism(ec, substrate, inhibitor, tuple(needs))
    except Exception:  # noqa: BLE001
        if strict:
            raise
        return None


def _choose_organism(ec: str, substrate: Optional[str], inhibitor: Optional[str],
                     needs: Tuple[str, ...]) -> Optional[Choice]:
    needs = tuple(t for t in ("km", "kcat", "ki") if t in needs or (t == "ki" and inhibitor))
    if not needs:
        return None
    named = {"km": substrate, "kcat": substrate, "ki": inhibitor}
    per: Dict[str, Dict[str, int]] = {}
    # Per organism and substrate, which tables have a row: a substrate with
    # a Km in one organism and a kcat only in another covers one constant
    # in each, not two.
    pair: Dict[str, Dict[str, set]] = {}
    for table in needs:
        for row in _usable(table_rows(ec, table, None)).rows:
            if not row.organism:
                continue
            if named[table] and not _matches(row.compound, named[table]):
                continue
            per.setdefault(row.organism, {t: 0 for t in needs})[table] += 1
            if table in ("km", "kcat"):
                pair.setdefault(row.organism, {}).setdefault(_group_key(row.compound), set()).add(table)
    anchor = needs[0]
    organisms = [o for o, r in per.items() if r.get(anchor, 0) > 0]
    if not organisms:
        # Every organism on the page is one the every-organism parse cannot
        # label (a virus): read the commonest few by name instead.
        unlabelled = [o for o, _ in _organisms_on_page(ec, anchor).most_common()
                      if not _BINOMIAL.fullmatch(o)][:UNLABELLED_ORGANISMS_READ]
        for organism in unlabelled:
            for table in needs:
                for row in _usable(table_rows(ec, table, organism)).rows:
                    if named[table] and not _matches(row.compound, named[table]):
                        continue
                    per.setdefault(organism, {t: 0 for t in needs})[table] += 1
                    if table in ("km", "kcat"):
                        pair.setdefault(organism, {}).setdefault(_group_key(row.compound), set()).add(table)
        organisms = [o for o, r in per.items() if r.get(anchor, 0) > 0]
    if not organisms:
        return None

    def covered(o: str) -> int:
        substrates = pair.get(o, {})
        enzyme_side = max((len(t) for t in substrates.values()), default=0)
        return enzyme_side + (1 if "ki" in needs and per[o].get("ki", 0) else 0)

    def without_named_ki(o: str) -> bool:
        # The inhibitor the user NAMED is the point of the question: an
        # organism with a Ki row for it ranks before every organism without
        # one, however well measured. "neuraminidase inhibited by zanamivir"
        # was otherwise modelled as human neuraminidase (33 Km, 1 kcat) with
        # the zanamivir Ki a placeholder, though BRENDA holds influenza
        # zanamivir Ki rows (2026-11-12).
        return bool(inhibitor) and per[o].get("ki", 0) == 0

    def rank(o: str) -> tuple:
        return (without_named_ki(o), -covered(o), -sum(per[o].values()), o)

    ranked = sorted(organisms, key=rank)
    full = len(needs)
    human = PREFERRED_ORGANISM in organisms and covered(PREFERRED_ORGANISM) == full
    best = PREFERRED_ORGANISM if human else ranked[0]
    if human:
        ranked = [best] + [o for o in ranked if o != best]
    what = ", ".join(
        f"{TABLE_NAMES[t]}" + (f" for {named[t]}" if named[t] else "") for t in needs)
    r = per[best]
    counts = ", ".join(f"{r[t]} {TABLE_NAMES[t]}" for t in needs)
    if human:
        how = (f"{PREFERRED_ORGANISM} is used when it has rows for every constant this model needs "
               f"({what}), and it does ({counts})")
    else:
        lacking = ""
        if best == PREFERRED_ORGANISM:
            lacking = ""
        elif PREFERRED_ORGANISM in per:
            lacking = f"; {PREFERRED_ORGANISM}, preferred when it covers them all, does not"
        elif PREFERRED_ORGANISM not in organisms:
            lacking = f"; {PREFERRED_ORGANISM}, preferred when it covers them all, has none"
        named_first = ""
        if inhibitor and not without_named_ki(best) and any(
                without_named_ki(o) and (covered(o), sum(per[o].values()))
                > (covered(best), sum(per[best].values())) for o in organisms):
            named_first = (f"; organisms with no Ki row for {inhibitor}, the inhibitor named, rank "
                           f"after those with one, however many other rows they have")
        tied = _tied(ranked, rank)
        most = "as many rows as any other" if tied else "the most rows"
        how = (f"it has rows for {covered(best)} of the {full} constant(s) this model needs "
               f"({what}) and {most} of those that do ({counts}){lacking}{named_first}"
               f"{_tie_clause(tied)}")
    why = f"of the {_plural(len(organisms), 'organism')} with rows under EC {ec}, {how}"
    alternatives = tuple(Option(o, dict(per[o])) for o in ranked[1:1 + ALTERNATIVES_NAMED])
    return Choice("organism", best, why, alternatives, len(organisms), dict(r))


# ---------------------------------------------------------------------------
# Enzyme: a name that is a few enzymes, when the data settles it
# ---------------------------------------------------------------------------


def choose_enzyme(name: str, candidates: Sequence[Tuple[str, str]],
                  organism: Optional[str] = None) -> Optional[Choice]:
    """The EC number among `candidates` ((ec, name) pairs, at most
    ENZYME_CANDIDATES_CONSIDERED) that BRENDA's data singles out, or None.

    With an organism, exactly one candidate may have Km rows for it; with
    none, one must have DOMINANCE times the rows of every other. Anything
    else is a real ambiguity and stays a refusal with the candidates named:
    the data can break a tie between readings of a name, never choose
    between two enzymes that both have measurements.
    """
    if not candidates or len(candidates) > ENZYME_CANDIDATES_CONSIDERED:
        return None
    try:
        rows = {ec: len(table_rows(ec, "km", organism)) for ec, _ in candidates}
    except Exception:  # noqa: BLE001 - one unreadable page and nothing is singled out
        return None
    names = dict(candidates)
    with_rows = [ec for ec, n in rows.items() if n > 0]
    ranked = sorted(rows, key=lambda ec: (-rows[ec], ec))
    best = ranked[0]
    if organism:
        if len(with_rows) != 1:
            return None
        how = (f"it is the only one of the {len(candidates)} enzymes the name matches best with Km "
               f"rows in {organism} ({_plural(rows[best], 'Km row')})")
    else:
        if rows[best] == 0 or any(rows[ec] * DOMINANCE > rows[best] for ec in ranked[1:]):
            return None
        how = (f"of the {len(candidates)} enzymes the name matches best it has at least "
               f"{DOMINANCE} times the Km rows of every other ({_plural(rows[best], 'Km row')})")
    why = f"your description names {name!r}, which is not one enzyme; {names[best]} is used because {how}"
    alternatives = tuple(Option(f"EC {ec} ({names[ec]})", {"km": rows[ec]}) for ec in ranked[1:])
    return Choice("enzyme", best, why, alternatives, len(candidates), {"km": rows[best]})


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m caterva.compose.defaults",
        description="Say what compose would choose for a substrate, inhibitor or organism "
                    "the user did not name, from BRENDA's page for the enzyme (ADR 0182).")
    parser.add_argument("--ec", required=True, help="the enzyme's EC number")
    parser.add_argument("--organism", help="the organism (choose_substrate, choose_inhibitor)")
    parser.add_argument("--substrate", help="the substrate already named")
    parser.add_argument("--inhibitor", help="the inhibitor already named (--role organism)")
    parser.add_argument("--role", choices=("substrate", "inhibitor", "organism"), default="substrate")
    parser.add_argument("--isoform", help="the isoform the model is of (substrate, inhibitor)")
    parser.add_argument("--mode", help="the model's inhibition mode (--role inhibitor)")
    parser.add_argument("--no-kcat", action="store_true", help="the model needs no kcat")
    parser.add_argument("--json", action="store_true", help="print {choice, note} as JSON")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    from caterva.compose.organisms import normalise_organism

    organism, _ = normalise_organism(args.organism)
    error: Optional[str] = None
    choice: Optional[Choice] = None
    if not EC_NUMBER.fullmatch(args.ec.strip()):
        # Never fetched: BRENDA answers any string with a page, and "no Km
        # rows under EC abc" reads as a fact about an enzyme.
        note = (f"{args.ec!r} is not an EC number (four fields, like 2.7.1.1), so there is no "
                f"BRENDA page to choose a {args.role} from.")
        print(json.dumps({"choice": None, "note": note}, indent=2) if args.json else note)
        return 3
    try:
        if args.role == "substrate":
            choice = choose_substrate(args.ec, organism, needs_kcat=not args.no_kcat, strict=True,
                                      isoform=args.isoform)
        elif args.role == "inhibitor":
            choice = choose_inhibitor(args.ec, organism, args.substrate, strict=True,
                                      isoform=args.isoform, mode=args.mode)
        else:
            needs = ("km",) if args.no_kcat else ("km", "kcat")
            choice = choose_organism(args.ec, args.substrate, args.inhibitor, needs=needs, strict=True)
    except Exception as exc:  # noqa: BLE001 - said, and exit 3
        error = f"BRENDA's page for EC {args.ec} could not be read: {type(exc).__name__}: {exc}"
    if choice is not None:
        note = choice.note()
    elif error is not None:
        note = error
    else:
        table = {"substrate": "Km", "inhibitor": "Ki", "organism": "Km"}[args.role]
        note = (f"BRENDA holds no {table} rows under {_where(args.ec, organism)}"
                + (f" for {args.substrate}" if args.role == "organism" and args.substrate else "")
                + f", so there is no {args.role} to choose.")
    if args.json:
        print(json.dumps({"choice": choice.to_json() if choice else None, "note": note}, indent=2))
    else:
        print(note)
    return 0 if choice is not None else 3


__all__ = [
    "ALTERNATIVES_NAMED", "COFACTORS", "Choice", "Option", "ROLES", "choose_enzyme",
    "choose_inhibitor", "choose_organism", "choose_substrate", "is_cofactor", "ki_compounds",
    "ki_modes", "km_organisms", "main", "neighbour_of", "table_rows",
]


if __name__ == "__main__":
    sys.exit(main())
