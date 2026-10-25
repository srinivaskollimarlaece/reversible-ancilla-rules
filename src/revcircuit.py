"""Reversible circuit model and simulator (Phase 1).

Gates are mixed-polarity multiple-control Toffoli (MPMCT) gates, written
G[P, N, q] as in Feng and Li, "A Complete Set of Transformation Rules for
Reversible Circuits", IEEE TCAD, 2026:

    P  set of positive control lines
    N  set of negative control lines
    q  target line

The gate flips q when every line in P is 1 and every line in N is 0.
Special cases: X[q] = G[{}, {}, q], CNOT[p, q] = G[{p}, {}, q], and a
Toffoli gate is G[{a, b}, {}, q].

A basis state is stored as an integer whose bit i is the value of line q_i.
A circuit is a list of gates; the leftmost gate executes first.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from itertools import product
from typing import Iterable, Iterator, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Gate:
    """One MPMCT gate G[pos, neg, target]."""

    pos: frozenset
    neg: frozenset
    target: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "pos", frozenset(self.pos))
        object.__setattr__(self, "neg", frozenset(self.neg))
        if self.pos & self.neg:
            raise ValueError("a line cannot be both a positive and a negative control")
        if self.target in self.pos or self.target in self.neg:
            raise ValueError("the target line cannot also be a control")
        if min(self.lines) < 0:
            raise ValueError("line numbers must be non-negative")
        # Bit masks used by the simulator.
        object.__setattr__(self, "_pmask", sum(1 << l for l in self.pos))
        object.__setattr__(self, "_nmask", sum(1 << l for l in self.neg))
        object.__setattr__(self, "_tmask", 1 << self.target)

    @property
    def controls(self) -> frozenset:
        return self.pos | self.neg

    @property
    def lines(self) -> frozenset:
        return self.pos | self.neg | {self.target}

    def apply(self, state: int) -> int:
        """Return the state after this gate acts on `state`."""
        if (state & self._pmask) == self._pmask and not (state & self._nmask):
            return state ^ self._tmask
        return state

    def __str__(self) -> str:
        t = self.target
        if not self.neg:
            if not self.pos:
                return f"X[q{t}]"
            if len(self.pos) == 1:
                (c,) = self.pos
                return f"CNOT[q{c},q{t}]"

        def fmt(s: frozenset) -> str:
            return "{" + ",".join(f"q{l}" for l in sorted(s)) + "}"

        return f"G[{fmt(self.pos)},{fmt(self.neg)},q{t}]"


def G(pos: Iterable[int], neg: Iterable[int], target: int) -> Gate:
    """General gate G[P, N, q]."""
    return Gate(frozenset(pos), frozenset(neg), target)


def X(q: int) -> Gate:
    """NOT gate on line q."""
    return Gate(frozenset(), frozenset(), q)


def CNOT(control: int, target: int) -> Gate:
    """Controlled-NOT (Feynman gate)."""
    return Gate(frozenset({control}), frozenset(), target)


def TOF(c1: int, c2: int, target: int) -> Gate:
    """Toffoli gate with two positive controls."""
    return Gate(frozenset({c1, c2}), frozenset(), target)


def MCT(controls: Iterable[int], target: int) -> Gate:
    """Multiple-control Toffoli gate with positive controls only."""
    return Gate(frozenset(controls), frozenset(), target)


# ---------------------------------------------------------------------------
# Circuit
# ---------------------------------------------------------------------------
class Circuit:
    """A reversible circuit on n lines: an ordered list of gates."""

    def __init__(self, n: int, gates: Iterable[Gate] = ()) -> None:
        self.n = n
        self.gates: List[Gate] = list(gates)
        for g in self.gates:
            if max(g.lines) >= n:
                raise ValueError(f"gate {g} uses a line outside q0..q{n - 1}")

    # -- container behaviour ------------------------------------------------
    def __len__(self) -> int:
        return len(self.gates)

    def __getitem__(self, i: int) -> Gate:
        return self.gates[i]

    def __iter__(self) -> Iterator[Gate]:
        return iter(self.gates)

    def __eq__(self, other: object) -> bool:
        """Structural equality: same lines and the same gate list."""
        return isinstance(other, Circuit) and self.n == other.n and self.gates == other.gates

    def __add__(self, other: "Circuit") -> "Circuit":
        """Concatenation: self executes first, then other."""
        if self.n != other.n:
            raise ValueError("circuits must have the same number of lines")
        return Circuit(self.n, self.gates + other.gates)

    def __str__(self) -> str:
        return " ".join(str(g) for g in self.gates) if self.gates else "(empty)"

    def copy(self) -> "Circuit":
        return Circuit(self.n, self.gates)

    def replace(self, i: int, j: int, new_gates: Sequence[Gate]) -> "Circuit":
        """Return a new circuit with gates[i:j] replaced by new_gates."""
        return Circuit(self.n, self.gates[:i] + list(new_gates) + self.gates[j:])

    def inverse(self) -> "Circuit":
        """Every gate is its own inverse, so the inverse is the reversed list."""
        return Circuit(self.n, reversed(self.gates))

    # -- simulation ---------------------------------------------------------
    def apply(self, state: int) -> int:
        for g in self.gates:
            state = g.apply(state)
        return state

    def permutation(self) -> Tuple[int, ...]:
        """The reversible function computed, as a tuple over all 2^n states."""
        return tuple(self.apply(s) for s in range(1 << self.n))

    def equivalent(self, other: "Circuit") -> bool:
        """Functional equivalence: both circuits compute the same function."""
        return self.n == other.n and self.permutation() == other.permutation()

    # -- display ------------------------------------------------------------
    def _bits(self, state: int) -> str:
        return " ".join(str((state >> i) & 1) for i in range(self.n))

    def truth_table(self) -> str:
        head = " ".join(f"q{i}" for i in range(self.n))
        rows = [f"{head} | {head}"]
        for s, t in enumerate(self.permutation()):
            pad = "  ".join(self._bits(s).split())
            out = "  ".join(self._bits(t).split())
            rows.append(f" {pad} |  {out}")
        return "\n".join(rows)

    def draw(self) -> str:
        """Text drawing: circled plus = target, filled dot = positive control, open dot = negative control."""
        width = len(f"q{self.n - 1}")
        rows = []
        for r in range(self.n):
            cells = []
            for g in self.gates:
                lo, hi = min(g.lines), max(g.lines)
                if r == g.target:
                    ch = "\u2295"  # target
                elif r in g.pos:
                    ch = "\u25cf"  # filled dot
                elif r in g.neg:
                    ch = "\u25cb"  # open dot
                elif lo < r < hi:
                    ch = "\u253c"  # wire crossing a gate
                else:
                    ch = "\u2500"
                cells.append("\u2500" + ch + "\u2500")
            rows.append(f"q{r}:".ljust(width + 2) + "\u2500" + "".join(cells) + "\u2500")
        return "\n".join(rows)


# ---------------------------------------------------------------------------
# Helpers for experiments
# ---------------------------------------------------------------------------
def pn_choices(lines: Sequence[int]) -> Iterator[Tuple[frozenset, frozenset]]:
    """All ways to make each given line absent, a positive or a negative control."""
    for states in product((0, 1, 2), repeat=len(lines)):
        pos = frozenset(l for l, s in zip(lines, states) if s == 1)
        neg = frozenset(l for l, s in zip(lines, states) if s == 2)
        yield pos, neg


def all_gates(n: int) -> List[Gate]:
    """Every MPMCT gate on n lines: n * 3^(n-1) gates."""
    gates = []
    for target in range(n):
        others = [l for l in range(n) if l != target]
        for pos, neg in pn_choices(others):
            gates.append(Gate(pos, neg, target))
    return gates


def random_gate(n: int, rng: Optional[random.Random] = None) -> Gate:
    rng = rng or random
    target = rng.randrange(n)
    pos, neg = set(), set()
    for l in range(n):
        if l == target:
            continue
        s = rng.randrange(3)
        if s == 1:
            pos.add(l)
        elif s == 2:
            neg.add(l)
    return Gate(frozenset(pos), frozenset(neg), target)


def random_circuit(n: int, length: int, rng: Optional[random.Random] = None) -> Circuit:
    return Circuit(n, [random_gate(n, rng) for _ in range(length)])
