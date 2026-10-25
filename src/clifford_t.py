"""Clifford+T synthesis, ZX-calculus optimization and hardware mapping (Phase 12).

These are compiled-circuit measures, a step closer to an implementation than
the cost model of the paper (quantum cost, T-count 7 per Toffoli, Toffoli
depth). They are still not physical results: no device was run, no noise model
is used, and no error-correction overhead is included.

  clifford_t(c)      every MPMCT gate decomposed into H, T, T^dagger, S, CNOT
                     and X by Qiskit (the standard 7-T Toffoli circuit; a
                     negative control is an X gate on each side).
  t_metrics(qc)      T-count (T and T^dagger gates) and T-depth (the depth of
                     the circuit when only T and T^dagger gates count).
  pyzx_optimize(qc)  PyZX full_reduce, circuit extraction and basic
                     optimization: reduces the T-count while keeping the full
                     unitary, so it cannot use ancilla or garbage lines.
  map_heavy_hex(c)   Qiskit transpile, optimization level 3, onto a heavy-hex
                     coupling map (distance 9, 193 qubits) with basis
                     {CX, RZ, SX, X}: two-qubit gate count and depth after
                     routing.

Needs: pip install qiskit pyzx
"""
from __future__ import annotations

from revcircuit import Circuit
from qiskit_compare import to_qiskit

BASIS = ["h", "t", "tdg", "s", "sdg", "cx", "x", "z"]
T_GATES = ("t", "tdg")


def clifford_t(circuit: Circuit):
    from qiskit import transpile
    return transpile(to_qiskit(circuit), basis_gates=BASIS, optimization_level=0)


def t_metrics(qc) -> dict:
    ops = qc.count_ops()
    return dict(t=ops.get("t", 0) + ops.get("tdg", 0),
                tdepth=qc.depth(filter_function=lambda ins: ins.operation.name in T_GATES),
                cx=ops.get("cx", 0))


def _zx_metrics(circ) -> dict:
    """T-count, T-depth and CNOT count of a PyZX circuit of basic gates."""
    level = [0] * circ.qubits
    t = cx = 0
    for g in circ.gates:
        qs = [q for q in (getattr(g, "target", None), getattr(g, "control", None)) if q is not None]
        phase = getattr(g, "phase", None)
        is_t = phase is not None and getattr(phase, "denominator", 1) == 4
        if g.name in ("CNOT", "CZ"):
            cx += 1
        top = max(level[q] for q in qs) + (1 if is_t else 0)
        for q in qs:
            level[q] = top
        t += is_t
    return dict(t=t, tdepth=max(level) if level else 0, cx=cx)


def pyzx_optimize(qc) -> dict:
    """T-count, T-depth and CNOT count after PyZX optimization."""
    import pyzx as zx
    from qiskit import qasm2
    circ = zx.Circuit.from_qasm(qasm2.dumps(qc))
    g = circ.to_graph()
    zx.full_reduce(g, quiet=True)
    out = zx.extract_circuit(g.copy())
    out = zx.optimize.basic_optimization(out.to_basic_gates())
    m = _zx_metrics(out)
    assert m["t"] == zx.tcount(out)
    return m


def map_heavy_hex(circuit: Circuit, seed: int = 7) -> dict:
    from qiskit import transpile
    from qiskit.transpiler import CouplingMap
    cmap = CouplingMap.from_heavy_hex(9)
    qc = transpile(to_qiskit(circuit), coupling_map=cmap, basis_gates=["cx", "rz", "sx", "x"],
                   optimization_level=3, seed_transpiler=seed)
    ops = qc.count_ops()
    return dict(cx=ops.get("cx", 0), depth=qc.depth(),
                cxdepth=qc.depth(filter_function=lambda ins: ins.operation.num_qubits == 2))
