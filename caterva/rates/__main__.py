"""`caterva rates`: fit your own initial rates, and hold them against the literature.

    caterva rates examples/rates/puromycin.csv --sigma-from residuals --group state
    caterva rates my_rates.csv --sigma-from replicates --ec 1.1.1.27 --organism human \\
        --substrate pyruvate --inhibitor oxamate
    caterva rates my_rates.csv --export csv > constants.csv

The measurement every enzyme lab makes: initial rates at several substrate
concentrations, and often at several inhibitor concentrations. This fits them
by weighted nonlinear least squares, reports each constant with a
profile-likelihood interval, says what the data do and do not determine,
tests which inhibition mechanisms the data rule out, tests which constants
differ between groups, and compares the fitted Km and Ki with the values
BRENDA cites for the same enzyme, organism and compound.

The package's modules, in the order the run uses them: table.py (the CSV and
its units), uncertainty.py (where sigma comes from), models.py (the rate
laws), fit.py (fitting and intervals), determine.py (what the data
determine), discriminate.py (mechanism tests and lack of fit), groups.py
(differences between groups), literature.py (the cited constants),
linearize.py (the straight-line plots, for teaching), analysis.py (one run)
and report.py (every output).

EXIT CODES
----------
    0   everything asked for was produced
    2   the question was not well formed: a missing column, a cell that is
        not a number, an unknown flag, a flag combination with no meaning
    3   refused, and said why: no uncertainty given, a unit that cannot be
        read, too few conditions for the law, a group with one rate, or a
        literature comparison that could not be made -- the literature layer
        is absent, or a column's unit does not convert to the cited one (the
        report is still printed). A search that ran and found no row is an
        answer, not a refusal, as in compose.
    1   a crash
"""
from __future__ import annotations

import argparse
import sys
from typing import Any, Optional, Sequence

EXIT_OK, EXIT_CRASH, EXIT_USAGE, EXIT_REFUSED = 0, 1, 2, 3
EXPORTS = ("csv", "curves", "methods")


class _Once(argparse.Action):
    """An option that may be given once. argparse keeps the last of two, so
    `--sigma-from residuals --sigma-from replicates` would otherwise fit with
    replicates and say nothing about the residuals asked for first; one
    source of uncertainty is the rule, and two named is a malformed question."""

    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest, None) is not None:
            parser.error(f"{option_string} was given twice ({getattr(namespace, self.dest)} and "
                         f"{values}); give it once")
        setattr(namespace, self.dest, values)


def build_parser(prog: str = "caterva rates") -> argparse.ArgumentParser:
    from caterva.rates.analysis import MODEL_CHOICES

    p = argparse.ArgumentParser(
        prog=prog,
        description=("Fit initial rates measured at several substrate (and inhibitor) "
                     "concentrations: every constant with its profile interval, what the data "
                     "determine, which mechanisms they rule out, and how the constants compare "
                     "with the cited ones."),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "The file is a CSV whose header names each column and its unit, e.g.\n"
            "  substrate (mM), rate (uM/min), sigma (uM/min), inhibitor (uM), group\n"
            "Lines starting with # are comments. Rows with identical conditions are replicates.\n"
            "\nExamples:\n"
            f"  {prog} examples/rates/puromycin.csv --sigma-from residuals --group state\n"
            f"  {prog} rates.csv --sigma-from replicates --error-model proportional\n"
            f"  {prog} rates.csv --model competitive --show-linearizations\n"
            f"  {prog} rates.csv --ec 1.1.1.27 --organism human --substrate pyruvate "
            "--inhibitor oxamate\n"
            f"  {prog} rates.csv --export csv > constants.csv\n"
            "\nExit codes: 0 produced everything asked for, 2 the question was not well formed, "
            "3 something refused and said why (the report is still printed when there is one), "
            "1 a crash.\n"),
    )
    p.add_argument("file", help="the CSV of initial rates")
    columns = p.add_argument_group("columns (found by the name before the unit's parenthesis)")
    columns.add_argument("--substrate-column", metavar="NAME",
                         help="the substrate concentration column (default: substrate)")
    columns.add_argument("--rate-column", metavar="NAME",
                         help="the initial rate column (default: rate)")
    columns.add_argument("--sigma-column", metavar="NAME",
                         help="a per-row standard deviation of the rate, in the rate's unit "
                              "(default: sigma, used when present)")
    columns.add_argument("--inhibitor-column", metavar="NAME",
                         help="the inhibitor concentration column (default: inhibitor, used when "
                              "present)")
    columns.add_argument("--group", metavar="COLUMN",
                         help="fit each group of rows (wild type and mutant, treated and untreated) "
                              "separately, then test which constants differ between groups")
    errors = p.add_argument_group("uncertainty (exactly one source; none is ever invented)")
    errors.add_argument("--sigma-from", choices=("replicates", "residuals"), action=_Once,
                        help="replicates: pool the spread of rows with identical conditions, its "
                             "degrees of freedom stated; residuals: ordinary least squares with "
                             "sigma from the fit's own scatter, which assumes the law is right "
                             "(what R's nls reports). Without this, a sigma column is required")
    errors.add_argument("--error-model", choices=("constant", "proportional"), action=_Once,
                        help="with --sigma-from replicates: pool the standard deviation "
                             "(constant, the default) or the coefficient of variation "
                             "(proportional, for noise that grows with the rate)")
    fitting = p.add_argument_group("fitting")
    fitting.add_argument("--model", choices=MODEL_CHOICES, default="auto",
                         help="the rate law. auto (the default): with an inhibitor, fit "
                              "competitive, uncompetitive, noncompetitive and mixed and test which "
                              "the data rule out; without, fit Michaelis-Menten and test it "
                              "against substrate inhibition and the Hill law")
    fitting.add_argument("--level", type=float, default=0.95,
                         help="confidence level of the intervals (default 0.95)")
    fitting.add_argument("--significance", type=float, default=0.05,
                         help="p-value below which a law is called ruled out, a convention "
                              "(default 0.05); every p-value is printed")
    fitting.add_argument("--show-linearizations", action="store_true",
                         help="also print the Lineweaver-Burk, Eadie-Hofstee and Hanes-Woolf "
                              "points and the Km and Vmax their straight lines give, beside the "
                              "nonlinear fit, for teaching; they are never the reported estimate")
    lit = p.add_argument_group("literature (reads BRENDA live: needs a network connection)")
    lit.add_argument("--ec", metavar="EC",
                     help="the enzyme's EC number, e.g. 1.1.1.27, to compare the fitted Km and Ki "
                          "with the values BRENDA cites")
    lit.add_argument("--organism",
                     help="the organism, e.g. 'Homo sapiens' or human; required with --ec, "
                          "because kinetic constants are species-specific")
    lit.add_argument("--substrate", metavar="NAME",
                     help="the substrate's name, to look up its Km")
    lit.add_argument("--inhibitor", metavar="NAME",
                     help="the inhibitor's name, to look up its Ki for the mechanism the data "
                          "support (BRENDA files a Ki under the inhibitor)")
    lit.add_argument("--isoform", metavar="NAME",
                     help="the isoform measured, e.g. LDH-A, so a row measured on another "
                          "isoform is not compared as though it were this one")
    out = p.add_argument_group("output")
    out.add_argument("--json", action="store_true",
                     help="print the whole analysis as JSON instead of the report")
    out.add_argument("--export", choices=EXPORTS,
                     help="print one artefact instead of the report: csv (every constant, its "
                          "unit and interval), curves (the fitted curves on a grid for plotting, "
                          "with the measured rates, one row per point, units in the headers), "
                          "methods (a methods paragraph with software versions and references)")
    return p


def _usage_error(parser: argparse.ArgumentParser, message: str) -> int:
    parser.print_usage(sys.stderr)
    print(f"{parser.prog}: error: {message}", file=sys.stderr)
    return EXIT_USAGE


def main(argv: Optional[Sequence[str]] = None, prog: str = "caterva rates",
         resolver: Any = None) -> int:
    """`resolver` replaces the literature layer's resolve_kinetic_value, so the
    tests can read committed BRENDA pages instead of the network."""
    from caterva.rates import report
    from caterva.rates.analysis import Options, Refused, analyse, compare_literature
    from caterva.rates.fit import FitRefused
    from caterva.rates.literature import LiteratureUnavailable
    from caterva.rates.table import TableError, UnitRefused, read_table
    from caterva.rates.uncertainty import NoUncertainty, resolve

    parser = build_parser(prog)
    args = parser.parse_args(argv)
    if not 0.0 < args.level < 1.0:
        return _usage_error(parser, f"--level is a probability between 0 and 1 (0.95, not 95); "
                                    f"got {args.level:g}")
    if not 0.0 < args.significance < 1.0:
        return _usage_error(parser, f"--significance is a probability between 0 and 1; got "
                                    f"{args.significance:g}")
    wants_literature = bool(args.substrate or args.inhibitor or args.isoform)
    if wants_literature and not args.ec:
        return _usage_error(parser, "--substrate, --inhibitor and --isoform name what to look up in "
                                    "the literature, and need --ec to say which enzyme")
    if args.ec and not (args.substrate or args.inhibitor):
        return _usage_error(parser, "--ec compares the fitted constants with cited ones, and needs "
                                    "--substrate (for Km) or --inhibitor (for Ki) to say which")
    if args.ec and not args.organism:
        return _usage_error(parser, "--ec needs --organism: a Km or a Ki is a property of one "
                                    "organism's enzyme, and borrowing another's would compare "
                                    "different proteins")
    if args.json and args.export:
        return _usage_error(parser, "--json and --export each replace the report; give one")

    names = {"substrate": args.substrate_column, "rate": args.rate_column,
             "sigma": args.sigma_column, "inhibitor": args.inhibitor_column}
    try:
        data = read_table(args.file, names=names, group=args.group)
    except TableError as exc:
        print(f"{prog}: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except UnitRefused as exc:
        print(f"{prog}: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    if args.inhibitor and not data.has_inhibitor:
        return _usage_error(parser, "--inhibitor names the inhibitor whose Ki to look up, and the "
                                    "file has no rate measured with an inhibitor")

    try:
        uncertainty = resolve(data, args.sigma_from, args.error_model)
        options = Options(model=args.model, level=args.level, significance=args.significance,
                          linearizations=args.show_linearizations)
        analysis = analyse(data, uncertainty, options)
    except (NoUncertainty, Refused, FitRefused) as exc:
        print(f"{prog}: {exc}", file=sys.stderr)
        return EXIT_REFUSED

    refused = False
    if args.ec:
        from caterva.compose.organisms import normalise_organism

        organism, read_as = normalise_organism(args.organism)
        if read_as:
            analysis.notes.append(read_as)
        try:
            compare_literature(analysis, ec=args.ec.strip(), organism=organism,
                               substrate=args.substrate, inhibitor=args.inhibitor,
                               isoform=args.isoform, resolver=resolver)
        except LiteratureUnavailable as exc:
            analysis.literature = []
            analysis.literature_refused = str(exc)
        except Exception as exc:  # noqa: BLE001 - a failed search is a refusal with a reason, as in compose
            analysis.literature = []
            analysis.literature_refused = f"the literature search failed: {type(exc).__name__}: {exc}"
        # A comparison this command declined is a refusal (exit 3); a
        # resolver that ran and found no row has answered, as in compose.
        refused = analysis.literature_refused is not None or any(
            c.declined for c in analysis.literature)

    if args.json:
        sys.stdout.write(report.to_json(analysis))
    elif args.export == "csv":
        sys.stdout.write(report.parameters_csv(analysis))
    elif args.export == "curves":
        sys.stdout.write(report.curves_csv(analysis))
    elif args.export == "methods":
        sys.stdout.write(report.methods(analysis))
    else:
        sys.stdout.write(report.render(analysis))
    if refused:
        reasons = ([analysis.literature_refused] if analysis.literature_refused else
                   [f"{c.constant}" + (f" [{c.group}]" if c.group else "") + f": {c.refused}"
                    for c in analysis.literature if c.declined])
        print(f"{prog}: a literature comparison was not made: " + "; ".join(reasons),
              file=sys.stderr)
        return EXIT_REFUSED
    return EXIT_OK


def console_main() -> int:
    return main()


if __name__ == "__main__":
    sys.exit(main())
