"""Whether every number in a composed model still says what it is.

WHAT THESE TESTS ARE PINNING
-----------------------------
`core.network.Parameter` has an id and a value and nothing else, so the unit,
the kind, the motif and the database table a number came from are all dropped
the moment a network is built. Three modules hit that hole independently and
each worked around its own corner of it.

`quantities.py` is the side table that keeps all of it, and these tests pin
the four properties that make it worth having:

  * every number in every composable model is described, including the
    species initials -- which is where a composed model keeps its
    concentrations, and the reason a parameters-only table would have the
    same blind spot that made `robustness.py` vary nothing;
  * a kind comes from the motif that declared it, never from the id, because
    `library_enzymology` has an affinity called `L`;
  * an unrecognised unit is refused with what was read, not guessed at -- a
    converter that assumed molar would introduce the thousandfold error that
    `scale.py` exists to find;
  * the consistency check can actually fail, demonstrated on a network
    holding a parameter the model has never heard of. A checker nobody has
    seen go red is not a checker.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from Terium.compose.builder import Composition
from Terium.compose.library import CATALYTIC_STEP
from Terium.compose.motifs import (
    KIND_AFFINITY, KIND_CONCENTRATION, KIND_EXPONENT, KIND_RATE_CONSTANT,
)
from Terium.compose.pipeline import compose
from Terium.compose.quantities import (
    DIMENSION_CONCENTRATION, DIMENSION_CONCENTRATION_PER_TIME,
    DIMENSION_DIMENSIONLESS, DIMENSION_PER_CONCENTRATION_PER_TIME,
    DIMENSION_PER_TIME, SOURCE_PARAMETER, SOURCE_SPECIES_INITIAL, Quantity,
    QuantityError, QuantityTable, check_consistency, dimension_of,
    quantities_of, to_molar, to_per_second,
)

#: Shapes the grammar recognises, one per family, covering every kind the
#: library declares: rate constants, affinities, Hill exponents and the
#: concentrations that live on species. Several rather than one because the
#: claim is about the LIBRARY, and a single motif could satisfy it by
#: accident.
QUERIES = (
    "three step phosphorylation cascade",
    "a toggle switch between two repressors",
    "repressilator oscillations",
    "reversible binding of a ligand to a receptor",
    "two enzymes competing for the same substrate",
    "substrate inhibition at high substrate concentration",
    "gene expression with transcription and translation",
    "a futile cycle of two opposing enzymes",
    "an open system with constant inflow",
    "competitive inhibition of an enzyme",
    "a carrier transporting a solute across a membrane",
    "cooperative ligand binding with a Hill coefficient",
    "feedback inhibition of a linear pathway at the first step",
    "an autoregulated gene repressing its own promoter",
    "receptor internalisation after ligand binding",
    "the concerted two-state model of an allosteric enzyme",
    "autocatalysis of a product",
    "a reversible enzymatic step",
)


@pytest.fixture(scope="module")
def models():
    """Every shape above, composed once.

    Module-scoped because composing eighteen models per test dominated the
    runtime of this file. Safe to share: nothing here mutates a model, and
    the two tests that need an edited network build a new one with
    `dataclasses.replace`.
    """
    return {query: compose(query) for query in QUERIES}


class TestEveryNumberIsDescribed:
    """The property the whole module exists for.

    A table that covers most of a model is worse than no table, because the
    numbers it misses are exactly the ones nothing else describes either.
    """

    def test_every_parameter_of_every_model_gets_a_quantity(self, models) -> None:
        assert len(models) == len(QUERIES), "the premise: every shape composed"
        for query, model in models.items():
            table = quantities_of(model)
            in_network = {p.id for p in model.network.parameters}
            described = {q.id for q in table.parameters}
            assert in_network, f"{query} has no parameters at all"
            assert described == in_network, (query, in_network ^ described)
            assert all(
                table[name].source == SOURCE_PARAMETER for name in in_network
            ), query

    def test_every_quantity_carries_a_readable_non_empty_unit(self, models) -> None:
        """A unit is the point. An empty one is the gap wearing a value.

        `dimension_of` refuses an empty unit separately from an unreadable
        one, so this catches both shapes of missing.
        """
        for query, model in models.items():
            for quantity in quantities_of(model):
                assert quantity.unit.strip(), (query, quantity.id)
                # Raises rather than guessing, so reaching the assert at all
                # is the claim.
                assert dimension_of(quantity.unit), (query, quantity.id)

    def test_the_table_covers_species_as_well_as_parameters(self, models) -> None:
        for query, model in models.items():
            table = quantities_of(model)
            everything = {p.id for p in model.network.parameters} | {
                s.id for s in model.network.species
            }
            assert set(table.ids()) == everything, query

    def test_every_model_is_self_consistent_as_built(self, models) -> None:
        # The negative control for TestTheConsistencyCheckCanFail below. If
        # this failed, that one would prove nothing.
        for query, model in models.items():
            report = check_consistency(model)
            assert report.complete, (query, report.summary())
            assert report.checked == report.governed


class TestSpeciesInitialsAreQuantitiesToo:
    """Where a composed model keeps its concentrations.

    ADR 0013 makes the builder write kcat and the enzyme separately, which
    is what makes a composed model more resolvable than a catalogue one --
    and the consequence is that every concentration lands on a `Species`
    rather than a `Parameter`. A parameters-only table would therefore have
    a blind spot shaped exactly like the bug that made `robustness.py` offer
    to vary concentrations and vary nothing.
    """

    def test_a_concentration_is_a_species_initial_not_a_parameter(self) -> None:
        model = compose("substrate inhibition at high substrate concentration")
        table = quantities_of(model)
        concentrations = table.of_kind(KIND_CONCENTRATION)
        assert concentrations, "the premise: this model has concentrations"
        assert all(q.source == SOURCE_SPECIES_INITIAL for q in concentrations)
        assert not [
            q for q in table.parameters if q.kind == KIND_CONCENTRATION
        ], "no concentration of this model lives on a Parameter"

    def test_species_initials_are_chosen_and_never_resolvable(self, models) -> None:
        seen = 0
        for query, model in models.items():
            for quantity in quantities_of(model).species:
                seen += 1
                assert quantity.kind == KIND_CONCENTRATION, (query, quantity.id)
                assert quantity.chosen, (query, quantity.id)
                assert not quantity.resolvable, (query, quantity.id)
                assert quantity.table is None, (
                    query, quantity.id,
                    "no database serves how much you put in the tube",
                )
        assert seen > 0, "the premise: these models have species"

    def test_a_species_initial_of_a_resolvable_kind_is_refused(self) -> None:
        """Nobody publishes how much enzyme is in your tube.

        A starting amount is a concentration by construction, so a species
        quantity of any other kind would make the pipeline go and search for
        a number that is the caller's to choose.
        """
        with pytest.raises(QuantityError, match="concentration by construction"):
            Quantity(
                id="x_S", value=1.0, unit="mM", kind=KIND_RATE_CONSTANT,
                motif="catalytic_step", instance="x", name="S",
                source=SOURCE_SPECIES_INITIAL,
            )

    def test_the_species_unit_is_the_one_the_composition_declared(self) -> None:
        """Read, not assumed.

        `scale.LIBRARY_CONCENTRATION_UNIT` has to assume mM because it works
        from a network, and says so. A table built from the composition can
        read what the composition declared, so a model in uM is described in
        uM rather than misread by a factor of a thousand.
        """
        composition = Composition("micromolar", concentration_unit="uM")
        composition.add(CATALYTIC_STEP, "reaction")
        table = QuantityTable.from_composition(composition)

        assert table.concentration_unit == "uM"
        assert {q.unit for q in table.species} == {"uM"}
        # And the conversion follows the declaration rather than a default.
        substrate = table["reaction_S"]
        assert substrate.molar() == pytest.approx(substrate.value * 1e-6)


class TestKindComesFromTheMotifNotFromTheName:
    """The reason the kind is carried rather than re-derived.

    `scale.check` has to guess affinity-from-concentration by looking for
    `_km`, `_kd`, `_ki` in the id, and says so. That guess is right often and
    wrong quietly: `library_enzymology.mwc_allostery` declares an affinity
    called `L`, and `library_metabolic` one called `Keq`.
    """

    def test_an_affinity_called_L_is_still_an_affinity(self) -> None:
        """`mwc_allostery` declares one, and no name rule would find it.

        Built directly from the motif because the grammar reads "allosteric"
        as Hill repression; the motif is in the library either way, and any
        composition that reaches it has this parameter in it.
        """
        from Terium.compose.library_enzymology import MWC_ALLOSTERY

        composition = Composition("mwc")
        composition.add(MWC_ALLOSTERY, "enzyme")
        table = QuantityTable.from_composition(composition)

        allosteric = table["enzyme_L"]
        assert allosteric.kind == KIND_AFFINITY
        assert allosteric.resolvable
        # `scale.check` picks affinities out by looking for `_km`, `_kd`,
        # `_ki` or `_k` in the id. None of them is in this one.
        assert not any(
            marker in allosteric.id.lower()
            for marker in ("_km", "_kd", "_ki", "_ksi", "_k")
        )

    def test_the_unit_alone_cannot_tell_an_affinity_from_an_exponent(self) -> None:
        """Which is why the kind is carried, and a real misreading today.

        `mwc_allostery` declares BOTH an allosteric equilibrium constant `L`
        (an affinity, ~1000) and a Hill exponent `n`, and both are
        dimensionless. Given only the unit, a checker has to treat them
        alike -- and `scale.check` does: it reports L = 1000 as a Hill
        coefficient "higher than any natural system known", comparing an
        equilibrium constant against haemoglobin.

        That finding is wrong and the number in it is right, which is the
        hardest kind to notice. Fixing `scale.check` to consult the kind is
        a change to what that module reports and is not made here; this
        pins the fact that the information it needs now exists.
        """
        from Terium.compose.library_enzymology import MWC_ALLOSTERY
        from Terium.compose.scale import check

        composition = Composition("mwc")
        composition.add(MWC_ALLOSTERY, "enzyme")
        table = QuantityTable.from_composition(composition)

        assert table["enzyme_L"].dimension == table["enzyme_n"].dimension
        assert table["enzyme_L"].kind != table["enzyme_n"].kind

        report = check(composition.to_network(), units=table.parameter_units())
        misread = [f for f in report.findings if f.parameter == "enzyme_L"]
        assert misread, "the premise: scale judges L as though it were n"
        assert "cooperative" in misread[0].against

    def test_a_hill_exponent_is_chosen_not_resolvable(self) -> None:
        model = compose("a toggle switch between two repressors")
        table = quantities_of(model)
        exponents = table.of_kind(KIND_EXPONENT)
        assert exponents, "the premise: a toggle switch has Hill coefficients"
        for quantity in exponents:
            assert quantity.chosen
            assert not quantity.resolvable
            assert quantity.dimension == DIMENSION_DIMENSIONLESS

    def test_resolvable_is_derived_from_the_kind_and_cannot_be_set(self) -> None:
        # Stored separately, the two could drift and a concentration could
        # become resolvable. It is a property, so they cannot.
        quantity = Quantity(
            id="x_E", value=1.0, unit="mM", kind=KIND_CONCENTRATION,
            motif="catalytic_step", instance="x", name="E",
            source=SOURCE_SPECIES_INITIAL,
        )
        assert not quantity.resolvable
        with pytest.raises(AttributeError):
            quantity.resolvable = True  # type: ignore[misc]

    def test_an_unknown_kind_is_refused(self) -> None:
        # Kind decides whether the literature is asked, so a kind that is
        # neither resolvable nor chosen has no defined behaviour.
        with pytest.raises(QuantityError, match="neither resolvable nor chosen"):
            Quantity(
                id="x_q", value=1.0, unit="mM", kind="probably_measurable",
                motif="catalytic_step", instance="x", name="q",
            )


class TestConversionsAreExactWhereTheyCanBe:
    """Against arithmetic, not against the implementation.

    Every one of these has a closed-form answer, which is the only kind of
    test worth writing about a unit conversion -- a test that asserts
    whatever the code returns would pass against the factor-of-a-thousand
    error it is meant to prevent.
    """

    def test_millimolar_is_a_thousandth_of_molar(self) -> None:
        assert to_molar(5.0, "mM") == pytest.approx(5e-3, rel=1e-12)
        assert to_molar(5.0, "M") == 5.0

    def test_millimolar_and_micromolar_differ_by_exactly_a_thousand(self) -> None:
        # The error this module is built to make impossible: dimensionally
        # identical, and a factor of a thousand apart.
        ratio = to_molar(1.0, "mM") / to_molar(1.0, "uM")
        assert ratio == pytest.approx(1000.0, rel=1e-12)

    def test_per_minute_is_a_sixtieth_of_per_second(self) -> None:
        assert to_per_second(60.0, "1/min") == pytest.approx(1.0, rel=1e-12)
        assert to_per_second(3600.0, "1/h") == pytest.approx(1.0, rel=1e-12)
        assert to_per_second(2.5, "1/s") == 2.5

    def test_dimension_of_names_every_shape_the_library_uses(self) -> None:
        # These four plus dimensionless are every unit the six motif
        # libraries declare between them.
        assert dimension_of("mM") == DIMENSION_CONCENTRATION
        assert dimension_of("1/s") == DIMENSION_PER_TIME
        assert dimension_of("1/(mM*s)") == DIMENSION_PER_CONCENTRATION_PER_TIME
        assert dimension_of("mM/s") == DIMENSION_CONCENTRATION_PER_TIME
        assert dimension_of("dimensionless") == DIMENSION_DIMENSIONLESS


class TestAnUnrecognisedUnitIsRefusedNotGuessed:
    """Silence and a default are the same failure here.

    A converter that fell back to molar would produce a number
    indistinguishable from a correct one, which is the whole reason
    `scale.py` reports an uninterpretable parameter as UNCHECKED rather than
    checking it against a guess.
    """

    def test_a_unit_the_parser_does_not_know_is_refused(self) -> None:
        with pytest.raises(QuantityError, match="cannot read the unit"):
            dimension_of("furlongs per fortnight")
        with pytest.raises(QuantityError, match="rather than guessed at"):
            to_molar(1.0, "furlongs per fortnight")

    def test_the_refusal_says_what_the_parser_does_read(self) -> None:
        # A refusal with no way forward is a wall. This one names the units
        # that would work.
        with pytest.raises(QuantityError) as raised:
            to_per_second(1.0, "beats per bar")
        message = str(raised.value)
        assert "molar with a metric prefix" in message
        assert "guessed at" in message

    def test_a_missing_unit_is_refused_differently_from_dimensionless(self) -> None:
        """Opposite statements, and the parser reads them the same way.

        `units.parse_unit("")` returns dimensionless, which is a reasonable
        reading for a rate-law checker and the wrong one here: an empty unit
        says the declaration is missing, and calling that a pure ratio is
        the original gap wearing a value.
        """
        assert dimension_of("dimensionless") == DIMENSION_DIMENSIONLESS
        with pytest.raises(QuantityError, match="NOT `dimensionless`"):
            dimension_of("")
        with pytest.raises(QuantityError, match="no unit is recorded"):
            dimension_of("   ")

    def test_a_rate_has_no_value_in_molar(self) -> None:
        with pytest.raises(QuantityError, match="not a concentration"):
            to_molar(10.0, "1/s")

    def test_a_second_order_constant_is_not_converted_as_a_first_order_one(self) -> None:
        """The confusion that made `catalytically_dead` refuse to act.

        `1/(mM*s)` contains a time unit, so a converter that looked for one
        would divide it happily and return a number that reads as a turnover
        number.
        """
        with pytest.raises(QuantityError, match="not a rate per unit time"):
            to_per_second(1e6, "1/(mM*s)")
        with pytest.raises(QuantityError, match="not a concentration"):
            to_molar(1e6, "1/(mM*s)")

    def test_a_quantity_refuses_in_terms_of_what_it_actually_is(self) -> None:
        model = compose("substrate inhibition at high substrate concentration")
        kcat = quantities_of(model)["reaction_kcat"]
        assert kcat.dimension == DIMENSION_PER_TIME
        assert kcat.per_second() == pytest.approx(kcat.value)
        with pytest.raises(QuantityError, match="rate_constant"):
            kcat.molar()


class TestTheConsistencyCheckCanFail:
    """A checker nobody has seen go red is not a checker.

    Every case below is a way the side table and the network can come apart,
    and the first is the one that matters: a number in the network that no
    quantity describes is the unit gap reappearing one level up.
    """

    def test_an_extra_parameter_the_model_does_not_know_is_reported(self) -> None:
        from Terium.core.network import Parameter

        model = compose("substrate inhibition at high substrate concentration")
        assert check_consistency(model).complete, "the premise: clean to start"

        edited = replace(
            model.network,
            parameters=model.network.parameters + (Parameter("k_smuggled", 3.0),),
        )
        report = check_consistency(model, network=edited)

        assert not report.complete
        assert report.ungoverned == ("k_smuggled",)
        assert report.governed == report.checked - 1

    def test_the_summary_says_the_gap_has_reappeared(self) -> None:
        from Terium.core.network import Parameter

        model = compose("substrate inhibition at high substrate concentration")
        edited = replace(
            model.network,
            parameters=model.network.parameters + (Parameter("k_smuggled", 3.0),),
        )
        summary = check_consistency(model, network=edited).summary()

        assert "k_smuggled" in summary
        assert "NO quantity" in summary
        # And it says what that MEANS, not only that it happened.
        assert "no unit, no kind" in summary
        assert "rebuild the table" in summary

    def test_an_extra_species_is_reported_too(self) -> None:
        # A concentration is a species initial here, so a species the table
        # does not know is exactly as ungoverned as a parameter.
        from Terium.core.network import Species

        model = compose("substrate inhibition at high substrate concentration")
        edited = replace(
            model.network,
            species=model.network.species + (Species("ghost", 1.0),),
        )
        report = check_consistency(model, network=edited)

        assert not report.complete
        assert "ghost" in report.ungoverned

    def test_a_quantity_naming_nothing_is_reported_as_orphaned(self) -> None:
        model = compose("substrate inhibition at high substrate concentration")
        dropped = model.network.parameters[0].id
        edited = replace(
            model.network,
            parameters=tuple(
                p for p in model.network.parameters if p.id != dropped
            ),
        )
        report = check_consistency(model, network=edited)

        assert not report.complete
        assert report.orphaned == (dropped,)
        assert not report.ungoverned

    def test_a_quantity_with_no_unit_is_reported(self) -> None:
        table = QuantityTable([
            Quantity(id="x_kcat", value=1.0, unit="", kind=KIND_RATE_CONSTANT,
                     motif="catalytic_step", instance="x", name="kcat"),
        ])

        class _Network:
            parameters = (type("P", (), {"id": "x_kcat", "value": 1.0})(),)
            species = ()

        report = table.consistency(_Network())
        assert not report.complete
        assert report.unitless == ("x_kcat",)
        assert "not `dimensionless`" in report.summary()

    def test_an_empty_network_is_not_a_clean_result(self) -> None:
        """Refusing to report success on an empty scan.

        A checker that returns True over zero numbers reports success in
        precisely the case where it verified nothing -- the defect
        `scripts/check_no_vacuous_tests.py` exists to find in tests, in a
        checker instead.
        """
        composition = Composition("empty-check")
        composition.add(CATALYTIC_STEP, "reaction")
        table = QuantityTable.from_composition(composition)

        class _Empty:
            parameters = ()
            species = ()

        report = table.consistency(_Empty())
        assert not report.complete
        assert report.checked == 0
        assert "empty scan is not a clean one" in report.summary()

    def test_raise_if_incomplete_refuses_with_the_whole_summary(self) -> None:
        from Terium.core.network import Parameter

        model = compose("substrate inhibition at high substrate concentration")
        edited = replace(
            model.network,
            parameters=model.network.parameters + (Parameter("k_smuggled", 3.0),),
        )
        report = check_consistency(model, network=edited)

        with pytest.raises(QuantityError, match="k_smuggled"):
            report.raise_if_incomplete()
        # The clean one does not raise, or the refusal above proves nothing.
        check_consistency(model).raise_if_incomplete()


class TestTheTableRefusesWhatItCannotDescribe:
    def test_a_bare_network_is_refused_by_name(self) -> None:
        """The refusal a caller most needs, because it says WHY.

        A bare `ReactionNetwork` has already lost the units, kinds and
        provenance. Returning an empty table would describe that loss as a
        model with nothing in it.
        """
        model = compose("substrate inhibition at high substrate concentration")
        with pytest.raises(QuantityError, match="dropped when it was built"):
            QuantityTable.from_model(model.network)

    def test_an_unknown_id_says_what_the_model_does_hold(self) -> None:
        model = compose("substrate inhibition at high substrate concentration")
        table = quantities_of(model)
        with pytest.raises(QuantityError, match="reaction_kcat"):
            table["reaction_kcat_typo"]

    def test_two_quantities_for_one_id_are_refused(self) -> None:
        # The IR holds one number under an id, so two descriptions of it
        # means one is wrong and nothing can say which.
        shared = dict(
            value=1.0, unit="1/s", kind=KIND_RATE_CONSTANT,
            motif="catalytic_step", instance="x", name="kcat",
        )
        with pytest.raises(QuantityError, match="two quantities claim the id"):
            QuantityTable([
                Quantity(id="x_kcat", **shared),
                Quantity(id="x_kcat", **shared),
            ])

    def test_a_composition_with_no_motifs_is_refused(self) -> None:
        with pytest.raises(QuantityError, match="missing model"):
            QuantityTable.from_composition(Composition("nothing"))

    def test_asking_for_a_kind_that_is_not_one_is_refused(self) -> None:
        # An empty tuple would read as "this model has none".
        model = compose("substrate inhibition at high substrate concentration")
        with pytest.raises(QuantityError, match="is not a kind"):
            quantities_of(model).of_kind("vibes")


class TestScaleStillWorksThroughThis:
    """`scale.units_from_model` now delegates here, and must not have moved.

    It has callers beyond `scale.check` -- `perturbation.dead_mutant` reads
    it to decide whether a parameter is a rate -- so the contract being
    preserved is the mapping itself, not merely that the scale suite is
    green.
    """

    def test_it_returns_exactly_what_the_motifs_declare(self, models) -> None:
        from Terium.compose.scale import units_from_model

        for query, model in models.items():
            independent = {
                instance.parameter_id(parameter.name): parameter.unit
                for instance in model.recognition.composition.instances
                for parameter in instance.motif.parameters
            }
            assert independent, query
            assert units_from_model(model) == independent, query

    def test_it_still_returns_parameters_only(self) -> None:
        """Narrower than the table on purpose.

        `scale.check` looks this mapping up per PARAMETER and handles species
        through its own `species_unit` argument. Species entries here would
        look as though they were being checked through the mapping when they
        are not.
        """
        from Terium.compose.scale import units_from_model

        model = compose("three step phosphorylation cascade")
        units = units_from_model(model)
        species = {s.id for s in model.network.species}

        assert species, "the premise: this model has species"
        assert not (set(units) & species)
        assert set(units) == {p.id for p in model.network.parameters}

    def test_a_model_with_no_composition_still_yields_an_empty_mapping(self) -> None:
        """The tolerance that was there before, kept deliberately.

        `QuantityTable.from_model` refuses this case loudly, which is right
        for a new caller. Doing that here would turn a report that says
        "everything unchecked" into an exception, for callers that have
        handled the empty mapping for their whole life.
        """
        from Terium.compose.scale import units_from_model

        assert units_from_model(object()) == {}

    def test_no_parameter_is_unchecked_for_want_of_a_unit(self, models) -> None:
        """The gap, measured through the module that first reported it.

        `scale.check` on a bare network says every parameter is unchecked
        because "no unit is recorded for it". Through this table, that
        reason must never appear.
        """
        from Terium.compose.scale import check_model

        for query, model in models.items():
            report = check_model(model)
            assert report.physically_possible, (
                query, [f.describe() for f in report.errors]
            )
            unitless = [
                name for name, reason in report.unchecked.items()
                if "no unit is recorded" in reason
            ]
            assert not unitless, (query, unitless)

    def test_what_remains_unchecked_is_scales_converter_not_a_missing_unit(
        self, models
    ) -> None:
        """A residual gap, named rather than left as a vague remainder.

        The unit is now always there, and `scale.check` still cannot read
        all of them: its converters are two lookup tables covering molar and
        per-time, and the library also writes zero-order synthesis rates in
        `mM/s`. Those stay UNCHECKED, which is the honest report -- and it
        is a gap in that module's converters, not in the provenance, because
        this one reads the unit perfectly well.
        """
        from Terium.compose.scale import check_model

        remaining = {}
        for query, model in models.items():
            table = quantities_of(model)
            for name, reason in check_model(model).unchecked.items():
                assert "not one this module recognises" in reason, (
                    query, name, reason
                )
                remaining[table[name].unit] = name

        assert remaining, (
            "the premise: something the library writes is still outside "
            "scale's converters"
        )
        assert set(remaining) == {"mM/s", "1/(mM*s)"}, remaining
        # Both read perfectly well here, so what is missing over there is a
        # converter and not the provenance.
        assert dimension_of("mM/s") == DIMENSION_CONCENTRATION_PER_TIME
        assert dimension_of("1/(mM*s)") == DIMENSION_PER_CONCENTRATION_PER_TIME

    def test_the_diffusion_limit_never_fires_on_a_library_model(self) -> None:
        """A defect this work surfaced, RECORDED rather than fixed here.

        `scale.DIFFUSION_LIMIT_PER_MOLAR_PER_SECOND` is that module's
        headline physical bound, and `_is_second_order` decides when to
        apply it by looking for `/M/s`, `M^-1s^-1` or `1/(M*s)` in the unit
        string. Every second-order constant the motif libraries declare is
        written `1/(mM*s)`, which matches none of those -- so the constant
        is reported UNCHECKED and the diffusion limit has never fired on a
        model this repository can build.

        Not fixed in this commit: it changes what `scale.check` reports and
        belongs with its own tests in `test_compose_scale.py`. Recorded so
        that it is visible rather than merely true. WHEN IT IS FIXED THIS
        TEST GOES RED -- delete it then; it exists to make the gap
        impossible to forget, not to defend it.
        """
        from Terium.compose.library import REVERSIBLE_BINDING
        from Terium.compose.scale import _is_second_order, check

        composition = Composition("association")
        composition.add(REVERSIBLE_BINDING, "reaction")
        table = QuantityTable.from_composition(composition)

        second_order = [
            q for q in table.parameters
            if q.dimension == DIMENSION_PER_CONCENTRATION_PER_TIME
        ]
        assert second_order, "the premise: this motif has a second-order step"
        assert not _is_second_order(second_order[0].unit), (
            "fixed -- delete this test and assert the bound instead"
        )

        # Faster than anything in water can associate, and unremarked.
        network = replace(
            composition.to_network(),
            parameters=tuple(
                replace(p, value=1e20) if p.id == second_order[0].id else p
                for p in composition.to_network().parameters
            ),
        )
        report = check(network, units=table.parameter_units())
        assert second_order[0].id in report.unchecked
        assert not report.errors


class TestWhatTheTableSaysAboutItself:
    def test_the_summary_does_not_claim_the_values_are_measured(self) -> None:
        """Nor that they are definitely not.

        This table describes the SLOTS -- id, unit, kind, where a search
        would go. It does not record whether a resolver has since written a
        measured value into any of them, so it says so and defaults to
        placeholder, which is the safe direction to be wrong in.
        """
        summary = quantities_of(compose("three step phosphorylation cascade")).summary()
        assert "NOT recorded in this table" in summary
        assert "illustrative placeholders unless a search report" in summary
        assert "yours to choose" in summary

    def test_there_is_no_property_asserting_a_value_is_a_placeholder(self) -> None:
        """It would be confidently wrong on exactly the grounded models.

        Such a property could only return `resolvable`, and a resolved kcat
        is still resolvable while no longer being a placeholder.
        """
        assert not hasattr(Quantity, "illustrative")
        assert not hasattr(Quantity, "placeholder")
        assert not hasattr(Quantity, "measured")

    def test_no_quantity_claims_a_citation_for_its_value(self) -> None:
        """`table` is an address, not a source.

        It names the BRENDA table a search would go to. A field that read as
        provenance for the number currently sitting in `value` would attach a
        citation to a placeholder, which is the one thing this project never
        does.
        """
        model = compose("three step phosphorylation cascade")
        quantities = list(quantities_of(model))
        assert quantities, "the premise: this model has numbers in it"
        for quantity in quantities:
            for field_name in ("citation", "reference", "source_paper", "doi"):
                assert not hasattr(quantity, field_name), (quantity.id, field_name)
        # The wording carries the claim, so it is pinned rather than left to
        # a reader's memory of what `table` was for.
        assert "where a search" in Quantity.__doc__
        assert "rather than where this number came from" in Quantity.__doc__
        assert "asserts that the number is right" in Quantity.__doc__

    def test_a_resolvable_quantity_with_no_table_is_visible(self) -> None:
        """"Searched and not found" and "never searched" are different.

        An mRNA degradation rate is resolvable from a paper and from no
        database, and a report that listed it beside a kcat without saying so
        would describe a search that never happened.
        """
        model = compose("gene expression with transcription and translation")
        table = quantities_of(model)
        tableless = [q for q in table.resolvable if q.table is None]
        assert tableless, "the premise: this model has one"
        assert "only from a paper" in tableless[0].describe()
        assert "no database table behind them" in table.summary()
