"""A crafted XML document must not make a checker spin or multiply its memory: Control Expert,
IEC 61131-10, L5X and SimaticML.

Each scaling test feeds a checker an input whose size grows 4x and asserts the CPU time grows
about 4x, not 16x (a rescan per element). Each semantics test beside it pins what the linear
version must keep returning on legitimate input.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE))

from linear_support import LinearTime, xef, xml_root  # noqa: E402
from plccheck.logix import check_l5x  # noqa: E402
from plccheck.plcopen import check_iec61131_10  # noqa: E402
from plccheck.schneider import check_control_expert  # noqa: E402
from plccheck.simaticml import check_simaticml  # noqa: E402

class ControlExpertNestedDfb(LinearTime):
    """An STSource is linted once, for the nearest FBSource around it, not once per FBSource around it.

    The shape is the one Control Expert writes: FBSource > FBProgram > STSource.
    """

    OPEN = '<FBSource nameOfFBType="{}"><FBProgram name="Main">'
    CLOSE = "</FBProgram></FBSource>"

    def dfb(self, name: str, *sources: str) -> str:
        return self.OPEN.format(name) + "".join(f"<STSource>{s}</STSource>" for s in sources) + self.CLOSE

    def nested(self, depth: int, st: str) -> str:
        return xef(self.OPEN.format("D") * depth + f"<STSource>{st}</STSource>" + self.CLOSE * depth)

    def check(self, body: str) -> list[tuple[str, int, str | None]]:
        return [(f.code, f.line, f.context) for f in check_control_expert(xml_root(xef(body)))]

    def test_lint_time_grows_linearly_with_depth_and_source_size_together(self):
        # Depth and ST length grow together: relinting the ST once per enclosing FBSource is
        # quadratic in the file size (about 16x for 4x), one lint per STSource is linear (about 4x).
        def make(n):
            root = xml_root(self.nested(n, "IF a THEN " * (10 * n)))
            return lambda: check_control_expert(root)
        self.assert_linear(make, 15, 60)

    def test_a_dfb_body_reports_its_unclosed_block_once_with_the_dfb_context(self):
        self.assertEqual(self.check(self.dfb("Pump", "IF a THEN ")), [("ST002", 1, "DFB Pump (ST)")])
        self.assertEqual(self.check(self.dfb("Pump", "IF a THEN x := 1; END_IF;")), [])

    def test_deeply_nested_dfb_reports_the_findings_of_a_single_lint(self):
        st = "IF a THEN "
        single = check_control_expert(xml_root(self.nested(1, st)))
        self.assertEqual(len(single), 1, single)
        self.assertEqual(check_control_expert(xml_root(self.nested(50, st))), single)

    def test_an_st_source_under_two_wrappers_is_found(self):
        got = self.check('<FBSource nameOfFBType="Deep"><FBProgram name="Main"><Section><STSource>IF a THEN </STSource></Section>'
                         "</FBProgram></FBSource>")
        self.assertEqual(got, [("ST002", 1, "DFB Deep (ST)")])

    def test_two_st_sources_of_one_dfb_are_reported_in_document_order(self):
        got = self.check(self.OPEN.format("Pump") + "\n<STSource>IF a THEN </STSource>\n<STSource>FOR i := 1 TO 2 DO </STSource>"
                         + self.CLOSE)
        self.assertEqual(got, [("ST002", 2, "DFB Pump (ST)"), ("ST002", 3, "DFB Pump (ST)")])

    def test_st_sources_of_sibling_wrappers_are_reported_in_document_order(self):
        got = self.check('<FBSource nameOfFBType="Pump">\n<FBProgram name="A"><STSource>IF a THEN </STSource></FBProgram>\n'
                         '<FBProgram name="B"><STSource>FOR i := 1 TO 2 DO </STSource></FBProgram></FBSource>')
        self.assertEqual(got, [("ST002", 2, "DFB Pump (ST)"), ("ST002", 3, "DFB Pump (ST)")])

    def test_nested_st_source_belongs_to_the_nearest_dfb(self):
        got = self.check(self.OPEN.format("Outer") + "<STSource>IF a THEN </STSource>"
                         + self.dfb("Inner", "FOR i := 1 TO 2 DO ") + self.CLOSE)
        self.assertEqual(sorted((code, ctx) for code, _, ctx in got), [("ST002", "DFB Inner (ST)"), ("ST002", "DFB Outer (ST)")])

    def test_sibling_dfbs_keep_their_own_context_and_line(self):
        got = self.check("\n" + self.dfb("A", "IF a THEN ") + "\n" + self.dfb("B", "FOR i := 1 TO 2 DO "))
        self.assertEqual(got, [("ST002", 2, "DFB A (ST)"), ("ST002", 3, "DFB B (ST)")])


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


class LogixL5xNestedRoutines(LinearTime):
    """A rung is checked for the routine it is in, not once for every routine around it."""

    def l5x(self, programs: str) -> str:
        return ('<RSLogix5000Content SchemaRevision="1" SoftwareRevision="1" TargetType="Controller">'
                f'<Controller><Programs>{programs}</Programs></Controller></RSLogix5000Content>')

    def routine(self, name: str, rungs: str, inner: str = "") -> str:
        return f'<Routine Name="{name}" Type="RLL"><RLLContent>{rungs}</RLLContent>{inner}</Routine>'

    def rung(self, number: int, text: str) -> str:
        return f'<Rung Number="{number}"><Text>{text}</Text></Rung>'

    def nested(self, depth: int, text: str) -> str:
        """`depth` routines, each in the <Routines> of the one before and each with one rung."""
        out = ""
        for _ in range(depth):
            out = self.routine("r", self.rung(0, text), f"<Routines>{out}</Routines>" if out else "")
        return self.l5x(f'<Program Name="p"><Routines>{out}</Routines></Program>')

    def check(self, programs: str) -> list[tuple[str, int, str | None]]:
        return [(f.code, f.line, f.context) for f in check_l5x(xml_root(self.l5x(programs)))]

    def test_check_time_grows_linearly_with_the_nesting_depth(self):
        # Rescanning the whole subtree of every routine for rungs is quadratic in the depth
        # (about 16x for 4x); one visit per rung is linear (about 4x).
        def make(n):
            root = xml_root(self.nested(n, "XIC(a);"))
            return lambda: check_l5x(root)
        self.assert_linear(make, 150, 600)

    def test_deeply_nested_routines_report_each_rung_once(self):
        found = check_l5x(xml_root(self.nested(50, "XIC(a)")))  # no ';': one LX020 per rung
        self.assertEqual([f.code for f in found], ["LX020"] * 50)

    def test_sibling_routines_keep_their_own_rungs_and_context(self):
        got = self.check('<Program Name="p"><Routines>\n' + self.routine("a", self.rung(0, "XIC(a)")) + "\n"
                         + self.routine("b", self.rung(0, "XIC(b)") + self.rung(1, "OTE(c)")) + "</Routines></Program>")
        self.assertEqual(got, [("LX020", 2, "p/a rung 0"), ("LX020", 3, "p/b rung 0"), ("LX020", 3, "p/b rung 1")])

    def test_rungs_are_reported_in_document_order(self):
        # Two children of one routine, each holding a rung, and two rungs in one child.
        rungs = lambda *texts: "".join(f'<Rung Number="{i}"><Text>{t}</Text></Rung>' for i, t in enumerate(texts))
        routine = ('<Routine Name="a" Type="RLL">\n<RLLContent>' + rungs("XIC(a)", "XIC(b)") + "</RLLContent>\n"
                   "<RLLContent>" + rungs("XIC(c)", "XIC(d)") + "</RLLContent></Routine>")
        got = self.check('<Program Name="p"><Routines>' + routine + "</Routines></Program>")
        self.assertEqual([(line, ctx) for _, line, ctx in got],
                         [(2, "p/a rung 0"), (2, "p/a rung 1"), (3, "p/a rung 0"), (3, "p/a rung 1")])

    def test_coils_are_counted_per_routines_scope(self):
        got = self.check('<Program Name="p"><Routines>' + self.routine("a", self.rung(0, "OTE(x);") + self.rung(1, "OTE(x);"))
                         + self.routine("b", self.rung(0, "OTE(x);")) + "</Routines></Program>")
        self.assertEqual(got, [("LX040", 1, "p")])

    def test_a_double_coil_on_a_parenthesised_subscript_is_found(self):
        two = self.routine("a", self.rung(0, "OTE(Arr[(i+1)]);") + self.rung(1, "OTE(Arr[(i+1)]);"))
        self.assertEqual(self.check('<Program Name="p"><Routines>' + two + "</Routines></Program>"), [("LX040", 1, "p")])

    def test_a_routine_nested_without_a_routines_wrapper_keeps_its_rungs_with_the_routine_around_it(self):
        # Only a <Routines> is visited as a scope of its own; a bare <Routine> inside a routine is not.
        got = self.check('<Program Name="p"><Routines>' + self.routine("a", self.rung(0, "XIC(a);")
                         + self.routine("bare", self.rung(1, "XIC(b)"))) + "</Routines></Program>")
        self.assertEqual(got, [("LX020", 1, "p/a rung 1")])

    def test_rungs_of_a_nested_routines_scope_belong_to_it(self):
        # Not a valid structure; pinned so the scope is a decision, not an accident of the walk.
        got = self.check('<Program Name="p"><Routines>' + self.routine("a", self.rung(0, "XIC(a)"),
                         "<Routines>" + self.routine("in", self.rung(0, "XIC(b)")) + "</Routines>") + "</Routines></Program>")
        self.assertEqual(got, [("LX020", 1, "p/a rung 0"), ("LX020", 1, "a/in rung 0")])


class SimaticMlNamespaces(LinearTime):
    """Each (family, version) namespace is reported once, at its first element, in document order."""

    BASE = "http://www.siemens.com/automation/Openness/SW/"

    def check(self, body: str, declarations: str = "") -> list[tuple[str, int, str]]:
        doc = f'<Document {declarations}><Engineering version="V18"/>{body}</Document>'
        return [(f.code, f.line, f.message) for f in check_simaticml(xml_root(doc)) if f.code == "SM003"]

    def test_check_time_grows_linearly_with_the_namespaces_and_elements_together(self):
        # k distinct namespaces over 10k elements: rebuilding the set of seen (family, version)
        # pairs for every element is k times m, quadratic when both grow (about 16x for 4x).
        def make(n):
            declarations = " ".join(f'xmlns:p{i}="{self.BASE}Interface/v{i + 10}"' for i in range(n))
            root = xml_root(f'<Document {declarations}><Engineering version="V18"/>'
                            + "".join(f"<p{i % n}:e/>" for i in range(10 * n)) + "</Document>")
            return lambda: check_simaticml(root)
        self.assert_linear(make, 250, 1_000)

    def test_a_namespace_is_reported_once_at_its_first_element(self):
        ns = f'xmlns="{self.BASE}NetworkSource/FlgNet/v3"'
        got = self.check(f"\n<a {ns}/>\n<b {ns}/>\n<c {ns}/>")
        self.assertEqual(got, [("SM003", 2, "NetworkSource/FlgNet namespace is v3 but TIA V18 exports use v4; import may be rejected")])

    def test_a_matching_namespace_is_not_reported(self):
        self.assertEqual(self.check(f'<a xmlns="{self.BASE}NetworkSource/FlgNet/v4"/><b xmlns="{self.BASE}Interface/v5"/>'), [])

    def test_namespaces_on_one_line_are_reported_in_document_order(self):
        # Ties on the line used to fall to the iteration order of a set, which changes with the hash seed.
        versions = [9, 1, 8, 2, 7, 3, 6, 4]  # none is v5, the version V18 expects of Interface
        got = self.check("".join(f'<a xmlns="{self.BASE}Interface/v{v}"/>' for v in versions))
        self.assertEqual([(line, msg.split()[3]) for _, line, msg in got], [(1, f"v{v}") for v in versions])


class SimaticMlNestedCompileUnits(LinearTime):
    """A network payload is checked for the CompileUnit it is in, not once for every CompileUnit around it."""

    UNIT = "SW.Blocks.CompileUnit"
    PART = '<FlgNet><Parts><Part UId="1"/></Parts></FlgNet>'
    DUP = '<FlgNet><Parts><Part UId="1"/><Part UId="1"/></Parts></FlgNet>'  # one SM020

    def unit(self, *payloads: str) -> str:
        """A CompileUnit with each payload under its NetworkSource, as TIA writes it."""
        return f"<{self.UNIT}>" + "".join(f"<NetworkSource>{p}</NetworkSource>" for p in payloads) + f"</{self.UNIT}>"

    def document(self, units: str) -> str:
        return ('<Document><Engineering version="V18"/><SW.Blocks.FB><AttributeList><Name>B</Name></AttributeList>'
                f"<ObjectList>{units}</ObjectList></SW.Blocks.FB></Document>")

    def nested(self, depth: int, payload: str) -> str:
        return self.document(f"<{self.UNIT}><NetworkSource>{payload}</NetworkSource>" * depth + f"</{self.UNIT}>" * depth)

    def check(self, units: str) -> list[tuple[str, int, str | None]]:
        return [(f.code, f.line, f.context) for f in check_simaticml(xml_root(self.document(units)))]

    def test_check_time_grows_linearly_with_the_nesting_depth(self):
        # Collecting the payloads of the whole subtree for every CompileUnit is quadratic in the
        # depth (about 16x for 4x); one visit per payload is linear (about 4x).
        def make(n):
            root = xml_root(self.nested(n, self.PART))
            return lambda: check_simaticml(root)
        self.assert_linear(make, 150, 600)

    def test_deeply_nested_compile_units_report_each_network_once(self):
        found = check_simaticml(xml_root(self.nested(50, self.DUP)))
        self.assertEqual([f.code for f in found], ["SM020"] * 50)

    def test_sibling_compile_units_are_separate_scopes(self):
        self.assertEqual(self.check(self.unit(self.PART) + self.unit(self.PART)), [])
        self.assertEqual(self.check(f"\n{self.unit(self.DUP)}\n{self.unit(self.PART)}"), [("SM020", 2, "SW.Blocks.FB B")])

    def test_networks_of_one_compile_unit_are_reported_in_document_order(self):
        dup = '<FlgNet><Parts><Part UId="1"/><Part UId="1"/></Parts></FlgNet>'
        got = self.check(f"<{self.UNIT}>\n<NetworkSource>{dup}</NetworkSource>\n<NetworkSource>{dup}</NetworkSource></{self.UNIT}>")
        self.assertEqual([line for _, line, _ in got], [2, 3])

    def test_payloads_of_one_wrapper_are_reported_in_document_order(self):
        dup = '<FlgNet><Parts><Part UId="1"/><Part UId="1"/></Parts></FlgNet>'
        got = self.check(f"<{self.UNIT}><NetworkSource>\n{dup}\n{dup}</NetworkSource></{self.UNIT}>")
        self.assertEqual([line for _, line, _ in got], [2, 3])

    def test_unresolved_references_and_nested_graph_payloads_keep_their_scopes(self):
        graph = ('<Graph><Parts><Part UId="1"/></Parts><FlgNet><Parts><Part UId="1"/></Parts>'
                 '<Wires><IdentCon UId="9"/></Wires></FlgNet></Graph>')
        self.assertEqual(self.check(self.unit(graph)), [("SM021", 1, "SW.Blocks.FB B")])

    def test_payloads_of_a_nested_compile_unit_belong_to_it(self):
        # Not a valid structure; pinned so the scope is a decision, not an accident of the walk. The
        # outer unit's payload reuses UId 1 with the inner one's and neither sees the other.
        inner = self.unit(self.DUP)
        self.assertEqual(self.check(f"<{self.UNIT}><NetworkSource>{self.PART}</NetworkSource>{inner}</{self.UNIT}>"),
                         [("SM020", 1, "SW.Blocks.FB B")])

    def test_a_compile_unit_inside_a_payload_does_not_lend_its_parts_to_it(self):
        part_in_unit = f'<Parts><Part UId="1"/></Parts><{self.UNIT}><Part UId="1"/></{self.UNIT}>'
        self.assertEqual(self.check(self.unit(f"<FlgNet>{part_in_unit}</FlgNet>")), [])


if __name__ == "__main__":
    unittest.main()
