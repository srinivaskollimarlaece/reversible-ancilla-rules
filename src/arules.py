"""Local rewrite rules for circuits with ancilla and garbage lines (Phase 11).

The complete rule set RC of Feng and Li preserves the function of a circuit
on every line and for every input. A practical circuit has more freedom:
ancilla lines start at a known constant and garbage lines are never read.
Feng and Li leave this case open. This module states five rules for it. Each
rule rewrites ONE gate h, and its side condition looks only at the gates
before h (rules A1, A3, A4, A5) or after h (rule A2). No global simulation of
the circuit is needed, which is the difference from the state-aware analysis
of simplify.py.

Notation: a gate is G[P, N, t]. A line is "fresh" while no gate has targeted
it yet; a fresh ancilla holds its constant. "Window": the stretch of the
circuit between two gates.

A1  Constant control.  If h has a control on a fresh ancilla r with constant
    v, the control is either always satisfied (drop it) or never satisfied
    (delete h).

A2  Dead gate.  If the target of h is not a primary output and no later gate
    uses it as a control, delete h.

A3  Product implication.  Let a fresh 0-ancilla c be written by g0 = G[P0, N0,
    c], and let c be untouched between g0 and h. After g0, c = 1 implies every
    literal of g0 whose line is also untouched in that window. If h has c as a
    positive control:
      A3a  a literal of h contradicts an implied literal  -> delete h,
      A3b  a literal of h equals an implied literal       -> drop it from h.
    If no line of g0 was touched in the window, c equals the product exactly,
    and for a negative control on c:
      A3c  the other literals of h include all literals of g0 -> delete h,
      A3d  the other literals of h contradict g0               -> drop c from h.

A4  Literal substitution.  If c equals one literal x or not-x exactly (g0 has
    one control and the window condition of A3 holds), replace the control c
    of h by that literal. The copy gate g0 can then become dead (A2).

A5  Linear substitution.  If c was written, from 0, only by CNOT and NOT gates
    whose control lines S are untouched in the window, then c = k xor (xor of
    S). A CNOT controlled by c alone is replaced by one CNOT from each line of
    S (and a NOT when the constant k requires it).

Soundness. In every case the firing condition of h is unchanged on every
valid input (ancilla lines at their constants), so every line keeps its value
after h; A2 changes only a line that is never read again and is not an output.
Each rule therefore preserves the primary outputs for all valid inputs (design
equivalence). The rules are not claimed to be complete.

ancilla_optimize() alternates these rules with the RC optimizer of Phase 3,
which moves gates and so creates new instances, and keeps a round only if it
lowers (quantum cost, gate count, ancilla lines used). The result is checked
exactly against the original on every valid input.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Dict, FrozenSet, List, Optional, Sequence, Tuple

from revcircuit import CNOT, Circuit, G, Gate, X
from optimizer import circuit_cost, optimize, quantum_cost
from simplify import _Care


@dataclass
class _Def:
    """What is known about a line from the gates before the current point."""
    kind: str                                  # "const", "prod" or "xor"
    value: int = 0                             # const: the constant; xor: the constant term
    pos: FrozenSet[int] = frozenset()          # prod: literals implied by c = 1
    neg: FrozenSet[int] = frozenset()
    exact: bool = True                         # prod: c equals the product exactly
    support: FrozenSet[int] = frozenset()      # xor: the lines S


@dataclass
class ARuleResult:
    original: Circuit
    circuit: Circuit
    counts: Counter = field(default_factory=Counter)
    rounds: int = 0


ALL_RULES = ("A1", "A2", "A3", "A4", "A5")


def _forward(gates: List[Gate], ancilla: Sequence[int], ones: Sequence[int],
             substitute: bool, counts: Counter, use: Sequence[str] = ALL_RULES) -> List[Gate]:
    """One pass of rules A1, A3 (and A4, A5 when `substitute`) from left to right."""
    defs: Dict[int, Optional[_Def]] = {l: _Def("const", 1 if l in ones else 0) for l in ancilla}
    out: List[Gate] = []

    def rewrite(h: Gate) -> Optional[List[Gate]]:
        """Apply the rules to h. Returns the replacement gates ([] = deleted)."""
        changed = True
        while changed:
            changed = False
            for r in sorted(h.controls):
                d = defs.get(r)
                if d is None:
                    continue
                positive = r in h.pos
                others_pos, others_neg = h.pos - {r}, h.neg - {r}
                if d.kind == "const" and "A1" in use:                       # A1
                    if (d.value == 1) == positive:
                        h = G(others_pos, others_neg, h.target)
                        counts["A1 constant control dropped"] += 1
                        changed = True
                        break
                    counts["A1 gate never fires"] += 1
                    return []
                if d.kind == "prod" and "A3" in use:
                    if positive:
                        if (d.pos & others_neg) or (d.neg & others_pos):    # A3a
                            counts["A3a gate never fires"] += 1
                            return []
                        if (d.pos & others_pos) or (d.neg & others_neg):    # A3b
                            h = G(h.pos - d.pos | {r}, h.neg - d.neg, h.target)
                            counts["A3b implied control dropped"] += 1
                            changed = True
                            break
                    elif d.exact:
                        if d.pos <= others_pos and d.neg <= others_neg:      # A3c
                            counts["A3c gate never fires"] += 1
                            return []
                        if (d.pos & others_neg) or (d.neg & others_pos):    # A3d
                            h = G(others_pos, others_neg, h.target)
                            counts["A3d control dropped"] += 1
                            changed = True
                            break
                if d.kind == "prod" and "A4" in use:
                    if substitute and d.exact and len(d.pos) + len(d.neg) == 1:   # A4
                        (x,) = tuple(d.pos | d.neg)
                        same = (x in d.pos) == positive          # literal polarity on x
                        if x in h.controls or x == h.target:
                            continue
                        new_pos = others_pos | ({x} if same else set())
                        new_neg = others_neg | (set() if same else {x})
                        h = G(new_pos, new_neg, h.target)
                        counts["A4 literal substituted"] += 1
                        changed = True
                        break
                if (d.kind == "xor" and "A5" in use and substitute and len(h.controls) == 1
                        and h.target not in d.support and len(d.support) >= 1):     # A5
                    flip = d.value ^ (0 if positive else 1)
                    repl = [CNOT(s, h.target) for s in sorted(d.support)]
                    if flip:
                        repl.append(X(h.target))
                    counts["A5 linear substitution"] += 1
                    return repl
        return [h]

    def update(h: Gate) -> None:
        t = h.target
        old = defs.get(t)
        for c, d in list(defs.items()):                 # lines whose knowledge depended on t
            if d is None or c == t:
                continue
            if d.kind == "prod" and (t in d.pos or t in d.neg):
                defs[c] = _Def("prod", 0, d.pos - {t}, d.neg - {t}, False)
            elif d.kind == "xor" and t in d.support:
                defs[c] = None
        new: Optional[_Def] = None
        if old is not None:
            if not h.controls:                                           # NOT gate
                if old.kind == "const":
                    new = _Def("const", 1 - old.value)
                elif old.kind == "xor":
                    new = _Def("xor", 1 - old.value, support=old.support)
            elif old.kind == "const" and old.value == 0 and len(h.controls) >= 1:
                new = _Def("prod", 0, frozenset(h.pos), frozenset(h.neg), True)
            elif old.kind == "const" and len(h.controls) == 1:            # from constant 1
                (y,) = tuple(h.controls)
                new = _Def("xor", 1 ^ (0 if y in h.pos else 1), support=frozenset({y}))
            if len(h.controls) == 1 and old.kind in ("prod", "xor"):
                (y,) = tuple(h.controls)
                if old.kind == "prod" and old.exact and len(old.pos) + len(old.neg) == 1:
                    (x,) = tuple(old.pos | old.neg)
                    old = _Def("xor", 0 if x in old.pos else 1, support=frozenset({x}))
                if old.kind == "xor":
                    support = old.support ^ {y}
                    value = old.value ^ (0 if y in h.pos else 1)
                    new = _Def("xor", value, support=frozenset(support)) if support else _Def("const", value)
        defs[t] = new

    for h in gates:
        for g in rewrite(h):
            out.append(g)
            update(g)
    return out


def _dead(gates: List[Gate], outputs: Sequence[int], counts: Counter) -> List[Gate]:
    """Rule A2 from right to left."""
    read = set()
    outs = set(outputs)
    kept = []
    for g in reversed(gates):
        if g.target not in outs and g.target not in read:
            counts["A2 dead gate removed"] += 1
            continue
        kept.append(g)
        read |= g.controls
    return kept[::-1]


def ancilla_optimize(circuit: Circuit, inputs: Sequence[int], ancilla: Sequence[int],
                     outputs: Sequence[int], ancilla_ones: Sequence[int] = (),
                     cost: Callable[[Gate], int] = quantum_cost, use_rc: bool = True,
                     check: bool = True, max_rounds: int = 30,
                     use: Sequence[str] = ALL_RULES) -> ARuleResult:
    """Rules A1 to A5 (those listed in `use`) together with the RC optimizer.

    With use_rc the RC optimizer runs first and after every pass of the rules,
    so the result is never worse than the RC optimizer alone.
    """
    ancilla, ones = list(ancilla), set(ancilla_ones)
    anc_set = set(ancilla)

    def score(gates):
        touched = set()
        for g in gates:
            touched |= g.lines
        return (sum(cost(g) for g in gates), len(gates), len(touched & anc_set))

    gates = list(circuit.gates)
    counts: Counter = Counter()
    if use_rc:
        first = optimize(circuit, cost=cost)
        if score(first.circuit.gates) < score(gates):
            gates = list(first.circuit.gates)
            counts["RC rewrites"] += first.rewrites
    rounds = 0
    while rounds < max_rounds:
        rounds += 1
        best, best_counts = None, None
        for substitute in (False, True):
            trial_counts: Counter = Counter()
            trial = _forward(gates, ancilla, ones, substitute, trial_counts, use)
            if "A2" in use:
                trial = _dead(trial, outputs, trial_counts)
            if use_rc:
                result = optimize(Circuit(circuit.n, trial), cost=cost)
                if result.rewrites:
                    trial_counts["RC rewrites"] += result.rewrites
                trial = list(result.circuit.gates)
            if best is None or score(trial) < score(best):
                best, best_counts = trial, trial_counts
        if score(best) >= score(gates):
            break
        gates = best
        counts.update(best_counts)
    out = Circuit(circuit.n, gates)
    if check:
        care = _Care(circuit.n, inputs, ancilla, outputs, cost, "auto", ancilla_ones)
        if care.signature(gates) != care.signature(list(circuit.gates)):
            raise AssertionError("the ancilla rules changed a primary output")
    return ARuleResult(circuit, out, counts, rounds)
