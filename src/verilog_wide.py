"""Verilog for the adder designs of Phases 8 and 11, for Vivado or any simulator (Phase 10).

For every design (CLA blocks after Kumar et al., TSG ripple-carry, Peres
ripple-carry, Cuccaro, VBE, Draper) and every word length n = 4, 8, 16, 32,
two modules are written: the circuit as built and the circuit after all
simplification steps. Each module is structural, in the style of
rev_adders.v (Phase 6): library gates from rev_gates.v, and a single assign
for a Toffoli-type gate with a negative control, which the library lacks.

Files written into the folder (default "vivado/src" and "vivado/sim"):

  src/rev_adders_wide.v   56 adder modules (48 without hybrid.py)
  sim/tb_wide_4.v         all 512 inputs of the 4-bit modules
  sim/tb_wide_8.v ...     900 test vectors each for 8, 16 and 32 bits:
  sim/tb_wide_16.v        corner cases first, then pseudo-random vectors
  sim/tb_wide_32.v        from a fixed seed

Every testbench finishes before 1000 ns, the default run time of the Vivado
simulator, and prints one line per module and ALL TESTS PASSED at the end.

Ports
  a[n-1:0], b[n-1:0]  operands
  cin                 carry input (garbage-style designs only)
  sum[n-1:0], cout    result
  clean               clean designs only: 1 when every operand line is restored
                      and every ancilla line is back at 0, as the design requires

The decision-diagram proofs of Phase 8 already cover every input; the
simulation is an independent check in a hardware description language.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections import Counter
from typing import Dict, List, Sequence, Tuple

from nadders import DESIGNS, AdderDesign
from simplify import simplify
from verilog import _PORTS, LIBRARY, blocks_from_circuit

WIDTHS = (4, 8, 16, 32)
KEYS = {"cla4_blocks": "cla_blocks", "tsg_rca": "tsg_rca", "peres_rca": "peres_rca",
        "cuccaro": "cuccaro", "vbe": "vbe", "draper_qcla": "draper", "hybrid": "hybrid"}
try:                                       # Phase 11: the hybrid carry look-ahead adder
    from hybrid import hybrid_cla
    DESIGNS = dict(DESIGNS, hybrid=hybrid_cla)
except ImportError:
    del KEYS["hybrid"]
VECTORS = 900                     # test vectors for 8, 16 and 32 bits


def module_text(name: str, design: AdderDesign, blocks, note: str) -> str:
    """One structural Verilog module for an n-bit design given as blocks."""
    n, names = design.bits, design.line_names
    port_of = {}
    for i in range(n):
        port_of[f"a{i}"] = f"a[{i}]"
        port_of[f"b{i}"] = f"b[{i}]"
    if design.carry_in is not None:
        port_of[names[design.carry_in]] = "cin"
    version: Dict[int, int] = {l: 0 for l in range(design.n)}
    wires: List[str] = []
    body: List[str] = []

    def current(line: int) -> str:
        return f"{names[line]}_{version[line]}"

    def advance(line: int) -> str:
        version[line] += 1
        wires.append(current(line))
        return current(line)

    for line in range(design.n):
        wires.append(current(line))
        source = port_of.get(names[line], "1'b0")
        kind = "primary input" if names[line] in port_of else "ancilla, constant 0"
        body.append(f"  assign {current(line)} = {source};".ljust(34) + f"// {kind}")
    body.append("")

    counts: Counter = Counter()
    for index, (kind, lines) in enumerate(blocks, 1):
        counts[kind] += 1
        if kind == "MCT":
            g = lines[0]
            terms = [current(l) for l in sorted(g.pos)] + ["~" + current(l) for l in sorted(g.neg)]
            old = current(g.target)
            body.append(f"  assign {advance(g.target)} = {old} ^ ({' & '.join(terms)});"
                        f"   // gate {index}: Toffoli-type gate with a negative control")
            continue
        module, ins, outs, drives = _PORTS[kind]
        inputs = [f".{port}({current(l)})" for port, l in zip(ins, lines)]
        outputs = [f".{port}({advance(lines[k])})" for port, k in zip(outs, drives)]
        body.append(f"  {module:<13} u{index} ({', '.join(inputs + outputs)});")
    body.append("")

    for i, line in enumerate(design.sum_lines):
        body.append(f"  assign sum[{i}] = {current(line)};")
    body.append(f"  assign cout = {current(design.carry_line)};")
    clean = design.style == "clean"
    if clean:
        terms = []
        for line, src in sorted(design.restored.items()):
            terms.append(f"({current(line)} == {port_of[src]})")
        required = set(design.sum_lines) | {design.carry_line} | set(design.restored)
        for line in design.ancilla:
            if line not in required:
                terms.append(f"~{current(line)}")
        body.append("  assign clean = " + " &\n                 ".join(terms) + ";")

    inventory = ", ".join(f"{counts[k]} {k}" for k in ("Peres", "Feynman", "Toffoli", "NOT",
                                                       "TSG", "R2", "MCT") if counts[k])
    header = [f"// {note}",
              f"// Lines: {design.n}.  Gates: {inventory}.",
              f"module {name} (",
              f"  input  [{n - 1}:0] a,",
              f"  input  [{n - 1}:0] b,"]
    if design.carry_in is not None:
        header.append("  input         cin,")
    header += [f"  output [{n - 1}:0] sum,",
               "  output        cout" + ("," if clean else "")]
    if clean:
        header.append("  output        clean")
    header.append(");")
    decl = ["  wire " + ", ".join(wires[k:k + 8]) + ";" for k in range(0, len(wires), 8)]
    return "\n".join(header + decl + [""] + body + ["endmodule", ""])


def build(widths: Sequence[int] = WIDTHS) -> List[Tuple[str, AdderDesign, int]]:
    """All modules: (module name, design with the circuit to write, width)."""
    out = []
    for key, short in KEYS.items():
        for n in widths:
            design = DESIGNS[key](n)
            built = design.blocks or blocks_from_circuit(design.circuit)
            out.append((f"{short}_{n}_as_built", design, built, n,
                        f"{design.name}, as built."))
            result = simplify(design.circuit, list(design.inputs.values()), design.ancilla,
                              design.required)
            simple = design.with_circuit(result.circuit)
            out.append((f"{short}_{n}_simplified", simple, blocks_from_circuit(result.circuit), n,
                        f"{design.name}, after all simplification steps of this work."))
    return out


def testbench(n: int, modules: Sequence[Tuple[str, AdderDesign]]) -> str:
    """Self-checking testbench for all modules of one word length."""
    exhaustive = n == 4
    total = 512 if exhaustive else VECTORS
    t = [f"// Self-checking testbench for the {n}-bit adder modules.",
         ("// All 512 input combinations, one every 1 ns." if exhaustive else
          f"// {VECTORS} vectors, one every 1 ns: corner cases, then pseudo-random values (fixed seed)."),
         "// The run ends before 1000 ns, the default run time of the Vivado simulator.",
         "`timescale 1ns / 1ps",
         "",
         f"module tb_wide_{n};",
         f"  reg  [{n - 1}:0] a, b;",
         "  reg         cin;",
         f"  reg  [{n}:0] with_cin, without_cin;",
         "  integer     i, total, seed;"]
    for k, (name, d) in enumerate(modules, 1):
        t.append(f"  wire [{n - 1}:0] s{k};  wire c{k};" + (f"  wire ok{k};" if d.style == "clean" else ""))
        t.append(f"  integer     e{k};")
    t.append("")
    for k, (name, d) in enumerate(modules, 1):
        ports = ".a(a), .b(b), " + (".cin(cin), " if d.carry_in is not None else "")
        ports += f".sum(s{k}), .cout(c{k})" + (f", .clean(ok{k})" if d.style == "clean" else "")
        t.append(f"  {name} dut{k} ({ports});")
    t += ["",
          "  task check;",
          "    begin",
          "      with_cin    = a + b + cin;",
          "      without_cin = a + b;"]
    for k, (name, d) in enumerate(modules, 1):
        want = "with_cin" if d.carry_in is not None else "without_cin"
        cond = f"{{c{k}, s{k}}} !== {want}" + (f" || ok{k} !== 1'b1" if d.style == "clean" else "")
        t.append(f"      if ({cond}) e{k} = e{k} + 1;")
    t += ["    end", "  endtask", "", "  initial begin"]
    t += [f"    e{k} = 0;" for k in range(1, len(modules) + 1)]
    if exhaustive:
        t += ["    for (i = 0; i < 512; i = i + 1) begin",
              "      {a, b, cin} = i[8:0];",
              "      #1; check;",
              "    end"]
    else:
        ones = f"{{{n}{{1'b1}}}}"
        alt = "{" + str(n // 2) + "{2'b10}}"
        corners = [("0", "0", "0"), (ones, "1", "0"), (ones, ones, "1"), (ones, ones, "0"),
                   (alt, f"~{alt}", "1"), (alt, alt, "0"), ("1", ones, "0"), ("0", ones, "1")]
        for x, y, c in corners:
            t.append(f"    a = {x}; b = {y}; cin = {c}; #1; check;")
        t += ["    seed = 2026;",
              f"    for (i = {len(corners)}; i < {VECTORS}; i = i + 1) begin",
              "      a = $random(seed); b = $random(seed); cin = $random(seed);",
              "      #1; check;",
              "    end"]
    t += ["", "    total = 0;"]
    for k, (name, d) in enumerate(modules, 1):
        t.append(f'    $display("{name:<26} wrong answers: %0d of {total}", e{k});')
        t.append(f"    total = total + e{k};")
    t += ['    if (total == 0) $display("ALL TESTS PASSED");',
          '    else            $display("TESTS FAILED: %0d wrong answers", total);',
          "    $finish;",
          "  end",
          "endmodule",
          ""]
    return "\n".join(t)


def write_files(folder: str = "vivado", widths: Sequence[int] = WIDTHS) -> Dict[str, str]:
    src, sim = os.path.join(folder, "src"), os.path.join(folder, "sim")
    os.makedirs(src, exist_ok=True)
    os.makedirs(sim, exist_ok=True)
    modules = build(widths)
    text = ["// Reversible adders of Phase 8 at 4 to 32 bits, as built and simplified.",
            "// Built from the gates in rev_gates.v. Generated by verilog_wide.py; do not edit by hand.",
            "`timescale 1ns / 1ps", ""]
    text += [module_text(name, d, blocks, note) for name, d, blocks, n, note in modules]
    paths = {"rev_gates.v": os.path.join(src, "rev_gates.v"),
             "rev_adders_wide.v": os.path.join(src, "rev_adders_wide.v")}
    with open(paths["rev_gates.v"], "w", encoding="utf-8") as f:
        f.write(LIBRARY)
    with open(paths["rev_adders_wide.v"], "w", encoding="utf-8") as f:
        f.write("\n".join(text))
    for n in widths:
        name = f"tb_wide_{n}.v"
        paths[name] = os.path.join(sim, name)
        with open(paths[name], "w", encoding="utf-8") as f:
            f.write(testbench(n, [(m, d) for m, d, _, w, _ in modules if w == n]))
    return paths


def simulate(folder: str = "vivado", n: int = 4):
    """Run one testbench with Icarus Verilog. None when iverilog is missing."""
    if shutil.which("iverilog") is None or shutil.which("vvp") is None:
        return None
    files = [os.path.join(folder, "src", "rev_gates.v"), os.path.join(folder, "src", "rev_adders_wide.v"),
             os.path.join(folder, "sim", f"tb_wide_{n}.v")]
    with tempfile.TemporaryDirectory() as scratch:
        binary = os.path.join(scratch, "tb.vvp")
        compiled = subprocess.run(["iverilog", "-g2001", "-s", f"tb_wide_{n}", "-o", binary] + files,
                                  capture_output=True, text=True)
        if compiled.returncode != 0:
            return "COMPILE ERROR\n" + compiled.stdout + compiled.stderr
        run = subprocess.run(["vvp", "-n", binary], capture_output=True, text=True)
    return (compiled.stdout + compiled.stderr + run.stdout + run.stderr).strip()


if __name__ == "__main__":
    write_files()
    for n in WIDTHS:
        print(simulate(n=n) or "Icarus Verilog not found: files written, not simulated.")
        print()
