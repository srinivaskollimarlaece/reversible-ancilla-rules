"""Phase 3 verification: the rule-based optimizer.

  A. The two derived moves D1 and D2 are sound on every instance (2 to 4
     lines), and the three commutation tests find every commuting gate pair.
  B. The cost model.
  C. Known examples reduce to the expected circuits.
  D. Random circuits: the optimized circuit always computes the same
     function and never costs more.
  E. Redundancy recovery: redundancy is injected into a circuit with the
     Phase 1 rules, and the optimizer has to remove it again.
  F. Gap to the exact optimum for 3-line functions.
  G. Which rules fired.

Run:  python verify_phase3.py
"""
from __future__ import annotations

import random
import sys
import time
from collections import Counter

from revcircuit import CNOT, Circuit, G, TOF, X, all_gates, random_circuit, random_gate
import rules as R
from canonical import canonical_form, canonical_from_function
from optimizer import (circuit_cost, commute_tag, optimize, pass_gate,
                       quantum_cost)
from exact import ExactTable

# The circuit drawings use Unicode symbols; make sure they print on Windows too.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

rng = random.Random(2026)
failures = 0
usage: Counter = Counter()


def report(label: str, ok: bool, detail: str = "") -> None:
    global failures
    failures += not ok
    print(f"  {label:<52}{'PASS' if ok else 'FAIL'}" + (f"  {detail}" if detail else ""))


def run(circuit: Circuit, **kw):
    """Optimize, record rule usage, and confirm the function is unchanged."""
    result = optimize(circuit, **kw)
    usage.update(result.rule_counts)
    return result


# ---------------------------------------------------------------------------
# A. Derived moves
# ---------------------------------------------------------------------------
def part_a() -> None:
    print("A. Derived moves D1 and D2, every gate pair")
    print(f"  {'Lines':<7}{'Pairs':>8}{'Commuting':>11}{'Found':>8}"
          f"{'Rule 9':>8}{'D2':>7}  Result")
    for n in (2, 3, 4):
        gates = all_gates(n)
        commuting = found = rule9 = d2 = 0
        ok = True
        for a in gates:
            for b in gates:
                ab = Circuit(n, [a, b])
                really = ab.equivalent(Circuit(n, [b, a]))
                tag = commute_tag(a, b)
                ok &= really or tag is None           # a tag must never be wrong
                if a != b and really:
                    commuting += 1
                    found += tag is not None
                if tag is None:
                    passed = pass_gate(a, b)
                    if passed is not None:
                        left, moving, name, extra = passed
                        ok &= Circuit(n, left + [moving]).equivalent(ab)
                        ok &= len(left) + 1 == 2 + extra
                        rule9 += name == "Rule 9"
                        d2 += name == "D2"
        ok &= commuting == found
        global failures
        failures += not ok
        print(f"  {n:<7}{len(gates) ** 2:>8}{commuting:>11}{found:>8}{rule9:>8}{d2:>7}  "
              f"{'PASS' if ok else 'FAIL'}")
    print("  'Found' = commuting pairs recognised by Rule 7, Rule 3 or D1.\n")


# ---------------------------------------------------------------------------
# B. Cost model
# ---------------------------------------------------------------------------
def part_b() -> None:
    print("B. Cost model")
    table = [quantum_cost(G(range(1, c + 1), [], 0)) for c in range(6)]
    report("Positive controls 0..5 cost 1, 1, 5, 13, 29, 61", table == [1, 1, 5, 13, 29, 61])
    report("One negative control among two costs 5", quantum_cost(G([1], [2], 0)) == 5)
    report("All controls negative costs one more",
           quantum_cost(G([], [1], 0)) == 2 and quantum_cost(G([], [1, 2], 0)) == 6)
    print()


# ---------------------------------------------------------------------------
# C. Known examples
# ---------------------------------------------------------------------------
def part_c() -> None:
    print("C. Known examples")
    lhs5, rhs5 = R.rule5_sides([], [], [1, 2], 0)
    cases = [
        ("Paper Example 2: X CNOT X",
         Circuit(2, [X(0), CNOT(0, 1), X(0)]), Circuit(2, [G([], [0], 1)])),
        ("Three CNOT gates to two",
         Circuit(3, [CNOT(1, 2), CNOT(0, 1), CNOT(1, 2)]), Circuit(3, [CNOT(0, 1), CNOT(0, 2)])),
        ("X Toffoli X to a negative control",
         Circuit(3, [X(0), TOF(0, 1, 2), X(0)]), Circuit(3, [G([1], [0], 2)])),
        ("CNOT and Toffoli on one target",
         Circuit(3, [CNOT(0, 2), TOF(0, 1, 2)]), Circuit(3, [G([0], [1], 2)])),
        ("Canonical circuit of CNOT[q0,q1] (6 gates)",
         canonical_form(Circuit(3, [CNOT(0, 1)])).circuit, Circuit(3, [CNOT(0, 1)])),
        ("Canonical circuit of paper Example 7 (6 gates)",
         canonical_form(Circuit(3, [CNOT(0, 1), CNOT(1, 2)])).circuit,
         Circuit(3, [CNOT(0, 1), CNOT(1, 2)])),
        ("Rule 5 pattern, m = 2 (7 gates to 3)", Circuit(3, lhs5), Circuit(3, rhs5)),
    ]
    for label, start, expected in cases:
        result = run(start)
        ok = (result.circuit.equivalent(start)
              and len(result.circuit) <= len(expected)
              and result.cost_after <= circuit_cost(expected))
        report(label, ok, f"{len(start)} -> {len(result.circuit)} gates, "
                          f"cost {result.cost_before} -> {result.cost_after}")
    start = Circuit(3, [X(0), TOF(0, 1, 2), CNOT(1, 2), X(0), CNOT(1, 2)])
    result = run(start)
    print("\n  Example run:")
    for line in start.draw().splitlines():
        print("    " + line)
    print("    becomes")
    for line in result.circuit.draw().splitlines():
        print("    " + line)
    for line in result.summary().splitlines():
        print("    " + line)
    print()


# ---------------------------------------------------------------------------
# D. Random circuits
# ---------------------------------------------------------------------------
def part_d() -> None:
    print("D. Random circuits: same function, never a higher cost")
    print(f"  {'Lines':<7}{'Circuits':>9}{'Gates before':>14}{'after':>8}"
          f"{'Cost before':>13}{'after':>9}  Result")
    for n, count in ((3, 150), (4, 150), (5, 100), (6, 100), (7, 60), (8, 40)):
        g0 = g1 = c0 = c1 = 0
        ok = True
        for k in range(count):
            circuit = random_circuit(n, rng.randint(5, 40), rng)
            objective = "cost" if k % 2 == 0 else "gates"
            result = run(circuit, objective=objective)
            ok &= result.circuit.equivalent(circuit)
            if objective == "cost":
                ok &= result.cost_after <= result.cost_before
            else:
                ok &= result.gates_after <= result.gates_before
            g0 += result.gates_before
            g1 += result.gates_after
            c0 += result.cost_before
            c1 += result.cost_after
        global failures
        failures += not ok
        print(f"  {n:<7}{count:>9}{g0:>14}{g1:>8}{c0:>13}{c1:>9}  {'PASS' if ok else 'FAIL'}")
    print("  Equivalence is checked by simulating all 2^n inputs.\n")


# ---------------------------------------------------------------------------
# E. Redundancy recovery
# ---------------------------------------------------------------------------
def random_nct(n: int, length: int) -> Circuit:
    """Random circuit of X, CNOT and Toffoli gates, the gate set adders are built from."""
    gates = []
    for _ in range(length):
        kind = rng.choice((0, 1, 1, 2, 2))
        lines = rng.sample(range(n), kind + 1)
        gates.append(G(lines[1:], [], lines[0]))
    return Circuit(n, gates)


def scramble(c: Circuit, steps: int, max_len: int = 80) -> Circuit:
    """Rewrite a circuit with randomly chosen Phase 1 rules. The function is unchanged."""
    for _ in range(steps):
        i = rng.randrange(len(c) + 1)
        move = rng.randrange(12)
        new = None
        if move == 0 and len(c) + 2 <= max_len:
            new = R.rule1_insert(c, i, random_gate(c.n, rng))
        elif move == 1 and len(c) + 1 <= max_len:
            new = R.rule2_split(c, i, rng.randrange(c.n))
        elif move == 2 and len(c) + 2 * c.n <= max_len:
            new = R.rule8_expand(c, i)
        else:
            fn = (R.rule1_cancel, R.rule2_merge, R.rule3_commute, R.rule4_apply,
                  R.rule5_apply, R.rule7_commute, R.rule8_collapse, R.rule9_apply,
                  R.rule10_apply)[move - 3]
            new = fn(c, i)
        if new is not None:
            c = new
    return c


def part_e() -> None:
    print("E. Redundancy recovery (X, CNOT, Toffoli circuits of 6 to 12 gates)")
    print(f"  {'Lines':<7}{'Circuits':>9} | {'Average gates':^31} | {'Average quantum cost':^31} |"
          f"{'Back to original':>18}")
    print(f"  {'':<7}{'':>9} | {'original':>9}{'padded':>10}{'optimized':>11} |"
          f" {'original':>9}{'padded':>10}{'optimized':>11} |{'cost or lower':>18}")
    for n, count in ((4, 150), (5, 150), (6, 100)):
        sums = [0] * 6
        back = 0
        ok = True
        for _ in range(count):
            original = random_nct(n, rng.randint(6, 12))
            padded = scramble(original, 80)
            result = run(padded)
            ok &= result.circuit.equivalent(original)
            values = (len(original), len(padded), len(result.circuit),
                      circuit_cost(original), circuit_cost(padded), result.cost_after)
            sums = [s + v for s, v in zip(sums, values)]
            back += result.cost_after <= circuit_cost(original)
        global failures
        failures += not ok
        a = [s / count for s in sums]
        print(f"  {n:<7}{count:>9} | {a[0]:>9.1f}{a[1]:>10.1f}{a[2]:>11.1f} |"
              f" {a[3]:>9.1f}{a[4]:>10.1f}{a[5]:>11.1f} |{100 * back / count:>17.1f}%"
              f"  {'PASS' if ok else 'FAIL'}")
    print("  'Padded' = the original after 80 random rule steps that add redundancy.")
    print("  PASS means every optimized circuit still computes the original function.\n")


# ---------------------------------------------------------------------------
# F. Gap to the exact optimum on 3 lines
# ---------------------------------------------------------------------------
def part_f() -> None:
    print("F. Gap to the exact optimum, 3-line functions")
    start = time.time()
    table = ExactTable(3)
    sizes = Counter(table.min_gates.values())
    print(f"  Exact tables for all {len(table.min_gates)} functions built in "
          f"{time.time() - start:.1f} s.")
    print("  Functions by minimum gate count: "
          + ", ".join(f"{k} gates: {sizes[k]}" for k in sorted(sizes)))
    print(f"  Highest minimum quantum cost: {max(table.min_cost.values())}\n")
    samples = 1000
    print(f"  {samples} random functions per row.")
    print(f"  {'Starting circuit':<28}{'Measure':<10}{'Start':>8}{'Optimized':>11}"
          f"{'Optimum':>9}{'Reached optimum':>17}")
    ok = True
    for start_kind in ("canonical form", "padded optimal circuit"):
        for objective, measure in (("gates", "gates"), ("cost", "cost")):
            s0 = s1 = so = hit = 0
            for _ in range(samples):
                perm = tuple(rng.sample(range(8), 8))
                if start_kind == "canonical form":
                    circuit = canonical_from_function(3, perm).circuit
                elif objective == "gates":
                    circuit = scramble(table.min_gate_circuit(perm), 60)
                else:
                    circuit = scramble(table.min_cost_circuit(perm), 60)
                result = run(circuit, objective=objective)
                ok &= result.circuit.permutation() == perm
                if objective == "gates":
                    before, after, best = len(circuit), len(result.circuit), table.min_gates[perm]
                else:
                    before, after, best = result.cost_before, result.cost_after, table.min_cost[perm]
                ok &= after >= best                    # nothing can beat the optimum
                s0, s1, so, hit = s0 + before, s1 + after, so + best, hit + (after == best)
            print(f"  {start_kind:<28}{measure:<10}{s0 / samples:>8.2f}{s1 / samples:>11.2f}"
                  f"{so / samples:>9.2f}{100 * hit / samples:>16.1f}%")
    print()
    report("Results consistent with the exact tables", ok)
    print()


def part_g() -> None:
    print("G. Rule usage over all experiments above")
    total = sum(usage.values())
    for name, count in usage.most_common():
        print(f"  {name:<12}{count:>8}  {100 * count / total:5.1f}%")
    print()


def main() -> int:
    start = time.time()
    print("Phase 3 verification: rule-based optimizer\n")
    part_a()
    part_b()
    part_c()
    part_d()
    part_e()
    part_f()
    part_g()
    print(f"Time: {time.time() - start:.1f} s")
    print("\nAll checks passed." if failures == 0 else f"\n{failures} check(s) FAILED.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
