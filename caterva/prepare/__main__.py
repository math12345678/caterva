"""`caterva prepare`: what is wrong with a PDB entry before you simulate it.

    caterva prepare 1I10
    caterva prepare 1I10 --json audit.json --out audit.md
    caterva prepare ./my_model.cif

Reads the entry's own mmCIF records and reports, ranked by how much each
matters and how close it sits to the enzyme's catalytic residues:
residues that differ from UniProt (whatever the depositors called them),
chain breaks, truncated side chains, alternate conformations, non-standard
residues, the biological assembly against the deposited chains, and model
quality. It fixes nothing; it says what a setup would silently get wrong.

Exit codes follow the rest of Caterva: 0 at least one chain has no blocking
defect, 4 every chain has one, 2 a malformed question, 3 refused and said
why (no such entry, no network), 1 a crash.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from caterva.methods import METHODS
from caterva.prepare.audit import ACTIVE_SITE_RADIUS, Audit, audit

RCSB_CIF = "https://files.rcsb.org/download/{id}.cif"
UNIPROT_FASTA = "https://rest.uniprot.org/uniprotkb/{acc}.fasta"

EXIT_BLOCKS = 4


class PrepareError(Exception):
    """The audit could not be run, as distinct from finding defects."""


def _cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.environ.get("HOME") or "~", ".cache")
    return Path(os.path.expanduser(base)) / "caterva" / "prepare"


def live_fetch(timeout: float = 60.0) -> Callable[[str], str]:
    import requests

    def get(url: str) -> str:
        r = requests.get(url, timeout=timeout)
        if r.status_code == 404:
            raise PrepareError(f"not found: {url}")
        r.raise_for_status()
        return r.text
    return get


def cached(fetch: Callable[[str], str], cache: Optional[Path]) -> Callable[[str], str]:
    """Deposited entries and UniProt sequences are stable; fetch each once."""
    if cache is None:
        return fetch

    def get(url: str) -> str:
        name = re.sub(r"[^A-Za-z0-9._-]", "_", url.split("://", 1)[-1])
        path = cache / name
        if path.exists():
            return path.read_text(encoding="utf-8")
        text = fetch(url)
        cache.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return text
    return get


def sequence_fetcher(fetch: Callable[[str], str]) -> Callable[[str], str]:
    def sequence_of(acc: str) -> str:
        text = fetch(UNIPROT_FASTA.format(acc=acc))
        return "".join(l.strip() for l in text.splitlines() if l and not l.startswith(">"))
    return sequence_of


def run_audit(entry: str, fetch: Callable[[str], str]) -> Audit:
    path = Path(entry)
    if path.suffix.lower() in (".cif", ".mmcif") and path.exists():
        text = path.read_text(encoding="utf-8")
    elif re.fullmatch(r"[0-9][A-Za-z0-9]{3}", entry):
        text = fetch(RCSB_CIF.format(id=entry.upper()))
    else:
        raise PrepareError(f"{entry!r} is neither a PDB id (like 1I10) nor an existing .cif file")
    return audit(text, sequence_fetcher(fetch))


def _dist(d: Optional[float]) -> str:
    return "?" if d is None else f"{d:.1f}"


def report(a: Audit) -> List[str]:
    q = []
    if a.resolution is not None:
        q.append(f"{a.resolution} Å")
    if a.r_free is not None:
        q.append(f"R-free {a.r_free:.3f}")
    L = [f"# Preparation audit: {a.pdb_id}", "", f"*{a.title}*", "",
         f"{a.method.lower()}{', ' + ', '.join(q) if q else ''}. "
         f"Chains of the enzyme: {', '.join(a.chains)}.", ""]

    if a.reference:
        r = a.reference
        L += ["## Catalytic residues", "",
              f"From M-CSA entry {r.mcsa_id} ({r.enzyme}, reference {r.uniprot}), chosen by "
              f"{r.how}; {r.identity:.0%} identical to chain {a.chains[0]}. Positions are carried "
              "onto each chain by global alignment.", ""]
        if r.rejected:
            L.append("Other M-CSA mechanisms for this EC number, not used: " + "; ".join(
                f"{mid} {name} ({ident:.0%})" for mid, name, ident in r.rejected) + ".")
            L.append("")
        first = [c for c in a.catalytic if c.chain == a.chains[0]]
        L += ["| residue | reference | role | conserved |", "|---|---|---|---|"]
        for c in first:
            ok = "yes" if c.found == c.expected else f"**no** ({c.found or 'absent'})"
            L.append(f"| {(c.found or c.expected).title()}{c.auth_seq_id} | {c.reference} | {c.roles} | {ok} |")
        L.append("")

    L += ["## Which chain to start from", "",
          f"| chain | blocking defects | findings within {ACTIVE_SITE_RADIUS:g} Å of the active site | "
          "catalytic residues intact |", "|---|---|---|---|"]
    for s in a.chain_summary:
        L.append(f"| {s.chain} | {s.blocks} | {s.near_site} | {'yes' if s.catalytic_intact else '**no**'} |")
    clean = [s.chain for s in a.chain_summary if s.blocks == 0 and s.catalytic_intact]
    L += ["", ("Chains with no blocking defect: " + ", ".join(clean) + "."
               if clean else "**Every chain has at least one blocking defect.**"), ""]

    titles = {"blocks": "Blocks a faithful setup", "decide": "Choices to make and record",
              "note": "Worth knowing"}
    for sev in ("blocks", "decide", "note"):
        fs = a.by_severity(sev)
        if not fs:
            continue
        L += [f"## {titles[sev]} ({len(fs)})", "",
              "| chain | where | Å to active site | finding | from |", "|---|---|---|---|---|"]
        fs = sorted(fs, key=lambda f: (f.distance if f.distance is not None else 1e9, f.chain or ""))
        for f in fs:
            L.append(f"| {f.chain or '-'} | {', '.join(f.residues) or '-'} | {_dist(f.distance)} | "
                     f"{f.what} | `{f.source}` |")
        L.append("")

    L += ["## Not checked", ""] + [f"- {n}" for n in a.not_checked] + [""]
    L += ["## Sources", ""]
    for key in ("pdb", "mcsa", "needleman-wunsch", "blosum62"):
        m = METHODS[key]
        L.append(f"- {m.what}: {m.cite()}")
    L += ["", f"Distances are to the nearest atom of a catalytic residue in the same chain; "
          f"{ACTIVE_SITE_RADIUS:g} Å is a chosen cutoff, not a physical boundary. Unmodelled "
          "stretches are placed by their observed flanking residues."]
    return L


def build_parser(prog: str = "caterva prepare") -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=prog,
        description=(
            "Audit a PDB entry as the starting point of a simulation: sequence "
            "differences from UniProt, chain breaks, truncated side chains, alternate "
            "conformations, non-standard residues, the biological assembly, and model "
            "quality -- each placed relative to the enzyme's catalytic residues (M-CSA)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            f"  {prog} 1I10\n"
            f"  {prog} 1L63 --out 1l63-audit.md --json 1l63-audit.json\n"
            f"  {prog} ./model.cif\n"
            "\nExit codes: 0 a clean chain exists, 4 every chain has a blocking defect, "
            "2 malformed question, 3 refused and said why, 1 a crash."
        ),
    )
    p.add_argument("entry", help="a PDB id (1I10) or a local mmCIF file")
    p.add_argument("--out", metavar="FILE", help="write the report here as well as printing it")
    p.add_argument("--json", metavar="FILE", help="write the findings as JSON")
    p.add_argument("--no-cache", action="store_true", help="fetch everything fresh")
    return p


def main(argv: Optional[Sequence[str]] = None, prog: str = "caterva prepare",
         fetch: Optional[Callable[[str], str]] = None) -> int:
    args = build_parser(prog).parse_args(argv)
    try:
        get = fetch or cached(live_fetch(), None if args.no_cache else _cache_dir())
        a = run_audit(args.entry, get)
    except PrepareError as e:
        print(f"caterva prepare: {e}", file=sys.stderr)
        return 3
    except Exception as e:  # a network failure is a refusal, not a crash
        if type(e).__module__.startswith("requests"):
            print(f"caterva prepare: could not reach the PDB or UniProt ({e})", file=sys.stderr)
            return 3
        raise
    text = "\n".join(report(a)) + "\n"
    print(text, end="")
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    if args.json:
        Path(args.json).write_text(json.dumps(asdict(a), indent=2, default=str), encoding="utf-8")
    clean = any(s.blocks == 0 and s.catalytic_intact for s in a.chain_summary)
    return 0 if clean else EXIT_BLOCKS


def console_main() -> int:
    return main()


if __name__ == "__main__":
    sys.exit(main())
