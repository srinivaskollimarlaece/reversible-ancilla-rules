"""Phase 12: stronger tool comparison and compiled-circuit measures.

Run:  python verify_phase12.py            (parts B to D, about 20 minutes)
      python verify_phase12.py templates  (part A as well, 4- and 8-bit designs; about 40 more minutes)

  A. Template matching with the NCT templates of Maslov et al., as implemented
     in Qiskit's TemplateOptimization pass (pattern matching of Iten et al.).
  B. Clifford+T: every design decomposed into H, T, S, CNOT and X, then
     optimized with PyZX. T-count and T-depth as compiled, beside the
     estimates used in the paper (7 T per Toffoli gate, Toffoli depth).
  C. PyZX results checked against the original circuits on random inputs
     (state vectors, designs of at most 16 lines).
  D. Mapping onto a heavy-hex coupling map: two-qubit gate count and depth
     after routing.

Needs: pip install qiskit pyzx sympy
"""
from __future__ import annotations

import json
import random
import sys
import time

from nadders import DESIGNS, t_count, toffoli_depth
from hybrid import hybrid_cla
from simplify import simplify
from arules import ancilla_optimize
from optimizer import circuit_cost, optimize
from clifford_t import clifford_t, t_metrics, pyzx_optimize, map_heavy_hex

ALL = dict(DESIGNS, hybrid=hybrid_cla)
WIDTHS = (4, 8, 16, 32)


def versions(d):
    args = (d.circuit, list(d.inputs.values()), d.ancilla, d.required)
    return {"built": d.circuit, "local": ancilla_optimize(*args).circuit, "global": simplify(*args).circuit}


def part_a(widths=(4, 8)):
    import qiskit.circuit.library.templates.nct as nct
    from qiskit.transpiler import PassManager
    from qiskit.transpiler.passes import TemplateOptimization
    from qiskit_compare import from_qiskit, to_qiskit
    templates = [getattr(nct, n)() for n in dir(nct) if n.startswith("template_nct")]
    print(f"A. NCT template matching ({len(templates)} templates), quantum cost")
    print(f"  {'Design':<13}{'Bits':>5}{'Built':>7}{'Templates':>11}{'RC':>6}{'RC+A':>6}{'Time (s)':>10}")
    for key, make in ALL.items():
        for n in widths:
            d = make(n)
            t = time.time()
            pm = PassManager([TemplateOptimization(template_list=templates, heuristics_qubits_param=[1],
                                                   heuristics_backward_param=[3, 1])])
            tm = from_qiskit(pm.run(to_qiskit(d.circuit)), d.circuit.n)
            elapsed = time.time() - t
            rc = optimize(d.circuit).circuit
            loc = versions(d)["local"]
            print(f"  {key:<13}{n:>5}{circuit_cost(d.circuit):>7}{circuit_cost(tm):>11}"
                  f"{circuit_cost(rc):>6}{circuit_cost(loc):>6}{elapsed:>10.1f}", flush=True)
    print()


def part_b():
    print("B. Clifford+T and PyZX (T-count / T-depth)")
    print(f"  {'Design':<13}{'Bits':>5}{'Version':>8}{'Est. T':>8}{'Tof. depth':>11}"
          f"{'T':>6}{'T-depth':>9}{'PyZX T':>8}{'PyZX T-depth':>14}{'PyZX CX':>9}")
    rows = []
    for n in WIDTHS:
        for key, make in ALL.items():
            d = make(n)
            for label, c in versions(d).items():
                if label == "local":
                    continue
                q = clifford_t(c)
                m, z = t_metrics(q), pyzx_optimize(q)
                assert m["t"] == t_count(c)
                rows.append(dict(design=key, n=n, version=label, est_t=t_count(c), tof_depth=toffoli_depth(c),
                                 t=m["t"], t_depth=m["tdepth"], zx_t=z["t"], zx_t_depth=z["tdepth"], zx_cx=z["cx"]))
                r = rows[-1]
                print(f"  {key:<13}{n:>5}{label:>8}{r['est_t']:>8}{r['tof_depth']:>11}{r['t']:>6}{r['t_depth']:>9}"
                      f"{r['zx_t']:>8}{r['zx_t_depth']:>14}{r['zx_cx']:>9}", flush=True)
    print()
    return rows


def part_c(trials=8):
    import numpy as np
    import pyzx as zx
    from qiskit import QuantumCircuit, qasm2
    from qiskit.quantum_info import Statevector
    print("C. PyZX output against the original circuit (random basis inputs, state vectors)")
    rng = random.Random(3)
    checked = 0
    for key, make in ALL.items():
        d = make(4)
        for label, c in versions(d).items():
            if c.n > 16:
                continue
            q = clifford_t(c)
            circ = zx.Circuit.from_qasm(qasm2.dumps(q))
            g = circ.to_graph()
            zx.full_reduce(g, quiet=True)
            out = zx.optimize.basic_optimization(zx.extract_circuit(g.copy()).to_basic_gates())
            back = QuantumCircuit.from_qasm_str(out.to_qasm())
            for _ in range(trials):
                x = rng.randrange(1 << c.n)
                a = Statevector.from_int(x, 1 << c.n).evolve(q)
                b = Statevector.from_int(x, 1 << c.n).evolve(back)
                overlap = abs(np.vdot(a.data, b.data))
                assert overlap > 1 - 1e-9, (key, label, x, overlap)
            checked += 1
    print(f"  {checked} circuits, {trials} random inputs each: identical state vectors\n")


def part_d(widths=(8, 32)):
    print("D. Heavy-hex mapping (Qiskit, optimization level 3, 193-qubit heavy-hex map)")
    print(f"  {'Design':<13}{'Bits':>5}{'Lines':>7}{'CX':>8}{'CX depth':>10}{'Depth':>8}")
    rows = []
    for n in widths:
        for key, make in ALL.items():
            d = make(n)
            c = versions(d)["global"]
            m = map_heavy_hex(c)
            rows.append(dict(design=key, n=n, **m))
            print(f"  {key:<13}{n:>5}{c.n:>7}{m['cx']:>8}{m['cxdepth']:>10}{m['depth']:>8}", flush=True)
    print()
    return rows


if __name__ == "__main__":
    start = time.time()
    print("Phase 12: tool comparison and compiled-circuit measures\n")
    if "templates" in sys.argv:
        part_a()
    rows_b = part_b()
    part_c()
    rows_d = part_d()
    with open("phase12_results.json", "w") as f:
        json.dump(dict(clifford_t=rows_b, mapping=rows_d), f, indent=1)
    print(f"Time: {time.time() - start:.1f} s\n\nAll checks passed.")
