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

* a peptide written in one-letter, three-letter or full residue names, the
  L- of each residue being the convention a code leaves unwritten:
  "Ac-DEVD-pNA", "acetyl-DEVD-4-nitroanilide" and
  "acetyl-L-Asp-L-Glu-L-Val-L-Asp-4-nitroanilide" are one compound (the
  fourth round's caspase-3 pair was under the last spelling, the search
  asked for the second), and so are "benzoyl-DL-Arg-p-nitroanilide" and
  "N-benzoyl-DL-arginine 4-nitroanilide" (human trypsin's BAPNA pair). A
  D- or DL- before a residue is kept; AMC, MCA and 7-amido-4-methylcoumarin
  are one leaving group. A one-letter run is read as residues only beside
  an acyl group or a leaving group, so "L-NMMA" and "L-NAME" are not
  peptides;
* a free amino acid by its three-letter code ("D-Ala" is D-alanine, "L-Orn"
  L-ornithine), stereo descriptor kept;
* an acid and its anion ("arachidonic acid" is arachidonate);
* drug and radical names a reader types for what a paper prints (`ALIASES`):
  L-NMMA and Ngamma-monomethyl-L-arginine, DFMO and
  alpha-difluoromethylornithine, galantamine and galanthamine, donepezil and
  its systematic name, adrenaline and epinephrine, O2.- and superoxide.

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
    r"^n(?:-?alpha|\(alpha\))?-(?=(?:benzoyl|acetyl|succinyl|tosyl|glutaryl|hippuryl)-)", re.IGNORECASE)
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
    # The stereo-unspecified name is the natural (S) form: human DHODH's
    # rows were counted as two substrates (fifth round, R5V1-28).
    "dihydroorotate": "l-dihydroorotate",
    "pep": "phosphoenolpyruvate",
    "h2o2": "hydrogenperoxide",
    "co2": "carbondioxide",
    # A nucleotide by the name an enzyme's name uses: "adenylate kinase".
    "adenylate": "amp",
    "guanylate": "gmp",
    "cytidylate": "cmp",
    "uridylate": "ump",
    "thymidylate": "dtmp",
    # Dihydroxyacetone is symmetric, so its 1- and 3-phosphate are one
    # molecule, which IUPAC calls glycerone phosphate (triose-phosphate
    # isomerase listed "dihydroxyacetone phosphate" and "dihydroxyacetone
    # 3-phosphate" as two substrates, fifth round of the review).
    "dihydroxyacetone3-phosphate": "dihydroxyacetonephosphate",
    "dihydroxyacetone1-phosphate": "dihydroxyacetonephosphate",
    "glyceronephosphate": "dihydroxyacetonephosphate",
    "dhap": "dihydroxyacetonephosphate",
}


#: Residues by three-letter code, with the names a paper writes them by
#: (free acid, residue "-yl" form). The code is the key inside a peptide; a
#: free amino acid keeps its full name (`_FREE_NAME`).
_RESIDUES = {
    "ala": ("alanine", "alanyl"), "arg": ("arginine", "arginyl"), "asn": ("asparagine", "asparaginyl"),
    "asp": ("aspartate", "aspartyl", "alpha-aspartyl", "aspartic acid"),
    "cys": ("cysteine", "cysteinyl"), "gln": ("glutamine", "glutaminyl"),
    "glu": ("glutamate", "glutamyl", "alpha-glutamyl", "glutamic acid"), "gly": ("glycine", "glycyl"),
    "his": ("histidine", "histidyl"), "ile": ("isoleucine", "isoleucyl"), "leu": ("leucine", "leucyl"),
    "lys": ("lysine", "lysyl"), "met": ("methionine", "methionyl"),
    "phe": ("phenylalanine", "phenylalanyl"), "pro": ("proline", "prolyl"), "ser": ("serine", "seryl"),
    "thr": ("threonine", "threonyl"), "trp": ("tryptophan", "tryptophyl", "tryptophanyl"),
    "tyr": ("tyrosine", "tyrosyl"), "val": ("valine", "valyl"), "orn": ("ornithine", "ornithyl"),
    "nle": ("norleucine", "norleucyl"), "nva": ("norvaline", "norvalyl"), "cit": ("citrulline", "citrullyl"),
}
_RESIDUE_OF = {code: code for code in _RESIDUES}
_RESIDUE_OF.update({n.replace(" ", "-"): code for code, names in _RESIDUES.items() for n in names})
_FREE_NAME = {code: names[0] for code, names in _RESIDUES.items()}
_ONE_LETTER = {"A": "ala", "R": "arg", "N": "asn", "D": "asp", "C": "cys", "Q": "gln", "E": "glu",
               "G": "gly", "H": "his", "I": "ile", "L": "leu", "K": "lys", "M": "met", "F": "phe",
               "P": "pro", "S": "ser", "T": "thr", "W": "trp", "Y": "tyr", "V": "val"}
_ONE_LETTER_RUN = re.compile(r"[ACDEFGHIKLMNPQRSTVWY]{2,8}")
#: An acyl group on a peptide's N-terminus, by abbreviation and name.
_ACYL = {"ac": "acetyl", "acetyl": "acetyl", "suc": "succinyl", "succinyl": "succinyl",
         "bz": "benzoyl", "benzoyl": "benzoyl", "glt": "glutaryl", "glutaryl": "glutaryl",
         "tos": "tosyl", "tosyl": "tosyl", "z": "z", "boc": "boc", "meosuc": "methoxysuccinyl",
         # Hippuryl (benzoylglycyl): "hippuryl-L-Phe" and
         # "hippuryl-L-phenylalanine" are one carboxypeptidase A substrate,
         # listed apart with split row counts (fifth round's review).
         "hippuryl": "hippuryl", "hip": "hippuryl",
         "methoxysuccinyl": "methoxysuccinyl", "abz": "abz", "dabcyl": "dabcyl", "fmoc": "fmoc"}
#: A leaving group or C-terminal group on a peptide substrate.
_TERMINAL = {"pna", "amc", "nh2", "ome", "oet", "sbzl", "ester", "amide", "afc", "betana"}
_AMC = re.compile(
    r"(?:-|\s)(?:7-amido-4-methylcoumarin|7-amino-4-methylcoumarin|4-methylcoumaryl-7-amide"
    r"|4-methyl-coumaryl-7-amide|4-methylcoumarin-7-amide|methylcoumarylamide|amc|mca)$",
    re.IGNORECASE)
_STEREO_TOKEN = {"l": "", "d": "d", "dl": "dl"}


def _peptide(text: str) -> str:
    """A peptide (or acyl amino acid) written with its residues as codes and
    the L- of each left unwritten; any other name unchanged (module
    docstring). `text` has its case: a one-letter run is upper case."""
    body = _AMC.sub("-amc", text)
    body = re.sub(r"-4-nitroanilide$", "-pna", body)
    tokens = [t for t in re.split(r"[-\s]+", body) if t]
    if len(tokens) > 2 and tokens[0] == "H" and (tokens[1].casefold() in _RESIDUE_OF
                                                 or tokens[1].casefold() in _STEREO_TOKEN):
        tokens = tokens[1:]  # "H-D-Phe-..." writes the free amine
    if len(tokens) < 2:
        return text
    acyl = any(t.casefold() in _ACYL for t in tokens[:2])
    terminal = tokens[-1].casefold() in _TERMINAL or (
        len(tokens) >= 2 and tokens[-2].casefold() in ("ethyl", "methyl") and tokens[-1].casefold() == "ester")
    # A one-letter run needs an acyl group or a leaving group beside it:
    # "NG-nitro-L-arginine methyl ester" is no Asn-Gly peptide.
    leaving = tokens[-1].casefold() in ("pna", "amc", "afc", "betana", "sbzl")
    out: list = []
    residues = 0
    i = 0
    while i < len(tokens):
        tok, low = tokens[i], tokens[i].casefold()
        nxt = tokens[i + 1].casefold() if i + 1 < len(tokens) else ""
        if low in _STEREO_TOKEN and nxt in _RESIDUE_OF:
            if _STEREO_TOKEN[low]:
                out.append(_STEREO_TOKEN[low])
            i += 1
            continue
        if low in _RESIDUE_OF:
            out.append(_RESIDUE_OF[low])
            residues += 1
        elif (acyl or leaving) and _ONE_LETTER_RUN.fullmatch(tok):
            out.extend(_ONE_LETTER[ch] for ch in tok)
            residues += len(tok)
        elif low in _ACYL and i < 2:
            out.append(_ACYL[low])
        else:
            out.append(tok)
        i += 1
    if residues >= 2 or (residues >= 1 and (acyl or terminal)):
        return "-".join(out)
    return text


def _free_amino_acid(text: str) -> str:
    """"D-Ala" as D-alanine: a free amino acid by its code, stereo kept."""
    match = re.fullmatch(r"((?:[DL]{1,2}|\([RS]\))-)?([A-Za-z]{3})", text)
    if match and match.group(2).casefold() in _FREE_NAME:
        return (match.group(1) or "") + _FREE_NAME[match.group(2).casefold()]
    return text


#: An acid and its anion are one compound to a kinetic table.
_ACID = re.compile(r"^(.*[a-z])ic-?acid$")
#: Whole-word renamings inside a key: one molecule's two trivial names.
_RENAMED = ((re.compile(r"(nor)?adrenaline"), r"\1epinephrine"),
            (re.compile(r"galanthamine"), "galantamine"),
            # A 2-oxo acid by its older names: "2-ketobutyrate",
            # "alpha-ketobutyrate" and "2-oxobutanoate" are one molecule
            # (pyruvate decarboxylase listed "2-Ketobutyrate" and
            # "2-ketobutanoic acid" apart, fifth round's review). The keto
            # group of a locant-numbered or alpha-keto acid is the oxo group;
            # the trivial acid names propionate and butyrate are the
            # propanoate and butanoate of the systematic ones.
            (re.compile(r"^(?:alpha|α)-keto"), "2-oxo"),
            (re.compile(r"(?<=\d)-keto"), "-oxo"),
            (re.compile(r"(?<![a-z])butyrate$"), "butanoate"),
            (re.compile(r"(?<=oxo)butyrate$"), "butanoate"),
            (re.compile(r"(?<![a-z])propionate$"), "propanoate"),
            (re.compile(r"(?<=oxo)propionate$"), "propanoate"),
            (re.compile(r"(?<![a-z])valerate$"), "pentanoate"),
            (re.compile(r"(?<=oxo)valerate$"), "pentanoate"),
            # A pyranoside by its shorter name: E. coli beta-galactosidase's
            # ONPG rows are filed as "2-nitrophenyl beta-D-galactopyranoside"
            # and as "o-nitrophenyl-beta-D-galactoside", and the organism
            # chooser counted them apart (fifth round, XS5-02).
            (re.compile(r"(?<=-d-)(galacto|gluco|manno|xylo|fuco)side$"), r"\1pyranoside"))


def _base(name: str) -> str:
    text = _COUNTER_ION.sub("", " ".join((name or "").translate(_PRIMES).split()))
    text = _SALT_FORM.sub("", text)
    text = _LETTER_LOCANT.sub(lambda m: _LOCANT_NUMBER[m.group(1)] + "-", text)
    text = _PNA.sub("-4-nitroanilide", text)
    text = _Z_GROUP.sub("z-", text)
    return _N_ALPHA_ACYL.sub("", text)


def _folded(name: str) -> str:
    text = _base(name)
    plain = re.sub(r"\s+", "", text).casefold()
    if plain in SYNONYMS or plain.replace("-", "") in _ALIAS_KEYS:
        return plain
    text = _free_amino_acid(_peptide(text))
    key = re.sub(r"\s+", "", text).casefold()
    key = _ACID.sub(r"\1ate", key)
    for pattern, replacement in _RENAMED:
        key = pattern.sub(replacement, key)
    return key


#: Names a reader types for a compound a paper prints otherwise: (name,
#: the name it is). Keyed by `_base` with hyphens removed (`_ALIAS_KEYS`).
ALIASES = (
    ("L-NMMA", "NG-monomethyl-L-arginine"), ("NMMA", "NG-monomethyl-L-arginine"),
    ("Ngamma-monomethyl-L-arginine", "NG-monomethyl-L-arginine"),
    ("N(G)-monomethyl-L-arginine", "NG-monomethyl-L-arginine"),
    ("Nomega-monomethyl-L-arginine", "NG-monomethyl-L-arginine"),
    ("N-omega-monomethyl-L-arginine", "NG-monomethyl-L-arginine"),
    ("NG-methyl-L-arginine", "NG-monomethyl-L-arginine"),
    ("Ngamma-methyl-L-arginine", "NG-monomethyl-L-arginine"),
    ("Nomega-methyl-L-arginine", "NG-monomethyl-L-arginine"),
    ("L-NAME", "NG-nitro-L-arginine methyl ester"),
    ("Nomega-nitro-L-arginine methyl ester", "NG-nitro-L-arginine methyl ester"),
    ("Ngamma-nitro-L-arginine methyl ester", "NG-nitro-L-arginine methyl ester"),
    ("N(G)-nitro-L-arginine methyl ester", "NG-nitro-L-arginine methyl ester"),
    ("L-NNA", "NG-nitro-L-arginine"), ("L-NOARG", "NG-nitro-L-arginine"),
    ("Nomega-nitro-L-arginine", "NG-nitro-L-arginine"), ("Ngamma-nitro-L-arginine", "NG-nitro-L-arginine"),
    ("DFMO", "alpha-difluoromethylornithine"), ("eflornithine", "alpha-difluoromethylornithine"),
    ("DL-alpha-difluoromethylornithine", "alpha-difluoromethylornithine"),
    ("alpha-DL-difluoromethylornithine", "alpha-difluoromethylornithine"),
    ("difluoromethylornithine", "alpha-difluoromethylornithine"),
    ("2-difluoromethylornithine", "alpha-difluoromethylornithine"),
    ("DL-2-difluoromethylornithine", "alpha-difluoromethylornithine"),
    ("alpha-difluoromethyl-DL-ornithine", "alpha-difluoromethylornithine"),
    ("galanthamine", "galantamine"),
    ("E2020", "donepezil"),
    ("(R,S)-1-benzyl-4-[(5,6-dimethoxy-1-indanon)-2-yl]methylpiperidine", "donepezil"),
    ("1-benzyl-4-[(5,6-dimethoxy-1-indanon)-2-yl]methylpiperidine", "donepezil"),
    ("1-benzyl-4-[(5,6-dimethoxy-1-oxoindan-2-yl)methyl]piperidine", "donepezil"),
    ("O2-", "superoxide"), ("O2.-", "superoxide"), ("O2•-", "superoxide"), ("O2·-", "superoxide"),
    ("superoxide anion", "superoxide"), ("superoxide radical", "superoxide"),
    ("superoxide anion radical", "superoxide"), ("superoxide radical anion", "superoxide"),
    # One amine, four spellings: MAO-B's tally split "2-Phenylethylamine"
    # (3 Km, 1 kcat) from "Phenylethylamine" (2 Km, 1 kcat), and kynuramine
    # was called the best measured (sixth round, VR2-03).
    ("phenylethylamine", "2-phenylethylamine"), ("beta-phenylethylamine", "2-phenylethylamine"),
    ("β-phenylethylamine", "2-phenylethylamine"), ("phenethylamine", "2-phenylethylamine"),
    ("2-phenethylamine", "2-phenylethylamine"), ("beta-phenethylamine", "2-phenylethylamine"),
    # 6-phosphogluconate dehydrogenase's substrate under three names: sheep
    # 6PGD's 14 Km rows were split between two of them and lost to a
    # phosphonate analogue (sixth round, NEW-12).
    ("6-phospho-D-gluconate", "6-phosphogluconate"), ("D-gluconate 6-phosphate", "6-phosphogluconate"),
    ("6-phospho-D-gluconic acid", "6-phosphogluconate"), ("6-phosphogluconic acid", "6-phosphogluconate"),
    ("gluconate 6-phosphate", "6-phosphogluconate"), ("D-gluconate-6-phosphate", "6-phosphogluconate"),
    # RNase A's classic substrate under five spellings: bovine RNase A was
    # modelled on ref 682742's "cyclic 2',3'-cytidine monophosphate" (1 Km,
    # 0.0023 mM) as if it were another compound than the 5 wild-type
    # "cytidine-2',3'-cyclic monophosphate" rows at 0.45-0.62 mM (sixth
    # round, NEW-13).
    ("cyclic 2',3'-CMP", "cytidine 2',3'-cyclic monophosphate"),
    ("cyclic 2',3'-cytidine monophosphate", "cytidine 2',3'-cyclic monophosphate"),
    ("cytidine-2',3'-cyclic monophosphate", "cytidine 2',3'-cyclic monophosphate"),
    ("cytidine 2',3'-cyclic phosphate", "cytidine 2',3'-cyclic monophosphate"),
    ("cytidine 2',3'-phosphate", "cytidine 2',3'-cyclic monophosphate"),
    ("2',3'-cCMP", "cytidine 2',3'-cyclic monophosphate"),
    ("2',3'-cyclic CMP", "cytidine 2',3'-cyclic monophosphate"),
    ("HMG-CoA", "3-hydroxy-3-methylglutaryl-CoA"),
    ("hydroxymethylglutaryl-CoA", "3-hydroxy-3-methylglutaryl-CoA"),
    ("3-hydroxy-3-methylglutaryl-coenzyme A", "3-hydroxy-3-methylglutaryl-CoA"),
    # Drugs BRENDA files under a development code or a full chemical name
    # (fifth round, R5V1-03, R5V1-08, R5V1-09, R5V1-30): each was a
    # placeholder Ki though BRENDA holds the row under the other name.
    ("sitagliptin", "MK-0431"), ("sitagliptin phosphate", "MK-0431"),
    ("vildagliptin", "LAF237"), ("LAF-237", "LAF237"),
    ("saxagliptin", "BMS-477118"),
    ("SAHA", "suberoylanilide hydroxamic acid"), ("vorinostat", "suberoylanilide hydroxamic acid"),
    ("teriflunomide", "2-hydroxyethylidene-cyanoacetic acid 4-trifluoromethyl anilide"),
    ("A77 1726", "2-hydroxyethylidene-cyanoacetic acid 4-trifluoromethyl anilide"),
    ("A771726", "2-hydroxyethylidene-cyanoacetic acid 4-trifluoromethyl anilide"),
    ("A77-1726", "2-hydroxyethylidene-cyanoacetic acid 4-trifluoromethyl anilide"),
    ("sivelestat", "ONO-5046"),
    ("ONPG", "2-nitrophenyl beta-D-galactopyranoside"),
    # The lipid by its usual abbreviation (PTEN with PIP3, R5V1-15).
    ("PIP3", "phosphatidylinositol 3,4,5-trisphosphate"),
    ("PtdIns(3,4,5)P3", "phosphatidylinositol 3,4,5-trisphosphate"),
    ("PI(3,4,5)P3", "phosphatidylinositol 3,4,5-trisphosphate"),
    # Drugs by their INN or development code, filed by BRENDA under a
    # research name or a full chemical name (sixth round of the real-values
    # review): each Ki was a placeholder, and the placeholder listed the
    # same compound under its other name as "another inhibitor".
    # Forodesine is immucillin-H (BCX-1777); ulodesine is DADMe-immucillin-H
    # (BCX4208). Both bind purine nucleoside phosphorylase slowly and tightly.
    ("forodesine", "immucillin-H"), ("BCX-1777", "immucillin-H"), ("BCX1777", "immucillin-H"),
    ("ImmH", "immucillin-H"), ("Imm-H", "immucillin-H"),
    ("ulodesine", "DADMe-immucillin-H"), ("BCX4208", "DADMe-immucillin-H"),
    ("BCX-4208", "DADMe-immucillin-H"),
    # The arginase inhibitors by their usual abbreviations; BRENDA writes
    # the omega nitrogen "Nomega-" (human arginase's 51 nM row, ref 654612).
    ("nor-NOHA", "Nomega-hydroxy-nor-L-arginine"), ("norNOHA", "Nomega-hydroxy-nor-L-arginine"),
    ("N-omega-hydroxy-nor-L-arginine", "Nomega-hydroxy-nor-L-arginine"),
    ("Nomega-hydroxy-nor-arginine", "Nomega-hydroxy-nor-L-arginine"),
    ("N(omega)-hydroxy-nor-L-arginine", "Nomega-hydroxy-nor-L-arginine"),
    ("NOHA", "Nomega-hydroxy-L-arginine"), ("L-NOHA", "Nomega-hydroxy-L-arginine"),
    ("N-omega-hydroxy-L-arginine", "Nomega-hydroxy-L-arginine"),
    ("N(omega)-hydroxy-L-arginine", "Nomega-hydroxy-L-arginine"),
    ("NG-hydroxy-L-arginine", "Nomega-hydroxy-L-arginine"),
    # Terbinafine under its systematic name, as squalene epoxidase's rat
    # and Candida rows file it (EC 1.14.14.17, ref 438202; the counter-ion
    # "hydrochloride" is set aside by the key).
    ("terbinafine", "(E)-N-(6,6-dimethylhept-2-en-4-ynyl)-N-methyl-1-naphthalenemethaneamine"),
    ("Lamisil", "(E)-N-(6,6-dimethylhept-2-en-4-ynyl)-N-methyl-1-naphthalenemethaneamine"),
    ("SF 86-327", "(E)-N-(6,6-dimethylhept-2-en-4-ynyl)-N-methyl-1-naphthalenemethaneamine"),
    ("(E)-N-(6,6-dimethyl-2-hepten-4-ynyl)-N-methyl-1-naphthalenemethanamine",
     "(E)-N-(6,6-dimethylhept-2-en-4-ynyl)-N-methyl-1-naphthalenemethaneamine"),
    ("(E)-N-(6,6-dimethylhept-2-en-4-ynyl)-N-methyl-1-naphthalenemethanamine",
     "(E)-N-(6,6-dimethylhept-2-en-4-ynyl)-N-methyl-1-naphthalenemethaneamine"),
    ("BAPNA", "N-benzoyl-DL-arginine 4-nitroanilide"),
    ("DL-BAPNA", "N-benzoyl-DL-arginine 4-nitroanilide"),
    ("L-BAPNA", "N-benzoyl-L-arginine 4-nitroanilide"),
) + tuple(
    # A deoxynucleotide by its abbreviation, its "-ylate" name and its full
    # name: E. coli thymidylate synthase filed one K48Q mutant's Km under
    # "dUMP" and every wild-type row (0.0011-0.004 mM) under
    # "2'-deoxyuridylate", and the substrate chooser, counting them apart,
    # carried the mutant's 0.05 mM (fifth round of the real-values review).
    (spelling.format(n=nucleoside, y=ylate), abbreviation)
    for abbreviation, nucleoside, ylate in (
        ("dUMP", "uridine", "uridylate"), ("dTMP", "thymidine", "thymidylate"),
        ("dAMP", "adenosine", "adenylate"), ("dGMP", "guanosine", "guanylate"),
        ("dCMP", "cytidine", "cytidylate"))
    for spelling in ("2'-deoxy{y}", "deoxy{y}", "2'-deoxy{n} 5'-monophosphate",
                     "2'-deoxy{n} 5'-phosphate", "2'-deoxy{n} monophosphate",
                     "deoxy{n} monophosphate", "deoxy{n} 5'-monophosphate",
                     "2'-deoxy{n}-5'-monophosphate", "2'-deoxy{n}-5'-phosphate")
)


def _alias_key(name: str) -> str:
    return re.sub(r"\s+", "", _base(name)).casefold().replace("-", "")


_ALIAS_KEYS = {_alias_key(a): b for a, b in ALIASES}


def identity_key(name: str) -> str:
    """The key every spelling of one compound shares (module docstring)."""
    alias = _ALIAS_KEYS.get(_alias_key(name))
    if alias is not None:
        name = alias
    folded = _folded(name)
    folded = SYNONYMS.get(folded, folded)
    return folded.replace("-", "")


def same_compound(a: str, b: str) -> bool:
    """Whether two names are spellings of one compound by `identity_key`."""
    return bool(a and b) and identity_key(a) == identity_key(b)
