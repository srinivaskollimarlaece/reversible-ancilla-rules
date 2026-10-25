"""Heuristic rule-based optimizer for reversible circuits (Phase 3).

The optimizer rewrites a circuit with the transformation rules of Feng and
Li (IEEE TCAD, 2026) until the cost stops falling. One search step takes a
gate, moves it along the circuit, and looks for a partner it can cancel or
merge with.

Moves that remove gates
    Rule 1          A A                      ->  (nothing)
    Rule 2          G[P,N+p,q] G[P+p,N,q]    ->  G[P,N,q]
    Rule 2 + 1      G[P,N,q]   G[P+p,N,q]    ->  G[P,N+p,q]      ("absorb")
    Rule 5          the 2m+3 gate pattern    ->  2m-1 gates

Moves that carry a gate past its neighbour
    Rule 7          same target: the gates commute
    Rule 3          a shared control of opposite polarity: they commute
    D1 (derived)    neither target is a control of the other: they commute
    Rule 9          the gate passes; a control polarity flips in one gate
    D2 (derived)    the gate passes and leaves one extra gate behind

D1 and D2 are not listed in the paper. Both are sound (verify_phase3.py
checks every instance on 2 to 4 lines), so by the completeness theorem of
the paper they follow from Rules 1 to 5. Rule 9 is the special case of D2
in which the extra gate merges with its neighbour.

Every accepted rewrite strictly lowers the objective, so the search stops.
With check=True each rewrite is also verified by simulating the replaced
gates and the new gates on the lines they use.
"""
from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple

from revcircuit import Circuit, G, Gate
import rules as R

CostFn = Callable[[Gate], int]


# ---------------------------------------------------------------------------
# Cost model
# ---------------------------------------------------------------------------
def quantum_cost(gate: Gate) -> int:
    """Quantum cost of one mixed-polarity multiple-control Toffoli gate.

    Controls:  0   1   2   3    4    5   ...   c
    Cost:      1   1   5   13   29   61  ...   2^(c+1) - 3

    This is the count of elementary gates in the decomposition of Barenco et
    al. (1995) without ancilla lines. Negative controls are free, except that
    a gate whose controls are ALL negative costs one more. The model is a
    stated assumption of this project; pass another function to change it.
    """
    c = len(gate.pos) + len(gate.neg)
    cost = 1 if c <= 1 else (1 << (c + 1)) - 3
    if c >= 1 and not gate.pos:
        cost += 1
    return cost


def circuit_cost(circuit, cost: CostFn = quantum_cost) -> int:
    """Total quantum cost of a circuit or a list of gates."""
    return sum(cost(g) for g in circuit)


# ---------------------------------------------------------------------------
# Elementary moves
# ---------------------------------------------------------------------------
def reduce_pair(a: Gate, b: Gate) -> Optional[Tuple[List[Gate], str]]:
    """Replace two gates with the same target by at most one gate, if possible."""
    if a.target != b.target:
        return None
    if a == b:
        return [], "Rule 1"
    la, lb = a.controls, b.controls
    if la == lb:
        differ = a.pos ^ b.pos                      # lines with opposite polarity
        if len(differ) == 1:
            (p,) = differ
            return [G(a.pos - {p}, a.neg - {p}, a.target)], "Rule 2"
    elif len(la ^ lb) == 1:
        big, small = (a, b) if len(la) > len(lb) else (b, a)
        (p,) = big.controls - small.controls
        if big.pos - {p} == small.pos and big.neg - {p} == small.neg:
            return [_flip(big, p)], "Rule 2 + 1"
    return None


def _flip(gate: Gate, p: int) -> Gate:
    """The same gate with the polarity of control p reversed."""
    if p in gate.pos:
        return G(gate.pos - {p}, gate.neg | {p}, gate.target)
    return G(gate.pos | {p}, gate.neg - {p}, gate.target)


def commute_tag(a: Gate, b: Gate) -> Optional[str]:
    """Name of the rule by which two adjacent gates commute, or None."""
    if a.target == b.target:
        return "Rule 7"
    if (a.pos & b.neg) or (a.neg & b.pos):
        return "Rule 3"
    if a.target not in b.controls and b.target not in a.controls:
        return "D1"
    return None


def induced_gate(a: Gate, b: Gate) -> Optional[Gate]:
    """The extra gate of rule D2.

    A = G[P1,N1,p] writes line p, and B = G[..p.., q] reads it. Then
        A B  ==  B B'' A      and      B A  ==  A B'' B
    with B'' = G[P1 + P2, N1 + N2, q], where P2, N2 are the controls of B
    other than p. Returns None when the rule does not apply.
    """
    p, q = a.target, b.target
    if p not in b.controls or q in a.controls:
        return None
    pos, neg = a.pos | (b.pos - {p}), a.neg | (b.neg - {p})
    if pos & neg:
        return None                                  # then Rule 3 applies instead
    return G(pos, neg, q)


def pass_gate(moving: Gate, fixed: Gate) -> Optional[Tuple[List[Gate], Gate, str, int]]:
    """Carry `moving` from the left of `fixed` to its right.

    Returns (gates left behind, the moving gate afterwards, rule, extra gates)
    or None when neither Rule 9 nor D2 applies.
    """
    extra = induced_gate(moving, fixed)              # moving writes, fixed reads
    if extra is not None:
        merged = reduce_pair(fixed, extra)
        if merged is not None:
            return merged[0], moving, "Rule 9", 0
        return [fixed, extra], moving, "D2", 1
    extra = induced_gate(fixed, moving)              # fixed writes, moving reads
    if extra is not None:
        merged = reduce_pair(extra, moving)
        if merged is not None:
            return [fixed], merged[0][0], "Rule 9", 0
        return [fixed, extra], moving, "D2", 1
    return None


# ---------------------------------------------------------------------------
# Checking one rewrite
# ---------------------------------------------------------------------------
def same_function(old: Sequence[Gate], new: Sequence[Gate],
                  rng: Optional[random.Random] = None, limit: int = 12) -> bool:
    """True when two gate lists act identically on the lines they use.

    Exhaustive for up to `limit` lines; beyond that, 4096 random states.
    """
    lines = sorted(set().union(*(g.lines for g in list(old) + list(new)))) if (old or new) else []
    index = {l: i for i, l in enumerate(lines)}

    def remap(gates):
        return [G([index[l] for l in g.pos], [index[l] for l in g.neg], index[g.target])
                for g in gates]

    a, b = remap(old), remap(new)
    k = len(lines)
    if k <= limit:
        states = range(1 << k)
    else:
        rng = rng or random.Random(0)
        states = [rng.getrandbits(k) for _ in range(4096)]
    for s in states:
        x = y = s
        for g in a:
            x = g.apply(x)
        for g in b:
            y = g.apply(y)
        if x != y:
            return False
    return True


# ---------------------------------------------------------------------------
# The optimizer
# ---------------------------------------------------------------------------
@dataclass
class OptimizationResult:
    original: Circuit
    circuit: Circuit
    rule_counts: Counter = field(default_factory=Counter)
    rewrites: int = 0
    passes: int = 0
    cost_fn: CostFn = quantum_cost

    @property
    def gates_before(self) -> int:
        return len(self.original)

    @property
    def gates_after(self) -> int:
        return len(self.circuit)

    @property
    def cost_before(self) -> int:
        return circuit_cost(self.original, self.cost_fn)

    @property
    def cost_after(self) -> int:
        return circuit_cost(self.circuit, self.cost_fn)

    def summary(self) -> str:
        def change(before, after):
            pct = 100.0 * (before - after) / before if before else 0.0
            return f"{before} -> {after} ({pct:.1f}% lower)"

        lines = [f"Gate count:   {change(self.gates_before, self.gates_after)}",
                 f"Quantum cost: {change(self.cost_before, self.cost_after)}",
                 f"Rewrites accepted: {self.rewrites} in {self.passes} passes"]
        if self.rule_counts:
            lines.append("Rule usage: " + ", ".join(
                f"{name} x{count}" for name, count in sorted(self.rule_counts.items())))
        return "\n".join(lines)


class _Search:
    def __init__(self, objective: str, window: int, extra_gates: int,
                 cost: CostFn, check: bool) -> None:
        if objective not in ("cost", "gates"):
            raise ValueError('objective must be "cost" or "gates"')
        self.objective, self.window, self.extra_gates = objective, window, extra_gates
        self.cost, self.check = cost, check
        self.counts: Counter = Counter()
        self.rewrites = 0
        self.rng = random.Random(0)

    def score(self, gates: Sequence[Gate]) -> Tuple[int, int]:
        qc, count = sum(self.cost(g) for g in gates), len(gates)
        return (qc, count) if self.objective == "cost" else (count, qc)

    def walk(self, gates: List[Gate], i: int):
        """Move gate i to the right; return the best improving rewrite found."""
        moving, left, tags, growth = gates[i], [], [], 0
        best = None
        for k in range(i + 1, min(len(gates), i + 1 + self.window)):
            fixed = gates[k]
            reduced = reduce_pair(moving, fixed)
            if reduced is not None:
                new = left + reduced[0]
                gain = tuple(o - n for o, n in zip(self.score(gates[i:k + 1]), self.score(new)))
                if gain > (0, 0) and (best is None or gain > best[0]):
                    best = (gain, k, new, tags + [reduced[1]])
            tag = commute_tag(moving, fixed)
            if tag is not None:
                left, tags = left + [fixed], tags + [tag]
                continue
            passed = pass_gate(moving, fixed)
            if passed is None or growth + passed[3] > self.extra_gates:
                break
            left, moving = left + passed[0], passed[1]
            tags, growth = tags + [passed[2]], growth + passed[3]
        return best

    def sweep(self, gates: List[Gate]) -> bool:
        """One left-to-right sweep. Returns True when the circuit changed."""
        changed, i = False, 0
        while i < len(gates):
            best = self.walk(gates, i)
            if best is None:
                i += 1
                continue
            _, k, new, tags = best
            if self.check and not same_function(gates[i:k + 1], new, self.rng):
                raise AssertionError("optimizer produced a non-equivalent rewrite")
            gates[i:k + 1] = new
            self.counts.update(tags)
            self.rewrites += 1
            changed = True
        return changed

    def rule5(self, n: int, gates: List[Gate]) -> bool:
        """Apply Rule 5 wherever its pattern appears literally."""
        changed, i = False, 0
        while i < len(gates):
            new = R.rule5_apply(Circuit(n, gates), i)
            if new is not None and self.score(new.gates) < self.score(gates):
                gates[:] = new.gates
                self.counts["Rule 5"] += 1
                self.rewrites += 1
                changed = True
            else:
                i += 1
        return changed


def optimize(circuit: Circuit, objective: str = "cost", window: int = 50,
             extra_gates: int = 1, cost: CostFn = quantum_cost,
             check: bool = True, max_passes: int = 100) -> OptimizationResult:
    """Reduce a reversible circuit with the transformation rules.

    objective    "cost" minimises quantum cost, then gate count;
                 "gates" minimises gate count, then quantum cost.
    window       how many gates a moving gate may travel past.
    extra_gates  how many extra gates (rule D2) one move may leave behind.
    check        verify every rewrite by simulation on the lines it touches.
    """
    search = _Search(objective, window, extra_gates, cost, check)
    gates = list(circuit.gates)
    passes = 0
    while passes < max_passes:
        passes += 1
        changed = search.sweep(gates)
        # The same search on the reversed circuit moves gates to the left.
        # Each gate is its own inverse, so the reversed circuit is the
        # inverse circuit and every rule stays valid.
        gates.reverse()
        changed |= search.sweep(gates)
        gates.reverse()
        changed |= search.rule5(circuit.n, gates)
        if not changed:
            break
    return OptimizationResult(circuit, Circuit(circuit.n, gates), search.counts,
                              search.rewrites, passes, cost)
