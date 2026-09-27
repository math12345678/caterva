"""Gene expression, and the lumped constant these motifs exist to remove.

The library's route to a gene was `synthesis_degradation`, whose `ks` is in
mM/s. That constant is k_tx * [gene] -- a promoter property multiplied by a
copy number nobody but the caller knows -- so it is the Vmax of gene
expression and it is unresolvable for the same reason (ADR 0013).

These tests pin the three things that follow. That no parameter in the
module has the dimensions of a rate of production, because writing the gene
out as a species is what removed them. That the two-stage model lands on its
closed-form steady state and separates the two response times, since a
one-step model has one time constant where the biology has two. And that
doubling the gene dose doubles the output -- an experiment a lumped `ks`
cannot express at all.
"""

from __future__ import annotations

import math

import pytest

from caterva.compose.analysis import analyse, derivative_function
from caterva.compose.builder import Composition
from caterva.compose.library_expression import (
    ACTIVATED_PROMOTER, AUTOREGULATED_GENE, CONSTITUTIVE_PROMOTER,
    EXPRESSION_LIBRARY, MRNA_DEGRADATION, PROTEIN_DEGRADATION_TAGGED,
    REPRESSED_PROMOTER, TRANSLATION, TWO_STAGE_EXPRESSION, expression_motif,
)
from caterva.compose.motifs import (
    CHOSEN_KINDS, KIND_CONCENTRATION, KIND_EXPONENT, RESOLVABLE_KINDS,
)
from caterva.compose.units import REACTION_RATE, parse_unit

#: How many motifs this module ships. Stated so that a motif deleted or
#: silently renamed fails here rather than shrinking every loop below into
#: a test of nothing.
MOTIF_COUNT = 8


def _whole_gene() -> Composition:
    """A gene assembled from four separate motifs.

    Promoter, translation, message decay and protein removal, wired through
    shared species rather than written as one big motif. This is the
    composition the module is for: each piece carries its own assumption and
    its own basis, and swapping the promoter for a repressed one is a
    one-line change rather than a new entry in a catalogue.
    """
    composition = Composition("whole_gene")
    composition.add(CONSTITUTIVE_PROMOTER, "prom")
    composition.add(TRANSLATION, "tl", {"M": "prom_M"})
    composition.add(MRNA_DEGRADATION, "decay", {"M": "prom_M"})
    composition.add(PROTEIN_DEGRADATION_TAGGED, "clp", {"P": "tl_P"})
    return composition


class TestTheMotifsThemselves:
    def test_every_motif_validates_at_construction(self) -> None:
        """Importing the module is the test; this makes it explicit.

        `Motif.__post_init__` rejects a rate law referencing anything that
        is not a port or a parameter, a duplicate name, and a stoichiometry
        naming a port the motif does not have. All eight are built at import
        time, so a malformed one cannot reach this assertion.
        """
        assert len(EXPRESSION_LIBRARY) == MOTIF_COUNT
        for name, motif in EXPRESSION_LIBRARY.items():
            assert motif.name == name
            assert motif.summary, f"{name} has no summary"
            assert motif.reactions, f"{name} has no reactions"

    def test_every_basis_says_where_the_assumption_breaks(self) -> None:
        # An assumption stated without its failure condition is decoration:
        # a reader cannot tell whether it applies to their system. Every
        # basis here names the case that breaks it.
        missing = [
            name for name, motif in EXPRESSION_LIBRARY.items()
            if "fail" not in motif.basis.lower()
        ]
        assert missing == [], (
            f"these motifs state an assumption but not where it stops "
            f"holding: {missing}"
        )

    def test_no_parameter_has_the_dimensions_of_a_synthesis_rate(self) -> None:
        """The property the whole module exists for.

        A production term in mM/s is a lumped quantity: it is a per-copy
        rate times a copy number, and the copy number is the caller's. Every
        production rate here is a per-copy constant in 1/s multiplying a
        SPECIES, so a parameter with the dimensions of mM/s would mean the
        lump had come back.
        """
        lumped = [
            f"{name}.{parameter.name} ({parameter.unit})"
            for name, motif in EXPRESSION_LIBRARY.items()
            for parameter in motif.parameters
            if parse_unit(parameter.unit).same_dimensions(REACTION_RATE)
        ]
        assert lumped == [], (
            f"a parameter with the dimensions of amount-per-time is a rate "
            f"of production with a copy number multiplied into it: {lumped}"
        )

    def test_no_parameter_is_called_vmax_or_ks(self) -> None:
        # The dimensional test above is the real one -- this catches the
        # same mistake spelled in a unit that hides it, e.g. a "ks" declared
        # in 1/s that is used as though it were zero order.
        named = [
            f"{name}.{parameter.name}"
            for name, motif in EXPRESSION_LIBRARY.items()
            for parameter in motif.parameters
            if parameter.name.lower() in {"vmax", "v_max", "ks", "k_s"}
        ]
        assert named == [], f"lumped synthesis parameter reintroduced: {named}"

    def test_every_hill_exponent_is_chosen_and_never_resolved(self) -> None:
        # A Hill coefficient is a modelling choice with a conventional
        # value. Sending a scout to find "the" n for a promoter asks for a
        # measurement nobody made.
        exponents = [
            (name, parameter)
            for name, motif in EXPRESSION_LIBRARY.items()
            for parameter in motif.parameters
            if parameter.name == "n"
        ]
        assert len(exponents) == 3, (
            f"expected the three Hill motifs to carry an exponent, found "
            f"{[name for name, _ in exponents]}"
        )
        for name, parameter in exponents:
            assert parameter.kind == KIND_EXPONENT, name
            assert not parameter.resolvable, name
            assert parameter.kind in CHOSEN_KINDS, name

    def test_no_amount_is_a_parameter(self) -> None:
        """Every concentration in this module is a species.

        `KIND_CONCENTRATION` exists for a parameter that is an amount, and
        nothing here has one: the gene, the ribosome pool and the protease
        pool are all ports, so their values are species initials that the
        caller sets and no scout is ever sent to find. A concentration that
        arrived as a parameter would be resolvable-looking by accident.
        """
        amounts = [
            f"{name}.{parameter.name}"
            for name, motif in EXPRESSION_LIBRARY.items()
            for parameter in motif.parameters
            if parameter.kind == KIND_CONCENTRATION
        ]
        assert amounts == [], (
            f"these amounts are parameters and should be ports: {amounts}"
        )

    def test_an_affinity_keeps_concentration_units_and_stays_resolvable(self) -> None:
        # The converse trap: a Km or an operator constant is measured in mM
        # and IS a literature quantity. Ruling out concentration-valued
        # parameters entirely would have thrown those away.
        affinities = [
            parameter
            for motif in EXPRESSION_LIBRARY.values()
            for parameter in motif.parameters
            if parameter.name in {"K", "Km_tl", "Km_deg"}
        ]
        assert len(affinities) == 5
        for parameter in affinities:
            assert parameter.resolvable
            assert parameter.kind in RESOLVABLE_KINDS
            assert parse_unit(parameter.unit).same_dimensions(parse_unit("mM"))

    def test_a_rate_constant_with_no_table_says_so(self) -> None:
        """A failed lookup and an absent one are different sentences.

        `MotifParameter.__post_init__` appends the note when a resolvable
        parameter has no table. Transcription and translation rates have
        none -- BRENDA holds enzyme constants and these are not enzyme
        constants -- and the report must say that rather than implying a
        failed lookup.
        """
        note = "resolvable only from a paper"
        k_tx = next(p for p in TWO_STAGE_EXPRESSION.parameters if p.name == "k_tx")
        assert k_tx.table is None
        assert note in k_tx.description

        # And the protease, which IS an enzyme, keeps its table and does not
        # get the note.
        kcat = next(
            p for p in PROTEIN_DEGRADATION_TAGGED.parameters
            if p.name == "kcat_deg"
        )
        assert kcat.table == "kcat"
        assert note not in kcat.description

    def test_naming_a_motif_that_does_not_exist_lists_the_ones_that_do(self) -> None:
        # A refusal that only says no leaves the reader guessing at
        # spelling. This one says what to type instead.
        with pytest.raises(KeyError) as raised:
            expression_motif("two_step_expression")
        message = str(raised.value)
        assert "two_stage_expression" in message
        assert "autoregulated_gene" in message


class TestWhatTheLiteratureIsAskedFor:
    def test_no_species_amount_is_ever_sent_to_a_scout(self) -> None:
        """The gene dose, the ribosome pool and the protease pool.

        All three are amounts, all three are ports, and none of them may
        appear in the list of quantities the pipeline goes and searches for.
        Nobody publishes how many copies of your plasmid you transformed.
        """
        composition = _whole_gene()
        resolvable = {q.parameter_id for q in composition.quantities_to_resolve()}
        species = set(composition.species_ids)

        assert resolvable & species == set()
        assert species <= set(composition.chosen_quantities())
        assert {"prom_G", "tl_R", "clp_Prot"} <= species

    def test_every_quantity_to_resolve_is_a_rate_or_an_affinity(self) -> None:
        composition = _whole_gene()
        quantities = composition.quantities_to_resolve()
        assert quantities, "a gene with no unmeasured constants is not a gene"
        for quantity in quantities:
            assert quantity.kind in RESOLVABLE_KINDS, quantity.parameter_id

    def test_the_gap_list_says_which_constants_have_no_table(self) -> None:
        # The point of carrying `table` into the request: two of these
        # can be looked up in a database and the rest need a paper. A gap
        # list that did not distinguish them would send every one of them
        # to the same place and report the same failure for both reasons.
        composition = _whole_gene()
        without_table = {
            q.parameter_name for q in composition.quantities_to_resolve()
            if q.table is None
        }
        with_table = {
            q.parameter_name for q in composition.quantities_to_resolve()
            if q.table is not None
        }
        assert {"k_tx", "d_m", "kcat_tl", "Km_tl", "mu"} <= without_table
        assert with_table == {"kcat_deg", "Km_deg"}


class TestDimensionalConsistency:
    def test_every_motif_balances_on_its_own(self) -> None:
        """No findings, not few findings.

        A rate law with the wrong dimensions integrates perfectly well and
        the trajectory is wrong by whatever factor the mistake introduced.
        There is no later point at which that becomes visible, so it is
        checked here, at composition time.
        """
        findings = []
        for name, motif in EXPRESSION_LIBRARY.items():
            composition = Composition(f"check_{name}")
            composition.add(motif, "u")
            findings.extend(
                f"{name}: {finding.detail}" for finding in composition.unit_findings()
            )
        assert findings == []

    def test_a_gene_composed_from_four_motifs_still_balances(self) -> None:
        # Each motif balancing alone does not make the composition balance:
        # the shared species is what ties them together, and a motif that
        # assumed a different concentration unit would only show up here.
        assert _whole_gene().unit_findings() == ()

    def test_the_check_notices_a_hill_constant_in_the_wrong_unit(self) -> None:
        """The mutation that proves the two tests above can fail.

        `repressed_promoter` declares K in mM. Composed into a model whose
        species are in uM, the Hill term compares K^n against R^n with the
        bases a thousand apart -- dimensionally identical, wrong by 1000^n.
        Without the symbolic-scale tracking in units.py this passes
        silently, which is why the mutation is pinned rather than assumed.
        """
        composition = Composition("micromolar_model", concentration_unit="uM")
        composition.add(REPRESSED_PROMOTER, "p")
        findings = composition.unit_findings()
        assert findings, "a 1000-fold unit mismatch went unreported"
        assert [finding.severity for finding in findings] == ["scale"]
        assert "differ in scale by a factor" in findings[0].detail


class TestTheAnalyticSteadyState:
    """Cases where the right answer is known in closed form.

    dM/dt = k_tx*G - d_m*M and dP/dt = k_tl*M - d_p*P have exactly one
    steady state and it is a ratio, not a root find's opinion. If the
    machinery cannot reproduce it, nothing it says about the autoregulated
    gene -- where no closed form survives -- is worth reading.
    """

    @staticmethod
    def _two_stage(gene_dose: float | None = None):
        composition = Composition("two_stage_expression")
        composition.add(TWO_STAGE_EXPRESSION, "gene")
        if gene_dose is not None:
            composition.set_initial("gene_G", gene_dose)
        return composition

    @staticmethod
    def _values(network):
        constants = {p.id: p.value for p in network.parameters}
        constants.update({s.id: s.initial for s in network.species})
        return constants

    def test_the_closed_form_is_exactly_a_zero_of_the_vector_field(self) -> None:
        """The answer, checked without asking a solver for it.

        Evaluated straight against the compiled right-hand side, so it
        tests the MODEL rather than the root find: if the motif's rate laws
        did not compose into dM/dt = k_tx*G - d_m*M, this fails no matter
        how well the solver behaves. The sibling test below then asks
        whether `analyse` finds the same point.
        """
        network = self._two_stage().to_network()
        values = self._values(network)
        rhs, order = derivative_function(network)

        message = values["gene_k_tx"] * values["gene_G"] / values["gene_d_m"]
        protein = values["gene_k_tl"] * message / values["gene_d_p"]
        state = {"gene_G": values["gene_G"], "gene_M": message, "gene_P": protein}

        derivatives = rhs([state[name] for name in order])
        # The largest flux in the model, so the bound below is a statement
        # about round-off and not about the absolute size of nanomolar
        # numbers -- which are small enough that any absolute bound would
        # be met by a model that did nothing at all.
        largest_flux = values["gene_k_tl"] * message
        assert largest_flux > 0.0
        assert max(abs(value) for value in derivatives) < 1e-12 * largest_flux

    def test_the_model_lands_on_k_tx_over_d_m_and_k_tl_over_d_p(self) -> None:
        network = self._two_stage().to_network()
        values = self._values(network)
        report = analyse(network)

        assert len(report.stable_points) == 1, report.summary()
        state = report.stable_points[0].state

        message = values["gene_k_tx"] * values["gene_G"] / values["gene_d_m"]
        protein = values["gene_k_tl"] * message / values["gene_d_p"]
        assert state["gene_M"] == pytest.approx(message, rel=1e-6)
        assert state["gene_P"] == pytest.approx(protein, rel=1e-6)
        # And the gene itself did not move: it is a template, not a
        # reactant, so nothing consumes it.
        assert state["gene_G"] == pytest.approx(values["gene_G"], rel=1e-9)

    def test_the_two_stages_keep_their_own_response_times(self) -> None:
        """Why two stages and not one.

        The Jacobian is triangular, so its eigenvalues are exactly -d_m and
        -d_p. A one-step model has ONE of them, and the protein's approach
        to steady state follows the slower -- which is the quantity most
        gene-circuit models are built to ask about.
        """
        network = self._two_stage().to_network()
        values = self._values(network)
        point = analyse(network).stable_points[0]

        rates = sorted(value.real for value in point.eigenvalues)
        expected = sorted([-values["gene_d_m"], -values["gene_d_p"]])
        assert rates == pytest.approx(expected, rel=1e-6)
        # Not the same number: an order of magnitude apart, which is the
        # whole content of separating the stages.
        assert values["gene_d_m"] > 10 * values["gene_d_p"]

    def test_doubling_the_gene_dose_doubles_the_protein(self) -> None:
        """The experiment a lumped synthesis rate cannot express.

        Copy number is a scenario choice -- one chromosomal copy or fifty on
        a plasmid -- so with production written as a single mM/s constant,
        asking this question means editing a rate constant and calling the
        answer a prediction. Here it is an initial condition.
        """
        single = self._two_stage()
        network = single.to_network()
        base = self._values(network)["gene_G"]
        one_copy = analyse(network).stable_points[0].state

        network = self._two_stage(gene_dose=2.0 * base).to_network()
        two_copies = analyse(network).stable_points[0].state

        assert two_copies["gene_M"] == pytest.approx(2.0 * one_copy["gene_M"], rel=1e-6)
        assert two_copies["gene_P"] == pytest.approx(2.0 * one_copy["gene_P"], rel=1e-6)

    def test_a_repressed_promoter_at_zero_repressor_is_the_unrepressed_one(self) -> None:
        # The Hill factor is K^n/(K^n + R^n), which is exactly 1 at R = 0.
        # Analytic, and it pins the direction of the term: written the other
        # way up it would be 0 here and the test would fail rather than
        # producing a plausible smaller number.
        composition = Composition("repressed_with_no_repressor")
        composition.add(REPRESSED_PROMOTER, "prom")
        composition.add(MRNA_DEGRADATION, "decay", {"M": "prom_M"})
        network = composition.to_network()
        values = {p.id: p.value for p in network.parameters}
        values.update({s.id: s.initial for s in network.species})
        assert values["prom_R"] == 0.0

        point = analyse(network).stable_points[0]
        unrepressed = values["prom_k_tx"] * values["prom_G"] / values["decay_d_m"]
        assert point.state["prom_M"] == pytest.approx(unrepressed, rel=1e-6)


class TestNegativeAutoregulation:
    def test_the_gene_settles_below_the_unregulated_one(self) -> None:
        """What the feedback is for, stated as an inequality.

        `autoregulated_gene` shares the four rate constants of
        `two_stage_expression`, so the only difference between the two
        steady states is the Hill factor -- which is strictly less than one
        for any positive protein. The regulated gene must land lower, and
        by more than rounding.
        """
        unregulated = Composition("unregulated")
        unregulated.add(TWO_STAGE_EXPRESSION, "gene")
        open_loop = analyse(unregulated.to_network()).stable_points[0].state

        regulated = Composition("autoregulated")
        regulated.add(AUTOREGULATED_GENE, "gene")
        closed_loop = analyse(regulated.to_network()).stable_points[0].state

        assert closed_loop["gene_P"] < 0.5 * open_loop["gene_P"]
        assert closed_loop["gene_P"] > 0.0

    def test_it_lands_on_the_analytic_root_of_the_cubic(self) -> None:
        """The closed form that survives the feedback, and its measured cost.

        Eliminating M from the two steady-state conditions gives

            P = ceiling * K^n / (K^n + P^n),   ceiling = k_tl*k_tx*G/(d_p*d_m)

        and at n = 2 that is a cubic, P^3 + K^2 P - ceiling*K^2 = 0, with
        exactly one positive real root -- one sign change in its
        coefficients. Newton from `ceiling`, which is above the root because
        the Hill factor is below one, converges monotonically and to machine
        precision. So this compares `analyse` against an answer it had no
        part in producing, which a self-consistency check of its own output
        cannot do.

        MEASURED, on the motif's own defaults:

            analytic root                     1.7055336431300678e-4
            rhs at the analytic root           4.1e-25   (machine precision)
            what `analyse` converges to       1.7053827003915816e-4
            relative gap                       8.9e-5
            the converged point's residual     5.6e-13

        The algebra is exact and the root find is not, and the reason is
        the scale rather than the motif: dM/dt changes by only 2.2e-5 per
        unit of P here, so a residual of 5.6e-13 -- comfortably inside
        `analysis.py`'s 1e-9 acceptance gate -- still leaves P wrong in its
        fifth digit. The linear two-stage model above agrees to 1e-6
        because a linear residual is solved in one exact step; this one
        cannot be. The bound below is set an order of magnitude above the
        measured gap, and is still far tighter than any wiring mistake
        would survive: repression pointed the wrong way misses by a factor
        of four.
        """
        composition = Composition("autoregulated")
        composition.add(AUTOREGULATED_GENE, "gene")
        network = composition.to_network()
        values = {p.id: p.value for p in network.parameters}
        values.update({s.id: s.initial for s in network.species})

        ceiling = (
            values["gene_k_tl"] * values["gene_k_tx"] * values["gene_G"]
            / (values["gene_d_p"] * values["gene_d_m"])
        )
        squared = values["gene_K"] ** 2
        assert values["gene_n"] == 2.0, "the cubic is what n = 2 buys"

        root = ceiling
        for _ in range(200):
            step = (root ** 3 + squared * root - ceiling * squared) / (
                3 * root ** 2 + squared
            )
            root -= step
            if abs(step) <= 1e-18 * abs(root):
                break
        assert 0.0 < root < ceiling

        # The root is a root: checked on the model's own right-hand side,
        # not on the polynomial it was derived from, so an error in that
        # derivation fails here.
        rhs, order = derivative_function(network)
        message = values["gene_d_p"] * root / values["gene_k_tl"]
        analytic = {"gene_G": values["gene_G"], "gene_M": message, "gene_P": root}
        derivatives = rhs([analytic[name] for name in order])
        assert max(abs(value) for value in derivatives) < 1e-12 * (
            values["gene_k_tl"] * message
        )

        state = analyse(network).stable_points[0].state
        assert state["gene_P"] == pytest.approx(root, rel=1e-3)
        assert state["gene_M"] == pytest.approx(message, rel=1e-3)

    def test_the_feedback_is_wired_to_the_gene_s_own_protein(self) -> None:
        """The wiring mistake this motif exists to make impossible.

        Autoregulation means the repressor IS the product. Composed from
        separate motifs it is a `couple` call that can be forgotten or
        pointed at the wrong species, and the model still simulates -- as
        an unregulated gene next to an inert repressor. Here there is one
        protein species and the transcription law names it.
        """
        composition = Composition("autoregulated")
        composition.add(AUTOREGULATED_GENE, "gene")
        network = composition.to_network()

        transcription = next(
            r for r in network.reactions
            if r.id == "gene_autorepressed_transcription"
        )
        assert "gene_P" in transcription.rate_law
        assert "gene_G" in transcription.rate_law
        # The protein is a modifier of transcription, not a reactant of it:
        # repression occupies the operator, it does not consume the
        # repressor.
        assert "gene_P" not in transcription.reactants
        assert "gene_P" not in transcription.products
        assert [s.id for s in network.species].count("gene_P") == 1


class TestTranslationSaturates:
    def test_it_is_michaelis_menten_in_the_message_not_first_order(self) -> None:
        """Half the ribosome pool at Km, which is what "ribosome-limited"
        means and what `k_tl * M` cannot say.

        Evaluated directly against the rate law rather than through a
        steady state, because the claim is about the shape of the term:
        doubling the message from Km does NOT double the output.
        """
        composition = Composition("translation")
        composition.add(TRANSLATION, "tl")
        network = composition.to_network()
        values = {p.id: p.value for p in network.parameters}
        values.update({s.id: s.initial for s in network.species})

        law = next(r for r in network.reactions if r.id == "tl_translation").rate_law

        def rate(message: float) -> float:
            return eval(  # noqa: S307 - a rate law this test just built
                law.replace("^", "**"), {"__builtins__": {}},
                {**values, "tl_M": message},
            )

        km = values["tl_Km_tl"]
        maximal = values["tl_kcat_tl"] * values["tl_R"]
        assert rate(km) == pytest.approx(maximal / 2.0, rel=1e-12)
        # Saturating: ten times the message is not ten times the protein.
        assert rate(10 * km) < 2.0 * rate(km)
        assert rate(10 * km) == pytest.approx(maximal * 10 / 11, rel=1e-12)
        # And the linear limit the two-stage motif assumes: far below Km it
        # IS first order, which is why `k_tl * M` is a limit and not a
        # different model.
        small = km / 1e4
        assert rate(small) == pytest.approx(
            maximal * small / km, rel=1e-3
        )


class TestSaturableProteinRemoval:
    def test_dilution_survives_when_the_protease_is_swamped(self) -> None:
        """Why the motif carries two terms and not one.

        Past Km the protease contributes a constant, so a first-order model
        of removal overstates it without bound. Dilution does not saturate,
        so total removal keeps rising -- and a protein whose only removal
        route was proteolysis would accumulate forever. Both facts are
        arithmetic on the rate laws, so both are asserted exactly.
        """
        composition = Composition("tagged_removal")
        composition.add(PROTEIN_DEGRADATION_TAGGED, "clp")
        network = composition.to_network()
        values = {p.id: p.value for p in network.parameters}
        values.update({s.id: s.initial for s in network.species})

        laws = {r.id: r.rate_law for r in network.reactions}

        def flux(reaction: str, protein: float) -> float:
            return eval(  # noqa: S307 - a rate law this test just built
                laws[reaction].replace("^", "**"), {"__builtins__": {}},
                {**values, "clp_P": protein},
            )

        km = values["clp_Km_deg"]
        saturated = values["clp_kcat_deg"] * values["clp_Prot"]
        assert flux("clp_proteolysis", 1e4 * km) == pytest.approx(
            saturated, rel=1e-3
        )
        # Ten times the protein: proteolysis is flat, dilution is tenfold.
        assert flux("clp_dilution", 10 * km) == pytest.approx(
            10 * flux("clp_dilution", km), rel=1e-12
        )
        assert flux("clp_proteolysis", 10 * km) < 2.0 * flux("clp_proteolysis", km)

    def test_the_half_life_conversion_is_written_where_it_is_needed(self) -> None:
        # Papers report half-lives in minutes; the motif wants 1/s. Reading
        # one into the other drops a factor of ln 2 -- a 30% error that
        # looks like a plausible answer, so the conversion is stated on the
        # parameter that needs it rather than in a docstring nobody reads
        # at resolution time.
        d_m = next(p for p in MRNA_DEGRADATION.parameters if p.name == "d_m")
        assert "ln(2)" in d_m.description
        # The default is a placeholder, not a measurement -- but it should
        # at least be a plausible one: a few minutes of message half-life.
        half_life_minutes = math.log(2.0) / d_m.default / 60.0
        assert 0.5 < half_life_minutes < 30.0


class TestThePromotersAgree:
    def test_repression_and_activation_are_the_same_term_inverted(self) -> None:
        # Both promoters use one K and one n and differ only in which
        # concentration sits in the numerator. Written independently they
        # drift; asserted together they cannot.
        repressed = REPRESSED_PROMOTER.reactions[0].rate_law
        activated = ACTIVATED_PROMOTER.reactions[0].rate_law
        assert repressed.endswith("{K}^{n} / ({K}^{n} + {R}^{n})")
        assert activated.endswith("{A}^{n} / ({K}^{n} + {A}^{n})")
        assert repressed.startswith("{k_tx} * {G} * ")
        assert activated.startswith("{k_tx} * {G} * ")

    def test_the_constitutive_promoter_is_first_order_in_the_gene(self) -> None:
        # No Hill factor, no lumped rate: the whole law is one rate
        # constant times one species.
        assert CONSTITUTIVE_PROMOTER.reactions[0].rate_law == "{k_tx} * {G}"
        assert [p.name for p in CONSTITUTIVE_PROMOTER.parameters] == ["k_tx"]
