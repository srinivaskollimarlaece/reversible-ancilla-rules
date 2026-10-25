# Synthesizes ONE adder module for the FPGA and writes utilization and timing
# reports into the folder "reports" next to this file.
#
# 1. Put the module name on the "set top" line below (names are listed in README.txt).
# 2. Open the project, then Tools > Run Tcl Script...  and choose this file.
#
# The module is synthesized out of context, so its 60 to 100 inputs and outputs
# do not need package pins.
#
# Read the numbers with care: synthesis turns every module into ordinary
# look-up-table logic for the same addition. They describe an FPGA version of the
# function, not the reversible circuit, and say nothing about quantum cost.

set top cla_blocks_32_simplified

source [file join [file dirname [file normalize [info script]]] open_project_if_needed.tcl]

set here [file dirname [file normalize [info script]]]
file mkdir [file join $here reports]

set_property top $top [current_fileset]
update_compile_order -fileset sources_1
set_property -name {STEPS.SYNTH_DESIGN.ARGS.MORE OPTIONS} -value {-mode out_of_context} -objects [get_runs synth_1]
reset_run synth_1
launch_runs synth_1 -jobs 4
wait_on_run synth_1
open_run synth_1 -name synth_1

report_utilization -file [file join $here reports ${top}_utilization.txt]
set_max_delay 50 -from [all_inputs] -to [all_outputs]
report_timing -from [all_inputs] -to [all_outputs] -max_paths 1 -file [file join $here reports ${top}_timing.txt]
puts "Reports written to [file join $here reports]"
