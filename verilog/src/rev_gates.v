// Reversible gate library.
// Every gate has as many outputs as inputs and realises a one-to-one mapping.
`timescale 1ns / 1ps

// NOT gate: P = A'
module rev_not (input a, output p);
  assign p = ~a;
endmodule

// Feynman (CNOT) gate: P = A, Q = A xor B
module feynman_gate (input a, input b, output p, output q);
  assign p = a;
  assign q = a ^ b;
endmodule

// Toffoli gate: P = A, Q = B, R = AB xor C
module toffoli_gate (input a, input b, input c, output p, output q, output r);
  assign p = a;
  assign q = b;
  assign r = (a & b) ^ c;
endmodule

// Peres gate: P = A, Q = A xor B, R = AB xor C
module peres_gate (input a, input b, input c, output p, output q, output r);
  assign p = a;
  assign q = a ^ b;
  assign r = (a & b) ^ c;
endmodule

// TSG gate: P = A, Q = A'C' xor B', R = Q xor D, S = QD xor AB xor C
module tsg_gate (input a, input b, input c, input d,
                 output p, output q, output r, output s);
  assign p = a;
  assign q = (~a & ~c) ^ ~b;
  assign r = q ^ d;
  assign s = (q & d) ^ (a & b) ^ c;
endmodule

// R2 gate: P = A, Q = B, R = C, S = D xor A xor B xor C
module r2_gate (input a, input b, input c, input d,
                output p, output q, output r, output s);
  assign p = a;
  assign q = b;
  assign r = c;
  assign s = d ^ a ^ b ^ c;
endmodule
