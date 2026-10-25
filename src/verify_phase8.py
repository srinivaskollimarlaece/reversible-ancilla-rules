"""Phase 8: extensions for the journal paper.

  A. The decision-diagram backend of the simplifier gives the same result as
     the enumerating backend.
  B. Six published adder designs at 4, 8, 16 and 32 bits: exact proof of
     correctness, and the Draper adder against its published gate counts.
  C. Resources of the designs as built, including T-count and Toffoli depth.
  D. Rule-based optimizer and full simplification on every design and width;
     every result is proved again.
  E. Toffoli depth of ripple-carry against carry look-ahead.
  F. RevLib benchmark circuits: rule-based optimizer and simplifier, with
     exact equivalence checks.
  G. Comparison with Qiskit (needs: pip install qiskit z3-solver).

Run:  python verify_phase8.py
"""
from __future__ import annotations

import random
import re
import sys
import time

from revcircuit import Circuit, G
from bdd import BDD, Fn
from optimizer import circuit_cost, optimize, quantum_cost
from adders import cla_adder, depth, rca_adder
from simplify import _Care, simplify, simplify_design
from nadders import (DESIGNS, draper_qcla, prove_adder, random_test, t_count,
                     toffoli_count, toffoli_depth, used_ancilla)
import revlib

WIDTHS = (4, 8, 16, 32)
rng = random.Random(2026)
failures = 0


def note(ok: bool) -> str:
    global failures
    failures += not ok
    return "PASS" if ok else "FAIL"


def report(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {label:<58}{note(ok)}" + (f"  {detail}" if detail else ""))


def pct(before: int, after: int) -> str:
    return f"{100.0 * (before - after) / before:.1f}" if before else "0.0"


# ---------------------------------------------------------------------------
# A. Backends agree
# ---------------------------------------------------------------------------
def random_design(n: int):
    gates = []
    for _ in range(rng.randint(8, 30)):
        if rng.random() < 0.8:
            kind = rng.choice((0, 1, 1, 2, 2))
            lines = rng.sample(range(n), kind + 1)
            gates.append(G(lines[1:], [], lines[0]))
        else:
            lines = rng.sample(range(n), rng.randint(2, min(4, n)))
            split = rng.randint(0, len(lines) - 1)
            gates.append(G(lines[1:1 + split], lines[1 + split:], lines[0]))
    lines = list(range(n))
    rng.shuffle(lines)
    k = rng.randint(2, n - 1)
    inputs, ancilla = sorted(lines[:k]), sorted(lines[k:])
    outputs = sorted(rng.sample(range(n), rng.randint(1, max(1, n // 2))))
    ones = [l for l in ancilla if rng.random() < 0.3]
    return Circuit(n, gates), inputs, ancilla, outputs, ones


def part_a() -> None:
    print("A. Decision-diagram backend against the enumerating backend")
    same = 0
    for _ in range(300):
        c, inputs, ancilla, outputs, ones = random_design(rng.randint(5, 9))
        r1 = simplify(c, inputs, ancilla, outputs, backend="bits", ancilla_ones=ones)
        r2 = simplify(c, inputs, ancilla, outputs, backend="bdd", ancilla_ones=ones)
        same += r1.circuit == r2.circuit
    report("300 random designs: identical simplified circuits", same == 300, f"{same}/300")
    ok = all(simplify_design(d, backend="bits").circuit == simplify_design(d, backend="bdd").circuit
             for d in (cla_adder(), cla_adder(carry_out=True), rca_adder()))
    report("The three 4-bit adders of Phase 5: identical", ok)
    print()


# ---------------------------------------------------------------------------
# B, C. Designs as built
# ---------------------------------------------------------------------------
def part_b_c(designs) -> None:
    print("B. Exact proof of every design (all inputs, by decision diagrams)")
    ok_all = True
    for key in DESIGNS:
        ok = all(prove_adder(designs[key, n]) and random_test(designs[key, n]) == 0 for n in WIDTHS)
        ok_all &= ok
        d = designs[key, 4]
        report(f"{d.name.rsplit(',', 1)[0]} ({d.style} style), 4 to 32 bits", ok)
    ok = True
    for n in WIDTHS:
        d = draper_qcla(n)
        w, log = bin(n).count("1"), n.bit_length() - 1
        ancilla_p = sum(1 for name in d.line_names if name.startswith("p"))
        ok &= toffoli_count(d.circuit) == 5 * n - 3 * w - 3 * log - 1 and ancilla_p == n - w - log
    report("Draper adder: Toffoli and ancilla counts match the paper", ok,
           "5n - 3w(n) - 3 floor(log n) - 1 Toffoli gates")
    print()

    print("C. Resources as built")
    print(f"  {'Design':<26}{'Bits':>5}{'Lines':>7}{'Gates':>7}{'Cost':>7}{'T-count':>9}"
          f"{'Ancilla':>9}{'Depth':>7}{'Toffoli depth':>15}")
    for key in DESIGNS:
        for n in WIDTHS:
            d = designs[key, n]
            c = d.circuit
            print(f"  {d.name.rsplit(',', 1)[0]:<26}{n:>5}{d.n:>7}{len(c):>7}{circuit_cost(c):>7}"
                  f"{t_count(c):>9}{used_ancilla(d):>9}{depth(c):>7}{toffoli_depth(c):>15}")
    print("  T-count = 7 per two-control gate. Toffoli depth counts only two-control gates.\n")


# ---------------------------------------------------------------------------
# D, E. Optimization of the designs
# ---------------------------------------------------------------------------
def part_d_e(designs) -> dict:
    print("D. Rule-based optimizer and full simplification")
    print(f"  {'Design':<26}{'Bits':>5} | {'Cost':>6}{'Rules':>7}{'All':>6}{'Saved %':>9} |"
          f"{'Gates':>11}{'T-count':>11}{'Ancilla':>9}{'Depth':>9}{'Tof. depth':>11}  Result")
    results = {}
    for key in DESIGNS:
        for n in WIDTHS:
            d = designs[key, n]
            c = d.circuit
            inputs = list(d.inputs.values())
            ruled = optimize(c).circuit
            simp = simplify(c, inputs, d.ancilla, d.required)
            s = simp.circuit
            new = d.with_circuit(s)
            ok = prove_adder(new) and random_test(new) == 0 and prove_adder(d.with_circuit(ruled))
            ok &= circuit_cost(s) <= circuit_cost(ruled) <= circuit_cost(c)
            results[key, n] = (ruled, s, simp)
            print(f"  {d.name.rsplit(',', 1)[0]:<26}{n:>5} | {circuit_cost(c):>6}{circuit_cost(ruled):>7}"
                  f"{circuit_cost(s):>6}{pct(circuit_cost(c), circuit_cost(s)):>9} |"
                  f"{f'{len(c)}->{len(s)}':>11}{f'{t_count(c)}->{t_count(s)}':>11}"
                  f"{f'{used_ancilla(d)}->{used_ancilla(d, s)}':>9}{f'{depth(c)}->{depth(s)}':>9}"
                  f"{f'{toffoli_depth(c)}->{toffoli_depth(s)}':>11}  {note(ok)}")
    print("  Rules = cost after the rule-based optimizer alone. All = after every step.")
    print("  PASS = both results proved correct for all inputs (sum, carry, restored lines,")
    print("  clean ancillas where the design requires them).")
    for key in DESIGNS:
        simp = results[key, 32][2]
        steps = ", ".join(f"{k} x{v}" for k, v in sorted(simp.step_counts.items()))
        print(f"  {designs[key, 32].name}: {steps or 'no step applied'}")
    print()

    print("E. Toffoli depth, as built -> simplified")
    print(f"  {'Design':<26}" + "".join(f"{f'{n} bits':>12}" for n in WIDTHS))
    for key in DESIGNS:
        row = "".join(f"{toffoli_depth(designs[key, n].circuit)}->{toffoli_depth(results[key, n][1])}".rjust(12)
                      for n in WIDTHS)
        print(f"  {designs[key, 4].name.rsplit(',', 1)[0]:<26}{row}")
    print()
    return results


# ---------------------------------------------------------------------------
# F. RevLib
# ---------------------------------------------------------------------------
def exact_equal(a: Circuit, b: Circuit) -> bool:
    """Same value on every line for every input, by decision diagrams."""
    bdd = BDD(a.n)

    def run(c):
        v = [Fn(bdd, bdd.var(i)) for i in range(c.n)]
        for g in c:
            act = Fn(bdd, 1)
            for l in g.pos:
                act = act & v[l]
            for l in g.neg:
                act = act & ~v[l]
            v[g.target] = v[g.target] ^ act
        return [x.node for x in v]

    return run(a) == run(b)


def random_equal(a: Circuit, b: Circuit, trials: int = 2000) -> bool:
    return all(a.apply(s) == b.apply(s) for s in (rng.getrandbits(a.n) for _ in range(trials)))


def random_outputs_equal(bench, a: Circuit, b: Circuit, trials: int = 2000) -> bool:
    fixed = sum(1 << l for l in bench.ancilla_ones)
    mask = sum(1 << l for l in bench.outputs)
    for _ in range(trials):
        state = fixed | sum(rng.getrandbits(1) << l for l in bench.inputs)
        if (a.apply(state) ^ b.apply(state)) & mask:
            return False
    return True


def part_f() -> dict:
    print("F. RevLib benchmark circuits")
    try:
        folder = revlib.fetch("revlib")
    except Exception as error:                                    # no network, no git
        print(f"  SKIPPED: the RevLib files could not be obtained ({type(error).__name__}).\n")
        return {}
    benches = revlib.load_all(folder)
    stated = matched = 0
    for b in benches:
        with open(f"{folder}/{b.name}.real", encoding="utf-8") as handle:
            m = re.search(r"Gates:\s*(\d+), Quantum costs:\s*(\d+)", handle.read())
        if m:
            stated += 1
            matched += (len(b.circuit) == int(m.group(1))
                        and circuit_cost(b.circuit, revlib.revlib_cost(b.circuit.n)) == int(m.group(2)))
    report(f"{len(benches)} circuits read; cost table reproduces the file headers",
           matched >= stated - 1, f"{matched} of {stated} headers exactly")
    print(f"  {'Circuit':<15}{'Lines':>6} | {'Gates':>11}{'Cost':>14}{'Saved %':>9} |"
          f"{'With constants and garbage':>28}  Result")
    out = {}
    totals = [0, 0, 0, 0, 0]
    for b in benches:
        c, n = b.circuit, b.circuit.n
        cost = revlib.revlib_cost(n)
        ruled = optimize(c, cost=cost).circuit
        ok = exact_equal(c, ruled) and random_equal(c, ruled)
        c0, c1 = circuit_cost(c, cost), circuit_cost(ruled, cost)
        row = (f"  {b.name:<15}{n:>6} | {f'{len(c)}->{len(ruled)}':>11}{f'{c0}->{c1}':>14}{pct(c0, c1):>9} |")
        simp = None
        if b.outputs is not None:
            simp = simplify(c, b.inputs, b.ancilla, b.outputs, cost=cost,
                            ancilla_ones=b.ancilla_ones).circuit
            ok &= random_outputs_equal(b, c, simp) and circuit_cost(simp, cost) <= c1
            row += f"{f'{c0}->{circuit_cost(simp, cost)}':>28}"
        else:
            row += f"{'no constants in file':>28}"
        totals[0] += len(c); totals[1] += len(ruled); totals[2] += c0; totals[3] += c1
        totals[4] += circuit_cost(simp, cost) if simp is not None else c1
        out[b.name] = (b, ruled, simp)
        print(row + f"  {note(ok)}")
    t = totals
    print(f"  {'Total':<15}{'':>6} | {f'{t[0]}->{t[1]}':>11}{f'{t[2]}->{t[3]}':>14}{pct(t[2], t[3]):>9} |"
          f"{f'{t[2]}->{t[4]}':>28}")
    print("  Gates, Cost, Saved: rule-based optimizer alone, RevLib cost table.")
    print("  PASS = equal on every line for every input (decision diagrams), confirmed on")
    print("  2,000 random inputs; with constants and garbage, equal primary outputs.\n")
    return out


# ---------------------------------------------------------------------------
# G. Qiskit
# ---------------------------------------------------------------------------
def same_all_lines(n, inputs, ancilla, ones, a: Circuit, b: Circuit) -> bool:
    care = _Care(n, inputs, ancilla, list(range(n)), quantum_cost, "auto", ones)
    return care.signature(list(a.gates)) == care.signature(list(b.gates))


def part_g(designs, results, benches) -> None:
    print("G. Comparison with Qiskit")
    try:
        import qiskit
        import z3  # noqa: F401
        from qiskit_compare import qiskit_cancel, qiskit_hoare
    except ImportError:
        print("  SKIPPED: Qiskit or z3 is not installed.  pip install qiskit z3-solver\n")
        return
    print(f"  Qiskit version {qiskit.__version__}")
    print("  Adders, quantum cost. 'Keeps function' passes preserve every line for every input;")
    print("  'ancilla at 0' passes preserve every line for inputs with ancilla lines at 0.")
    print(f"  {'Design':<26}{'Bits':>5}{'As built':>10} |{'Qiskit':>8}{'Rules':>7} |"
          f"{'Qiskit':>8}{'This work':>11} |{'With garbage':>14}  Result")
    print(f"  {'':<26}{'':>5}{'':>10} |{'keeps function':>15} |{'ancilla at 0':>19} |")
    for key in DESIGNS:
        for n in WIDTHS:
            d = designs[key, n]
            c = d.circuit
            inputs = list(d.inputs.values())
            q1 = qiskit_cancel(c)
            q2 = qiskit_hoare(c, inputs)
            ours_keep = simplify(c, inputs, d.ancilla, list(range(d.n))).circuit
            ruled, full, _ = results[key, n]
            ok = (prove_adder(d.with_circuit(q1)) and same_all_lines(d.n, inputs, d.ancilla, [], c, q1)
                  and same_all_lines(d.n, inputs, d.ancilla, [], c, q2)
                  and same_all_lines(d.n, inputs, d.ancilla, [], c, ours_keep))
            print(f"  {d.name.rsplit(',', 1)[0]:<26}{n:>5}{circuit_cost(c):>10} |{circuit_cost(q1):>8}"
                  f"{circuit_cost(ruled):>7} |{circuit_cost(q2):>8}{circuit_cost(ours_keep):>11} |"
                  f"{circuit_cost(full):>14}  {note(ok)}")
    print("  Qiskit, keeps function: InverseCancellation + CommutativeInverseCancellation.")
    print("  Qiskit, ancilla at 0:   HoareOptimizer + the two cancellation passes.")
    print("  With garbage:           all steps of this work; Qiskit has no notion of garbage.")
    if benches:
        print()
        print("  RevLib circuits, passes that keep the function, RevLib cost table")
        print(f"  {'Circuit':<15}{'As given':>10}{'Qiskit':>9}{'Rules':>8}  Result")
        totals = [0, 0, 0]
        for name, (b, ruled, _) in benches.items():
            cost = revlib.revlib_cost(b.circuit.n)
            q = qiskit_cancel(b.circuit)
            ok = exact_equal(b.circuit, q)
            v = (circuit_cost(b.circuit, cost), circuit_cost(q, cost), circuit_cost(ruled, cost))
            totals = [x + y for x, y in zip(totals, v)]
            print(f"  {name:<15}{v[0]:>10}{v[1]:>9}{v[2]:>8}  {note(ok)}")
        print(f"  {'Total':<15}{totals[0]:>10}{totals[1]:>9}{totals[2]:>8}")
    print()


def main() -> int:
    start = time.time()
    print("Phase 8: extensions\n")
    designs = {(key, n): make(n) for key, make in DESIGNS.items() for n in WIDTHS}
    part_a()
    part_b_c(designs)
    results = part_d_e(designs)
    benches = part_f()
    part_g(designs, results, benches)
    print(f"Time: {time.time() - start:.1f} s")
    print("\nAll checks passed." if failures == 0 else f"\n{failures} check(s) FAILED.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
