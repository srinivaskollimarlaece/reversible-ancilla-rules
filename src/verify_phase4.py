"""Phase 4 verification: reversible adders and the rule-based optimizer.

  A. Gate library: each block equals its defining function.
  B. The adders add correctly for all 512 input combinations.
  C. Resources of each design, beside the figures the adder paper reports.
  D. The optimizer on the adders, checked on every input of every line.
  E. Search for hidden redundancy: reorder each adder at random and optimize again.
  F. Control experiment: redundancy planted in the adder is removed again.

Run:  python verify_phase4.py
"""
from __future__ import annotations

import random
import sys
import time
from itertools import product

from revcircuit import CNOT, Circuit, G, TOF, X
from optimizer import circuit_cost, commute_tag, optimize, pass_gate
from adders import (PAPER_BLOCK_COST, PAPER_REPORTED, check_adder, cla_adder,
                    depth, feynman, feynman_ref, peres, peres_ref, r2, r2_ref,
                    rca_adder, tsg, tsg_ref)
from bitsim import equivalent_all_inputs

# The circuit drawings use Unicode symbols; make sure they print on Windows too.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

rng = random.Random(2026)
failures = 0


def report(label: str, ok: bool, detail: str = "") -> None:
    global failures
    failures += not ok
    print(f"  {label:<50}{'PASS' if ok else 'FAIL'}" + (f"  {detail}" if detail else ""))


# ---------------------------------------------------------------------------
# A. Gate library
# ---------------------------------------------------------------------------
def part_a() -> None:
    print("A. Gate library (each block as Toffoli-type gates)")
    print(f"  {'Block':<9}{'Lines':>6}{'Gates':>7}{'Cost, this project':>20}"
          f"{'Cost, adder paper':>19}  Result")
    library = (("Feynman", feynman, feynman_ref, 2, None),
               ("Peres", peres, peres_ref, 3, None),
               ("TSG", tsg, tsg_ref, 4, (0, 1, 3, 2)),      # outputs on lines a, b, d, c
               ("R2", r2, r2_ref, 4, None))
    for name, maker, ref, k, order in library:
        circuit = Circuit(k, maker(*range(k)))
        ok, images = True, set()
        for bits in product((0, 1), repeat=k):
            state = sum(bit << i for i, bit in enumerate(bits))
            out = circuit.apply(state)
            got = tuple((out >> i) & 1 for i in range(k))
            want = ref(*bits)
            if order:
                want = tuple(want[j] for j in order)
            ok &= got == want
            images.add(got)
        ok &= len(images) == 1 << k                           # the block is reversible
        global failures
        failures += not ok
        print(f"  {name:<9}{k:>6}{len(circuit):>7}{circuit_cost(circuit):>20}"
              f"{PAPER_BLOCK_COST[name]:>19}  {'PASS' if ok else 'FAIL'}")
    print("  The two cost columns differ because the adder paper prices each block as a")
    print("  unit, while this project prices the Toffoli-type gates inside it.\n")


# ---------------------------------------------------------------------------
# B and C. The adders
# ---------------------------------------------------------------------------
def part_b(designs) -> None:
    print("B. Adders: all 512 input combinations (ancilla lines start at 0)")
    for d in designs:
        cases, wrong = check_adder(d)
        outs = ", ".join(sorted(d.outputs))
        report(f"{d.name}: outputs {outs}", wrong == 0, f"{cases - wrong}/{cases} correct")
    print()


def part_c(designs) -> None:
    print("C. Resources")
    print(f"  {'Design':<24}{'Lines':>6}{'Blocks':>8}{'Ancilla':>9}{'Garbage':>9}"
          f"{'Cost (paper':>13}{'Gates':>7}{'Cost (this':>12}{'Depth':>7}")
    print(f"  {'':<24}{'':>6}{'':>8}{'':>9}{'':>9}{'prices)':>13}{'':>7}{'project)':>12}{'':>7}")
    p = PAPER_REPORTED
    print(f"  {'Reported in adder paper':<24}{'-':>6}{p['gates']:>8}{p['ancilla']:>9}"
          f"{p['garbage']:>9}{p['cost']:>13}{'-':>7}{'-':>12}{'-':>7}")
    for d in designs:
        print(f"  {d.name:<24}{d.n:>6}{d.block_count():>8}{len(d.ancilla):>9}"
              f"{len(d.garbage):>9}{d.block_cost():>13}{len(d.circuit):>7}"
              f"{circuit_cost(d.circuit):>12}{depth(d.circuit):>7}")
    print("  Blocks   = Feynman, Peres, TSG and R2 gates, each counted once.")
    print("  Garbage  = every output line that is not a sum or carry output.")
    print("  Gates    = Toffoli-type gates after decomposing the blocks.")
    print("  Depth    = time steps of this netlist when gates on separate lines run together.")
    for d in designs:
        print(f"  {d.name}: {d.block_summary()}")
    print()


# ---------------------------------------------------------------------------
# D. Optimizer on the adders
# ---------------------------------------------------------------------------
def part_d(designs) -> None:
    print("D. Rule-based optimizer on the adders (every line treated as a real input and output)")
    print(f"  {'Design':<24}{'Objective':<11}{'Gates':>12}{'Cost':>12}{'Depth':>10}"
          f"{'Rewrites':>10}  Result")
    for d in designs:
        for objective in ("cost", "gates"):
            result = optimize(d.circuit, objective=objective)
            same = equivalent_all_inputs(d.circuit, result.circuit)
            adds = check_adder(d.with_circuit(result.circuit, d.name))[1] == 0
            ok = same and adds and result.cost_after <= result.cost_before
            global failures
            failures += not ok
            print(f"  {d.name:<24}{objective:<11}"
                  f"{f'{result.gates_before} -> {result.gates_after}':>12}"
                  f"{f'{result.cost_before} -> {result.cost_after}':>12}"
                  f"{f'{depth(d.circuit)} -> {depth(result.circuit)}':>10}"
                  f"{result.rewrites:>10}  {'PASS' if ok else 'FAIL'}")
    print("  PASS = identical to the original on all 2^n inputs of all lines, and still adds.\n")


# ---------------------------------------------------------------------------
# E. Hidden redundancy
# ---------------------------------------------------------------------------
def reorder(circuit: Circuit, steps: int) -> Circuit:
    """Random function-preserving moves that keep the gate count: commute, or Rule 9."""
    gates = list(circuit.gates)
    for _ in range(steps):
        i = rng.randrange(len(gates) - 1)
        a, b = gates[i], gates[i + 1]
        if commute_tag(a, b) is not None:
            gates[i], gates[i + 1] = b, a
        else:
            passed = pass_gate(a, b)
            if passed is not None and passed[3] == 0:        # Rule 9: no extra gate
                gates[i:i + 2] = passed[0] + [passed[1]]
    return Circuit(circuit.n, gates)


def part_e(designs) -> None:
    print("E. Search for hidden redundancy (random reordering, then optimize again)")
    trials = 200
    for d in designs:
        base = circuit_cost(d.circuit)
        best, ok = base, True
        for k in range(trials):
            shuffled = reorder(d.circuit, 400)
            result = optimize(shuffled, extra_gates=2)
            best = min(best, result.cost_after)
            if k % 50 == 0:                                   # spot-check full equivalence
                ok &= equivalent_all_inputs(d.circuit, result.circuit)
        report(f"{d.name}: {trials} random orderings", ok,
               f"lowest cost found {best} (original {base})")
    print()


# ---------------------------------------------------------------------------
# F. Planted redundancy
# ---------------------------------------------------------------------------
def plant(circuit: Circuit, pairs: int) -> Circuit:
    """Insert `pairs` cancelling gate pairs (Rule 1 backwards), then drift them apart."""
    gates = list(circuit.gates)
    n = circuit.n
    for _ in range(pairs):
        kind = rng.choice((0, 1, 2))
        lines = rng.sample(range(n), kind + 1)
        g = G(lines[1:], [], lines[0])
        i = rng.randrange(len(gates) + 1)
        gates[i:i] = [g, g]
    return reorder(Circuit(n, gates), 600)


def part_f(designs) -> None:
    print("F. Control experiment: 15 cancelling gate pairs planted in each adder")
    print(f"  {'Design':<24}{'Trials':>7}{'Avg cost planted':>18}{'Avg cost after':>16}"
          f"{'Original':>10}{'Fully recovered':>17}  Result")
    trials = 30
    for d in designs:
        base = circuit_cost(d.circuit)
        planted_sum = after_sum = recovered = 0
        ok = True
        for k in range(trials):
            padded = plant(d.circuit, 15)
            result = optimize(padded)
            planted_sum += circuit_cost(padded)
            after_sum += result.cost_after
            recovered += result.cost_after <= base
            ok &= check_adder(d.with_circuit(result.circuit, d.name))[1] == 0
            if k % 10 == 0:
                ok &= equivalent_all_inputs(d.circuit, result.circuit)
        global failures
        failures += not ok
        print(f"  {d.name:<24}{trials:>7}{planted_sum / trials:>18.1f}{after_sum / trials:>16.1f}"
              f"{base:>10}{100 * recovered / trials:>16.1f}%  {'PASS' if ok else 'FAIL'}")
    print("  PASS = every optimized circuit still adds correctly.\n")


def main() -> int:
    start = time.time()
    print("Phase 4 verification: reversible adders\n")
    designs = [cla_adder(), cla_adder(carry_out=True), rca_adder()]
    part_a()
    part_b(designs)
    part_c(designs)
    part_d(designs)
    part_e(designs)
    part_f(designs)
    print(f"Time: {time.time() - start:.1f} s")
    print("\nAll checks passed." if failures == 0 else f"\n{failures} check(s) FAILED.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
