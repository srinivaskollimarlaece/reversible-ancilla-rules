"""Phase 11: rewrite rules for ancilla and garbage lines, and a hybrid adder.

Run:  python verify_phase11.py      (about one minute)

  A. Soundness of rules A1 to A5 on random circuits, checked with the plain
     one-input-at-a-time simulator (independent of the rule code).
  B. The six adders: RC rules alone, RC with rules A1-A5 (local), and the
     global simplifier of Phase 5, at 4 to 32 bits. Exact proofs.
  C. Which rule matters: each rule left out in turn, 32-bit adders.
  D. RevLib circuits: RC alone, RC with A1-A5, global simplifier.
  E. The hybrid carry look-ahead adder: exact proofs at 2 to 32 bits,
     resources, and the comparison with the six designs after all steps,
     with the designs that are Pareto-optimal.
"""
from __future__ import annotations

import random
import sys
import time

from revcircuit import Circuit, G
from optimizer import circuit_cost, optimize
from simplify import simplify
from arules import ALL_RULES, ancilla_optimize
from nadders import DESIGNS, prove_adder, random_test, t_count, toffoli_depth, used_ancilla
from hybrid import hybrid_cla
from adders import depth
import revlib

WIDTHS = (4, 8, 16, 32)
failures = 0


def report(label: str, ok: bool, detail: str = "") -> None:
    global failures
    failures += 0 if ok else 1
    print(f"  {label:<60}{'PASS' if ok else 'FAIL'}  {detail}")


def pct(a, b):
    return f"{100.0 * (a - b) / a:.1f}" if a else "0.0"


def part_a() -> None:
    print("A. Soundness of rules A1-A5 on random circuits")
    rng = random.Random(7)
    wrong = changed = 0
    trials = 800
    for _ in range(trials):
        n = rng.randint(4, 8)
        lines = list(range(n))
        rng.shuffle(lines)
        k = rng.randint(1, n - 1)
        inputs, ancilla = sorted(lines[:k]), sorted(lines[k:])
        ones = [l for l in ancilla if rng.random() < 0.3]
        outputs = sorted(rng.sample(range(n), rng.randint(1, n)))
        gates = []
        for _ in range(rng.randint(5, 25)):
            t = rng.randrange(n)
            others = [l for l in range(n) if l != t]
            ctrl = rng.sample(others, min(rng.choice([0, 1, 1, 2, 2, 2, 3]), len(others)))
            pos = [c for c in ctrl if rng.random() < 0.7]
            gates.append(G(pos, [c for c in ctrl if c not in pos], t))
        c = Circuit(n, gates)
        use = tuple(r for r in ALL_RULES if rng.random() < 0.85) or ALL_RULES
        r = ancilla_optimize(c, inputs, ancilla, outputs, ones, use_rc=rng.random() < 0.5,
                             check=False, use=use)
        changed += r.circuit.gates != c.gates
        base = sum(1 << l for l in ones)
        mask = sum(1 << l for l in outputs)
        for bits in range(1 << k):
            s = base | sum(((bits >> i) & 1) << l for i, l in enumerate(inputs))
            if (c.apply(s) ^ r.circuit.apply(s)) & mask:
                wrong += 1
                break
    report(f"{trials} random circuits, primary outputs unchanged", wrong == 0,
           f"{changed} circuits rewritten, {wrong} wrong")
    print()


def part_b() -> dict:
    print("B. Adders: RC alone, RC + rules A1-A5 (local), global simplifier (quantum cost)")
    print(f"  {'Design':<26}{'Bits':>5}{'As built':>10}{'RC':>7}{'RC+A':>7}{'Global':>8}  Result")
    totals = [0, 0, 0, 0]
    out = {}
    for key, make in DESIGNS.items():
        for n in WIDTHS:
            d = make(n)
            args = (d.circuit, list(d.inputs.values()), d.ancilla, d.required)
            rc = optimize(d.circuit).circuit
            loc = ancilla_optimize(*args)
            glob = simplify(*args).circuit
            ok = prove_adder(d.with_circuit(loc.circuit)) and random_test(d.with_circuit(loc.circuit)) == 0
            v = [circuit_cost(x) for x in (d.circuit, rc, loc.circuit, glob)]
            totals = [a + b for a, b in zip(totals, v)]
            out[key, n] = loc
            print(f"  {d.name.rsplit(',', 1)[0]:<26}{n:>5}{v[0]:>10}{v[1]:>7}{v[2]:>7}{v[3]:>8}  {'PASS' if ok else 'FAIL'}")
            if not ok:
                global failures
                failures += 1
    saved_local, saved_global = totals[0] - totals[2], totals[0] - totals[3]
    print(f"  {'Total':<31}{totals[0]:>10}{totals[1]:>7}{totals[2]:>7}{totals[3]:>8}")
    print(f"  Saving: RC {totals[0] - totals[1]}, RC+A {saved_local}, global {saved_global}. "
          f"The local rules reach {100.0 * saved_local / saved_global:.1f}% of the global saving.")
    print("  Rule uses at 32 bits:")
    for key in DESIGNS:
        counts = out[key, 32].counts
        text = ", ".join(f"{k} x{v}" for k, v in sorted(counts.items())) or "none"
        print(f"    {key:<12} {text}")
    print()
    return out


def part_c() -> None:
    print("C. Each rule left out in turn, 32-bit adders (quantum cost with RC + the other rules)")
    print(f"  {'Design':<14}{'all':>6}" + "".join(f"{'no ' + r:>7}" for r in ALL_RULES))
    for key, make in DESIGNS.items():
        d = make(32)
        args = (d.circuit, list(d.inputs.values()), d.ancilla, d.required)
        full = circuit_cost(ancilla_optimize(*args).circuit)
        row = [circuit_cost(ancilla_optimize(*args, use=tuple(x for x in ALL_RULES if x != r)).circuit)
               for r in ALL_RULES]
        print(f"  {key:<14}{full:>6}" + "".join(f"{v:>7}" for v in row))
    print()


def part_d() -> None:
    print("D. RevLib circuits with constant inputs (RevLib cost table)")
    try:
        folder = revlib.fetch("revlib")
    except Exception as error:
        print(f"  SKIPPED: the RevLib files could not be obtained ({type(error).__name__}).\n")
        return
    totals = [0, 0, 0, 0]
    count = 0
    for b in revlib.load_all(folder):
        if b.outputs is None:
            continue
        cost = revlib.revlib_cost(b.circuit.n)
        rc = optimize(b.circuit, cost=cost).circuit
        loc = ancilla_optimize(b.circuit, b.inputs, b.ancilla, b.outputs, b.ancilla_ones, cost=cost).circuit
        glob = simplify(b.circuit, b.inputs, b.ancilla, b.outputs, cost=cost, ancilla_ones=b.ancilla_ones).circuit
        v = [circuit_cost(x, cost) for x in (b.circuit, rc, loc, glob)]
        totals = [a + c for a, c in zip(totals, v)]
        count += 1
    report(f"{count} circuits: as given / RC / RC+A / global", totals[2] <= totals[1],
           " / ".join(str(x) for x in totals))
    print()


def resources(d, c):
    used = set(d.inputs.values())
    for g in c:
        used |= g.lines
    garbage = 0 if d.style == "clean" else len(used) - (d.bits + 1)
    return dict(cost=circuit_cost(c), T=t_count(c), tdepth=toffoli_depth(c), depth=depth(c),
                anc=used_ancilla(d, c), lines=len(used), garbage=garbage, gates=len(c))


def part_e() -> None:
    print("E. Hybrid carry look-ahead adder (Peres PGA blocks + prefix carries, garbage style)")
    ok = all(prove_adder(hybrid_cla(n)) and random_test(hybrid_cla(n)) == 0
             for n in (2, 3, 4, 5, 6, 7, 8, 12, 16, 32))
    report("proved correct for every input, n = 2-8, 12, 16, 32", ok)
    print(f"  {'Bits':>5}{'Lines':>7}{'Gates':>7}{'Cost':>7}{'T-count':>9}{'Ancilla':>9}{'Garbage':>9}"
          f"{'Depth':>7}{'Toffoli depth':>15}")
    for n in WIDTHS:
        d = hybrid_cla(n)
        r = resources(d, d.circuit)
        print(f"  {n:>5}{r['lines']:>7}{r['gates']:>7}{r['cost']:>7}{r['T']:>9}{r['anc']:>9}{r['garbage']:>9}"
              f"{r['depth']:>7}{r['tdepth']:>15}")
    unchanged = all(circuit_cost(simplify(hybrid_cla(n).circuit, list(hybrid_cla(n).inputs.values()),
                                          hybrid_cla(n).ancilla, hybrid_cla(n).required).circuit)
                    == circuit_cost(hybrid_cla(n).circuit) for n in WIDTHS)
    report("no rule or simplification step changes it", unchanged)
    print()
    print("  All designs after all steps. P = Pareto-optimal in (cost, Toffoli depth, ancilla);")
    print("  P+ = Pareto-optimal when T-count and garbage outputs are added.")
    designs = dict(DESIGNS)
    designs["hybrid"] = hybrid_cla
    for n in WIDTHS:
        rows = []
        for key, make in designs.items():
            d = make(n)
            s = simplify(d.circuit, list(d.inputs.values()), d.ancilla, d.required).circuit
            rows.append((key, resources(d, s)))

        def pareto(r, keys):
            return not any(all(o[k] <= r[k] for k in keys) and any(o[k] < r[k] for k in keys)
                           for _, o in rows if o is not r)
        print(f"  n = {n}")
        print(f"    {'Design':<13}{'Cost':>6}{'T-count':>9}{'Tof. depth':>12}{'Ancilla':>9}{'Garbage':>9}   Pareto")
        for key, r in rows:
            mark = ("P" if pareto(r, ("cost", "tdepth", "anc")) else "-") + \
                   (" P+" if pareto(r, ("cost", "T", "tdepth", "anc", "garbage")) else "")
            print(f"    {key:<13}{r['cost']:>6}{r['T']:>9}{r['tdepth']:>12}{r['anc']:>9}{r['garbage']:>9}   {mark}")
    print()


def main() -> int:
    start = time.time()
    print("Phase 11: ancilla and garbage rules, hybrid adder\n")
    part_a()
    part_b()
    part_c()
    part_d()
    part_e()
    print(f"Time: {time.time() - start:.1f} s")
    print("\nAll checks passed." if failures == 0 else f"\n{failures} check(s) FAILED.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
