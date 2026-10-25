"""Figures for the thesis: circuit diagrams and a simulation waveform (Phase 7).

  gate_library_figure   the four blocks (Feynman, Peres, TSG, R2) as
                        Toffoli-type circuits
  circuit_figure        any adder as a reversible circuit diagram, with its
                        blocks marked along the top
  waveform_figure       inputs and outputs of the Verilog adders for the four
                        named test cases, taken from an Icarus Verilog run

Diagram symbols: filled dot = positive control, open dot = negative control,
circled plus = target. Time runs from left to right.

  depth_figure          Toffoli depth of the Phase 8 designs against word length
  design_figure         a Phase 8 adder design (TSG, Cuccaro, VBE, Draper) as a
                        circuit diagram with its blocks marked

All figures are black on white so that they print well. They need matplotlib;
the waveform also needs the Icarus Verilog simulator (command `iverilog`).

    python figures.py            figures at 300 dpi
    python figures.py --print    figures at 600 dpi, each also as a vector PDF
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle

from revcircuit import Circuit, Gate
from adders import Design, cla_adder, feynman, peres, r2, rca_adder, tsg
from simplify import simplify_design
import verilog

DPI = 300            # IEEE asks for at least 600 dpi for line art; make_all(dpi=600) gives that
VECTOR = False       # True: also write a vector PDF next to every PNG

INK = "#000000"
SOFT = "#555555"
BAND = "#e6e6e6"
GATES_IN = {"Feynman": 1, "Peres": 2, "Toffoli": 1, "NOT": 1, "MCT": 1, "TSG": 5, "R2": 3}
SHORT = {"Feynman": "F", "Peres": "P", "Toffoli": "T", "NOT": "N", "MCT": "M", "TSG": "TSG", "R2": "R2"}


def _save(fig, path: str) -> None:
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    if VECTOR:
        fig.savefig(os.path.splitext(path)[0] + ".pdf", bbox_inches="tight", facecolor="white")


def _math(name: str) -> str:
    """'a0' -> '$A_0$', 'c0' -> '$C_0$' for input labels."""
    return f"${name[0].upper()}_{{{name[1:]}}}$"


def _draw_gates(ax, gates: Sequence[Gate], row: Dict[int, int], x0: float = 1.0) -> None:
    for k, g in enumerate(gates):
        x = x0 + k
        ys = [row[l] for l in g.lines]
        ax.plot([x, x], [min(ys), max(ys)], color=INK, lw=1.1, zorder=2)
        for l in g.pos:
            ax.add_patch(Circle((x, row[l]), 0.13, fc=INK, ec=INK, lw=1.0, zorder=3))
        for l in g.neg:
            ax.add_patch(Circle((x, row[l]), 0.15, fc="white", ec=INK, lw=1.1, zorder=3))
        y = row[g.target]
        ax.add_patch(Circle((x, y), 0.26, fc="white", ec=INK, lw=1.1, zorder=3))
        ax.plot([x - 0.26, x + 0.26], [y, y], color=INK, lw=1.1, zorder=4)
        ax.plot([x, x], [y - 0.26, y + 0.26], color=INK, lw=1.1, zorder=4)


def circuit_figure(path: str, design: Design, circuit: Circuit,
                   blocks: Optional[Sequence[Tuple[str, tuple]]] = None,
                   title: str = "") -> str:
    """Draw an adder circuit. Lines that no gate touches are left out."""
    used = set(design.inputs.values()) | set(design.outputs.values())
    for g in circuit:
        used |= g.lines
    lines = sorted(used)
    row = {l: i for i, l in enumerate(lines)}
    n_gates, n_rows = len(circuit), len(lines)
    x_end = n_gates + 1

    fig, ax = plt.subplots(figsize=(0.30 * n_gates + 3.2, 0.33 * n_rows + 1.3), dpi=DPI)

    if blocks:                                         # alternate shading marks the blocks
        k = 0
        for index, (kind, _) in enumerate(blocks):
            width = GATES_IN[kind]
            if index % 2 == 0:
                ax.add_patch(Rectangle((k + 0.5, -0.6), width, n_rows + 0.2, fc=BAND, ec="none", zorder=0))
            ax.text(k + 0.5 + width / 2, -0.95, SHORT[kind], ha="center", va="center",
                    fontsize=7.5, color=INK)
            k += width

    outputs = {l: name for name, l in design.outputs.items()}
    names = design.line_names
    for l in lines:
        y = row[l]
        ax.plot([0.3, x_end - 0.3], [y, y], color=INK, lw=0.7, zorder=1)
        is_input = names[l] in design.inputs
        ax.text(-0.1, y, _math(names[l]) if is_input else "0", ha="right", va="center",
                fontsize=9, color=INK)
        ax.text(-1.5, y, names[l], ha="right", va="center", fontsize=7.5, color=SOFT,
                family="monospace")
        if l in outputs:
            ax.text(x_end + 0.1, y, _math(outputs[l]), ha="left", va="center", fontsize=9,
                    color=INK, fontweight="bold")
    _draw_gates(ax, circuit.gates, row)

    ax.text(-1.5, -0.95, "line", ha="right", va="center", fontsize=7, color=SOFT)
    ax.text(-0.1, -0.95, "input", ha="right", va="center", fontsize=7, color=SOFT)
    ax.text(x_end + 0.1, -0.95, "output", ha="left", va="center", fontsize=7, color=SOFT)
    if blocks:
        kinds = [k for k in ("Peres", "Feynman", "Toffoli", "TSG", "R2", "NOT", "MCT")
                 if any(kind == k for kind, _ in blocks)]
        key = "Blocks:  " + ",  ".join(f"{SHORT[k]} = {k}" for k in kinds if SHORT[k] != k)
        ax.text(0.5, n_rows + 0.15, key, ha="left", va="center", fontsize=7.5, color=SOFT)
    if title:
        ax.set_title(title, fontsize=10, color=INK, pad=6)
    ax.set_xlim(-3.2, x_end + 1.6)
    ax.set_ylim(n_rows + 0.5, -1.4)
    ax.set_aspect("equal")
    ax.axis("off")
    _save(fig, path)
    plt.close(fig)
    return path


def gate_library_figure(path: str) -> str:
    """The four blocks of the adder paper as Toffoli-type circuits."""
    panels = [
        ("Feynman gate", feynman(0, 1), "AB", ["A", "A ⊕ B"]),
        ("Peres gate", peres(0, 1, 2), "ABC", ["A", "A ⊕ B", "AB ⊕ C"]),
        ("TSG gate", tsg(0, 1, 2, 3), "ABCD", ["A", "Q", "QD ⊕ AB ⊕ C", "Q ⊕ D"]),
        ("R2 gate", r2(0, 1, 2, 3), "ABCD", ["A", "B", "C", "D ⊕ A ⊕ B ⊕ C"]),
    ]
    widths = [len(g) + 5.2 for _, g, _, _ in panels]
    fig, axes = plt.subplots(1, 4, figsize=(0.46 * sum(widths), 2.6), dpi=DPI,
                             gridspec_kw={"width_ratios": widths, "wspace": 0.05})
    for ax, (name, gates, ins, outs) in zip(axes, panels):
        n = len(ins)
        row = {l: l for l in range(n)}
        x_end = len(gates) + 1
        for l in range(n):
            ax.plot([0.3, x_end - 0.3], [l, l], color=INK, lw=0.7, zorder=1)
            ax.text(0.1, l, ins[l], ha="right", va="center", fontsize=9, color=INK, style="italic")
            ax.text(x_end - 0.1, l, outs[l], ha="left", va="center", fontsize=8.5, color=INK)
        _draw_gates(ax, gates, row)
        ax.set_title(name, fontsize=9.5, color=INK, pad=4)
        ax.set_xlim(-0.6, x_end + 3.6)
        ax.set_ylim(3.6, -0.7)
        ax.set_aspect("equal")
        ax.axis("off")
    fig.text(0.5, 0.02, "TSG gate:  Q = A'C' ⊕ B'", ha="center", fontsize=8, color=SOFT)
    _save(fig, path)
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# Waveform
# ---------------------------------------------------------------------------
WAVE_CASES = [(5, 3, 0), (15, 1, 0), (10, 5, 0), (9, 9, 1)]          # (a, b, cin), 50 ns each
WAVE_DUTS = [("cla_as_built", False), ("cla_simplified", False),
             ("cla_carry_simplified", True), ("rca_peres", True)]


def _wave_testbench() -> str:
    t = ["`timescale 1ns / 1ps", "module tb_waveform;", "  reg [3:0] a, b;", "  reg cin;"]
    for name, carry in WAVE_DUTS:
        t.append(f"  wire [3:0] sum_{name};" + (f" wire cout_{name};" if carry else ""))
        ports = f".a(a), .b(b), .cin(cin), .sum(sum_{name})" + (f", .cout(cout_{name})" if carry else "")
        t.append(f"  {name} dut_{name} ({ports});")
    t += ["  initial begin", '    $dumpfile("wave.vcd");', "    $dumpvars(1, tb_waveform);"]
    for a, b, cin in WAVE_CASES:
        t.append(f"    a = 4'd{a}; b = 4'd{b}; cin = 1'b{cin}; #50;")
    t += ["    $finish;", "  end", "endmodule", ""]
    return "\n".join(t)


def _read_vcd(text: str) -> Dict[str, List[Tuple[int, int]]]:
    """Value changes per signal: {name: [(time in ns, value), ...]}."""
    names, changes, now = {}, {}, 0
    scale = 1.0
    m = re.search(r"\$timescale\s+(\d+)\s*(\w+)\s+\$end", text)
    if m:
        scale = int(m.group(1)) * {"s": 1e9, "ms": 1e6, "us": 1e3, "ns": 1.0, "ps": 1e-3, "fs": 1e-6}[m.group(2)]
    for line in text.splitlines():
        line = line.strip()
        var = re.match(r"\$var\s+\w+\s+\d+\s+(\S+)\s+(\S+)", line)
        if var:
            names[var.group(1)] = var.group(2)
            changes[var.group(2)] = []
        elif line.startswith("#"):
            now = int(round(int(line[1:]) * scale))
        elif line.startswith("b"):
            bits, ident = line[1:].split()
            if ident in names and set(bits) <= {"0", "1"}:
                changes[names[ident]].append((now, int(bits, 2)))
        elif line and line[0] in "01" and line[1:] in names:
            changes[names[line[1:]]].append((now, int(line[0])))
    return changes


def waveform_figure(path: str, folder: str = "verilog") -> Optional[str]:
    """Simulate the four named cases and draw the waveform. None if no simulator."""
    if shutil.which("iverilog") is None or shutil.which("vvp") is None:
        return None
    with tempfile.TemporaryDirectory() as scratch:
        tb = os.path.join(scratch, "tb_waveform.v")
        with open(tb, "w", encoding="utf-8") as handle:
            handle.write(_wave_testbench())
        sources = [os.path.abspath(os.path.join(folder, f)) for f in ("rev_gates.v", "rev_adders.v")]
        subprocess.run(["iverilog", "-g2001", "-s", "tb_waveform", "-o", "wave.vvp", tb] + sources,
                       cwd=scratch, check=True, capture_output=True)
        subprocess.run(["vvp", "-n", "wave.vvp"], cwd=scratch, check=True, capture_output=True)
        with open(os.path.join(scratch, "wave.vcd"), encoding="utf-8") as handle:
            data = _read_vcd(handle.read())

    end = 50 * len(WAVE_CASES)
    rows = [("a[3:0]", "a", True), ("b[3:0]", "b", True), ("cin", "cin", False)]
    for name, carry in WAVE_DUTS:
        rows.append((f"sum[3:0]  {name}", f"sum_{name}", True))
        if carry:
            rows.append((f"cout  {name}", f"cout_{name}", False))

    fig, ax = plt.subplots(figsize=(10, 0.46 * len(rows) + 1.2), dpi=DPI)
    for k in range(len(WAVE_CASES) + 1):
        ax.plot([50 * k, 50 * k], [-0.7, len(rows) - 0.3], color="#bbbbbb", lw=0.6, ls=(0, (3, 3)), zorder=0)
    for r, (label, key, bus) in enumerate(rows):
        seq = data[key] + [(end, None)]
        ax.text(-4, r, label, ha="right", va="center", fontsize=8.5, color=INK, family="monospace")
        for (t0, value), (t1, _) in zip(seq, seq[1:]):
            if t1 <= t0:
                continue
            if bus:                                    # a bus is a closed box holding its value
                s = 1.2
                ax.plot([t0, t0 + s, t1 - s, t1, t1 - s, t0 + s, t0],
                        [r, r - 0.3, r - 0.3, r, r + 0.3, r + 0.3, r], color=INK, lw=1.0)
                ax.text((t0 + t1) / 2, r, str(value), ha="center", va="center", fontsize=9, color=INK)
            else:                                      # one bit: high is drawn above low
                y = r - 0.3 if value else r + 0.3
                ax.plot([t0, t1], [y, y], color=INK, lw=1.2)
                ax.text((t0 + t1) / 2, r, str(value), ha="center", va="center", fontsize=8, color=SOFT)
        if not bus:
            for (t0, v0), (t1, v1) in zip(data[key], data[key][1:]):
                if v0 != v1:
                    ax.plot([t1, t1], [r - 0.3, r + 0.3], color=INK, lw=1.2)
    for k, (a, b, cin) in enumerate(WAVE_CASES):
        ax.text(50 * k + 25, -1.05, f"{a} + {b} + {cin} = {a + b + cin}", ha="center", va="center",
                fontsize=8.5, color=INK)
    ax.set_xlim(-2, end + 2)
    ax.set_ylim(len(rows) - 0.2, -1.5)
    ax.set_xticks([50 * k for k in range(len(WAVE_CASES) + 1)])
    ax.set_xlabel("Time (ns)", fontsize=9, color=INK)
    ax.set_yticks([])
    for side in ("left", "right", "top"):
        ax.spines[side].set_visible(False)
    ax.tick_params(axis="x", labelsize=8.5, colors=INK)
    _save(fig, path)
    plt.close(fig)
    return path


def depth_figure(path: str, widths: Sequence[int] = (4, 8, 16, 32)) -> str:
    """Toffoli depth of five adder designs as built, against the word length."""
    from nadders import DESIGNS, toffoli_depth
    series = [("vbe", "VBE ripple-carry", "s", "-"),
              ("cuccaro", "Cuccaro ripple-carry", "^", "-"),
              ("cla4_blocks", "CLA blocks (Kumar style)", "D", "--"),
              ("peres_rca", "Peres ripple-carry", "o", "-"),
              ("draper_qcla", "Draper carry look-ahead", "v", "-")]
    fig, ax = plt.subplots(figsize=(6.4, 4.2), dpi=DPI)
    for key, label, marker, style in series:
        values = [toffoli_depth(DESIGNS[key](n).circuit) for n in widths]
        ax.plot(widths, values, color=INK, lw=1.3, ls=style, marker=marker, ms=6,
                mfc="white", mec=INK, mew=1.2, zorder=3)
        ax.annotate(f"{label}  ({values[-1]})", (widths[-1], values[-1]), xytext=(9, 0),
                    textcoords="offset points", va="center", fontsize=8.5, color=INK)
    ax.set_xscale("log", base=2)
    ax.set_yscale("log", base=2)
    ax.set_xticks(list(widths))
    ax.set_xticklabels([str(n) for n in widths])
    ax.set_yticks([4, 8, 16, 32, 64, 128])
    ax.set_yticklabels(["4", "8", "16", "32", "64", "128"])
    ax.set_xlim(widths[0] * 0.85, widths[-1] * 1.12)
    ax.set_ylim(3.5, 140)
    ax.set_xlabel("Word length n (bits)", fontsize=9.5, color=INK)
    ax.set_ylabel("Toffoli depth", fontsize=9.5, color=INK)
    ax.grid(True, which="major", color="#dddddd", lw=0.6, zorder=0)
    ax.minorticks_off()
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.tick_params(labelsize=9, colors=INK)
    _save(fig, path)
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# The adder designs of Phase 8 (nadders.py)
# ---------------------------------------------------------------------------
def adder_bands(key: str, n: int) -> List[Tuple[str, int]]:
    """(label, number of gates) for each block of a Phase 8 design as built."""
    if key == "tsg_rca":
        return [("TSG", 5)] * n
    if key == "peres_rca":
        return [("P", 2)] * (2 * n)
    if key == "cuccaro":
        return [("MAJ", 3)] * n + [("", 1)] + [("UMA", 3)] * n
    if key == "vbe":
        inv = "CARRY$^{-1}$"
        return [("CARRY", 3)] * n + [("", 1), ("SUM", 2)] + [(inv, 3), ("SUM", 2)] * (n - 1)
    if key == "draper_qcla":
        log = n.bit_length() - 1
        p_round = sum((n >> t) - 1 for t in range(1, log))
        g_round = sum(n >> t for t in range(1, log + 1))
        top = 0
        while 3 * (1 << (top + 1)) <= 2 * n:
            top += 1
        c_round = sum((n - (1 << (t - 1))) // (1 << t) for t in range(top, 0, -1))
        bands = [("generate", n), ("propagate", n - 1), ("P", p_round), ("G", g_round),
                 ("C", c_round), ("P$^{-1}$", p_round), ("sum", n + 1), ("restore", n - 1)]
        return [(label, width) for label, width in bands if width]
    raise ValueError(key)


def design_figure(path: str, design, circuit: Optional[Circuit] = None,
                  bands: Optional[Sequence[Tuple[str, int]]] = None) -> str:
    """Draw a Phase 8 adder design (an AdderDesign of nadders.py).

    Left: line name and input (an operand bit, or 0 for a line that starts at 0).
    Right: S for a sum bit, C for the carry-out, the operand name for a restored
    line and 0 for an ancilla line that a clean design returns to 0. A line
    without a label on the right is a garbage output.
    """
    circuit = design.circuit if circuit is None else circuit
    n_rows, n_gates = design.n, len(circuit)
    row = {l: l for l in range(n_rows)}
    x_end = n_gates + 1
    fig, ax = plt.subplots(figsize=(0.30 * n_gates + 3.2, 0.33 * n_rows + 1.3), dpi=DPI)

    if bands:
        k = 0
        for index, (label, width) in enumerate(bands):
            if index % 2 == 0:
                ax.add_patch(Rectangle((k + 0.5, -0.6), width, n_rows + 0.2, fc=BAND, ec="none", zorder=0))
            ax.text(k + 0.5 + width / 2, -0.95, label, ha="center", va="center", fontsize=7, color=INK)
            k += width

    line_of_input = {l: name for name, l in design.inputs.items()}
    out_label: Dict[int, Tuple[str, bool]] = {}
    for l, name in design.restored.items():
        out_label[l] = (_math(name), False)
    if design.style == "clean":
        for l in design.ancilla:
            out_label[l] = ("0", False)
    for i, l in enumerate(design.sum_lines):
        out_label[l] = (f"$S_{{{i}}}$", True)
    if design.carry_line is not None:
        out_label[design.carry_line] = (f"$C_{{{design.bits}}}$", True)

    for l in range(n_rows):
        ax.plot([0.3, x_end - 0.3], [l, l], color=INK, lw=0.7, zorder=1)
        ax.text(-0.1, l, _math(line_of_input[l]) if l in line_of_input else "0", ha="right",
                va="center", fontsize=9, color=INK)
        ax.text(-1.5, l, design.line_names[l], ha="right", va="center", fontsize=7.5, color=SOFT,
                family="monospace")
        if l in out_label:
            text, bold = out_label[l]
            ax.text(x_end + 0.1, l, text, ha="left", va="center", fontsize=9, color=INK,
                    fontweight="bold" if bold else "normal")
    _draw_gates(ax, circuit.gates, row)

    ax.text(-1.5, -0.95, "line", ha="right", va="center", fontsize=7, color=SOFT)
    ax.text(-0.1, -0.95, "input", ha="right", va="center", fontsize=7, color=SOFT)
    ax.text(x_end + 0.1, -0.95, "output", ha="left", va="center", fontsize=7, color=SOFT)
    ax.set_xlim(-3.2, x_end + 1.6)
    ax.set_ylim(n_rows - 0.3, -1.4)
    ax.set_aspect("equal")
    ax.axis("off")
    _save(fig, path)
    plt.close(fig)
    return path


def design_figures(folder: str = "figures", bits: int = 4) -> Dict[str, str]:
    """The Phase 8 designs that the earlier figures do not show, as built, and the
    two that simplification changes into a new circuit, after all steps."""
    from nadders import DESIGNS
    from simplify import simplify
    out = {}
    for key in ("tsg_rca", "cuccaro", "vbe", "draper_qcla"):
        design = DESIGNS[key](bits)
        name = key.replace("_qcla", "")
        out[name] = design_figure(os.path.join(folder, f"fig_{name}.png"), design,
                                  bands=adder_bands(key, bits))
        if key in ("cuccaro", "vbe"):
            result = simplify(design.circuit, list(design.inputs.values()), design.ancilla, design.required)
            out[name + "_simplified"] = design_figure(
                os.path.join(folder, f"fig_{name}_simplified.png"), design, result.circuit)
    try:                                                   # Phase 11: the hybrid adder, at 8 bits
        from hybrid import hybrid_bands, hybrid_cla
        out["hybrid"] = design_figure(os.path.join(folder, "fig_hybrid.png"), hybrid_cla(8),
                                      bands=hybrid_bands(8))
    except ImportError:
        pass
    return out


def make_all(folder: str = "figures", verilog_folder: str = "verilog", dpi: int = 300,
             vector: bool = False) -> Dict[str, Optional[str]]:
    """Write every figure as a PNG file into `folder`. Returns {name: path}.

    dpi=600 meets the IEEE requirement for line art; vector=True also writes
    a PDF version of every figure.
    """
    global DPI, VECTOR
    DPI, VECTOR = dpi, vector
    os.makedirs(folder, exist_ok=True)
    verilog.write_files(verilog_folder)
    out: Dict[str, Optional[str]] = {}
    out["gate_library"] = gate_library_figure(os.path.join(folder, "fig_gate_library.png"))
    for key, design in (("cla", cla_adder()), ("cla_carry", cla_adder(carry_out=True))):
        out[f"{key}_as_built"] = circuit_figure(
            os.path.join(folder, f"fig_{key}_as_built.png"), design, design.circuit, design.blocks)
        result = simplify_design(design)
        out[f"{key}_simplified"] = circuit_figure(
            os.path.join(folder, f"fig_{key}_simplified.png"), design, result.circuit,
            verilog.blocks_from_circuit(result.circuit))
    rca = rca_adder()
    out["rca_peres"] = circuit_figure(os.path.join(folder, "fig_rca_peres.png"), rca, rca.circuit, rca.blocks)
    out["waveform"] = waveform_figure(os.path.join(folder, "fig_waveform.png"), verilog_folder)
    try:
        out["toffoli_depth"] = depth_figure(os.path.join(folder, "fig_toffoli_depth.png"))
        out.update(design_figures(folder))
    except ImportError:                                   # nadders.py (Phase 8) not present
        out["toffoli_depth"] = None
    return out


if __name__ == "__main__":
    import sys
    options = dict(dpi=600, vector=True) if "--print" in sys.argv else {}
    for name, path in make_all(**options).items():
        print(f"{name:<22}{path or 'SKIPPED (no Verilog simulator found)'}")
