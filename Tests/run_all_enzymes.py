"""
run_all_enzymes.py

Runs the full dynamic pipeline (KEGG substrate resolution + PubChem
synonym expansion + UniProt accession resolution + BRENDA fetch/parse)
against live APIs for any EC number you pass in. There is no hardcoded
enzyme registry anymore - brenda_client.fetch_and_parse_brenda_km()
resolves everything for any EC number on the fly, trying three tiers in
order: strict KEGG substrate match -> PubChem-synonym-expanded match ->
unfiltered fallback (flagged substrate_verified=False) if even that
finds nothing.

Usage:
    python3 run_all_enzymes.py                          # runs a small default demo set
    python3 run_all_enzymes.py 1.1.1.27 3.1.1.7          # runs specific EC numbers
    python3 run_all_enzymes.py 1.1.1.1                   # try any enzyme, even ones
                                                          # never touched in this project
"""

import sys
import time

from brenda_client import fetch_and_parse_brenda_km
import enzyme_lookup
from fallback_logic import resolve_kinetic_value

# Just a demo list for convenience when no EC numbers are given on the
# command line - not a registry anything else in the app depends on.
DEFAULT_DEMO_ECS = ["1.1.1.27", "3.1.1.7", "2.7.1.1", "3.4.21.4", "3.4.21.1"]

ec_numbers = sys.argv[1:] or DEFAULT_DEMO_ECS

print(f"{'EC':<12} {'Total':>6} {'Flagged':>8} {'Unverified':>11}  Notes")
print("(also prints 'table-scoped' count per enzyme: how many results were")
print(" confirmed to come from BRENDA's actual KM Values table, structurally,")
print(" vs a whole-page fallback scan)")
print("-" * 90)

for ec in ec_numbers:
    try:
        kegg_text = enzyme_lookup.fetch_kegg_enzyme_text(ec)
        substrates = enzyme_lookup.parse_kegg_substrates(kegg_text)
    except Exception as exc:  # noqa: BLE001
        print(f"{ec:<12} {'ERR':>6} {'':>8} {'':>11}  KEGG lookup failed: {exc}")
        continue

    kegg_had_no_substrates = not substrates
    # Peptidases (EC 3.4.x.x) have no KEGG SUBSTRATE field at all - KEGG
    # models them via gene orthologs and cleavage-specificity comments,
    # not compound lists, since they act on proteins rather than named
    # small molecules (confirmed live for trypsin/chymotrypsin). That's
    # not a failure to work around by skipping - it just means name-based
    # matching can't succeed, so fetch_and_parse_brenda_km (passed the
    # empty list explicitly, avoiding a duplicate KEGG fetch) falls
    # straight through to the unfiltered/flagged fallback tier and
    # surfaces the real BRENDA data marked substrate_verified=False,
    # instead of the pipeline giving up before even trying BRENDA.

    try:
        entries = fetch_and_parse_brenda_km(ec, target_substrates=substrates)
    except Exception as exc:  # noqa: BLE001
        print(f"{ec:<12} {'ERR':>6} {'':>8} {'':>11}  BRENDA fetch/parse failed: {exc}")
        continue

    cross_species_result = None
    if not entries:
        # No human data anywhere on the page, even in the unfiltered
        # fallback tier - before giving up, try fallback_logic's
        # cross-species tier (any organism, flagged as such) per KEGG
        # substrate, and keep the best (lowest Km) hit across substrates.
        # This is real BRENDA data, just not from a human study - it must
        # never be presented as if it were human data.
        candidates = []
        for sub in substrates:
            try:
                result = resolve_kinetic_value(
                    ec, "Homo sapiens", sub, search_literature=False
                )
            except Exception:  # noqa: BLE001
                continue
            if result.found and result.source == "brenda_cross_species":
                candidates.append((sub, result))
        if candidates:
            cross_species_result = min(candidates, key=lambda pair: pair[1].value)

    total = len(entries)
    flagged = sum(1 for e in entries if e.flagged)
    unverified = sum(1 for e in entries if not e.substrate_verified)
    not_table_scoped = sum(1 for e in entries if not e.table_scoped)
    note = ""
    if total == 0 and cross_species_result:
        sub, result = cross_species_result
        note = (
            "!! ZERO human-organism results in BRENDA's KM Values table - "
            "showing lowest cross-species (non-human) Km instead, flagged"
        )
        print(f"{ec:<12} {total:>6} {flagged:>8} {unverified:>11}  {note}")
        print(f"             KEGG substrates used: {substrates}")
        print(
            f"             [CROSS-SPECIES, NOT HUMAN] {result.value} {result.unit} "
            f"({sub}, organism={result.organism}) source={result.source}"
        )
        time.sleep(1)
        continue
    if total == 0:
        note = "!! ZERO RESULTS even after synonym expansion, unfiltered fallback, and cross-species search - check manually"
    elif kegg_had_no_substrates:
        note = (
            "!! KEGG has no SUBSTRATE field for this EC (peptidase - modeled "
            "via gene orthologs, not compounds) - every result below is "
            "unverified BRENDA data by necessity, not a matching failure"
        )
    elif unverified == total:
        note = "!! all results came from the UNVERIFIED fallback tier - substrate match failed entirely"
    elif not_table_scoped == total:
        note = "!! could not locate the KM Values table container at all - whole-page fallback used"
    elif flagged == total:
        note = "!! every result flagged - investigate before trusting this enzyme"

    print(f"{ec:<12} {total:>6} {flagged:>8} {unverified:>11}  {note}")
    print(f"             KEGG substrates used: {substrates}")
    print(
        f"             table-scoped (confirmed from the real KM Values table): "
        f"{total - not_table_scoped}/{total}"
    )

    if entries:
        verified_entries = [e for e in entries if e.substrate_verified]
        classic = [e for e in verified_entries if e.substrate_type == "classic"]
        reporter = [e for e in verified_entries if e.substrate_type == "engineered_reporter"]

        if classic:
            cheapest_classic = min(classic, key=lambda e: e.km_value)
            print(
                f"             lowest Km (classic, verified): {cheapest_classic.km_value} "
                f"{cheapest_classic.unit} ({cheapest_classic.substrate}, "
                f"uniprot={cheapest_classic.uniprot})"
            )
        elif not reporter and unverified:
            print("             lowest Km (classic, verified): none - only unverified results found")
        elif not reporter:
            print("             lowest Km (classic, verified): none")

        if reporter:
            cheapest_reporter = min(reporter, key=lambda e: e.km_value)
            print(
                f"             lowest Km (engineered/reporter, informational only): "
                f"{cheapest_reporter.km_value} {cheapest_reporter.unit} "
                f"({cheapest_reporter.substrate})"
            )

        if unverified:
            unverified_entries = [e for e in entries if not e.substrate_verified]
            cheapest_unverified = min(unverified_entries, key=lambda e: e.km_value)
            print(
                f"             lowest Km (UNVERIFIED, substrate match failed): "
                f"{cheapest_unverified.km_value} {cheapest_unverified.unit} "
                f"({cheapest_unverified.substrate})"
            )

        flagged_rows = [e for e in entries if e.flagged]
        for f in flagged_rows:
            print(f"             [FLAGGED] {f.km_value} {f.unit} {f.substrate}: {f.flag_reason}")

    # be polite to BRENDA/KEGG/PubChem/UniProt servers between requests
    time.sleep(1)

print("-" * 90)
print("'Unverified' results came from the last-resort fallback: KEGG's")
print("substrate name (and its PubChem synonyms) matched nothing in BRENDA's")
print("text, so every human numeric-Km row was returned unfiltered instead")
print("of nothing. Those rows may include inhibitors, not just the real")
print("substrate - review before trusting them the way verified rows can be.")
