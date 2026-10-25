"""Transformation rules for reversible circuits (Phase 1).

Rules 1 to 5 are the complete rule set RC of Feng and Li (IEEE TCAD, 2026).
Rules 6 to 10 are the rules the paper derives from RC.

Every rewrite function takes a circuit and a position i and returns a NEW
circuit with the rule applied at position i, or None when the rule does not
match there. The input circuit is never modified.

For rules stated on gates rather than positions, a `ruleK_gates` or
`ruleK_sides` helper returns the gate lists on each side of the rule.
"""
from __future__ import annotations

from itertools import combinations
from typing import Iterable, List, Optional, Sequence, Tuple

from revcircuit import CNOT, Circuit, G, Gate, X


# ===========================================================================
# Rule 1:  A A  ==  (empty)
# ===========================================================================
def rule1_cancel(c: Circuit, i: int) -> Optional[Circuit]:
    """Delete two adjacent identical gates at positions i and i+1."""
    if 0 <= i and i + 1 < len(c) and c[i] == c[i + 1]:
        return c.replace(i, i + 2, [])
    return None


def rule1_insert(c: Circuit, i: int, gate: Gate) -> Circuit:
    """Rule 1 read right to left: insert the pair `gate gate` before position i."""
    return c.replace(i, i, [gate, gate])


# ===========================================================================
# Rule 2:  G[P, N+{p}, q] G[P+{p}, N, q]  ==  G[P, N, q]
# ===========================================================================
def rule2_gates(gate: Gate, p: int) -> List[Gate]:
    """The pair A0, A1 that Rule 2 merges into `gate`, using extra line p."""
    if p in gate.lines:
        raise ValueError("p must be a line the gate does not use")
    return [G(gate.pos, gate.neg | {p}, gate.target), G(gate.pos | {p}, gate.neg, gate.target)]


def rule2_merge(c: Circuit, i: int) -> Optional[Circuit]:
    """Merge gates i and i+1 when they are A0 A1 in the order of the paper."""
    if i < 0 or i + 1 >= len(c):
        return None
    a0, a1 = c[i], c[i + 1]
    extra = a1.pos - a0.pos
    if a0.target != a1.target or len(extra) != 1:
        return None
    (p,) = extra
    merged = G(a1.pos - {p}, a1.neg, a1.target)
    if rule2_gates(merged, p) == [a0, a1]:
        return c.replace(i, i + 2, [merged])
    return None


def rule2_split(c: Circuit, i: int, p: int) -> Optional[Circuit]:
    """Rule 2 read right to left: split gate i into A0 A1 on unused line p."""
    if not (0 <= i < len(c)) or not (0 <= p < c.n) or p in c[i].lines:
        return None
    return c.replace(i, i + 1, rule2_gates(c[i], p))


# ===========================================================================
# Rule 3:  A B == B A  when a control has opposite polarity in A and B
# ===========================================================================
def rule3_condition(a: Gate, b: Gate) -> bool:
    return bool(a.pos & b.neg) or bool(b.pos & a.neg)


def rule3_commute(c: Circuit, i: int) -> Optional[Circuit]:
    """Swap gates i and i+1 when they share a control of opposite polarity."""
    if 0 <= i and i + 1 < len(c) and rule3_condition(c[i], c[i + 1]):
        return c.replace(i, i + 2, [c[i + 1], c[i]])
    return None


# ===========================================================================
# Rule 4:  A B A C1 == C2 A B A,  A = CNOT[p,q], B = CNOT[q,p]
#          (moving a swap of p and q through a gate)
# ===========================================================================
def rule4_sides(p: int, q: int, P: Iterable[int], N: Iterable[int],
                negative: bool = False) -> Tuple[List[Gate], List[Gate]]:
    """Both sides of Rule 4.

    negative=False is condition (a): C1 has q as positive control, target p.
    negative=True  is condition (b): C1 has q as negative control, target p.
    """
    P, N = frozenset(P), frozenset(N)
    a, b = CNOT(p, q), CNOT(q, p)
    if negative:
        c1, c2 = G(P, N | {q}, p), G(P, N | {p}, q)
    else:
        c1, c2 = G(P | {q}, N, p), G(P | {p}, N, q)
    return [a, b, a, c1], [c2, a, b, a]


def _is_cnot(g: Gate) -> bool:
    return len(g.pos) == 1 and not g.neg


def rule4_apply(c: Circuit, i: int) -> Optional[Circuit]:
    """Apply Rule 4 to the four gates starting at i, in either direction."""
    if i < 0 or i + 4 > len(c):
        return None
    seg = c.gates[i:i + 4]
    # Left to right:  A B A C1  ->  C2 A B A
    if _is_cnot(seg[0]):
        (p,) = seg[0].pos
        q = seg[0].target
        c1 = seg[3]
        if c1.target == p and q in c1.controls:
            lhs, rhs = rule4_sides(p, q, c1.pos - {q}, c1.neg - {q}, q in c1.neg)
            if seg == lhs:
                return c.replace(i, i + 4, rhs)
    # Right to left:  C2 A B A  ->  A B A C1
    if _is_cnot(seg[1]):
        (p,) = seg[1].pos
        q = seg[1].target
        c2 = seg[0]
        if c2.target == q and p in c2.controls:
            lhs, rhs = rule4_sides(p, q, c2.pos - {p}, c2.neg - {p}, p in c2.neg)
            if seg == rhs:
                return c.replace(i, i + 4, lhs)
    return None


# ===========================================================================
# Rule 5:  A0 A1 B1..Bm..B1 A1 A0  ==  B'1..B'm..B'1
#          (changes the polarity of control q0)
# ===========================================================================
def rule5_sides(P: Iterable[int], N: Iterable[int], Q: Sequence[int],
                q0: int) -> Tuple[List[Gate], List[Gate]]:
    """Both sides of Rule 5 for control sets P, N, ordered list Q and line q0."""
    P, N, Q = frozenset(P), frozenset(N), list(Q)
    Qs = frozenset(Q)
    if not Q or len(Qs) != len(Q):
        raise ValueError("Q must be a non-empty list of distinct lines")
    a0 = G(P, N | Qs, q0)
    a1 = G(P | Qs, N, q0)
    b = [G(P | {q0} | frozenset(Q[k + 1:]), N | frozenset(Q[:k]), Q[k]) for k in range(len(Q))]
    bp = [G(P | frozenset(Q[k + 1:]), N | {q0} | frozenset(Q[:k]), Q[k]) for k in range(len(Q))]
    lhs = [a0, a1] + b + b[-2::-1] + [a1, a0]
    rhs = bp + bp[-2::-1]
    return lhs, rhs


def rule5_apply(c: Circuit, i: int) -> Optional[Circuit]:
    """Left to right: replace the 2m+3 gate pattern starting at i by 2m-1 gates."""
    if i < 0 or i + 1 >= len(c):
        return None
    a0, a1 = c[i], c[i + 1]
    Qs = a1.pos - a0.pos
    if a0.target != a1.target or not Qs or a0.neg - a1.neg != Qs:
        return None
    if a0.pos - a1.pos or a1.neg - a0.neg:
        return None
    m = len(Qs)
    end = i + 2 * m + 3
    if end > len(c):
        return None
    order = [g.target for g in c.gates[i + 2:i + 2 + m]]
    if frozenset(order) != Qs:
        return None
    lhs, rhs = rule5_sides(a0.pos, a1.neg, order, a0.target)
    if c.gates[i:end] == lhs:
        return c.replace(i, end, rhs)
    return None


def rule5_reverse(c: Circuit, i: int, Q: Sequence[int], q0: int) -> Optional[Circuit]:
    """Right to left: expand B'1..B'm..B'1 at i, given the list Q and line q0."""
    Q = list(Q)
    end = i + 2 * len(Q) - 1
    if i < 0 or not Q or end > len(c):
        return None
    b1 = c[i]
    if b1.target != Q[0] or q0 not in b1.neg:
        return None
    try:
        lhs, rhs = rule5_sides(b1.pos - frozenset(Q[1:]), b1.neg - {q0}, Q, q0)
    except ValueError:
        return None
    if c.gates[i:end] == rhs:
        return c.replace(i, end, lhs)
    return None


# ===========================================================================
# Derived rules 6 to 10
# ===========================================================================
# Rule 6:  G[P,N,q] == product over all subsets S of Q of G[P+S, N+(Q-S), q]
def rule6_gates(gate: Gate, Q: Iterable[int]) -> List[Gate]:
    Q = sorted(set(Q))
    if set(Q) & gate.lines:
        raise ValueError("Q must not overlap the lines of the gate")
    out = []
    for r in range(len(Q) + 1):
        for sub in combinations(Q, r):
            out.append(G(gate.pos | set(sub), gate.neg | (set(Q) - set(sub)), gate.target))
    return out


def rule6_expand(c: Circuit, i: int, Q: Iterable[int]) -> Optional[Circuit]:
    """Expand gate i over all polarity patterns of the unused lines Q."""
    Q = set(Q)
    if not (0 <= i < len(c)) or not Q or Q & c[i].lines or max(Q) >= c.n or min(Q) < 0:
        return None
    return c.replace(i, i + 1, rule6_gates(c[i], Q))


# Rule 7:  two gates with the same target commute
def rule7_commute(c: Circuit, i: int) -> Optional[Circuit]:
    if 0 <= i and i + 1 < len(c) and c[i].target == c[i + 1].target:
        return c.replace(i, i + 2, [c[i + 1], c[i]])
    return None


# Rule 8:  G[P,N,q] == X[N] G[P+N, {}, q] X[N]
def rule8_gates(gate: Gate) -> List[Gate]:
    xs = [X(l) for l in sorted(gate.neg)]
    return xs + [G(gate.pos | gate.neg, (), gate.target)] + xs


def rule8_expand(c: Circuit, i: int) -> Optional[Circuit]:
    """Replace the negative controls of gate i by X gates before and after."""
    if 0 <= i < len(c) and c[i].neg:
        return c.replace(i, i + 1, rule8_gates(c[i]))
    return None


def rule8_collapse(c: Circuit, i: int) -> Optional[Circuit]:
    """Right to left: absorb X..X B X..X starting at i into one gate."""
    k = 0
    while i + k < len(c) and not c[i + k].controls:
        k += 1
    if i < 0 or k == 0 or i + 2 * k + 1 > len(c):
        return None
    b = c[i + k]
    lines = frozenset(g.target for g in c.gates[i:i + k])
    if len(lines) != k or b.neg or not lines <= b.pos:
        return None
    merged = G(b.pos - lines, lines, b.target)
    if c.gates[i:i + 2 * k + 1] == rule8_gates(merged):
        return c.replace(i, i + 2 * k + 1, [merged])
    return None


# Rule 9:  A B1 == B2 A, where A targets p and B1, B2 differ in the polarity of p
def _rule9_pair(a: Gate, b: Gate) -> Optional[Gate]:
    """If A can pass B by Rule 9, return B with the polarity of A's target flipped."""
    p = a.target
    if p not in b.controls:
        return None
    if not (a.pos <= b.pos - {p} and a.neg <= b.neg - {p}):
        return None
    if p in b.pos:
        return G(b.pos - {p}, b.neg | {p}, b.target)
    return G(b.pos | {p}, b.neg - {p}, b.target)


def rule9_apply(c: Circuit, i: int) -> Optional[Circuit]:
    """Move a gate past its neighbour, flipping one control polarity in the neighbour."""
    if i < 0 or i + 1 >= len(c):
        return None
    g1, g2 = c[i], c[i + 1]
    flipped = _rule9_pair(g1, g2)          # A B1 -> B2 A
    if flipped is not None:
        return c.replace(i, i + 2, [flipped, g1])
    flipped = _rule9_pair(g2, g1)          # B2 A -> A B1
    if flipped is not None:
        return c.replace(i, i + 2, [g2, flipped])
    return None


# Rule 10:  A B A == B A B,  A = G[P+{p}, {}, q],  B = G[P+{q}, {}, p]
def rule10_sides(P: Iterable[int], p: int, q: int) -> Tuple[List[Gate], List[Gate]]:
    P = frozenset(P)
    a, b = G(P | {p}, (), q), G(P | {q}, (), p)
    return [a, b, a], [b, a, b]


def rule10_apply(c: Circuit, i: int) -> Optional[Circuit]:
    if i < 0 or i + 3 > len(c):
        return None
    a, b = c[i], c[i + 1]
    p, q = b.target, a.target
    if a.neg or b.neg or p == q or p not in a.pos or q not in b.pos:
        return None
    if a.pos - {p} != b.pos - {q}:
        return None
    lhs, rhs = rule10_sides(a.pos - {p}, p, q)
    if c.gates[i:i + 3] == lhs:
        return c.replace(i, i + 3, rhs)
    return None
