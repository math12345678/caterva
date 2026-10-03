#!/usr/bin/env python3
"""One document a student can hand in.

Reads a JSON payload on stdin, writes Markdown on stdout.

    {"title": "...", "question": "...",
     "ec": "1.1.1.27", "organism": "Homo sapiens",
     "parameters": [{"name": "km", "substrate": "lactate", "quantity": "km"}],
     "supplied":   [{"name": "s0", "value": 10, "unit": "mM",
                     "basis": "lab handout"}],
     "vmax": 0.25, "s0": 10}

WHY THIS EXISTS
---------------
Caterva could resolve a literature value, record its provenance, parse the
assay conditions, grade it on Bakker's axes, run an ensemble over values the
evidence cannot rank, export BibTeX, annotate a model, and integrate it.

Nine capabilities, and nothing a person could hand to a teacher. Each one
answered a question nobody asks in isolation; the student's actual job is
"run the simulation and show where the numbers came from", and they were
left to assemble that from a terminal transcript and two export files.

WHAT IT WILL NOT DO
-------------------
It does not resolve anything it was not asked for, and it does not fill a
gap. A parameter that could not be sourced appears in the report as a
refusal with its reason — because a document that silently omits what it
could not find is indistinguishable from one where nobody looked, and the
student cannot defend a gap they cannot see.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "Tests"))
# The repository root too — `lab_report` reaches modules that import
# `caterva.*`. `export_citations.py` shipped in HEAD with only the first of
# these lines and died on its import line (ADR 0107).
sys.path.insert(0, str(REPO_ROOT))

from brenda_client import fetch_brenda_html  # noqa: E402
from enzyme_lookup import EnzymeNameNotResolved, ec_number_for_name  # noqa: E402
from fallback_logic import resolve_kinetic_value  # noqa: E402
from lab_report import DerivedValue, SuppliedValue, build_report  # noqa: E402
from ensemble import ensemble_from_entries  # noqa: E402
from model_ensemble import ensemble_over  # noqa: E402
from spread_consequence import consequence_of  # noqa: E402


def _fail(message: str) -> int:
    print(json.dumps({"ok": False, "error": message}))
    return 1


class ConflictingValue(ValueError):
    """The same quantity arrived twice, with two different numbers."""


class MalformedSuppliedValue(ValueError):
    """A supplied value arrived without a name or without a number."""


def supplied_values(payload: dict) -> list[SuppliedValue]:
    """The student's own numbers, with a lost one refused rather than dropped.

    A NULL VALUE IS A CALLER THAT LOST A NUMBER, NOT A CALLER WITH NOTHING
    TO SAY.

    This was a comprehension filtering on `s.get("value") is not None`, so an
    entry arriving with a null value was silently removed. That is exactly
    what `--s0 10mM` produced: the CLI read it with `Number()`, which gives
    NaN, `JSON.stringify` wrote `null`, this filter deleted it, and the
    document told the student

        the simulation was not run: s0 is missing — yours to choose

    about a number they had chosen. A refusal that blames the user for the
    tool's own data loss is worse than a crash: it looks actionable and it is
    wrong (ADR 0141).

    The CLI is fixed. This stays as the second line, because a name with no
    number is a defect in whoever built the payload, and the only safe thing
    to do with a defect is say so. Skipping it yields a report that is wrong
    about its own inputs while looking complete.
    """
    values: list[SuppliedValue] = []
    for entry in payload.get("supplied") or []:
        name = entry.get("name")
        if name is None:
            raise MalformedSuppliedValue(
                "A supplied value arrived with no name. Caterva cannot put "
                "it in the report, and will not drop it silently."
            )
        if entry.get("value") is None:
            raise MalformedSuppliedValue(
                f"The supplied value {str(name)!r} arrived with no number. "
                "This usually means a unit was not understood upstream — "
                f"check what you passed for --{name}. Caterva will not drop "
                "it and then report it as missing."
            )
        values.append(
            SuppliedValue(
                name=str(name),
                value=float(entry["value"]),
                unit=entry.get("unit"),
                basis=entry.get("basis"),
            )
        )
    return values


def model_inputs(
    resolved: dict,
    quantities: dict[str, str],
    supplied: list[SuppliedValue],
    payload: dict,
) -> dict[str, float]:
    """Every number the model will run at, each taken from exactly ONE place.

    WHY THIS IS A FUNCTION AND NOT THREE `payload.get` CALLS
    -------------------------------------------------------
    Before this, `s0` could arrive twice: as `payload["s0"]`, which is what
    the ensemble ran at, and inside `payload["supplied"]`, which is what the
    Parameters table printed. Nothing compared them. A caller passing 10 in
    one and 5 in the other got a document whose table said 5, whose ensemble
    was computed at 10, and which looked entirely consistent.

    That is this repository's most-repeated defect -- one fact, two copies,
    no check (ADR 0003, 0027, 0036, 0086) -- and a lab report is the worst
    place for it, because the whole document is a claim that the numbers
    shown are the numbers used.

    So the sections do not each read the payload. They are all handed this.
    A disagreement is refused rather than resolved by precedence: picking a
    winner silently would restore the original defect with a rule attached.
    """
    values: dict[str, float] = {}
    origin: dict[str, str] = {}

    def claim(name: str, value: float, where: str) -> None:
        if name in values and float(values[name]) != float(value):
            raise ConflictingValue(
                f"{name} was given twice with different values: "
                f"{values[name]} ({origin[name]}) and {value} ({where}). "
                "Caterva will not choose between them, because the report "
                "would state one number and be computed from the other."
            )
        values[name] = float(value)
        origin.setdefault(name, where)

    # Literature-resolved values are keyed by the QUANTITY they measure, not
    # by the label the caller chose. A caller naming a parameter "km_lactate"
    # still resolved a km, and the model takes a km.
    for name, result in resolved.items():
        if getattr(result, "found", False) and result.value is not None:
            claim(quantities.get(name, name), result.value, f"literature, via {name}")

    for entry in supplied:
        claim(entry.name, entry.value, "supplied by you")

    for name in ("km", "vmax", "s0"):
        if payload.get(name) is not None:
            claim(name, float(payload[name]), f"payload {name!r}")

    return values


def band_for(candidates, *, parameter, inputs, seed, draws):
    """The weighted band across the values, or None with the reason.

    WHY A SEED IS REQUIRED RATHER THAN DEFAULTED
    --------------------------------------------
    `sample_ensemble` makes `seed` a required argument because an ensemble
    nobody can reproduce is not evidence, and this repository's whole claim
    is that its numbers can be re-derived. Defaulting one here would undo
    that at the last step -- the report would carry a band, print a seed
    the caller never chose, and look reproducible.

    So a missing seed produces no band AND a sentence saying so, rather
    than a band nobody asked to be able to repeat.

    Returns (band, refusal). Exactly one is None.
    """
    if len(candidates) < 2:
        return None, None
    if seed is None:
        return None, (
            "no band was produced across the "
            f"{len(candidates)} values the literature reports for "
            f"{parameter}: no seed was supplied, and an ensemble nobody can "
            "reproduce is not evidence. Re-run with --seed N."
        )
    missing = [n for n in ("km", "vmax", "s0") if inputs.get(n) is None]
    if missing:
        return None, (
            f"no band was produced for {parameter}: the model cannot be run "
            f"without {', '.join(missing)}."
        )

    from caterva.continuous.simulations import simulate_michaelis_menten

    try:
        drawn = ensemble_from_entries(
            candidates, draws=draws, seed=seed, value_attr="value"
        )
        return ensemble_over(
            simulate=simulate_michaelis_menten,
            base_parameters={
                "km": inputs["km"], "vmax": inputs["vmax"], "s0": inputs["s0"]
            },
            parameter=parameter,
            drawn=drawn,
        ), None
    except Exception as exc:  # noqa: BLE001 - reported, never a traceback
        # A band that will not compute is a finding about the values, which
        # are printed above it. Swallowing it would leave the document
        # silently narrower than the evidence.
        return None, f"no band was produced for {parameter}: {exc}"


def one_page_per_run(fetch):
    """Fetch each EC page once, however many quantities are read from it.

    BRENDA serves km, ki and kcat as separate TABLES ON ONE PAGE, and
    `resolve_kinetic_value` fetches inside itself — so a report asking for
    two parameters fetched the same page twice, and adding the kcat lookup
    for the Vmax bridge would have made it three.

    Lisa Jeske (BRENDA/DSMZ) asked directly that tools be gentle with their
    servers, and this repository already refuses to auto-download a bulk
    corpus for that reason. Re-requesting a page Caterva is still holding is
    the same discourtesy in miniature, repeated once per parameter.

    Scoped to a single run deliberately. A cache that outlives the process
    would make a report reproducible against a page nobody can see any more,
    which is a provenance problem dressed as an optimisation (ADR 0016).
    """
    cache: dict[str, str] = {}

    def get(ec_number: str, timeout: float = 15) -> str:
        key = str(ec_number)
        if key not in cache:
            cache[key] = fetch(key, timeout)
        return cache[key]

    get.fetches = cache  # type: ignore[attr-defined]
    return get


class FixtureUnusable(ValueError):
    """A saved page was given that cannot answer the question asked."""


#: BRENDA's own EC number as it appears on a saved page. Every fixture in
#: `Tests/fixtures/` contains exactly one, and it is the page's subject.
_EC_IN_PAGE = re.compile(r"\b\d+\.\d+\.\d+\.\d+\b")


def fixture_reader(fixture: str | None, ec: str):
    """The saved-page path, or the live one when no fixture was given.

    WHY `report` NEEDED THIS
    -----------------------
    `ensemble` has taken `--fixture` since it was written. `report` did not,
    and `report` is the command this project chose as its product — "one
    command, one document a student can hand in".

    Measured on 2026-08-21, running the exact invocation printed in the
    command's own help text:

        $ scientific report --ec 1.1.1.27 --organism "Homo sapiens" \\
              --substrate "(S)-lactate" --s0 10mM --vmax 0.25mM/s --seed 1
        -> Could not resolve 'km': 403 Forbidden

    That is the whole run. BRENDA rate-limits, institutions proxy, and a
    teaching lab of thirty students hitting one host in one period is exactly
    the traffic Lisa Jeske asked this project to be gentle about. The
    flagship command had no path that did not require the network to be
    working at that moment — so it could not be demonstrated, could not be
    exercised end to end by any test, and failed the student with a bare HTTP
    status.

    The capability already existed one command over. This is the fifth
    consecutive instance of the same shape (ADR 0136, 0139, 0141, 0142):
    parts that each work, and no wiring at the seam.

    WHY IT VERIFIES THE EC RATHER THAN TRUSTING THE PATH
    ----------------------------------------------------
    A fixture is one saved page for one enzyme. Nothing about a filename
    stops somebody passing `brenda_ldh_fixture.html` while asking about
    EC 2.7.1.1 — and the resolver would then parse lactate dehydrogenase
    rows, find them, and report them under hexokinase's name with real
    reference numbers attached.

    That is not a missing feature, it is **a real citation for the wrong
    protein**, which ADR 0126 already refuses at the name-to-EC step. An
    offline path that reintroduces it at the fixture step would have made
    the tool less trustworthy in exchange for being testable.

    So the page's own EC is read and compared. A page carrying no EC at all
    is refused too: "I could not find one" must not pass as "it matches".
    """
    if not fixture:
        return fetch_brenda_html

    path = pathlib.Path(fixture).expanduser()
    if not path.is_file():
        raise FixtureUnusable(
            f"No saved BRENDA page at {fixture!r}. --fixture takes a path to "
            "an HTML page you saved yourself; Caterva does not download one "
            "for you and then call the result offline."
        )

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise FixtureUnusable(f"Could not read {fixture!r}: {exc}") from exc

    found = set(_EC_IN_PAGE.findall(text))
    if not found:
        raise FixtureUnusable(
            f"{fixture!r} contains no EC number, so Caterva cannot tell which "
            "enzyme it describes. It will not read kinetic rows off a page it "
            "cannot identify — a value is only as good as knowing what it "
            "measures."
        )
    if str(ec) not in found:
        raise FixtureUnusable(
            f"{fixture!r} is a page for EC {', '.join(sorted(found))}, and you "
            f"asked about EC {ec}. Caterva will not read rows from one "
            "enzyme's page and report them under another's name: the "
            "reference numbers would be real and the protein would be wrong "
            "(ADR 0126)."
        )

    def read(ec_number: str, timeout: float = 15) -> str:
        # `timeout` is accepted and ignored on purpose, so this is a drop-in
        # for `fetch_brenda_html` and `one_page_per_run` needs no branch. A
        # cache keyed on the EC still works: there is one page and one key.
        return text

    return read


def bridge_vmax(kcat_result, enzyme_conc: float, km: float | None):
    """Vmax from a literature kcat and the student's enzyme concentration.

    WHY THIS EXISTS
    ---------------
    `report` required `--vmax`, which is the one required input a teaching
    lab's student genuinely cannot produce: Vmax is a property of *their
    tube*, not of the enzyme, and no database reports it. BRENDA does report
    kcat, and `simulate --resolve` has bridged the two since ADR 0019 — so
    `report` was demanding a number it could have computed.

    WHAT IS NOT REIMPLEMENTED HERE
    ------------------------------
    The arithmetic, the unit convention and the validation all live in
    `caterva.core.validation.vmax_from_kcat` (ADR 0012, ADR 0013), which also
    flags the [E]0 << Km assumption the Michaelis-Menten rate law rests on.
    Multiplying two floats here instead would have been three lines and a
    second definition of what the bridge means — the defect this repository
    has spent most of its effort on. This function resolves nothing and
    computes nothing; it arranges and it reports.

    Returns (DerivedValue, warnings) or (None, refusal-string).
    """
    from caterva.core.validation import vmax_from_kcat

    if not getattr(kcat_result, "found", False) or kcat_result.value is None:
        return None, (
            "vmax could not be derived: an enzyme concentration was given, "
            "but no kcat was found to combine it with. Vmax = kcat x [E]0 "
            "needs both."
        )

    try:
        value, validation = vmax_from_kcat(
            float(kcat_result.value), float(enzyme_conc), km
        )
    except Exception as exc:  # noqa: BLE001 - reported, never a traceback
        return None, f"vmax could not be derived from kcat: {exc}"

    if not getattr(validation, "ok", True):
        # A rejected bridge is a finding about the numbers, and the reason
        # names which one. Returning a Vmax anyway would put an invalid
        # number in the table with a citation beside it.
        reasons = "; ".join(getattr(validation, "errors", []) or ["rejected"])
        return None, f"vmax could not be derived from kcat: {reasons}"

    unit = getattr(kcat_result, "unit", None) or "1/s"
    return (
        DerivedValue(
            name="vmax",
            value=value,
            unit="mM/s",
            from_cited=(
                f"kcat {_fmt_number(kcat_result.value)} {unit} "
                f"({_citation_of(kcat_result)})"
            ),
            from_chosen=f"[E]0 {_fmt_number(enzyme_conc)} mM, which is yours",
            relation="Vmax = kcat x [E]0",
        ),
        list(getattr(validation, "warnings", []) or []),
    )


def _fmt_number(value) -> str:
    return f"{float(value):.6g}"


def _citation_of(result) -> str:
    """The reference for a resolved value, or an honest absence."""
    citation = getattr(result, "citation", None)
    if citation is None:
        return "no citation recorded"
    source = getattr(citation, "source", None) or "unknown source"
    reference = getattr(citation, "reference_id", None)
    return f"{source} ref {reference}" if reference else source


#: What the Michaelis-Menten model cannot run without, and who owns each.
#:
#: The distinction is the one the professors' correspondence turns on: a km
#: is a property of the enzyme that the literature can supply, while s0 is
#: how much substrate the student put in the tube. Reporting a missing s0
#: the same way as a missing km tells a reader to go looking for a paper
#: that cannot exist.
MM_REQUIRED = {
    "km": "a measured property of the enzyme; Caterva resolves it or refuses",
    "vmax": "yours to supply, or derived from kcat and the enzyme concentration",
    "s0": "yours to choose — how much substrate you put in, not a property "
    "of the enzyme",
}


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        return _fail(f"Invalid JSON payload: {exc}")
    result = run_payload(payload)
    print(json.dumps(result))
    return 0 if result.get("ok") else 1


def _failure(message: str, name_refusal: dict | None = None) -> dict:
    """A refusal. `name_refusal` is the enzyme-name policy's refusal as data
    (named candidates, kind, recommended EC, re-run flag) when the refusal
    was a name that is not exactly one enzyme."""
    out = {"ok": False, "error": message}
    if name_refusal:
        out["name_refusal"] = name_refusal
    return out


def run_payload(payload: dict) -> dict:
    """The JSON object `main` prints for `payload`: {"ok": False, "error"}
    for a refusal, else the document and the facts it was built from.

    In-process callers (Caterva Studio's `constants` kind, through
    scripts/cite.py's `run_report_lab`) call this rather than spawning
    Python: in a frozen app `sys.executable` is the app, not an
    interpreter. `resolved` carries each KineticResult the document was
    built from (`model_dump(mode="json")`), so a reader of the JSON reads
    the resolver's own value, citation and conditions rather than parsing
    them back out of the markdown.
    """
    ec = payload.get("ec")
    organism = payload.get("organism")

    # A STUDENT KNOWS THE NAME, NOT THE NUMBER.
    #
    # `report` shipped requiring an EC number, so the first thing a teaching
    # lab's student typed -- the enzyme's name, the flag `catalog` and
    # `simulate` both already accept -- was refused by a message beginning
    # "report needs an enzyme". Measured, before this:
    #
    #   $ report --enzyme "lactate dehydrogenase" --organism "Homo sapiens" \
    #            --substrate lactate
    #   -> report needs an enzyme, an organism and a substrate
    #
    # The name is resolved through the SAME policy `catalog` uses, which
    # refuses rather than picking when a name maps to more than one enzyme.
    # Resolving is not guessing: the enzyme nomenclature is asked, and one
    # answer is an answer. Two answers is a refusal that names both.
    if not ec and payload.get("enzyme"):
        try:
            ec = ec_number_for_name(
                str(payload["enzyme"]), organism=organism, rerun="--ec {ec}",
            )
        except EnzymeNameNotResolved as exc:
            return _failure(str(exc), getattr(exc, "view", None))

    if not ec or not organism:
        return _failure(
            "A report needs an enzyme and an organism. Give the enzyme as an "
            "EC number ('ec') or as a name ('enzyme') — a name is looked up "
            "in UniProt, and refused if it matches more than one enzyme. The "
            "organism is not inferred from free text: guessing it would "
            "attach real citations to a system nobody named."
        )

    # Read BEFORE anything is fetched. A malformed payload should cost a
    # message, not a BRENDA round trip followed by a document with a hole in
    # it — and a check that only runs after a network call cannot be tested
    # without one.
    try:
        supplied = supplied_values(payload)
    except MalformedSuppliedValue as exc:
        return _failure(str(exc))

    # One fetch per page, not one per quantity. See `one_page_per_run`.
    try:
        fetch = fixture_reader(payload.get("fixture"), str(ec))
    except FixtureUnusable as exc:
        return _failure(str(exc))
    page = one_page_per_run(fetch)

    # A SAVED PAGE MEANS THE WHOLE RUN IS OFFLINE, AND THE DOCUMENT SAYS SO.
    #
    # `--fixture` replaced only the BRENDA fetch at first, and the run still
    # died — on **NCBI**, not BRENDA. `resolve_kinetic_value` also consults
    # UniProt, NCBI Taxonomy and a literature search, and the failure it
    # printed was `Could not resolve 'km': 403 Forbidden`, which names the
    # parameter and the status and not the service. A student reading that
    # would go and check whether BRENDA was down. It was not.
    #
    # So a fixture run does not consult them either. It cannot: the student
    # reaching for a saved page is usually the student with no network.
    #
    # What that costs is REAL and is recorded rather than absorbed. Organism
    # relatedness is graded from an NCBI lineage; without it the axis is
    # `not_assessed`, which is the honest third state and not a pass. A
    # document that quietly skipped the check would be indistinguishable
    # from one where the organism matched.
    offline = bool(payload.get("fixture"))
    offline_note = (
        "Caterva did not verify the organism against NCBI Taxonomy or "
        "UniProt, and ran no literature search: you supplied a saved BRENDA "
        "page with --fixture, so this run made no network requests at all. "
        "Organism relatedness is therefore NOT ASSESSED rather than matched "
        "— the rows below are whatever the saved page holds. Re-run without "
        "--fixture, on a machine with network, to have that checked."
    )
    lookups = (
        {
            "uniprot_provider": lambda *a, **k: None,
            "taxon_id_provider": lambda *a, **k: None,
            "search_literature": False,
        }
        if offline
        else {}
    )

    resolved: dict = {}
    ensembles: dict = {}
    bands: dict = {}
    band_refusals: list[str] = []
    quantities: dict[str, str] = {}
    for entry in payload.get("parameters") or []:
        name = entry.get("name")
        substrate = entry.get("substrate")
        if not name or not substrate:
            return _failure(
                "Every parameter needs a 'name' and a 'substrate'. BRENDA's "
                "tables are keyed on the substrate, so a lookup without one "
                "is answered by every compound ever tested against the enzyme."
            )
        try:
            result = resolve_kinetic_value(
                str(ec), str(organism), str(substrate),
                html_provider=page,
                **lookups,
                quantity=str(entry.get("quantity", "km")),
                allow_cross_species=bool(entry.get("allowCrossSpecies", False)),
            )
        except Exception as exc:  # noqa: BLE001 - reported, never a traceback
            return _failure(f"Could not resolve {name!r}: {exc}")

        resolved[str(name)] = result
        quantities[str(name)] = str(entry.get("quantity", "km"))

    try:
        inputs = model_inputs(resolved, quantities, supplied, payload)
    except ConflictingValue as exc:
        return _failure(str(exc))

    # ---- Vmax from kcat, when the student gave [E]0 instead ---------------
    #
    # Only when Vmax is genuinely absent. A supplied Vmax is a decision, and
    # silently replacing it with a derived one would overrule the student
    # using a number they cannot see — the same defect as discarding their
    # --vmax in a suggested command (ADR 0116).
    derived: list[DerivedValue] = []
    derive_refusals: list[str] = []
    enzyme_conc = payload.get("enzymeConc")

    if enzyme_conc is not None and "vmax" not in inputs:
        substrate = None
        for entry in payload.get("parameters") or []:
            if entry.get("substrate"):
                substrate = str(entry["substrate"])
                break
        try:
            kcat_result = resolve_kinetic_value(
                str(ec), str(organism), str(substrate),
                html_provider=page,
                **lookups,
                quantity="kcat",
                allow_cross_species=bool(
                    (payload.get("parameters") or [{}])[0].get(
                        "allowCrossSpecies", False
                    )
                ),
            )
        except Exception as exc:  # noqa: BLE001 - reported, never a traceback
            return _failure(f"Could not resolve kcat: {exc}")

        value, detail = bridge_vmax(kcat_result, float(enzyme_conc), inputs.get("km"))
        if value is None:
            derive_refusals.append(str(detail))
        else:
            derived.append(value)
            inputs["vmax"] = value.value
            # The rate law's [E]0 << Km assumption is stretched, not broken.
            # The run still teaches something, so it is a warning in the
            # document rather than a refusal (ADR 0013).
            derive_refusals.extend(str(w) for w in (detail or []))
    elif enzyme_conc is not None:
        derive_refusals.append(
            "an enzyme concentration was given and not used: a vmax was "
            "already supplied, and Caterva does not overrule a value you "
            "chose with one it computed."
        )

    # ---- The ensemble, and the run, from the SAME numbers -----------------
    #
    # Both of these used to read `payload` directly. They now read `inputs`,
    # so "what the model does across the evidence" and "what the model did"
    # cannot be computed at different values than the table states.
    for name, result in resolved.items():
        candidates = list(getattr(result, "cross_species_candidates", []) or [])
        tie = getattr(result, "selection_tie", None)
        if tie is not None and getattr(tie, "is_tied", False):
            candidates = list(tie.candidates)
        if len(candidates) > 1:
            ensembles[name] = consequence_of(
                candidates,
                parameter=quantities.get(name, "km"),
                vmax=inputs.get("vmax"),
                s0=inputs.get("s0"),
            )
            # And the weighted band over the same candidates. Both appear in
            # the document because they answer different questions, and ADR
            # 0134's agreement test makes carrying both safe: the band
            # cannot reach outside the enumerated outcomes.
            band, why_not = band_for(
                candidates,
                parameter=quantities.get(name, "km"),
                inputs=inputs,
                seed=payload.get("seed"),
                draws=int(payload.get("draws", 400)),
            )
            if band is not None:
                bands[name] = band
            elif why_not:
                band_refusals.append(why_not)

    simulation = None
    # The offline note is a REFUSAL, not a footnote. It belongs in "What
    # Caterva would not do" beside everything else the run declined, because
    # that is the section a reader checks before trusting the document — and
    # an unverified organism is exactly the kind of gap this report exists to
    # make visible rather than absorb.
    also_refused: list[str] = [offline_note] if offline else []
    missing = [name for name in MM_REQUIRED if name not in inputs]

    if missing:
        # NOT silence. Until now the Result section simply did not render
        # when the model could not be run, which is indistinguishable from a
        # report where nobody tried to run it -- the exact failure the "What
        # Caterva would not do" section exists to prevent, occurring inside
        # the document that section belongs to.
        also_refused.append(
            "the simulation was not run: "
            + "; ".join(f"{name} is missing — {MM_REQUIRED[name]}" for name in missing)
        )
    else:
        try:
            from caterva.continuous.simulations import simulate_michaelis_menten

            simulation = simulate_michaelis_menten(
                km=inputs["km"],
                vmax=inputs["vmax"],
                s0=inputs["s0"],
                end=float(payload.get("endTime", 10.0)),
                points=int(payload.get("points", 51)),
            )
        except Exception as exc:  # noqa: BLE001 - reported, never a traceback
            # A model that would not integrate is a finding about the
            # parameters, which are printed directly above it. Swallowing it
            # would leave a report asserting values that cannot be run.
            also_refused.append(
                f"the simulation was not run: the model would not integrate "
                f"at these values — {exc}"
            )

    report = build_report(
        title=str(payload.get("title") or f"EC {ec} in {organism}"),
        question=str(payload.get("question") or ""),
        resolved=resolved,
        supplied=supplied,
        derived=derived,
        ensembles=ensembles,
        bands=bands,
        simulation=simulation,
        bibtex=payload.get("bibtex"),
        also_refused=also_refused + band_refusals + derive_refusals,
    )

    return {
        "ok": True,
        "markdown": report.markdown,
        "sourced": report.sourced,
        "supplied": report.supplied,
        "derived": report.derived,
        "refusals": report.refusals,
        "disagreements": report.disagreements,
        "defensible": report.is_defensible,
        "resolved": {name: result.model_dump(mode="json") for name, result in resolved.items()},
    }


if __name__ == "__main__":
    raise SystemExit(main())
