"""Phase 1 verification: every rule is checked by exhaustive simulation.

For each rule, every instance on 2 to MAX_N lines is generated. Two checks run:

  1. Soundness: the two sides of the rule compute the same permutation.
  2. Rewrite function: the instance is placed between random gates, the
     rewrite function is applied at that position, and the result must be
     the expected gate list and still compute the same function.

Run:  python verify_phase1.py          (lines 2 to 5)
      python verify_phase1.py 4        (lines 2 to 4, faster)
"""
from __future__ import annotations

import random
import sys
import time
from itertools import combinations, permutations

from revcircuit import CNOT, Circuit, G, X, all_gates, pn_choices, random_gate
import rules as R

# The circuit drawings use Unicode symbols; make sure they print on Windows too.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

MAX_N = int(sys.argv[1]) if len(sys.argv) > 1 else 5
PAIR_MAX_N = min(MAX_N, 4)          # rules over all gate pairs grow fastest
rng = random.Random(2026)


def subsets(s):
    s = sorted(s)
    for r in range(len(s) + 1):
        for sub in combinations(s, r):
            yield frozenset(sub)


# ---------------------------------------------------------------------------
# Instance generators: each yields (lhs gates, rhs gates, rewrite function)
# ---------------------------------------------------------------------------
def gen_rule1(n):
    for g in all_gates(n):
        yield [g, g], [], R.rule1_cancel


def gen_rule2(n):
    for g in all_gates(n):
        for p in range(n):
            if p not in g.lines:
                pair = R.rule2_gates(g, p)
                yield pair, [g], R.rule2_merge
                yield [g], pair, (lambda c, i, p=p: R.rule2_split(c, i, p))


def gen_rule3(n):
    gates = all_gates(n)
    for a in gates:
        for b in gates:
            if a != b and R.rule3_condition(a, b):
                yield [a, b], [b, a], R.rule3_commute


def gen_rule4(n):
    for p in range(n):
        for q in range(n):
            if p == q:
                continue
            others = [l for l in range(n) if l not in (p, q)]
            for P, N in pn_choices(others):
                for negative in (False, True):
                    lhs, rhs = R.rule4_sides(p, q, P, N, negative)
                    yield lhs, rhs, R.rule4_apply
                    yield rhs, lhs, R.rule4_apply


def gen_rule5(n):
    for q0 in range(n):
        rest = [l for l in range(n) if l != q0]
        for m in range(1, len(rest) + 1):
            for Q in permutations(rest, m):
                others = [l for l in rest if l not in Q]
                for P, N in pn_choices(others):
                    lhs, rhs = R.rule5_sides(P, N, Q, q0)
                    yield lhs, rhs, R.rule5_apply
                    yield rhs, lhs, (lambda c, i, Q=Q, q0=q0: R.rule5_reverse(c, i, Q, q0))


def gen_rule6(n):
    for g in all_gates(n):
        free = [l for l in range(n) if l not in g.lines]
        for Q in subsets(free):
            if Q:
                yield [g], R.rule6_gates(g, Q), (lambda c, i, Q=Q: R.rule6_expand(c, i, Q))


def gen_rule7(n):
    gates = all_gates(n)
    for a in gates:
        for b in gates:
            if a != b and a.target == b.target:
                yield [a, b], [b, a], R.rule7_commute


def gen_rule8(n):
    for g in all_gates(n):
        if g.neg:
            expanded = R.rule8_gates(g)
            yield [g], expanded, R.rule8_expand
            yield expanded, [g], R.rule8_collapse


def gen_rule9(n):
    for p in range(n):
        for q in range(n):
            if p == q:
                continue
            others = [l for l in range(n) if l not in (p, q)]
            for P2, N2 in pn_choices(others):
                b1 = G(P2 | {p}, N2, q)
                b2 = G(P2, N2 | {p}, q)
                for P1 in subsets(P2):
                    for N1 in subsets(N2):
                        a = G(P1, N1, p)
                        yield [a, b1], [b2, a], R.rule9_apply
                        yield [b2, a], [a, b1], R.rule9_apply
                        yield [a, b2], [b1, a], R.rule9_apply


def gen_rule10(n):
    for p in range(n):
        for q in range(n):
            if p == q:
                continue
            others = [l for l in range(n) if l not in (p, q)]
            for P in subsets(others):
                lhs, rhs = R.rule10_sides(P, p, q)
                yield lhs, rhs, R.rule10_apply


RULES = [
    ("1", "A A = empty", gen_rule1, MAX_N),
    ("2", "merge / split on one control", gen_rule2, MAX_N),
    ("3", "commute, opposite-polarity control", gen_rule3, PAIR_MAX_N),
    ("4", "move swap through a gate", gen_rule4, MAX_N),
    ("5", "change control polarity", gen_rule5, MAX_N),
    ("6", "expand over unused lines", gen_rule6, MAX_N),
    ("7", "commute, same target", gen_rule7, PAIR_MAX_N),
    ("8", "negative controls <-> X gates", gen_rule8, MAX_N),
    ("9", "move gate past neighbour", gen_rule9, MAX_N),
    ("10", "A B A = B A B", gen_rule10, MAX_N),
]


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------
def check_rule(gen, max_n):
    """Return (instances checked, embedded rewrites checked, first failure or None)."""
    sound = embedded = 0
    for n in range(2, max_n + 1):
        for lhs, rhs, fn in gen(n):
            left, right = Circuit(n, lhs), Circuit(n, rhs)
            if not left.equivalent(right):
                return sound, embedded, f"NOT EQUIVALENT on {n} lines: {left}  vs  {right}"
            sound += 1
            # Embedded rewrite test (all instances on small n, a sample on larger n).
            if n <= 3 or rng.random() < 0.1:
                prefix = [random_gate(n, rng) for _ in range(rng.randrange(4))]
                suffix = [random_gate(n, rng) for _ in range(rng.randrange(4))]
                before = Circuit(n, prefix + lhs + suffix)
                after = fn(before, len(prefix))
                if after is None:
                    return sound, embedded, f"rewrite did not match: {left}"
                if after.gates != prefix + rhs + suffix:
                    return sound, embedded, f"rewrite gave unexpected gates: {left}"
                if not after.equivalent(before):
                    return sound, embedded, f"rewrite changed the function: {left}"
                embedded += 1
    return sound, embedded, None


def main() -> int:
    print(f"Phase 1 verification, lines 2 to {MAX_N} "
          f"(pair rules 3 and 7: 2 to {PAIR_MAX_N})\n")
    print(f"{'Rule':<5}{'Statement':<38}{'Instances':>10}{'Rewrites':>10}  Result")
    print("-" * 72)
    failures = 0
    start = time.time()
    for name, text, gen, max_n in RULES:
        sound, embedded, err = check_rule(gen, max_n)
        result = "PASS" if err is None else "FAIL"
        failures += err is not None
        print(f"{name:<5}{text:<38}{sound:>10}{embedded:>10}  {result}")
        if err:
            print(f"      {err}")
    print("-" * 72)
    print(f"Time: {time.time() - start:.1f} s\n")

    # Sanity check: the equivalence test must reject a wrong rewrite.
    wrong_a = Circuit(2, [CNOT(0, 1), CNOT(1, 0)])
    wrong_b = Circuit(2, [CNOT(1, 0), CNOT(0, 1)])
    detected = not wrong_a.equivalent(wrong_b)
    failures += not detected
    print("Sanity check, non-commuting gates detected as different:",
          "PASS" if detected else "FAIL")

    # Worked example: Example 2 of Feng and Li.
    print("\nWorked example (Example 2 of the paper):")
    print("X[q0] CNOT[q0,q1] X[q0]  ->  negatively controlled NOT\n")
    c = Circuit(2, [X(0), CNOT(0, 1), X(0)])
    steps = [("Start", c)]
    c = R.rule2_split(c, 0, 1); steps.append(("Rule 2 on the first X", c))
    c = R.rule2_split(c, 3, 1); steps.append(("Rule 2 on the second X", c))
    c = R.rule3_commute(c, 3);  steps.append(("Rule 3 on the last two gates", c))
    c = R.rule5_apply(c, 0);    steps.append(("Rule 5 on the whole circuit", c))
    for label, circ in steps:
        print(f"{label}:  {circ}")
        print(circ.draw())
        print()
    ok = (c == Circuit(2, [G((), {0}, 1)])) and all(s.equivalent(steps[0][1]) for _, s in steps)
    failures += not ok
    print("Example 2 reproduced:", "PASS" if ok else "FAIL")

    print("\nAll checks passed." if failures == 0 else f"\n{failures} check(s) FAILED.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
