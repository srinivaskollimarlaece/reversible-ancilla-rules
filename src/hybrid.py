"""A hybrid carry look-ahead adder (Phase 11).

The design keeps what is cheap in the adder of Kumar et al. and replaces what
is slow:

  * Generate and propagate come from one Peres gate per bit, as in the PGA
    block of Kumar et al.: Peres(A_i, B_i, 0) leaves P_i = A_i xor B_i on the
    B line and G_i = A_i B_i on a fresh line.
  * The carry input is folded into the first generate bit with one Toffoli
    gate: G_0 := G_0 xor P_0 C_0. Every carry is then a group generate.
  * The carries come from the logarithmic-depth prefix network of Draper et
    al. (P-rounds, G-rounds and C-rounds), in place on the generate lines.
  * Unlike the Draper adder, nothing is uncomputed: the design is in the
    garbage style of Kumar et al., where only the sum and the carry-out are
    specified. This removes the inverse P-rounds and the restoring gates.
  * The sum is formed in place on the B lines: S_i = P_i xor C_i.

Lines: A (n, garbage), B (n, sum), carry input c0, generate lines z1..zn
(z_n is the carry-out, the others garbage) and the propagate ancillas of the
prefix network.
"""
from __future__ import annotations

from typing import List

from revcircuit import CNOT, Circuit, Gate, TOF
from adders import peres
from nadders import AdderDesign, _Lines, _interleaved


def hybrid_cla(n: int) -> AdderDesign:
    if n < 2:
        raise ValueError("n must be at least 2")
    log = n.bit_length() - 1                                  # floor(log2 n)
    L = _Lines()
    L.add("c0", *[x for i in range(n) for x in (f"a{i}", f"b{i}")], *[f"z{i}" for i in range(1, n + 1)])
    for t in range(1, log):
        L.add(*[f"p{t}_{m}" for m in range(1, n >> t)])

    def P(t, m):
        return L[f"b{m}"] if t == 0 else L[f"p{t}_{m}"]

    def Z(j):
        return L[f"z{j}"]

    gates: List[Gate] = []
    for i in range(n):                                        # PGA: Peres per bit
        gates += peres(L[f"a{i}"], L[f"b{i}"], Z(i + 1))
    gates.append(TOF(L["b0"], L["c0"], Z(1)))                 # fold the carry input into G_0
    rounds = {"P": 0, "G": 0, "C": 0}
    for t in range(1, log):                                   # P-rounds
        for m in range(1, n >> t):
            gates.append(TOF(P(t - 1, 2 * m), P(t - 1, 2 * m + 1), P(t, m)))
            rounds["P"] += 1
    for t in range(1, log + 1):                               # G-rounds
        for m in range(0, n >> t):
            gates.append(TOF(Z((m << t) + (1 << (t - 1))), P(t - 1, 2 * m + 1), Z((m << t) + (1 << t))))
            rounds["G"] += 1
    top = 0
    while 3 * (1 << (top + 1)) <= 2 * n:                      # floor(log2(2n/3))
        top += 1
    for t in range(top, 0, -1):                               # C-rounds
        for m in range(1, (n - (1 << (t - 1))) // (1 << t) + 1):
            gates.append(TOF(Z(m << t), P(t - 1, 2 * m), Z((m << t) + (1 << (t - 1)))))
            rounds["C"] += 1
    gates.append(CNOT(L["c0"], L["b0"]))                      # S_0 = P_0 xor C_0
    for i in range(1, n):
        gates.append(CNOT(Z(i), L[f"b{i}"]))                  # S_i = P_i xor C_i
    inputs = _interleaved(L, n, "c0")
    ancilla = [i for i, name in enumerate(L.names) if name not in inputs]
    design = AdderDesign(f"Hybrid CLA, {n} bits", "garbage", n, Circuit(len(L.names), gates), L.names,
                         inputs, ancilla, [L[f"b{i}"] for i in range(n)], Z(n), L["c0"], {}, [])
    design.rounds = rounds
    return design


def hybrid_bands(n: int):
    """(label, gates) per stage, for figures."""
    d = hybrid_cla(n)
    r = d.rounds
    bands = [("PGA", 2)] * n + [("cin", 1), ("P", r["P"]), ("G", r["G"]), ("C", r["C"]), ("sum", n)]
    return [(label, width) for label, width in bands if width]
