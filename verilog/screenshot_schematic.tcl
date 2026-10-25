# Opens the elaborated (RTL) schematic of one adder module, for a screenshot of
# its gate-level structure. Small modules (4 or 8 bits) give readable pictures.
#
# 1. Put the module name on the "set top" line.
# 2. Open the project, then Tools > Run Tcl Script...  and choose this file.
# 3. The schematic window opens. Use File > Export > Export Schematic... or a
#    screenshot.

set top hybrid_8_simplified

source [file join [file dirname [file normalize [info script]]] open_project_if_needed.tcl]

set_property top $top [current_fileset]
update_compile_order -fileset sources_1
synth_design -rtl -name rtl_1 -top $top
show_schematic [get_cells]
