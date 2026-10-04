"""The small allowlist the grounding check's proper-noun rule uses.

A capitalised word (or an enzyme-shaped one ending in -ase) in an assistant's
text must appear in the result it was written from, or be here. The list is
deliberately short and boring: ordinary English that starts sentences, the
names of Studio's own screens, and the glossary terms a first-year student
needs defined ("Michaelis-Menten", "Km"). It contains NO enzyme, compound,
organism, database or journal name: those must come from the result.

Everything is lower case; the checker lowercases before looking up.
"""
from __future__ import annotations

_COMMON = """
a about above across actually after again against all almost along already also although always am an and another any
anyone are around as ask asked at away back be because been before being below best better between both but by can
cannot careful certain check choose clear close come compare could current currently do does doing done down during each
either else enough even ever every example explain far few fewer first follow following for found from further get give
given go going good great had has have having he help her here hers high him his how however i if in inside instead into
is it its itself just keep key kind know large last later least less let like likely little look made make many may me
might more most much must my near need needs never new next no none nor not note nothing now of off often on once one
only onto or other others our out over own part per perhaps place please point possible put quite rather really result
results right same say see seem seems several shall she should show shown since so some something sometimes still such
sure take than that the their them then there these they thing things this those though through thus time to together too
toward under unless until up upon us use used using very want was way we well were what when where whether which while
who whole why will with within without would yes yet you your yours
also first second third fourth fifth last next then finally overall instead specifically
therefore meanwhile otherwise similarly typically usually generally mostly mainly simply mean means meaning
caterva studio compose constants bind rates analyze analyse history settings assistant engine
michaelis menten km ki kcat vmax kd ic50 lineweaver burk hill
enzyme enzymes substrate substrates inhibitor inhibitors product products reaction reactions rate rates constant
constants parameter parameters value values measured measurement measurements fitted fit computed compute chosen
placeholder placeholders cited citation citations literature source sources model models mechanism shape shapes
verdict concern concerns remedy simulation steady state states stable unstable equilibrium binding affinity
temperature concentration concentrations assay assays pH condition conditions organism organisms isoform isoforms
mutation mutant wild-type wildtype
ec number numbers reference references ref
zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen
nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred thousand million half twice
tier tiers step steps figure table section stage row rows item option rule line page chapter number candidate rank
base phase case increase decrease release because whose purchase lease please database erase chase phrase ease cease
crease appease tease lowercase uppercase showcase staircase suitcase decrease increases decreases released
"""

PLAIN_WORDS = frozenset(w for w in _COMMON.replace("\n", " ").split() if w)

#: Words ending in "ase" that are not enzymes.
NON_ENZYME_ASE = frozenset({
    "base", "bases", "phase", "phases", "case", "cases", "increase", "increases", "decrease", "decreases", "release",
    "releases", "because", "whose", "purchase", "lease", "please", "database", "databases", "erase", "chase", "phrase",
    "phrases", "ease", "cease", "crease", "appease", "tease", "lowercase", "uppercase", "showcase", "staircase",
    "suitcase", "disease", "diseases", "baseline", "baselines", "phased", "based", "released", "increased",
    "decreased", "erased", "ceased", "eased", "chased", "leased", "purchased", "pleased", "paraphrase", "praise",
    "raise", "arise", "noise", "cause", "pause", "clause", "house", "mouse", "course", "worse", "else", "false", "close",
    "loose", "choose", "those", "these", "whose", "verse", "reverse", "sparse", "rinse", "response", "tense",
})

#: Common organism names and what they stand for in a result.
ORGANISM_SYNONYMS = {
    "human": ("homo sapiens",),
    "humans": ("homo sapiens",),
    "mouse": ("mus musculus",),
    "rat": ("rattus",),
    "yeast": ("saccharomyces",),
    "bovine": ("bos taurus",),
    "e. coli": ("escherichia coli",),
    "e.coli": ("escherichia coli",),
    "bacterial": ("escherichia", "bacillus", "bacteria"),
}

__all__ = ["NON_ENZYME_ASE", "ORGANISM_SYNONYMS", "PLAIN_WORDS"]
