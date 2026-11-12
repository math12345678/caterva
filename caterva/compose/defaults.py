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
mode (`require_substrate_match=False`), so a count here is a count of rows
the resolver can reach.

- Substrate: cosubstrates and cofactors (ATP, NAD+, CoA, water, metal ions
  ...) are set aside unless nothing else has rows, because "hexokinase on
  ATP" is not what anyone means by hexokinase kinetics, though ATP has the
  most rows. Then a substrate with BOTH a Km and a kcat row in the organism
  (when the model needs a kcat), then one BRENDA files as a natural
  substrate, then the most Km + kcat rows, then the name.
- Inhibitor: compounds with Ki rows in the organism, the chosen substrate
  excluded; a substrate or product of the reaction (D-glucose 6-phosphate
  for hexokinase is product inhibition) is set aside when any other
  compound has a row, and so is a cofactor; then the most Ki rows, then
  the name.
- Organism (none named): Homo sapiens when it has rows for every constant
  the model needs; otherwise the organism covering the most of them, then
  the most rows, then the name. Never one with no row for the substrate
  named or chosen.

Spellings that differ only in case or spacing are counted as one compound
and the commonest spelling is the one used; anything subtler ("Z-" and
"N-benzyloxycarbonyl-") is left as BRENDA wrote it, because merging names is
a chemical judgement this module cannot make.
"""
from __future__ import annotations

import argparse
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

#: Words in a Ki row's commentary that state an inhibition mode, longest first.
_MODE = re.compile(r"\b(non-?competitive|un-?competitive|mixed(?:-type)?|competitive)\b",
                   re.IGNORECASE)


@dataclass(frozen=True)
class Option:
    """One thing that could have been chosen, with the rows behind it."""

    name: str
    #: table -> row count ({"km": 25, "kcat": 61} or {"ki": 7}).
    rows: Dict[str, int] = field(default_factory=dict)

    def describe(self) -> str:
        parts = [f"{n} {TABLE_NAMES.get(t, t)}" for t, n in self.rows.items() if n]
        return f"{self.name} ({', '.join(parts) if parts else 'no rows'})"


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
                 None if getattr(r, "reference_id", None) is None else str(r.reference_id))
            for r in parsed
            if getattr(r, "table_scoped", True) and getattr(r, "substrate", None)
            and str(r.substrate) != "unknown compound"
        )
    if len(_PARSED) >= _PARSED_MAX:
        _PARSED.clear()
    _PARSED[key] = out
    return out


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


def is_cofactor(name: str) -> bool:
    """True for a cosubstrate, cofactor or small ion (COFACTORS)."""
    key = _PREFIX.sub("", _key(name))
    return key in _COFACTOR_KEYS or bool(_METAL_ION.match(key))


class _Counts:
    """Row counts per compound, spellings merged by `_key`."""

    def __init__(self) -> None:
        self.by_table: Dict[str, Counter] = {}
        self.spellings: Dict[str, Counter] = {}

    def add(self, table: str, rows: Iterable[_Row]) -> None:
        counter = self.by_table.setdefault(table, Counter())
        for row in rows:
            k = _key(row.compound)
            counter[k] += 1
            self.spellings.setdefault(k, Counter())[row.compound] += 1

    def name(self, key: str) -> str:
        # The commonest spelling, then the first alphabetically: deterministic.
        spellings = self.spellings[key]
        return sorted(spellings, key=lambda s: (-spellings[s], s))[0]

    def rows(self, key: str, tables: Sequence[str]) -> Dict[str, int]:
        return {t: int(self.by_table.get(t, Counter()).get(key, 0)) for t in tables}

    def keys(self, table: str) -> List[str]:
        return list(self.by_table.get(table, Counter()))


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


def _where(ec: str, organism: Optional[str]) -> str:
    return f"EC {ec} in {organism}" if organism else f"EC {ec} (every organism)"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


# ---------------------------------------------------------------------------
# Substrate
# ---------------------------------------------------------------------------


def choose_substrate(ec: str, organism: Optional[str], *, needs_kcat: bool = True,
                     strict: bool = False, among: Optional[Sequence[str]] = None) -> Optional[Choice]:
    """The best-measured substrate BRENDA lists Km rows for, for `ec` in
    `organism` (any organism when None); None when it lists none, or the
    page cannot be read (`strict` lets that error out instead, so a caller
    can tell the two apart). `among` limits the choice to those names
    (the listed substrates a word of the description matched, when it
    matched several): the user's word decides the field, the rows decide
    within it."""
    try:
        return _choose_substrate(ec, organism, needs_kcat, among)
    except Exception:  # noqa: BLE001 - a choice that cannot be made is no choice
        if strict:
            raise
        return None


def _choose_substrate(ec: str, organism: Optional[str], needs_kcat: bool,
                      among: Optional[Sequence[str]] = None) -> Optional[Choice]:
    counts = _Counts()
    counts.add("km", table_rows(ec, "km", organism))
    tables = ["km"]
    if needs_kcat:
        counts.add("kcat", table_rows(ec, "kcat", organism))
        tables.append("kcat")
    candidates = counts.keys("km")
    if among:
        allowed = {_key(n) for n in among}
        candidates = [k for k in candidates if k in allowed]
    if not candidates:
        return None
    try:
        natural, _ = _reaction_compounds(ec)
    except Exception:  # noqa: BLE001 - natural is a preference, not a requirement
        natural = frozenset()

    def rows(k: str) -> Dict[str, int]:
        return counts.rows(k, tables)

    def total(k: str) -> int:
        return sum(rows(k).values())

    def has_both(k: str) -> bool:
        return not needs_kcat or rows(k).get("kcat", 0) > 0

    def rank(k: str) -> tuple:
        return (is_cofactor(counts.name(k)), not has_both(k), k not in natural, -total(k),
                counts.name(k).casefold())

    ranked = sorted(candidates, key=rank)
    best = ranked[0]
    name = counts.name(best)
    r = rows(best)
    measured = (f"{r['km']} Km, {r['kcat']} kcat" if needs_kcat else _plural(r["km"], "Km row"))
    if needs_kcat and has_both(best):
        how = "it has the most Km and kcat rows"
        if any(not has_both(k) and total(k) > total(best) and not is_cofactor(counts.name(k))
               for k in candidates):
            how = "it has the most rows of those with both a Km and a kcat row"
    elif needs_kcat:
        how = ("none has both a Km and a kcat row there, and it has the most Km rows, so its kcat "
               "stays a placeholder unless the search finds one")
    else:
        how = "it has the most Km rows"
    if best in natural and any(
            k not in natural and total(k) > total(best) and has_both(k) == has_both(best)
            and not is_cofactor(counts.name(k)) for k in candidates):
        how = ("it is the natural substrate (BRENDA's Natural Substrates table) with the most rows; "
               "better-measured assay substrates rank after it")
    aside = [counts.name(k) for k in ranked if is_cofactor(counts.name(k)) and total(k) >= total(best)]
    if is_cofactor(name):
        aside = []
        how += "; only cosubstrates and cofactors have rows here, so one of them was used"
    clause = f"; the cosubstrate{'s' if len(aside) > 1 else ''} {', '.join(aside[:3])} set aside" \
        if aside else ""
    which = " that your word matches" if among else ""
    why = (f"of the {_plural(len(candidates), 'substrate')}{which} BRENDA lists Km rows for under "
           f"{_where(ec, organism)}, {how} ({measured}{clause})")
    alternatives = tuple(Option(counts.name(k), rows(k)) for k in ranked[1:1 + ALTERNATIVES_NAMED])
    return Choice("substrate", name, why, alternatives, len(candidates), dict(r))


# ---------------------------------------------------------------------------
# Inhibitor
# ---------------------------------------------------------------------------


def ki_compounds(ec: str, organism: Optional[str]) -> Dict[str, int]:
    """Compound -> Ki row count for `ec` in `organism`, spellings merged."""
    counts = _Counts()
    counts.add("ki", table_rows(ec, "ki", organism))
    return {counts.name(k): counts.by_table["ki"][k] for k in counts.keys("ki")}


def ki_modes(ec: str, organism: Optional[str], inhibitor: str) -> Counter:
    """Mode word -> how many of the inhibitor's Ki rows state it; "no mode"
    for a row whose commentary names none."""
    out: Counter = Counter()
    for row in table_rows(ec, "ki", organism):
        if _key(row.compound) != _key(inhibitor):
            continue
        found = _MODE.search(row.conditions)
        out[found.group(1).lower().replace("-", "") if found else "no mode"] += 1
    return out


def choose_inhibitor(ec: str, organism: Optional[str], substrate: Optional[str] = None, *,
                     strict: bool = False) -> Optional[Choice]:
    """The best-measured inhibitor BRENDA lists Ki rows for; None when it
    lists none (or the page cannot be read, unless `strict`)."""
    try:
        return _choose_inhibitor(ec, organism, substrate)
    except Exception:  # noqa: BLE001
        if strict:
            raise
        return None


def _choose_inhibitor(ec: str, organism: Optional[str], substrate: Optional[str]) -> Optional[Choice]:
    counts = _Counts()
    counts.add("ki", table_rows(ec, "ki", organism))
    excluded = _key(substrate) if substrate else None
    candidates = [k for k in counts.keys("ki") if k != excluded]
    if not candidates:
        return None
    try:
        _, reaction = _reaction_compounds(ec)
    except Exception:  # noqa: BLE001
        reaction = frozenset()

    def n(k: str) -> int:
        return counts.by_table["ki"][k]

    def rank(k: str) -> tuple:
        return (k in reaction, is_cofactor(counts.name(k)), -n(k), counts.name(k).casefold())

    ranked = sorted(candidates, key=rank)
    best = ranked[0]
    name = counts.name(best)
    why = (f"of the {_plural(len(candidates), 'compound')} with Ki rows under "
           f"{_where(ec, organism)}"
           + (f" (the substrate {substrate} aside)" if excluded in counts.keys("ki") else "")
           + f", it has the most ({_plural(n(best), 'Ki row')})")
    aside = [k for k in ranked if k in reaction and n(k) >= n(best) and k != best]
    if best in reaction:
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
    alternatives = tuple(Option(counts.name(k), {"ki": n(k)}) for k in ranked[1:1 + ALTERNATIVES_NAMED])
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
    want = _key(compound)
    rows = table_rows(ec, table, organism)
    listed = any(_key(r.compound) == want for r in rows) or any(
        _key(r.compound) == want for r in table_rows(ec, table, None))
    if not listed:
        return None
    ref = str(reference_id)
    same = [r for r in rows if r.reference_id == ref and r.value is not None
            and abs(r.value - float(value)) <= 1e-9 * max(1.0, abs(float(value)))]
    if not same or any(_key(r.compound) == want for r in same):
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
    """Organism -> Km row count for `ec` (for `substrate` when given),
    including organisms that are not binomials (`_organisms_on_page`)."""
    out: Counter = Counter()
    for row in table_rows(ec, "km", None):
        if row.organism and (substrate is None or _key(row.compound) == _key(substrate)):
            out[row.organism] += 1
    for organism, n in _organisms_on_page(ec, "km").items():
        if organism in out or _BINOMIAL.fullmatch(organism):
            continue
        if substrate is None:
            out[organism] = n
        else:
            rows = [r for r in table_rows(ec, "km", organism) if _key(r.compound) == _key(substrate)]
            if rows:
                out[organism] = len(rows)
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
        for row in table_rows(ec, table, None):
            if not row.organism:
                continue
            if named[table] and _key(row.compound) != _key(named[table]):
                continue
            per.setdefault(row.organism, {t: 0 for t in needs})[table] += 1
            if table in ("km", "kcat"):
                pair.setdefault(row.organism, {}).setdefault(_key(row.compound), set()).add(table)
    anchor = needs[0]
    organisms = [o for o, r in per.items() if r.get(anchor, 0) > 0]
    if not organisms:
        # Every organism on the page is one the every-organism parse cannot
        # label (a virus): read the commonest few by name instead.
        unlabelled = [o for o, _ in _organisms_on_page(ec, anchor).most_common()
                      if not _BINOMIAL.fullmatch(o)][:UNLABELLED_ORGANISMS_READ]
        for organism in unlabelled:
            for table in needs:
                for row in table_rows(ec, table, organism):
                    if named[table] and _key(row.compound) != _key(named[table]):
                        continue
                    per.setdefault(organism, {t: 0 for t in needs})[table] += 1
                    if table in ("km", "kcat"):
                        pair.setdefault(organism, {}).setdefault(_key(row.compound), set()).add(table)
        organisms = [o for o, r in per.items() if r.get(anchor, 0) > 0]
    if not organisms:
        return None

    def covered(o: str) -> int:
        substrates = pair.get(o, {})
        enzyme_side = max((len(t) for t in substrates.values()), default=0)
        return enzyme_side + (1 if "ki" in needs and per[o].get("ki", 0) else 0)

    def rank(o: str) -> tuple:
        return (-covered(o), -sum(per[o].values()), o)

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
        if PREFERRED_ORGANISM in per:
            lacking = f"; {PREFERRED_ORGANISM}, preferred when it covers them all, does not"
        elif PREFERRED_ORGANISM not in organisms:
            lacking = f"; {PREFERRED_ORGANISM}, preferred when it covers them all, has none"
        how = (f"it has rows for {covered(best)} of the {full} constant(s) this model needs "
               f"({what}) and the most rows of those that do ({counts}){lacking}")
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
    parser.add_argument("--no-kcat", action="store_true", help="the model needs no kcat")
    parser.add_argument("--json", action="store_true", help="print {choice, note} as JSON")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    from caterva.compose.organisms import normalise_organism

    organism, _ = normalise_organism(args.organism)
    error: Optional[str] = None
    choice: Optional[Choice] = None
    try:
        if args.role == "substrate":
            choice = choose_substrate(args.ec, organism, needs_kcat=not args.no_kcat, strict=True)
        elif args.role == "inhibitor":
            choice = choose_inhibitor(args.ec, organism, args.substrate, strict=True)
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
