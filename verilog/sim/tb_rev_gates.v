// Self-checking testbench for the reversible gate library.
// Every gate is tried on every input; expected values come from the Python model.
`timescale 1ns / 1ps

module tb_rev_gates;
  reg  [3:0] x;
  integer    errors, total;
  wire [0:0] y1;
  rev_not g1 (.a(x[0]), .p(y1[0]));
  wire [1:0] y2;
  feynman_gate g2 (.a(x[1]), .b(x[0]), .p(y2[1]), .q(y2[0]));
  wire [2:0] y3;
  toffoli_gate g3 (.a(x[2]), .b(x[1]), .c(x[0]), .p(y3[2]), .q(y3[1]), .r(y3[0]));
  wire [2:0] y4;
  peres_gate g4 (.a(x[2]), .b(x[1]), .c(x[0]), .p(y4[2]), .q(y4[1]), .r(y4[0]));
  wire [3:0] y5;
  tsg_gate g5 (.a(x[3]), .b(x[2]), .c(x[1]), .d(x[0]), .p(y5[3]), .q(y5[2]), .r(y5[1]), .s(y5[0]));
  wire [3:0] y6;
  r2_gate g6 (.a(x[3]), .b(x[2]), .c(x[1]), .d(x[0]), .p(y6[3]), .q(y6[2]), .r(y6[1]), .s(y6[0]));

  initial begin
    total = 0;
    errors = 0;                                  // rev_not
    x = 4'b0000; #1; if (y1 !== 1'b1) errors = errors + 1;
    x = 4'b0001; #1; if (y1 !== 1'b0) errors = errors + 1;
    $display("rev_not       wrong answers: %0d of 2", errors);
    total = total + errors;
    errors = 0;                                  // feynman_gate
    x = 4'b0000; #1; if (y2 !== 2'b00) errors = errors + 1;
    x = 4'b0001; #1; if (y2 !== 2'b01) errors = errors + 1;
    x = 4'b0010; #1; if (y2 !== 2'b11) errors = errors + 1;
    x = 4'b0011; #1; if (y2 !== 2'b10) errors = errors + 1;
    $display("feynman_gate  wrong answers: %0d of 4", errors);
    total = total + errors;
    errors = 0;                                  // toffoli_gate
    x = 4'b0000; #1; if (y3 !== 3'b000) errors = errors + 1;
    x = 4'b0001; #1; if (y3 !== 3'b001) errors = errors + 1;
    x = 4'b0010; #1; if (y3 !== 3'b010) errors = errors + 1;
    x = 4'b0011; #1; if (y3 !== 3'b011) errors = errors + 1;
    x = 4'b0100; #1; if (y3 !== 3'b100) errors = errors + 1;
    x = 4'b0101; #1; if (y3 !== 3'b101) errors = errors + 1;
    x = 4'b0110; #1; if (y3 !== 3'b111) errors = errors + 1;
    x = 4'b0111; #1; if (y3 !== 3'b110) errors = errors + 1;
    $display("toffoli_gate  wrong answers: %0d of 8", errors);
    total = total + errors;
    errors = 0;                                  // peres_gate
    x = 4'b0000; #1; if (y4 !== 3'b000) errors = errors + 1;
    x = 4'b0001; #1; if (y4 !== 3'b001) errors = errors + 1;
    x = 4'b0010; #1; if (y4 !== 3'b010) errors = errors + 1;
    x = 4'b0011; #1; if (y4 !== 3'b011) errors = errors + 1;
    x = 4'b0100; #1; if (y4 !== 3'b110) errors = errors + 1;
    x = 4'b0101; #1; if (y4 !== 3'b111) errors = errors + 1;
    x = 4'b0110; #1; if (y4 !== 3'b101) errors = errors + 1;
    x = 4'b0111; #1; if (y4 !== 3'b100) errors = errors + 1;
    $display("peres_gate    wrong answers: %0d of 8", errors);
    total = total + errors;
    errors = 0;                                  // tsg_gate
    x = 4'b0000; #1; if (y5 !== 4'b0000) errors = errors + 1;
    x = 4'b0001; #1; if (y5 !== 4'b0010) errors = errors + 1;
    x = 4'b0010; #1; if (y5 !== 4'b0111) errors = errors + 1;
    x = 4'b0011; #1; if (y5 !== 4'b0100) errors = errors + 1;
    x = 4'b0100; #1; if (y5 !== 4'b0110) errors = errors + 1;
    x = 4'b0101; #1; if (y5 !== 4'b0101) errors = errors + 1;
    x = 4'b0110; #1; if (y5 !== 4'b0001) errors = errors + 1;
    x = 4'b0111; #1; if (y5 !== 4'b0011) errors = errors + 1;
    x = 4'b1000; #1; if (y5 !== 4'b1110) errors = errors + 1;
    x = 4'b1001; #1; if (y5 !== 4'b1101) errors = errors + 1;
    x = 4'b1010; #1; if (y5 !== 4'b1111) errors = errors + 1;
    x = 4'b1011; #1; if (y5 !== 4'b1100) errors = errors + 1;
    x = 4'b1100; #1; if (y5 !== 4'b1001) errors = errors + 1;
    x = 4'b1101; #1; if (y5 !== 4'b1011) errors = errors + 1;
    x = 4'b1110; #1; if (y5 !== 4'b1000) errors = errors + 1;
    x = 4'b1111; #1; if (y5 !== 4'b1010) errors = errors + 1;
    $display("tsg_gate      wrong answers: %0d of 16", errors);
    total = total + errors;
    errors = 0;                                  // r2_gate
    x = 4'b0000; #1; if (y6 !== 4'b0000) errors = errors + 1;
    x = 4'b0001; #1; if (y6 !== 4'b0001) errors = errors + 1;
    x = 4'b0010; #1; if (y6 !== 4'b0011) errors = errors + 1;
    x = 4'b0011; #1; if (y6 !== 4'b0010) errors = errors + 1;
    x = 4'b0100; #1; if (y6 !== 4'b0101) errors = errors + 1;
    x = 4'b0101; #1; if (y6 !== 4'b0100) errors = errors + 1;
    x = 4'b0110; #1; if (y6 !== 4'b0110) errors = errors + 1;
    x = 4'b0111; #1; if (y6 !== 4'b0111) errors = errors + 1;
    x = 4'b1000; #1; if (y6 !== 4'b1001) errors = errors + 1;
    x = 4'b1001; #1; if (y6 !== 4'b1000) errors = errors + 1;
    x = 4'b1010; #1; if (y6 !== 4'b1010) errors = errors + 1;
    x = 4'b1011; #1; if (y6 !== 4'b1011) errors = errors + 1;
    x = 4'b1100; #1; if (y6 !== 4'b1100) errors = errors + 1;
    x = 4'b1101; #1; if (y6 !== 4'b1101) errors = errors + 1;
    x = 4'b1110; #1; if (y6 !== 4'b1111) errors = errors + 1;
    x = 4'b1111; #1; if (y6 !== 4'b1110) errors = errors + 1;
    $display("r2_gate       wrong answers: %0d of 16", errors);
    total = total + errors;
    if (total == 0) $display("ALL GATE TESTS PASSED");
    else            $display("GATE TESTS FAILED: %0d wrong answers", total);
    $finish;
  end
endmodule
