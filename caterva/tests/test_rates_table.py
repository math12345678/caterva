"""`caterva rates`: reading the table, its units, and where the error bars come from.

The small tables here are written inline to exercise the reader: their
numbers test parsing and refusal, not kinetics, and none is fitted.
"""
from __future__ import annotations

import math

import pytest

from caterva.rates.table import TableError, UnitRefused, read_table, read_unit
from caterva.rates.uncertainty import NoUncertainty, condition_means, pure_error, resolve


def table(text, **kw):
    return read_table("inline.csv", text=text, **kw)


class TestColumnsAndUnits:
    def test_columns_are_found_by_name_and_units_parsed(self):
        data = table("# a comment\nSubstrate (mM), rate (uM/min), sigma (nM/min), inhibitor (uM)\n"
                     "0.1,2.0,50,0\n0.2,3.0,50,1\n")
        assert data.substrate == (0.1, 0.2)
        assert data.inhibitor == (0.0, 1.0)
        # nM/min converted to the rate's uM/min.
        assert data.sigma == pytest.approx((0.05, 0.05))
        assert data.units["substrate"].kind == "concentration"
        assert data.units["rate"].kind == "concentration per time"
        assert data.comments == ("a comment",)
        assert any("converted" in n for n in data.notes)

    def test_flags_name_columns_whose_headers_differ(self):
        data = table("conc (ppm),v (counts/min/min),state\n0.02,76,treated\n",
                     names={"substrate": "conc", "rate": "v"}, group="state")
        assert data.group == ("treated",)
        assert data.units["substrate"].kind == "arbitrary"
        assert not data.units["substrate"].convertible

    @pytest.mark.parametrize("unit, kind", [
        ("counts/min/min", "arbitrary"), ("A340/min", "arbitrary"), ("umol/min/mg", "arbitrary"),
        ("RFU/s", "arbitrary"), ("uM/min", "concentration per time"), ("1/s", "per time"),
        ("mM/s", "concentration per time"),
    ])
    def test_rate_units_that_are_accepted(self, unit, kind):
        assert read_unit("rate", unit, "rate").kind == kind

    def test_a_unit_it_cannot_read_is_refused_naming_the_column(self):
        with pytest.raises(UnitRefused, match="'substrate'.*mMol|mMol.*'substrate'"):
            table("substrate (mMol),rate (uM/min),sigma (uM/min)\n1,2,0.1\n")

    def test_a_misspelled_time_unit_is_not_taken_as_arbitrary(self):
        with pytest.raises(UnitRefused, match="cannot read the unit 'uM/mn'"):
            read_unit("rate", "uM/mn", "rate")

    def test_a_molar_unit_the_parser_cannot_read_is_not_taken_as_arbitrary(self):
        """'uM min^-1' is a molar rate in a form the parser does not take; read
        as arbitrary it would fit, and then refuse the conversions it has."""
        with pytest.raises(UnitRefused, match="as uM/min or uM\\*min\\^-1"):
            read_unit("rate", "uM min^-1", "rate")
        assert read_unit("rate", "uM*min^-1", "rate").kind == "concentration per time"
        # An amount per time is a readout, not a concentration: it stays arbitrary.
        assert read_unit("rate", "nmol/min", "rate").kind == "arbitrary"

    def test_a_column_without_a_unit_is_refused(self):
        with pytest.raises(UnitRefused, match="column 'substrate' has no unit"):
            table("substrate,rate (uM/min)\n1,2\n")

    def test_a_rate_without_time_is_refused(self):
        with pytest.raises(UnitRefused, match="not a rate"):
            read_unit("rate", "mM", "rate")
        with pytest.raises(UnitRefused, match="no time in it"):
            read_unit("rate", "counts", "rate")

    def test_a_concentration_column_in_a_rate_unit_is_refused(self):
        with pytest.raises(UnitRefused, match="not a concentration"):
            read_unit("substrate", "mM/min", "substrate")

    def test_a_sigma_in_another_kind_of_unit_is_refused(self):
        with pytest.raises(UnitRefused, match="column 'sigma' is in 'mM', which is not a rate"):
            table("substrate (mM),rate (uM/min),sigma (mM)\n1,2,0.1\n")

    def test_malformed_tables_are_table_errors(self):
        with pytest.raises(TableError, match="no column called 'substrate'"):
            table("conc (mM),rate (uM/min)\n1,2\n")
        with pytest.raises(TableError, match="not a number"):
            table("substrate (mM),rate (uM/min)\n1,fast\n")
        with pytest.raises(TableError, match="write 0 for no inhibitor"):
            table("substrate (mM),rate (uM/min),inhibitor (uM)\n1,2,\n")
        with pytest.raises(TableError, match="negative"):
            table("substrate (mM),rate (uM/min)\n-1,2\n")
        with pytest.raises(TableError, match="no rows"):
            table("substrate (mM),rate (uM/min)\n")

    def test_a_zero_standard_deviation_is_refused(self):
        with pytest.raises(UnitRefused, match="must be positive"):
            table("substrate (mM),rate (uM/min),sigma (uM/min)\n1,2,0\n")


class TestUncertainty:
    DUPLICATES = ("substrate (mM),rate (uM/min)\n"
                  "1,10\n1,12\n2,20\n2,23\n4,30\n")

    def test_no_source_is_refused_naming_the_three(self):
        data = table(self.DUPLICATES)
        with pytest.raises(NoUncertainty) as info:
            resolve(data, None)
        text = str(info.value)
        assert "sigma (uM/min)" in text and "--sigma-from replicates" in text
        assert "--sigma-from residuals" in text and "will not invent one" in text

    def test_two_sources_are_refused(self):
        data = table("substrate (mM),rate (uM/min),sigma (uM/min)\n1,2,0.1\n2,3,0.1\n")
        with pytest.raises(NoUncertainty, match="Exactly one source"):
            resolve(data, "residuals")

    def test_error_model_without_replicates_is_refused(self):
        with pytest.raises(NoUncertainty, match="needs --sigma-from replicates"):
            resolve(table(self.DUPLICATES), "residuals", "proportional")

    def test_constant_pooling_by_hand(self):
        u = resolve(table(self.DUPLICATES), "replicates")
        # (10-12)^2/2 + (20-23)^2/2 = 2 + 4.5 = 6.5 on 2 degrees of freedom.
        assert u.dof == 2 and u.sets == 2
        assert u.pooled == pytest.approx(math.sqrt(6.5 / 2), rel=1e-12)
        assert set(u.sigma) == {u.pooled}

    def test_proportional_pooling_by_hand(self):
        data = table(self.DUPLICATES)
        u = resolve(data, "replicates", "proportional")
        cv2 = ((10 - 11) ** 2 + (12 - 11) ** 2) / 11 ** 2 + ((20 - 21.5) ** 2 + (23 - 21.5) ** 2) / 21.5 ** 2
        assert u.pooled == pytest.approx(math.sqrt(cv2 / 2), rel=1e-12)
        assert u.sigma[4] == pytest.approx(u.pooled * 30, rel=1e-12)
        assert tuple(condition_means(data)) == (11, 11, 21.5, 21.5, 30)

    def test_replicates_are_required_for_pooling(self):
        with pytest.raises(NoUncertainty, match="measured once"):
            resolve(table("substrate (mM),rate (uM/min)\n1,2\n2,3\n"), "replicates")

    def test_pure_error_by_hand(self):
        data = table(self.DUPLICATES)
        ss, df, conditions = pure_error(data, [1.0] * 5)
        assert (ss, df, conditions) == (6.5, 2, 3)
