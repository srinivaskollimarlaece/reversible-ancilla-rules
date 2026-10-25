// Demonstration testbench for screenshots of the waveform window.
// Four 8-bit additions, each held for 50 ns, applied to four designs:
// the CLA blocks after Kumar et al., the Peres ripple-carry adder,
// the Draper adder (no carry input) and the hybrid adder of this work.
//   0-50 ns     100 + 27  + 0  = 127
//   50-100 ns   255 + 1   + 0  = 256  (carry through all 8 bits)
//   100-150 ns  170 + 85  + 1  = 256  (alternating bits, carry input)
//   150-200 ns  200 + 200 + 1  = 401
// Set the radix of a, b, sum_* and expected to Unsigned Decimal in the
// waveform window. The run ends at 200 ns and prints DEMO PASSED.
`timescale 1ns / 1ps

module tb_demo_8;
  reg  [7:0] a, b;
  reg        cin;
  wire [8:0] expected = a + b + cin;
  wire [8:0] expected_no_cin = a + b;

  wire [7:0] sum_cla, sum_peres, sum_draper, sum_hybrid;
  wire       cout_cla, cout_peres, cout_draper, cout_hybrid, clean_draper;

  cla_blocks_8_simplified u_cla    (.a(a), .b(b), .cin(cin), .sum(sum_cla),    .cout(cout_cla));
  peres_rca_8_simplified  u_peres  (.a(a), .b(b), .cin(cin), .sum(sum_peres),  .cout(cout_peres));
  draper_8_simplified     u_draper (.a(a), .b(b),            .sum(sum_draper), .cout(cout_draper), .clean(clean_draper));
  hybrid_8_simplified     u_hybrid (.a(a), .b(b), .cin(cin), .sum(sum_hybrid), .cout(cout_hybrid));

  integer errors;

  task apply(input [7:0] x, input [7:0] y, input c);
    begin
      a = x; b = y; cin = c;
      #50;
      if ({cout_cla, sum_cla} !== expected)       errors = errors + 1;
      if ({cout_peres, sum_peres} !== expected)   errors = errors + 1;
      if ({cout_hybrid, sum_hybrid} !== expected) errors = errors + 1;
      if ({cout_draper, sum_draper} !== expected_no_cin || clean_draper !== 1'b1) errors = errors + 1;
      $display("%t: %0d + %0d + %0d = %0d | CLA %0d  Peres %0d  Hybrid %0d | Draper (no cin) %0d",
               $time, x, y, c, expected, {cout_cla, sum_cla}, {cout_peres, sum_peres},
               {cout_hybrid, sum_hybrid}, {cout_draper, sum_draper});
    end
  endtask

  initial begin
    errors = 0;
    $timeformat(-9, 0, " ns", 6);
    apply(8'd100, 8'd27,  1'b0);
    apply(8'd255, 8'd1,   1'b0);
    apply(8'd170, 8'd85,  1'b1);
    apply(8'd200, 8'd200, 1'b1);
    if (errors == 0) $display("DEMO PASSED");
    else             $display("DEMO FAILED: %0d wrong results", errors);
    $finish;
  end
endmodule
