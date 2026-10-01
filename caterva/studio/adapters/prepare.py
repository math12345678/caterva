"""Kind `prepare`: `caterva prepare`, what is wrong with an entry before it is simulated (owner: sci-structure).

WHAT IT CALLS
-------------
The command's own pieces (caterva/prepare/__main__.py): `fetcher` (RCSB and
UniProt, cached where the command caches them), `audit_or_refuse` (the
audit, or the refusal the command prints for a missing entry or no
network), `report` (the markdown the command prints), `clean_chains` (the
exit rule: 0 when a chain has no blocking defect and its catalytic residues
intact, 4 when none has) and `charge_states` (the rows of the protonation
table, judged at the assay pH). The audit object itself goes back as
`audit`, exactly as `--json` writes it.

WHAT A REQUEST MAY NAME
-----------------------
A PDB id, or an absolute path to a local .cif/.mmcif file (CONTRACT.md,
"User paths"): resolved, required to be a regular file with that suffix,
and recorded resolved. Anything else is malformed here, before a run
exists, although the command itself reaches the same refusal one step
later (exit 3, "neither a PDB id nor an existing .cif file"): a question
the page can tell is not well formed should be refused under its field,
not run. `--out` and `--json` are never produced; the report and the audit
are the result.

HOW EACH NUMBER IS LABELLED
---------------------------
Resolution and R-free are the entry's own statements about itself:
measured, cited to the entry. A finding's distance to the active site is
computed by the audit (nearest atom of a catalytic residue in the same
chain). The active-site radius is the command's chosen cutoff, said to be
one. A titratable residue's typical pKa is the cited survey's mean (Grimsley,
Scholtz & Pace 2009), and the fraction protonated at the assay pH is
computed from it by Henderson-Hasselbalch; the pH itself is the person's.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from caterva.studio import contract
from caterva.studio.adapters import AdapterOutcome, AdapterSpec, RunContext, cli_parser
from caterva.studio.adapters.md import checked, first_line, user_file
from caterva.studio.adapters.structure import entry_citation, method_citation, reported

PROG = "caterva prepare"

REQUEST_KEYS: Mapping[str, type] = {"entry": str, "ph": float, "no_cache": bool}

PDB_ID = re.compile(r"[0-9][A-Za-z0-9]{3}")

#: Suffixes a local entry may have (the command reads .cif and .mmcif).
CIF_SUFFIXES = (".cif", ".mmcif")


def prepare_argv(request: Mapping[str, Any]) -> List[str]:
    from caterva.prepare.__main__ import build_parser

    r = checked(request, REQUEST_KEYS, required=("entry",))
    entry = r["entry"].strip()
    if PDB_ID.fullmatch(entry):
        argv = [entry.upper()]
    elif entry.startswith("/") or entry.startswith("~") or "/" in entry or "\\" in entry:
        argv = [str(user_file(entry, "entry", CIF_SUFFIXES))]
    else:
        raise contract.Malformed(f"entry: {entry!r} is neither a PDB id (four characters, starting with a digit, "
                                 "like 1I10) nor an absolute path to a .cif file", field="entry")
    if "ph" in r:
        argv += ["--ph", repr(r["ph"])]
    if r.get("no_cache"):
        argv.append("--no-cache")
    cli_parser(build_parser, PROG).parse_args(argv)
    return argv


def _describe(request: Mapping[str, Any]) -> str:
    entry = str(request.get("entry", "?"))
    name = Path(entry).name if "/" in entry else entry.upper()
    return f"Audit of {name}" + (f" at pH {request['ph']:g}" if isinstance(request.get("ph"), (int, float)) else "")


def _entry_citation(a: Any, entry: str) -> contract.Citation:
    if PDB_ID.fullmatch(entry):
        return entry_citation(entry)
    return {"text": f"local file {entry} (entry {a.pdb_id} as the file names it)", "registry": None, "url": None}


def finding_row(f: Any) -> contract.FindingRow:
    """One finding as the audit made it. The distance is the audit's (to the
    nearest atom of a catalytic residue in the same chain)."""
    from caterva.prepare.audit import ACTIVE_SITE_RADIUS

    distance = None
    if f.distance is not None:
        distance = contract.sourced(f.distance, "Å", contract.computed(
            "distance to the nearest atom of a catalytic residue in the same chain, from the entry's coordinates "
            "(unmodelled stretches placed by their observed flanking residues)", [f.chain or "?"]),
            label="to the active site")
    return {"severity": f.severity, "chain": f.chain, "residues": list(f.residues), "distance": distance,
            "what": f.what, "source": f.source, "check": f.check, "catalytic": bool(f.catalytic),
            "near_active_site": f.distance is not None and f.distance <= ACTIVE_SITE_RADIUS}


def _catalytic_rows(a: Any) -> List[Dict[str, Any]]:
    return [{"chain": c.chain, "resseq": c.auth_seq_id, "expected": c.expected, "found": c.found,
             "conserved": c.found == c.expected, "roles": c.roles, "reference": c.reference, "seq_id": c.seq_id}
            for c in a.catalytic]


def _reference(a: Any) -> Optional[Dict[str, Any]]:
    from caterva.studio.adapters.structure import catalytic_reference

    ref = catalytic_reference(a)
    return None if ref is None else dict(ref)


def charge_rows(a: Any, ph: float) -> List[Dict[str, Any]]:
    """The protonation table at `ph`, each row from `charge_states`."""
    from caterva.prepare.__main__ import charge_states
    from caterva.prepare.protonation import SOURCE

    survey = {"text": SOURCE, "registry": None, "doi": "10.1002/pro.19", "url": "https://doi.org/10.1002/pro.19"}
    rows: List[Dict[str, Any]] = []
    for c in charge_states(a, ph):
        t = c.titration
        row: Dict[str, Any] = {
            "residue": c.name, "chain": c.site.chain, "resseq": c.site.auth_seq_id, "resname": c.site.resname,
            "catalytic": bool(c.site.catalytic),
            "distance": contract.sourced(c.site.distance, "Å", contract.computed(
                "distance to the nearest atom of a catalytic residue in the same chain",
                [c.site.chain]), label="to the active site"),
            "at_ph": c.at_ph, "state": c.state, "emphasised": c.emphasised,
            "contradicted": c.contradicted, "uncertain": c.uncertain,
            "pka": None, "pka_sd": None, "protonated": None, "band": None, "default_protonated": None,
        }
        if t is not None:
            prov: contract.Provenance = {
                "kind": "measured", "citation": survey, "organism": None, "cross_species": False,
                "conditions": {"ph": None, "temperature_c": None, "buffer": None, "unreported": []},
                "commentary": f"mean of {t.n} measured {t.group} pKa values in folded proteins",
                "scope": ["a survey average for the residue type, not this residue's pKa in this structure"],
            }
            row["pka"] = contract.sourced(t.pka, "", prov, label=f"typical pKa of {t.group}")
            row["pka_sd"] = contract.sourced(t.sd, "", prov, label="standard deviation across the survey")
            hh = contract.computed("Henderson-Hasselbalch at the assay pH: 1 / (1 + 10^(pH - pKa))",
                                   [f"typical pKa of {t.group}", "pH"])
            row["protonated"] = contract.sourced(t.protonated, "", hh, label="fraction protonated")
            row["band"] = [contract.sourced(t.band[0], "", hh, label="at pKa - SD"),
                           contract.sourced(t.band[1], "", hh, label="at pKa + SD")]
            row["default_protonated"] = t.default_protonated
        rows.append(row)
    return rows


def prepare_run(request: Mapping[str, Any], ctx: RunContext) -> AdapterOutcome:
    from caterva.prepare.__main__ import audit_or_refuse, build_parser, clean_chains, fetcher, report
    from caterva.prepare.audit import ACTIVE_SITE_RADIUS

    args = cli_parser(build_parser, PROG).parse_args(prepare_argv(request))
    ctx.progress.stage("fetch", f"Reading {Path(args.entry).name if '/' in args.entry else 'PDB ' + args.entry}"
                       " and its UniProt sequences")
    ctx.progress.check_cancelled()
    a, refusal = audit_or_refuse(args.entry, fetcher(args.no_cache))
    if a is None:
        return AdapterOutcome(3, None, first_line(refusal), refusal)
    ctx.progress.stage("audit", f"Placing every finding against the catalytic residues of {a.pdb_id}")
    ctx.progress.check_cancelled()
    text = "\n".join(report(a, args.ph)) + "\n"
    clean = clean_chains(a)
    organism = None
    result: contract.PrepareResult = {
        "pdb_id": a.pdb_id,
        "title": a.title,
        "method": a.method,
        "resolution": reported(a.resolution, "Å", _entry_citation(a, args.entry), organism, "resolution",
                               note="refine.ls_d_res_high of the entry's mmCIF"),
        "r_free": reported(a.r_free, "", _entry_citation(a, args.entry), organism, "R-free",
                           note="refine.ls_R_factor_R_free of the entry's mmCIF"),
        "chains": list(a.chains),
        "clean": bool(clean),
        "chain_summary": [{"chain": s.chain, "blocks": s.blocks, "near_site": s.near_site,
                           "catalytic_intact": s.catalytic_intact} for s in a.chain_summary],
        "findings": [finding_row(f) for f in a.findings],
        "catalytic": _catalytic_rows(a),
        "reference": _reference(a),
        "protonation": None if args.ph is None else charge_rows(a, args.ph),
        "not_checked": list(a.not_checked),
        "report_markdown": text,
        "audit": json.loads(json.dumps(asdict(a), default=str)),
        "entry_citation": _entry_citation(a, args.entry),
        "clean_chains": clean,
        "ph": None if args.ph is None else contract.sourced(
            args.ph, "", contract.chosen("user", "the assay pH, as given"), label="assay pH"),
        "active_site_radius": contract.sourced(ACTIVE_SITE_RADIUS, "Å", contract.chosen(
            "default", "a chosen cutoff, not a physical boundary (caterva prepare)"), label="active-site radius"),
    }
    blocks = len(a.by_severity("blocks"))
    summary = (f"{a.pdb_id}: {len(a.chains)} chain{'s' if len(a.chains) != 1 else ''}, "
               + (f"clean: {', '.join(clean)}" if clean else "every chain blocked")
               + f"; {blocks} blocking finding{'s' if blocks != 1 else ''}")
    return AdapterOutcome(0 if clean else 4, result, summary)


def register(registry) -> None:
    registry.register(AdapterSpec(
        kind="prepare",
        title="Audit an entry",
        command="prepare",
        needs=("network",),
        argv=prepare_argv,
        run=prepare_run,
        describe=_describe,
        cli_prefix=("caterva", "prepare"),
    ))


__all__ = ["PROG", "charge_rows", "finding_row", "prepare_argv", "prepare_run", "register"]
