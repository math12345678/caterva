"""What can be proved about a model while every rate constant is still a placeholder.

WHY THIS MODULE IS THE ONE THAT FITS TERRIUM
--------------------------------------------
Every other module in `compose/` needs numbers. `analysis.py` finds steady
states by root-finding on rate laws whose constants must be filled in.
`sensitivity.py` differentiates through them. `bifurcation.py` sweeps them.
All three answer "what does this model do at these values", and when the
values are the motif library's illustrative placeholders the honest report
is that the answer is about the placeholders.

Chemical Reaction Network Theory answers a different question. Given only
the SHAPE of a network -- which complexes react to which -- it decides
things that hold for EVERY choice of positive rate constants. A model whose
twelve constants are all unmeasured is exactly as amenable to this as one
parameterised from BRENDA, because the theorems never look at a constant.

That is the whole reason this file exists. Terrium spends most of its effort
refusing to state numbers it cannot source. Here is a class of real, strong,
publishable statements it can make anyway.

WHAT A COMPLEX IS, AND WHY CANONICALISING IT IS THE WHOLE GAME
--------------------------------------------------------------
A complex is the multiset of species on one side of an arrow: the `A + B` in
`A + B -> AB` is one node of the reaction graph, and the `AB` is another.
Not the species -- the multiset. `A + B` and `B + A` are one node.
`2 A` and `A + B` are two. `A` and `2 A` are two.

Everything downstream is counting: n complexes, l connected components,
s = rank of the span of the reaction vectors, and the deficiency

    delta = n - l - s

Miscanonicalise a complex and n is wrong, so delta is wrong, so a theorem
gets applied to a network it does not cover -- silently, with a confident
verdict attached. The canonical form here is a sorted tuple of
(species, coefficient) pairs with zero coefficients dropped, which makes the
multiset identity structural rather than a convention every call site has to
remember.

THE DEFICIENCY IS COMPUTED EXACTLY, OVER Fraction
--------------------------------------------------
`s` is the rank of a matrix of integers, and the deficiency is a difference
of three integers. Deciding it in floating point would make an integer fact
depend on a tolerance. `Terium/core/network.py` already refuses that for
conservation laws -- its left null space is Gauss-Jordan over `Fraction` --
and `exact_rank` here follows the same discipline, so the two exact
computations agree by construction: for a network with no rate rules,

    stoichiometric_rank(network) + len(network.conservation_laws())
        == len(network.species)

which is the rank-nullity theorem and is asserted in the tests.

THE HYPOTHESIS THIS MODULE CANNOT VERIFY FROM STRUCTURE, AND SO REFUSES ON
--------------------------------------------------------------------------
The deficiency theorems are about MASS-ACTION kinetics. Most of the motifs
in `library.py` are not mass action: `catalytic_step` writes

    kcat * E * S / (Km + S)

which is a Michaelis-Menten law, and `hill_repression` writes a Hill
function. The deficiency theorems say NOTHING about either.

This is the failure mode the module is built around. A structural "proof" of
uniqueness and stability, attached to a model the theorem does not cover,
would be the worst output this codebase could produce: it carries all the
authority of a theorem and none of its content, and unlike a wrong number it
does not look wrong. So `classify_kinetics` decides, per reaction, whether
the rate law IS a positive constant times the product of its reactant
species raised to their stoichiometric coefficients -- and the verdict
functions raise `KineticsNotMassAction` unless every reaction is. The
classifier proves mass action or refuses; it never assumes it. Anything it
cannot parse, anything with a sum in a denominator, anything raised to a
non-integer power, anything mentioning `time`, and anything whose species
powers differ from its own stoichiometry comes back not-mass-action with the
reason.

Two consequences worth stating plainly, because both look like bugs:

**A catalyst outside the arrow makes a reaction not mass action.** Terrium
writes enzymatic steps as `S -> P` with `E` a modifier of the rate law. As a
reaction network that reaction's reactant complex is `S`, so mass action
would make its rate depend on `S` alone. To be visible to these theorems the
enzyme has to be in the complexes -- `E + S -> ES -> E + P` -- which is a
different model, not a different notation.

**Refusal is per network, not per reaction.** One Michaelis-Menten step in
an otherwise mass-action network refuses the whole verdict. The theorems are
statements about the system of ODEs, and a system with one non-mass-action
term is not a mass-action system.

WHAT IS NOT CLAIMED HERE
------------------------
`deficiency()`, `complexes()`, `linkage_classes()` and
`is_weakly_reversible()` are facts about the REACTIONS. A network with rate
rules has species evolving outside the reaction stoichiometry entirely;
those functions still describe its reaction graph, which is a true and
narrower thing than describing its dynamics, and the verdict functions
refuse on such a network rather than pretending otherwise.

Neither theorem says the model is right. A wrong mechanism with deficiency
zero has exactly the same uniqueness and stability as a right one. These
verdicts constrain what the equations can do; they say nothing about whether
the equations are the biology.

And neither theorem says anything about WHERE the steady state is. That
depends on the rate constants, which is the question this module cannot
answer and `sensitivity.py` can only answer at the values it is given.

REFERENCES
----------
Horn, F. and Jackson, R. "General mass action kinetics." Archive for
Rational Mechanics and Analysis, 1972.

Feinberg, M. "Complex balancing in general kinetic systems." Archive for
Rational Mechanics and Analysis, 1972.

Feinberg, M. "Chemical reaction network structure and the stability of
complex isothermal reactors -- I. The deficiency zero and deficiency one
theorems." Chemical Engineering Science, 1987.

Feinberg, M. "The existence and uniqueness of steady states for a class of
chemical reaction networks." Archive for Rational Mechanics and Analysis,
1995.

Feinberg, M. "Foundations of Chemical Reaction Network Theory." Springer,
2019.

No numeric quantity in this module comes from any of those; there is no
numeric quantity in this module. Everything it reports is counted or derived
from the network it was handed.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Dict, List, Mapping, Sequence, Set, Tuple


class StructuralRefusal(RuntimeError):
    """A structural verdict was asked for and must not be given.

    Distinct from a verdict of "the theorem does not cover this network",
    which is a real answer and is returned rather than raised. This is the
    case where the question itself cannot be evaluated -- the kinetics are
    outside the theorem's scope, or the object handed in is not a reaction
    network at all.
    """


class KineticsNotMassAction(StructuralRefusal):
    """The rate laws are not mass action, so the deficiency theorems do not
    cover this model."""


class NotAReactionNetwork(StructuralRefusal):
    """The object handed in does not describe a reaction network whose
    structure these theorems are about."""


# ---------------------------------------------------------------------------
# Complexes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Complex:
    """A multiset of species: one node of the reaction graph.

    Stored as a tuple of (species, coefficient) pairs, sorted by species
    name, with zero coefficients dropped. That canonical form is what makes
    `A + B` and `B + A` the SAME node rather than two, which is not a
    cosmetic matter: n is a term in the deficiency, and an over-counted n
    turns a deficiency-zero network into a deficiency-one one and hands the
    reader a theorem that does not apply.

    The empty tuple is the zero complex, which is a real node and not a
    missing one: `-> X` (a constitutive source) reacts the zero complex to
    the complex X, and `synthesis_degradation` is weakly reversible
    precisely because `X -> ` reacts it back.
    """

    species: Tuple[Tuple[str, int], ...]

    @classmethod
    def of(cls, mapping: Mapping[str, int]) -> "Complex":
        entries: List[Tuple[str, int]] = []
        for name, coefficient in mapping.items():
            if isinstance(coefficient, bool) or not isinstance(coefficient, int):
                raise NotAReactionNetwork(
                    f"the stoichiometric coefficient of {name!r} is "
                    f"{coefficient!r}, which is not an integer. A complex is a "
                    f"multiset of species, and a multiset has whole-number "
                    f"multiplicities; there is no complex this describes."
                )
            if coefficient < 0:
                raise NotAReactionNetwork(
                    f"the stoichiometric coefficient of {name!r} is "
                    f"{coefficient}. Put the species on the other side of the "
                    f"arrow instead -- a negative multiplicity is not a "
                    f"complex."
                )
            if coefficient:
                entries.append((name, coefficient))
        return cls(tuple(sorted(entries)))

    @property
    def is_zero(self) -> bool:
        return not self.species

    @property
    def support(self) -> Tuple[str, ...]:
        """The species present, ignoring how many of each."""
        return tuple(name for name, _ in self.species)

    def coefficient(self, species: str) -> int:
        for name, count in self.species:
            if name == species:
                return count
        return 0

    def __str__(self) -> str:
        if self.is_zero:
            # Feinberg's notation for the complex with no species in it.
            return "0"
        return " + ".join(
            name if count == 1 else f"{count} {name}" for name, count in self.species
        )


def complexes(network: Any) -> Tuple[Complex, ...]:
    """The distinct complexes of the network, in order of first appearance.

    Ordered by when each is first seen -- reactant before product, reaction
    by reaction -- rather than sorted, so that two runs over the same
    network report the same graph and a reader can follow the numbering back
    to the model text.
    """
    seen: Dict[Complex, None] = {}
    for reaction in _reactions(network):
        for side in (reaction.reactants, reaction.products):
            seen.setdefault(Complex.of(side), None)
    return tuple(seen)


# ---------------------------------------------------------------------------
# The reaction graph
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReactionGraph:
    """Complexes as nodes, reactions as directed edges.

    Carried as a value because every structural question below is asked of
    the same graph, and rebuilding it per question would let two answers be
    computed from two different canonicalisations of the same network.
    """

    nodes: Tuple[Complex, ...]
    #: (from index, to index, reaction id)
    edges: Tuple[Tuple[int, int, str], ...]

    def index_of(self, node: Complex) -> int:
        return self.nodes.index(node)


def reaction_graph(network: Any) -> ReactionGraph:
    nodes = complexes(network)
    position = {node: i for i, node in enumerate(nodes)}
    edges: List[Tuple[int, int, str]] = []
    for reaction in _reactions(network):
        source = position[Complex.of(reaction.reactants)]
        target = position[Complex.of(reaction.products)]
        edges.append((source, target, reaction.id))
    return ReactionGraph(nodes=nodes, edges=tuple(edges))


def linkage_classes(network: Any) -> Tuple[Tuple[Complex, ...], ...]:
    """Connected components of the reaction graph, ignoring arrow direction.

    `l` in delta = n - l - s. Two complexes are in the same linkage class
    when some chain of reactions connects them, whichever way the arrows
    point -- so `A -> B` and `B -> A` give one linkage class, and so does
    `A -> B` alone.
    """
    graph = reaction_graph(network)
    parent = list(range(len(graph.nodes)))

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for source, target, _ in graph.edges:
        a, b = find(source), find(target)
        if a != b:
            parent[b] = a

    grouped: Dict[int, List[int]] = {}
    for index in range(len(graph.nodes)):
        grouped.setdefault(find(index), []).append(index)

    # Ordered by the earliest complex in each class, so the numbering is
    # stable across runs and follows the model text.
    ordered = sorted(grouped.values(), key=min)
    return tuple(tuple(graph.nodes[i] for i in members) for members in ordered)


def strong_linkage_classes(network: Any) -> Tuple[Tuple[Complex, ...], ...]:
    """Strongly connected components: complexes mutually reachable ALONG the
    arrows.

    The directed refinement of a linkage class. `A -> B -> A` is one strong
    linkage class; `A -> B` is two.
    """
    graph = reaction_graph(network)
    components = _strongly_connected(len(graph.nodes), graph.edges)
    return tuple(
        tuple(graph.nodes[i] for i in members) for members in components
    )


def terminal_strong_linkage_classes(
    network: Any,
) -> Tuple[Tuple[Complex, ...], ...]:
    """Strong linkage classes with no reaction leading out of them.

    Once the system's composition is "in" a terminal strong linkage class
    there is no reaction that leaves it. Counting them per linkage class is
    the first hypothesis of the Deficiency One Theorem, which is why they are
    exposed rather than being an implementation detail of the verdict.
    """
    graph = reaction_graph(network)
    components = _strongly_connected(len(graph.nodes), graph.edges)
    label = {}
    for number, members in enumerate(components):
        for member in members:
            label[member] = number

    leaves: Set[int] = set()
    for source, target, _ in graph.edges:
        if label[source] != label[target]:
            leaves.add(label[source])

    return tuple(
        tuple(graph.nodes[i] for i in members)
        for number, members in enumerate(components)
        if number not in leaves
    )


def is_weakly_reversible(network: Any) -> bool:
    """Whether every linkage class is strongly connected.

    Equivalently: whenever a chain of reactions leads from complex y to
    complex y', some chain leads back. This is what separates the two halves
    of the Deficiency Zero Theorem -- one half asserts a unique stable
    positive steady state, the other asserts that no positive steady state
    exists at all -- so a wrong answer here does not degrade the verdict, it
    inverts it.
    """
    graph = reaction_graph(network)
    if not graph.nodes:
        raise NotAReactionNetwork(
            "this network has no reactions, so it has no reaction graph and "
            "weak reversibility is not defined for it. Weak reversibility is "
            "a property of arrows; there are none."
        )
    components = _strongly_connected(len(graph.nodes), graph.edges)
    label = {}
    for number, members in enumerate(components):
        for member in members:
            label[member] = number

    for members in linkage_classes(network):
        labels = {label[graph.index_of(node)] for node in members}
        if len(labels) > 1:
            return False
    return True


def _strongly_connected(
    count: int, edges: Sequence[Tuple[int, int, str]]
) -> List[List[int]]:
    """Kosaraju's algorithm, iteratively.

    Iterative rather than recursive because a long linear pathway is a
    perfectly ordinary network and Python's recursion limit is not a fact
    about chemistry. Components come back sorted internally and ordered by
    their smallest member, so the output is deterministic.
    """
    forward: List[List[int]] = [[] for _ in range(count)]
    backward: List[List[int]] = [[] for _ in range(count)]
    for source, target, _ in edges:
        forward[source].append(target)
        backward[target].append(source)

    visited = [False] * count
    order: List[int] = []
    for start in range(count):
        if visited[start]:
            continue
        visited[start] = True
        stack = [(start, iter(forward[start]))]
        while stack:
            node, remaining = stack[-1]
            advanced = False
            for candidate in remaining:
                if not visited[candidate]:
                    visited[candidate] = True
                    stack.append((candidate, iter(forward[candidate])))
                    advanced = True
                    break
            if not advanced:
                order.append(node)
                stack.pop()

    component = [-1] * count
    components: List[List[int]] = []
    for node in reversed(order):
        if component[node] != -1:
            continue
        number = len(components)
        component[node] = number
        members = [node]
        stack = [node]
        while stack:
            current = stack.pop()
            for previous in backward[current]:
                if component[previous] == -1:
                    component[previous] = number
                    members.append(previous)
                    stack.append(previous)
        components.append(sorted(members))

    return sorted(components, key=min)


# ---------------------------------------------------------------------------
# The stoichiometric subspace, exactly
# ---------------------------------------------------------------------------


def reaction_vectors(network: Any) -> Tuple[Tuple[Fraction, ...], ...]:
    """`y' - y` for each reaction, in the network's declared species order.

    Over `Fraction`, so the rank taken from them is exact. The species order
    is the network's own rather than the order species happen to appear in
    reactions, which is what lets the rank be cross-checked against
    `ReactionNetwork.conservation_laws()` -- the two must satisfy
    rank + nullity = number of species, and a different ordering would make
    that comparison meaningless.
    """
    order = _species_ids(network)
    position = {name: i for i, name in enumerate(order)}

    vectors: List[Tuple[Fraction, ...]] = []
    for reaction in _reactions(network):
        row = [Fraction(0)] * len(order)
        for side, sign in ((reaction.reactants, -1), (reaction.products, +1)):
            for name, coefficient in Complex.of(side).species:
                if name not in position:
                    raise NotAReactionNetwork(
                        f"reaction {reaction.id!r} names {name!r}, which is "
                        f"not a declared species of this network. Call "
                        f"`network.validate()` -- the structure cannot be "
                        f"read off a model whose stoichiometry refers to "
                        f"something that does not exist."
                    )
                row[position[name]] += sign * Fraction(coefficient)
        vectors.append(tuple(row))
    return tuple(vectors)


def exact_rank(rows: Sequence[Sequence[Fraction]]) -> int:
    """Rank of a matrix over the rationals, by Gauss-Jordan on `Fraction`.

    The same discipline `Terium/core/network.py` uses for conservation laws,
    and for the same reason. The rank is a term in an integer identity --
    delta = n - l - s, and delta is always a non-negative integer -- so
    deciding it by "is this pivot smaller than 1e-12" makes an integer fact a
    fact about the tolerance. On the small integer matrices a reaction
    network produces, floating point would usually agree; "usually" is not
    the claim this project makes.

    Public because it is the part of the deficiency a reader is most likely
    to want to check independently, and because a helper that cannot be
    exercised on a matrix where floats give the wrong answer is a claim of
    exactness rather than a demonstration of one.
    """
    matrix = [[Fraction(value) for value in row] for row in rows]
    if not matrix:
        return 0
    width = len(matrix[0])
    for row in matrix:
        if len(row) != width:
            raise ValueError(
                f"the rows of this matrix are not the same length "
                f"({width} then {len(row)}); a rank is not defined for it"
            )

    rank = 0
    pivot_row = 0
    for column in range(width):
        target = None
        for candidate in range(pivot_row, len(matrix)):
            if matrix[candidate][column] != 0:
                target = candidate
                break
        if target is None:
            continue
        matrix[pivot_row], matrix[target] = matrix[target], matrix[pivot_row]
        lead = matrix[pivot_row][column]
        matrix[pivot_row] = [value / lead for value in matrix[pivot_row]]
        for other in range(len(matrix)):
            if other != pivot_row and matrix[other][column] != 0:
                factor = matrix[other][column]
                matrix[other] = [
                    a - factor * b
                    for a, b in zip(matrix[other], matrix[pivot_row])
                ]
        rank += 1
        pivot_row += 1
        if pivot_row == len(matrix):
            break
    return rank


def stoichiometric_rank(network: Any) -> int:
    """`s`: the dimension of the span of the reaction vectors.

    The stoichiometric subspace is the set of directions the composition can
    move in. Its dimension is what the deficiency measures the complexes
    against, and it is also -- by rank-nullity -- the number of species minus
    the number of independent conservation laws the network derives.
    """
    return exact_rank(reaction_vectors(network))


def deficiency(network: Any) -> int:
    """`delta = n - l - s`, exactly.

    n distinct complexes, l linkage classes, s the rank of the
    stoichiometric subspace. The deficiency is a non-negative integer for
    every reaction network -- that is a theorem, not an assumption -- so a
    negative result here would mean this module miscounted, and it says so
    rather than returning it.

    A fact about the REACTIONS. A network that also carries rate rules has
    species evolving outside this structure; the deficiency of its reaction
    graph is still what this returns, and the verdict functions refuse on
    such a network rather than reading dynamics into it.
    """
    n = len(complexes(network))
    if n == 0:
        raise NotAReactionNetwork(
            "this network has no reactions, so it has no complexes and no "
            "deficiency. Deficiency counts the complexes against the "
            "reaction vectors; with no reactions there is nothing to count."
        )
    l = len(linkage_classes(network))
    s = stoichiometric_rank(network)
    delta = n - l - s
    if delta < 0:
        raise NotAReactionNetwork(
            f"computed a deficiency of {delta} (n={n}, l={l}, s={s}). The "
            f"deficiency of a reaction network is a non-negative integer, so "
            f"this is a bug in this module rather than a property of your "
            f"model -- most likely two complexes that should be one node were "
            f"counted separately. Please report the network."
        )
    return delta


def linkage_class_deficiencies(network: Any) -> Tuple[int, ...]:
    """The deficiency of each linkage class, in `linkage_classes()` order.

    `delta_i = n_i - 1 - s_i`, where n_i counts the complexes in that class
    and s_i is the rank of the reaction vectors of the reactions inside it.
    The `1` is because a linkage class is by construction connected, so it
    has one linkage class of its own.

    These are what the Deficiency One Theorem's second and third hypotheses
    are about. Note that sum(delta_i) <= delta always; the theorem asks for
    equality, and inequality is a real and common answer.
    """
    graph = reaction_graph(network)
    classes = linkage_classes(network)
    membership: Dict[Complex, int] = {}
    for number, members in enumerate(classes):
        for member in members:
            membership[member] = number

    vectors = reaction_vectors(network)
    per_class: List[List[Tuple[Fraction, ...]]] = [[] for _ in classes]
    for (source, _target, _rid), vector in zip(graph.edges, vectors):
        per_class[membership[graph.nodes[source]]].append(vector)

    return tuple(
        len(members) - 1 - exact_rank(rows)
        for members, rows in zip(classes, per_class)
    )


# ---------------------------------------------------------------------------
# Is it mass action? The hypothesis structure cannot supply.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KineticsFinding:
    """Whether one reaction's rate law is mass action, and why not if not."""

    reaction_id: str
    mass_action: bool
    #: Empty when `mass_action`. Otherwise a sentence naming what in the rate
    #: law is outside mass action -- a reader has to be able to act on this,
    #: and "not mass action" on its own is not actionable.
    reason: str = ""
    #: Parameters that multiply into this reaction's rate constant. Reported
    #: so the positivity a theorem requires can be checked against the model
    #: the caller actually holds.
    rate_constants: Tuple[str, ...] = ()

    def describe(self) -> str:
        if self.mass_action:
            return (
                f"{self.reaction_id}: mass action"
                + (
                    f", rate constant {' * '.join(self.rate_constants)}"
                    if self.rate_constants
                    else " with a numeric rate constant"
                )
            )
        return f"{self.reaction_id}: NOT mass action -- {self.reason}"


class _NotAMonomial(Exception):
    """Internal: a rate law is not a constant times a product of powers."""


@dataclass(frozen=True)
class _Monomial:
    exponents: Mapping[str, int]
    parameters: Tuple[str, ...]


def classify_kinetics(network: Any) -> Tuple[KineticsFinding, ...]:
    """Per reaction: is the rate law mass action for THAT reaction?

    Mass action for a reaction with reactant complex y is

        rate = k * product over species i of (x_i ** y_i)

    with k a strictly positive constant. Two halves, and both are checked:
    the rate law must have that FORM, and the exponents must be that
    reaction's own stoichiometry. The second half is what catches the
    enzymatic motifs even before their denominators are looked at -- a
    Terrium catalytic step is the reaction `S -> P` with a rate law
    mentioning `E`, and mass action for `S -> P` cannot mention `E`.

    Errs toward refusing, deliberately and in every branch. The classifier
    either PROVES a rate law is mass action or reports that it could not, and
    "could not" covers unparseable laws, function calls, sums, negative
    literals, non-integer powers, `time`, division by anything containing a
    species, and any symbol that is neither a species nor a parameter of this
    network. The cost of a false "not mass action" is a refused verdict the
    reader can argue with. The cost of a false "mass action" is a theorem
    applied to a model it does not cover, which nobody would catch.
    """
    species = set(_species_ids(network))
    parameters = set(_parameter_ids(network))
    return tuple(
        _classify_one(reaction, species, parameters)
        for reaction in _reactions(network)
    )


def is_mass_action(network: Any) -> bool:
    """Whether every reaction was PROVED to be mass action.

    Not "whether any reaction was shown not to be": a network with a rate law
    this module cannot parse is not mass action as far as anything here is
    entitled to say, and the theorems are only available to networks it can
    vouch for entirely.
    """
    findings = classify_kinetics(network)
    return bool(findings) and all(finding.mass_action for finding in findings)


def _classify_one(
    reaction: Any, species: Set[str], parameters: Set[str]
) -> KineticsFinding:
    law = getattr(reaction, "rate_law", "") or ""
    # Antimony spells exponentiation `^`; Python's parser reads that as
    # bitwise xor, which would silently classify `k * A^2` as something it
    # is not. Translated before parsing rather than after, so no branch below
    # ever sees an operator it would have to guess about.
    text = law.replace("^", "**")

    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        return KineticsFinding(
            reaction.id,
            False,
            f"its rate law could not be parsed as an expression "
            f"({exc.msg}), so nothing can be proved about its form",
        )

    try:
        monomial = _monomial(tree.body, species, parameters)
    except _NotAMonomial as exc:
        return KineticsFinding(
            reaction.id,
            False,
            f"its rate law is not a positive constant times a product of "
            f"species powers: {exc}",
        )

    wanted = dict(Complex.of(reaction.reactants).species)
    got = {name: power for name, power in monomial.exponents.items() if power}
    if got != wanted:
        return KineticsFinding(
            reaction.id, False, _mismatch(reaction, wanted, got)
        )

    return KineticsFinding(
        reaction.id, True, "", tuple(monomial.parameters)
    )


def _mismatch(
    reaction: Any, wanted: Mapping[str, int], got: Mapping[str, int]
) -> str:
    """Why the species powers are not this reaction's stoichiometry.

    Written to be acted on. The commonest case by far in this codebase is an
    enzyme that appears in a rate law but not in the arrow, and a reader told
    only "the exponents do not match" would have to work out why that matters
    and what to do about it.
    """
    extra = sorted(set(got) - set(wanted))
    missing = sorted(set(wanted) - set(got))
    differing = sorted(
        name for name in set(got) & set(wanted) if got[name] != wanted[name]
    )

    complex_text = str(Complex.of(reaction.reactants))
    parts: List[str] = []
    if extra:
        parts.append(
            f"it depends on {', '.join(extra)}, which is not in its reactant "
            f"complex ({complex_text}). As a reaction network this reaction "
            f"is `{complex_text} -> "
            f"{Complex.of(reaction.products)}`, and mass action makes its "
            f"rate depend only on {complex_text or 'nothing'}. A catalyst has "
            f"to appear in the complexes -- `E + S -> E + P` -- before any "
            f"theorem here can see it"
        )
    if missing:
        parts.append(
            f"it does not depend on {', '.join(missing)}, which its reactant "
            f"complex ({complex_text}) contains"
        )
    for name in differing:
        parts.append(
            f"it raises {name} to the power {got[name]}, but the reactant "
            f"complex has {wanted[name]} of it"
        )
    return "; ".join(parts)


def _monomial(node: ast.AST, species: Set[str], parameters: Set[str]) -> _Monomial:
    """A rate law as (species exponents, parameter factors), or a refusal.

    Every branch that is not provably a constant-times-powers monomial
    raises, with the reason phrased for someone reading a refused verdict.
    """
    if isinstance(node, ast.Name):
        name = node.id
        if name in species:
            return _Monomial({name: 1}, ())
        if name in parameters:
            return _Monomial({}, (name,))
        if name == "time":
            raise _NotAMonomial(
                "it depends on `time`, so the system is not autonomous. The "
                "deficiency theorems are about autonomous mass-action "
                "systems and say nothing about a rate that is driven "
                "externally"
            )
        raise _NotAMonomial(
            f"it refers to {name!r}, which is neither a species nor a "
            f"parameter of this network"
        )

    if isinstance(node, ast.Constant):
        value = node.value
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise _NotAMonomial(
                f"it contains the literal {value!r}, which is not a number"
            )
        if value <= 0:
            raise _NotAMonomial(
                f"it contains the literal {value!r}. A mass-action rate "
                f"constant is strictly positive, and every conclusion these "
                f"theorems reach is quantified over positive rate constants"
            )
        return _Monomial({}, ())

    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.UAdd):
            return _monomial(node.operand, species, parameters)
        raise _NotAMonomial(
            "it negates a term. A mass-action rate is a positive constant "
            "times a product of concentrations, so it is never negative"
        )

    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Mult):
            left = _monomial(node.left, species, parameters)
            right = _monomial(node.right, species, parameters)
            merged: Dict[str, int] = dict(left.exponents)
            for name, power in right.exponents.items():
                merged[name] = merged.get(name, 0) + power
            return _Monomial(merged, left.parameters + right.parameters)

        if isinstance(node.op, ast.Div):
            left = _monomial(node.left, species, parameters)
            # A DENOMINATOR IS WHERE THE ENZYMOLOGY LIVES, so its refusal is
            # written for the reader who arrived here with a Michaelis-Menten
            # model. Without this branch the failure surfaces as whatever the
            # denominator's innermost node happened to be -- for
            # `kcat*E*S/(Km+S)` that is "it is a sum of terms", which is true
            # and tells nobody what is actually wrong with their model.
            try:
                right = _monomial(node.right, species, parameters)
            except _NotAMonomial as exc:
                raise _NotAMonomial(
                    f"it divides by an expression that could not be shown to "
                    f"be a positive constant ({exc}). A rate law with a "
                    f"species in its denominator SATURATES: Michaelis-Menten, "
                    f"`kcat*E*S/(Km+S)`, and every Hill law have exactly this "
                    f"shape. A mass-action rate does not saturate -- it stays "
                    f"proportional to a product of concentrations at every "
                    f"concentration -- so these theorems say nothing about it"
                ) from None
            if right.exponents:
                raise _NotAMonomial(
                    f"it divides by an expression containing "
                    f"{', '.join(sorted(right.exponents))}, so the rate is "
                    f"not proportional to a product of species powers. A "
                    f"saturating law -- Michaelis-Menten, Hill -- has exactly "
                    f"this shape, and the deficiency theorems do not cover it"
                )
            # k1 / k2 is a perfectly good positive rate constant, so this is
            # allowed rather than refused; both parameters are reported, and
            # the verdict's positivity caveat covers them.
            return _Monomial(left.exponents, left.parameters + right.parameters)

        if isinstance(node.op, ast.Pow):
            base = _monomial(node.left, species, parameters)
            exponent = node.right
            if not (
                isinstance(exponent, ast.Constant)
                and not isinstance(exponent.value, bool)
                and isinstance(exponent.value, (int, float))
            ):
                raise _NotAMonomial(
                    "it raises a factor to an exponent that is not a literal "
                    "number. A mass-action rate law raises a species to its "
                    "stoichiometric coefficient, which the arrow fixes; an "
                    "exponent that is itself a parameter is a Hill "
                    "coefficient, and a Hill law is not mass action"
                )
            value = exponent.value
            if value != int(value) or int(value) < 0:
                raise _NotAMonomial(
                    f"it raises a factor to the power {value!r}. A "
                    f"stoichiometric coefficient is a non-negative whole "
                    f"number; a fractional or negative exponent is an "
                    f"empirical rate law, which these theorems do not cover"
                )
            power = int(value)
            if base.exponents and power == 0:
                # x ** 0 is 1 -- structurally a constant, and saying so is
                # correct rather than clever. Kept explicit so nobody reads
                # the branch below as dropping a species by accident.
                return _Monomial({}, ())
            return _Monomial(
                {name: count * power for name, count in base.exponents.items()},
                base.parameters * power,
            )

        if isinstance(node.op, (ast.Add, ast.Sub)):
            raise _NotAMonomial(
                "it is a sum of terms. A single reaction's mass-action rate "
                "is one product; a sum means either two mechanisms have been "
                "written as one reaction, or the law is empirical"
            )

        raise _NotAMonomial(
            f"it uses the operator {type(node.op).__name__}, which has no "
            f"place in a mass-action rate law"
        )

    if isinstance(node, ast.Call):
        name = getattr(node.func, "id", "a function")
        raise _NotAMonomial(
            f"it calls {name}(). A mass-action rate law is a product of "
            f"powers and calls nothing"
        )

    raise _NotAMonomial(
        f"it contains a {type(node).__name__}, which this module cannot show "
        f"to be a product of powers. It refuses rather than assuming"
    )


# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Hypothesis:
    """One condition a theorem requires, and whether this network meets it."""

    name: str
    holds: bool
    detail: str = ""

    def describe(self) -> str:
        return f"[{'yes' if self.holds else 'NO '}] {self.name}: {self.detail}"


@dataclass(frozen=True)
class Verdict:
    """What a theorem does and does not say about this network.

    `applies` is about the theorem's hypotheses, not about whether the
    reader will like the answer: a deficiency-zero network that is not weakly
    reversible gets `applies=True` and a conclusion that no positive steady
    state exists, which is a strong statement and not a failure.

    `not_claimed` is a field rather than prose in a docstring because it
    travels with the verdict into a report. The whole hazard of this module
    is a theorem's authority attaching to a claim the theorem never made, and
    the counter-claim has to be as portable as the claim.
    """

    theorem: str
    applies: bool
    hypotheses: Tuple[Hypothesis, ...]
    #: What is proved. Empty when the theorem does not apply.
    conclusion: str = ""
    #: Why it does not apply. Empty when it does.
    reason: str = ""
    #: What the theorem is silent about, stated whether or not it applies.
    not_claimed: str = ""
    caveats: Tuple[str, ...] = ()

    def summary(self) -> str:
        lines = [f"{self.theorem}: " + ("APPLIES." if self.applies else "does not apply.")]
        if self.reason:
            lines.append(self.reason)
        if self.conclusion:
            lines.append(self.conclusion)
        lines.extend(self.caveats)
        if self.not_claimed:
            lines.append("Not claimed: " + self.not_claimed)
        lines.append("Hypotheses: " + " ".join(h.describe() for h in self.hypotheses))
        return " ".join(lines)


#: What the Deficiency Zero Theorem is silent about. Kept as a constant so
#: both branches of the verdict carry the same disclaimer, and so a reader
#: can find it without a verdict in hand.
DEFICIENCY_ZERO_NOT_CLAIMED = (
    "global convergence -- where this theorem asserts stability at all, the "
    "stability is LOCAL, relative to the steady state's own stoichiometric "
    "compatibility class, and whether every positive trajectory reaches it is "
    "the Global Attractor Conjecture, which this theorem does not settle; "
    "anything about WHERE the steady state sits, "
    "which depends on rate constants this model has not measured; anything "
    "about trajectories on the boundary of the positive orthant, where one or "
    "more species is exactly zero; and anything about whether the mechanism is "
    "the right one -- a wrong model of deficiency zero has all of these "
    "properties too."
)

#: What the Deficiency One Theorem is silent about. The first clause is the
#: one that matters: the theorem counts steady states and says nothing at all
#: about stability, so a reader who has just read a Deficiency Zero verdict
#: must not carry its stability claim across.
DEFICIENCY_ONE_NOT_CLAIMED = (
    "STABILITY, of any kind. Unlike the Deficiency Zero Theorem this one "
    "counts positive steady states and stops there: the unique steady state it "
    "gives may be unstable, and the system may have sustained oscillations "
    "around it. It also does not claim a steady state EXISTS unless the "
    "network is weakly reversible -- 'at most one' is satisfied by none -- and "
    "it says nothing about where the steady state sits or about the boundary "
    "of the positive orthant."
)


def deficiency_zero_verdict(network: Any) -> Verdict:
    """The Deficiency Zero Theorem, checked against this network.

    Feinberg (1972), Horn and Jackson (1972). For a network of deficiency
    zero:

      * weakly reversible: for EVERY choice of strictly positive rate
        constants, the mass-action system has precisely one steady state in
        the interior of each positive stoichiometric compatibility class,
        that steady state is asymptotically stable relative to its class, and
        there is no non-trivial cyclic trajectory in the positive orthant;

      * not weakly reversible: for every choice of strictly positive rate
        constants there is NO steady state with every species strictly
        positive, and no cyclic trajectory through a strictly positive
        composition.

    That both halves hold for every positive rate constant is the reason this
    is worth running on a model whose constants are all placeholders. It is
    also the reason the verdict is not softened when the placeholders are
    implausible: the claim was never about them.

    Raises rather than answering when the rate laws are not mass action.
    Feinberg states the second half for a class of kinetics wider than mass
    action; this module does not lean on that, because the value of a
    structural proof is entirely in its being correct, and a theorem cited
    slightly beyond its stated scope is worth less than no theorem.
    """
    _require_mass_action(network, "Deficiency Zero Theorem")

    delta = deficiency(network)
    weakly_reversible = is_weakly_reversible(network)
    n = len(complexes(network))
    l = len(linkage_classes(network))
    s = stoichiometric_rank(network)

    hypotheses = (
        Hypothesis(
            "mass-action kinetics",
            True,
            "every rate law was shown to be a positive constant times its "
            "reactant complex",
        ),
        Hypothesis(
            "deficiency zero",
            delta == 0,
            f"delta = n - l - s = {n} - {l} - {s} = {delta}",
        ),
    )

    if delta != 0:
        return Verdict(
            theorem="Deficiency Zero Theorem",
            applies=False,
            hypotheses=hypotheses,
            reason=(
                f"this network has deficiency {delta}, and the theorem covers "
                f"deficiency zero only. That is not a defect in the model -- "
                f"a positive deficiency is what makes multiple steady states "
                f"and oscillation POSSIBLE, which is often the point of the "
                f"mechanism. Try `deficiency_one_verdict`, and note that a "
                f"network outside both theorems has not been shown to be "
                f"multistable either; it has been shown to be unconstrained "
                f"by these two results."
            ),
            not_claimed=DEFICIENCY_ZERO_NOT_CLAIMED,
            caveats=_positivity_caveats(network),
        )

    if weakly_reversible:
        conclusion = (
            f"For EVERY choice of strictly positive rate constants, the "
            f"mass-action system of this network has exactly one steady state "
            f"in the interior of each positive stoichiometric compatibility "
            f"class; that steady state is asymptotically stable relative to "
            f"its class; and no non-trivial cyclic trajectory lies in the "
            f"positive orthant, so this network cannot oscillate. None of "
            f"that depends on a rate constant being known, which is why it "
            f"survives the {len(_parameter_ids(network))} placeholder "
            f"constant(s) this model still carries."
        )
    else:
        conclusion = (
            "For EVERY choice of strictly positive rate constants, the "
            "mass-action system of this network has NO steady state with all "
            "species strictly positive, and no cyclic trajectory through a "
            "strictly positive composition. Whatever this model settles to "
            "lies on the boundary, with at least one species driven to zero "
            "-- which is the correct behaviour for an irreversible pathway "
            "and not a fault. The theorem does not say which boundary state."
        )

    return Verdict(
        theorem="Deficiency Zero Theorem",
        applies=True,
        hypotheses=hypotheses
        + (
            Hypothesis(
                "weakly reversible",
                weakly_reversible,
                "every linkage class is strongly connected"
                if weakly_reversible
                else "at least one linkage class is not strongly connected, "
                "so the second half of the theorem applies",
            ),
        ),
        conclusion=conclusion,
        not_claimed=DEFICIENCY_ZERO_NOT_CLAIMED,
        caveats=_positivity_caveats(network),
    )


def deficiency_one_verdict(network: Any) -> Verdict:
    """The Deficiency One Theorem, checked against this network.

    Feinberg (1987, 1995). Consider a mass-action network with linkage
    classes L_1 .. L_l of deficiencies delta_1 .. delta_l. If

      (i)   each linkage class contains exactly one terminal strong linkage
            class,
      (ii)  delta_i <= 1 for every i, and
      (iii) the delta_i sum to the network's deficiency delta,

    then the system has AT MOST one steady state in the interior of each
    positive stoichiometric compatibility class, whatever the positive rate
    constants are. If the network is additionally weakly reversible, there is
    EXACTLY one.

    All three hypotheses are structural and are checked exactly here. The
    hypothesis that is not structural is the kinetics, and it is the one this
    function refuses on: `KineticsNotMassAction` names it rather than the
    module guessing that a Michaelis-Menten law is "close enough" to mass
    action. It is not close to it; it is a different function, and the
    theorem has nothing to say about a system built from it.

    The conclusion is about COUNTING and nothing else. See
    `DEFICIENCY_ONE_NOT_CLAIMED`: a reader coming from a Deficiency Zero
    verdict has just been handed a stability claim, and there is no stability
    claim here to carry across.
    """
    _require_mass_action(network, "Deficiency One Theorem")

    delta = deficiency(network)
    per_class = linkage_class_deficiencies(network)
    classes = linkage_classes(network)
    terminal = terminal_strong_linkage_classes(network)

    membership: Dict[Complex, int] = {}
    for number, members in enumerate(classes):
        for member in members:
            membership[member] = number
    terminal_per_class = [0] * len(classes)
    for component in terminal:
        terminal_per_class[membership[component[0]]] += 1

    one_terminal = all(count == 1 for count in terminal_per_class)
    at_most_one = all(value <= 1 for value in per_class)
    sums = sum(per_class) == delta
    weakly_reversible = is_weakly_reversible(network)

    hypotheses = (
        Hypothesis(
            "mass-action kinetics",
            True,
            "every rate law was shown to be a positive constant times its "
            "reactant complex",
        ),
        Hypothesis(
            "one terminal strong linkage class per linkage class",
            one_terminal,
            "terminal strong linkage classes per linkage class: "
            + ", ".join(str(count) for count in terminal_per_class),
        ),
        Hypothesis(
            "every linkage class has deficiency at most 1",
            at_most_one,
            "linkage-class deficiencies: "
            + ", ".join(str(value) for value in per_class),
        ),
        Hypothesis(
            "the linkage-class deficiencies sum to the network deficiency",
            sums,
            f"sum of linkage-class deficiencies = {sum(per_class)}, network "
            f"deficiency = {delta}",
        ),
    )

    failed = [h.name for h in hypotheses if not h.holds]
    if failed:
        return Verdict(
            theorem="Deficiency One Theorem",
            applies=False,
            hypotheses=hypotheses,
            reason=(
                f"this network fails {len(failed)} of the theorem's "
                f"hypotheses: {'; '.join(failed)}. The theorem therefore says "
                f"nothing about how many positive steady states it has -- "
                f"which is not the same as saying it has more than one. "
                f"Nothing structural has been established here either way, "
                f"and a numerical search (`compose/analysis.py`) is what "
                f"remains, with the caveat that a search reports what it "
                f"converged to."
            ),
            not_claimed=DEFICIENCY_ONE_NOT_CLAIMED,
            caveats=_positivity_caveats(network),
        )

    if weakly_reversible:
        conclusion = (
            "For EVERY choice of strictly positive rate constants, the "
            "mass-action system of this network has exactly one steady state "
            "in the interior of each positive stoichiometric compatibility "
            "class. This network is weakly reversible, so existence as well "
            "as uniqueness is asserted."
        )
    else:
        conclusion = (
            "For EVERY choice of strictly positive rate constants, the "
            "mass-action system of this network has AT MOST one steady state "
            "in the interior of each positive stoichiometric compatibility "
            "class. The network is not weakly reversible, so the theorem does "
            "not assert that one exists: 'at most one' is satisfied by none, "
            "and an irreversible pathway typically has none."
        )

    return Verdict(
        theorem="Deficiency One Theorem",
        applies=True,
        hypotheses=hypotheses
        + (
            Hypothesis(
                "weakly reversible",
                weakly_reversible,
                "decides existence as well as uniqueness"
                if weakly_reversible
                else "so uniqueness is asserted without existence",
            ),
        ),
        conclusion=conclusion,
        not_claimed=DEFICIENCY_ONE_NOT_CLAIMED,
        caveats=_positivity_caveats(network),
    )


def _grouped_reasons(offenders: Sequence[Any]) -> str:
    """The offending reactions, with each distinct reason stated ONCE.

    WHY THIS IS NOT COSMETIC. Every reaction in a Michaelis-Menten cascade
    fails mass action for the same reason, and the reason is a paragraph.
    Printed per reaction, a six-reaction cascade produced six identical
    copies inside one refusal -- and the refusal is raised twice, once per
    theorem, so the document carried eighteen.

    That is ADR 0028's failure in its purest form: the explanation is
    correct, load-bearing, and unreadable, so nobody reads it and the one
    line that differs between two models is lost in the repetition. Reactions
    are grouped by the reason they share and the reason is given once.
    """
    by_reason: Dict[str, List[str]] = {}
    for finding in offenders:
        by_reason.setdefault(finding.reason, []).append(finding.reaction_id)

    lines = []
    for reason, reactions in by_reason.items():
        if len(reactions) == 1:
            lines.append(f"{reactions[0]}: {reason}")
        else:
            lines.append(
                f"{', '.join(reactions)} ({len(reactions)} reactions, same "
                f"reason): {reason}"
            )
    return "\n  - ".join(lines)


def _require_mass_action(network: Any, theorem: str) -> None:
    """Refuse the verdict unless every rate law was proved mass action.

    THE REFUSAL THIS MODULE EXISTS TO MAKE. A deficiency-zero Michaelis-
    Menten model would otherwise be handed a proof of uniqueness and
    stability that no theorem supports, phrased with all the confidence of
    one that does. The message names the missing hypothesis, names the
    reactions that fail it, says why each fails, and says what to do -- which
    is either to write the mechanism out in elementary steps, or to use the
    numerical analysis that does not need the hypothesis.
    """
    if getattr(network, "rate_rules", ()):
        targets = ", ".join(rule.target for rule in network.rate_rules)
        raise NotAReactionNetwork(
            f"the {theorem} is a statement about the mass-action differential "
            f"equations OF A REACTION NETWORK, and this model drives "
            f"{targets} by rate rule(s) rather than by reactions. Those "
            f"species change in ways the stoichiometry does not describe, so "
            f"the deficiency of the reaction part -- which `deficiency()` "
            f"will still tell you -- does not constrain the dynamics. Write "
            f"the mechanism as reactions if you want a structural verdict."
        )

    # ASSIGNMENT RULES need no branch of their own. A rate law that uses one
    # references a symbol that is neither a species nor a parameter, which
    # `classify_kinetics` already declines to call mass action; one that
    # nothing references is an output and changes no dynamics. Adding a rule
    # here would either duplicate that refusal or reject a model for
    # reporting a derived quantity.
    findings = classify_kinetics(network)
    if not findings:
        raise NotAReactionNetwork(
            f"this model has no reactions, so the {theorem} has nothing to "
            f"apply to. Deficiency counts complexes against reaction vectors, "
            f"and there are none."
        )

    offenders = [finding for finding in findings if not finding.mass_action]
    if offenders:
        raise KineticsNotMassAction(
            f"the {theorem} applies to MASS-ACTION kinetics, and "
            f"{len(offenders)} of this model's {len(findings)} reaction(s) do "
            f"not have mass-action rate laws:\n  - "
            + _grouped_reasons(offenders)
            + "\nThe theorem does not cover these rate laws, so no verdict is "
            "given -- a structural proof about a model the theorem says "
            "nothing about would be worse than no proof at all, because it "
            "would carry a theorem's authority. Michaelis-Menten and Hill "
            "laws are the usual cause and they are not an approximation to "
            "mass action, they are a different function: `kcat*E*S/(Km+S)` "
            "saturates and `k*S` does not. Two ways forward. Write the "
            "mechanism out in elementary steps -- `E + S -> ES`, `ES -> E + "
            "S`, `ES -> E + P` -- which is mass action and is the model the "
            "Michaelis-Menten law was derived FROM; that network can be given "
            "a verdict. Or accept that this question is not structural here "
            "and use `compose/analysis.py`, which needs rate constants and "
            "reports what a numerical search converged to rather than what is "
            "true for every choice of them."
        )


def _positivity_caveats(network: Any) -> Tuple[str, ...]:
    """Note any rate constant that is not currently positive.

    Both theorems quantify over STRICTLY POSITIVE rate constants. That is
    what lets the verdict be given while every constant is a placeholder --
    but a placeholder that is zero or negative puts the model as it currently
    stands outside the family the conclusion is about. Reported rather than
    used to refuse, because the structural verdict is still true of the
    family; what would be false is reading it as a statement about this
    particular parameterisation.
    """
    values = {p.id: float(p.value) for p in getattr(network, "parameters", ())}
    named: Set[str] = set()
    for finding in classify_kinetics(network):
        named.update(finding.rate_constants)

    bad = sorted(name for name in named if values.get(name, 1.0) <= 0.0)
    if not bad:
        return ()
    return (
        f"The conclusion above is quantified over STRICTLY POSITIVE rate "
        f"constants, and {', '.join(bad)} currently hold values that are not "
        f"positive. The verdict is still true of the network; it does not "
        f"cover the model at the values it is carrying right now.",
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def describe(network: Any) -> str:
    """The structural facts, in the order they build on each other.

    Deliberately reports the counts before any verdict, because n, l and s
    are checkable by hand from the model text in a way a theorem's conclusion
    is not, and a reader who disagrees with the verdict should be able to
    find out where the disagreement starts.
    """
    nodes = complexes(network)
    classes = linkage_classes(network)
    s = stoichiometric_rank(network)
    delta = len(nodes) - len(classes) - s

    lines = [
        f"{len(nodes)} complex(es): " + ", ".join(str(node) for node in nodes) + ".",
        f"{len(classes)} linkage class(es): "
        + "; ".join(
            "{" + ", ".join(str(node) for node in members) + "}"
            for members in classes
        )
        + ".",
        f"Stoichiometric subspace has rank {s}, computed exactly over the "
        f"rationals.",
        f"Deficiency = n - l - s = {len(nodes)} - {len(classes)} - {s} = {delta}.",
        f"Weakly reversible: {'yes' if is_weakly_reversible(network) else 'no'}.",
    ]

    findings = classify_kinetics(network)
    if all(finding.mass_action for finding in findings):
        lines.append(
            f"All {len(findings)} rate law(s) are mass action, so the "
            f"deficiency theorems are available."
        )
    else:
        offenders = [f for f in findings if not f.mass_action]
        distinct = {f.reason for f in offenders}
        named = ", ".join(f.reaction_id for f in offenders)
        lines.append(
            f"{len(offenders)} of {len(findings)} rate law(s) are NOT mass "
            f"action, so no deficiency theorem applies. The offenders are "
            f"{named}. "
            + (
                # The reason ONCE, not once per reaction. Every reaction in
                # a Michaelis-Menten cascade fails for the same paragraph,
                # and repeating it six times is how a correct explanation
                # becomes an unread one. The reaction NAMES stay, because a
                # reader has to know which ones.
                f"All {len(offenders)} fail for the same reason: "
                f"{next(iter(distinct))}"
                if len(distinct) == 1 else
                f"{len(distinct)} distinct reasons -- "
                + "; ".join(sorted(distinct))
            )
            + "."
        )
    return " ".join(lines)


# ---------------------------------------------------------------------------
# Reading the network
# ---------------------------------------------------------------------------
#
# Duck-typed, like `analysis.py` and `sensitivity.py`, so this module can be
# read and tested without importing the engine package -- and so a caller can
# hand it any object with the same three attributes.


def _reactions(network: Any) -> Tuple[Any, ...]:
    return tuple(getattr(network, "reactions", ()) or ())


def _species_ids(network: Any) -> Tuple[str, ...]:
    reader = getattr(network, "species_ids", None)
    if callable(reader):
        return tuple(reader())
    return tuple(s.id for s in getattr(network, "species", ()))


def _parameter_ids(network: Any) -> Tuple[str, ...]:
    reader = getattr(network, "parameter_ids", None)
    if callable(reader):
        return tuple(reader())
    return tuple(p.id for p in getattr(network, "parameters", ()))


__all__ = [
    "Complex",
    "Hypothesis",
    "KineticsFinding",
    "KineticsNotMassAction",
    "NotAReactionNetwork",
    "ReactionGraph",
    "StructuralRefusal",
    "Verdict",
    "DEFICIENCY_ONE_NOT_CLAIMED",
    "DEFICIENCY_ZERO_NOT_CLAIMED",
    "classify_kinetics",
    "complexes",
    "deficiency",
    "deficiency_one_verdict",
    "deficiency_zero_verdict",
    "describe",
    "exact_rank",
    "is_mass_action",
    "is_weakly_reversible",
    "linkage_class_deficiencies",
    "linkage_classes",
    "reaction_graph",
    "reaction_vectors",
    "stoichiometric_rank",
    "strong_linkage_classes",
    "terminal_strong_linkage_classes",
]
