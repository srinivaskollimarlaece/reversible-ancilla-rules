"""Phase 5 verification: ancilla- and garbage-aware simplification.

  A. Each step on a small hand-made example.
  B. Random circuits: the primary outputs never change. This check uses the
     plain one-input-at-a-time simulator, not the simplifier's own simulation.
  C. The adders before and after, with all 512 input combinations re-tested.
  D. Contribution of each step on the carry look-ahead adder.
  E. The result counted the way the adder paper counts.
  F. The simplified carry look-ahead netlist.

Run:  python verify_phase5.py
"""
from __future__ import annotations

import random
import sys
import time

from revcircuit import CNOT, Circuit, G, TOF, X
from optimizer import circuit_cost
from adders import PAPER_REPORTED, check_adder, cla_adder, depth, rca_adder
from simplify import ALL_STEPS, block_view, simplify, simplify_design

# The circuit drawings use Unicode symbols; make sure they print on Windows too.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

rng = random.Random(2026)
failures = 0


def report(label: str, ok: bool, detail: str = "") -> None:
    global failures
    failures += not ok
    print(f"  {label:<54}{'PASS' if ok else 'FAIL'}" + (f"  {detail}" if detail else ""))


def primary_outputs(circuit: Circuit, inputs, outputs):
    """Primary outputs for every primary input, by plain simulation (ancilla at 0)."""
    table = []
    for value in range(1 << len(inputs)):
        state = sum(((value >> j) & 1) << line for j, line in enumerate(inputs))
        out = circuit.apply(state)
        table.append(tuple((out >> line) & 1 for line in outputs))
    return table


# ---------------------------------------------------------------------------
# A. Hand-made examples
# ---------------------------------------------------------------------------
def part_a() -> None:
    print("A. Each step on a small example (lines: q0, q1 inputs; the rest ancilla)")
    cases = [
        ("constants: control on a line that is still 0",
         Circuit(4, [TOF(0, 2, 1), CNOT(0, 1)]), [0, 1], [2, 3], [1], ("constants",), 1),
        ("constants: control that is always 1",
         Circuit(4, [X(2), TOF(0, 2, 1)]), [0, 1], [2, 3], [1, 2], ("constants",), 2),
        ("garbage: result that nobody reads",
         Circuit(4, [CNOT(0, 1), TOF(0, 1, 2)]), [0, 1], [2, 3], [1], ("garbage",), 1),
        ("alias: use the original instead of its copy",
         Circuit(4, [CNOT(0, 2), TOF(2, 1, 3)]), [0, 1], [2, 3], [3], ("garbage", "alias"), 1),
        ("xor: skip an intermediate line",
         Circuit(5, [CNOT(0, 2), CNOT(1, 2), CNOT(2, 3)]), [0, 1], [2, 3, 4], [3],
         ("garbage", "xor"), 2),
    ]
    for label, circuit, inputs, ancilla, outputs, steps, expected in cases:
        result = simplify(circuit, inputs, ancilla, outputs, steps)
        same = primary_outputs(circuit, inputs, outputs) == primary_outputs(result.circuit, inputs, outputs)
        report(label, same and len(result.circuit) == expected,
               f"{len(circuit)} -> {len(result.circuit)} gates:  {circuit}   =>   {result.circuit}")
    print()


# ---------------------------------------------------------------------------
# B. Random circuits
# ---------------------------------------------------------------------------
def random_design(n: int):
    gates = []
    for _ in range(rng.randint(8, 30)):
        if rng.random() < 0.8:                                # X, CNOT, Toffoli
            kind = rng.choice((0, 1, 1, 2, 2))
            lines = rng.sample(range(n), kind + 1)
            gates.append(G(lines[1:], [], lines[0]))
        else:                                                 # mixed-polarity gate
            lines = rng.sample(range(n), rng.randint(2, min(4, n)))
            split = rng.randint(0, len(lines) - 1)
            gates.append(G(lines[1:1 + split], lines[1 + split:], lines[0]))
    lines = list(range(n))
    rng.shuffle(lines)
    k = rng.randint(2, n - 1)
    inputs, ancilla = sorted(lines[:k]), sorted(lines[k:])
    outputs = sorted(rng.sample(range(n), rng.randint(1, max(1, n // 2))))
    return Circuit(n, gates), inputs, ancilla, outputs


def part_b() -> None:
    print("B. Random circuits with random ancilla lines and random primary outputs")
    print(f"  {'Lines':<7}{'Circuits':>9}{'Gates before':>14}{'after':>8}"
          f"{'Cost before':>13}{'after':>8}  Result")
    for n, count in ((5, 150), (6, 150), (7, 120), (8, 100), (9, 80)):
        g0 = g1 = c0 = c1 = 0
        ok = True
        for _ in range(count):
            circuit, inputs, ancilla, outputs = random_design(n)
            result = simplify(circuit, inputs, ancilla, outputs)
            ok &= (primary_outputs(circuit, inputs, outputs)
                   == primary_outputs(result.circuit, inputs, outputs))
            ok &= circuit_cost(result.circuit) <= circuit_cost(circuit)
            g0, g1 = g0 + len(circuit), g1 + len(result.circuit)
            c0, c1 = c0 + circuit_cost(circuit), c1 + circuit_cost(result.circuit)
        global failures
        failures += not ok
        print(f"  {n:<7}{count:>9}{g0:>14}{g1:>8}{c0:>13}{c1:>8}  {'PASS' if ok else 'FAIL'}")
    print("  PASS = same primary outputs for every primary input, and no higher cost.\n")


# ---------------------------------------------------------------------------
# C. The adders
# ---------------------------------------------------------------------------
def part_c(designs, results) -> None:
    print("C. Adders before and after simplification (project cost model)")
    print(f"  {'Design':<24}{'Gates':>10}{'Cost':>10}{'Ancilla':>10}{'Garbage':>10}"
          f"{'Depth':>10}{'Cost saved':>12}  Result")
    for d, r in zip(designs, results):
        new = d.with_circuit(r.circuit, d.name)
        cases, wrong = check_adder(new)
        before, after = circuit_cost(d.circuit), circuit_cost(r.circuit)
        ok = wrong == 0 and after <= before
        global failures
        failures += not ok
        print(f"  {d.name:<24}{f'{len(d.circuit)} -> {len(r.circuit)}':>10}"
              f"{f'{before} -> {after}':>10}"
              f"{f'{r.ancilla_used(d.circuit)} -> {r.ancilla_used()}':>10}"
              f"{f'{r.garbage(d.circuit)} -> {r.garbage()}':>10}"
              f"{f'{depth(d.circuit)} -> {depth(r.circuit)}':>10}"
              f"{100 * (before - after) / before:>11.1f}%  {'PASS' if ok else 'FAIL'}")
    print("  PASS = the simplified circuit adds correctly for all 512 input combinations.")
    for d, r in zip(designs, results):
        steps = ", ".join(f"{name} x{count}" for name, count in sorted(r.step_counts.items()))
        print(f"  {d.name}: {steps or 'no step applied'}")
    print()


# ---------------------------------------------------------------------------
# D. Contribution of each step
# ---------------------------------------------------------------------------
def part_d(designs) -> None:
    print("D. Contribution of each step")
    stages = [("no simplification", ()),
              ("rules only (Phase 3)", ("rules",)),
              ("constants", ("constants",)),
              ("constants + garbage", ("constants", "garbage")),
              ("... + alias", ("constants", "garbage", "alias")),
              ("... + xor", ("constants", "garbage", "alias", "xor")),
              ("all steps", ALL_STEPS)]
    for d in designs[:2]:
        print(f"  {d.name}")
        print(f"    {'Steps used':<24}{'Gates':>7}{'Cost':>7}{'Ancilla':>9}{'Garbage':>9}")
        for label, steps in stages:
            r = simplify_design(d, steps)
            ok = check_adder(d.with_circuit(r.circuit, d.name))[1] == 0
            global failures
            failures += not ok
            print(f"    {label:<24}{len(r.circuit):>7}{circuit_cost(r.circuit):>7}"
                  f"{r.ancilla_used():>9}{r.garbage():>9}" + ("" if ok else "  FAIL"))
    print()


# ---------------------------------------------------------------------------
# E. Counted as in the adder paper
# ---------------------------------------------------------------------------
def part_e(designs, results) -> None:
    print("E. Counted the way the adder paper counts (Peres 4, Feynman 1, Toffoli 5)")
    print(f"  {'Design':<34}{'Blocks':>7}{'Ancilla':>9}{'Garbage':>9}{'Cost':>6}{'Total':>7}")
    p = PAPER_REPORTED
    print(f"  {'Reported in the adder paper':<34}{p['gates']:>7}{p['ancilla']:>9}"
          f"{p['garbage']:>9}{p['cost']:>6}{p['trlic']:>7}")
    for d, r in zip(designs, results):
        b0, a0, g0, c0 = d.block_count(), len(d.ancilla), len(d.garbage), d.block_cost()
        print(f"  {d.name + ', as built':<34}{b0:>7}{a0:>9}{g0:>9}{c0:>6}{b0 + a0 + g0 + c0:>7}")
        b1, c1, kinds = block_view(r.circuit)
        a1, g1 = r.ancilla_used(), r.garbage()
        print(f"  {d.name + ', simplified':<34}{b1:>7}{a1:>9}{g1:>9}{c1:>6}{b1 + a1 + g1 + c1:>7}"
              f"   ({', '.join(f'{v} {k}' for k, v in sorted(kinds.items()))})")
    print("  Total = blocks + ancilla + garbage + cost (the paper's TRLIC).")
    print("  Garbage here counts every used line that is not a sum or carry output; the")
    print("  paper does not say how it counts garbage, so its 14 may not be comparable.\n")


# ---------------------------------------------------------------------------
# F. The simplified netlist
# ---------------------------------------------------------------------------
def part_f(design, result) -> None:
    print(f"F. Simplified netlist of '{design.name}'")
    names = design.line_names
    used = sorted(set().union(*(g.lines for g in result.circuit)) | set(design.inputs.values()))
    dropped = [names[l] for l in range(design.n) if l not in used]
    for i, g in enumerate(result.circuit, 1):
        controls = [names[l] for l in sorted(g.pos)] + ["not " + names[l] for l in sorted(g.neg)]
        kind = {0: "NOT", 1: "CNOT", 2: "Toffoli"}.get(len(controls), "MCT")
        print(f"  {i:>2}. {kind:<8}{names[g.target]:<3} ^= {' AND '.join(controls) or '1'}")
    outs = ", ".join(f"{k} on {names[l]}" for k, l in sorted(design.outputs.items()))
    print(f"  Outputs: {outs}")
    print(f"  Ancilla lines no longer needed: {', '.join(dropped) or 'none'}\n")


def main() -> int:
    start = time.time()
    print("Phase 5 verification: ancilla- and garbage-aware simplification\n")
    designs = [cla_adder(), cla_adder(carry_out=True), rca_adder()]
    results = [simplify_design(d) for d in designs]
    part_a()
    part_b()
    part_c(designs, results)
    part_d(designs)
    part_e(designs, results)
    part_f(designs[0], results[0])
    print(f"Time: {time.time() - start:.1f} s")
    print("\nAll checks passed." if failures == 0 else f"\n{failures} check(s) FAILED.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
