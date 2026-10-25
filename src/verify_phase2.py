"""Phase 2 verification: canonical form of reversible circuits.

Checks, in order:

  A. The paper's worked examples (Examples 4, 5 and 7) are reproduced.
  B. Algorithm 1 on every 2-bit and 3-bit reversible function, and on random
     4-bit and 5-bit functions: the canonical circuit computes the function,
     satisfies Definition 1 and Fact 1, and different functions get
     different canonical circuits.
  C. Equivalent circuits get the same canonical form; non-equivalent
     circuits get different ones. Equivalent circuits are produced by
     rewriting with the Phase 1 rules.
  D. Other Hamiltonian paths also work (Remark 1 of the paper).
  E. Size of the canonical circuit as the number of lines grows.

Run:  python verify_phase2.py
"""
from __future__ import annotations

import random
import sys
import time
from itertools import permutations
from math import factorial

from revcircuit import CNOT, Circuit, X, random_circuit, random_gate
import rules as R
from canonical import (bits_of, canonical_blocks, canonical_form,
                       canonical_from_function, circuit_from_indices,
                       count_canonical_forms, delta_gates, fact1_holds,
                       function_from_table, gray_path, is_canonical,
                       is_hamiltonian_path, max_canonical_gates)

# The circuit drawings use Unicode symbols; make sure they print on Windows too.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

rng = random.Random(2026)
failures = 0


def report(label: str, ok: bool, detail: str = "") -> None:
    global failures
    failures += not ok
    print(f"  {label:<58}{'PASS' if ok else 'FAIL'}" + (f"  {detail}" if detail else ""))


# ---------------------------------------------------------------------------
# A. Worked examples from the paper
# ---------------------------------------------------------------------------
def part_a() -> None:
    print("A. Worked examples from the paper")
    n = 3
    path = gray_path(n)
    expected_path = "000 001 011 010 110 111 101 100".split()
    report("Hamiltonian path of Example 4",
           [bits_of(s, n) for s in path] == expected_path)

    # Example 4: function of Table I, canonical circuit M3 M4 M5 M0 M1 M2.
    table = {"000": "010", "001": "000", "010": "101", "011": "001",
             "100": "100", "101": "111", "110": "011", "111": "110"}
    f = function_from_table(n, table)
    cf4 = canonical_from_function(n, f)
    report("Example 4: canonical circuit of Table I",
           cf4.indices == [3, 4, 5, 0, 1, 2] and cf4.circuit.permutation() == tuple(f),
           str(cf4))

    # Example 5: a 9-gate circuit over Delta_H reduces to C2 C1 C0.
    c5 = circuit_from_indices(n, [4, 2, 3, 0, 4, 1, 3, 4, 0])
    cf5 = canonical_form(c5)
    report("Example 5: M4 M2 M3 M0 M4 M1 M3 M4 M0",
           cf5.indices == [2, 3, 1, 0, 1], str(cf5))

    # Example 7: the circuit of Example 3, CNOT[q0,q1] CNOT[q1,q2].
    c7 = Circuit(n, [CNOT(0, 1), CNOT(1, 2)])
    cf7 = canonical_form(c7)
    report("Example 7: CNOT[q0,q1] CNOT[q1,q2]",
           cf7.indices == [5, 6, 4, 5, 6, 2], str(cf7))

    print("\n  Gates of Delta_H for 3 lines (Fig. 4 of the paper):")
    for i, g in enumerate(delta_gates(n)):
        print(f"    M{i}: exchanges {bits_of(path[i], n)} and {bits_of(path[i + 1], n)}   {g}")
    print("\n  Canonical circuit of Example 4:  " + str(cf4))
    for line in cf4.circuit.draw().splitlines():
        print("    " + line)
    print()


# ---------------------------------------------------------------------------
# B. Algorithm 1 on reversible functions
# ---------------------------------------------------------------------------
def check_function(n: int, perm, path=None):
    """Return (canonical form, all properties hold)."""
    cf = canonical_from_function(n, perm, path)
    idx = cf.indices
    ok = (cf.circuit.permutation() == tuple(perm)
          and is_canonical(idx, n) and fact1_holds(idx, n)
          and len(idx) <= max_canonical_gates(n))
    return cf, ok


def part_b() -> dict:
    print("B. Algorithm 1 on reversible functions")
    print(f"  {'Lines':<7}{'Functions':>10}{'Coverage':>12}{'Distinct forms':>16}"
          f"{'Avg gates':>11}{'Max gates':>11}{'Bound':>8}  Result")
    stats = {}
    for n, sample in ((2, None), (3, None), (4, 2000), (5, 200)):
        size = 1 << n
        if sample is None:
            functions = permutations(range(size))
            coverage = "all"
        else:
            functions = (tuple(rng.sample(range(size), size)) for _ in range(sample))
            coverage = "random"
        seen, total_gates, max_gates, count, ok = {}, 0, 0, 0, True
        for perm in functions:
            cf, good = check_function(n, perm)
            ok &= good
            key = tuple(cf.indices)
            # Two different functions must never share a canonical circuit.
            ok &= seen.setdefault(key, perm) == perm
            total_gates += len(cf)
            max_gates = max(max_gates, len(cf))
            count += 1
        if sample is None:
            # Every function has its own form, and the number of index lists
            # allowed by Definition 1 equals the number of functions.
            ok &= len(seen) == count == factorial(size) == count_canonical_forms(n)
        stats[n] = (count, total_gates / count, max_gates)
        global failures
        failures += not ok
        print(f"  {n:<7}{count:>10}{coverage:>12}{len(seen):>16}{total_gates / count:>11.1f}"
              f"{max_gates:>11}{max_canonical_gates(n):>8}  {'PASS' if ok else 'FAIL'}")
    print("  Each row checks: the canonical circuit computes the function, satisfies")
    print("  Definition 1 and Fact 1, and no two functions share a canonical circuit.\n")
    return stats


# ---------------------------------------------------------------------------
# C. Equivalent circuits give the same canonical form
# ---------------------------------------------------------------------------
def scramble(c: Circuit, steps: int, max_len: int = 60) -> Circuit:
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


def part_c() -> None:
    print("C. Equivalent and non-equivalent circuits")
    print(f"  {'Lines':<7}{'Pairs':>7}{'Rewritten differently':>23}"
          f"{'Same form':>11}{'Changed circuit differs':>25}  Result")
    for n, pairs in ((3, 300), (4, 200), (5, 100)):
        differ = same = separated = 0
        for _ in range(pairs):
            c = random_circuit(n, rng.randint(3, 10), rng)
            d = scramble(c, 40)
            differ += c != d
            same += canonical_form(c).indices == canonical_form(d).indices
            # One extra gate changes the function, so the form must change.
            k = rng.randrange(len(d) + 1)
            e = d.replace(k, k, [random_gate(n, rng)])
            separated += canonical_form(e).indices != canonical_form(c).indices
        ok = same == pairs and separated == pairs and differ > pairs // 2
        global failures
        failures += not ok
        print(f"  {n:<7}{pairs:>7}{differ:>23}{same:>11}{separated:>25}  "
              f"{'PASS' if ok else 'FAIL'}")
    print("  Each pair is a random circuit and a copy rewritten by 40 random rule steps.\n")


# ---------------------------------------------------------------------------
# D. Other Hamiltonian paths (Remark 1)
# ---------------------------------------------------------------------------
def random_path(n: int):
    """A Hamiltonian path made from the Gray code by renaming lines, flipping bits, reversing."""
    order = list(range(n))
    rng.shuffle(order)
    mask = rng.randrange(1 << n)
    path = [sum(((s >> i) & 1) << order[i] for i in range(n)) ^ mask for s in gray_path(n)]
    return path[::-1] if rng.random() < 0.5 else path


def part_d() -> None:
    print("D. Other Hamiltonian paths")
    for n, paths, per_path in ((3, 20, 200), (4, 20, 50)):
        ok, used = True, set()
        for _ in range(paths):
            path = random_path(n)
            ok &= is_hamiltonian_path(n, path)
            used.add(tuple(path))
            for _ in range(per_path):
                perm = tuple(rng.sample(range(1 << n), 1 << n))
                ok &= check_function(n, perm, path)[1]
        report(f"{n} lines: {len(used)} different paths, {per_path} functions each", ok)
    print()


# ---------------------------------------------------------------------------
# E. Growth of the canonical circuit
# ---------------------------------------------------------------------------
def part_e(stats: dict) -> None:
    print("E. Size of the canonical circuit")
    print("  Canonical circuit of ONE gate placed on n lines (Gray-code path).")
    print("  Every canonical gate is an n-bit gate with n - 1 controls.")
    print(f"  {'Lines':<7}{'X[q0]':>12}{'CNOT[q0,q1]':>14}{'Worst case':>13}")
    for n in range(2, 11):
        path = gray_path(n)
        sizes = []
        for gate in (X(0), CNOT(0, 1)):
            perm = Circuit(n, [gate]).permutation()
            sizes.append(sum(len(b) for b in canonical_blocks(n, perm, path)))
        print(f"  {n:<7}{sizes[0]:>12}{sizes[1]:>14}{max_canonical_gates(n):>13}")
    print("  Worst case = 2^n (2^n - 1) / 2 gates.")
    print("  Average over the functions tested in part B: "
          + ", ".join(f"{n} lines {avg:.1f}" for n, (_, avg, _) in stats.items()) + ".\n")


def main() -> int:
    start = time.time()
    print("Phase 2 verification: canonical form\n")
    part_a()
    stats = part_b()
    part_c()
    part_d()
    part_e(stats)
    print(f"Time: {time.time() - start:.1f} s")
    print("\nAll checks passed." if failures == 0 else f"\n{failures} check(s) FAILED.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
