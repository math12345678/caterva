#!/usr/bin/env python3
"""Regenerate caterva/prepare/data/mcsa_catalytic.json from the M-CSA API.

    python3 scripts/capture_mcsa_snapshot.py            # fetch live
    python3 scripts/capture_mcsa_snapshot.py --from DIR # pages saved as DIR/ent*.json

`caterva prepare` reads catalytic residues from this snapshot rather than
the live API so an audit is reproducible and works offline, and because the
API's filtered queries return HTTP 500 (observed 2026-09-27) -- only the
paged full listing works. Each entry keeps the reference UniProt accession,
its EC numbers and its catalytic residues, numbered on the reference
sequence. M-CSA is CC BY 4.0; the snapshot carries its citation.
"""
from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import sys

API = "https://www.ebi.ac.uk/thornton-srv/m-csa/api/entries/?format=json"
OUT = pathlib.Path(__file__).resolve().parents[1] / "caterva" / "prepare" / "data" / "mcsa_catalytic.json"


def pages_live():
    import requests
    url = API
    while url:
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        page = r.json()
        yield page["results"]
        url = page.get("next")


def pages_from(directory: pathlib.Path):
    files = sorted(directory.glob("ent*.json"), key=lambda p: int(p.stem[3:] or 0))
    for f in files:
        yield json.loads(f.read_text())["results"]


def compact(entries):
    out = []
    for x in entries:
        residues = []
        for r in x["residues"]:
            seqs = [s for s in r["residue_sequences"] if s.get("is_reference")] or r["residue_sequences"]
            if not seqs or seqs[0].get("resid") is None:
                continue
            s = seqs[0]
            row = {"code": s["code"], "resid": s["resid"], "roles": (r.get("roles_summary") or "")[:80]}
            if s["uniprot_id"] != x["reference_uniprot_id"]:
                row["uniprot"] = s["uniprot_id"]  # a residue on a partner subunit
            residues.append(row)
        out.append({"mcsa_id": x["mcsa_id"], "enzyme": x["enzyme_name"],
                    "uniprot": x["reference_uniprot_id"], "ecs": x["all_ecs"], "residues": residues})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--from", dest="src", type=pathlib.Path, help="read saved pages instead of fetching")
    ap.add_argument("--date", default=datetime.date.today().isoformat(), help="retrieval date to record")
    args = ap.parse_args(argv)
    entries = [e for page in (pages_from(args.src) if args.src else pages_live()) for e in page]
    snap = {
        "source": "M-CSA (Ribeiro et al. 2018, Nucleic Acids Res. 46:D618, doi:10.1093/nar/gkx1012), CC BY 4.0",
        "retrieved": args.date,
        "api": API,
        "note": "Reference-protein catalytic residues, numbered on the reference UniProt sequence. "
                "Regenerate with scripts/capture_mcsa_snapshot.py.",
        "entries": compact(entries),
    }
    OUT.write_text(json.dumps(snap, separators=(",", ":")), encoding="utf-8")
    print(f"{len(snap['entries'])} entries, "
          f"{sum(len(e['residues']) for e in snap['entries'])} residues -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
