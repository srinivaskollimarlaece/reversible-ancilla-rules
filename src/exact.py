"""Exact minimum circuits for small reversible functions (Phase 3).

For n lines there are (2^n)! reversible functions. For n = 3 that is 40320,
few enough to search completely. The search uses every mixed-polarity
multiple-control Toffoli gate on n lines as its library (27 gates for n = 3).

    minimum gate count    breadth-first search
    minimum quantum cost  Dijkstra's algorithm with the project cost model

The tables give the true optimum for every 3-line function, so the
heuristic optimizer can be measured against it.
"""
from __future__ import annotations

import heapq
from typing import Callable, Dict, List, Optional, Tuple

from revcircuit import Circuit, Gate, all_gates
from optimizer import quantum_cost

Perm = Tuple[int, ...]


class ExactTable:
    """Minimum gate count and minimum quantum cost of every n-line function."""

    def __init__(self, n: int = 3, cost: Callable[[Gate], int] = quantum_cost) -> None:
        if n > 3:
            raise ValueError("complete search is practical only for n <= 3")
        self.n = n
        self.gates: List[Gate] = all_gates(n)
        size = 1 << n
        self._acts = [tuple(g.apply(s) for s in range(size)) for g in self.gates]
        self._costs = [cost(g) for g in self.gates]
        self._identity: Perm = tuple(range(size))
        self.min_gates, self._gate_parent = self._breadth_first()
        self.min_cost, self._cost_parent = self._dijkstra()

    def _breadth_first(self):
        dist: Dict[Perm, int] = {self._identity: 0}
        parent: Dict[Perm, Optional[Tuple[Perm, int]]] = {self._identity: None}
        frontier = [self._identity]
        while frontier:
            nxt = []
            for p in frontier:
                d = dist[p] + 1
                for gi, act in enumerate(self._acts):
                    q = tuple([act[x] for x in p])        # circuit p, then gate gi
                    if q not in dist:
                        dist[q] = d
                        parent[q] = (p, gi)
                        nxt.append(q)
            frontier = nxt
        return dist, parent

    def _dijkstra(self):
        dist: Dict[Perm, int] = {self._identity: 0}
        parent: Dict[Perm, Optional[Tuple[Perm, int]]] = {self._identity: None}
        done = set()
        heap = [(0, self._identity)]
        while heap:
            d, p = heapq.heappop(heap)
            if p in done:
                continue
            done.add(p)
            for gi, act in enumerate(self._acts):
                q = tuple([act[x] for x in p])
                nd = d + self._costs[gi]
                if nd < dist.get(q, 1 << 60):
                    dist[q] = nd
                    parent[q] = (p, gi)
                    heapq.heappush(heap, (nd, q))
        return dist, parent

    def _rebuild(self, perm: Perm, parent) -> Circuit:
        gates = []
        while parent[perm] is not None:
            perm, gi = parent[perm]
            gates.append(self.gates[gi])
        return Circuit(self.n, gates[::-1])

    def min_gate_circuit(self, perm) -> Circuit:
        """A circuit with the fewest gates for the function perm."""
        return self._rebuild(tuple(perm), self._gate_parent)

    def min_cost_circuit(self, perm) -> Circuit:
        """A circuit with the lowest quantum cost for the function perm."""
        return self._rebuild(tuple(perm), self._cost_parent)
