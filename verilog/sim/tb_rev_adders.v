// Self-checking testbench for the reversible 4-bit adders.
// Part 1 applies a few named cases, convenient for a waveform figure.
// Part 2 applies all 512 input combinations and counts wrong answers.
`timescale 1ns / 1ps

module tb_rev_adders;
  reg  [3:0] a, b;
  reg        cin;
  reg  [4:0] expected;
  integer    i, total;
  wire [3:0] sum1;
  integer    errors1;
  wire [3:0] sum2;
  integer    errors2;
  wire [3:0] sum3;  wire cout3;
  integer    errors3;
  wire [3:0] sum4;  wire cout4;
  integer    errors4;
  wire [3:0] sum5;  wire cout5;
  integer    errors5;

  cla_as_built dut1 (.a(a), .b(b), .cin(cin), .sum(sum1));
  cla_simplified dut2 (.a(a), .b(b), .cin(cin), .sum(sum2));
  cla_carry_as_built dut3 (.a(a), .b(b), .cin(cin), .sum(sum3), .cout(cout3));
  cla_carry_simplified dut4 (.a(a), .b(b), .cin(cin), .sum(sum4), .cout(cout4));
  rca_peres dut5 (.a(a), .b(b), .cin(cin), .sum(sum5), .cout(cout5));

  task check;
    begin
      expected = a + b + cin;
      if (sum1 !== expected[3:0]) errors1 = errors1 + 1;
      if (sum2 !== expected[3:0]) errors2 = errors2 + 1;
      if ({cout3, sum3} !== expected) errors3 = errors3 + 1;
      if ({cout4, sum4} !== expected) errors4 = errors4 + 1;
      if ({cout5, sum5} !== expected) errors5 = errors5 + 1;
    end
  endtask

  initial begin
    errors1 = 0;
    errors2 = 0;
    errors3 = 0;
    errors4 = 0;
    errors5 = 0;

    // Part 1: named cases
    a = 4'd5;  b = 4'd3; cin = 1'b0; #50; check;   //  5 + 3     =  8
    a = 4'd15; b = 4'd1; cin = 1'b0; #50; check;   // 15 + 1     = 16 (sum 0, carry 1)
    a = 4'd10; b = 4'd5; cin = 1'b0; #50; check;   // 10 + 5     = 15
    a = 4'd9;  b = 4'd9; cin = 1'b1; #50; check;   //  9 + 9 + 1 = 19 (sum 3, carry 1)

    // Part 2: all 512 input combinations (the whole test ends at 712 ns)
    for (i = 0; i < 512; i = i + 1) begin
      {a, b, cin} = i[8:0];
      #1;
      check;
    end

    total = 0;
    $display("cla_as_built           (sum only     ) wrong answers: %0d of 516", errors1);
    total = total + errors1;
    $display("cla_simplified         (sum only     ) wrong answers: %0d of 516", errors2);
    total = total + errors2;
    $display("cla_carry_as_built     (sum and carry) wrong answers: %0d of 516", errors3);
    total = total + errors3;
    $display("cla_carry_simplified   (sum and carry) wrong answers: %0d of 516", errors4);
    total = total + errors4;
    $display("rca_peres              (sum and carry) wrong answers: %0d of 516", errors5);
    total = total + errors5;
    if (total == 0) $display("ALL TESTS PASSED");
    else            $display("TESTS FAILED: %0d wrong answers", total);
    $finish;
  end
endmodule
