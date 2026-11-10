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

from plccheck.plcopen import check_iec61131_10  # noqa: E402
from plccheck.schneider import check_control_expert  # noqa: E402
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


if __name__ == "__main__":
    unittest.main()
