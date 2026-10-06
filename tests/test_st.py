"""Every ST rule is exercised red (it fires) and green (it stays quiet on valid code)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from plccheck.st import check_st_file, lint_st, scan_call_findings  # noqa: E402


def codes(findings):
    return sorted(f.code for f in findings)


GOOD_FB = """
FUNCTION_BLOCK FB_Motor
VAR_INPUT
    xStart : BOOL;
    xStop  : BOOL;
    rSpeed : REAL;
END_VAR
VAR_OUTPUT
    xRunning : BOOL;
END_VAR
VAR
    tonDelay : TON;
    rtStart  : R_TRIG;
    eState   : E_MotorState := E_MotorState#Idle;
    aBuf     : ARRAY[1..10] OF INT;
    i        : INT;
END_VAR

rtStart(CLK := xStart);
tonDelay(IN := eState = E_MotorState#Starting, PT := T#2S);

CASE eState OF
    E_MotorState#Idle:
        IF rtStart.Q AND NOT xStop THEN
            eState := E_MotorState#Starting;
        ELSIF rSpeed > 0.5 THEN
            xRunning := FALSE;
        ELSE
            ;
        END_IF;
    E_MotorState#Starting, E_MotorState#Running:
        IF tonDelay.Q THEN
            eState := E_MotorState#Running;
        END_IF;
ELSE
    eState := E_MotorState#Idle;
END_CASE;

FOR i := 1 TO 10 BY 1 DO
    IF aBuf[i] = 0 THEN
        EXIT;
    END_IF;
END_FOR;

WHILE i > 0 DO
    i := i - 1;
END_WHILE;

REPEAT
    i := i + 1;
UNTIL i >= 10
END_REPEAT;

xRunning := eState = E_MotorState#Running;
END_FUNCTION_BLOCK
"""


class StructureTests(unittest.TestCase):
    def test_valid_fb_is_clean(self):
        self.assertEqual(codes(check_st_file(GOOD_FB)), [])

    def test_missing_end_if(self):
        src = "IF a THEN\n  b := 1;\nEND_FOR;\n"
        self.assertIn("ST002", codes(check_st_file(src)))

    def test_unclosed_block_at_eof(self):
        f = check_st_file("PROGRAM P\nVAR x : INT; END_VAR\nx := 1;\n")
        self.assertEqual(codes(f), ["ST002"])
        self.assertIn("never closed", f[0].message)

    def test_closer_without_opener(self):
        self.assertEqual(codes(check_st_file("x := 1;\nEND_IF;\n")), ["ST002"])

    def test_if_without_then(self):
        self.assertIn("ST003", codes(check_st_file("IF a\n  b := 1;\nEND_IF;\n")))

    def test_case_without_of(self):
        self.assertIn("ST003", codes(check_st_file("CASE x\n 1: y := 2;\nEND_CASE;\n")))

    def test_exit_outside_loop(self):
        self.assertEqual(codes(check_st_file("IF a THEN EXIT; END_IF;\n")), ["ST005"])

    def test_exit_inside_loop_ok(self):
        self.assertEqual(codes(check_st_file("WHILE a DO IF b THEN EXIT; END_IF; END_WHILE;\n")), [])

    def test_unbalanced_parens(self):
        self.assertIn("ST006", codes(check_st_file("x := (a + b;\n")))

    def test_unterminated_comment_and_string(self):
        self.assertIn("ST001", codes(check_st_file("x := 1; (* never closed\n")))
        self.assertIn("ST001", codes(check_st_file("s := 'oops;\n")))

    def test_nested_comments_and_pragmas_ignored(self):
        src = "(* outer (* inner END_IF *) still comment *)\n{attribute 'hide'}\n// END_FOR\nx := 1;\n"
        self.assertEqual(codes(check_st_file(src)), [])

    def test_member_named_like_keyword_is_not_keyword(self):
        self.assertEqual(codes(check_st_file("stCfg.Type := 1;\nx := stCfg.Step;\n")), [])


class SemanticHeuristicTests(unittest.TestCase):
    def test_equals_used_as_assignment(self):
        self.assertEqual(codes(check_st_file("x = 5;\n")), ["ST010"])

    def test_equals_in_case_branch(self):
        self.assertIn("ST010", codes(check_st_file("CASE s OF\n 1: y = 2;\nEND_CASE;\n")))

    def test_comparison_in_condition_is_fine(self):
        self.assertEqual(codes(check_st_file("IF x = 5 THEN y := 1; END_IF;\nz := x = 5;\n")), [])

    def test_real_equality_warning(self):
        self.assertEqual(codes(check_st_file("IF rTemp = 21.5 THEN y := 1; END_IF;\n")), ["ST020"])
        self.assertEqual(codes(check_st_file("IF 1.0E3 <> rX THEN y := 1; END_IF;\n")), ["ST020"])

    def test_real_zero_guard_is_allowed(self):  # PLCopen CP8 exception
        self.assertEqual(codes(check_st_file("IF rDen <> 0.0 THEN r := rNum / rDen; END_IF;\n")), [])

    def test_configuration_program_instances(self):
        src = ("CONFIGURATION C\n RESOURCE R ON CPU\n  TASK T (INTERVAL := T#20MS, PRIORITY := 2);\n"
               "  PROGRAM P1 WITH T : Main(x := %IX1.1);\n END_RESOURCE\nEND_CONFIGURATION\n")
        self.assertEqual(codes(check_st_file(src)), [])

    def test_integer_equality_no_warning(self):
        self.assertEqual(codes(check_st_file("IF n = 21 THEN y := 1; END_IF;\n")), [])

    def test_duplicate_declaration(self):
        src = "FUNCTION_BLOCK F\nVAR_INPUT a : INT; END_VAR\nVAR a : BOOL; END_VAR\nEND_FUNCTION_BLOCK\n"
        self.assertEqual(codes(check_st_file(src)), ["ST040"])

    def test_same_name_in_different_pous_ok(self):
        src = ("FUNCTION_BLOCK F\nVAR a : INT; END_VAR\nEND_FUNCTION_BLOCK\n"
               "FUNCTION_BLOCK G\nVAR a : INT; END_VAR\nEND_FUNCTION_BLOCK\n")
        self.assertEqual(codes(check_st_file(src)), [])

    def test_bad_direct_address(self):
        src = "PROGRAM P\nVAR x AT %IX0.0 : BOOL; y AT %QW4 : WORD; z AT %Z9 : BOOL; END_VAR\nEND_PROGRAM\n"
        self.assertEqual(codes(check_st_file(src)), ["ST050"])


class ScanCallTests(unittest.TestCase):
    def prog(self, body: str) -> str:
        return ("PROGRAM P\nVAR\n tonA : TON;\n rtB : Standard.R_TRIG;\n x : BOOL;\n i : INT;\nEND_VAR\n"
                + body + "\nEND_PROGRAM\n")

    def test_timer_called_only_conditionally(self):
        f = check_st_file(self.prog("rtB(CLK := x);\nIF x THEN\n tonA(IN := TRUE, PT := T#5S);\nEND_IF;"))
        self.assertEqual(codes(f), ["ST030"])

    def test_qualified_type_is_recognised(self):
        f = check_st_file(self.prog("tonA(IN := x, PT := T#1S);\nIF x THEN rtB(CLK := x); END_IF;"))
        self.assertEqual(codes(f), ["ST030"])

    def test_timer_called_twice(self):
        f = check_st_file(self.prog("rtB(CLK := x);\ntonA(IN := x, PT := T#1S);\ntonA(IN := NOT x, PT := T#1S);"))
        self.assertEqual(codes(f), ["ST031"])

    def test_timer_called_in_loop(self):
        f = check_st_file(self.prog("rtB(CLK := x);\nFOR i := 1 TO 3 DO tonA(IN := x, PT := T#1S); END_FOR;"))
        self.assertEqual(codes(f), ["ST032"])

    def test_timer_read_never_called(self):
        f = check_st_file(self.prog("rtB(CLK := x);\nx := tonA.Q;"))
        self.assertEqual(codes(f), ["ST033"])

    def test_unconditional_calls_clean(self):
        f = check_st_file(self.prog("rtB(CLK := x);\ntonA(IN := x AND rtB.Q, PT := T#1S);"))
        self.assertEqual(codes(f), [])

    def test_split_declaration_and_body(self):
        decl, an1 = lint_st("FUNCTION_BLOCK FB_X\nVAR\n t : TON;\nEND_VAR\n", "declaration")
        body, an2 = lint_st("IF go THEN\n t(IN := TRUE, PT := T#1S);\nEND_IF;\n", "body")
        self.assertEqual(codes(decl + body), [])
        self.assertEqual(an1.header, ("FUNCTION_BLOCK", "FB_X"))
        self.assertEqual(codes(scan_call_findings([an1, an2])), ["ST030"])


class DialectTests(unittest.TestCase):
    def test_siemens_scl_source(self):
        src = '''FUNCTION_BLOCK "FB_Conveyor"
TITLE = 'Conveyor'
{ S7_Optimized_Access := 'TRUE' }
AUTHOR : comex
VERSION : 0.1
   VAR_INPUT
      start { ExternalAccessible := 'False'} : Bool;
   END_VAR
   VAR
      t1 {InstructionName := 'TON_TIME'; LibVersion := '1.0'} : TON_TIME;
      iec : IEC_TIMER;
   END_VAR

BEGIN
   REGION Timers
      #t1(IN := #start, PT := T#3S);
      #iec.TON(IN := #start, PT := T#1S);
   END_REGION
   IF #t1.Q THEN
      "GlobalDB".running := TRUE;
   END_IF;
END_FUNCTION_BLOCK
'''
        self.assertEqual(codes(check_st_file(src)), [])

    def test_siemens_conditional_multi_instance_timer(self):
        src = ('FUNCTION_BLOCK "F"\nVAR iec : IEC_TIMER; x : Bool; END_VAR\nBEGIN\n'
               'IF #x THEN #iec.TON(IN := TRUE, PT := T#1S); END_IF;\nEND_FUNCTION_BLOCK\n')
        self.assertEqual(codes(check_st_file(src)), ["ST030"])

    def test_textual_sfc(self):
        src = """PROGRAM P
VAR go : BOOL; END_VAR
INITIAL_STEP Start: END_STEP
TRANSITION FROM Start TO Fill := go; END_TRANSITION
STEP Fill: FillValve(N); END_STEP
TRANSITION FROM Fill TO Start := NOT go; END_TRANSITION
END_PROGRAM
"""
        self.assertEqual(codes(check_st_file(src)), [])

    def test_step_as_variable_name(self):
        self.assertEqual(codes(check_st_file("step := step + 1;\nIF step > 3 THEN step := 0; END_IF;\n")), [])

    def test_twincat_oop_declaration(self):
        src = ("{attribute 'reflection'}\nFUNCTION_BLOCK PUBLIC FB_Axis EXTENDS FB_Base IMPLEMENTS I_Axis\n"
               "VAR_INPUT\n  bEnable : BOOL;\nEND_VAR\n")
        f, an = lint_st(src, "declaration")
        self.assertEqual(codes(f), [])
        self.assertEqual(an.header, ("FUNCTION_BLOCK", "FB_Axis"))

    def test_typed_and_time_literals(self):
        src = "d := DT#2026-01-01-12:30:00;\nt := TOD#12:00:00.5;\nw := 16#FF_FF;\nb := 2#1010;\nn := INT#-5;\n"
        self.assertEqual(codes(check_st_file(src)), [])

    def test_type_declarations(self):
        src = ("TYPE E_State : (Idle := 0, Run := 1) INT; END_TYPE\n"
               "TYPE ST_Cfg : STRUCT\n  a : INT;\n  b : ARRAY[0..3] OF REAL;\nEND_STRUCT\nEND_TYPE\n")
        self.assertEqual(codes(check_st_file(src)), [])


if __name__ == "__main__":
    unittest.main()
