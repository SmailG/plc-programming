"""A crafted file must not make a checker spin or multiply its memory.

Each scaling test feeds a checker an input whose size grows 4x and asserts the CPU time grows
about 4x, not 16x (a rescan per element). Each semantics test beside it pins what the linear
version must keep returning on legitimate input.
"""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

from plccheck.logix import check_l5k  # noqa: E402
from plccheck.plcopen import check_iec61131_10  # noqa: E402
from plccheck.schneider import check_control_expert  # noqa: E402
from plccheck.simaticml import check_simatic_sd  # noqa: E402
from plccheck.twincat import _blank_spans, _strip_comments  # noqa: E402
from plccheck.xmlutil import parse_bytes  # noqa: E402


class LinearTime(unittest.TestCase):
    """Base class: the ratio helper."""

    RUNS = 3
    MAX_RATIO = 8
    TIMER_FLOOR = 0.01  # seconds; keeps the ratio meaningful if the small run is below timer noise

    def best_of_runs(self, run) -> float:
        best = float("inf")
        for _ in range(self.RUNS):
            start = time.process_time()
            run()
            best = min(best, time.process_time() - start)
        return best

    def assert_linear(self, make, small, big):
        """`make(n)` builds the input outside the timer and returns the thunk to time.

        A ratio, not an absolute bound, so a slow CI runner does not flake: both sizes slow down
        together. Process (CPU) time drops scheduler noise, and the best of three drops a run a
        hiccup inflated. Linear work lands near big/small, a rescan per element near its square.
        """
        run_small, run_big = make(small), make(big)
        t_small, t_big = self.best_of_runs(run_small), self.best_of_runs(run_big)
        self.assertLess(t_big, self.MAX_RATIO * max(t_small, self.TIMER_FLOOR),
                        f"size {small} took {t_small:.3f}s, size {big} took {t_big:.3f}s")


def xml_root(text: str):
    return parse_bytes(text.encode())


def xef(body: str) -> str:
    return f"<FEFExchangeFile><fileHeader/>{body}</FEFExchangeFile>"


class ControlExpertNestedDfb(LinearTime):
    """An STSource is linted once, for the nearest FBSource around it, not once per FBSource around it."""

    def nested(self, depth: int, st: str) -> str:
        return xef('<FBSource nameOfFBType="D">' * depth + f"<STSource>{st}</STSource>" + "</FBSource>" * depth)

    def test_lint_time_grows_linearly_with_depth_and_source_size_together(self):
        # Depth and ST length grow together: relinting the ST once per enclosing FBSource is
        # quadratic in the file size (about 16x for 4x), one lint per STSource is linear (about 4x).
        def make(n):
            root = xml_root(self.nested(n, "IF a THEN " * (10 * n)))
            return lambda: check_control_expert(root)
        self.assert_linear(make, 15, 60)

    def test_deeply_nested_dfb_reports_the_findings_of_a_single_lint(self):
        st = "IF a THEN "
        single = check_control_expert(xml_root(self.nested(1, st)))
        self.assertEqual(len(single), 1, single)
        self.assertEqual(check_control_expert(xml_root(self.nested(50, st))), single)

    def test_nested_st_source_belongs_to_the_nearest_dfb(self):
        root = xml_root(xef(
            '<FBSource nameOfFBType="Outer"><STSource>IF a THEN </STSource>'
            '<FBSource nameOfFBType="Inner"><STSource>FOR i := 1 TO 2 DO </STSource></FBSource></FBSource>'))
        got = sorted((f.code, f.context) for f in check_control_expert(root))
        self.assertEqual(got, [("ST002", "DFB Inner (ST)"), ("ST002", "DFB Outer (ST)")])

    def test_sibling_dfbs_keep_their_own_context_and_line(self):
        root = xml_root(xef(
            '<FBSource nameOfFBType="A">\n<STSource>IF a THEN </STSource></FBSource>\n'
            '<FBSource nameOfFBType="B">\n<STSource>FOR i := 1 TO 2 DO </STSource></FBSource>'))
        got = [(f.code, f.line, f.context) for f in check_control_expert(root)]
        self.assertEqual(got, [("ST002", 2, "DFB A (ST)"), ("ST002", 4, "DFB B (ST)")])


class Iec61131_10NestedBodies(LinearTime):
    """Connections and ids are collected in one pass, each for its nearest BodyContent."""

    def project(self, body: str) -> str:
        return f'<Project schemaVersion="1">{body}</Project>'

    def px121(self, body: str) -> list[tuple[str, int]]:
        found = check_iec61131_10(xml_root(self.project(body)))
        self.assertEqual({f.code for f in found}, {"PX121"} if found else set())
        return [(f.message.split()[4], f.line) for f in found]

    def test_check_time_grows_linearly_with_the_nesting_depth(self):
        # Scanning the whole subtree of every BodyContent for ids and Connection elements is
        # quadratic in the depth (about 16x for 4x); one walk is linear (about 4x).
        def make(n):
            root = xml_root(self.project('<BodyContent type="x:ST">' * n + "</BodyContent>" * n))
            return lambda: check_iec61131_10(root)
        self.assert_linear(make, 500, 2000)

    def test_a_missing_ref_warns_and_a_resolving_one_does_not(self):
        got = self.px121(
            '<BodyContent type="x:FBD">\n<Block connectionPointOutId="1"/>\n'
            '<Connection refConnectionPointOutId="1"/>\n<Connection refConnectionPointOutId="9"/></BodyContent>')
        self.assertEqual(got, [("9,", 4)])

    def test_ids_resolve_only_inside_their_own_body(self):
        got = self.px121(
            '<BodyContent><Block connectionPointOutId="1"/><Connection refConnectionPointOutId="2"/></BodyContent>\n'
            '<BodyContent><Block connectionPointOutId="2"/><Connection refConnectionPointOutId="1"/></BodyContent>')
        self.assertEqual(got, [("2,", 1), ("1,", 2)])

    def test_the_body_element_itself_and_deeper_elements_supply_ids(self):
        got = self.px121(
            '<BodyContent connectionPointOutId="1"><Pins><Pin connectionPointOutId="2"/></Pins>'
            '<Connection refConnectionPointOutId="1"/><Connection refConnectionPointOutId="2"/></BodyContent>')
        self.assertEqual(got, [])

    def test_elements_outside_any_body_are_ignored(self):
        got = self.px121('<Block connectionPointOutId="1"/><Connection refConnectionPointOutId="2"/>'
                         '<BodyContent><Connection refConnectionPointOutId="1"/></BodyContent>')
        self.assertEqual(got, [("1,", 1)])

    def test_nested_body_is_its_own_scope(self):
        # Not a valid structure; pinned so the scope is a decision, not an accident of the walk.
        got = self.px121(
            '<BodyContent><Connection refConnectionPointOutId="1"/>'
            '<BodyContent><Block connectionPointOutId="1"/><Connection refConnectionPointOutId="2"/></BodyContent>'
            '<Connection refConnectionPointOutId="3"/></BodyContent>')
        self.assertEqual(got, [("1,", 1), ("3,", 1), ("2,", 1)])


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
                self.assert_linear(lambda n, unit=unit: (lambda text=unit * n: _strip_comments(text)), small, big)

    def test_an_opener_without_a_closer_ends_the_scan(self):
        # The timing test cannot see a retry loop built on str.find (about 10x cheaper than a regex
        # retry, so below timer noise at a test-sized input), so count the searches directly.
        class CountingStr(str):
            calls = 0

            def find(self, *args):
                CountingStr.calls += 1
                return super().find(*args)

        text = CountingStr("(* " * 1000)
        self.assertEqual(_blank_spans(text, "(*", "*)"), text)
        self.assertEqual(CountingStr.calls, 2)  # one opener found, one failed closer search
        CountingStr.calls = 0
        _blank_spans(CountingStr("(* a *) " * 1000), "(*", "*)")
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
                self.assertEqual(_strip_comments(text), want)

    def test_an_opener_is_not_closed_by_its_own_characters(self):
        for text in ("(*)", "a (*) b", "/*/", "a /*/ b"):
            with self.subTest(text=text):
                self.assertEqual(_strip_comments(text), text)
        self.assertEqual(_strip_comments("(*)*)"), " ")
        self.assertEqual(_strip_comments("/*/*/"), " ")

    def test_openers_do_not_nest_and_passes_run_in_order(self):
        self.assertEqual(_strip_comments("(* (* *) *)"), "  *)")
        self.assertEqual(_strip_comments("(* // *)\nx"), " \nx")  # the (* *) pass runs before //
        self.assertEqual(_strip_comments("(* /* *) */"), "  */")  # (* *) first: it takes the /* inside
        self.assertEqual(_strip_comments("/* (* */ *)"), "/*  ")  # then /* */ finds nothing left to pair with
        self.assertEqual(_strip_comments("// (* \n *)"), " ")  # so the (* *) span crosses the line end
        self.assertEqual(_strip_comments("// x (* y\nz"), " \nz")  # an unclosed (* is left for the // pass
        self.assertEqual(_strip_comments("{ // }\nz"), "{  \nz")  # { } runs last: // already took the }
        self.assertEqual(_strip_comments("/* { */ }"), "  }")


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


if __name__ == "__main__":
    unittest.main()
