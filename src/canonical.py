"""Canonical form of a reversible circuit (Phase 2).

Implements Section IV-A of Feng and Li, "A Complete Set of Transformation
Rules for Reversible Circuits", IEEE TCAD, 2026:

  * a Hamiltonian path H = (a_0, ..., a_{2^n - 1}) of the n-hypercube,
  * the gate set Delta_H = {M_0, ..., M_{2^n - 2}}, where the n-bit gate M_i
    exchanges the neighbouring strings a_i and a_{i+1},
  * Definition 1 (canonical form) and Fact 1,
  * Algorithm 1, which builds the canonical circuit of a reversible function.

Strings follow the paper: the string "s0 s1 ... s(n-1)" gives line q_i the
value s_i. Inside the program a state is an integer whose bit i is s_i, the
same convention as revcircuit.py.

Circuits are written left to right in execution order, as in the paper. The
canonical circuit C = C_m ... C_1 C_0 therefore runs block C_m first.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import factorial
from typing import Dict, List, Optional, Sequence, Tuple

from revcircuit import Circuit, G, Gate


# ---------------------------------------------------------------------------
# Strings and Hamiltonian paths
# ---------------------------------------------------------------------------
def state_of(bits: str) -> int:
    """Convert a paper-style string, e.g. "010" (q0=0, q1=1, q2=0), to a state."""
    return sum(1 << i for i, ch in enumerate(bits) if ch == "1")


def bits_of(state: int, n: int) -> str:
    """Convert a state back to a paper-style string of length n."""
    return "".join(str((state >> i) & 1) for i in range(n))


def gray_path(n: int) -> List[int]:
    """Reflected Gray code as a Hamiltonian path of the n-hypercube.

    For n = 3 this is the path of Example 4 in the paper:
    000, 001, 011, 010, 110, 111, 101, 100.
    """
    return [state_of(format(k ^ (k >> 1), f"0{n}b")) for k in range(1 << n)]


def is_hamiltonian_path(n: int, path: Sequence[int]) -> bool:
    """True when `path` visits every n-bit state once and each step flips one bit."""
    if sorted(path) != list(range(1 << n)):
        return False
    return all(bin(a ^ b).count("1") == 1 for a, b in zip(path, path[1:]))


def _resolve_path(n: int, path: Optional[Sequence[int]]) -> List[int]:
    if path is None:
        return gray_path(n)
    path = list(path)
    if not is_hamiltonian_path(n, path):
        raise ValueError("path is not a Hamiltonian path of the n-hypercube")
    return path


# ---------------------------------------------------------------------------
# The gate set Delta_H
# ---------------------------------------------------------------------------
def exchange_gate(a: int, b: int, n: int) -> Gate:
    """The n-bit gate that exchanges states a and b, which differ in one bit.

    Every other line is a control: positive where a and b hold 1, negative
    where they hold 0. All other states are left unchanged.
    """
    diff = a ^ b
    if diff == 0 or diff & (diff - 1):
        raise ValueError("the two states must differ in exactly one bit")
    target = diff.bit_length() - 1
    pos = [l for l in range(n) if l != target and (a >> l) & 1]
    neg = [l for l in range(n) if l != target and not (a >> l) & 1]
    return G(pos, neg, target)


def delta_gates(n: int, path: Optional[Sequence[int]] = None) -> List[Gate]:
    """Delta_H = [M_0, ..., M_{2^n - 2}] for the given path (Gray code by default)."""
    path = _resolve_path(n, path)
    return [exchange_gate(path[i], path[i + 1], n) for i in range(len(path) - 1)]


def circuit_from_indices(n: int, indices: Sequence[int],
                         path: Optional[Sequence[int]] = None) -> Circuit:
    """The circuit M_i1 M_i2 ... for a list of gate indices."""
    delta = delta_gates(n, path)
    return Circuit(n, [delta[i] for i in indices])


def indices_of_circuit(circuit: Circuit, path: Optional[Sequence[int]] = None) -> List[int]:
    """Indices of a circuit whose gates all belong to Delta_H."""
    lookup: Dict[Gate, int] = {g: i for i, g in enumerate(delta_gates(circuit.n, path))}
    try:
        return [lookup[g] for g in circuit]
    except KeyError as err:
        raise ValueError(f"gate {err.args[0]} is not in Delta_H") from None


# ---------------------------------------------------------------------------
# Definition 1 and Fact 1
# ---------------------------------------------------------------------------
def split_blocks(indices: Sequence[int]) -> List[List[int]]:
    """Cut an index list into maximal runs i, i+1, i+2, ... (execution order)."""
    blocks: List[List[int]] = []
    for i in indices:
        if blocks and blocks[-1][-1] + 1 == i:
            blocks[-1].append(i)
        else:
            blocks.append([i])
    return blocks


def is_canonical(indices: Sequence[int], n: int) -> bool:
    """Definition 1: blocks of consecutive gates whose first indices decrease.

    In execution order the circuit is C_m ... C_1 C_0, and the first index of
    C_i must be smaller than the first index of C_j whenever i < j.
    """
    if any(not 0 <= i <= (1 << n) - 2 for i in indices):
        return False
    starts = [block[0] for block in split_blocks(indices)]
    return all(later < earlier for earlier, later in zip(starts, starts[1:]))


def fact1_holds(indices: Sequence[int], n: int) -> bool:
    """Fact 1: at most 2^n - 1 blocks, and M_i occurs at most i + 1 times."""
    if len(split_blocks(indices)) > (1 << n) - 1:
        return False
    return all(indices.count(i) <= i + 1 for i in set(indices))


def count_canonical_forms(n: int) -> int:
    """Number of index lists that satisfy Definition 1.

    For each first index x there is either no block or a block of length
    1 .. 2^n - 1 - x, giving 2^n - x choices. The product is (2^n)!, the
    number of n-bit reversible functions.
    """
    total = 1
    for x in range((1 << n) - 1):
        total *= (1 << n) - x
    assert total == factorial(1 << n)
    return total


def max_canonical_gates(n: int) -> int:
    """Largest possible canonical circuit: every block has full length."""
    size = 1 << n
    return size * (size - 1) // 2


# ---------------------------------------------------------------------------
# Algorithm 1
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CanonicalForm:
    """Canonical circuit of a reversible function, based on a Hamiltonian path."""

    n: int
    path: Tuple[int, ...]
    blocks: Tuple[Tuple[int, ...], ...]      # execution order: C_m, ..., C_1, C_0

    @property
    def indices(self) -> List[int]:
        """Gate indices in execution order."""
        return [i for block in self.blocks for i in block]

    @property
    def circuit(self) -> Circuit:
        return circuit_from_indices(self.n, self.indices, self.path)

    def __len__(self) -> int:
        return sum(len(block) for block in self.blocks)

    def __str__(self) -> str:
        if not self.blocks:
            return "(empty)"
        return " | ".join(" ".join(f"M{i}" for i in block) for block in self.blocks)


def canonical_blocks(n: int, perm: Sequence[int], path: Sequence[int]) -> List[List[int]]:
    """Algorithm 1 on index lists. Returns the blocks in execution order.

    perm[s] is the output state for input state s. The target arrangement is
    (f(a_0), f(a_1), ...). Position i is filled by moving the wanted string
    from its position l down to i with the gates M_i M_{i+1} ... M_{l-1}.
    """
    size = 1 << n
    if sorted(perm) != list(range(size)):
        raise ValueError("perm is not a permutation of the n-bit states")
    current = list(path)
    built: List[List[int]] = []              # construction order: C_0, C_1, ...
    for i in range(size):
        wanted = perm[path[i]]
        l = current.index(wanted, i)
        if l > i:
            built.append(list(range(i, l)))
            current.insert(i, current.pop(l))
    assert current == [perm[a] for a in path]
    return built[::-1]


def canonical_from_function(n: int, perm: Sequence[int],
                            path: Optional[Sequence[int]] = None) -> CanonicalForm:
    """Canonical circuit of the reversible function perm (Algorithm 1)."""
    path = _resolve_path(n, path)
    blocks = canonical_blocks(n, perm, path)
    return CanonicalForm(n, tuple(path), tuple(tuple(b) for b in blocks))


def canonical_form(circuit: Circuit, path: Optional[Sequence[int]] = None) -> CanonicalForm:
    """Canonical form of a circuit: simulate it, then apply Algorithm 1."""
    return canonical_from_function(circuit.n, circuit.permutation(), path)


def function_from_table(n: int, table: Dict[str, str]) -> List[int]:
    """Build perm from a truth table written with paper-style strings."""
    perm = [0] * (1 << n)
    for inp, out in table.items():
        perm[state_of(inp)] = state_of(out)
    if len(table) != 1 << n or sorted(perm) != list(range(1 << n)):
        raise ValueError("the table is not a complete reversible truth table")
    return perm
