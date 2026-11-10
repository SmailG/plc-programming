"""A crafted text file must not make a checker spin: TwinCAT comments, L5K and SIMATIC SD blocks, Logix
rungs and ST routines in L5K.

Each scaling test feeds a checker an input whose size grows 4x and asserts the CPU time grows
about 4x, not 16x (a rescan per element). Each semantics test beside it pins what the linear
version must keep returning on legitimate input.
"""

from __future__ import annotations

import sys
import tracemalloc
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE))

from linear_support import LinearTime  # noqa: E402
from plccheck import twincat  # noqa: E402
from plccheck.logix import check_l5k, check_rung  # noqa: E402
from plccheck.simaticml import check_simatic_sd  # noqa: E402
from plccheck.st import lint_st  # noqa: E402


class TwinCatCommentStripping(LinearTime):
    """Comment stripping scans once; an opener that never closes must not rescan the rest of the text."""

    # (opener repeated, small, big). Every opener is unclosed, so a retry from each one walks to the
    # end of the text. The pragma case needs a bigger text: its scan is a single character class.
    INPUTS = {
        "(* never closed": ("(* ", 1_500, 6_000),
        "/* never closed": ("/* ", 1_500, 6_000),
        "{ never closed": ("{ ", 5_000, 20_000),
    }

    def test_strip_time_grows_linearly_with_the_unclosed_openers(self):
        for name, (unit, small, big) in self.INPUTS.items():
            with self.subTest(name):
                self.assert_linear(lambda n, unit=unit: (lambda text=unit * n: twincat._strip_comments(text)), small, big)

    def test_an_opener_without_a_closer_ends_the_scan(self):
        # The timing test cannot see a retry loop built on str.find (about 10x cheaper than a regex
        # retry, so below timer noise at a test-sized input), so count the searches directly.
        class CountingStr(str):
            calls = 0

            def find(self, *args):
                CountingStr.calls += 1
                return super().find(*args)

        text = CountingStr("(* " * 1000)
        self.assertEqual(twincat._blank_spans(text, "(*", "*)"), text)
        self.assertLessEqual(CountingStr.calls, 3)  # one opener found, one failed closer search; a retry per opener is 1000
        CountingStr.calls = 0
        twincat._blank_spans(CountingStr("(* a *) " * 1000), "(*", "*)")
        self.assertLessEqual(CountingStr.calls, 2 * 1000 + 1)  # an opener and a closer search per span, one last opener search

    def test_terminated_unterminated_and_adjacent_comments(self):
        cases = {
            "a (* c *) b": "a   b",
            "a (* c": "a (* c",
            "(* x *)(* y *)": "  ",
            "a /* c */ b /* d": "a   b /* d",
            "/* x *//* y */z": "  z",
            "a (* x\ny *) b": "a   b",
            "{ pragma } a { open": "  a { open",
            "{a\n}b": " b",
            "x // c\ny": "x  \ny",
            "x // c": "x  ",
            "//\n//\n": " \n \n",
        }
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(twincat._strip_comments(text), want)

    def test_an_opener_is_not_closed_by_its_own_characters(self):
        for text in ("(*)", "a (*) b", "/*/", "a /*/ b"):
            with self.subTest(text=text):
                self.assertEqual(twincat._strip_comments(text), text)
        self.assertEqual(twincat._strip_comments("(*)*)"), " ")
        self.assertEqual(twincat._strip_comments("/*/*/"), " ")

    def test_openers_do_not_nest_and_passes_run_in_order(self):
        self.assertEqual(twincat._strip_comments("(* (* *) *)"), "  *)")
        self.assertEqual(twincat._strip_comments("(* // *)\nx"), " \nx")  # the (* *) pass runs before //
        self.assertEqual(twincat._strip_comments("(* /* *) */"), "  */")  # (* *) first: it takes the /* inside
        self.assertEqual(twincat._strip_comments("/* (* */ *)"), "/*  ")  # then /* */ finds nothing left to pair with
        self.assertEqual(twincat._strip_comments("// (* \n *)"), " ")  # so the (* *) span crosses the line end
        self.assertEqual(twincat._strip_comments("// x (* y\nz"), " \nz")  # an unclosed (* is left for the // pass
        self.assertEqual(twincat._strip_comments("{ // }\nz"), "{  \nz")  # { } runs last: // already took the }
        self.assertEqual(twincat._strip_comments("/* { */ }"), "  }")


class LogixL5kBlockStack(LinearTime):
    """A closer that matches no open block is found without scanning the stack."""

    def errors(self, text: str) -> list[tuple[int | None, str]]:
        found = check_l5k(text)
        self.assertEqual({f.code for f in found}, {"LX050"} if found else set())
        return [(f.line, f.message) for f in found]

    def test_check_time_grows_linearly_with_the_open_blocks(self):
        # Every END_ZZ matches nothing, so each one used to walk all the open PROGRAM frames:
        # quadratic in the depth (about 16x for 4x), a count lookup is linear (about 4x).
        def make(n):
            text = "PROGRAM " * n + "END_ZZ " * n
            return lambda: check_l5k(text)
        self.assert_linear(make, 1_000, 4_000)

    def test_a_closer_matching_nothing_reports_its_error(self):
        self.assertEqual(self.errors("END_ROUTINE"), [(1, "END_ROUTINE without an open ROUTINE")])
        self.assertEqual(self.errors("PROGRAM p\nEND_ROUTINE\nEND_PROGRAM"), [(2, "END_ROUTINE without an open ROUTINE")])

    def test_a_matched_closer_closes_its_block(self):
        self.assertEqual(self.errors("PROGRAM p\nROUTINE r\nEND_ROUTINE\nEND_PROGRAM"), [])
        self.assertEqual(self.errors("PROGRAM p\nEND_PROGRAM\nEND_PROGRAM"), [(3, "END_PROGRAM without an open PROGRAM")])
        self.assertEqual(self.errors("PROGRAM a PROGRAM b END_PROGRAM END_PROGRAM END_PROGRAM"),
                         [(1, "END_PROGRAM without an open PROGRAM")])

    def test_a_closer_closes_the_blocks_inside_its_own_and_none_more(self):
        got = self.errors("PROGRAM p\nROUTINE r\nTAG t\nEND_PROGRAM\nEND_ROUTINE\nEND_TAG\nEND_PROGRAM")
        self.assertEqual(got, [
            (2, "ROUTINE opened at line 2 is not closed before END_PROGRAM"),
            (3, "TAG opened at line 3 is not closed before END_PROGRAM"),
            (5, "END_ROUTINE without an open ROUTINE"),
            (6, "END_TAG without an open TAG"),
            (7, "END_PROGRAM without an open PROGRAM"),
        ])

    def test_blocks_left_open_are_reported_at_the_end(self):
        self.assertEqual(self.errors("PROGRAM p\nROUTINE r\nEND_ROUTINE"), [(1, "PROGRAM opened here is never closed")])


class LogixL5kStRoutineLines(LinearTime):
    """An ST routine is linted from its own line, not behind a padding of one newline per file line before it."""

    def test_lint_time_grows_linearly_with_the_number_of_routines(self):
        # Routine k used to be padded with about 3k newlines, so n routines cost n^2 characters:
        # quadratic in the file size (about 16x for 4x).
        def make(n):
            text = "ST_ROUTINE r\n'a := 1;\nEND_ST_ROUTINE\n" * n
            return lambda: check_l5k(text)
        self.assert_linear(make, 700, 2_800)

    def test_findings_name_file_lines_in_their_position_and_their_message(self):
        text = "PROGRAM p\nROUTINE r\nEND_ROUTINE\nST_ROUTINE s\n'IF a THEN\n'x := 1;\nEND_ST_ROUTINE\n" \
               "ST_ROUTINE t\n'(* open\nEND_ST_ROUTINE\nEND_PROGRAM"
        got = [(f.code, f.line, f.message, f.context) for f in check_l5k(text)]
        self.assertEqual(got, [
            ("ST002", 5, "IF opened at line 5 is never closed", "L5K ST routine"),
            ("ST001", 9, "unterminated comment opened with '(*'", "L5K ST routine"),
        ])

    def test_lint_st_numbers_lines_from_first_line(self):
        findings, _ = lint_st("x := 1;\nIF a THEN", "body", 10)
        self.assertEqual([(f.line, f.message) for f in findings], [(11, "IF opened at line 11 is never closed")])
        findings, _ = lint_st("x := 1;\nIF a THEN", "body")
        self.assertEqual([(f.line, f.message) for f in findings], [(2, "IF opened at line 2 is never closed")])


class SimaticSdBlockStack(LinearTime):
    """SIMATIC SD: a closer that matches no open NETWORK/RUNG is found without scanning the stack."""

    def errors(self, text: str) -> list[tuple[int | None, str]]:
        found = check_simatic_sd(text)
        self.assertEqual({f.code for f in found}, {"SD001"} if found else set())
        return [(f.line, f.message) for f in found]

    def test_check_time_grows_linearly_with_the_open_blocks(self):
        # Every END_RUNG matches nothing, so each one used to walk all the open NETWORK frames:
        # quadratic in the depth (about 16x for 4x), a count lookup is linear (about 4x).
        def make(n):
            text = "NETWORK " * n + "END_RUNG " * n
            return lambda: check_simatic_sd(text)
        self.assert_linear(make, 1_000, 4_000)

    def test_a_closer_matching_nothing_reports_its_error(self):
        self.assertEqual(self.errors("END_RUNG"), [(1, "END_RUNG without matching RUNG")])
        self.assertEqual(self.errors("NETWORK\nEND_RUNG\nEND_NETWORK"), [(2, "END_RUNG without matching RUNG")])

    def test_a_matched_closer_closes_its_block(self):
        self.assertEqual(self.errors("NETWORK\nRUNG\nEND_RUNG\nEND_NETWORK"), [])
        self.assertEqual(self.errors("NETWORK\nEND_NETWORK\nEND_NETWORK"), [(3, "END_NETWORK without matching NETWORK")])
        self.assertEqual(self.errors("RUNG RUNG END_RUNG END_RUNG END_RUNG"), [(1, "END_RUNG without matching RUNG")])

    def test_a_closer_closes_the_blocks_inside_its_own_and_none_more(self):
        got = self.errors("NETWORK\nRUNG\nEND_NETWORK\nEND_RUNG\nEND_NETWORK")
        self.assertEqual(got, [
            (2, "RUNG opened at line 2 is not closed before END_NETWORK"),
            (4, "END_RUNG without matching RUNG"),
            (5, "END_NETWORK without matching NETWORK"),
        ])

    def test_blocks_left_open_are_reported_at_the_end(self):
        self.assertEqual(self.errors("NETWORK\nRUNG\nEND_RUNG"), [(1, "NETWORK opened here is never closed")])


class LogixRungOperands(LinearTime):
    """Operands of every instruction are read in one pass, not by rescanning from each `NAME(`."""

    # (text for n, small n, big n). Nested and unclosed instructions rescanned the rest of the rung
    # per `(`; a long identifier rescanned its run from every character; sequential instructions with
    # commas must not search all commas at their depth.
    INPUTS = {
        "n nested instructions": (lambda n: "XIC(" * n + ")" * n + ";", 300, 1_200),
        "n unclosed instructions": (lambda n: "XIC(" * n + ";", 300, 1_200),
        "one identifier of n characters": (lambda n: "a" * n + ";", 2_500, 10_000),
        "n sequential instructions with commas": (lambda n: "XIC(a,b)" * n + ";", 3_000, 12_000),
    }

    def warnings(self, text: str) -> list[str]:
        return [f.message for f in check_rung(text, 1, "r")[0] if f.code == "LX022"]

    def test_check_time_grows_linearly_with_the_rung_length(self):
        for name, (make, small, big) in self.INPUTS.items():
            with self.subTest(name):
                self.assert_linear(lambda n, make=make: (lambda text=make(n): check_rung(text, 1, "r")), small, big)

    def test_operands_are_counted_at_the_instruction_s_own_bracket_depth(self):
        self.assertEqual(self.warnings("XIC(a);XIO(b);"), [])
        self.assertEqual(self.warnings("XIC(a,b);"), ["XIC takes 1 operand(s), found 2"])
        self.assertEqual(self.warnings("MOV(a,,b);"), ["MOV takes 2 operand(s), found 3"])
        self.assertEqual(self.warnings("COP([a,b],c,d);"), [])  # a comma inside [ ] separates nothing
        self.assertEqual(self.warnings("XIC(MOV(a,b));"), [])  # nor does one inside a nested instruction
        self.assertEqual(self.warnings("XIC(MOV(a,b,c));"), ["MOV takes 2 operand(s), found 3"])
        self.assertEqual(self.warnings("XIC(a));"), [])  # a stray ) closes nothing
        self.assertEqual(self.warnings("MOV(ABS(x),y);"), [])  # the comma after a nested call is at the outer depth
        self.assertEqual(self.warnings("MOV(ABS(x),y,z);"), ["MOV takes 2 operand(s), found 3"])
        self.assertEqual(self.warnings("MOV(ABS(ABS(x)),y);"), [])
        self.assertEqual(self.warnings("MOV(x,ABS(y));XIC(a);"), [])  # depth returns to 0 after each instruction

    def test_blank_operands_count_as_none(self):
        self.assertEqual(self.warnings("XIC();"), ["XIC takes 1 operand(s), found 0"])
        self.assertEqual(self.warnings("XIC( , );"), ["XIC takes 1 operand(s), found 0"])
        self.assertEqual(self.warnings("MOV(a, );"), [])  # one blank part among others still counts
        self.assertEqual(self.warnings("XIC(,a);"), ["XIC takes 1 operand(s), found 2"])  # a comma right after the `(`

    def test_an_instruction_without_its_closing_parenthesis_drops_the_last_character(self):
        # How the checker has always read `XIC(a,b` (operands "a,"): pinned, not endorsed.
        self.assertEqual(self.warnings("XIC(a,b"), ["XIC takes 1 operand(s), found 2"])
        self.assertEqual(self.warnings("XIC(a"), ["XIC takes 1 operand(s), found 0"])
        self.assertEqual(self.warnings("XIC(a,"), [])  # the dropped last character is the comma: one operand, `a`
        self.assertEqual(self.warnings("XIC(a,,"), ["XIC takes 1 operand(s), found 2"])
        self.assertEqual(self.warnings("XIC("), ["XIC takes 1 operand(s), found 0"])

    def test_the_mnemonic_skips_leading_digits(self):
        self.assertEqual(self.warnings("12XIC(a,b);"), ["XIC takes 1 operand(s), found 2"])
        self.assertEqual(self.warnings("9(a,b);"), [])

    def test_output_coil_operands_are_the_first_operand_stripped(self):
        self.assertEqual(check_rung("XIC(a)OTE(b);", 1, "r")[1], ["b"])
        self.assertEqual(check_rung("OTE( x [1] , y );", 1, "r")[1], ["x [1]"])
        self.assertEqual(check_rung("ote(a);", 1, "r")[1], ["a"])
        self.assertEqual(check_rung("OTE( , a);", 1, "r")[1], [""])  # as before: an empty first operand is kept
        self.assertEqual(check_rung("OTE( );", 1, "r")[1], [])

    def test_an_operand_holding_an_instruction_is_not_a_coil(self):
        # A copy of every enclosing operand grew with the square of the nesting depth (20 KB of
        # `OTE(` held 50 MB of operands). An operand that holds another `NAME(` is a call, not a tag.
        self.assertEqual(check_rung("OTE(OTE(a));", 1, "r")[1], ["a"])
        self.assertEqual(check_rung("OTE(a(b),c);", 1, "r")[1], [])
        self.assertEqual(check_rung("OTE(12XIC(a));", 1, "r")[1], [])
        self.assertEqual(check_rung("OTE(a, OTE(b));", 1, "r")[1], ["a", "b"])  # a first operand ends at its comma
        self.assertEqual(check_rung("OTE(a(", 1, "r")[1], ["a"])  # the unclosed text drops its last character, the `(`
        self.assertEqual(check_rung("OTE(a()", 1, "r")[1], [])  # here the dropped last character is a `)`: `a(` is inside
        self.assertEqual(check_rung("OTE(" * 400 + ")" * 400 + ";", 1, "r")[1], [])

    def test_a_parenthesis_that_starts_no_instruction_keeps_the_operand(self):
        # Whether Logix accepts a parenthesised subscript is not verified; the checker must not
        # lose the double-coil warning for it (v0.2.1 kept these operands).
        self.assertEqual(check_rung("OTE((a));", 1, "r")[1], ["(a)"])
        self.assertEqual(check_rung("OTE(Arr[(i+1)]);", 1, "r")[1], ["Arr[(i+1)]"])
        self.assertEqual(check_rung("OTE(Arr[(i+1)],b);", 1, "r")[1], ["Arr[(i+1)]"])

    def test_memory_grows_linearly_with_the_nesting_depth(self):
        # About 2 MB for 5000 nested `OTE(` (the lists indexed by character); the operand copies
        # the rescan kept were 50 MB.
        for text in ("OTE(" * 5_000, "OTE(" * 5_000 + ")" * 5_000 + ";"):
            tracemalloc.start()
            try:
                check_rung(text, 1, "r")
                peak = tracemalloc.get_traced_memory()[1]
            finally:
                tracemalloc.stop()
            self.assertLess(peak, 10_000_000)


if __name__ == "__main__":
    unittest.main()
