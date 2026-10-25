"""Reversible n-bit adders from the literature (Phase 8).

Six designs, each for any width n (cla4_blocks needs n divisible by 4):

  Garbage style: only the sum and carry lines are read at the end.
    cla4_blocks   4-bit carry look-ahead blocks in the style of Kumar et al.
                  (IACIS 2024), with the carry rippling from block to block.
                  The 4-bit block is a RECONSTRUCTION; see adders.py.
    tsg_rca       ripple-carry adder with one TSG gate per bit
                  (Thapliyal and Srinivas).
    peres_rca     ripple-carry adder with two Peres gates per bit.

  Clean style: every line is part of the specification. Operands are
  restored and every ancilla returns to 0, as quantum algorithms require.
    cuccaro       MAJ/UMA ripple-carry adder of Cuccaro et al., simple version.
    vbe           CARRY/SUM adder of Vedral, Barenco and Ekert.
    draper_qcla   out-of-place carry look-ahead adder of Draper et al.,
                  without carry input; logarithmic depth.

prove_adder() checks a design exactly for any width with decision diagrams.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from revcircuit import CNOT, Circuit, G, Gate, TOF
from adders import feynman, peres, r2, tsg
from bdd import BDD, Fn


@dataclass
class AdderDesign:
    name: str
    style: str                              # "garbage" or "clean"
    bits: int
    circuit: Circuit
    line_names: List[str]
    inputs: Dict[str, int]                  # primary inputs, in decision-diagram order
    ancilla: List[int]                      # lines that start at 0
    sum_lines: List[int]                    # line of S0, S1, ...
    carry_line: Optional[int]               # line of the carry-out
    carry_in: Optional[int]                 # line of the carry input, if it is a primary input
    restored: Dict[int, str]                # clean style: line -> input name it must equal again
    blocks: List[Tuple[str, tuple]] = field(default_factory=list)

    @property
    def n(self) -> int:
        return self.circuit.n

    @property
    def required(self) -> List[int]:
        """Lines whose final value is part of the specification."""
        if self.style == "clean":
            return list(range(self.n))
        return self.sum_lines + ([self.carry_line] if self.carry_line is not None else [])

    def with_circuit(self, circuit: Circuit) -> "AdderDesign":
        return AdderDesign(self.name, self.style, self.bits, circuit, self.line_names, self.inputs,
                           self.ancilla, self.sum_lines, self.carry_line, self.carry_in,
                           self.restored, [])


class _Lines:
    def __init__(self) -> None:
        self.names: List[str] = []
        self.index: Dict[str, int] = {}

    def add(self, *names: str) -> None:
        for name in names:
            self.index[name] = len(self.names)
            self.names.append(name)

    def __getitem__(self, name: str) -> int:
        return self.index[name]


def _interleaved(lines: _Lines, n: int, carry: Optional[str]) -> Dict[str, int]:
    order = ([carry] if carry else []) + [x for i in range(n) for x in (f"a{i}", f"b{i}")]
    return {name: lines[name] for name in order}


# ---------------------------------------------------------------------------
# Garbage-style designs
# ---------------------------------------------------------------------------
def cla4_blocks(n: int) -> AdderDesign:
    """Kumar-style 4-bit look-ahead blocks; the carry ripples between blocks."""
    if n % 4:
        raise ValueError("n must be a multiple of 4")
    L = _Lines()
    L.add(*[f"a{i}" for i in range(n)], *[f"b{i}" for i in range(n)], "c0",
          *[f"g{i}" for i in range(n)])
    for j in range(n // 4):
        L.add(*[f"k{m}_{j}" for m in range(4)], *[f"t{m}_{j}" for m in range(1, 7)], f"z_{j}")
    gates: List[Gate] = []
    blocks = []

    def add(kind, *names):
        ids = tuple(L[x] for x in names)
        gates.extend({"Feynman": feynman, "Peres": peres, "TSG": tsg, "R2": r2}[kind](*ids))
        blocks.append((kind, ids))

    sums = []
    cin = "c0"
    for j in range(n // 4):
        a = [f"a{4 * j + m}" for m in range(4)]
        b = [f"b{4 * j + m}" for m in range(4)]
        g = [f"g{4 * j + m}" for m in range(4)]
        k = [f"k{m}_{j}" for m in range(4)]
        t = [None] + [f"t{m}_{j}" for m in range(1, 7)]
        for m in range(4):
            add("Peres", a[m], b[m], g[m])              # b = P, g = G
        add("Feynman", cin, k[0])                       # copy the carry input
        add("Feynman", b[0], cin)                       # cin line = S(4j)
        add("Peres", b[0], k[0], t[1])                  # t1 = P0 C
        add("Feynman", g[0], k[1])
        add("Feynman", t[1], k[1])                      # k1 = C1
        add("Peres", b[1], g[0], t[2])
        add("Peres", b[1], t[1], t[3])
        add("Feynman", b[1], k[1])                      # k1 = S(4j+1)
        add("Feynman", g[1], k[2])
        add("Feynman", t[2], k[3])
        add("TSG", t[3], k[3], f"z_{j}", k[2])          # k2 = C2
        add("Peres", b[2], g[1], t[4])
        add("Peres", b[2], t[2], t[5])
        add("Peres", b[2], t[3], t[6])
        add("Feynman", b[2], k[2])                      # k2 = S(4j+2)
        add("R2", t[4], t[5], t[6], g[2])               # g2 = C3
        add("Peres", b[3], g[2], g[3])                  # g2 = S(4j+3), g3 = C(4j+4)
        sums += [L[cin], L[k[1]], L[k[2]], L[g[2]]]
        cin = g[3]
    inputs = _interleaved(L, n, "c0")
    ancilla = [i for i, name in enumerate(L.names) if name not in inputs]
    return AdderDesign(f"CLA blocks (Kumar style), {n} bits", "garbage", n,
                       Circuit(len(L.names), gates), L.names, inputs, ancilla, sums, L[cin],
                       L["c0"], {}, blocks)


def tsg_rca(n: int) -> AdderDesign:
    """One TSG gate per bit: TSG(A, B, 0, C) gives the sum on the carry line
    and the next carry on the constant line."""
    L = _Lines()
    L.add(*[f"a{i}" for i in range(n)], *[f"b{i}" for i in range(n)], "c0",
          *[f"z{i}" for i in range(n)])
    gates, blocks, sums = [], [], []
    carry = "c0"
    for i in range(n):
        ids = (L[f"a{i}"], L[f"b{i}"], L[f"z{i}"], L[carry])
        gates += tsg(*ids)
        blocks.append(("TSG", ids))
        sums.append(L[carry])
        carry = f"z{i}"
    inputs = _interleaved(L, n, "c0")
    ancilla = [L[f"z{i}"] for i in range(n)]
    return AdderDesign(f"TSG ripple-carry, {n} bits", "garbage", n, Circuit(len(L.names), gates),
                       L.names, inputs, ancilla, sums, L[carry], L["c0"], {}, blocks)


def peres_rca(n: int) -> AdderDesign:
    """Two Peres gates per bit."""
    L = _Lines()
    L.add(*[f"a{i}" for i in range(n)], *[f"b{i}" for i in range(n)], "c0",
          *[f"z{i}" for i in range(n)])
    gates, blocks, sums = [], [], []
    carry = "c0"
    for i in range(n):
        for ids in ((L[f"a{i}"], L[f"b{i}"], L[f"z{i}"]), (L[f"b{i}"], L[carry], L[f"z{i}"])):
            gates += peres(*ids)
            blocks.append(("Peres", ids))
        sums.append(L[carry])
        carry = f"z{i}"
    inputs = _interleaved(L, n, "c0")
    ancilla = [L[f"z{i}"] for i in range(n)]
    return AdderDesign(f"Peres ripple-carry, {n} bits", "garbage", n, Circuit(len(L.names), gates),
                       L.names, inputs, ancilla, sums, L[carry], L["c0"], {}, blocks)


# ---------------------------------------------------------------------------
# Clean designs
# ---------------------------------------------------------------------------
def cuccaro(n: int) -> AdderDesign:
    """MAJ/UMA ripple-carry adder of Cuccaro et al. (simple version).

    MAJ(x, y, w): CNOT(w, y), CNOT(w, x), Toffoli(x, y -> w).
    UMA(x, y, w): Toffoli(x, y -> w), CNOT(w, x), CNOT(x, y).
    The sum replaces b, a is restored, the ancilla c0 returns to 0 and the
    carry-out is added to z.
    """
    L = _Lines()
    L.add("c0", *[x for i in range(n) for x in (f"b{i}", f"a{i}")], "z")
    gates: List[Gate] = []

    def chain(i):
        x = "c0" if i == 0 else f"a{i - 1}"
        return L[x], L[f"b{i}"], L[f"a{i}"]

    for i in range(n):
        x, y, w = chain(i)
        gates += [CNOT(w, y), CNOT(w, x), TOF(x, y, w)]
    gates.append(CNOT(L[f"a{n - 1}"], L["z"]))
    for i in reversed(range(n)):
        x, y, w = chain(i)
        gates += [TOF(x, y, w), CNOT(w, x), CNOT(x, y)]
    inputs = _interleaved(L, n, None)
    return AdderDesign(f"Cuccaro ripple-carry, {n} bits", "clean", n, Circuit(len(L.names), gates),
                       L.names, inputs, [L["c0"], L["z"]], [L[f"b{i}"] for i in range(n)], L["z"],
                       None, {L[f"a{i}"]: f"a{i}" for i in range(n)})


def vbe(n: int) -> AdderDesign:
    """CARRY/SUM adder of Vedral, Barenco and Ekert.

    CARRY(c, a, b, c'): Toffoli(a, b -> c'), CNOT(a, b), Toffoli(c, b -> c').
    SUM(c, a, b): CNOT(a, b), CNOT(c, b).
    The sum replaces b, with the carry-out on the extra line b_n; a is
    restored and all carry lines return to 0.
    """
    L = _Lines()
    L.add(*[x for i in range(n) for x in (f"c{i}", f"a{i}", f"b{i}")], f"b{n}")

    def carry(i):
        c, a, b = L[f"c{i}"], L[f"a{i}"], L[f"b{i}"]
        nxt = L[f"c{i + 1}"] if i + 1 < n else L[f"b{n}"]
        return [TOF(a, b, nxt), CNOT(a, b), TOF(c, b, nxt)]

    def total(i):
        return [CNOT(L[f"a{i}"], L[f"b{i}"]), CNOT(L[f"c{i}"], L[f"b{i}"])]

    gates: List[Gate] = []
    for i in range(n):
        gates += carry(i)
    gates.append(CNOT(L[f"a{n - 1}"], L[f"b{n - 1}"]))
    gates += total(n - 1)
    for i in reversed(range(n - 1)):
        gates += carry(i)[::-1]
        gates += total(i)
    inputs = _interleaved(L, n, None)
    ancilla = [L[f"c{i}"] for i in range(n)] + [L[f"b{n}"]]
    return AdderDesign(f"VBE ripple-carry, {n} bits", "clean", n, Circuit(len(L.names), gates),
                       L.names, inputs, ancilla, [L[f"b{i}"] for i in range(n)], L[f"b{n}"], None,
                       {L[f"a{i}"]: f"a{i}" for i in range(n)})


def draper_qcla(n: int) -> AdderDesign:
    """Out-of-place carry look-ahead adder of Draper, Kutin, Rains and Svore,
    without carry input.

    Z[0..n] receives the sum and the carry-out. A and B are restored and the
    ancilla lines P_t[m] return to 0. G[j] is kept on Z[j] and P_0[i] on B[i].
    """
    if n < 2:
        raise ValueError("n must be at least 2")
    log = n.bit_length() - 1                                  # floor(log2 n)
    L = _Lines()
    L.add(*[x for i in range(n) for x in (f"a{i}", f"b{i}")], *[f"z{i}" for i in range(n + 1)])
    for t in range(1, log):
        L.add(*[f"p{t}_{m}" for m in range(1, n >> t)])

    def P(t, m):
        return L[f"b{m}"] if t == 0 else L[f"p{t}_{m}"]

    def Gn(j):
        return L[f"z{j}"]

    gates: List[Gate] = []
    for i in range(n):
        gates.append(TOF(L[f"a{i}"], L[f"b{i}"], Gn(i + 1)))             # generate bits
    for i in range(1, n):
        gates.append(CNOT(L[f"a{i}"], L[f"b{i}"]))                       # propagate bits
    p_rounds = [TOF(P(t - 1, 2 * m), P(t - 1, 2 * m + 1), P(t, m))
                for t in range(1, log) for m in range(1, n >> t)]
    gates += p_rounds
    for t in range(1, log + 1):                                          # G-rounds
        for m in range(0, n >> t):
            gates.append(TOF(Gn((m << t) + (1 << (t - 1))), P(t - 1, 2 * m + 1), Gn((m << t) + (1 << t))))
    top = 0
    while 3 * (1 << (top + 1)) <= 2 * n:                                 # floor(log2(2n/3))
        top += 1
    for t in range(top, 0, -1):                                          # C-rounds
        for m in range(1, (n - (1 << (t - 1))) // (1 << t) + 1):
            gates.append(TOF(Gn(m << t), P(t - 1, 2 * m), Gn((m << t) + (1 << (t - 1)))))
    gates += p_rounds[::-1]                                              # undo the P-rounds
    for i in range(n):
        gates.append(CNOT(L[f"b{i}"], L[f"z{i}"]))
    gates.append(CNOT(L["a0"], L["z0"]))
    for i in range(1, n):
        gates.append(CNOT(L[f"a{i}"], L[f"b{i}"]))                       # restore B
    inputs = _interleaved(L, n, None)
    ancilla = [i for i, name in enumerate(L.names) if name not in inputs]
    restored = {L[f"a{i}"]: f"a{i}" for i in range(n)}
    restored.update({L[f"b{i}"]: f"b{i}" for i in range(n)})
    return AdderDesign(f"Draper carry look-ahead, {n} bits", "clean", n,
                       Circuit(len(L.names), gates), L.names, inputs, ancilla,
                       [L[f"z{i}"] for i in range(n)], L[f"z{n}"], None, restored)


DESIGNS = {"cla4_blocks": cla4_blocks, "tsg_rca": tsg_rca, "peres_rca": peres_rca,
           "cuccaro": cuccaro, "vbe": vbe, "draper_qcla": draper_qcla}


# ---------------------------------------------------------------------------
# Exact proof and independent random test
# ---------------------------------------------------------------------------
def prove_adder(design: AdderDesign) -> bool:
    """Exact check for every input: sum, carry, restored lines, clean ancillas.

    All lines are simulated as decision diagrams over the primary inputs and
    compared with a reference adder built from the textbook recurrence.
    """
    names = list(design.inputs)
    bdd = BDD(len(names))
    var = {name: Fn(bdd, bdd.var(i)) for i, name in enumerate(names)}
    zero = Fn(bdd, 0)
    v = [zero] * design.n
    for name, line in design.inputs.items():
        v[line] = var[name]
    for g in design.circuit:
        act = Fn(bdd, 1)
        for l in g.pos:
            act = act & v[l]
        for l in g.neg:
            act = act & ~v[l]
        v[g.target] = v[g.target] ^ act
    carry = var["c0"] if design.carry_in is not None else zero
    for i in range(design.bits):
        a, b = var[f"a{i}"], var[f"b{i}"]
        if v[design.sum_lines[i]] != a ^ b ^ carry:
            return False
        carry = (a & b) ^ ((a ^ b) & carry)
    if design.carry_line is not None and v[design.carry_line] != carry:
        return False
    if design.style == "clean":
        for line, name in design.restored.items():
            if v[line] != var[name]:
                return False
        special = set(design.sum_lines) | {design.carry_line} | set(design.restored)
        if any(v[l] != zero for l in design.ancilla if l not in special):
            return False
    return True


def random_test(design: AdderDesign, trials: int = 2000, seed: int = 1) -> int:
    """Independent check with the plain simulator. Returns the number of wrong sums."""
    rng = random.Random(seed)
    n, wrong = design.bits, 0
    full = (1 << n) - 1
    corner = [(0, 0, 0), (full, 1, 0), (full, full, 1), (full, 0, 1), (1, full, 0)]
    for k in range(trials):
        a, b, c = corner[k] if k < len(corner) else (rng.getrandbits(n), rng.getrandbits(n), rng.getrandbits(1))
        if design.carry_in is None:
            c = 0
        state = 0
        for i in range(n):
            state |= ((a >> i) & 1) << design.inputs[f"a{i}"]
            state |= ((b >> i) & 1) << design.inputs[f"b{i}"]
        if design.carry_in is not None:
            state |= c << design.carry_in
        out = design.circuit.apply(state)
        total = a + b + c
        got = sum(((out >> line) & 1) << i for i, line in enumerate(design.sum_lines))
        if design.carry_line is not None:
            got |= ((out >> design.carry_line) & 1) << n
        else:
            total &= full
        wrong += got != total
    return wrong


# ---------------------------------------------------------------------------
# Measures
# ---------------------------------------------------------------------------
def toffoli_count(circuit: Circuit) -> int:
    """Gates with exactly two controls. Larger gates are not expected in adders."""
    if any(len(g.controls) > 2 for g in circuit):
        raise ValueError("a gate has more than two controls; T-count is not defined here")
    return sum(1 for g in circuit if len(g.controls) == 2)


def t_count(circuit: Circuit) -> int:
    """7 T gates per two-control Toffoli-type gate; NOT and CNOT are free."""
    return 7 * toffoli_count(circuit)


def toffoli_depth(circuit: Circuit) -> int:
    """Depth counting only two-control gates; NOT and CNOT take no time."""
    level = [0] * circuit.n
    for g in circuit:
        step = max(level[l] for l in g.lines) + (1 if len(g.controls) >= 2 else 0)
        for l in g.lines:
            level[l] = step
    return max(level, default=0)


def used_ancilla(design: AdderDesign, circuit: Optional[Circuit] = None) -> int:
    circuit = design.circuit if circuit is None else circuit
    touched = set()
    for g in circuit:
        touched |= g.lines
    return len(touched & set(design.ancilla))
