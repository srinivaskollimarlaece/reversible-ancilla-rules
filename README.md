# Local rewrite rules for reversible circuits with ancilla and garbage lines

Code, notebooks and Verilog for the paper

> K. Srinivasa Rao, Pappuleti Bharath, "Local Rewrite Rules for Reversible Circuits with Ancilla and Garbage Lines: Evaluation on Benchmarks and Reversible Adders", submitted to *Integration, the VLSI Journal*, 2026.

The repository contains:

- an implementation of the complete rule set for reversible circuits of Feng and Li (IEEE TCAD 45(8), 2026), with a cost-driven optimizer;
- five local rewrite rules **A1–A5** for circuits with ancilla (constant-input) and garbage lines, with a soundness test on random circuits;
- six published reversible adders at 4–32 bits and a **hybrid carry look-ahead adder** (Peres-gate PGA blocks + prefix carry network), each proved correct for all inputs with binary decision diagrams;
- structural Verilog for 56 adder modules, with self-checking testbenches and Vivado scripts.

The code is plain Python 3 with no required packages. Matplotlib is needed only for the figures; Qiskit, PyZX and sympy only for the tool comparison and compiled-circuit measures (Tables 9, 12 and 13).

## Quick start

```bash
git clone https://github.com/srinivaskollimarlaece/reversible-ancilla-rules.git
cd reversible-ancilla-rules/src
python verify_phase11.py      # main results of the paper, about one minute
```

The run ends with `All checks passed.` Its expected output is in [`results/phase11_output.txt`](results/phase11_output.txt).

**Google Colab.** Open any notebook in `notebooks/` in Colab and choose *Runtime → Run all*. Each notebook writes the modules it needs with `%%writefile` cells, so no other file is needed.

## Where each result comes from

Run each script from the `src` folder.

| Paper | Script | Notes |
| --- | --- | --- |
| Sec. 3.1, rule verification (26,978 instances) | `verify_phase1.py` | `python verify_phase1.py 4` is a faster run on 2–4 lines |
| Sec. 3.1, canonical form | `verify_phase2.py` | |
| Table 2, optimizer against the exact optimum | `verify_phase3.py` | |
| Tables 5–6, Figs. 1–3, the adder of Kumar et al. | `verify_phase4.py`, `verify_phase5.py` | |
| Table 3, RevLib benchmarks | `verify_phase8.py` (part F) | downloads RevLib files from MQT QCEC 1.10.0 with `git` |
| Table 9, Hoare-logic pass (Qiskit) | `verify_phase8.py` (part G) | needs `pip install qiskit==2.5.2 z3-solver` |
| Table 9, NCT template matching | `python verify_phase12.py templates` | about 40 minutes; needs `qiskit==2.5.2 sympy` |
| Tables 12–13, Clifford+T, PyZX and heavy-hex routing | `verify_phase12.py` | about 20 minutes; needs `qiskit==2.5.2 pyzx==0.10.7` |
| Tables 4, 7, 8, 10, 11, rules A1–A5 and hybrid adder | `verify_phase11.py` | |
| Sec. 9, Verilog validation | `verify_phase6.py`, `python verilog_wide.py` | needs Icarus Verilog (`iverilog`) |
| Figs. 1–4 and 6 | `python figures.py --print` | 600 dpi PNG and vector PDF |
| Fig. 5 | `python fig_pareto.py` | |

## Layout

```
src/            Python modules and verification scripts
notebooks/      Self-contained Google Colab notebooks, one per phase of the work
verilog/        src/ (gate library, adder modules), sim/ (testbenches), Vivado Tcl scripts
figures/        Figures 1-6 of the paper (vector PDF)
results/        Expected output of verify_phase8.py, verify_phase11.py and verify_phase12.py
```

Main modules in `src/`:

| Module | Content |
| --- | --- |
| `revcircuit.py` | MPMCT gates and circuits, simulation |
| `rules.py` | The ten rules of Feng and Li as rewrite functions |
| `canonical.py` | Canonical form (Algorithm 1 of Feng and Li) |
| `optimizer.py` | Cost-driven rule-based optimizer (moves D1, D2, absorb) |
| `exact.py` | Exact minimum circuits for three lines |
| `arules.py` | **Rules A1–A5** for ancilla and garbage lines (`ancilla_optimize`) |
| `simplify.py`, `bdd.py`, `bitsim.py` | Global simplifier, decision diagrams, bit-parallel simulation |
| `adders.py`, `nadders.py` | Gate library and the six adder designs at n bits |
| `hybrid.py` | **Hybrid carry look-ahead adder** |
| `revlib.py`, `qiskit_compare.py` | RevLib reader, Qiskit comparison |
| `clifford_t.py` | Clifford+T compilation, PyZX optimization, heavy-hex routing |
| `verilog.py`, `verilog_wide.py` | Verilog and testbench generation |
| `figures.py`, `fig_pareto.py` | Figures |

## Verilog and Vivado

`verilog/src` holds the gate library (`rev_gates.v`) and the adder modules. `verilog/sim` holds the testbenches. With Icarus Verilog:

```bash
cd verilog
iverilog -g2001 -s tb_wide_32 -o tb.vvp src/rev_gates.v src/rev_adders_wide.v sim/tb_wide_32.v && vvp tb.vvp
```

For Vivado, see `verilog/README_vivado.txt`. The Verilog checks function only. A synthesis tool maps the modules to ordinary irreversible logic, so the repository makes no area, delay or power claim.

## Requirements

- Python 3.9 or later; tested with Python 3.13 and in Google Colab.
- Optional: `matplotlib` (figures); `qiskit==2.5.2`, `z3-solver`, `sympy` and `pyzx==0.10.7` (Tables 9, 12, 13); Icarus Verilog (Verilog tests); `git` (RevLib download).

## Third-party data

The RevLib benchmark circuits are not included. `revlib.py` downloads them from the MQT QCEC repository, release 1.10.0 (https://github.com/cda-tum/mqt-qcec), which is under its own license.

## How the code was written

The software was written with the assistance of an AI system (Claude, Anthropic) at the direction of the authors, who ran it and checked its results. Every rule is checked by exhaustive simulation, and every reported circuit is proved equal to its specification with decision diagrams.

## Citation

If you use this code, please cite the paper (details will be updated on publication) and this repository (see `CITATION.cff`).

## License

MIT; see `LICENSE`.
