"""`caterva bind`: the measured binding free energy a simulation is held to.

    caterva bind --ec 1.1.1.27 --organism human --list
    caterva bind --ec 1.1.1.27 --organism human --inhibitor gossypol
    caterva bind --ec 1.1.1.27 --organism human --inhibitor gossypol --computed "-7.9±0.4"

Every Ki BRENDA records for the inhibitor, each turned into ΔG°bind =
RT ln(Ki / 1 M) at its own assay temperature, with the inhibition mode, the
molecule it was measured against and the enzyme construct kept beside it.
The rows that can validate the simulated state (--state free: inhibitor
with apo enzyme; ternary: with the enzyme-substrate complex) form a band;
a computed ΔG (FEP, TI, MM/PBSA, in kcal/mol unless --unit kj) is judged
against it at 2σ, and the report says how wide the literature's own
disagreement is before it says anything about agreement.

--html reads a saved BRENDA page instead of the network (tests use the
recorded LDH page).

Exit codes: 0 a target was built (and, with --computed, agrees), 4 the
computed value disagrees, 3 refused and said why (no Ki rows, none fit the
state), 2 malformed question, 1 a crash.

The parser (`build_parser`), the page read (`read_page`), the survey's
targets (`survey_targets`), the compound list (`compound_names`) and the
judgement (`assess`, rendered by `render`) are functions of their own so
that Caterva Studio (caterva/studio/adapters/bind.py) reads the same
objects this command prints from: the band's edges unrounded, the
temperature the Ki fold was judged at, the rows each with its exclusion.
`report` is `render(assess(...))`, and every byte this command prints is
what it printed before they were separated.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from caterva.bind.core import (
    KJ_PER_KCAL, MODE_MEANING, Measurement, Target, Verdict, judge, measurement, parse_computed,
    target,
)

EXIT_OK, EXIT_CRASH, EXIT_USAGE, EXIT_REFUSED, EXIT_DISAGREES = 0, 1, 2, 3, 4

COMMON = {"human": "Homo sapiens", "mouse": "Mus musculus", "rat": "Rattus norvegicus",
          "rabbit": "Oryctolagus cuniculus", "yeast": "Saccharomyces cerevisiae",
          "e. coli": "Escherichia coli", "ecoli": "Escherichia coli"}


def _rows(html: str, ec: str, organism: str, inhibitor: Optional[str]) -> List[Measurement]:
    from caterva.checkout import literature_module
    brenda = literature_module("brenda_client")
    prep = literature_module("enzyme_preparation")
    entries = brenda.parse_brenda_ki_html(
        html, ec, [inhibitor] if inhibitor else [], organism,
        require_substrate_match=bool(inhibitor),
    )
    out = []
    for e in entries:
        if inhibitor and e.substrate.lower() != inhibitor.lower():
            # A substring hit ("NAD" in "NADH") is not the molecule asked for.
            continue
        compound = inhibitor if inhibitor else e.substrate
        out.append(measurement(
            e.km_value, compound, e.organism, e.reference_id, e.conditions,
            e.assay_ph, e.assay_temperature_c, prep.classify(e.conditions).status,
        ))
    return out


def compound_names(html: str, ec: str, organism: str) -> List[str]:
    """Every compound with a Ki row for this enzyme and organism (--list)."""
    return sorted({m.compound for m in _rows(html, ec, organism, None)
                   if m.compound != "unknown compound"}, key=str.lower)


_compound_names = compound_names


def organism_of(text: str) -> str:
    """The organism --organism names: a common name read as its species."""
    return COMMON.get(text.strip().lower(), text.strip())


def read_page(ec: str, html: Optional[Path] = None) -> str:
    """The BRENDA page for `ec`: the saved file --html names, else fetched.

    Raises whatever reading or fetching raised (network, missing file,
    missing literature layer); `main` reports it as a refusal."""
    if html:
        return html.read_text(encoding="utf-8")
    from caterva.checkout import literature_module
    return literature_module("brenda_client").fetch_brenda_html(ec)


def _fmt_row(m: Measurement) -> str:
    dg = (f"{m.dg_kcal[0]:6.2f}" if len(m.dg_kcal) == 1
          else f"{m.dg_lo:.2f}..{m.dg_hi:.2f}")
    t = f"{m.temperature_c:g} °C" if m.temperature_c is not None else "T not stated"
    ph = f"pH {m.ph:g}" if m.ph is not None else "pH not stated"
    mode = m.mode + (f" vs {m.versus}" if m.versus else "")
    iso = f", {m.isoform}" if m.isoform else ""
    prep = f", {m.preparation} enzyme" if m.preparation not in (None, "unstated", "absent", "native") else ""
    return (f"  Ki {m.ki_mM:g} mM  ->  ΔG {dg} kcal/mol   [{t}, {ph}, {mode}{iso}{prep}]"
            f"  BRENDA ref {m.reference or '?'}")


#: What makes a Ki target a sound benchmark: independent laboratories, a
#: stated mode (so the binding event is known) and a stated temperature.
BENCHMARK_RULE = "at least 2 publications, inhibition mode stated, assay temperature stated"


@dataclass
class SurveyTarget:
    """One (compound, organism, isoform) of the survey: its Target and why it
    cannot benchmark, if it cannot (empty when it can)."""
    compound: str
    organism: str
    isoform: Optional[str]
    rows: List[Measurement]
    target: Target
    why_not: List[str]


def survey_targets(html: str, ec: str, organism: str, state: str) -> List[SurveyTarget]:
    """One SurveyTarget per (compound, organism, isoform), unrounded, in the
    order `survey` lists them."""
    groups: dict = {}
    for m in _rows(html, ec, organism, None):
        if m.compound == "unknown compound":
            continue
        # Species and isoforms are different proteins: never one band.
        groups.setdefault((m.compound, m.organism, m.isoform), []).append(m)
    out = []
    for (compound, species, isoform), ms in sorted(groups.items(),
                                                   key=lambda kv: (kv[0][0].lower(), kv[0][1], kv[0][2] or "")):
        t = target(ms, state, isoform)
        missing = []
        if len(t.references) < 2:
            missing.append("one publication")
        if any(m.mode == "unstated" for m in t.used):
            missing.append("mode not stated")
        if any(m.temperature_c is None for m in t.used):
            missing.append("temperature not stated")
        if t.lo is None:
            missing = [f"no row measured the {state} state"]
        out.append(SurveyTarget(compound, species, isoform, ms, t, missing))
    out.sort(key=lambda r: (bool(r.why_not), r.target.lo is None, r.compound.lower()))
    return out


def survey(html: str, ec: str, organism: str, state: str) -> List[dict]:
    """One row per (compound, isoform): its band and whether it can benchmark."""
    return [{
        "compound": r.compound, "organism": r.organism, "isoform": r.isoform, "rows": len(r.rows),
        "used": len(r.target.used), "references": r.target.references,
        "band_kcal": None if r.target.lo is None else [round(r.target.lo, 2), round(r.target.hi, 2)],
        "benchmark": not r.why_not, "why_not": r.why_not,
    } for r in survey_targets(html, ec, organism, state)]


def render_survey(rows: List[dict], ec: str, organism: str, state: str) -> str:
    good = [r for r in rows if r["benchmark"]]
    lines = [f"Ki targets for EC {ec} in {organism or 'every organism'}, {state} state: {len(rows)} compound/isoform pair(s), "
             f"{len(good)} usable as a benchmark ({BENCHMARK_RULE}).", ""]
    for r in rows:
        tag = ", ".join(x for x in (None if organism else r["organism"], r["isoform"]) if x)
        name = r["compound"] + (f" [{tag}]" if tag else "")
        name = name if len(name) <= 48 else name[:45] + "..."
        band = (f"{r['band_kcal'][0]:6.2f} to {r['band_kcal'][1]:6.2f} kcal/mol"
                if r["band_kcal"] else "            no target")
        mark = "BENCHMARK" if r["benchmark"] else "not yet: " + ", ".join(r["why_not"])
        lines.append(f"  {name:<48} {band}  {r['used']}/{r['rows']} row(s), "
                     f"{len(r['references'])} ref(s)  {mark}")
    if not good:
        lines += ["", "None qualifies: a force field validated on this enzyme's published Ki values "
                  "would be validated against single, partly described measurements."]
    return "\n".join(lines)


@dataclass
class Assessment:
    """What one `--inhibitor` question found, before it is rendered.

    `computed` is the computed value and its σ in kcal/mol (converted from
    kJ/mol when --unit kj), `temperature_c` the temperature the Ki fold was
    judged at (the mean stated assay temperature of the rows used, else
    25 °C), `verdict` the judgement; all three None without --computed or
    when no row fits the state."""
    state: str
    target: Target
    computed: Optional[Tuple[float, float]] = None
    temperature_c: Optional[float] = None
    verdict: Optional[Verdict] = None


def assess(rows: List[Measurement], state: str, computed: Optional[tuple], unit: str,
           isoform: Optional[str] = None) -> Assessment:
    """The band for `state` and, with a computed value, the verdict on it."""
    t = target(rows, state, isoform)
    out = Assessment(state, t)
    if t.lo is None or computed is None:
        return out
    value, err = computed
    if unit == "kj":
        value, err = value / KJ_PER_KCAL, err / KJ_PER_KCAL
    temps = [m.temperature_c for m in t.used if m.temperature_c is not None]
    temperature = (sum(temps) / len(temps)) if temps else 25.0
    out.computed = (value, err)
    out.temperature_c = temperature
    out.verdict = judge(t, value, err, temperature_c=temperature)
    return out


def report(rows: List[Measurement], state: str, computed: Optional[tuple], unit: str,
           isoform: Optional[str] = None) -> tuple[str, int, dict]:
    return render(assess(rows, state, computed, unit, isoform))


def render(a: Assessment) -> tuple[str, int, dict]:
    """(the text --inhibitor prints, the exit code, the --json payload)."""
    t, state = a.target, a.state
    lines = [f"{t.compound} binding {t.organism}, simulated state: {state} "
             f"({'inhibitor + apo enzyme' if state == 'free' else 'inhibitor + enzyme-substrate complex'})", ""]
    lines.append(f"MEASURED ({len(t.used)} row(s) fit this state)")
    lines += [_fmt_row(m) for m in t.used] or ["  none"]
    if t.excluded:
        lines += ["", f"NOT COMPARABLE ({len(t.excluded)} row(s), shown so the exclusion can be argued with)"]
        for m in t.excluded:
            lines.append(_fmt_row(m))
            lines.append(f"      {m.excluded}")
    payload = {"compound": t.compound, "organism": t.organism, "state": state,
               "used": [asdict(m) for m in t.used], "excluded": [asdict(m) for m in t.excluded],
               "band_kcal": None if t.lo is None else [t.lo, t.hi], "caveats": t.caveats}
    if t.lo is None:
        lines += ["", "REFUSED: no measurement fits the simulated state, so there is nothing to validate against."]
        if t.excluded:
            other = "ternary" if state == "free" else "free"
            lines.append(f"  Try --state {other} if that is what the simulation modelled.")
        return "\n".join(lines), EXIT_REFUSED, payload

    lines += ["", f"TARGET  ΔG°bind {t.lo:.2f} to {t.hi:.2f} kcal/mol "
              f"(band {t.width:.2f} kcal/mol wide, {len(t.references)} publication(s), c° = 1 M)"]
    if t.width and t.width > 0:
        sources = []
        if len(t.references) > 1:
            sources.append("different laboratories")
        if len({m.ki_mM for m in t.used}) > 1:
            sources.append("different measured Ki")
        if any(m.temperature_c is None for m in t.used):
            sources.append("unstated assay temperature")
        lines.append(f"  A computed value cannot be judged more finely than this {t.width:.2f} kcal/mol band "
                     f"({', '.join(sources)}).")
    for c in t.caveats:
        lines.append(f"  caveat: {c}")

    code = EXIT_OK
    if a.verdict is not None and a.computed is not None:
        value, err = a.computed
        v = a.verdict
        lines += ["", f"VERDICT  {v.word.upper()}: computed {value:.2f} ± {err:.2f} kcal/mol. {v.detail}."]
        if err == 0.0:
            lines.append("  No uncertainty was given for the computed value; a single number has none only "
                         "if it was never repeated. Pass --computed \"ΔG±σ\" from independent replicas.")
        if v.word == "agrees" and len(t.references) < 2:
            lines.append("  Agreement with one publication is consistency, not validation.")
        payload["verdict"] = asdict(v)
        payload["computed_kcal"] = [value, err]
        code = EXIT_OK if v.word == "agrees" else EXIT_DISAGREES
    return "\n".join(lines), code, payload


def render_list(names: List[str], ec: str, organism: str) -> str:
    """What --list prints for the compounds it found."""
    return "\n".join([f"Compounds with a recorded Ki for EC {ec} in {organism}:"]
                     + [f"  {n}" for n in names])


def no_rows_for(inhibitor: str, ec: str, organism: str, names: List[str]) -> str:
    """The refusal --inhibitor prints to stderr when the compound has no Ki
    row, naming the compounds that do."""
    lines = [f"No Ki for {inhibitor!r} with EC {ec} in {organism}."]
    if names:
        lines.append("Compounds that do have one: " + "; ".join(names))
    return "\n".join(lines)


def build_parser(prog: str = "caterva bind") -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=prog, description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ec", required=True, help="EC number, e.g. 1.1.1.27")
    p.add_argument("--organism", default="Homo sapiens", help="species (common names accepted)")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--inhibitor", help="the compound, exactly as BRENDA names it (see --list)")
    g.add_argument("--list", action="store_true", help="list compounds with a Ki for this enzyme and organism")
    g.add_argument("--survey", action="store_true",
                   help="every inhibitor's target, and which are sound benchmarks for a free-energy method")
    p.add_argument("--state", choices=("free", "ternary"), default="free",
                   help="what the simulation modelled: inhibitor with apo enzyme (free) or with E·S (ternary)")
    p.add_argument("--isoform", help="the isoform simulated (e.g. LDH-A); rows naming another are excluded")
    p.add_argument("--computed", help='your ΔG, e.g. "-7.9±0.4" (kcal/mol unless --unit kj)')
    p.add_argument("--unit", choices=("kcal", "kj"), default="kcal")
    p.add_argument("--html", type=Path, help="a saved BRENDA page, instead of fetching one")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    return p


def main(argv: Optional[Sequence[str]] = None, prog: str = "caterva bind") -> int:
    p = build_parser(prog)
    # Binding free energies are negative, and argparse reads "-7.9" as a flag.
    args = list(sys.argv[1:] if argv is None else argv)
    for i in range(len(args) - 1):
        if args[i] == "--computed":
            args[i:i + 2] = [f"--computed={args[i + 1]}"]
            break
    try:
        a = p.parse_args(args)
    except SystemExit as e:
        return EXIT_USAGE if e.code else EXIT_OK
    organism = organism_of(a.organism)
    computed = None
    if a.computed:
        try:
            computed = parse_computed(a.computed)
        except ValueError as e:
            print(f"caterva bind: {e}", file=sys.stderr)
            return EXIT_USAGE

    try:
        html = read_page(a.ec, a.html)
    except Exception as e:  # network, missing file, missing literature layer
        print(f"caterva bind: could not read BRENDA for {a.ec}: {e}", file=sys.stderr)
        return EXIT_REFUSED

    if a.survey:
        rows = survey(html, a.ec, organism, a.state)
        if not rows:
            print(f"No Ki rows for EC {a.ec} in {organism}.")
            return EXIT_REFUSED
        if a.json:
            print(json.dumps(rows, indent=2, default=str))
        else:
            print(render_survey(rows, a.ec, organism, a.state))
        return EXIT_OK

    if a.list:
        names = compound_names(html, a.ec, organism)
        if not names:
            print(f"No Ki rows for EC {a.ec} in {organism}.")
            return EXIT_REFUSED
        print(render_list(names, a.ec, organism))
        return EXIT_OK

    rows = _rows(html, a.ec, organism, a.inhibitor)
    if not rows:
        print(no_rows_for(a.inhibitor, a.ec, organism, compound_names(html, a.ec, organism)),
              file=sys.stderr)
        return EXIT_REFUSED

    text, code, payload = report(rows, a.state, computed, a.unit, a.isoform)
    print(json.dumps(payload, indent=2, default=str) if a.json else text)
    return code


if __name__ == "__main__":
    sys.exit(main())
