"""A small binary decision diagram (BDD) package (Phase 8).

simplify.py needs to compare Boolean functions of the primary inputs
exactly. For a 4-bit adder it lists all 512 input combinations, but a 32-bit
adder has 2^65 of them. A reduced ordered BDD represents a function as a
graph in which equal functions share one node, so two functions are equal
exactly when their node numbers are equal. For adders the graphs stay small
when the variable order interleaves the operand bits: c0, a0, b0, a1, b1, ...

Only what the project needs is implemented: AND, XOR, NOT, constants and
variables. `Fn` wraps a node so that the operators &, ^, ~ and == work, which
lets the same simplification code run on integers or on BDDs.
"""
from __future__ import annotations

import sys
from typing import Dict, List, Tuple

sys.setrecursionlimit(max(sys.getrecursionlimit(), 20000))


class BDD:
    """Reduced ordered BDD over variables 0 .. nvars-1 (0 is the top variable)."""

    def __init__(self, nvars: int) -> None:
        self.nvars = nvars
        self.level: List[int] = [nvars, nvars]       # nodes 0 (false) and 1 (true)
        self.low: List[int] = [0, 1]
        self.high: List[int] = [0, 1]
        self._unique: Dict[Tuple[int, int, int], int] = {}
        self._and: Dict[Tuple[int, int], int] = {}
        self._xor: Dict[Tuple[int, int], int] = {}

    def _node(self, level: int, low: int, high: int) -> int:
        if low == high:
            return low
        key = (level, low, high)
        node = self._unique.get(key)
        if node is None:
            node = len(self.level)
            self.level.append(level)
            self.low.append(low)
            self.high.append(high)
            self._unique[key] = node
        return node

    def var(self, i: int) -> int:
        return self._node(i, 0, 1)

    def _split(self, u: int, level: int) -> Tuple[int, int]:
        if self.level[u] == level:
            return self.low[u], self.high[u]
        return u, u

    def AND(self, u: int, v: int) -> int:
        if u == 0 or v == 0:
            return 0
        if u == 1:
            return v
        if v == 1 or u == v:
            return u
        key = (u, v) if u < v else (v, u)
        r = self._and.get(key)
        if r is None:
            level = min(self.level[u], self.level[v])
            u0, u1 = self._split(u, level)
            v0, v1 = self._split(v, level)
            r = self._node(level, self.AND(u0, v0), self.AND(u1, v1))
            self._and[key] = r
        return r

    def XOR(self, u: int, v: int) -> int:
        if u == v:
            return 0
        if u == 0:
            return v
        if v == 0:
            return u
        key = (u, v) if u < v else (v, u)
        r = self._xor.get(key)
        if r is None:
            level = min(self.level[u], self.level[v])
            u0, u1 = self._split(u, level)
            v0, v1 = self._split(v, level)
            r = self._node(level, self.XOR(u0, v0), self.XOR(u1, v1))
            self._xor[key] = r
        return r

    def NOT(self, u: int) -> int:
        return self.XOR(u, 1)

    def evaluate(self, u: int, assignment) -> int:
        """Value of the function for a list of 0/1 values, one per variable."""
        while u > 1:
            u = self.high[u] if assignment[self.level[u]] else self.low[u]
        return u

    def size(self) -> int:
        return len(self.level)


class Fn:
    """A Boolean function held as a BDD node, with operator syntax."""

    __slots__ = ("bdd", "node")

    def __init__(self, bdd: BDD, node: int) -> None:
        self.bdd, self.node = bdd, node

    def __and__(self, other: "Fn") -> "Fn":
        return Fn(self.bdd, self.bdd.AND(self.node, other.node))

    def __xor__(self, other: "Fn") -> "Fn":
        return Fn(self.bdd, self.bdd.XOR(self.node, other.node))

    def __invert__(self) -> "Fn":
        return Fn(self.bdd, self.bdd.NOT(self.node))

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Fn) and self.node == other.node

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        return hash(self.node)

    def __repr__(self) -> str:
        return f"Fn({self.node})"
