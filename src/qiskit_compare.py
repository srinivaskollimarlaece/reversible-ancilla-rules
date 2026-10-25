"""Comparison with Qiskit (Phase 8).

Two Qiskit optimizations are run on the same circuits as this project's own
tools, and the results are converted back and priced with the same cost model.

  qiskit_cancel   InverseCancellation and CommutativeInverseCancellation,
                  repeated until the circuit stops shrinking. These keep the
                  full function, like the rule-based optimizer of Phase 3.
  qiskit_hoare    HoareOptimizer, which removes gates and controls that are
                  trivial given that ancilla qubits start in |0>. It is the
                  counterpart of the "constants" step of Phase 5. Qiskit has
                  no notion of garbage outputs.

For HoareOptimizer a Hadamard gate is placed on every primary input, so that
Qiskit treats those qubits as unknown, and removed again afterwards.

Negative controls are passed to Qiskit as a positive control between two X
gates. Where that pattern is still present afterwards it is folded back
(Rule 8), so an untouched circuit returns with its original cost.

Needs:  pip install qiskit z3-solver
"""
from __future__ import annotations

from typing import List, Sequence

from revcircuit import Circuit, G, Gate, X
import rules as R


def to_qiskit(circuit: Circuit):
    from qiskit import QuantumCircuit
    qc = QuantumCircuit(circuit.n)
    for g in circuit:
        for l in sorted(g.neg):
            qc.x(l)
        controls = sorted(g.pos | g.neg)
        if not controls:
            qc.x(g.target)
        elif len(controls) == 1:
            qc.cx(controls[0], g.target)
        elif len(controls) == 2:
            qc.ccx(controls[0], controls[1], g.target)
        else:
            qc.mcx(controls, g.target)
        for l in sorted(g.neg):
            qc.x(l)
    return qc


def from_qiskit(qc, n: int, prepared_ones: Sequence[int] = ()) -> Circuit:
    """Convert back. Hadamard gates (input preparation) are dropped, and so is
    the first X gate on every line in `prepared_ones` (constant-1 preparation)."""
    gates: List[Gate] = []
    for inst in qc.data:
        op = inst.operation
        lines = [qc.find_bit(q).index for q in inst.qubits]
        base = getattr(op, "base_gate", None)
        if op.name == "x":
            gates.append(X(lines[0]))
        elif op.name in ("cx", "ccx") or (base is not None and base.name == "x"):
            state = getattr(op, "ctrl_state", (1 << (len(lines) - 1)) - 1)
            pos = [l for k, l in enumerate(lines[:-1]) if (state >> k) & 1]
            neg = [l for k, l in enumerate(lines[:-1]) if not (state >> k) & 1]
            gates.append(G(pos, neg, lines[-1]))
        elif op.name == "h":
            continue
        else:
            raise ValueError(f"unexpected gate from Qiskit: {op.name}")
    for line in prepared_ones:
        first = next(k for k, g in enumerate(gates) if line in g.lines)
        if gates[first] != X(line):
            raise ValueError("the preparation gate of a constant-1 line was changed")
        del gates[first]
    return fold_negative(Circuit(n, gates))


def fold_negative(circuit: Circuit) -> Circuit:
    """Fold X..X gate X..X back into one gate with negative controls (Rule 8)."""
    i = 0
    while i < len(circuit):
        folded = R.rule8_collapse(circuit, i)
        if folded is not None:
            circuit = folded
        else:
            i += 1
    return circuit


def qiskit_cancel(circuit: Circuit) -> Circuit:
    """Qiskit's cancellation passes, repeated to a fixed point."""
    from qiskit.circuit.library import CCXGate, CXGate, XGate
    from qiskit.transpiler import PassManager
    from qiskit.transpiler.passes import CommutativeInverseCancellation, InverseCancellation
    pm = PassManager([InverseCancellation([XGate(), CXGate(), CCXGate()]),
                      CommutativeInverseCancellation()])
    qc = to_qiskit(circuit)
    while True:
        new = pm.run(qc)
        if new.size() >= qc.size():
            break
        qc = new
    return from_qiskit(qc, circuit.n)


def qiskit_hoare(circuit: Circuit, inputs: Sequence[int], ancilla_ones: Sequence[int] = (),
                 cancel: bool = True, size: int = 10) -> Circuit:
    """Qiskit's HoareOptimizer with constant ancilla qubits and unknown inputs.

    With cancel=True the two cancellation passes run as well, and the three
    passes repeat until the circuit stops shrinking.
    """
    from qiskit import QuantumCircuit
    from qiskit.circuit.library import CCXGate, CXGate, XGate
    from qiskit.transpiler import PassManager
    from qiskit.transpiler.passes import (CommutativeInverseCancellation, HoareOptimizer,
                                          InverseCancellation)
    passes = [HoareOptimizer(size=size)]
    if cancel:
        passes += [InverseCancellation([XGate(), CXGate(), CCXGate()]),
                   CommutativeInverseCancellation()]
    pm = PassManager(passes)
    qc = QuantumCircuit(circuit.n)
    for l in inputs:
        qc.h(l)
    for l in ancilla_ones:
        qc.x(l)                                   # prepare the constant 1
    qc = qc.compose(to_qiskit(circuit))
    while True:
        new = pm.run(qc)
        if new.size() >= qc.size():
            break
        qc = new
    return from_qiskit(qc, circuit.n, ancilla_ones)
