"""Global alignment, used to carry catalytic residues onto the protein asked about.

M-CSA curates one reference enzyme per mechanism. The structure a lab wants
to simulate is usually a homologue (human LDH-A, against M-CSA's dogfish
reference), so a reference position means nothing until it is mapped.

Needleman & Wunsch (1970) with the BLOSUM62 matrix (Henikoff & Henikoff
1992) and affine gaps (open 11, extend 1, the BLAST defaults). Quadratic in
time and memory, which is fine for single chains of a few hundred residues.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

_ORDER = "ARNDCQEGHILKMFPSTWYV"
_ROWS = """
 4 -1 -2 -2  0 -1 -1  0 -2 -1 -1 -1 -1 -2 -1  1  0 -3 -2  0
-1  5  0 -2 -3  1  0 -2  0 -3 -2  2 -1 -3 -2 -1 -1 -3 -2 -3
-2  0  6  1 -3  0  0  0  1 -3 -3  0 -2 -3 -2  1  0 -4 -2 -3
-2 -2  1  6 -3  0  2 -1 -1 -3 -4 -1 -3 -3 -1  0 -1 -4 -3 -3
 0 -3 -3 -3  9 -3 -4 -3 -3 -1 -1 -3 -1 -2 -3 -1 -1 -2 -2 -1
-1  1  0  0 -3  5  2 -2  0 -3 -2  1  0 -3 -1  0 -1 -2 -1 -2
-1  0  0  2 -4  2  5 -2  0 -3 -3  1 -2 -3 -1  0 -1 -3 -2 -2
 0 -2  0 -1 -3 -2 -2  6 -2 -4 -4 -2 -3 -3 -2  0 -2 -2 -3 -3
-2  0  1 -1 -3  0  0 -2  8 -3 -3 -1 -2 -1 -2 -1 -2 -2  2 -3
-1 -3 -3 -3 -1 -3 -3 -4 -3  4  2 -3  1  0 -3 -2 -1 -3 -1  3
-1 -2 -3 -4 -1 -2 -3 -4 -3  2  4 -2  2  0 -3 -2 -1 -2 -1  1
-1  2  0 -1 -3  1  1 -2 -1 -3 -2  5 -1 -3 -1  0 -1 -3 -2 -2
-1 -1 -2 -3 -1  0 -2 -3 -2  1  2 -1  5  0 -2 -1 -1 -1 -1  1
-2 -3 -3 -3 -2 -3 -3 -3 -1  0  0 -3  0  6 -4 -2 -2  1  3 -1
-1 -2 -2 -1 -3 -1 -1 -2 -2 -3 -3 -1 -2 -4  7 -1 -1 -4 -3 -2
 1 -1  1  0 -1  0  0  0 -1 -2 -2  0 -1 -2 -1  4  1 -3 -2 -2
 0 -1  0 -1 -1 -1 -1 -2 -2 -1 -1 -1 -1 -2 -1  1  5 -2 -2  0
-3 -3 -4 -4 -2 -2 -3 -2 -2 -3 -2 -3 -1  1 -4 -3 -2 11  2 -3
-2 -2 -2 -3 -2 -1 -2 -3  2 -1 -1 -2 -1  3 -3 -2 -2  2  7 -1
 0 -3 -3 -3 -1 -2 -2 -3 -3  3  1 -2  1 -1 -2 -2  0 -3 -1  4
"""
BLOSUM62: Dict[Tuple[str, str], int] = {}
for _a, _row in zip(_ORDER, _ROWS.strip().splitlines()):
    for _b, _v in zip(_ORDER, _row.split()):
        BLOSUM62[(_a, _b)] = int(_v)

GAP_OPEN = 11
GAP_EXTEND = 1


def _score(a: str, b: str) -> int:
    # Non-standard letters (X, U, B, Z) score as a mild mismatch.
    return BLOSUM62.get((a, b), -1)


@dataclass(frozen=True)
class Alignment:
    #: query position (1-based) -> target position (1-based), aligned pairs only
    mapping: Dict[int, int]
    identity: float  # identical pairs / shorter sequence length
    aligned: int

    def target_of(self, query_pos: int) -> Optional[int]:
        return self.mapping.get(query_pos)


def align(query: str, target: str) -> Alignment:
    """Global affine-gap alignment; returns the position map and identity."""
    n, m = len(query), len(target)
    neg = float("-inf")
    # M: ends in a pair; X: gap in target (query residue unpaired); Y: gap in query.
    M = [[neg] * (m + 1) for _ in range(n + 1)]
    X = [[neg] * (m + 1) for _ in range(n + 1)]
    Y = [[neg] * (m + 1) for _ in range(n + 1)]
    M[0][0] = 0.0
    for i in range(1, n + 1):
        X[i][0] = -GAP_OPEN - (i - 1) * GAP_EXTEND
    for j in range(1, m + 1):
        Y[0][j] = -GAP_OPEN - (j - 1) * GAP_EXTEND
    for i in range(1, n + 1):
        qi = query[i - 1]
        Mi, Xi, Yi = M[i], X[i], Y[i]
        Mp, Xp, Yp = M[i - 1], X[i - 1], Y[i - 1]
        for j in range(1, m + 1):
            s = _score(qi, target[j - 1])
            Mi[j] = max(Mp[j - 1], Xp[j - 1], Yp[j - 1]) + s
            Xi[j] = max(Mp[j] - GAP_OPEN, Xp[j] - GAP_EXTEND)
            Yi[j] = max(Mi[j - 1] - GAP_OPEN, Yi[j - 1] - GAP_EXTEND)
    # Traceback.
    i, j = n, m
    state = max((M[n][m], 0), (X[n][m], 1), (Y[n][m], 2))[1]
    mapping: Dict[int, int] = {}
    same = 0
    while i > 0 or j > 0:
        if state == 0 and i > 0 and j > 0:
            mapping[i] = j
            if query[i - 1] == target[j - 1]:
                same += 1
            s = _score(query[i - 1], target[j - 1])
            prev = M[i][j] - s
            i, j = i - 1, j - 1
            state = 0 if M[i][j] == prev else (1 if X[i][j] == prev else 2)
        elif state == 1 and i > 0:
            state = 0 if (j > 0 or i > 1) and M[i - 1][j] - GAP_OPEN == X[i][j] else 1
            i -= 1
        elif j > 0:
            state = 0 if M[i][j - 1] - GAP_OPEN == Y[i][j] else 2
            j -= 1
        else:
            state = 1
    shorter = max(1, min(n, m))
    return Alignment(mapping=mapping, identity=same / shorter, aligned=len(mapping))


THREE_TO_ONE = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q",
    "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K",
    "MET": "M", "PHE": "F", "PRO": "P", "SER": "S", "THR": "T", "TRP": "W",
    "TYR": "Y", "VAL": "V",
}


def one_letter(code3: str) -> str:
    return THREE_TO_ONE.get(code3.upper(), "X")


__all__ = ["Alignment", "align", "one_letter", "BLOSUM62", "THREE_TO_ONE"]
