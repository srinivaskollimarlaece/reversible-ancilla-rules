# Creates a Vivado project with every adder module and every testbench.
#
# In the Vivado GUI:  Tools > Run Tcl Script...  and choose this file.
# From a terminal:    vivado -mode batch -source create_project.tcl
#
# The project is created in the folder rev_adders_project next to this file.

set here [file dirname [file normalize [info script]]]

# Any installed part works for simulation. xc7a35tcpg236-1 is the Artix-7 of the
# Basys 3 board and is included in the free Vivado edition. Change it if needed.
set part xc7a35tcpg236-1

create_project rev_adders [file join $here rev_adders_project] -part $part -force
add_files -norecurse [glob [file join $here src *.v]]
add_files -fileset sim_1 -norecurse [glob [file join $here sim *.v]]
set_property top tb_rev_adders [get_filesets sim_1]
set_property top_lib xil_defaultlib [get_filesets sim_1]
update_compile_order -fileset sources_1
update_compile_order -fileset sim_1

puts "Project created."
puts "Run a test: Flow Navigator > SIMULATION > Run Simulation > Run Behavioral Simulation."
puts "Run every test: Tools > Run Tcl Script... > run_all_tests.tcl"
