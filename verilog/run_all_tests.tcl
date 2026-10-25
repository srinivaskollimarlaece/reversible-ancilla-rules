# Runs all seven testbenches one after the other in the open project.
# Each prints one line per module and ALL TESTS PASSED (or TESTS FAILED)
# in the Tcl Console.
#
# Open the project first (create_project.tcl), then type in the Tcl Console:
#   source C:/rev/vivado/run_all_tests.tcl
#
# On Windows, Vivado sometimes cannot start the compiler while it is still
# re-parsing the large source file ("Spawn failed: No error"). The script
# therefore waits 5 s before each testbench and retries up to three times.

source [file join [file dirname [file normalize [info script]]] open_project_if_needed.tcl]

foreach tb {tb_rev_gates tb_rev_adders tb_wide_4 tb_wide_8 tb_wide_16 tb_wide_32 tb_demo_8} {
    puts "=================== $tb ==================="
    set_property top $tb [get_filesets sim_1]
    update_compile_order -fileset sim_1
    after 5000
    set ok 0
    for {set try 1} {$try <= 3} {incr try} {
        if {![catch {launch_simulation -simset sim_1 -mode behavioral} err]} {
            set ok 1
            break
        }
        puts "Simulation did not start (try $try of 3): $err"
        after 5000
    }
    if {!$ok} {
        puts "SKIPPED $tb: run it by hand (see VIVADO_GUIDE.pdf, section 3.2)"
        continue
    }
    run all
    close_sim
}
