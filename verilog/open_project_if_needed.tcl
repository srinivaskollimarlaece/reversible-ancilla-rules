# Opens the rev_adders project unless it is already the current project.
# Sourced by the other scripts, so they work after Vivado is restarted.
set here [file dirname [file normalize [info script]]]
set xpr  [file join $here rev_adders_project rev_adders.xpr]
set need 1
if {![catch {current_project} cur] && [get_property NAME [current_project]] eq "rev_adders"} {
    set need 0
}
if {$need} {
    if {![file exists $xpr]} {
        error "Project not found: $xpr. Run create_project.tcl first."
    }
    catch {close_project}
    open_project $xpr
    puts "Opened project $xpr"
}
