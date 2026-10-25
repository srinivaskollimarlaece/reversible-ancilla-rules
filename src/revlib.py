"""RevLib benchmark circuits (Phase 8).

Reads circuits in the RevLib ".real" format and prepares them for the
rule-based optimizer and for the ancilla- and garbage-aware simplifier.

The 20 files used here are RevLib circuits (www.revlib.org) as distributed
with the test suite of the MQT QCEC tool, release v1.10.0:
    https://github.com/cda-tum/mqt-qcec/tree/v1.10.0/test/circuits/original
fetch() downloads them with git when they are not present.

Constant inputs are taken from the ".constants" line of each file. The
".garbage" line is used for the four files that also name their outputs
(garbage outputs are called "g" there). In the other files, which come from
an ESOP-based synthesis, the garbage string is not ordered consistently, so
the function outputs f are taken as primary outputs and the input lines x as
garbage; this is the evident intent of those files.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional

from revcircuit import CNOT, Circuit, G, Gate

SOURCE = "https://github.com/cda-tum/mqt-qcec"
TAG = "v1.10.0"
SUBDIR = "test/circuits/original"


@dataclass
class Benchmark:
    name: str
    circuit: Circuit
    line_names: List[str]
    inputs: List[int]                  # lines with a free primary input
    ancilla: List[int]                 # lines with a constant input
    ancilla_ones: List[int]            # constant inputs that are 1
    outputs: Optional[List[int]]       # primary outputs, or None when the file gives none
    family: str                        # "esop", "bdd" or "plain"


def fetch(folder: str = "revlib") -> str:
    """Make sure the RevLib files are in `folder`; download them if needed."""
    if os.path.isdir(folder) and any(f.endswith(".real") for f in os.listdir(folder)):
        return folder
    clone = folder + "_clone"
    subprocess.run(["git", "-c", "advice.detachedHead=false", "clone", "-q", "--depth", "1",
                    "--branch", TAG, SOURCE, clone], check=True)
    os.makedirs(folder, exist_ok=True)
    source = os.path.join(clone, SUBDIR)
    for name in os.listdir(source):
        if name.endswith(".real"):
            with open(os.path.join(source, name), encoding="utf-8") as src, \
                    open(os.path.join(folder, name), "w", encoding="utf-8") as dst:
                dst.write(src.read())
    return folder


def parse_real(path: str) -> Optional[Benchmark]:
    """Read one .real file. Returns None if it uses gates other than Toffoli,
    Fredkin and Peres gates (for example controlled-V gates)."""
    header: Dict[str, List[str]] = {}
    body: List[List[str]] = []
    in_body = False
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.split("#")[0].strip()
            if not line:
                continue
            if line.lower() == ".begin":
                in_body = True
            elif line.lower() == ".end":
                in_body = False
            elif in_body:
                body.append(line.split())
            elif line.startswith("."):
                parts = line.split()
                header[parts[0].lower()] = parts[1:]
    names = header[".variables"]
    n = len(names)
    index = {name: i for i, name in enumerate(names)}

    def control(token: str):
        return (index[token[1:]], False) if token.startswith("-") else (index[token], True)

    gates: List[Gate] = []
    for tokens in body:
        kind, args = tokens[0].lower(), tokens[1:]
        if kind.startswith("t"):                                   # multiple-control Toffoli
            controls = [control(x) for x in args[:-1]]
            gates.append(G([l for l, p in controls if p], [l for l, p in controls if not p],
                           index[args[-1]]))
        elif kind.startswith("p"):                                 # Peres: Toffoli, then CNOT
            a, b, c = (index[x] for x in args)
            gates += [G([a, b], [], c), CNOT(a, b)]
        elif kind.startswith("f"):                                 # Fredkin: controlled swap
            controls = [control(x) for x in args[:-2]]
            x, y = index[args[-2]], index[args[-1]]
            pos = [l for l, p in controls if p]
            neg = [l for l, p in controls if not p]
            gates += [CNOT(y, x), G(pos + [x], neg, y), CNOT(y, x)]
        else:
            return None
    constants = "".join(header.get(".constants", ["-" * n]))
    garbage = "".join(header.get(".garbage", ["-" * n]))
    inputs = [i for i in range(n) if constants[i] == "-"]
    ancilla = [i for i in range(n) if constants[i] != "-"]
    ones = [i for i in range(n) if constants[i] == "1"]
    out_names = header.get(".outputs", [])
    if ".constants" not in header:
        family, outputs = "plain", None
    elif "g" in out_names:
        family, outputs = "bdd", [i for i in range(n) if garbage[i] == "-"]
    else:
        family, outputs = "esop", list(ancilla)
    name = os.path.basename(path)[:-len(".real")]
    return Benchmark(name, Circuit(n, gates), names, inputs, ancilla, ones, outputs, family)


def load_all(folder: str = "revlib") -> List[Benchmark]:
    """All usable benchmarks in the folder, sorted by name."""
    out = []
    for name in sorted(os.listdir(folder)):
        if name.endswith(".real"):
            bench = parse_real(os.path.join(folder, name))
            if bench is not None:
                out.append(bench)
    return out


# ---------------------------------------------------------------------------
# RevLib quantum cost
# ---------------------------------------------------------------------------
def _table(size: int, free: int) -> int:
    """Cost of a Toffoli gate on `size` lines when `free` other lines exist.

    This is the table used by RevLib. It reproduces the quantum cost printed
    in the header of 13 of the 14 files that state one; the last differs by 24.
    """
    if size <= 2:
        return 1
    if size == 3:
        return 5
    if size == 4:
        return 13
    if size == 5:
        return 26 if free >= 2 else 29
    rich = {6: (3, 38), 7: (4, 50), 8: (5, 62), 9: (6, 74), 10: (7, 86)}
    some = {6: 52, 7: 80, 8: 100, 9: 128, 10: 152}
    if size <= 10:
        need, low = rich[size]
        return low if free >= need else some[size] if free >= 1 else (1 << size) - 3
    return 12 * size - 34 if free >= size - 3 else 24 * size - 88 if free >= 1 else (1 << size) - 3


def revlib_cost(n: int):
    """Cost function for circuits on n lines, RevLib convention. Negative
    controls are priced like positive ones, except that a gate whose controls
    are all negative costs one more (the convention of this project)."""
    def cost(gate: Gate) -> int:
        size = len(gate.pos) + len(gate.neg) + 1
        extra = 1 if (gate.neg and not gate.pos) else 0
        return _table(size, n - size) + extra
    return cost
