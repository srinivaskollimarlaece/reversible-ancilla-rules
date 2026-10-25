"""Verilog for the reversible adders (Phase 6).

Four text files are produced:

  rev_gates.v       the reversible gate library: NOT, Feynman, Toffoli,
                    Peres, TSG and R2, each with as many outputs as inputs
  rev_adders.v      one module per adder, built only from library gates
  tb_rev_adders.v   a self-checking testbench for the adders: a few named
                    cases for the waveform, then all 512 input combinations
  tb_rev_gates.v    a self-checking testbench for the gate library

The adder modules are structural. Every gate instance takes the current
wire of each of its lines and drives a new wire, so the netlist reads in the
same order as the reversible circuit. Ancilla lines are tied to 0. Outputs
that are not sum or carry bits are garbage and are left unconnected.

A synthesis tool treats these modules as ordinary combinational logic. The
simulation confirms that the circuits add correctly; it says nothing about
the energy behaviour of reversible logic.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from typing import Dict, List, Sequence, Tuple

from revcircuit import Circuit, Gate
from adders import Design, cla_adder, rca_adder
from simplify import simplify_design

Block = Tuple[str, tuple]

LIBRARY = """\
// Reversible gate library.
// Every gate has as many outputs as inputs and realises a one-to-one mapping.
`timescale 1ns / 1ps

// NOT gate: P = A'
module rev_not (input a, output p);
  assign p = ~a;
endmodule

// Feynman (CNOT) gate: P = A, Q = A xor B
module feynman_gate (input a, input b, output p, output q);
  assign p = a;
  assign q = a ^ b;
endmodule

// Toffoli gate: P = A, Q = B, R = AB xor C
module toffoli_gate (input a, input b, input c, output p, output q, output r);
  assign p = a;
  assign q = b;
  assign r = (a & b) ^ c;
endmodule

// Peres gate: P = A, Q = A xor B, R = AB xor C
module peres_gate (input a, input b, input c, output p, output q, output r);
  assign p = a;
  assign q = a ^ b;
  assign r = (a & b) ^ c;
endmodule

// TSG gate: P = A, Q = A'C' xor B', R = Q xor D, S = QD xor AB xor C
module tsg_gate (input a, input b, input c, input d,
                 output p, output q, output r, output s);
  assign p = a;
  assign q = (~a & ~c) ^ ~b;
  assign r = q ^ d;
  assign s = (q & d) ^ (a & b) ^ c;
endmodule

// R2 gate: P = A, Q = B, R = C, S = D xor A xor B xor C
module r2_gate (input a, input b, input c, input d,
                output p, output q, output r, output s);
  assign p = a;
  assign q = b;
  assign r = c;
  assign s = d ^ a ^ b ^ c;
endmodule
"""

# kind -> (module name, input ports, output ports, which line each output drives)
_PORTS = {
    "NOT": ("rev_not", "a", "p", (0,)),
    "Feynman": ("feynman_gate", "ab", "pq", (0, 1)),
    "Toffoli": ("toffoli_gate", "abc", "pqr", (0, 1, 2)),
    "Peres": ("peres_gate", "abc", "pqr", (0, 1, 2)),
    "TSG": ("tsg_gate", "abcd", "pqrs", (0, 1, 3, 2)),      # R drives line d, S drives line c
    "R2": ("r2_gate", "abcd", "pqrs", (0, 1, 2, 3)),
}


def blocks_from_circuit(circuit: Circuit) -> List[Block]:
    """Group Toffoli-type gates into library gates.

    A Toffoli gate followed directly by a CNOT from one of its controls to
    the other is one Peres gate. A gate the library does not have (negative
    controls, or more than two controls) is kept as ("MCT", (gate,)).
    """
    def plain(g: Gate, controls: int) -> bool:
        return len(g.pos) == controls and not g.neg

    blocks: List[Block] = []
    gates, i = circuit.gates, 0
    while i < len(gates):
        g = gates[i]
        nxt = gates[i + 1] if i + 1 < len(gates) else None
        if (plain(g, 2) and nxt is not None and plain(nxt, 1)
                and nxt.pos <= g.pos and nxt.target in g.pos):
            (a,) = nxt.pos
            blocks.append(("Peres", (a, nxt.target, g.target)))
            i += 2
            continue
        if plain(g, 2):
            blocks.append(("Toffoli", (*sorted(g.pos), g.target)))
        elif plain(g, 1):
            blocks.append(("Feynman", (*g.pos, g.target)))
        elif plain(g, 0):
            blocks.append(("NOT", (g.target,)))
        else:
            blocks.append(("MCT", (g,)))
        i += 1
    return blocks


def adder_module(name: str, design: Design, blocks: Sequence[Block], note: str) -> str:
    """Verilog module for a 4-bit adder design given as a list of blocks."""
    names = design.line_names
    has_carry = "c4" in design.outputs
    port_of = {f"a{i}": f"a[{i}]" for i in range(4)}
    port_of.update({f"b{i}": f"b[{i}]" for i in range(4)})
    port_of["c0"] = "cin"

    used = set(design.inputs.values()) | set(design.outputs.values())
    for kind, lines in blocks:
        used |= lines[0].lines if kind == "MCT" else set(lines)

    version: Dict[int, int] = {l: 0 for l in used}
    wires: List[str] = []
    body: List[str] = []

    def current(line: int) -> str:
        return f"{names[line]}_{version[line]}"

    def advance(line: int) -> str:
        version[line] += 1
        wires.append(current(line))
        return current(line)

    for line in sorted(used):
        wires.append(current(line))
        source = port_of.get(names[line], "1'b0")
        kind = "primary input" if names[line] in port_of else "ancilla, constant 0"
        body.append(f"  assign {current(line)} = {source};".ljust(30) + f"// {kind}")
    body.append("")

    counts: Counter = Counter()
    for index, (kind, lines) in enumerate(blocks, 1):
        counts[kind] += 1
        if kind == "MCT":
            g = lines[0]
            terms = [current(l) for l in sorted(g.pos)] + ["~" + current(l) for l in sorted(g.neg)]
            old = current(g.target)
            body.append(f"  assign {advance(g.target)} = {old} ^ ({' & '.join(terms)});"
                        f"   // gate {index}: Toffoli-type gate with negative control")
            continue
        module, ins, outs, drives = _PORTS[kind]
        inputs = [f".{port}({current(l)})" for port, l in zip(ins, lines)]
        outputs = [f".{port}({advance(lines[k])})" for port, k in zip(outs, drives)]
        body.append(f"  {module:<13} u{index} ({', '.join(inputs + outputs)});")
    body.append("")

    for i in range(4):
        body.append(f"  assign sum[{i}] = {current(design.outputs[f's{i}'])};")
    if has_carry:
        body.append(f"  assign cout = {current(design.outputs['c4'])};")
    outs = set(design.outputs.values())
    garbage = [current(l) for l in sorted(used) if l not in outs]

    inventory = ", ".join(f"{counts[k]} {k}" for k in ("Peres", "Feynman", "Toffoli", "NOT",
                                                       "TSG", "R2", "MCT") if counts[k])
    ancilla = sum(1 for l in used if l in design.ancilla)
    header = [f"// {note}",
              f"// Gates: {inventory}.  Ancilla inputs: {ancilla}.  Garbage outputs: {len(garbage)}.",
              f"module {name} (",
              "  input  [3:0] a,",
              "  input  [3:0] b,",
              "  input        cin,",
              "  output [3:0] sum" + ("," if has_carry else ""),
              ]
    if has_carry:
        header.append("  output       cout")
    header.append(");")
    decl = []
    for start in range(0, len(wires), 8):
        decl.append("  wire " + ", ".join(wires[start:start + 8]) + ";")
    tail = ["", "  // Garbage outputs (not used): " + ", ".join(garbage), "endmodule", ""]
    return "\n".join(header + decl + [""] + body + tail)


def testbench(modules: Sequence[Tuple[str, bool]]) -> str:
    """Self-checking testbench. `modules` lists (module name, has carry output)."""
    t = ["// Self-checking testbench for the reversible 4-bit adders.",
         "// Part 1 applies a few named cases, convenient for a waveform figure.",
         "// Part 2 applies all 512 input combinations and counts wrong answers.",
         "`timescale 1ns / 1ps",
         "",
         "module tb_rev_adders;",
         "  reg  [3:0] a, b;",
         "  reg        cin;",
         "  reg  [4:0] expected;",
         "  integer    i, total;"]
    for k, (name, carry) in enumerate(modules, 1):
        t.append(f"  wire [3:0] sum{k};" + (f"  wire cout{k};" if carry else ""))
        t.append(f"  integer    errors{k};")
    t.append("")
    for k, (name, carry) in enumerate(modules, 1):
        ports = f".a(a), .b(b), .cin(cin), .sum(sum{k})" + (f", .cout(cout{k})" if carry else "")
        t.append(f"  {name} dut{k} ({ports});")
    t += ["",
          "  task check;",
          "    begin",
          "      expected = a + b + cin;"]
    for k, (name, carry) in enumerate(modules, 1):
        got = f"{{cout{k}, sum{k}}} !== expected" if carry else f"sum{k} !== expected[3:0]"
        t.append(f"      if ({got}) errors{k} = errors{k} + 1;")
    t += ["    end",
          "  endtask",
          "",
          "  initial begin"]
    for k in range(1, len(modules) + 1):
        t.append(f"    errors{k} = 0;")
    t += ["",
          "    // Part 1: named cases",
          "    a = 4'd5;  b = 4'd3; cin = 1'b0; #50; check;   //  5 + 3     =  8",
          "    a = 4'd15; b = 4'd1; cin = 1'b0; #50; check;   // 15 + 1     = 16 (sum 0, carry 1)",
          "    a = 4'd10; b = 4'd5; cin = 1'b0; #50; check;   // 10 + 5     = 15",
          "    a = 4'd9;  b = 4'd9; cin = 1'b1; #50; check;   //  9 + 9 + 1 = 19 (sum 3, carry 1)",
          "",
          "    // Part 2: all 512 input combinations (the whole test ends at 712 ns)",
          "    for (i = 0; i < 512; i = i + 1) begin",
          "      {a, b, cin} = i[8:0];",
          "      #1;",
          "      check;",
          "    end",
          "",
          "    total = 0;"]
    for k, (name, carry) in enumerate(modules, 1):
        what = "sum and carry" if carry else "sum only"
        t.append(f'    $display("{name:<22} ({what:<13}) wrong answers: %0d of 516", errors{k});')
        t.append(f"    total = total + errors{k};")
    t += ['    if (total == 0) $display("ALL TESTS PASSED");',
          '    else            $display("TESTS FAILED: %0d wrong answers", total);',
          "    $finish;",
          "  end",
          "endmodule",
          ""]
    return "\n".join(t)


def gate_testbench() -> str:
    """Self-checking testbench for the gate library.

    The expected outputs come from the Python reference functions in
    adders.py, so this compares the Verilog gates with the Python model.
    """
    from adders import feynman_ref, peres_ref, r2_ref, tsg_ref
    refs = [("rev_not", "a", "p", lambda a: (1 - a,)),
            ("feynman_gate", "ab", "pq", feynman_ref),
            ("toffoli_gate", "abc", "pqr", lambda a, b, c: (a, b, (a & b) ^ c)),
            ("peres_gate", "abc", "pqr", peres_ref),
            ("tsg_gate", "abcd", "pqrs", tsg_ref),
            ("r2_gate", "abcd", "pqrs", r2_ref)]
    t = ["// Self-checking testbench for the reversible gate library.",
         "// Every gate is tried on every input; expected values come from the Python model.",
         "`timescale 1ns / 1ps",
         "",
         "module tb_rev_gates;",
         "  reg  [3:0] x;",
         "  integer    errors, total;"]
    for k, (module, ins, outs, _) in enumerate(refs, 1):
        width = len(outs)
        t.append(f"  wire [{width - 1}:0] y{k};")
        ports = [f".{port}(x[{len(ins) - 1 - j}])" for j, port in enumerate(ins)]
        ports += [f".{port}(y{k}[{width - 1 - j}])" for j, port in enumerate(outs)]
        t.append(f"  {module} g{k} ({', '.join(ports)});")
    t += ["", "  initial begin", "    total = 0;"]
    for k, (module, ins, outs, ref) in enumerate(refs, 1):
        n = len(ins)
        t.append(f"    errors = 0;                                  // {module}")
        for value in range(1 << n):
            bits = [(value >> (n - 1 - j)) & 1 for j in range(n)]
            want = "".join(str(b) for b in ref(*bits))
            given = "".join(str(b) for b in bits).rjust(4, "0")
            t.append(f"    x = 4'b{given}; #1; if (y{k} !== {len(outs)}'b{want}) errors = errors + 1;")
        t.append(f'    $display("{module:<13} wrong answers: %0d of {1 << n}", errors);')
        t.append("    total = total + errors;")
    t += ['    if (total == 0) $display("ALL GATE TESTS PASSED");',
          '    else            $display("GATE TESTS FAILED: %0d wrong answers", total);',
          "    $finish;",
          "  end",
          "endmodule",
          ""]
    return "\n".join(t)


def build_designs() -> List[Tuple[str, Design, List[Block], str]]:
    """The five adder modules: (module name, design, blocks, description)."""
    out = []
    for module, design in (("cla", cla_adder()), ("cla_carry", cla_adder(carry_out=True))):
        tail = "with carry-out" if "c4" in design.outputs else "sum bits only"
        out.append((f"{module}_as_built", design, list(design.blocks),
                    f"Carry look-ahead adder, {tail}, reconstructed from Kumar et al. (IACIS 2024)."))
        result = simplify_design(design)
        out.append((f"{module}_simplified", design.with_circuit(result.circuit, design.name),
                    blocks_from_circuit(result.circuit),
                    f"Carry look-ahead adder, {tail}, after ancilla- and garbage-aware simplification."))
    rca = rca_adder()
    out.append(("rca_peres", rca, list(rca.blocks),
                "Ripple-carry adder with carry-out, two Peres gates per bit."))
    return out


def write_files(folder: str = "verilog") -> Dict[str, str]:
    """Write the three Verilog files into `folder`. Returns {file name: path}."""
    os.makedirs(folder, exist_ok=True)
    designs = build_designs()
    adders = ["// Reversible 4-bit adders built from the gates in rev_gates.v.",
              "// Generated by verilog.py (Phase 6). Do not edit by hand.",
              "`timescale 1ns / 1ps", ""]
    for name, design, blocks, note in designs:
        adders.append(adder_module(name, design, blocks, note))
    contents = {
        "rev_gates.v": LIBRARY,
        "rev_adders.v": "\n".join(adders),
        "tb_rev_adders.v": testbench([(name, "c4" in d.outputs) for name, d, _, _ in designs]),
        "tb_rev_gates.v": gate_testbench(),
    }
    paths = {}
    for file_name, text in contents.items():
        paths[file_name] = os.path.join(folder, file_name)
        with open(paths[file_name], "w", encoding="utf-8") as handle:
            handle.write(text)
    return paths


def simulate(folder: str = "verilog", top: str = "tb_rev_adders"):
    """Compile the files in `folder` and run one testbench with Icarus Verilog.

    Returns the simulator output, or None when iverilog is not installed.
    """
    if shutil.which("iverilog") is None or shutil.which("vvp") is None:
        return None
    sources = [os.path.join(folder, f) for f in ("rev_gates.v", "rev_adders.v", top + ".v")]
    with tempfile.TemporaryDirectory() as scratch:        # keep compiled files out of `folder`
        binary = os.path.join(scratch, top + ".vvp")
        compiled = subprocess.run(["iverilog", "-g2001", "-Wall", "-s", top, "-o", binary] + sources,
                                  capture_output=True, text=True)
        if compiled.returncode != 0:
            return "COMPILE ERROR\n" + compiled.stdout + compiled.stderr
        run = subprocess.run(["vvp", "-n", binary], capture_output=True, text=True)
    return (compiled.stdout + compiled.stderr + run.stdout + run.stderr).strip()


def instance_counts(verilog_text: str, module: str) -> Counter:
    """Count gate instances inside one module of a Verilog file."""
    body = re.search(rf"module {module} \(.*?endmodule", verilog_text, re.S).group(0)
    return Counter(re.findall(r"^\s+(rev_not|feynman_gate|toffoli_gate|peres_gate|tsg_gate|r2_gate)\s",
                              body, re.M))
