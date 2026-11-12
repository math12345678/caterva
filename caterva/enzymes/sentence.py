"""Read the enzyme, organism, substrate and inhibitor a description names.

WHY THIS EXISTS
---------------
`caterva compose "Michaelis-Menten kinetics of human hexokinase on glucose"`
built a model with the motif library's placeholder constants and said "no
enzyme was named", in a report about hexokinase. "hexokinase glucose human",
"yeast alcohol dehydrogenase with ethanol" and "EC 2.7.1.1 glucose" were
refused outright ("No shape in this grammar matches"), although the same
words as `--subject/--organism/--substrate` flags reach BRENDA's Km 6.0 mM
(ref 641068) and kcat 40.1 1/s (ref 739603) for human hexokinase. The
measured value was one flag away and the report pointed the reader at the
wrong place. Found 2026-11-02 by typing the sentences a biochemist types
(ADR 0181).

WHAT IT READS, AND WHAT IT NEVER GUESSES
----------------------------------------
* The ENZYME only through `finder.resolve`, and only when that resolution
  is not a choice and not a stretch: an EC number, an accepted name typed
  exactly, a full alternative name typed exactly, or a gene symbol, lab
  abbreviation or curated alias the symbol table maps to ONE enzyme in the
  organism (ADR 0182: "human HK2" is hexokinase, isoform HK2; "CYP2B6" is
  EC 1.14.14.1, isoform CYP2B6, Homo sapiens assumed and said). A symbol is
  read only when typed with a capital letter and at least three characters
  long ("PKA", never "ace" in a sentence), and never when it is also a
  substrate's abbreviation ("PEP", "FBP", "G6P"). A misspelt name is read
  only when ONE enzyme name is that close and it is said
  (`finder.spelling_match`: "acetylcholinestrase"). Never a phrase inside a
  longer name or a stereo-tolerant match ("peptidase" is not
  "L-peptidase"). A window of words
  that are all class words ("kinase", "protein kinase", "MAP kinase",
  "phosphatase", "dehydrogenase", "enzyme") is not read at all: the
  nomenclature lists "protein kinase" as another name of histidine kinase
  and "MAP kinase" as one of EC 2.7.11.24, and "three step MAP kinase
  cascade" grounded in one of them would be the adjacent-paper miscitation
  of ADR 0076. A name that is several enzymes ("lactate dehydrogenase") is
  returned as `ambiguity` for the caller to refuse with the candidates named,
  never skipped and never picked. So are, when nothing else names an
  enzyme, an abbreviation several enzymes go by ("LDH", "HMG-CoA reductase"
  with no organism), the head word of several names ("amylase", "DNA
  polymerase", "aldehyde dehydrogenase") and a near spelling with no single
  reading ("hexokinaze"): each used to be dropped, and the report said no
  enzyme was named (round-1 findings M7, F12; `_names_some_enzyme`).
* The ORGANISM through `index.organism_code`, the one normaliser every caller
  shares, so "human", "humans", "human's", "H. sapiens", "E. coli" and
  "yeast" are read the same way here as `--organism` reads them; and a
  binomial written after "in" or "from" ("in Thermus thermophilus"); the
  index also holds the classic enzyme sources by common name (jack bean,
  hen egg white, electric eel, mushroom). Words after "from" just after the
  enzyme that name no organism it knows are said, and not tried as a
  substrate (`unread_organism` with no close name). A near
  spelling where an organism goes ("humna hexokinase") is never read as one,
  and is said (`unread_organism`).
* The SUBSTRATE only as CANDIDATES (`substrate_candidates`). Whether one is
  the substrate is decided by `match_substrate` against the substrates BRENDA
  lists for the resolved enzyme, never here: "glucose" is a substrate of
  hexokinase because BRENDA has Km rows for D-glucose, not because it looks
  like a sugar.
* The INHIBITOR from "inhibited by X", "blocked by X", "inhibitor X",
  "X inhibitor", "in the presence of X" and "<enzyme> by X" in a sentence
  about inhibition, as typed; never from a "by" after any other word
  ("measured by fluorescence"). The Ki search then looks it up as it looks
  up `--inhibitor`. A bare "with X" is only a POSSIBLE inhibitor
  (`possible_inhibitor_text`): whether X is one is decided against
  BRENDA's Ki list by the caller, never here.
* The SUBSTRATE candidates follow the verbs people use for what an enzyme
  does to its substrate ("metabolising midazolam", "cleaving BAPNA"), and a
  verb is never part of a candidate. A virus or strain tag ("HIV-1",
  "K-12") or a mutation ("R132H") is never a candidate; a mutation typed
  after the enzyme is said to be not modelled (`mutations`).
* The SUBSTRATE candidates are whole runs of words, never one word of a
  longer compound name ("glucose" out of "glucose 6-phosphate").

Everything inferred is said, in `notes()`, so the report shows what was read
and a reader can see a wrong reading instead of trusting it. Offline and
deterministic: the finder's committed index, no network.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .finder import (
    TIER_ACCEPTED_EXACT, TIER_ACCEPTED_TOLERANT, TIER_ALTERNATIVE_EXACT, TIER_ALTERNATIVE_PHRASE,
    TIER_ALTERNATIVE_TOLERANT, TIER_EC,
    TIER_TYPO, Ambiguous, Resolved, _ENZYME_ENDING, _outside_parentheses, _tables, compact_name_key, is_abbreviation, loose_key, read_ec,
    resolve, spelling_match, strict_key,
)
from .index import ORGANISMS, load_index, organism_code

#: Class words. A window made only of these names a family of enzymes, never
#: one, whatever the nomenclature lists it as another name of: "protein
#: kinase" resolves to histidine kinase (EC 2.7.13.3) and "MAP kinase" to
#: EC 2.7.11.24 by exact alternative name, and "enzyme" to D-enzyme once the
#: D- is set aside. So these windows are neither resolved nor reported as
#: ambiguous: "a kinase and a phosphatase" is a mechanism, not two enzymes.
CLASS_WORDS = frozenset({
    "enzyme", "enzymes", "protein", "proteins", "kinase", "kinases", "phosphatase", "phosphatases",
    "dehydrogenase", "dehydrogenases", "reductase", "oxidase", "synthase", "synthetase", "ligase",
    "isomerase", "mutase", "transferase", "hydrolase", "lyase", "protease", "proteinase", "peptidase",
    "esterase", "nuclease", "polymerase", "atpase", "gtpase", "map", "mapk", "mapkk", "mapkkk",
    "map2k", "map3k", "mitogen", "activated", "serine", "threonine", "tyrosine", "receptor",
    "catalyst", "catalytic", "subunit", "domain", "regulatory", "first", "second", "third",
    "upstream", "downstream", "two", "three", "four", "five", "one", "step", "steps", "tier",
})

#: Words that join phrases. A window never starts or ends on one, and a
#: substrate or inhibitor phrase stops at one.
STOPWORDS = frozenset({
    "a", "an", "the", "of", "on", "with", "for", "and", "using", "by", "in", "from", "at", "to",
    "its", "their", "as", "into", "onto", "via", "under", "over", "or", "between", "that", "which",
    "is", "are", "be", "this", "these", "each", "per", "it", "than",
})

#: Words that describe the model or the request rather than a compound.
#: They are never substrate candidates.
FILLER = frozenset({
    "kinetics", "kinetic", "model", "modelling", "modeling", "simulate", "simulation", "rate",
    "rates", "constant", "constants", "reaction", "reactions", "activity", "michaelis", "menten",
    "michaelis-menten", "turnover", "catalysis", "substrate", "substrates", "measured", "real",
    "values", "value", "km", "kcat", "vmax", "inhibition", "inhibited", "inhibitor", "inhibitors",
    "competitive", "noncompetitive", "non-competitive", "uncompetitive", "mixed", "converting",
    "conversion", "turning", "human", "humans", "cell", "cells", "enzyme", "enzymes",
    "presence", "absence", "blocked", "blocking", "blocks", "block",
    # "carbonic anhydrase in human follows Michaelis-Menten": a verb of the
    # request, which was read as a compound and said to be "not a substrate".
    "follows", "follow", "following", "obeys", "obey", "obeying",
}) | CLASS_WORDS

#: Verbs for what an enzyme does to its substrate. Each ends a candidate
#: (it is never part of one: "cleaving BAPNA" glued the verb onto the
#: compound and matched nothing) and starts one, like "with" or "on".
SUBSTRATE_VERBS = frozenset({
    "metabolising", "metabolizing", "metabolises", "metabolizes", "metabolise", "metabolize",
    "cleaving", "cleaves", "cleave", "hydrolysing", "hydrolyzing", "hydrolyses", "hydrolyzes",
    "hydrolyse", "hydrolyze", "phosphorylating", "phosphorylates", "phosphorylate",
    "oxidising", "oxidizing", "oxidises", "oxidizes", "oxidise", "oxidize", "reducing", "reduces",
    "reduce", "converting", "converts", "convert", "turning", "turns", "acting", "acts",
    "catalysing", "catalyzing", "processing", "processes", "degrading", "degrades",
    "deaminating", "decarboxylating", "dephosphorylating", "dephosphorylates", "transferring",
})
FILLER = FILLER | SUBSTRATE_VERBS

#: Words that introduce a substrate candidate.
_INTRODUCERS = frozenset({"with", "on", "for", "of", "and", "using", "over"}) | SUBSTRATE_VERBS

#: A virus, strain or construct tag: never a compound ("HIV-1", "K-12",
#: "MG1655", "BL21", "S288C").
_TAG = re.compile(
    r"^(?:(?:hiv|htlv|siv|hcv|hbv|hpv|sars|mers|cov)(?:-?\d+)?|sars-cov-?\d*|[a-z]{0,3}-?\d{2,5}[a-z]?\d*|\d+)$",
    re.IGNORECASE)
#: A point mutation: R132H, V600E.
_MUTATION = re.compile(r"^[ACDEFGHIKLMNPQRSTVWY]\d{1,4}[ACDEFGHIKLMNPQRSTVWY*]$")

#: Organism-table aliases that are also ordinary English words and are
#: therefore not read from a sentence ("man" is an alias of Homo sapiens in
#: the index, for `--organism man`; "a man-made substrate" is not human).
_NOT_IN_A_SENTENCE = frozenset({"man"})

_EC_FULL = re.compile(r"^(?:e\.?c\.?[:#]?)?\d+\.\d+\.\d+\.n?\d+$", re.IGNORECASE)
_EC_WORD = re.compile(r"^e\.?c\.?[:#]?$", re.IGNORECASE)
_EC_PARTIAL = re.compile(r"^\d+(?:\.(?:\d+|-))*\.?$")
_POSSESSIVE = re.compile(r"(?:'s|’s|s'|’)$", re.IGNORECASE)
_EDGE = "\"'“”‘’()[]{}<>,;:!?"
_BINOMIAL = re.compile(r"^[A-Z][a-z]{2,}$")
_EPITHET = re.compile(r"^[a-z]{3,}$")

#: The longest enzyme name, in words, a window is tried at.
MAX_WINDOW = 6


@dataclass(frozen=True)
class SentenceReading:
    """What a description named, each part as typed and as read."""

    text: str
    #: The enzyme span exactly as typed ("human hexokinase" gives "hexokinase").
    enzyme_text: Optional[str] = None
    ec: Optional[str] = None
    enzyme_name: Optional[str] = None
    #: The finder's own reason ("accepted name matches exactly").
    how: Optional[str] = None
    #: The finder's cautions (an enzyme with no protein from the organism).
    cautions: Tuple[str, ...] = ()
    #: The binomial BRENDA files the organism under, and the words read as it.
    organism: Optional[str] = None
    organism_text: Optional[str] = None
    #: The first substrate candidate, and all of them in the order tried.
    substrate_text: Optional[str] = None
    substrate_candidates: Tuple[str, ...] = ()
    inhibitor_text: Optional[str] = None
    #: The finder's `Ambiguous` when the enzyme span names several enzymes.
    ambiguity: Optional[Ambiguous] = None
    #: Other enzymes the description names, beside `ec` (a sentence naming
    #: two is not grounded in either).
    other_enzymes: Tuple[Tuple[str, str, str], ...] = ()
    #: (typed, EC, name, how) for words that name one enzyme only once its
    #: stereo labels are set aside ("lysine oxidase", L-lysine oxidase):
    #: not read as naming it, and said.
    near: Optional[Tuple[str, str, str, str]] = None
    #: Organisms the description names when it names more than one.
    organisms_named: Tuple[Tuple[str, str], ...] = ()
    #: (typed, organism name it is close to) for a word placed where an
    #: organism goes that is a near spelling of one ("humna"), when no
    #: organism was read; (typed, None) for words after "from" just after
    #: the enzyme that name no organism Caterva knows. Never read as an
    #: organism: said.
    unread_organism: Optional[Tuple[str, Optional[str]]] = None
    #: The description with the enzyme, organism and inhibitor spans removed.
    remainder: str = ""
    #: The protein of `ec` the enzyme words name (HK2, CYP2B6, PTGS2), for
    #: `--isoform`; None when they name the whole enzyme. (ADR 0182)
    isoform: Optional[str] = None
    #: True when `organism` was not named but assumed from the enzyme's
    #: name (a human gene symbol, HIV-1 protease); `organism_note` says so.
    organism_assumed: bool = False
    #: Sentences about how the enzyme words were read beyond the name: the
    #: isoform, a spelling, a mutation set aside. Part of `enzyme_note`.
    read_notes: Tuple[str, ...] = ()
    #: The words after a bare "with" (or "in the presence of" in a sentence
    #: not about inhibition) when no inhibitor was read: a compound that may
    #: be the inhibitor. The caller decides, against BRENDA's Ki list and
    #: the substrates BRENDA lists, never this reader.
    possible_inhibitor_text: Optional[str] = None
    #: Point mutations typed after the enzyme ("R132H"): not modelled, said.
    mutations: Tuple[str, ...] = ()

    @property
    def names_enzyme(self) -> bool:
        """True when the description names an enzyme, resolved or ambiguous."""
        return self.ec is not None or self.ambiguity is not None

    def enzyme_note(self) -> Optional[str]:
        if self.ec is None:
            return None
        name = f" ({self.enzyme_name})" if self.enzyme_name else ""
        how = self.how or "read from your description"
        text = f"Read {self.enzyme_text!r} in your description as EC {self.ec}{name}: {how}."
        if self.read_notes:
            text += " " + " ".join(self.read_notes)
        if self.cautions:
            text += " " + " ".join(self.cautions)
        return text

    def near_note(self) -> str:
        typed, ec, name, _ = self.near
        return (f"The words {typed!r} in your description match EC {ec} ({name}) only once stereo labels "
                f"or a parenthesised word are set aside, which is not taken as naming it (pass --subject "
                f"{ec} if it is the enzyme you mean).")

    def organism_note(self) -> Optional[str]:
        if self.organism is None:
            return None
        if self.organism_assumed:
            return (f"Your description names no organism; {self.enzyme_text!r} names an enzyme of "
                    f"{self.organism}, so {self.organism} was searched (pass --organism to change it).")
        if self.organism_text == self.organism:
            return f"Read the organism {self.organism} from your description."
        return f"Read {self.organism_text!r} in your description as {self.organism}."

    def unread_organism_note(self) -> str:
        typed, close = self.unread_organism
        if close is None:
            return (f"{typed!r} in your description stands where the organism goes, but it is not an organism "
                    "name Caterva knows, so no organism was read from your description and it was not tried "
                    "as a substrate (pass --organism with the binomial BRENDA uses, e.g. --organism "
                    "\"Canavalia ensiformis\" for jack bean).")
        return (f"{typed!r} in your description was not read as an organism: it is close to {close!r}, "
                f"but a near spelling is never taken as one, so no organism was read from your "
                f"description (pass --organism if you mean one).")

    def notes(self) -> List[str]:
        """The sentences a report prints: what was read, as what."""
        out = [n for n in (self.enzyme_note(), self.organism_note()) if n]
        if self.inhibitor_text:
            out.append(f"Read {self.inhibitor_text!r} in your description as the inhibitor.")
        if len(self.organisms_named) > 1:
            out.append("Your description names " + " and ".join(
                f"{typed!r} ({binomial})" for typed, binomial in self.organisms_named)
                + "; no organism was read from it, because choosing one would be a guess.")
        if self.unread_organism is not None:
            out.append(self.unread_organism_note())
        if self.near is not None and self.ec is None:
            out.append(self.near_note())
        if self.other_enzymes:
            out.append("Your description also names " + "; ".join(
                f"{typed!r} (EC {ec}, {name})" for typed, ec, name in self.other_enzymes)
                + ", so no enzyme was read from it: a model grounded in one of several named enzymes "
                "would carry constants for a protein the sentence did not single out.")
        return out


# ---------------------------------------------------------------------------
# Substrate abbreviations
# ---------------------------------------------------------------------------

#: Lab abbreviations of substrates, and the names BRENDA lists the compound
#: under. Each value is a list of GROUPS: the names in one group are one
#: compound spelled the ways BRENDA's rows spell it (trypsin's page lists
#: "N-benzoyl-DL-arginine 4-nitroanilide", "Nalpha-benzoyl-DL-arginine
#: 4-nitroanilide" and "Nalpha-benzoyl-DL-arginine-4-nitroanilide"), and a
#: later group is a different compound the letters are also used for (L-BAPNA
#: after DL-BAPNA). `match_substrate` takes the first group with a name
#: BRENDA lists, and within it the spelling with the most rows. Checked
#: against the live BRENDA pages for 3.4.21.4, 3.2.1.23, 3.1.3.1, 2.7.1.40,
#: 3.1.1.7 and 3.4.15.1 on 2026-11-11.
SUBSTRATE_ABBREVIATIONS: Dict[str, Tuple[Tuple[str, ...], ...]] = {
    "bapna": (
        ("N-benzoyl-DL-arginine 4-nitroanilide", "Nalpha-benzoyl-DL-arginine 4-nitroanilide",
         "Nalpha-benzoyl-DL-arginine-4-nitroanilide", "N-alpha-benzoyl-DL-arginine 4-nitroanilide",
         "N-benzoyl-DL-arginine-4-nitroanilide", "N-benzoyl-DL-arginine p-nitroanilide",
         "Nalpha-benzoyl-DL-arginine p-nitroanilide", "benzoyl-DL-arginine-p-nitroanilide"),
        ("benzoyl-L-arginine-p-nitroanilide", "N-benzoyl-L-arginine-p-nitroanilide",
         "N-alpha-benzoyl-L-arginine 4-nitroanilide", "N-alpha-benzoyl-L-arginine-p-nitroanilide",
         "Nalpha-benzoyl-L-arginine 4-nitroanilide", "N-benzoyl-L-arginine 4-nitroanilide",
         "Nalpha-benzoyl-L-arginine-4-nitroanilide"),
    ),
    "lbapna": (
        ("benzoyl-L-arginine-p-nitroanilide", "N-benzoyl-L-arginine-p-nitroanilide",
         "N-alpha-benzoyl-L-arginine 4-nitroanilide", "N-alpha-benzoyl-L-arginine-p-nitroanilide",
         "Nalpha-benzoyl-L-arginine 4-nitroanilide", "N-benzoyl-L-arginine 4-nitroanilide",
         "Nalpha-benzoyl-L-arginine-4-nitroanilide"),
    ),
    "baee": (
        ("Nalpha-benzoyl-L-arginine ethyl ester", "N-alpha-benzoyl-L-arginine ethyl ester",
         "N-benzoyl-L-arginine ethyl ester", "N-alpha-benzoyl-L-Arg ethyl ester", "N-benzoyl-L-Arg ethyl ester",
         "benzoyl-L-arginine ethyl ester", "benzoyl-Arg ethyl ester"),
    ),
    "onpg": (
        ("2-nitrophenyl beta-D-galactopyranoside", "2-nitrophenyl-beta-D-galactopyranoside",
         "o-nitrophenyl beta-D-galactopyranoside", "o-nitrophenyl-beta-D-galactopyranoside",
         "2-nitrophenyl beta-D-galactoside", "2-nitrophenyl-beta-D-galactoside",
         "o-nitrophenyl beta-D-galactoside", "o-nitrophenyl-beta-D-galactoside",
         "ortho-nitrophenyl-beta-D-galactopyranoside"),
    ),
    "pnpp": (("4-nitrophenyl phosphate", "p-nitrophenyl phosphate", "4-nitrophenylphosphate",
              "p-nitrophenylphosphate"),),
    "pnpa": (("4-nitrophenyl acetate", "p-nitrophenyl acetate"),),
    "pep": (("phosphoenolpyruvate",),),
    "atch": (("acetylthiocholine", "acetyl thiocholine", "acetylthiocholine iodide", "acetylthiocholine chloride"),),
    "atci": (("acetylthiocholine iodide", "acetylthiocholine"),),
    "btch": (("butyrylthiocholine", "S-butyrylthiocholine", "butyrylthiocholine iodide"),),
    "g6p": (("D-glucose 6-phosphate", "glucose 6-phosphate", "D-glucose-6-phosphate"),),
    "f6p": (("D-fructose 6-phosphate", "fructose 6-phosphate", "D-fructose-6-phosphate"),),
    "fbp": (("D-fructose 1,6-bisphosphate", "fructose 1,6-bisphosphate", "D-fructose-1,6-bisphosphate"),),
    "f16bp": (("D-fructose 1,6-bisphosphate", "fructose 1,6-bisphosphate", "D-fructose-1,6-bisphosphate"),),
    "nad": (("NAD+", "beta-NAD+"),),
    "nadh": (("NADH", "beta-NADH"),),
    "nadp": (("NADP+", "beta-NADP+"),),
    "nadph": (("NADPH", "beta-NADPH"),),
    "nicotinamideadeninedinucleotide": (("NAD+",),),
    "hhl": (("hippuryl-His-Leu", "hippuryl-L-His-L-Leu", "hippuryl-L-histidyl-L-leucine", "Hip-His-Leu"),),
    "akg": (("2-oxoglutarate",),),
    "aaket": (("2-oxoglutarate",),),
    "2og": (("2-oxoglutarate",),),
    "accoa": (("acetyl-CoA",),),
    "sam": (("S-adenosyl-L-methionine",),),
    "adomet": (("S-adenosyl-L-methionine",),),
    "dhf": (("7,8-dihydrofolate", "dihydrofolate"),),
    "thf": (("5,6,7,8-tetrahydrofolate", "tetrahydrofolate"),),
    # Round-1 finding F13 (2026-11-11): "glutathione S-transferase with CDNB"
    # matched nothing and the cosubstrate glutathione was chosen instead,
    # and "catalase with hydrogen peroxide" said the typed compound "was
    # not used" before using H2O2, the same molecule. Spellings checked
    # against the live BRENDA pages for 2.5.1.18, 1.11.1.6, 1.11.1.7,
    # 3.1.1.7, 3.1.1.8, 1.8.1.7, 1.1.1.34, 1.1.1.37, 5.3.1.1, 1.2.1.12,
    # 4.1.1.39, 3.1.4.17, 3.4.22.56, 3.5.2.6 and 4.2.1.1 on 2026-11-11.
    "cdnb": (("1-chloro-2,4-dinitrobenzene",),),
    "hydrogenperoxide": (("H2O2", "hydrogen peroxide"),),
    "h2o2": (("H2O2", "hydrogen peroxide"),),
    "abts": (("2,2'-azinobis(3-ethylbenzthiazoline-6-sulfonic acid)",
              "2,2'-azino-bis-(3-ethylbenzthiazole-6-sulfonic acid)",
              "2,2'-azino-bis(3-ethylbenzthiazole-6-sulfonic acid)",
              "2,2'-azino-bis(3-ethylbenzthiazoline-6-sulfonic acid)",
              "2,2'-azino-bis (3-ethylbenzthiazoline-6-sulphonic acid)",
              "2,2'-azino-bis(3-ethylbenzothiazoline-6-sulfonic acid)"),),
    "tmb": (("3,3',5,5'-tetramethylbenzidine",),),
    "opd": (("o-phenylenediamine",),),
    "ach": (("acetylcholine", "acetylcholine chloride", "acetylcholine iodide"),),
    "gsh": (("glutathione", "reduced glutathione"),),
    "reducedglutathione": (("glutathione", "reduced glutathione"),),
    "gssg": (("GSSG", "glutathione disulfide", "oxidized glutathione"),),
    "glutathionedisulfide": (("GSSG", "glutathione disulfide", "oxidized glutathione"),),
    "oxidizedglutathione": (("GSSG", "glutathione disulfide", "oxidized glutathione"),),
    "oxidisedglutathione": (("GSSG", "glutathione disulfide", "oxidized glutathione"),),
    "hmgcoa": (("3-hydroxy-3-methylglutaryl-CoA", "HMG-CoA", "3-hydroxy-3-methylglutaryl-coenzyme A"),
               ("(S)-3-hydroxy-3-methylglutaryl-CoA",)),
    "oaa": (("oxaloacetate",),),
    "dhap": (("glycerone phosphate", "dihydroxyacetone phosphate", "dihydroxyacetone 3-phosphate"),),
    "gap": (("D-glyceraldehyde 3-phosphate", "D-glyceraldehyde-3-phosphate"),),
    "rubp": (("D-ribulose 1,5-bisphosphate", "D-ribulose-1,5-bisphosphate"),),
    "cyclicamp": (("3',5'-cAMP", "cAMP", "adenosine 3',5'-cyclic phosphate"),),
    "cyclicgmp": (("3',5'-cGMP", "cGMP", "guanosine 3',5'-cyclic phosphate"),),
    "acdevdamc": (("acetyl-DEVD-7-amido-4-methylcoumarin", "Ac-DEVD-4-methylcoumarin 7-amide",
                   "Ac-DEVD-AMC", "acetyl-Asp-Glu-Val-Asp-7-amido-4-methylcoumarin"),),
    "acdevdpna": (("acetyl-DEVD-4-nitroanilide", "Ac-DEVD-pNA", "acetyl-Asp-Glu-Val-Asp-4-nitroanilide"),),
    "carbondioxide": (("CO2",),),
    "bicarbonate": (("HCO3-", "bicarbonate"),),
    "hco3": (("HCO3-", "bicarbonate"),),
    "oxygen": (("O2",),),
    "water": (("H2O", "water"),),
    "penicilling": (("benzylpenicillin", "penicillin G"),),
    # Chromogenic and fluorogenic substrates by their trade codes and lab
    # abbreviations. Spellings checked against the live BRENDA pages for
    # 3.4.21.5, 3.4.21.6, 3.4.21.1, 3.4.21.62 and 3.2.1.18 on 2026-11-11:
    # "thrombin with S-2238" used to drop S-2238 as a strain tag.
    "s2238": (("D-phenylalanyl-pipecolyl-L-arginine-4-nitroanilide", "D-Phe-L-pipecolyl-L-Arg-4-nitroanilide",
               "D-Phe-Pip-Arg-4-nitroanilide", "S2238"),),
    # S-2222 is Bz-Ile-Glu(gamma-OR)-Gly-Arg-pNA with R = H and CH3 (50:50);
    # BRENDA writes the bovine factor Xa rows "benzoyl-Ile-Glu-(-H/OMe)-...".
    # The piperidineamide (S-2337) is another substrate and is not listed.
    "s2222": (("S2222", "benzoyl-Ile-Glu-(-H/OMe)-Gly-Arg-p-nitroanilide"),),
    "s2765": (("S2765", "S-2765"),),
    "btee": (("N-benzoyl-L-tyrosine ethyl ester",),),
    "sucaapfpna": (("N-succinyl-Ala-Ala-Pro-Phe-4-nitroanilide", "N-succinyl-Ala-Ala-Pro-Phe-p-nitroanilide",
                    "succinyl-L-Ala-L-Ala-L-Pro-L-Phe-4-nitroanilide", "succinyl-Ala-Ala-Pro-Phe-4-nitroanilide",
                    "succinyl-Ala-Ala-Pro-Phe-p-nitroanilide", "N-succinyl-L-Ala-L-Ala-L-Pro-L-Phe-4-nitroanilide"),),
    "munana": (("4-methylumbelliferyl alpha-D-N-acetylneuraminic acid",
                "4-methylumbelliferyl-alpha-D-N-acetylneuraminic acid",
                "2'-(4-methylumbelliferyl)-alpha-D-N-acetylneuraminic acid",
                "4-methylumbelliferyl N-acetylneuraminic acid"),),
}


#: Words that say which tissue or preparation an enzyme came from ("rabbit
#: muscle LDH", "alkaline phosphatase from calf intestine", "bovine milk
#: xanthine oxidase"). A run of them alone is the enzyme's source, never a
#: substrate candidate: "muscle", "liver" and "milk" used to be offered as
#: the substrate after the one typed.
SOURCE_TISSUES = frozenset({
    "liver", "muscle", "skeletal", "heart", "cardiac", "pancreas", "pancreatic", "intestine", "intestinal",
    "milk", "stomach", "gastric", "kidney", "renal", "brain", "erythrocyte", "erythrocytes", "placenta",
    "placental", "spleen", "lung", "serum", "plasma", "blood", "tissue", "tissues", "mitochondria",
    "mitochondrial", "cytosol", "cytosolic", "microsomes", "microsomal", "seeds", "seed", "leaf", "leaves",
    "root", "roots", "tuber", "tubers", "venom", "recombinant", "purified", "commercial", "crude",
})


def _substrate_key(text: str) -> str:
    """Letters and digits only, lower case: "pNPP", "p-NPP" and "PNPP" are one key."""
    return re.sub(r"[^0-9a-z]+", "", (text or "").lower())


# ---------------------------------------------------------------------------
# Words
# ---------------------------------------------------------------------------


@dataclass
class _Token:
    raw: str       # as typed, edges stripped
    low: str       # lower case
    start: int
    end: int
    used: bool = False


def _tokens(text: str) -> List[_Token]:
    out: List[_Token] = []
    for match in re.finditer(r"\S+", text):
        raw = match.group(0)
        start, end = match.start(), match.end()
        # A bracket is an edge only when it is unmatched in the word:
        # "(-)-huperzine" and "Na(+)/K(+)-ATPase" keep theirs, "(human)"
        # loses both.
        while raw and raw[0] in _EDGE and not _balanced_open(raw):
            raw, start = raw[1:], start + 1
        while raw and (
                (raw[-1] in _EDGE and not _balanced_close(raw))
                or (raw[-1] == "." and not _keeps_dot(raw))):
            raw, end = raw[:-1], end - 1
        if raw:
            out.append(_Token(raw, raw.lower(), start, end))
    return out


_PAIRS = {"(": ")", "[": "]", "{": "}"}


def _balanced_open(raw: str) -> bool:
    """A leading bracket closed inside the word ("(-)-huperzine")."""
    close = _PAIRS.get(raw[0])
    return close is not None and raw.count(raw[0]) <= raw.count(close) and raw.find(close) < len(raw) - 1


def _balanced_close(raw: str) -> bool:
    """A trailing bracket opened inside the word ("Na(+)")."""
    opening = {v: k for k, v in _PAIRS.items()}.get(raw[-1])
    return opening is not None and raw.count(raw[-1]) <= raw.count(opening)


def _joins(token: "_Token") -> bool:
    """A joining word. A capital letter on its own is a name's ("huperzine A",
    "pepsin A"), not the article."""
    return token.low in STOPWORDS and not (len(token.raw) == 1 and token.raw.isupper())


def _keeps_dot(raw: str) -> bool:
    """A trailing dot that belongs to the word: "E." of "E. coli", "e.c.", "2.7.1.-"."""
    return bool(re.fullmatch(r"[A-Za-z]\.|e\.c\.|\d[\d.\-]*\.", raw, re.IGNORECASE))


def _organism_key(words: Sequence[_Token]) -> str:
    joined = " ".join(w.raw for w in words)
    return _POSSESSIVE.sub("", joined)


# ---------------------------------------------------------------------------
# The three readings
# ---------------------------------------------------------------------------


def _read_organism(tokens: List[_Token]) -> List[Tuple[int, int, str, str]]:
    """(first, last+1, typed, binomial) for every organism named, longest first."""
    found: List[Tuple[int, int, str, str]] = []
    taken = [False] * len(tokens)
    for size in range(4, 0, -1):
        for i in range(len(tokens) - size + 1):
            if any(taken[i:i + size]):
                continue
            words = tokens[i:i + size]
            key = _organism_key(words)
            if key.lower() in _NOT_IN_A_SENTENCE or key.lower() in STOPWORDS:
                continue
            code = organism_code(key)
            if code is None:
                continue
            found.append((i, i + size, " ".join(w.raw for w in words), ORGANISMS[code][0]))
            for k in range(i, i + size):
                taken[k] = True
    # A binomial the table does not hold, written where an organism goes:
    # "in Thermus thermophilus". Only after "in" or "from", because a
    # capitalised word and a lower-case one are also how a sentence starts
    # ("Competitive inhibition of ...").
    for i in range(1, len(tokens) - 1):
        if taken[i] or taken[i + 1] or tokens[i - 1].low not in ("in", "from"):
            continue
        genus, epithet = tokens[i].raw, _POSSESSIVE.sub("", tokens[i + 1].raw)
        if _BINOMIAL.match(genus) and _EPITHET.match(epithet) and epithet not in STOPWORDS | FILLER:
            found.append((i, i + 2, f"{genus} {epithet}", f"{genus} {epithet}"))
            taken[i] = taken[i + 1] = True
    return sorted(found)


def _organism_words() -> List[str]:
    """Every one-word name the organism table reads, lower case."""
    out = set()
    for binomial, common, aliases in ORGANISMS.values():
        for name in (binomial, common, *aliases):
            if " " not in name and "." not in name and len(name) >= 3:
                out.add(name.lower())
    return sorted(out)


def _misspelt_organism(tokens: List[_Token]) -> Optional[Tuple[str, str]]:
    """(typed, close name) for an unread word where an organism goes -- just
    before a word read as the enzyme, or after "in"/"from" -- that is a near
    spelling of a one-word organism name.

    "Michaelis-Menten kinetics of humna hexokinase on glucose" read no
    organism and said nothing about 'humna': the search then ranked without
    one and the report never showed that a word meant as the organism had
    gone unread. It is still never READ as human: a near spelling is a
    guess, and the organism decides whose constants are cited. It is said.
    """
    import difflib

    names = _organism_words()
    for i, token in enumerate(tokens):
        if token.used or token.low in STOPWORDS or token.low in FILLER or len(token.low) < 3:
            continue
        before_enzyme = i + 1 < len(tokens) and tokens[i + 1].used
        after_in = i > 0 and tokens[i - 1].low in ("in", "from")
        if not (before_enzyme or after_in):
            continue
        close = difflib.get_close_matches(token.low, names, n=1, cutoff=0.8)
        if close:
            return token.raw, close[0]
    return None


#: Words that read as a compound, never as where an enzyme came from.
_COMPOUND_LIKE = re.compile(r"\d|(?:ose|ate|ide|ine|ol|one|ene|yl|ium|ase)$")


def _unread_source(tokens: List[_Token], text: str) -> Optional[Tuple[str, None]]:
    """(typed, None) for the words after "from" just after the enzyme
    ("urease from sword bean") when no organism was read from them: that is
    where a description says whose enzyme it is.

    They used to be passed over, tried as substrate words ("No word ('hen
    egg white') is a substrate BRENDA lists"), and the report then said "No
    organism was named" while choosing one (round-1 finding F04). They are
    taken out of the substrate candidates and said to be an organism Caterva
    does not know, never read as one.
    """
    for i, token in enumerate(tokens):
        if token.low != "from" or token.used or i == 0 or not tokens[i - 1].used:
            continue
        span = _phrase_after(tokens, i + 1)
        if span is None:
            continue
        words = tokens[span[0]:span[1]]
        if all(w.low in FILLER for w in words) or any(_COMPOUND_LIKE.search(w.low) for w in words):
            # "hexokinase from glucose": a compound, not a source.
            continue
        for w in words:
            w.used = True
        return text[words[0].start:words[-1].end], None
    return None


def _is_class_window(words: Sequence[_Token]) -> bool:
    """Only class words and joining words. A capital letter on its own is a
    name's, not the article: "protein kinase A" is cAMP-dependent protein
    kinase, and reading its "A" as "a" set the whole window aside."""
    # The window's first word is the article whatever its case ("A kinase
    # and a phosphatase"); a capital letter after a class word is the name's.
    return all(w.low.strip("-") in CLASS_WORDS or _joins(w) or (k == 0 and w.low in STOPWORDS)
               for k, w in enumerate(words))


def _acceptable(result: Resolved, typed: str) -> bool:
    """A resolution that is not a stretch: see the module docstring."""
    candidate = result.candidate
    if candidate is None:
        return False
    if candidate.tier == TIER_EC:
        return True
    if _substrate_key(typed) in SUBSTRATE_ABBREVIATIONS:
        # "PEP", "FBP", "G6P": a compound in a sentence, whatever enzyme
        # the letters are also an abbreviation of.
        return False
    if candidate.via == "abbreviation" or (
            result.symbol_read or result.isoform is not None or result.notes) and candidate.via != "typo":
        # A symbol, abbreviation or alias the table reads as ONE enzyme
        # (ADR 0182). Written as one: a capital letter and three
        # characters ("HK2", "CYP2B6", "AChE"), or a name in words
        # ("angiotensin-converting enzyme", "HIV-1 protease").
        if is_abbreviation(typed):
            # "p38" is written in lower case and is no English word: a
            # letter beside a digit marks it as a symbol as a capital does.
            letters = re.sub(r"[^0-9A-Za-z]", "", typed)
            marked = any(ch.isupper() for ch in typed) or (
                any(ch.isdigit() for ch in letters) and any(ch.isalpha() for ch in letters))
            return len(letters) >= 3 and marked
        return True
    if candidate.partial or candidate.via != "name":
        return False
    if candidate.tier not in (TIER_ACCEPTED_EXACT, TIER_ALTERNATIVE_EXACT):
        return False
    if candidate.abbreviation:
        # "ACE" and "PKA" are confirmed abbreviations; "ace" in a sentence is
        # a word. Two letters are never enough.
        letters = re.sub(r"[^0-9A-Za-z]", "", typed)
        return candidate.confirmed and len(letters) >= 3 and any(ch.isupper() for ch in typed)
    return True


def _near(result: object) -> bool:
    """A unique resolution the reader does not accept: an accepted or other
    name met only once stereo labels or a glued parenthesis are set aside."""
    candidate = getattr(result, "candidate", None)
    return (isinstance(result, Resolved) and candidate is not None and not candidate.partial
            and candidate.via == "name" and candidate.tier in (TIER_ACCEPTED_TOLERANT, TIER_ALTERNATIVE_TOLERANT))


def _reportable(result: Ambiguous) -> bool:
    """An ambiguity worth refusing over: several enzymes whose NAMES the words
    are, not a phrase inside many names or a did-you-mean."""
    if result.suggestions_only or result.confirm_only or not result.candidates:
        return False
    best = result.candidates[0]
    tied = [c for c in result.candidates if c.tier == best.tier]
    if best.tier == TIER_EC:
        return True
    return (best.tier <= TIER_ALTERNATIVE_TOLERANT and all(not c.partial and c.via == "name" for c in tied))


def _could_be_enzyme_words(typed: str) -> bool:
    """Cheap test before `resolve` for the not-one-enzyme pass: an
    abbreviation the symbol table holds, or words whose last one ends the
    way an enzyme's name ends (-ase, -zyme, -in)."""
    from .symbols import load_symbols

    if load_symbols().knows(typed) or _could_be_a_name(typed) or _written_as_a_mnemonic(typed):
        return True
    words = loose_key(typed).split()
    if len(words) == 1 and _near_a_one_word_name(words[0]):
        return True
    if _misspelt_head(words):
        return True
    if not words or not (_ENZYME_ENDING.search(words[-1]) or len(words) == 1 and _TYPO_ENDING.search(words[-1])):
        return False
    # Several words: each one a word of some enzyme name ("DNA polymerase",
    # "aldehyde dehydrogenase"), so a run like "kinase cascade with
    # phosphatases" never reaches the finder's slow fuzzy search.
    vocabulary = _tables(load_index()).vocabulary
    if len(words) > 1:
        return all(w in vocabulary for w in words)
    word = words[0]
    if _ENZYME_ENDING.search(word) and (word in vocabulary or _could_be_a_name(typed)):
        return True
    # A near spelling: not a word of any name, nor a plural of one
    # ("phosphatases"), and close to one -- checked here because the
    # finder's own fuzzy search over every name takes seconds.
    if word in vocabulary or word.rstrip("s") in vocabulary or word.rstrip("s") in CLASS_WORDS:
        return False
    import difflib

    return bool(difflib.get_close_matches(word, _long_vocabulary(), n=1, cutoff=0.8))


_LONG_VOCABULARY: Optional[List[str]] = None


def _long_vocabulary() -> List[str]:
    """Words of enzyme names at least eight letters long and ending -ase."""
    global _LONG_VOCABULARY
    if _LONG_VOCABULARY is None:
        _LONG_VOCABULARY = sorted(w for w in _tables(load_index()).vocabulary
                                  if len(w) >= 8 and w.endswith("ase"))
    return _LONG_VOCABULARY


#: A word one letter away from ending -ase ("hexokinaze", "lipasse" aside).
_TYPO_ENDING = re.compile(r"(?:a.e|.se|as.)$")

_ONE_WORD_NAMES: Optional[List[str]] = None


def _one_word_names() -> List[str]:
    """Enzyme names that are one word not ending -ase ("chymotrypsin",
    "lysozyme", "papain", "thrombin"), seven letters or more, lower case."""
    global _ONE_WORD_NAMES
    if _ONE_WORD_NAMES is None:
        found = set()
        for entry in load_index().entries.values():
            if entry.status != "active":
                continue
            for name in (entry.name, *entry.alternative_names):
                word = name.strip().lower()
                if (len(word) >= 7 and word.isalpha() and not word.endswith(("ase", "ases"))
                        and word.endswith(("in", "ain", "zyme"))):
                    found.add(word)
        _ONE_WORD_NAMES = sorted(found)
    return _ONE_WORD_NAMES


def _near_a_one_word_name(word: str) -> bool:
    """A misspelling of a one-word enzyme name that does not end -ase
    ("chymotripsin", "trypsine", "lysozme"): not a word of any enzyme name,
    seven letters or more, and within one or two letters of the name
    (difflib ratio 0.9: "plasmid" is not "plasmin"). Review of the names
    stream, 2026-11-12: these were dropped, and "Michaelis-Menten for
    chymotripsin in bovine" reported that no enzyme was named."""
    word = word.lower()
    if len(word) < 7 or not word.isalpha() or word in _tables(load_index()).vocabulary:
        return False
    import difflib

    return bool(difflib.get_close_matches(word, _one_word_names(), n=1, cutoff=0.9))


def _misspelt_head(words: Sequence[str]) -> bool:
    """Several words, each but the last a word of some enzyme name, and the
    last one letter or two from a word ending -ase that names use ("pyruvate
    kinaze", "lactate dehydrogenaze"). Review of the names stream,
    2026-11-12: these were passed over in silence and the report said no
    enzyme was named; a one-word one ("hexokinaze") was already refused."""
    if len(words) < 2:
        return False
    vocabulary = _tables(load_index()).vocabulary
    last = words[-1]
    if (not last.isalpha() or len(last) < 5 or last in vocabulary or _TYPO_ENDING.search(last) is None
            or not all(w in vocabulary for w in words[:-1])):
        return False
    import difflib

    heads = _ase_heads()
    return bool(difflib.get_close_matches(last, heads, n=1, cutoff=0.8))


_ASE_HEADS: Optional[List[str]] = None


def _ase_heads() -> List[str]:
    """Words of enzyme names five letters or more ending -ase."""
    global _ASE_HEADS
    if _ASE_HEADS is None:
        _ASE_HEADS = sorted(w for w in _tables(load_index()).vocabulary if len(w) >= 5 and w.endswith("ase"))
    return _ASE_HEADS


def _written_as_a_mnemonic(typed: str) -> bool:
    """Written as a symbol is (capitals and digits, at least three LETTERS:
    "PLK1", "GSK3B", "NAMPT"; never "CO2") and the part before the
    underscore of some UniProt entry name the enzyme index lists. The
    finder offers such a word only as a reading to confirm, never resolves
    it (finder rule b), so it reaches the reader as a refusal at most."""
    from .symbols import human_style

    letters = re.sub(r"[^A-Za-z]", "", typed)
    return (human_style(typed) and len(letters) >= 3 and " " not in typed
            and strict_key(typed) in _tables(load_index()).symbols)


def _mnemonic_reading(result: object, typed: str, rank_by: Optional[str]) -> Optional[Ambiguous]:
    """A refusal naming the enzyme(s) whose UniProt entry name `typed` is,
    for the organism given or, with none given, for Homo sapiens when it is
    written as a human gene symbol is; else None.

    "PLK1 kinetics in human", "TPMT in human with 6-mercaptopurine" and
    "GSK3B in human" were passed over in silence (review of the names
    stream, 2026-11-12): the gene-symbol table holds a curated set of
    symbols, and these are not in it, so the reader saw no enzyme and the
    report said none was named. The entry name is not always the gene
    symbol (SYK_HUMAN is a lysine--tRNA ligase), so it is never read as the
    enzyme: the person confirms it with --subject and --isoform.
    """
    if not _written_as_a_mnemonic(typed):
        return None
    assumed = None
    if isinstance(result, Ambiguous) and not result.candidates and rank_by is None:
        assumed = "Homo sapiens"
        result = resolve(typed, assumed)
    if not isinstance(result, Ambiguous) or not result.candidates:
        return None
    if not all(c.via == "mnemonic" for c in result.candidates):
        return None
    where = organism_code(rank_by or assumed)
    reason = (f"{typed!r} is not a name or symbol Caterva reads an enzyme by: it is the UniProt entry name "
              f"{typed.upper()}_{where} of a protein the enzyme nomenclature lists under "
              + ("this enzyme" if len(result.candidates) == 1 else f"{len(result.candidates)} enzymes")
              + (", taking the organism as Homo sapiens because none was named and it is written as a human "
                 "gene symbol is" if assumed else "")
              + ". An entry name is not always the gene symbol, so it is not read as the enzyme without you; "
              f"add --isoform {typed} to the re-run to take the constants from rows that name it")
    return Ambiguous(query=typed, candidates=tuple(result.candidates), confirm_only=True,
                     organism=where, release=result.release, reason=reason)


def _two_letter_symbol(result: Resolved, typed: str) -> bool:
    """A two-capital-letter symbol the symbol table read as ONE enzyme in
    the organism ("CS" citrate synthase, "TS" thymidylate synthase), which
    `_acceptable` does not take from a sentence."""
    return (result.symbol_read and result.candidate is not None and len(typed) == 2
            and typed.isalpha() and typed.isupper() and not _acceptable(result, typed))


def _symbol_of_another_organism(typed: str) -> bool:
    """A symbol written as one (a capital, three characters) that the symbol
    table holds for some organism: refused, not passed over, when it is not
    read for the organism given."""
    from .symbols import load_symbols

    letters = re.sub(r"[^0-9A-Za-z]", "", typed)
    table = load_symbols()
    return (len(letters) >= 3 and any(ch.isupper() for ch in typed)
            and bool(table.organisms_for(typed) or table.alias_organisms(typed)))


def _names_some_enzyme(result: Ambiguous, typed: str) -> bool:
    """Whether an `Ambiguous` the reader would otherwise pass over is still
    the description naming an enzyme, to be refused with its candidates:

    * an abbreviation or symbol offered for confirmation (`confirm_only`),
      written as one (a capital letter, three characters: "LDH", "NOS",
      "tPA"), or a name the symbol table lists ("HMG-CoA reductase");
    * words that are a whole-word phrase inside the names of the enzymes
      that match best, ending the way an enzyme's name ends ("amylase",
      "DNA polymerase", "aldehyde dehydrogenase");
    * a near spelling (`suggestions_only`, typo candidates) of a word of at
      least eight letters ending -ase or -zyme that no enzyme name uses
      ("hexokinaze").

    A class word ("kinase", "protein kinase") is none of these: the caller
    has already set class windows aside, and the finder marks the rest.
    """
    from .finder import SPELLING_MIN_LENGTH
    from .symbols import load_symbols

    if not result.candidates or result.class_word:
        return False
    best = min(c.tier for c in result.candidates)
    tied = [c for c in result.candidates if c.tier == best]
    letters = re.sub(r"[^0-9A-Za-z]", "", typed)
    if result.confirm_only:
        written_as_one = len(letters) >= 3 and any(ch.isupper() for ch in typed)
        return written_as_one and (is_abbreviation(typed) or load_symbols().knows(typed))
    last = strict_key(typed).split()[-1]
    if all(c.tier == TIER_TYPO for c in result.candidates):
        if " " not in strict_key(typed) and _near_a_one_word_name(last):
            return True
        if _misspelt_head(loose_key(typed).split()):
            return True
        return (" " not in strict_key(typed) and len(last) >= SPELLING_MIN_LENGTH
                and _TYPO_ENDING.search(last) is not None and last not in _tables(load_index()).vocabulary)
    if not _ENZYME_ENDING.search(last) or len(last) < 5:
        return False
    # A phrase inside the names (not words scattered over one) that is the
    # HEAD of at least one of them -- the words its name ends on, a
    # qualifier in parentheses aside: "amylase" ends "alpha-amylase",
    # "aldehyde dehydrogenase" ends "aldehyde dehydrogenase (NAD(+))".
    # "heparin" is inside "heparin lyase" but heads no name: a compound.
    if best > TIER_ALTERNATIVE_PHRASE or not all(c.partial and c.via == "name" for c in tied):
        return False
    tail = f" {loose_key(typed)}"
    return any(_head(f" {loose_key(_outside_parentheses(name))}").endswith(tail)
               for c in tied for name in (c.name, *c.alternative_names))


#: A designator a family name is numbered or lettered by: the "1" of
#: calpain-1, the "B" of cathepsin B, the "II" of carbonic anhydrase II.
_DESIGNATOR = re.compile(r" (?:\d+|[ivx]+|[a-z])$")


def _head(key: str) -> str:
    """A loose name key without its trailing designator: "calpain" heads
    "calpain-1" and "calpain-2", so the word names that family, to be
    refused with its members named (it used to be passed over in silence)."""
    return _DESIGNATOR.sub("", key)


def _name_keys() -> frozenset:
    """Every key an enzyme name can be met by: strict, loose and bare.

    `resolve` scans the whole nomenclature on each call (about 0.2 s), so a
    window is resolved only when some name has its key: a sentence of ten
    words has some forty windows, and every one of them going to the finder
    made a plain-language compose seconds slower than a flag.
    """
    tables = _tables(load_index())
    keys = set()
    for name in tables.names:
        keys.update((name.strict, name.loose, name.bare))
    # A name written with its spaces moved ("butyrylcholinesterase" for
    # "butyrylcholine esterase"), which `resolve` reads as that name.
    keys.update("compact:" + key for key in tables.compact)
    return frozenset(keys)


_KEYS: Optional[frozenset] = None


def _could_be_a_name(text: str) -> bool:
    global _KEYS
    if _KEYS is None:
        _KEYS = _name_keys()
    from .symbols import load_symbols

    from .finder import respelt_symbol

    return (strict_key(text) in _KEYS or loose_key(text) in _KEYS
            or "compact:" + compact_name_key(text) in _KEYS or load_symbols().knows(text)
            or respelt_symbol(text) is not None
            or any("compact:" + key in _KEYS for key in _joined_once(text)))


def _joined_once(text: str) -> List[str]:
    """The compact keys of `text` with the letter two words share at a join
    written once: "acetylcholine esterase" -> "acetylcholinesterase", the
    listed name (finder._spacing_variant reads it so)."""
    words = strict_key(text).split()
    out = []
    for i in range(len(words) - 1):
        if words[i] and words[i + 1] and words[i][-1] == words[i + 1][0] and words[i][-1].isalpha():
            out.append("".join(words[:i + 1]) + "".join(words[i + 1:])[1:])
    return out


def _read_ec(tokens: List[_Token]) -> List[Tuple[int, int, str]]:
    """(first, last+1, typed) of every EC number written: "EC 2.7.1.1", "2.7.1.1",
    "EC:2.7.1.1". A bare number needs four parts ("2.5" is a concentration);
    a class needs the EC in front of it ("EC 2.7.1")."""
    out: List[Tuple[int, int, str]] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if _EC_FULL.match(token.raw):
            out.append((i, i + 1, token.raw))
        elif _EC_WORD.match(token.raw) and i + 1 < len(tokens) and _EC_PARTIAL.match(tokens[i + 1].raw):
            out.append((i, i + 2, f"{token.raw} {tokens[i + 1].raw}"))
            i += 1
        i += 1
    return out


def _windows(tokens: List[_Token]):
    """Unconsumed word windows, longest first, never starting or ending on a
    joining word."""
    for size in range(min(MAX_WINDOW, len(tokens)), 0, -1):
        for i in range(len(tokens) - size + 1):
            words = tokens[i:i + size]
            if any(w.used for w in words):
                continue
            if _joins(words[0]) or _joins(words[-1]):
                continue
            yield i, i + size, words


def _phrase_after(tokens: List[_Token], i: int) -> Optional[Tuple[int, int]]:
    """The run of unconsumed, non-joining words starting at i."""
    j = i
    while j < len(tokens) and not tokens[j].used and not _joins(tokens[j]):
        j += 1
    return (i, j) if j > i else None


def _about_inhibition(tokens: List[_Token]) -> bool:
    return any(t.low.startswith(("inhibit", "block")) for t in tokens)


def _phrase_before(tokens: List[_Token], i: int) -> Optional[Tuple[int, int]]:
    """The run of unconsumed, non-joining, non-filler words ending just before i."""
    j = i
    while j > 0 and not tokens[j - 1].used and not _joins(tokens[j - 1]) and tokens[j - 1].low not in FILLER:
        j -= 1
    return (j, i) if j < i else None


def _read_inhibitor(tokens: List[_Token]) -> Optional[Tuple[int, int]]:
    lows = [t.low for t in tokens]
    about_inhibition = _about_inhibition(tokens)
    for i, word in enumerate(lows):
        start = None
        if word in ("inhibitor", "inhibitors") and i + 1 < len(tokens) and not _joins(tokens[i + 1]) \
                and not all(t.low in FILLER for t in tokens[i + 1:(_phrase_after(tokens, i + 1) or (i, i + 1))[1]]):
            start = i + 1
        elif word in ("inhibitor", "inhibitors") and i > 0:
            # "a celecoxib inhibitor"? No: "X inhibitor" is "the drug X as
            # the inhibitor" only when X is not the enzyme ("a COX-2
            # inhibitor" names the enzyme, already consumed) and not a
            # mode ("competitive inhibitor", filler).
            span = _phrase_before(tokens, i)
            if span is not None:
                # "ACE inhibitor", "kinase inhibitor": an inhibitor OF an
                # enzyme, not a compound called that.
                typed = " ".join(t.raw for t in tokens[span[0]:span[1]])
                if not _could_be_a_name(typed):
                    return span
            continue
        elif word == "presence" and about_inhibition and i + 2 < len(tokens) and lows[i + 1] == "of":
            start = i + 2
        elif (word == "by" and about_inhibition and i > 0
              and (lows[i - 1].startswith(("inhibit", "block")) or tokens[i - 1].used)):
            # Only "inhibited by X", "inhibition by X" or "<enzyme or
            # organism> by X". Any "by" after an inhibition word read
            # "competitive inhibition of hexokinase on glucose measured by
            # fluorescence" as inhibited by fluorescence, and the report said
            # so; the Ki stayed a placeholder only because BRENDA has no
            # "fluorescence" row.
            start = i + 1
        if start is None:
            continue
        span = _phrase_after(tokens, start)
        if span is not None:
            words = [t.low for t in tokens[span[0]:span[1]]]
            if not all(w in FILLER for w in words):
                return span
    return None


#: How the symbol table's sentence about an assumed organism starts; that
#: sentence goes to `organism_note`, not the enzyme note.
_ASSUMED = "No organism was given"


def _is_tag(raw: str) -> bool:
    """A virus, strain or construct tag, a bare number or a mutation: never a
    compound. A substrate abbreviation ("G6P", "F6P") is not a tag."""
    if _substrate_key(raw) in SUBSTRATE_ABBREVIATIONS:
        return False
    return bool(_TAG.match(raw) or _MUTATION.match(raw))


def _assumed_organism(read_organism, given: Optional[str], assumed: Optional[str], organisms) -> Dict[str, object]:
    """organism fields of the reading: the one named, else the one the
    enzyme's name implies when nothing was given or named."""
    if read_organism is not None:
        return {"organism": read_organism[1], "organism_text": read_organism[0]}
    if assumed and not given and not organisms:
        return {"organism": assumed, "organism_text": None, "organism_assumed": True}
    return {"organism": None, "organism_text": None}


def read_sentence(text: str, organism: Optional[str] = None) -> SentenceReading:
    """What `text` names. `organism` (anything `organism_code` reads) ranks the
    enzyme candidates, as `--organism` does; the sentence's own organism is
    used when none is given."""
    text = " ".join((text or "").split())
    tokens = _tokens(text)
    if not tokens:
        return SentenceReading(text=text, remainder=text)

    organisms = _read_organism(tokens)
    distinct = {binomial for _, _, _, binomial in organisms}
    read_organism: Optional[Tuple[str, str]] = None
    for first, last, typed, binomial in organisms:
        for k in range(first, last):
            tokens[k].used = True
    if len(distinct) == 1:
        _, _, typed, binomial = organisms[0]
        read_organism = (typed, binomial)
    rank_by = organism or (read_organism[1] if read_organism else None)

    hits: List[Tuple[int, int, str, Resolved]] = []
    ambiguity: Optional[Ambiguous] = None
    ambiguity_text: Optional[str] = None
    near: Optional[Tuple[str, str, str, str]] = None
    for first, last, typed in _read_ec(tokens):
        result = resolve(typed, rank_by)
        if isinstance(result, Resolved) and _acceptable(result, typed):
            hits.append((first, last, typed, result))
        elif isinstance(result, Ambiguous) and result.candidates and ambiguity is None:
            ambiguity, ambiguity_text = result, typed
        for k in range(first, last):
            tokens[k].used = True

    for first, last, words in _windows(tokens):
        if any(w.used for w in words):
            continue  # consumed by a longer window found earlier at this size
        if _is_class_window(words):
            continue
        typed = text[words[0].start:words[-1].end]
        if not _could_be_a_name(typed):
            continue
        result = resolve(typed, rank_by)
        if isinstance(result, Resolved) and _acceptable(result, typed):
            hits.append((first, last, typed, result))
        elif isinstance(result, Ambiguous) and _reportable(result):
            if ambiguity is None:
                ambiguity, ambiguity_text = result, typed
        elif _near(result):
            # "lysine oxidase" is L-lysine oxidase only once the L- is set
            # aside. Not read as naming it, and not silently passed over:
            # the report says which enzyme it is close to and the flag
            # that takes it.
            if near is None:
                near = (typed, result.ec, result.candidate.name, result.how)
        else:
            continue
        for k in range(first, last):
            tokens[k].used = True

    if not hits and ambiguity is None and near is None:
        # A misspelt name: ONE enzyme name within a letter or two, ending
        # the way an enzyme name ends (finder.spelling_match). Said, never
        # silent: the note reads "Read 'acetylcholinestrase' as
        # acetylcholinesterase (spelling)".
        for first, last, words in _windows(tokens):
            if len(words) > 3 or any(w.used for w in words) or _is_class_window(words):
                continue
            # A class word may END the window: it is the head of the name
            # ("acetylcholine esterase" for acetylcholinesterase was passed
            # over in silence because "esterase" is a class word; review of
            # the names stream, 2026-11-12). Anywhere else it is filler.
            if any(w.low in FILLER and not (k == len(words) - 1 and w.low in CLASS_WORDS)
                   for k, w in enumerate(words)):
                continue
            typed = text[words[0].start:words[-1].end]
            if spelling_match(typed) is None:
                continue
            result = resolve(typed, rank_by)
            if isinstance(result, Resolved) and result.candidate is not None and result.candidate.via == "typo":
                hits.append((first, last, typed, result))
                for k in range(first, last):
                    tokens[k].used = True
                break

    if not hits and ambiguity is None and near is None:
        # Words that are an enzyme's name but not ONE enzyme's: an
        # abbreviation several enzymes go by ("LDH", "HMG-CoA reductase"),
        # the head word of several names ("amylase": alpha- and
        # beta-amylase), or a near spelling with no single reading
        # ("hexokinaze"). Each used to be passed over without a word, and
        # the report then said "no enzyme was named -- name the enzyme"
        # about a description that had named one (round-1 findings M7,
        # F12). Returned as `ambiguity`, so the caller refuses with the
        # candidates named, as for "lactate dehydrogenase"; never resolved.
        for first, last, words in _windows(tokens):
            if len(words) > 4 or any(w.used for w in words) or _is_class_window(words):
                continue
            if any(_joins(w) for w in words) or any(w.low in FILLER and w.low not in CLASS_WORDS for w in words):
                continue
            typed = text[words[0].start:words[-1].end]
            if _substrate_key(typed) in SUBSTRATE_ABBREVIATIONS or not _could_be_enzyme_words(typed):
                continue
            result = resolve(typed, rank_by)
            if isinstance(result, Resolved) and _two_letter_symbol(result, typed):
                # "CS in human", "TS kinetics": the symbol table reads them as
                # one enzyme, but two letters in a sentence are too often
                # something else (a transition state, caesium) to be taken.
                # Only reached when nothing else in the description names an
                # enzyme, so the refusal names the enzyme the letters would
                # be instead of saying no enzyme was named; never resolved.
                result = Ambiguous(
                    query=typed, candidates=(result.candidate,), confirm_only=True,
                    organism=organism_code(rank_by) if rank_by else None,
                    reason=(f"{typed!r} is two letters, which a description is not read as naming an enzyme "
                            f"by (they may be something else); as a symbol, {result.how}"))
                ambiguity, ambiguity_text = result, typed
                for k in range(first, last):
                    tokens[k].used = True
                break
            if (isinstance(result, Ambiguous) and not result.candidates and rank_by
                    and _symbol_of_another_organism(typed)):
                # "CYP2D6 in rat", "MAO-A from E. coli": a symbol the table
                # reads for other organisms only. Refused with the finder's
                # reason, which says so; no other organism's enzyme is
                # offered as a candidate (round-1 finding F12: these were
                # passed over and the report said no enzyme was named).
                ambiguity, ambiguity_text = result, typed
                for k in range(first, last):
                    tokens[k].used = True
                break
            mnemonic = _mnemonic_reading(result, typed, rank_by)
            if mnemonic is not None:
                ambiguity, ambiguity_text = mnemonic, typed
                for k in range(first, last):
                    tokens[k].used = True
                break
            if isinstance(result, Ambiguous) and _names_some_enzyme(result, typed):
                ambiguity, ambiguity_text = result, typed
                for k in range(first, last):
                    tokens[k].used = True
                break

    enzyme: Optional[Tuple[str, Resolved]] = None
    others: List[Tuple[str, str, str]] = []
    distinct_ecs = []
    for _, _, typed, result in sorted(hits, key=lambda hit: hit[0]):
        if result.ec not in [ec for ec, _ in distinct_ecs]:
            distinct_ecs.append((result.ec, (typed, result)))
    if len(distinct_ecs) == 1 and ambiguity is None:
        enzyme = distinct_ecs[0][1]
    elif distinct_ecs:
        # Two enzymes named, or one named and another ambiguous: neither is
        # the subject. The ambiguity, if any, is still reported.
        for ec, (typed, result) in distinct_ecs:
            name = result.candidate.name if result.candidate else ""
            others.append((typed, ec, name))

    # A point mutation typed right after the enzyme ("IDH1 R132H") is not
    # modelled: set aside and said, never a substrate candidate.
    mutations: List[str] = []
    if enzyme is not None:
        for first, last, typed_hit, _ in hits:
            k = last
            while k < len(tokens) and not tokens[k].used and _MUTATION.match(tokens[k].raw):
                mutations.append(tokens[k].raw)
                tokens[k].used = True
                k += 1
    # The isoform and assumed organism of the enzyme, from any window that
    # named it: "beta lactamase TEM-1" reads the enzyme from "beta
    # lactamase" and the isoform from "TEM-1".
    isoform: Optional[str] = None
    assumed: Optional[str] = None
    read_notes: List[str] = []
    if enzyme is not None:
        for _, _, _, result in sorted(hits, key=lambda hit: hit[0]):
            if result.ec != enzyme[1].ec:
                continue
            if result.isoform and isoform is None:
                isoform = result.isoform
            if result.organism and assumed is None:
                assumed = result.organism
            read_notes.extend(n for n in result.notes if n not in read_notes and not n.startswith(_ASSUMED))
        if mutations:
            from .policy import mutation_note

            read_notes.append(mutation_note(enzyme[0], mutations))

    unread_organism = _misspelt_organism(tokens) if not organisms and (hits or ambiguity) else None
    if unread_organism is None and not organisms and (hits or ambiguity):
        unread_organism = _unread_source(tokens, text)
    inhibitor_span = _read_inhibitor(tokens)
    inhibitor_text = None
    if inhibitor_span is not None:
        inhibitor_text = text[tokens[inhibitor_span[0]].start:tokens[inhibitor_span[1] - 1].end]
        for k in range(*inhibitor_span):
            tokens[k].used = True

    candidates: List[str] = []

    def add(span: Optional[Tuple[int, int]]) -> None:
        if span is None:
            return
        # A candidate is a whole run of non-filler words, never one word
        # taken out of a longer run. Each kept word used to be tried on its
        # own after the phrase, so "glucose 6-phosphate", "2 deoxy glucose"
        # and "glucose analogues" matched nothing whole and then 'glucose'
        # matched D-glucose: the report carried D-glucose's Km 6.0 mM (ref
        # 641068) as the answer for a different compound, and "fructose
        # 1,6-bisphosphate" and "N-acetyl glucosamine" got D-fructose's and
        # D-glucosamine's. A filler word ("kinetics", "rate") does separate
        # runs, because it describes the request, not the compound: "glucose
        # kinetics" is "glucose". A run that matches nothing whole takes no
        # substrate, and the refusal that lists BRENDA's substrates runs.
        run: List[_Token] = []
        for w in list(tokens[span[0]:span[1]]) + [None]:
            if w is not None and w.low not in FILLER:
                run.append(w)
                continue
            if run and not all(_is_tag(t.raw) or t.low in SOURCE_TISSUES for t in run):
                phrase = text[run[0].start:run[-1].end]
                if phrase not in candidates:
                    candidates.append(phrase)
            run = []

    possible_inhibitor: Optional[str] = None
    for i, token in enumerate(tokens):
        if token.low in _INTRODUCERS and not token.used:
            span = _phrase_after(tokens, i + 1)
            before = len(candidates)
            add(span)
            if token.low == "with" and possible_inhibitor is None and inhibitor_text is None \
                    and len(candidates) > before:
                possible_inhibitor = candidates[before]
        elif (token.low == "presence" and i + 2 < len(tokens) and tokens[i + 1].low == "of"
              and possible_inhibitor is None and inhibitor_text is None):
            span = _phrase_after(tokens, i + 2)
            if span is not None:
                phrase = text[tokens[span[0]].start:tokens[span[1] - 1].end]
                if not all(t.low in FILLER for t in tokens[span[0]:span[1]]):
                    possible_inhibitor = phrase
    i = 0
    while i < len(tokens):
        span = _phrase_after(tokens, i)
        if span is None:
            i += 1
            continue
        add(span)
        i = span[1]

    remainder = " ".join(t.raw for t in tokens if not t.used)
    if enzyme is not None:
        typed, result = enzyme
        return SentenceReading(
            text=text, enzyme_text=typed, ec=result.ec,
            enzyme_name=result.candidate.name if result.candidate else None,
            how=result.how, cautions=tuple(result.cautions),
            substrate_text=candidates[0] if candidates else None,
            substrate_candidates=tuple(candidates), inhibitor_text=inhibitor_text,
            organisms_named=tuple((t, b) for _, _, t, b in organisms) if len(distinct) > 1 else (),
            unread_organism=unread_organism, remainder=remainder,
            isoform=isoform, read_notes=tuple(read_notes), possible_inhibitor_text=possible_inhibitor,
            mutations=tuple(mutations),
            **_assumed_organism(read_organism, organism, assumed, organisms))
    return SentenceReading(possible_inhibitor_text=possible_inhibitor, near=near if ambiguity is None and not others else None,
        text=text, enzyme_text=ambiguity_text if ambiguity is not None else None,
        organism=read_organism[1] if read_organism else None,
        organism_text=read_organism[0] if read_organism else None,
        substrate_text=candidates[0] if candidates else None,
        substrate_candidates=tuple(candidates), inhibitor_text=inhibitor_text,
        ambiguity=ambiguity, other_enzymes=tuple(others) if ambiguity is None else (),
        organisms_named=tuple((t, b) for _, _, t, b in organisms) if len(distinct) > 1 else (),
        unread_organism=unread_organism, remainder=remainder)


# ---------------------------------------------------------------------------
# The substrate, against what BRENDA lists
# ---------------------------------------------------------------------------

#: Stereo and anomer prefixes set aside when the typed word is compared with
#: BRENDA's name: "glucose" against "D-glucose", "lactose" against
#: "beta-lactose". Only at the start, and only these.
_STEREO_PREFIX = re.compile(
    r"^(?:d|l|dl|alpha|beta|α|β|\(s\)|\(r\)|\(\+\)|\(-\)|\(±\)|meso)-", re.IGNORECASE)


def _without_stereo(name: str) -> str:
    previous = None
    while previous != name:
        previous, name = name, _STEREO_PREFIX.sub("", name.strip())
    return strict_key(name)


@dataclass(frozen=True)
class SubstrateMatch:
    """What `match_substrate` made of the candidates."""

    #: BRENDA's name for the substrate, when exactly one matched.
    name: Optional[str] = None
    #: The words of the description it was read from.
    typed: Optional[str] = None
    #: True when the match needed a stereo or anomer prefix set aside.
    prefix_set_aside: bool = False
    #: (typed, BRENDA name) for every match, when there was more than one.
    rivals: Tuple[Tuple[str, str], ...] = field(default_factory=tuple)
    #: The abbreviation that was expanded ("BAPNA"), when the match came
    #: through SUBSTRATE_ABBREVIATIONS; None otherwise.
    abbreviation: Optional[str] = None

    def note(self) -> Optional[str]:
        """A sentence for the expansion of an abbreviation, or None."""
        if self.name is None or self.abbreviation is None:
            return None
        return (f"Read {self.abbreviation!r} as {self.name}, the name BRENDA lists that compound under "
                "(the same molecule, written another way).")


def _expand(typed: str, listed: Sequence[str], counts: Dict[str, int]) -> Optional[str]:
    """BRENDA's name for an abbreviation typed, or None. See SUBSTRATE_ABBREVIATIONS."""
    groups = SUBSTRATE_ABBREVIATIONS.get(_substrate_key(typed))
    if not groups:
        return None
    by_key: Dict[str, List[str]] = {}
    for name in listed:
        by_key.setdefault(strict_key(name), []).append(name)
    for group in groups:
        found: List[str] = []
        for spelling in group:
            for name in by_key.get(strict_key(spelling), ()):
                if name not in found:
                    found.append(name)
        if found:
            # One compound, spelled several ways: the spelling with the most rows.
            return sorted(found, key=lambda n: (-counts.get(n, 0), found.index(n)))[0]
    return None


_LOCANT = ((re.compile(r"\b(?:p|para)\s?nitro"), "4 nitro"), (re.compile(r"\b(?:o|ortho)\s?nitro"), "2 nitro"),
           (re.compile(r"\b(?:m|meta)\s?nitro"), "3 nitro"), (re.compile(r"pyranoside\b"), "side"))


def _substrate_form(text: str) -> str:
    """A substrate name with the spellings of one compound made equal: the
    para/ortho/meta letter as its locant (p-nitrophenyl is 4-nitrophenyl)
    and a pyranoside as the glycoside BRENDA often writes (beta-D-
    glucopyranoside is beta-D-glucoside). Word breaks are kept: "2 deoxy
    glucose" is not "2-deoxyglucose" by this rule."""
    key = strict_key(text)
    for pattern, replacement in _LOCANT:
        key = pattern.sub(replacement, key)
    return " ".join(key.split())


def match_substrate(candidates: Sequence[str], listed: Sequence[str]) -> SubstrateMatch:
    """The one substrate BRENDA lists that the description's words name, or nothing.

    A candidate is accepted when it IS a name BRENDA lists, case and spacing
    aside; failing that, when exactly one listed name is the candidate with
    a D-/L-/alpha-/beta-/(S)-/(R)- prefix set aside ("glucose" is
    "D-glucose" for hexokinase, where BRENDA lists no other glucose). Two
    listed names that both fit ("alpha-D-glucose" and "beta-D-glucose" for
    "glucose") are a choice, and so are two candidates that each name a
    different substrate ("glucose and ATP"): either returns no name and the
    rivals, so the caller's refusal, which lists BRENDA's substrates, runs.

    A lab abbreviation ("BAPNA", "ONPG", "pNPP", "PEP", "ATCh", "G6P") is
    expanded to the names BRENDA lists the compound under
    (SUBSTRATE_ABBREVIATIONS) and accepted only as one of them; `listed`
    may be a mapping of name to row count, and then the spelling of that
    compound with the most rows is taken.
    """
    counts: Dict[str, int] = dict(listed) if isinstance(listed, dict) else {}
    listed = list(listed)
    by_key: Dict[str, List[str]] = {}
    stripped: Dict[str, List[str]] = {}
    for name in listed:
        by_key.setdefault(strict_key(name), []).append(name)
        stripped.setdefault(_without_stereo(name), []).append(name)
    found: List[Tuple[str, str, bool]] = []
    expanded: Dict[str, str] = {}
    for typed in candidates:
        key = strict_key(typed)
        if not key:
            continue
        if key not in by_key:
            name = _expand(typed, listed, counts)
            if name is not None:
                found.append((typed, name, False))
                expanded[name] = typed
                continue
        exact = by_key.get(key)
        if exact:
            if len(set(exact)) == 1:
                found.append((typed, exact[0], False))
            continue
        loose = sorted(set(stripped.get(_without_stereo(typed), [])))
        if len(loose) == 1:
            found.append((typed, loose[0], True))
        elif len(loose) > 1:
            found.extend((typed, name, True) for name in loose)
        else:
            # The same compound written the other way chemists write it:
            # "4-nitrophenyl beta-D-glucopyranoside" is BRENDA's
            # "4-nitrophenyl-beta-D-glucoside" for almond beta-glucosidase
            # (names-stream review, 2026-11-12: it matched nothing and
            # cellobiose was modelled instead). Taken only when ONE listed
            # name is it.
            form = _substrate_form(typed)
            same = sorted({name for name in listed if _substrate_form(name) == form})
            if len(same) == 1:
                found.append((typed, same[0], False))
    names = sorted({name for _, name, _ in found})
    if len(names) == 1:
        typed, name, prefix = next(f for f in found if f[1] == names[0])
        return SubstrateMatch(name=name, typed=typed, prefix_set_aside=prefix,
                              abbreviation=expanded.get(name) if expanded.get(name) == typed else None)
    return SubstrateMatch(rivals=tuple((t, n) for t, n, _ in found))


__all__ = [
    "CLASS_WORDS", "SUBSTRATE_ABBREVIATIONS", "SUBSTRATE_VERBS", "SentenceReading", "SubstrateMatch",
    "match_substrate", "read_sentence",
]
