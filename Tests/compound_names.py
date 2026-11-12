"""One compound under the spellings BRENDA files it by.

BRENDA keeps each paper's own spelling of a compound, so one compound sits on
a page under several names, and both the chooser (`caterva.compose.defaults`,
which counts rows per compound) and the resolver (`brenda_client
.substrate_matches`, which decides which rows a search reaches) must treat
them as one. Until the third round of the real-values review they did not
agree: the chooser merged "2-nitrophenyl beta-D-galactopyranoside" with
"2-nitrophenyl-beta-D-galactopyranoside" and the search, asked for one
spelling, took only its rows -- passing over beta-galactosidase's one
wild-type pair stating both pH and temperature. Trypsin's Z-Gly-Pro-Arg-pNA
was three compounds (Z-, N-benzyloxycarbonyl-, N-carbobenzyloxy-), and
PTP1B's rows naming P18031 were under "4-nitrophenyl phosphate" while the
search asked for "p-nitrophenyl phosphate".

`identity_key` is the one key both use. It folds only what does not change
the molecule:

* case, whitespace, a counter-ion ("acetylthiocholine iodide") and hyphens
  (BRENDA writes "D-fructose 1,6-bisphosphate" and
  "D-fructose-1,6-bisphosphate");
* an o-/m-/p- locant written as a letter ("p-nitrophenyl phosphate" is
  "4-nitrophenyl phosphate"); "pNA" as "4-nitroanilide";
* the benzyloxycarbonyl group under its names (Z, Cbz, N-benzyloxycarbonyl,
  N-carbobenzyloxy, carbobenzoxy); an N-alpha locant on an acyl group
  ("Nalpha-benzoyl", "N-alpha-benzoyl", "N-benzoyl", "benzoyl");
* a few names of one molecule a reader types or a paper prints
  (`SYNONYMS`): GSSG and glutathione disulfide, phosphocreatine and creatine
  phosphate, L-Glu and L-glutamate, (S)-malate and L-malate.

Never folded: a stereo descriptor that is not a synonym of another (D- and
L-glucose are two molecules; DL-BAPNA, a racemate, is not L-BAPNA), and any
change of a locant number.
"""
from __future__ import annotations

import re

_COUNTER_ION = re.compile(
    r"\s+(?:iodide|chloride|bromide|perchlorate|hydrochloride|sulfate|"
    r"(?:mono|di|tri)?sodium salt|potassium salt|lithium salt)$",
    re.IGNORECASE,
)
#: A drug's salt form, written after its name: "brequinar sodium" is
#: brequinar (human DHODH's Ki rows are filed under the salt, third round's
#: review), "imatinib mesylate" imatinib. Only after a name of its own, and
#: only salt words that are never a compound by themselves in such a place.
_SALT_FORM = re.compile(
    r"(?<=\w)\s+(?:(?:mono|di|tri)?sodium|potassium|calcium|magnesium|mesylate|mesilate|"
    r"besylate|besilate|maleate|tosylate|hydrobromide|dihydrochloride|monohydrate|hydrate"
    r"|trihydrate)$",
    re.IGNORECASE,
)
_PRIMES = str.maketrans({"’": "'", "′": "'", "‘": "'", "α": "alpha", "β": "beta"})
#: An o-/m-/p- locant written as a letter, lower case only ("O-acetyl" is an
#: oxygen substituent).
_LETTER_LOCANT = re.compile(r"(?<![A-Za-z0-9])([pom])-(?=[a-z])")
_LOCANT_NUMBER = {"o": "2", "m": "3", "p": "4"}
#: The benzyloxycarbonyl protecting group, under each name papers use.
_Z_GROUP = re.compile(
    r"^(?:n-?(?:alpha)?-?)?(?:benzyloxycarbonyl|carbobenzyloxy|carbobenzoxy|cbz|z)-",
    re.IGNORECASE)
#: An N-alpha locant before an acyl group, written several ways.
_N_ALPHA_ACYL = re.compile(
    r"^n(?:-?alpha|\(alpha\))?-(?=(?:benzoyl|acetyl|succinyl|tosyl|glutaryl)-)", re.IGNORECASE)
#: "pNA" (4-nitroanilide) and "AMC" spelled as a word at the end.
_PNA = re.compile(r"(?:-|\s)(?:pna|p-nitroanilide|4-nitroanilide)$", re.IGNORECASE)

#: Names of one molecule, each mapped to one spelling (keys and values are
#: already `_folded`). Only names a reader would type or BRENDA prints for a
#: natural substrate; never a guess about a stereo form.
SYNONYMS = {
    "gssg": "glutathionedisulfide",
    "oxidizedglutathione": "glutathionedisulfide",
    "gsh": "glutathione",
    "reducedglutathione": "glutathione",
    "l-glu": "l-glutamate",
    "lglu": "l-glutamate",
    "l-glutamicacid": "l-glutamate",
    "creatinephosphate": "phosphocreatine",
    "n-phosphocreatine": "phosphocreatine",
    "(s)-malate": "l-malate",
    "s-malate": "l-malate",
    "(s)-lactate": "l-lactate",
    "s-lactate": "l-lactate",
    "(s)-dihydroorotate": "l-dihydroorotate",
    "s-dihydroorotate": "l-dihydroorotate",
    "pep": "phosphoenolpyruvate",
    "h2o2": "hydrogenperoxide",
    "co2": "carbondioxide",
    # A nucleotide by the name an enzyme's name uses: "adenylate kinase".
    "adenylate": "amp",
    "guanylate": "gmp",
    "cytidylate": "cmp",
    "uridylate": "ump",
    "thymidylate": "dtmp",
}


def _folded(name: str) -> str:
    text = _COUNTER_ION.sub("", " ".join((name or "").translate(_PRIMES).split()))
    text = _SALT_FORM.sub("", text)
    text = _LETTER_LOCANT.sub(lambda m: _LOCANT_NUMBER[m.group(1)] + "-", text)
    text = _PNA.sub("-4-nitroanilide", text)
    text = _Z_GROUP.sub("z-", text)
    text = _N_ALPHA_ACYL.sub("", text)
    return re.sub(r"\s+", "", text).casefold()


def identity_key(name: str) -> str:
    """The key every spelling of one compound shares (module docstring)."""
    folded = _folded(name)
    folded = SYNONYMS.get(folded, folded)
    return folded.replace("-", "")


def same_compound(a: str, b: str) -> bool:
    """Whether two names are spellings of one compound by `identity_key`."""
    return bool(a and b) and identity_key(a) == identity_key(b)
