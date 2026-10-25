"""Ancilla- and garbage-aware simplification (Phase 5).

The transformation rules of Feng and Li keep the function of a circuit the
same on EVERY line and for EVERY input. A practical circuit needs less:

  * ancilla lines always start at 0, and
  * garbage outputs are never read.

Two circuits are called design-equivalent here when they give the same
primary outputs for every value of the primary inputs, with all ancilla
lines starting at 0. The steps below keep design-equivalence. They are NOT
among the rules of the paper, whose authors leave the case with ancillary
bits open; they are heuristics of this project.

  constants  A gate that can never fire is removed, and a control that is
             always satisfied is dropped. "Never" and "always" refer to the
             valid inputs only (ancilla lines at 0).
  garbage    A gate is removed when its target is not a primary output and
             is not read later by any gate that matters.
  alias      A control is moved to another line that holds the same value at
             that point (for example the source of a copy), after commuting
             the gate earlier if needed. Copy gates then become garbage.
  xor        A CNOT whose control equals the XOR of two or three other lines
             is replaced by CNOTs from those lines, when that makes the gates
             that built the control garbage.
  rules      The Phase 3 optimizer (the paper's rules) runs in between.

The valid inputs are simulated all at once: each line holds one integer with
one bit per combination of the primary inputs. Every step is accepted only
if it lowers (cost, gate count, lines used), and with check=True the primary
outputs are compared with the original on all valid inputs after each step.
"""
from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations
from typing import Callable, Iterable, List, Sequence, Tuple

from revcircuit import CNOT, Circuit, G, Gate
from optimizer import circuit_cost, commute_tag, optimize, quantum_cost
from bitsim import input_vectors
from bdd import BDD, Fn

ALL_STEPS = ("constants", "garbage", "alias", "xor", "rules")


@dataclass
class SimplifyResult:
    original: Circuit
    circuit: Circuit
    inputs: List[int]
    ancilla: List[int]
    outputs: List[int]
    step_counts: Counter = field(default_factory=Counter)
    cost_fn: Callable[[Gate], int] = quantum_cost

    def _used(self, circuit: Circuit) -> set:
        touched = set()
        for g in circuit:
            touched |= g.lines
        return touched

    def ancilla_used(self, circuit: Circuit = None) -> int:
        """Ancilla lines that some gate still touches."""
        circuit = self.circuit if circuit is None else circuit
        return len(self._used(circuit) & set(self.ancilla))

    def lines_used(self, circuit: Circuit = None) -> int:
        circuit = self.circuit if circuit is None else circuit
        return len(self.inputs) + self.ancilla_used(circuit)

    def garbage(self, circuit: Circuit = None) -> int:
        """Used lines that are not primary outputs."""
        return self.lines_used(circuit) - len(self.outputs)

    def summary(self) -> str:
        def change(before, after):
            pct = 100.0 * (before - after) / before if before else 0.0
            return f"{before} -> {after} ({pct:.1f}% lower)"

        o, c = self.original, self.circuit
        lines = [
            f"Gate count:     {change(len(o), len(c))}",
            f"Quantum cost:   {change(circuit_cost(o, self.cost_fn), circuit_cost(c, self.cost_fn))}",
            f"Ancilla inputs: {change(self.ancilla_used(o), self.ancilla_used())}",
            f"Garbage lines:  {change(self.garbage(o), self.garbage())}",
        ]
        if self.step_counts:
            lines.append("Steps applied: " + ", ".join(
                f"{name} x{count}" for name, count in sorted(self.step_counts.items())))
        return "\n".join(lines)


class _Care:
    """Simulation over the valid inputs, and the simplification steps.

    Two interchangeable ways of holding "the value of a line for every valid
    input" are supported:

      bits   one integer with one bit per combination of the primary inputs.
             Exact, and fast up to about 17 primary inputs.
      bdd    one binary decision diagram per line. Exact for any number of
             inputs; practical when the diagrams stay small, as for adders.

    With the bdd backend a second, random simulation runs alongside. It is
    used only to find candidates quickly; every decision is taken on the
    exact values.
    """

    def __init__(self, n: int, inputs: Sequence[int], ancilla: Sequence[int],
                 outputs: Sequence[int], cost: Callable[[Gate], int],
                 backend: str = "auto", ancilla_ones: Sequence[int] = ()) -> None:
        if sorted(list(inputs) + list(ancilla)) != list(range(n)):
            raise ValueError("every line must be either a primary input or an ancilla")
        if not set(ancilla_ones) <= set(ancilla):
            raise ValueError("ancilla_ones must be a subset of ancilla")
        if backend == "auto":
            backend = "bits" if len(inputs) <= 17 else "bdd"
        if backend not in ("bits", "bdd"):
            raise ValueError('backend must be "bits", "bdd" or "auto"')
        self.n, self.outputs, self.cost, self.backend = n, list(outputs), cost, backend
        self.ancilla = set(ancilla)
        self.counts: Counter = Counter()
        k = len(inputs)
        if backend == "bits":
            self.zero, self.mask = 0, (1 << (1 << k)) - 1
            self.start = [0] * n
            for vector, line in zip(input_vectors(k), inputs):
                self.start[line] = vector
            self.sig_mask, self.sig_start = self.mask, self.start
        else:
            manager = BDD(k)
            self.zero, self.mask = Fn(manager, 0), Fn(manager, 1)
            self.start = [self.zero] * n
            for i, line in enumerate(inputs):          # variable order = order of `inputs`
                self.start[line] = Fn(manager, manager.var(i))
            rng = random.Random(12345)
            width = 1024
            self.sig_mask = (1 << width) - 1
            self.sig_start = [0] * n
            for line in inputs:
                self.sig_start[line] = rng.getrandbits(width)
        for line in ancilla_ones:
            self.start = list(self.start)
            self.sig_start = list(self.sig_start) if self.sig_start is not self.start else self.start
            self.start[line] = self.mask
            self.sig_start[line] = self.sig_mask

    # -- simulation ---------------------------------------------------------
    def activation(self, g: Gate, v: List, ones=None):
        """Where the gate fires: exact values, or signatures when `ones` is given."""
        act = self.mask if ones is None else ones
        for l in g.pos:
            act = act & v[l]
        for l in g.neg:
            act = act & ~v[l]
        return act if ones is None else act & ones

    def states(self, gates: Sequence[Gate]) -> List[List]:
        """Exact line values before each gate, and after the last one."""
        v = list(self.start)
        out = [list(v)]
        for g in gates:
            v[g.target] = v[g.target] ^ self.activation(g, v)
            out.append(list(v))
        return out

    def sig_states(self, gates: Sequence[Gate], exact: List[List]) -> List[List[int]]:
        """Integer signatures of the line values, used to look candidates up."""
        if self.backend == "bits":
            return exact
        v = list(self.sig_start)
        out = [list(v)]
        for g in gates:
            v[g.target] ^= self.activation(g, v, self.sig_mask)
            out.append(list(v))
        return out

    def signature(self, gates: Sequence[Gate]) -> Tuple:
        """The primary outputs for all valid inputs (exact)."""
        v = list(self.start)
        for g in gates:
            v[g.target] = v[g.target] ^ self.activation(g, v)
        return tuple(v[l] for l in self.outputs)

    def score(self, gates: Sequence[Gate]) -> Tuple[int, int, int]:
        touched = set()
        for g in gates:
            touched |= g.lines
        return (sum(self.cost(g) for g in gates), len(gates), len(touched & self.ancilla))

    # -- steps --------------------------------------------------------------
    def constants(self, gates: List[Gate]) -> List[Gate]:
        v = list(self.start)
        out = []
        for g in gates:
            act = self.activation(g, v)
            if act == self.zero:
                self.counts["constants: gate never fires"] += 1
                continue
            reduced = True
            while reduced:
                reduced = False
                for l in sorted(g.controls):
                    smaller = G(g.pos - {l}, g.neg - {l}, g.target)
                    if self.cost(smaller) <= self.cost(g) and self.activation(smaller, v) == act:
                        g, reduced = smaller, True
                        self.counts["constants: control dropped"] += 1
                        break
            v[g.target] = v[g.target] ^ act
            out.append(g)
        return out

    def garbage(self, gates: List[Gate], count: bool = True) -> List[Gate]:
        live = set(self.outputs)
        kept = []
        for g in reversed(gates):
            if g.target in live:
                kept.append(g)
                live |= g.controls
            elif count:
                self.counts["garbage: gate removed"] += 1
        return kept[::-1]

    def alias(self, gates: List[Gate]) -> Tuple[List[Gate], bool]:
        states = self.states(gates)
        sigs = self.sig_states(gates, states)
        base = self.score(gates)
        index_at = {}                                   # position -> {signature: [lines]}
        for j, g in enumerate(gates):
            i = j
            while True:
                v, sig = states[i], sigs[i]
                for u in sorted(g.controls):
                    if v[u] == self.zero or v[u] == self.mask:
                        continue
                    if i not in index_at:
                        table = {}
                        for line in range(self.n):
                            table.setdefault(sig[line], []).append(line)
                        index_at[i] = table
                    table = index_at[i]
                    complement = ~sig[u] & self.sig_mask if self.backend == "bdd" else ~v[u] & self.mask
                    for w in sorted(set(table.get(sig[u], [])) | set(table.get(complement, []))):
                        if w in g.lines:
                            continue
                        same = v[w] == v[u]
                        opposite = v[w] == (~v[u] & self.mask)
                        if not (same or opposite):
                            continue
                        positive = (u in g.pos) == same
                        pos = (g.pos - {u}) | ({w} if positive else set())
                        neg = (g.neg - {u}) | (set() if positive else {w})
                        trial = gates[:i] + [G(pos, neg, g.target)] + gates[i:j] + gates[j + 1:]
                        trial = self.garbage(trial, count=False)
                        if self.score(trial) < base:
                            self.counts["alias: control moved to an equal line"] += 1
                            return trial, True
                if i == 0 or commute_tag(g, gates[i - 1]) is None:
                    break
                i -= 1
        return gates, False

    def xor(self, gates: List[Gate]) -> Tuple[List[Gate], bool]:
        states = self.states(gates)
        sigs = self.sig_states(gates, states)
        base = self.score(gates)
        for j, g in enumerate(gates):
            if len(g.pos) != 1 or g.neg:
                continue
            (u,) = g.pos
            v, sig = states[j], sigs[j]
            lines = [l for l in range(self.n) if l not in (u, g.target) and v[l] != self.zero]
            table = {}
            for l in lines:
                table.setdefault(sig[l], []).append(l)

            def candidates():
                for x in lines:                          # pairs x < y
                    for y in table.get(sig[u] ^ sig[x], []):
                        if y > x:
                            yield (x, y)
                for a, x in enumerate(lines):            # triples x < y < z
                    for y in lines[a + 1:]:
                        for z in table.get(sig[u] ^ sig[x] ^ sig[y], []):
                            if z > y:
                                yield (x, y, z)

            for combo in candidates():
                total = self.zero
                for l in combo:
                    total = total ^ v[l]
                if total != v[u]:
                    continue
                trial = gates[:j] + [CNOT(l, g.target) for l in combo] + gates[j + 1:]
                trial = self.garbage(trial, count=False)
                if self.score(trial) < base:
                    self.counts["xor: control rebuilt from other lines"] += 1
                    return trial, True
        return gates, False

    def rules(self, gates: List[Gate]) -> List[Gate]:
        result = optimize(Circuit(self.n, gates), cost=self.cost)
        if self.score(result.circuit.gates) < self.score(gates):
            self.counts["rules: Phase 3 rewrites"] += result.rewrites
            return list(result.circuit.gates)
        return gates


def simplify(circuit: Circuit, inputs: Sequence[int], ancilla: Sequence[int],
             outputs: Sequence[int], steps: Iterable[str] = ALL_STEPS,
             cost: Callable[[Gate], int] = quantum_cost, check: bool = True,
             backend: str = "auto", ancilla_ones: Sequence[int] = (),
             rules_first: bool = True) -> SimplifyResult:
    """Simplify a circuit, using that ancilla lines start at a constant and
    that only the lines in `outputs` are read.

    inputs        lines that carry primary inputs. With the bdd backend their
                  order is the variable order; interleave operand bits.
    ancilla       lines that start at a constant (0 unless listed in ancilla_ones)
    outputs       lines that carry primary outputs; all other outputs are garbage
    steps         which steps to use, any of ALL_STEPS
    backend       "bits", "bdd", or "auto" (bits up to 17 primary inputs)
    ancilla_ones  ancilla lines that start at 1
    rules_first   run the rule-based optimizer before the other steps in each
                  round (default) or after them
    """
    steps = set(steps)
    if not steps <= set(ALL_STEPS):
        raise ValueError(f"steps must come from {ALL_STEPS}")
    care = _Care(circuit.n, inputs, ancilla, outputs, cost, backend, ancilla_ones)
    gates = list(circuit.gates)
    reference = care.signature(gates)

    def confirm(new: List[Gate]) -> List[Gate]:
        if check and care.signature(new) != reference:
            raise AssertionError("a simplification step changed a primary output")
        return new

    while True:
        before = care.score(gates)
        if "rules" in steps and rules_first:
            gates = confirm(care.rules(gates))
        if "constants" in steps:
            gates = confirm(care.constants(gates))
        if "garbage" in steps:
            gates = confirm(care.garbage(gates))
        for name, step in (("alias", care.alias), ("xor", care.xor)):
            changed = name in steps
            while changed:
                gates, changed = step(gates)
                confirm(gates)
        if "rules" in steps and not rules_first:
            gates = confirm(care.rules(gates))
        if care.score(gates) >= before:
            break
    return SimplifyResult(circuit, Circuit(circuit.n, gates), list(inputs), list(ancilla),
                          list(outputs), care.counts, cost)


def simplify_design(design, steps: Iterable[str] = ALL_STEPS, **kw) -> SimplifyResult:
    """simplify() for a Design from adders.py."""
    return simplify(design.circuit, list(design.inputs.values()), design.ancilla,
                    list(design.outputs.values()), steps, **kw)


# ---------------------------------------------------------------------------
# Counting a circuit the way the adder paper does
# ---------------------------------------------------------------------------
def block_view(circuit: Circuit) -> Tuple[int, int, Counter]:
    """Count blocks and price them as in the adder paper.

    A Toffoli gate next to a CNOT between its two controls is one Peres block
    (cost 4). Every other gate is one block at its own cost: Feynman or NOT 1,
    Toffoli-type gates by the project cost model.
    Returns (number of blocks, cost, how many blocks of each kind).
    """
    def peres_pair(a: Gate, b: Gate) -> bool:
        tof, cnot = (a, b) if len(a.controls) == 2 else (b, a)
        return (len(tof.pos) == 2 and not tof.neg and len(cnot.pos) == 1 and not cnot.neg
                and cnot.pos <= tof.pos and cnot.target in tof.pos)

    kinds: Counter = Counter()
    blocks = cost = i = 0
    gates = circuit.gates
    while i < len(gates):
        if i + 1 < len(gates) and peres_pair(gates[i], gates[i + 1]):
            kinds["Peres"] += 1
            cost += 4
            i += 2
        else:
            g = gates[i]
            c = len(g.controls)
            kinds["NOT" if c == 0 else "Feynman" if c == 1 and g.pos else "Toffoli-type"] += 1
            cost += quantum_cost(g)
            i += 1
        blocks += 1
    return blocks, cost, kinds
