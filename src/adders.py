"""Reversible adders built from Feynman, Peres, TSG and R2 gates (Phase 4).

Two 4-bit adders are provided, each as a circuit of Toffoli-type gates:

  cla_adder()   carry look-ahead adder in the style of Kumar et al.,
                "An Optimised Design of a 4-bit Carry Look-Ahead Adder Using
                Novel Reversible Logic Gates", IACIS 2024.
  rca_adder()   ripple-carry adder from two Peres gates per bit.

IMPORTANT: the CLA netlist is a RECONSTRUCTION. The paper gives a block
diagram (its Fig. 6), not a netlist, and the diagram lets one signal feed
several blocks, which a reversible circuit cannot do without copy gates.
The circuit here follows the paper's building blocks and equations:

    PGA block   Peres(A_i, B_i, 0) gives P_i = A_i xor B_i and G_i = A_i B_i;
                Feynman(P_i, C_i) gives S_i = P_i xor C_i
    C1 = G0 xor P0 C0                               Peres + Feynman
    C2 = G1 xor P1 G0 xor P1 P0 C0                  Peres gates + TSG
    C3 = G2 xor P2 G1 xor P2 P1 G0 xor P2 P1 P0 C0  Peres gates + R2

and adds a Feynman copy gate wherever a signal is needed twice.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

from revcircuit import CNOT, Circuit, G, Gate, TOF

# Quantum cost of each block as stated in the adder paper.
PAPER_BLOCK_COST = {"Feynman": 1, "Peres": 4, "TSG": 17, "R2": 5}

# Figures the adder paper reports for its own design (its Table I).
PAPER_REPORTED = {"gates": 20, "ancilla": 14, "garbage": 14, "cost": 70, "trlic": 118}


# ---------------------------------------------------------------------------
# Gate library: each block as Toffoli-type gates, and its defining function
# ---------------------------------------------------------------------------
def feynman(a: int, b: int) -> List[Gate]:
    """Feynman gate: (A, B) -> (A, A xor B)."""
    return [CNOT(a, b)]


def peres(a: int, b: int, c: int) -> List[Gate]:
    """Peres gate: (A, B, C) -> (A, A xor B, AB xor C)."""
    return [TOF(a, b, c), CNOT(a, b)]


def tsg(a: int, b: int, c: int, d: int) -> List[Gate]:
    """TSG gate of Thapliyal and Srinivas: (A, B, C, D) -> (A, Q, Q xor D, QD xor AB xor C)
    with Q = A'C' xor B'. The outputs appear on lines a, b, d, c in that order."""
    return [TOF(a, b, c), CNOT(a, b), G([c], [a], b), TOF(b, d, c), CNOT(b, d)]


def r2(a: int, b: int, c: int, d: int) -> List[Gate]:
    """R2 gate: (A, B, C, D) -> (A, B, C, D xor A xor B xor C)."""
    return [CNOT(a, d), CNOT(b, d), CNOT(c, d)]


def feynman_ref(a, b):
    return a, a ^ b


def peres_ref(a, b, c):
    return a, a ^ b, (a & b) ^ c


def tsg_ref(a, b, c, d):
    q = ((1 - a) & (1 - c)) ^ (1 - b)
    return a, q, q ^ d, (q & d) ^ (a & b) ^ c


def r2_ref(a, b, c, d):
    return a, b, c, d ^ a ^ b ^ c


# ---------------------------------------------------------------------------
# A design: circuit plus the meaning of its lines
# ---------------------------------------------------------------------------
@dataclass
class Design:
    name: str
    circuit: Circuit
    line_names: List[str]
    inputs: Dict[str, int]                 # primary input name -> line
    ancilla: List[int]                     # lines that must start at 0
    outputs: Dict[str, int]                # primary output name -> line
    blocks: List[Tuple[str, Tuple[int, ...]]] = field(default_factory=list)

    @property
    def n(self) -> int:
        return self.circuit.n

    @property
    def garbage(self) -> List[int]:
        """Every output line that is not a primary output."""
        used = set(self.outputs.values())
        return [l for l in range(self.n) if l not in used]

    def block_count(self) -> int:
        return len(self.blocks)

    def block_cost(self) -> int:
        """Quantum cost with the block costs stated in the adder paper."""
        return sum(PAPER_BLOCK_COST[kind] for kind, _ in self.blocks)

    def block_summary(self) -> str:
        kinds = [kind for kind, _ in self.blocks]
        return ", ".join(f"{kinds.count(k)} {k}" for k in ("Peres", "Feynman", "TSG", "R2")
                         if k in kinds)

    def with_circuit(self, circuit: Circuit, name: str) -> "Design":
        """The same interface around another circuit (e.g. an optimized one)."""
        return Design(name, circuit, self.line_names, self.inputs, self.ancilla,
                      self.outputs, [])

    def run(self, values: Dict[str, int]) -> Dict[str, int]:
        """Simulate with the given primary input bits; ancilla lines start at 0."""
        state = sum(values[name] << line for name, line in self.inputs.items())
        out = self.circuit.apply(state)
        return {name: (out >> line) & 1 for name, line in self.outputs.items()}


class _Builder:
    def __init__(self, names: Sequence[str]) -> None:
        self.names = list(names)
        self.index = {name: i for i, name in enumerate(self.names)}
        self.gates: List[Gate] = []
        self.blocks: List[Tuple[str, Tuple[int, ...]]] = []

    def add(self, kind: str, *line_names: str) -> None:
        lines = tuple(self.index[name] for name in line_names)
        maker = {"Feynman": feynman, "Peres": peres, "TSG": tsg, "R2": r2}[kind]
        self.gates += maker(*lines)
        self.blocks.append((kind, lines))


# ---------------------------------------------------------------------------
# Carry look-ahead adder (reconstruction of Kumar et al.)
# ---------------------------------------------------------------------------
def cla_adder(carry_out: bool = False) -> Design:
    """4-bit reversible carry look-ahead adder.

    carry_out=False  the paper's block inventory: sum bits S0..S3 only.
    carry_out=True   the last Feynman gate is replaced by a Peres gate that
                     also produces the final carry C4 = G3 xor P3 C3.
    """
    names = ([f"a{i}" for i in range(4)] + [f"b{i}" for i in range(4)] + ["c0"]
             + [f"g{i}" for i in range(4)]            # G_i
             + ["k0", "k1", "k2", "k3"]               # copies
             + [f"t{i}" for i in range(1, 7)]         # product terms
             + ["z"])                                 # constant input of the TSG gate
    b = _Builder(names)
    for i in range(4):                                # PGA, Peres part: b_i = P_i, g_i = G_i
        b.add("Peres", f"a{i}", f"b{i}", f"g{i}")
    b.add("Feynman", "c0", "k0")                      # copy C0
    b.add("Feynman", "b0", "c0")                      # PGA 0, Feynman part: c0 = S0
    b.add("Peres", "b0", "k0", "t1")                  # t1 = P0 C0
    b.add("Feynman", "g0", "k1")                      # copy G0
    b.add("Feynman", "t1", "k1")                      # k1 = C1 = G0 xor P0 C0
    b.add("Peres", "b1", "g0", "t2")                  # t2 = P1 G0
    b.add("Peres", "b1", "t1", "t3")                  # t3 = P1 P0 C0
    b.add("Feynman", "b1", "k1")                      # PGA 1, Feynman part: k1 = S1
    b.add("Feynman", "g1", "k2")                      # copy G1
    b.add("Feynman", "t2", "k3")                      # copy P1 G0
    b.add("TSG", "t3", "k3", "z", "k2")               # k2 = C2 (three-input XOR)
    b.add("Peres", "b2", "g1", "t4")                  # t4 = P2 G1
    b.add("Peres", "b2", "t2", "t5")                  # t5 = P2 P1 G0
    b.add("Peres", "b2", "t3", "t6")                  # t6 = P2 P1 P0 C0
    b.add("Feynman", "b2", "k2")                      # PGA 2, Feynman part: k2 = S2
    b.add("R2", "t4", "t5", "t6", "g2")               # g2 = C3 (four-input XOR)
    outputs = {"s0": "c0", "s1": "k1", "s2": "k2", "s3": "g2"}
    if carry_out:
        b.add("Peres", "b3", "g2", "g3")              # g2 = S3, g3 = C4
        outputs["c4"] = "g3"
    else:
        b.add("Feynman", "b3", "g2")                  # PGA 3, Feynman part: g2 = S3
    ix = b.index
    return Design(
        name="CLA with carry-out" if carry_out else "CLA (paper style)",
        circuit=Circuit(len(names), b.gates), line_names=names,
        inputs={n: ix[n] for n in names[:9]},
        ancilla=[ix[n] for n in names[9:]],
        outputs={k: ix[v] for k, v in outputs.items()}, blocks=b.blocks)


# ---------------------------------------------------------------------------
# Ripple-carry adder: two Peres gates per bit
# ---------------------------------------------------------------------------
def rca_adder() -> Design:
    """4-bit reversible ripple-carry adder with carry-out.

    Per bit: Peres(A_i, B_i, 0) gives P_i and G_i, then Peres(P_i, C_i, G_i)
    gives S_i and C_(i+1) = G_i xor P_i C_i.
    """
    names = ([f"a{i}" for i in range(4)] + [f"b{i}" for i in range(4)] + ["c0"]
             + [f"z{i}" for i in range(4)])
    b = _Builder(names)
    carry = "c0"
    outputs = {}
    for i in range(4):
        b.add("Peres", f"a{i}", f"b{i}", f"z{i}")
        b.add("Peres", f"b{i}", carry, f"z{i}")
        outputs[f"s{i}"] = carry
        carry = f"z{i}"
    outputs["c4"] = carry
    ix = b.index
    return Design(
        name="Ripple-carry (Peres)", circuit=Circuit(len(names), b.gates), line_names=names,
        inputs={n: ix[n] for n in names[:9]}, ancilla=[ix[n] for n in names[9:]],
        outputs={k: ix[v] for k, v in outputs.items()}, blocks=b.blocks)


# ---------------------------------------------------------------------------
# Checks and measures
# ---------------------------------------------------------------------------
def check_adder(design: Design) -> Tuple[int, int]:
    """Test all 512 input combinations. Returns (cases tested, cases wrong)."""
    wrong = 0
    for a in range(16):
        for b in range(16):
            for c0 in range(2):
                values = {f"a{i}": (a >> i) & 1 for i in range(4)}
                values.update({f"b{i}": (b >> i) & 1 for i in range(4)})
                values["c0"] = c0
                out = design.run(values)
                total = a + b + c0
                good = all(out[f"s{i}"] == (total >> i) & 1 for i in range(4))
                if "c4" in out:
                    good = good and out["c4"] == (total >> 4) & 1
                wrong += not good
    return 512, wrong


def add(design: Design, a: int, b: int, c0: int = 0):
    """Add two 4-bit numbers with a design. Returns (sum, carry); carry is None
    when the design has no carry output."""
    values = {f"a{i}": (a >> i) & 1 for i in range(4)}
    values.update({f"b{i}": (b >> i) & 1 for i in range(4)})
    values["c0"] = c0
    out = design.run(values)
    total = sum(out[f"s{i}"] << i for i in range(4))
    return total, out.get("c4")


def depth(circuit: Circuit) -> int:
    """Number of time steps when gates on different lines run in parallel."""
    level = [0] * circuit.n
    for g in circuit:
        step = 1 + max(level[l] for l in g.lines)
        for l in g.lines:
            level[l] = step
    return max(level, default=0)
