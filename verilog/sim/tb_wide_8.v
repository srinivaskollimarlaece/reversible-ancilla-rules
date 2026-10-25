// Self-checking testbench for the 8-bit adder modules.
// 900 vectors, one every 1 ns: corner cases, then pseudo-random values (fixed seed).
// The run ends before 1000 ns, the default run time of the Vivado simulator.
`timescale 1ns / 1ps

module tb_wide_8;
  reg  [7:0] a, b;
  reg         cin;
  reg  [8:0] with_cin, without_cin;
  integer     i, total, seed;
  wire [7:0] s1;  wire c1;
  integer     e1;
  wire [7:0] s2;  wire c2;
  integer     e2;
  wire [7:0] s3;  wire c3;
  integer     e3;
  wire [7:0] s4;  wire c4;
  integer     e4;
  wire [7:0] s5;  wire c5;
  integer     e5;
  wire [7:0] s6;  wire c6;
  integer     e6;
  wire [7:0] s7;  wire c7;  wire ok7;
  integer     e7;
  wire [7:0] s8;  wire c8;  wire ok8;
  integer     e8;
  wire [7:0] s9;  wire c9;  wire ok9;
  integer     e9;
  wire [7:0] s10;  wire c10;  wire ok10;
  integer     e10;
  wire [7:0] s11;  wire c11;  wire ok11;
  integer     e11;
  wire [7:0] s12;  wire c12;  wire ok12;
  integer     e12;
  wire [7:0] s13;  wire c13;
  integer     e13;
  wire [7:0] s14;  wire c14;
  integer     e14;

  cla_blocks_8_as_built dut1 (.a(a), .b(b), .cin(cin), .sum(s1), .cout(c1));
  cla_blocks_8_simplified dut2 (.a(a), .b(b), .cin(cin), .sum(s2), .cout(c2));
  tsg_rca_8_as_built dut3 (.a(a), .b(b), .cin(cin), .sum(s3), .cout(c3));
  tsg_rca_8_simplified dut4 (.a(a), .b(b), .cin(cin), .sum(s4), .cout(c4));
  peres_rca_8_as_built dut5 (.a(a), .b(b), .cin(cin), .sum(s5), .cout(c5));
  peres_rca_8_simplified dut6 (.a(a), .b(b), .cin(cin), .sum(s6), .cout(c6));
  cuccaro_8_as_built dut7 (.a(a), .b(b), .sum(s7), .cout(c7), .clean(ok7));
  cuccaro_8_simplified dut8 (.a(a), .b(b), .sum(s8), .cout(c8), .clean(ok8));
  vbe_8_as_built dut9 (.a(a), .b(b), .sum(s9), .cout(c9), .clean(ok9));
  vbe_8_simplified dut10 (.a(a), .b(b), .sum(s10), .cout(c10), .clean(ok10));
  draper_8_as_built dut11 (.a(a), .b(b), .sum(s11), .cout(c11), .clean(ok11));
  draper_8_simplified dut12 (.a(a), .b(b), .sum(s12), .cout(c12), .clean(ok12));
  hybrid_8_as_built dut13 (.a(a), .b(b), .cin(cin), .sum(s13), .cout(c13));
  hybrid_8_simplified dut14 (.a(a), .b(b), .cin(cin), .sum(s14), .cout(c14));

  task check;
    begin
      with_cin    = a + b + cin;
      without_cin = a + b;
      if ({c1, s1} !== with_cin) e1 = e1 + 1;
      if ({c2, s2} !== with_cin) e2 = e2 + 1;
      if ({c3, s3} !== with_cin) e3 = e3 + 1;
      if ({c4, s4} !== with_cin) e4 = e4 + 1;
      if ({c5, s5} !== with_cin) e5 = e5 + 1;
      if ({c6, s6} !== with_cin) e6 = e6 + 1;
      if ({c7, s7} !== without_cin || ok7 !== 1'b1) e7 = e7 + 1;
      if ({c8, s8} !== without_cin || ok8 !== 1'b1) e8 = e8 + 1;
      if ({c9, s9} !== without_cin || ok9 !== 1'b1) e9 = e9 + 1;
      if ({c10, s10} !== without_cin || ok10 !== 1'b1) e10 = e10 + 1;
      if ({c11, s11} !== without_cin || ok11 !== 1'b1) e11 = e11 + 1;
      if ({c12, s12} !== without_cin || ok12 !== 1'b1) e12 = e12 + 1;
      if ({c13, s13} !== with_cin) e13 = e13 + 1;
      if ({c14, s14} !== with_cin) e14 = e14 + 1;
    end
  endtask

  initial begin
    e1 = 0;
    e2 = 0;
    e3 = 0;
    e4 = 0;
    e5 = 0;
    e6 = 0;
    e7 = 0;
    e8 = 0;
    e9 = 0;
    e10 = 0;
    e11 = 0;
    e12 = 0;
    e13 = 0;
    e14 = 0;
    a = 0; b = 0; cin = 0; #1; check;
    a = {8{1'b1}}; b = 1; cin = 0; #1; check;
    a = {8{1'b1}}; b = {8{1'b1}}; cin = 1; #1; check;
    a = {8{1'b1}}; b = {8{1'b1}}; cin = 0; #1; check;
    a = {4{2'b10}}; b = ~{4{2'b10}}; cin = 1; #1; check;
    a = {4{2'b10}}; b = {4{2'b10}}; cin = 0; #1; check;
    a = 1; b = {8{1'b1}}; cin = 0; #1; check;
    a = 0; b = {8{1'b1}}; cin = 1; #1; check;
    seed = 2026;
    for (i = 8; i < 900; i = i + 1) begin
      a = $random(seed); b = $random(seed); cin = $random(seed);
      #1; check;
    end

    total = 0;
    $display("cla_blocks_8_as_built      wrong answers: %0d of 900", e1);
    total = total + e1;
    $display("cla_blocks_8_simplified    wrong answers: %0d of 900", e2);
    total = total + e2;
    $display("tsg_rca_8_as_built         wrong answers: %0d of 900", e3);
    total = total + e3;
    $display("tsg_rca_8_simplified       wrong answers: %0d of 900", e4);
    total = total + e4;
    $display("peres_rca_8_as_built       wrong answers: %0d of 900", e5);
    total = total + e5;
    $display("peres_rca_8_simplified     wrong answers: %0d of 900", e6);
    total = total + e6;
    $display("cuccaro_8_as_built         wrong answers: %0d of 900", e7);
    total = total + e7;
    $display("cuccaro_8_simplified       wrong answers: %0d of 900", e8);
    total = total + e8;
    $display("vbe_8_as_built             wrong answers: %0d of 900", e9);
    total = total + e9;
    $display("vbe_8_simplified           wrong answers: %0d of 900", e10);
    total = total + e10;
    $display("draper_8_as_built          wrong answers: %0d of 900", e11);
    total = total + e11;
    $display("draper_8_simplified        wrong answers: %0d of 900", e12);
    total = total + e12;
    $display("hybrid_8_as_built          wrong answers: %0d of 900", e13);
    total = total + e13;
    $display("hybrid_8_simplified        wrong answers: %0d of 900", e14);
    total = total + e14;
    if (total == 0) $display("ALL TESTS PASSED");
    else            $display("TESTS FAILED: %0d wrong answers", total);
    $finish;
  end
endmodule
