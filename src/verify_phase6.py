"""Phase 6 verification: Verilog for the reversible adders.

  A. The four Verilog files are generated.
  B. Each adder module contains exactly the gates of its Python design.
  C. Gate library testbench: every gate on every input, against the Python model.
  D. Adder testbench: all 512 input combinations for the five adder modules.
  E. Control experiment: a deliberately broken adder makes the testbench fail.

Parts C to E need the Icarus Verilog simulator (the command `iverilog`).
In Google Colab:  !apt-get -qq install -y iverilog

Run:  python verify_phase6.py
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import time
from collections import Counter

from revcircuit import Circuit
import verilog
from verilog import (adder_module, blocks_from_circuit, build_designs,
                     instance_counts, simulate, write_files)

FOLDER = "verilog"
MODULE_OF = {"NOT": "rev_not", "Feynman": "feynman_gate", "Toffoli": "toffoli_gate",
             "Peres": "peres_gate", "TSG": "tsg_gate", "R2": "r2_gate"}
failures = 0
skipped = False


def report(label: str, ok: bool, detail: str = "") -> None:
    global failures
    failures += not ok
    print(f"  {label:<46}{'PASS' if ok else 'FAIL'}" + (f"  {detail}" if detail else ""))


def part_a() -> dict:
    print("A. Files")
    paths = write_files(FOLDER)
    for name, path in paths.items():
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().count("\n")
        report(f"{path}", lines > 0, f"{lines} lines")
    print()
    return paths


def part_b(paths: dict) -> None:
    print("B. Gate instances in each adder module")
    with open(paths["rev_adders.v"], encoding="utf-8") as handle:
        text = handle.read()
    for name, design, blocks, _ in build_designs():
        expected = Counter(MODULE_OF[kind] for kind, _ in blocks if kind != "MCT")
        found = instance_counts(text, name)
        detail = ", ".join(f"{count} {module}" for module, count in sorted(found.items()))
        report(name, found == expected and sum(found.values()) == len(blocks), detail)
    print()


def part_c_d() -> None:
    global skipped
    print("C. Gate library in the Verilog simulator")
    out = simulate(FOLDER, "tb_rev_gates")
    if out is None:
        skipped = True
        print("  SKIPPED: the command 'iverilog' was not found.")
        print("  In Google Colab run:  !apt-get -qq install -y iverilog\n")
        return
    for line in out.splitlines():
        if "wrong answers" in line or "PASSED" in line or "FAILED" in line or "ERROR" in line:
            print("    " + line)
    report("All gates match the Python model", "ALL GATE TESTS PASSED" in out)
    print()

    print("D. Adders in the Verilog simulator (4 named cases + all 512 combinations)")
    out = simulate(FOLDER, "tb_rev_adders")
    for line in out.splitlines():
        if "wrong answers" in line or "PASSED" in line or "FAILED" in line or "ERROR" in line:
            print("    " + line)
    wrong = [int(x) for x in re.findall(r"wrong answers: (\d+) of 516", out)]
    report("All five adders add correctly", "ALL TESTS PASSED" in out and wrong == [0] * 5)
    print()


def part_e() -> None:
    if skipped:
        return
    print("E. Control experiment: one gate removed from 'cla_simplified'")
    designs = build_designs()
    with tempfile.TemporaryDirectory() as folder:
        write_files(folder)
        parts = ["`timescale 1ns / 1ps", ""]
        for name, design, blocks, note in designs:
            if name == "cla_simplified":
                gates = list(design.circuit.gates)
                del gates[10]                                   # drop one gate on purpose
                blocks = blocks_from_circuit(Circuit(design.n, gates))
            parts.append(adder_module(name, design, blocks, note))
        with open(os.path.join(folder, "rev_adders.v"), "w", encoding="utf-8") as handle:
            handle.write("\n".join(parts))
        out = simulate(folder, "tb_rev_adders")
    wrong = [int(x) for x in re.findall(r"wrong answers: (\d+) of 516", out)]
    caught = (len(wrong) == 5 and wrong[1] > 0 and wrong[0] == wrong[2] == wrong[3] == wrong[4] == 0
              and "TESTS FAILED" in out)
    report("The testbench reports the broken adder", caught,
           f"cla_simplified: {wrong[1] if len(wrong) == 5 else '?'} wrong answers; others: 0")
    print()


def main() -> int:
    start = time.time()
    print("Phase 6 verification: Verilog\n")
    paths = part_a()
    part_b(paths)
    part_c_d()
    part_e()
    print(f"Time: {time.time() - start:.1f} s")
    if failures:
        print(f"\n{failures} check(s) FAILED.")
        return 1
    if skipped:
        print("\nFile checks passed. Simulation was SKIPPED (no Verilog simulator found).")
        return 0
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
