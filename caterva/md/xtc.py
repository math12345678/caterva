"""GROMACS .xtc trajectories, read without GROMACS.

The format stores each frame's coordinates as integers at a stated
precision (usually 1/1000 nm), packed with a variable-width bit code in
which runs of close atoms (a water's three) are written as small offsets
from their neighbour. This is a direct implementation of the reference
decoder (xdr3dfcoord in the xdrfile library GROMACS ships, format by
Frans van Hoesel): the same magic-number table, the same bit and integer
unpacking, the same exchange of a run's first two atoms.

It is checked against GROMACS itself: every coordinate of a real
trajectory decodes to what `gmx trjconv` writes (see the tests).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Sequence

import numpy as np

MAGIC = 1995
FIRSTIDX = 9
MAGICINTS = (
    0, 0, 0, 0, 0, 0, 0, 0, 0, 8, 10, 12, 16, 20, 25, 32, 40, 50, 64,
    80, 101, 128, 161, 203, 256, 322, 406, 512, 645, 812, 1024, 1290,
    1625, 2048, 2580, 3250, 4096, 5060, 6501, 8192, 10321, 13003,
    16384, 20642, 26007, 32768, 41285, 52015, 65536, 82570, 104031,
    131072, 165140, 208063, 262144, 330280, 416127, 524287, 660561,
    832255, 1048576, 1321122, 1664510, 2097152, 2642245, 3329021,
    4194304, 5284491, 6658042, 8388607, 10568983, 13316085, 16777216,
)


@dataclass
class Frame:
    step: int
    time: float            # ps
    box: np.ndarray        # (3, 3) nm
    x: np.ndarray          # (natoms, 3) nm
    precision: float


class _Bits:
    """The decoder's bit reader: receivebits() of xdrfile.c."""

    __slots__ = ("buf", "cnt", "lastbits", "lastbyte")

    def __init__(self, buf: bytes):
        self.buf, self.cnt, self.lastbits, self.lastbyte = buf, 0, 0, 0

    def bits(self, nbits: int) -> int:
        mask = (1 << nbits) - 1
        num = 0
        buf, cnt, lastbits, lastbyte = self.buf, self.cnt, self.lastbits, self.lastbyte
        while nbits >= 8:
            lastbyte = ((lastbyte << 8) | buf[cnt]) & 0xFFFFFFFF
            cnt += 1
            num |= (lastbyte >> lastbits) << (nbits - 8)
            nbits -= 8
        if nbits > 0:
            if lastbits < nbits:
                lastbits += 8
                lastbyte = ((lastbyte << 8) | buf[cnt]) & 0xFFFFFFFF
                cnt += 1
            lastbits -= nbits
            num |= (lastbyte >> lastbits) & ((1 << nbits) - 1)
        self.cnt, self.lastbits, self.lastbyte = cnt, lastbits, lastbyte
        return num & mask

    def ints(self, nbits: int, sizes: Sequence[int]) -> List[int]:
        """receiveints() for three integers packed into nbits."""
        b = [0, 0, 0, 0]
        nbytes = 0
        while nbits > 8:
            v = self.bits(8)
            if nbytes < len(b):
                b[nbytes] = v
            else:
                b.append(v)
            nbytes += 1
            nbits -= 8
        if nbits > 0:
            v = self.bits(nbits)
            if nbytes < len(b):
                b[nbytes] = v
            else:
                b.append(v)
            nbytes += 1
        out = [0, 0, 0]
        for i in (2, 1):
            num = 0
            for j in range(nbytes - 1, -1, -1):
                num = (num << 8) | b[j]
                p = num // sizes[i]
                b[j] = p
                num -= p * sizes[i]
            out[i] = num
        out[0] = b[0] | (b[1] << 8) | (b[2] << 16) | (b[3] << 24)
        return out


def _sizeofint(size: int) -> int:
    num, bits = 1, 0
    while size >= num and bits < 32:
        bits += 1
        num <<= 1
    return bits


def _sizeofints(sizes: Sequence[int]) -> int:
    b = [1]
    for s in sizes:
        tmp = 0
        for k in range(len(b)):
            tmp = b[k] * s + tmp
            b[k] = tmp & 0xFF
            tmp >>= 8
        while tmp:
            b.append(tmp & 0xFF)
            tmp >>= 8
    nbits, num = 0, 1
    top = len(b) - 1
    while b[top] >= num:
        nbits += 1
        num *= 2
    return nbits + top * 8


def _coords(data: bytes, pos: int, natoms: int):
    """xdr3dfcoord(): (coordinates nm, precision, next position)."""
    (lsize,) = struct.unpack_from(">i", data, pos); pos += 4
    if lsize != natoms:
        raise ValueError(f"frame says {natoms} atoms, coordinate block {lsize}")
    if natoms <= 9:
        x = np.array(struct.unpack_from(f">{3 * natoms}f", data, pos)).reshape(natoms, 3)
        return x, 0.0, pos + 12 * natoms
    (precision,) = struct.unpack_from(">f", data, pos); pos += 4
    minint = struct.unpack_from(">3i", data, pos); pos += 12
    maxint = struct.unpack_from(">3i", data, pos); pos += 12
    sizeint = [maxint[k] - minint[k] + 1 for k in range(3)]
    if any(s > 0xFFFFFF for s in sizeint):
        bitsizeint = [_sizeofint(s) for s in sizeint]
        bitsize = 0
    else:
        bitsizeint = [0, 0, 0]
        bitsize = _sizeofints(sizeint)
    (smallidx,) = struct.unpack_from(">i", data, pos); pos += 4
    smaller = MAGICINTS[max(FIRSTIDX, smallidx - 1)] // 2
    smallnum = MAGICINTS[smallidx] // 2
    sizesmall = [MAGICINTS[smallidx]] * 3
    (nbytes,) = struct.unpack_from(">i", data, pos); pos += 4
    bits = _Bits(data[pos:pos + nbytes])
    pos += (nbytes + 3) // 4 * 4

    out = np.empty((natoms, 3), dtype=np.int64)
    o = 0
    i = 0
    run = 0
    while i < natoms:
        if bitsize == 0:
            this = [bits.bits(bitsizeint[k]) for k in range(3)]
        else:
            this = bits.ints(bitsize, sizeint)
        i += 1
        this = [this[k] + minint[k] for k in range(3)]
        prev = this
        flag = bits.bits(1)
        is_smaller = 0
        if flag == 1:
            run = bits.bits(5)
            is_smaller = run % 3
            run -= is_smaller
            is_smaller -= 1
        if run > 0:
            for k in range(0, run, 3):
                s = bits.ints(smallidx, sizesmall)
                i += 1
                cur = [s[m] + prev[m] - smallnum for m in range(3)]
                if k == 0:
                    # The encoder swapped a run's first two atoms (a water's O
                    # and first H compress better that way); swap them back.
                    cur, prev = prev, cur
                    out[o] = prev; o += 1
                else:
                    prev = cur
                out[o] = cur; o += 1
        else:
            out[o] = this; o += 1
        smallidx += is_smaller
        if is_smaller < 0:
            smallnum = smaller
            smaller = MAGICINTS[smallidx - 1] // 2 if smallidx > FIRSTIDX else 0
        elif is_smaller > 0:
            smaller = smallnum
            smallnum = MAGICINTS[smallidx] // 2
        sizesmall = [MAGICINTS[smallidx]] * 3
    if o != natoms:
        raise ValueError(f"decoded {o} atoms of {natoms}")
    return out / precision, float(precision), pos


def frames(path: Path) -> Iterator[Frame]:
    data = Path(path).read_bytes()
    pos = 0
    while pos < len(data):
        magic, natoms, step = struct.unpack_from(">3i", data, pos); pos += 12
        if magic != MAGIC:
            raise ValueError(f"{path}: magic {magic} at byte {pos - 12}, not an xtc frame "
                             f"(only the 1995 format is read)")
        (time,) = struct.unpack_from(">f", data, pos); pos += 4
        box = np.array(struct.unpack_from(">9f", data, pos)).reshape(3, 3); pos += 36
        x, prec, pos = _coords(data, pos, natoms)
        yield Frame(step, float(time), box, x, prec)


def read(path: Path) -> List[Frame]:
    return list(frames(path))


__all__ = ["Frame", "frames", "read", "MAGICINTS"]


# -- geometry across periodic boundaries ------------------------------------------

_SHIFTS = np.array([[i, j, k] for i in (-1, 0, 1) for j in (-1, 0, 1) for k in (-1, 0, 1)], float)


def nearest_image(d: np.ndarray, box: np.ndarray) -> np.ndarray:
    """The shortest periodic copy of each displacement in d (n, 3), for any
    GROMACS box (rows are the box vectors, triclinic included): the 27
    neighbouring lattice shifts are tried and the shortest kept."""
    d = np.atleast_2d(d)
    cand = d[:, None, :] + (_SHIFTS @ box)[None, :, :]
    best = np.argmin((cand ** 2).sum(-1), axis=1)
    return cand[np.arange(len(d)), best]


def make_whole(x: np.ndarray, box: np.ndarray) -> np.ndarray:
    """Coordinates of one molecule or chain made continuous: each atom is
    placed at the periodic copy nearest the atom before it. xtc files store
    atoms wherever the box put them, so a ligand or chain can arrive split."""
    out = x.copy()
    for i in range(1, len(out)):
        out[i] = out[i - 1] + nearest_image(out[i] - out[i - 1], box)[0]
    return out


def kabsch_fit(P: np.ndarray, Q: np.ndarray):
    """Rotation R, translation t minimising |P R + t - Q|; never a reflection."""
    pc, qc = P.mean(0), Q.mean(0)
    with np.errstate(all="ignore"):  # Accelerate BLAS flags finite products; checked below
        U, _, Vt = np.linalg.svd((P - pc).T @ (Q - qc))
        D = np.diag([1.0, 1.0, np.sign(np.linalg.det(Vt.T @ U.T))])
        R = U @ D @ Vt
    if not np.all(np.isfinite(R)):
        raise FloatingPointError("superposition produced a non-finite rotation")
    return R, qc - pc @ R


def rmsf(traj: Sequence[Frame], idx: Sequence[int], reference: np.ndarray) -> np.ndarray:
    """Root-mean-square fluctuation (nm) of the atoms `idx` about their mean,
    each frame made whole and superposed on `reference` (the same atoms)."""
    idx = list(idx)
    fitted = []
    for f in traj:
        x = make_whole(f.x[idx], f.box)
        R, t = kabsch_fit(x, reference)
        with np.errstate(all="ignore"):
            fitted.append(x @ R + t)
    X = np.array(fitted)
    return np.sqrt(((X - X.mean(0)) ** 2).sum(-1).mean(0))


__all__ += ["nearest_image", "make_whole", "kabsch_fit", "rmsf"]
