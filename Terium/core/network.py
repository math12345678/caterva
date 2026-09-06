"""A reaction network as DATA, so a model stops being a variant and becomes a value.

WHY THIS EXISTS
---------------
Terrium's simulable systems were a closed catalogue. `SUPPORTED_DOMAINS` in
`llmResolver.ts` is thirteen string literals in an `as const` array, and
`model_building.py` is seven hand-written Antimony builders --
`build_michaelis_menten_antimony`, `build_sir_antimony`, one function per
system. Adding any new biology meant editing a TypeScript union, a Zod
schema, a dispatch table, a runner handler and a literature entry.

The language model's entire job, in a product whose pitch is AI-assisted
simulation, was to pick one of thirteen names.

Every one of those builders emits the same shape::

    model <name>
      <id>: <reactants> -> <products>; <rate law>;
      <species> = <value>;
      <parameter> = <value>;
    end

That is a template over data, so the data can be the interface. This module
is that data, and the compiler for it. `mm_network()` and its siblings in
``Terium/continuous/networks.py`` reconstruct the catalogue's models through
it, and `Terium/tests/test_network_equivalence.py` integrates both the old
builder and the compiled network and requires the trajectories to agree --
which is the only equivalence that matters, since Antimony treats ``0`` and
``0.0`` identically and byte equality would be a weaker claim about text.

WHAT MAKES THIS MORE THAN A REFACTOR
------------------------------------
Three things follow from models being values, and none of them is
expressible in a catalogue:

1. **The parameter set becomes dynamic.** Terrium's hard rule -- a value is
   refused unless it was resolved from literature or supplied by the user
   -- was enforced against a per-domain list of parameter names known at
   compile time. A network carries its own parameters, so the same rule
   applies to a system nobody enumerated in advance. Generality that cost
   the provenance guarantee would be worth nothing here; this keeps it.

2. **Rate laws are checked against the network that owns them.** Every
   symbol in a rate law must resolve to a species or parameter of that same
   network. A model proposing a term nobody declared is rejected at
   construction, before roadrunner ever sees it -- which matters precisely
   because the author of a rate law may be a language model.

3. **Invariants come from the model, not from a person.** `conservation_laws`
   computes the left null space of the stoichiometry matrix over the
   rationals, exactly. For an SIR network it derives S + I + R = N without
   being told that epidemics conserve population; for Michaelis-Menten it
   derives S + P = S0. Those are the checks a hand-written test supplies
   today, one domain at a time. Deriving them means a network the catalogue
   never anticipated still gets checked against mathematics it did not
   author and cannot argue with.

Exact arithmetic throughout: `fractions.Fraction`, not floats. A
conservation law is a statement about structure, and a structural claim
decided by floating-point tolerance is a claim about the tolerance.
"""

from __future__ import annotations


def _package_path_missing(exc: ModuleNotFoundError) -> bool:
    """See Terium/core/import_mode.py. Inlined deliberately: this
    guards the import machinery itself, so it cannot import a
    helper to do its job."""
    name = getattr(exc, "name", None)
    return bool(name) and (name == "Terium" or name.startswith("Terium."))


import keyword
import re
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Dict, List, Mapping, Sequence, Tuple

try:
    from Terium.core.data_structures import ModelBuildError
except ModuleNotFoundError as _exc:  # flat mode: Terium/ on sys.path
    if not _package_path_missing(_exc):
        # A missing THIRD-PARTY dependency. Flat mode cannot fix it, and
        # retrying replaces the real reason with a confusing
        # 'No module named core'. See Terium/core/import_mode.py.
        raise
    from core.data_structures import ModelBuildError  # type: ignore[no-redef]

try:
    from Terium.core.utils import _check_model_name, _fmt
except ModuleNotFoundError as _exc:
    if not _package_path_missing(_exc):
        raise
    from core.utils import _check_model_name, _fmt  # type: ignore[no-redef]


#: A valid Antimony identifier. Deliberately stricter than Antimony itself:
#: this is the alphabet a rate law is tokenised against, and a permissive
#: identifier rule would let a rate law smuggle syntax past the symbol check.
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

#: Names Antimony gives its own meaning. `gamma` is here because Antimony
#: resolves it to the gamma FUNCTION, not a parameter -- which is why
#: build_sir_antimony emits `gamma_rate` and the Python API still takes
#: `gamma` (see model_building.py's note and ADR 0024).
_RESERVED_SYMBOLS = frozenset(
    {
        "model",
        "end",
        "species",
        "function",
        "compartment",
        "const",
        "var",
        "at",
        "time",
        "gamma",
        "delay",
        "piecewise",
        "abs",
        "exp",
        "log",
        "log10",
        "ln",
        "pow",
        "sqrt",
        "sin",
        "cos",
        "tan",
    }
)

#: Functions a rate law may call. Anything else that looks like a call is
#: rejected: an unknown identifier followed by `(` is either a typo or an
#: attempt to reach something this module has not sanctioned.
_ALLOWED_FUNCTIONS = frozenset(
    {"abs", "exp", "ln", "log", "log10", "pow", "sqrt", "sin", "cos", "tan"}
)

#: Characters a rate law may contain, beyond identifiers and numbers. No
#: semicolons (statement injection), no braces, no assignment.
_RATE_LAW_ALLOWED = re.compile(r"^[A-Za-z0-9_+\-*/^().,\s]*$")

_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass(frozen=True)
class Species:
    """A pool whose amount changes over time.

    `initial` is the amount at t = 0. It is a quantity like any other, so
    it is subject to the same provenance rule as a rate constant -- see the
    module docstring; this module does not carry provenance itself, it makes
    the SET of quantities discoverable so the layer that does can enumerate
    them.
    """

    id: str
    initial: float


@dataclass(frozen=True)
class Parameter:
    """A constant of the model: a rate, an affinity, a population size."""

    id: str
    value: float


@dataclass(frozen=True)
class Reaction:
    """One transformation, with its stoichiometry and its rate law.

    `reactants` and `products` map a species id to its stoichiometric
    coefficient, which must be a positive integer. A species appearing on
    both sides (a catalyst, or SIR's infective) is legal and nets out to
    zero in the stoichiometry matrix, which is exactly what makes the
    derived conservation laws correct for those models.
    """

    id: str
    reactants: Mapping[str, int]
    products: Mapping[str, int]
    rate_law: str


@dataclass(frozen=True)
class RateRule:
    """``X' = expression`` -- a species driven by an ODE, not by reactions.

    Not every model in the catalogue is a reaction network. Lotka-Volterra,
    Tyson's cell-cycle oscillator and the repressilator are all written as
    rate rules, because their right-hand sides (Hill functions, predation
    terms) are not naturally a sum of mass-action reactions. An IR that
    covered only reactions would express four of the seven builders and
    quietly leave the interesting three behind.

    A species driven by a rate rule may not also appear in a reaction:
    SBML forbids determining one quantity two ways, and so does `problems`.
    """

    target: str
    expression: str


@dataclass(frozen=True)
class AssignmentRule:
    """``X := expression`` -- a derived quantity, recomputed every step.

    Tyson's model uses one for `alpha := k4prime / k4` and another to
    report `cyclin_fraction := v - u`. These are outputs and shorthands,
    not state: they have no initial value and no dynamics of their own.
    """

    target: str
    expression: str


@dataclass(frozen=True)
class ReactionNetwork:
    """A complete model, as data.

    Ordering is significant and preserved: the compiler emits statements in
    declaration order so that compilation is deterministic and two runs of
    the same network produce the same text.
    """

    name: str
    species: Tuple[Species, ...] = ()
    parameters: Tuple[Parameter, ...] = ()
    reactions: Tuple[Reaction, ...] = ()
    rate_rules: Tuple[RateRule, ...] = ()
    assignment_rules: Tuple[AssignmentRule, ...] = ()

    # -- discovery, for the layers that enforce provenance ---------------

    def species_ids(self) -> Tuple[str, ...]:
        return tuple(s.id for s in self.species)

    def parameter_ids(self) -> Tuple[str, ...]:
        return tuple(p.id for p in self.parameters)

    def quantity_ids(self) -> Tuple[str, ...]:
        """Every number this model needs to run.

        This is the set the hard rule must be satisfied over. A catalogue
        could hardcode it per domain; a constructed network cannot, which
        is the point.
        """
        return self.species_ids() + self.parameter_ids()

    # -- structure -------------------------------------------------------

    def stoichiometry_matrix(self) -> List[List[Fraction]]:
        """Rows are species (in declaration order), columns are reactions.

        Entry (i, j) is the net change in species i per unit extent of
        reaction j: products minus reactants, so a catalyst is zero.

        A species driven by a RATE RULE gets an extra column of its own,
        with a 1 in its row. That column is not a reaction; it is the
        honest statement that this species can change in a way stoichiometry
        does not describe. Its presence forces the left null space to
        exclude that species, so `conservation_laws` cannot claim a
        conservation that the rate rule is free to violate. Omitting it
        would produce derived invariants that are false -- which is worse
        than deriving none.
        """
        index = {s.id: i for i, s in enumerate(self.species)}
        n_columns = len(self.reactions) + len(self.rate_rules)
        matrix = [
            [Fraction(0) for _ in range(n_columns)] for _ in self.species
        ]
        for j, reaction in enumerate(self.reactions):
            for sid, coefficient in reaction.reactants.items():
                if sid in index:
                    matrix[index[sid]][j] -= Fraction(coefficient)
            for sid, coefficient in reaction.products.items():
                if sid in index:
                    matrix[index[sid]][j] += Fraction(coefficient)
        for k, rule in enumerate(self.rate_rules):
            if rule.target in index:
                matrix[index[rule.target]][len(self.reactions) + k] = Fraction(1)
        return matrix

    def conservation_laws(self) -> List[Dict[str, Fraction]]:
        """Linear combinations of species that no reaction can change.

        The left null space of the stoichiometry matrix: every vector y with
        yᵀ·N = 0. Each is a conserved quantity, returned as a mapping from
        species id to coefficient, normalised so the coefficients are
        integers with no common factor and the first non-zero is positive.

        For SIR this returns {S: 1, I: 1, R: 1} -- total population --
        without anyone having said that epidemics conserve people. For
        Michaelis-Menten it returns {S: 1, P: 1}. These are the invariants
        the hand-written domain tests check one at a time; deriving them
        means a network nobody anticipated is still checked.

        Computed over Fraction, exactly. A conservation law is a structural
        fact, and deciding a structural fact by floating-point tolerance
        would make it a fact about the tolerance.
        """
        matrix = self.stoichiometry_matrix()
        if not matrix or not matrix[0]:
            # Nothing changes anything: every species is trivially
            # conserved. The identity basis is correct and keeps callers
            # uniform rather than special-casing an empty model.
            return [{s.id: Fraction(1)} for s in self.species]
        return [
            self._as_law(vector) for vector in _left_null_space(matrix)
        ]

    def _as_law(self, vector: Sequence[Fraction]) -> Dict[str, Fraction]:
        return {
            self.species[i].id: value
            for i, value in enumerate(vector)
            if value != 0
        }

    # -- validation ------------------------------------------------------

    def problems(self) -> List[str]:
        """Everything wrong with this network, or an empty list.

        Returns rather than raises so a caller can report all of them at
        once. `validate()` is the raising form.
        """
        problems: List[str] = []

        try:
            _check_model_name(self.name)
        except ModelBuildError as exc:
            problems.append(str(exc))

        if not self.species:
            problems.append(
                "a network needs at least one species; nothing would change "
                "over time"
            )

        seen: Dict[str, str] = {}
        for kind, items in (
            ("species", self.species),
            ("parameter", self.parameters),
        ):
            for item in items:
                problems.extend(_identifier_problems(item.id, kind))
                if item.id in seen:
                    problems.append(
                        f"{item.id!r} is declared as both a {seen[item.id]} "
                        f"and a {kind}; a rate law referring to it could "
                        f"mean either"
                    )
                seen[item.id] = kind

        # Assignment-rule targets are usable in expressions, so they join
        # the symbol table -- but they are derived, not state, and must not
        # shadow a species or parameter.
        for rule in self.assignment_rules:
            problems.extend(_identifier_problems(rule.target, "assignment rule"))
            if rule.target in seen:
                problems.append(
                    f"assignment rule {rule.target!r} has the same name as a "
                    f"{seen[rule.target]}; the model would determine it twice"
                )
            seen[rule.target] = "assignment rule"

        known = set(seen)
        reaction_ids: set = set()
        for reaction in self.reactions:
            problems.extend(_identifier_problems(reaction.id, "reaction"))
            if reaction.id in reaction_ids:
                problems.append(f"duplicate reaction id {reaction.id!r}")
            reaction_ids.add(reaction.id)
            if reaction.id in known:
                problems.append(
                    f"reaction {reaction.id!r} collides with a "
                    f"{seen[reaction.id]} of the same name"
                )

            for side, mapping in (
                ("reactant", reaction.reactants),
                ("product", reaction.products),
            ):
                for sid, coefficient in mapping.items():
                    if sid not in {s.id for s in self.species}:
                        problems.append(
                            f"reaction {reaction.id!r} names {side} "
                            f"{sid!r}, which is not a declared species"
                        )
                    if not isinstance(coefficient, int) or isinstance(
                        coefficient, bool
                    ):
                        problems.append(
                            f"reaction {reaction.id!r}: stoichiometry for "
                            f"{sid!r} must be an int, got "
                            f"{type(coefficient).__name__}"
                        )
                    elif coefficient <= 0:
                        problems.append(
                            f"reaction {reaction.id!r}: stoichiometry for "
                            f"{sid!r} must be positive, got {coefficient}. "
                            f"Put it on the other side of the arrow instead."
                        )

            problems.extend(
                _rate_law_problems(reaction.id, reaction.rate_law, known)
            )

        species_ids = {s.id for s in self.species}
        driven_by_reaction = {
            sid
            for r in self.reactions
            for sid in set(r.reactants) | set(r.products)
            # A catalyst is untouched by the reaction, so it is not
            # "driven" by it and may still carry a rate rule.
            if r.reactants.get(sid, 0) != r.products.get(sid, 0)
        }
        rule_targets: set = set()
        for rule in self.rate_rules:
            if rule.target not in species_ids:
                problems.append(
                    f"rate rule targets {rule.target!r}, which is not a "
                    f"declared species. A rate rule sets a species' "
                    f"derivative; give it an initial value first."
                )
            if rule.target in rule_targets:
                problems.append(
                    f"two rate rules both target {rule.target!r}"
                )
            rule_targets.add(rule.target)
            if rule.target in driven_by_reaction:
                problems.append(
                    f"{rule.target!r} is changed by a reaction AND by a rate "
                    f"rule. SBML forbids determining one quantity two ways, "
                    f"and the derived conservation laws would be meaningless."
                )
            problems.extend(
                _rate_law_problems(
                    f"rate rule {rule.target}", rule.expression, known
                )
            )

        for rule in self.assignment_rules:
            problems.extend(
                _rate_law_problems(
                    f"assignment rule {rule.target}", rule.expression, known
                )
            )
            if rule.target in {t.target for t in self.rate_rules}:
                problems.append(
                    f"{rule.target!r} has both an assignment rule and a rate "
                    f"rule"
                )

        if not self.reactions and not self.rate_rules:
            problems.append(
                "this model has neither reactions nor rate rules, so nothing "
                "can change; it would integrate to a flat line"
            )
        elif self.reactions and not self.rate_rules and not any(
            r.reactants or r.products for r in self.reactions
        ):
            problems.append(
                "every reaction is empty on both sides, so no species can "
                "change; this model would integrate to a flat line"
            )

        return problems

    def validate(self) -> "ReactionNetwork":
        """Raise `ModelBuildError` unless the network is well formed."""
        problems = self.problems()
        if problems:
            raise ModelBuildError(
                f"invalid reaction network {self.name!r}:\n  - "
                + "\n  - ".join(problems)
            )
        return self


def _identifier_problems(name: str, kind: str) -> List[str]:
    if not isinstance(name, str) or not name:
        return [f"{kind} id must be a non-empty string, got {name!r}"]
    if not _IDENTIFIER.match(name):
        return [
            f"{kind} id {name!r} is not a valid Antimony identifier "
            f"(letters, digits and underscore; must not start with a digit)"
        ]
    if name in _RESERVED_SYMBOLS:
        return [
            f"{kind} id {name!r} is reserved by Antimony. `gamma` in "
            f"particular resolves to the gamma FUNCTION, which is why the "
            f"SIR builder emits `gamma_rate`."
        ]
    if keyword.iskeyword(name):
        return [f"{kind} id {name!r} is a Python keyword"]
    return []


def _rate_law_problems(
    reaction_id: str, rate_law: str, known: set
) -> List[str]:
    """Every symbol in a rate law must belong to the network that owns it.

    This is the check that makes a machine-authored rate law safe to
    compile. A term nobody declared is rejected here, with the undefined
    symbol named, rather than reaching roadrunner as a model that silently
    treats the unknown as zero or fails with a parser error nobody can act
    on.
    """
    problems: List[str] = []
    if not isinstance(rate_law, str) or not rate_law.strip():
        return [f"reaction {reaction_id!r} has an empty rate law"]

    if not _RATE_LAW_ALLOWED.match(rate_law):
        bad = sorted(set(re.findall(r"[^A-Za-z0-9_+\-*/^().,\s]", rate_law)))
        problems.append(
            f"reaction {reaction_id!r}: rate law contains disallowed "
            f"character(s) {''.join(bad)!r}. Rate laws are expressions, not "
            f"statements -- no assignment, no semicolons, no blocks."
        )

    for token in _TOKEN.finditer(rate_law):
        symbol = token.group(0)
        follows = rate_law[token.end():].lstrip()
        if follows.startswith("("):
            if symbol not in _ALLOWED_FUNCTIONS:
                problems.append(
                    f"reaction {reaction_id!r}: rate law calls {symbol!r}, "
                    f"which is not an allowed function "
                    f"({', '.join(sorted(_ALLOWED_FUNCTIONS))})"
                )
            continue
        if symbol in _ALLOWED_FUNCTIONS or symbol == "time":
            continue
        if symbol not in known:
            problems.append(
                f"reaction {reaction_id!r}: rate law refers to {symbol!r}, "
                f"which is not a species or parameter of this network. "
                f"Declared: {', '.join(sorted(known)) or '(nothing)'}"
            )
    return problems


def _left_null_space(matrix: List[List[Fraction]]) -> List[List[Fraction]]:
    """Basis for {y : yᵀ·M = 0}, exactly, over the rationals.

    Computed as the null space of the transpose by Gauss-Jordan elimination
    with Fractions. Vectors are normalised to integer coefficients with no
    common factor, first non-zero positive, so the same network always
    yields the same laws in the same form -- a conservation law printed
    two different ways reads as two different claims.
    """
    rows = len(matrix)
    cols = len(matrix[0]) if rows else 0
    # Transpose: null space of Mᵀ is the left null space of M.
    transposed = [[matrix[i][j] for i in range(rows)] for j in range(cols)]

    augmented = [row[:] for row in transposed]
    n_rows = len(augmented)
    n_cols = rows

    pivots: List[int] = []
    pivot_row = 0
    for col in range(n_cols):
        target = None
        for r in range(pivot_row, n_rows):
            if augmented[r][col] != 0:
                target = r
                break
        if target is None:
            continue
        augmented[pivot_row], augmented[target] = (
            augmented[target],
            augmented[pivot_row],
        )
        lead = augmented[pivot_row][col]
        augmented[pivot_row] = [v / lead for v in augmented[pivot_row]]
        for r in range(n_rows):
            if r != pivot_row and augmented[r][col] != 0:
                factor = augmented[r][col]
                augmented[r] = [
                    a - factor * b
                    for a, b in zip(augmented[r], augmented[pivot_row])
                ]
        pivots.append(col)
        pivot_row += 1
        if pivot_row == n_rows:
            break

    free = [c for c in range(n_cols) if c not in pivots]
    basis: List[List[Fraction]] = []
    for free_col in free:
        vector = [Fraction(0)] * n_cols
        vector[free_col] = Fraction(1)
        for row_index, pivot_col in enumerate(pivots):
            vector[pivot_col] = -augmented[row_index][free_col]
        basis.append(_normalise(vector))
    return basis


def _normalise(vector: List[Fraction]) -> List[Fraction]:
    """Integer coefficients, no common factor, first non-zero positive."""
    denominators = [v.denominator for v in vector if v != 0]
    if not denominators:
        return vector
    multiplier = 1
    for d in denominators:
        multiplier = multiplier * d // _gcd(multiplier, d)
    scaled = [v * multiplier for v in vector]

    numerators = [abs(v.numerator) for v in scaled if v != 0]
    divisor = 0
    for n in numerators:
        divisor = _gcd(divisor, n)
    if divisor > 1:
        scaled = [v / divisor for v in scaled]

    for value in scaled:
        if value != 0:
            if value < 0:
                scaled = [-v for v in scaled]
            break
    return scaled


def _gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return abs(a)


def _side(mapping: Mapping[str, int]) -> str:
    """One side of an Antimony reaction arrow.

    An empty side is emitted as nothing at all, which is how Antimony
    writes creation (`-> X`) and degradation (`X ->`).
    """
    if not mapping:
        return ""
    return " + ".join(
        (sid if coefficient == 1 else f"{coefficient} {sid}")
        for sid, coefficient in mapping.items()
    )


def compile_to_antimony(network: ReactionNetwork, validate: bool = True) -> str:
    """Render a network as Antimony source.

    Emits the same shape the hand-written builders in `model_building.py`
    produce -- reactions, then species initials, then parameters, in
    declaration order.

    `validate` defaults to True and should stay that way for anything whose
    rate laws were not written by hand. It is a parameter only because
    `model_building.py`'s builders take one, and a compiler that could not
    be asked the same question would be the odd one out.
    """
    if validate:
        network.validate()

    lines = [f"model {network.name}"]
    for reaction in network.reactions:
        lines.append(
            f"  {reaction.id}: {_side(reaction.reactants)} -> "
            f"{_side(reaction.products)}; {reaction.rate_law};"
        )
    for rule in network.rate_rules:
        lines.append(f"  {rule.target}' = {rule.expression};")
    for species in network.species:
        lines.append(f"  {species.id} = {_fmt(species.initial)};")
    for parameter in network.parameters:
        lines.append(f"  {parameter.id} = {_fmt(parameter.value)};")
    # Assignment rules last, matching the order the hand-written builders
    # use (Tyson's model emits `alpha :=` after its parameters).
    for rule in network.assignment_rules:
        lines.append(f"  {rule.target} := {rule.expression};")
    lines.append("end")
    return "\n".join(lines) + "\n"


def describe_conservation_laws(network: ReactionNetwork) -> List[str]:
    """Human-readable form of `conservation_laws`, for reports and errors.

    e.g. ``S + I + R`` for SIR, ``S + P`` for Michaelis-Menten.
    """
    described: List[str] = []
    for law in network.conservation_laws():
        terms = []
        for sid, coefficient in law.items():
            if coefficient == 1:
                terms.append(sid)
            else:
                terms.append(f"{coefficient} {sid}")
        described.append(" + ".join(terms))
    return described


__all__ = [
    "Species",
    "Parameter",
    "Reaction",
    "RateRule",
    "AssignmentRule",
    "ReactionNetwork",
    "compile_to_antimony",
    "describe_conservation_laws",
]
