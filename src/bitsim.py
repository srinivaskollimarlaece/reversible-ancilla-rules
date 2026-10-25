"""Bit-parallel simulation of reversible circuits (Phase 4).

revcircuit.py simulates one input at a time, which is too slow for a
24-line adder (16.7 million inputs). Here every line holds one large
integer whose bit s is the value of that line for input state s, so a gate
is applied to all 2^n inputs at once with a few integer operations.

This makes an exhaustive equivalence check practical up to about 26 lines.
"""
from __future__ import annotations

from typing import List

from revcircuit import Circuit


def input_vectors(n: int) -> List[int]:
    """vectors[i] has bit s equal to bit i of s, for s = 0 .. 2^n - 1."""
    size = 1 << n
    vectors = []
    for i in range(n):
        half = 1 << i
        v = ((1 << half) - 1) << half            # 'half' zeros, then 'half' ones
        length = 2 * half
        while length < size:                     # repeat the pattern to full length
            v |= v << length
            length *= 2
        vectors.append(v)
    return vectors


def output_vectors(circuit: Circuit) -> List[int]:
    """Truth vector of every output line over all 2^n inputs."""
    n = circuit.n
    mask = (1 << (1 << n)) - 1
    lines = input_vectors(n)
    for g in circuit:
        active = mask
        for l in g.pos:
            active &= lines[l]
        for l in g.neg:
            active &= ~lines[l]
        lines[g.target] ^= active & mask
    return lines


def equivalent_all_inputs(a: Circuit, b: Circuit) -> bool:
    """True when the two circuits agree on every line for every one of the 2^n inputs."""
    return a.n == b.n and output_vectors(a) == output_vectors(b)
