"""
enzyme_catalog.py

What does this enzyme actually report? Asked BEFORE the first query.

WHY THIS EXISTS
---------------
The owner's assessment of Terrium was that it was not fixing a problem.
Using it as a student does shows the shape of that. Measured through the
real resolver on the LDH fixture:

    substrate="lactate"    -> found, 10.73
    substrate="L-lactate"  -> found=False

BRENDA's label is `(S)-lactate`. "lactate" matches as a substring, and a
perfectly reasonable synonym does not. ADR 0118 made the MISS name the
labels that exist, which helps -- but only after a student has already
failed, and only for the substrate. They still have to guess the organism,
and guess which of Km, Ki and kcat the enzyme even has.

So the first query is a guess, and a wrong guess is indistinguishable from
"the literature has nothing". That is the friction. A tool whose value is
finding literature values should not make finding out what exists the
user's problem.

This is the other half of ADR 0116's idea. That one hands you the next
command after a refusal; this one means the first command need not be a
refusal.

WHAT IT IS NOT
--------------
Not a search, not a recommendation, not a ranking. It reports what is on the
page, per quantity, and says which quantities have no table at all. Nothing
here decides what a reader should ask for -- that is the judgement the whole
project refuses to make on their behalf.

ONE FETCH
---------
The three tables live on ONE BRENDA page, so a catalog costs the same single
request a single lookup does. `html_provider` is called once and the result
parsed three times. Jeske asked that tools be gentle with DSMZ's servers,
and a discovery command that hit them three times to answer one question
would be a poor way to honour that.
"""
from __future__ import annotations

from typing import Callable

from pydantic import BaseModel

from brenda_client import (
    KI_TABLE_LABEL,
    KM_TABLE_LABEL,
    TURNOVER_TABLE_LABEL,
    has_data_table,
    parse_brenda_km_html,
)

#: The quantities a reader can ask `resolve` for, and the table each lives
#: in. Taken from the same mapping the resolver dispatches on
#: (`fallback_logic.QUANTITY_TABLE_LABELS`) rather than restated -- two
#: tables kept equal by hand diverge, and this repository has the scars.
QUANTITIES: dict[str, str] = {
    "km": KM_TABLE_LABEL,
    "ki": KI_TABLE_LABEL,
    "kcat": TURNOVER_TABLE_LABEL,
}


class QuantityInventory(BaseModel):
    """What one BRENDA table holds for this enzyme."""

    quantity: str
    table_label: str

    #: Whether the page carries this table AT ALL.
    #:
    #: Three states collapse to two without it. `substrates == []` would
    #: mean both "BRENDA has no Ki table for this enzyme" and "the table is
    #: there and we could not read it", and ADR 0120 is what happens when
    #: that distinction is missing: substrates from the Km table were
    #: reported as an answer about Ki.
    reported: bool

    substrates: list[str] = []
    organisms: list[str] = []
    #: Rows in the table, so a reader can see where the data is thick and
    #: where a single paper is carrying the whole quantity.
    rows: int = 0

    @property
    def is_usable(self) -> bool:
        """A POSITIVE test: the table exists AND has something in it.

        `reported` alone would call an empty table usable. Same reasoning
        as `SelectionTie.is_tied` and `VariantVerdict.is_wild_type`.
        """
        return self.reported and self.rows > 0


class EnzymeCatalog(BaseModel):
    """Everything one BRENDA page says is available, before you ask for it."""

    ec_number: str
    quantities: list[QuantityInventory] = []

    @property
    def organisms(self) -> list[str]:
        """Every organism named anywhere on the page."""
        seen: set[str] = set()
        for inventory in self.quantities:
            seen.update(inventory.organisms)
        return sorted(seen)

    @property
    def usable(self) -> list[str]:
        return [q.quantity for q in self.quantities if q.is_usable]

    def summary(self) -> str:
        """What a reader needs to type a query that will work.

        Written here rather than in the CLI so the terminal, the script and
        any future surface say the same thing. Two renderers of one fact
        drift, which is ADR 0003.
        """
        if not self.usable:
            return (
                f"BRENDA's page for EC {self.ec_number} reports none of "
                f"{', '.join(QUANTITIES)} — no kinetic table on it carries a "
                "row. That is a fact about this enzyme's coverage, not about "
                "the question you asked."
            )

        lines = [f"EC {self.ec_number} — what BRENDA reports:"]
        for inventory in self.quantities:
            if not inventory.is_usable:
                lines.append(
                    f"  {inventory.quantity:5} no {inventory.table_label!r} "
                    "table on this page"
                )
                continue
            lines.append(
                f"  {inventory.quantity:5} {inventory.rows} row(s); "
                f"substrates: {', '.join(inventory.substrates)}"
            )
        lines.append(
            "  organisms: " + ", ".join(self.organisms)
            if self.organisms
            else "  organisms: none named"
        )
        lines.append(
            "These are BRENDA's own labels. Use them exactly — Terrium does "
            "not substitute a similar name, because a similar name can be a "
            "different molecule."
        )
        return "\n".join(lines)


def catalog(
    ec_number: str,
    html_provider: Callable[[str], str],
) -> EnzymeCatalog:
    """Read one BRENDA page and report what each kinetic table holds.

    `html_provider` is called ONCE. The three tables are on the same page,
    so three requests to answer one question would be gratuitous load on
    DSMZ's servers -- the thing Jeske's bulk-download recommendation was
    about.
    """
    html = html_provider(ec_number)

    inventories: list[QuantityInventory] = []
    for quantity, label in QUANTITIES.items():
        if not has_data_table(html, label):
            # NOT an empty inventory. ADR 0120: the parser falls back to
            # scanning the whole page when the label is absent, so parsing
            # anyway would report another table's contents under this
            # quantity's name.
            inventories.append(
                QuantityInventory(quantity=quantity, table_label=label, reported=False)
            )
            continue

        entries = parse_brenda_km_html(
            html,
            ec_number,
            target_substrates=[],
            target_organism=None,
            require_substrate_match=False,
            table_label=label,
        )
        inventories.append(
            QuantityInventory(
                quantity=quantity,
                table_label=label,
                reported=True,
                substrates=sorted(
                    {(getattr(e, "substrate", None) or "").strip() for e in entries}
                    - {""}
                ),
                organisms=sorted(
                    {(getattr(e, "organism", None) or "").strip() for e in entries}
                    - {""}
                ),
                rows=len(entries),
            )
        )

    return EnzymeCatalog(ec_number=ec_number, quantities=inventories)
