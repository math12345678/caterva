"""A small mmCIF reader: the categories a preparation audit needs, nothing more.

Written rather than imported so `caterva prepare` installs anywhere the rest
of Caterva does. It reads the two shapes a PDBx/mmCIF file uses -- single
``_cat.item value`` pairs and ``loop_`` tables -- with the three quoting
forms the dictionary allows ('single', "double", and ;-delimited text
fields). It does not validate against the dictionary; RCSB files already
are.
"""
from __future__ import annotations

from typing import Dict, Iterator, List


Table = List[Dict[str, str]]


def _tokens(text: str) -> Iterator[str]:
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith(";"):
            # A text field runs to the next line that is exactly ';...'.
            buf = [line[1:]]
            i += 1
            while i < len(lines) and not lines[i].startswith(";"):
                buf.append(lines[i])
                i += 1
            yield "\n".join(buf).strip()
            i += 1
            continue
        j = 0
        n = len(line)
        while j < n:
            c = line[j]
            if c.isspace():
                j += 1
            elif c == "#":
                break
            elif c in "'\"":
                # A quote closes only when followed by whitespace or end.
                k = j + 1
                while k < n and not (line[k] == c and (k + 1 == n or line[k + 1].isspace())):
                    k += 1
                yield line[j + 1:k]
                j = k + 1
            else:
                k = j
                while k < n and not line[k].isspace():
                    k += 1
                yield line[j:k]
                j = k
        i += 1


def parse(text: str) -> Dict[str, Table]:
    """Every category in the first data block, as a list of rows.

    A category written as single pairs becomes a one-row table, so callers
    never need to know which form the file used.
    """
    out: Dict[str, Table] = {}
    toks = list(_tokens(text))
    i = 0
    while i < len(toks):
        t = toks[i]
        if t == "loop_":
            i += 1
            names: List[str] = []
            while i < len(toks) and toks[i].startswith("_"):
                names.append(toks[i])
                i += 1
            cat = names[0].split(".", 1)[0][1:]
            cols = [n.split(".", 1)[1] for n in names]
            rows = out.setdefault(cat, [])
            while i < len(toks) and not toks[i].startswith("_") and toks[i] != "loop_" \
                    and not toks[i].startswith("data_"):
                rows.append(dict(zip(cols, toks[i:i + len(cols)])))
                i += len(cols)
        elif t.startswith("_") and "." in t:
            cat, item = t[1:].split(".", 1)
            rows = out.setdefault(cat, [{}])
            rows[0][item] = toks[i + 1] if i + 1 < len(toks) else ""
            i += 2
        else:
            i += 1
    return out


def missing(value: str) -> bool:
    """mmCIF's two null markers: '?' unknown, '.' not applicable."""
    return value in ("?", ".", "")
