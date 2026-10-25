# Synthesizes (and optionally places and routes) a list of adder modules and
# collects the results in reports/summary.csv, one row per module:
#   module, LUTs, slice LUTs as logic, longest input-to-output delay (ns),
#   logic levels on that path, total on-chip power (W, vectorless estimate)
# Full Vivado reports for each module are written to reports/<module>_*.txt.
#
# How to run: open the project (create_project.tcl), then
#   Tools > Run Tcl Script...  and choose this file.
# Or in a terminal, from this folder:
#   vivado -mode batch -source create_project.tcl
#   vivado -mode batch -source synth_all.tcl
#
# Out-of-context mode: a 32-bit module has 98 inputs and outputs, close to
# the 106 pins of the package, so no I/O buffers or pins are used. The delay is the
# combinational path from an input port to an output port inside the FPGA.
#
# IMPORTANT. These are FPGA figures for the addition each module computes.
# Vivado re-optimizes the logic, so they do not measure the reversible circuit
# (quantum cost, T-count, ancilla lines) and are not physical results of a
# reversible or quantum implementation. See the guide before using them.

# ---- settings -----------------------------------------------------------------
# Modules to process. The default is every design at 32 bits after all
# simplification steps, plus the CLA blocks as built. Names are in README.txt.
set modules {
    cla_blocks_32_as_built
    cla_blocks_32_simplified
    tsg_rca_32_simplified
    peres_rca_32_simplified
    cuccaro_32_simplified
    vbe_32_simplified
    draper_32_simplified
    hybrid_32_simplified
}
# 1 = also place and route (post-route delay, slower); 0 = synthesis only.
set implement 1
# -------------------------------------------------------------------------------

set here [file dirname [file normalize [info script]]]
set out  [file join $here reports]
file mkdir $out

source [file join [file dirname [file normalize [info script]]] open_project_if_needed.tcl]
set part [get_property PART [current_project]]

set csv [open [file join $out summary.csv] w]
puts $csv "module,stage,LUTs,delay_ns,logic_levels,power_W"

foreach top $modules {
    puts "=================== $top ==================="
    synth_design -top $top -part $part -mode out_of_context
    set stage synthesis
    if {$implement} {
        opt_design
        place_design
        route_design
        set stage routed
    }
    # A loose combinational constraint so that every input-to-output path is timed.
    set_max_delay 100 -datapath_only -from [all_inputs] -to [all_outputs]

    report_utilization -file [file join $out ${top}_utilization.txt]
    report_timing -from [all_inputs] -to [all_outputs] -max_paths 1 -nworst 1 \
        -file [file join $out ${top}_timing.txt]
    report_power -file [file join $out ${top}_power.txt]

    set luts  [llength [get_cells -hierarchical -filter {PRIMITIVE_GROUP == LUT}]]
    set path  [lindex [get_timing_paths -from [all_inputs] -to [all_outputs] -max_paths 1 -nworst 1] 0]
    set delay [format %.3f [get_property DATAPATH_DELAY $path]]
    set lvls  [get_property LOGIC_LEVELS $path]
    set power NA
    regexp {Total On-Chip Power \(W\)\s*\|\s*([0-9.]+)} [report_power -return_string] -> power

    puts $csv "$top,$stage,$luts,$delay,$lvls,$power"
    flush $csv
    puts "$top: $luts LUTs, $delay ns, $lvls logic levels, $power W"
    close_design
}
close $csv
puts "Summary written to [file join $out summary.csv]"
