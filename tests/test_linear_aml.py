"""A crafted AutomationML file must not make the checker spin: a PLCopen file linked from many interfaces.

Each scaling test feeds a checker an input whose size grows 4x and asserts the CPU time grows
about 4x, not 16x (a rescan per element). Each semantics test beside it pins what the linear
version must keep returning on legitimate input.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE))

from linear_support import LinearTime  # noqa: E402
from plccheck import aml  # noqa: E402
from plccheck.xmlutil import parse_bytes  # noqa: E402

class AmlLinkedFileParsing(LinearTime):
    """A PLCopen file linked from many interfaces is parsed and walked once, not once per link."""

    PLCOPEN = '<project><a globalId="g1"/><b uuid="u1"/></project>'

    def interface(self, i: int, ref: str, cls: str = "AMLBase/PLCopenXMLInterface") -> str:
        return (f'<ExternalInterface Name="i{i}" ID="x{i}" RefBaseClassPath="{cls}">'
                f'<Attribute Name="refURI"><Value>{ref}</Value></Attribute></ExternalInterface>')

    def aml_text(self, interfaces: list[str]) -> str:
        return ('<CAEXFile SchemaVersion="2.15"><InstanceHierarchy Name="h"><InternalElement Name="e" ID="e">'
                + "".join(interfaces) + "</InternalElement></InstanceHierarchy></CAEXFile>")

    def check(self, d: str, refs: list[str], files: dict[str, str] | None = None) -> list[tuple[str, str]]:
        base = Path(d)
        for name, text in {"plc.xml": self.PLCOPEN, **(files or {})}.items():
            (base / name).parent.mkdir(exist_ok=True)
            (base / name).write_text(text, encoding="utf-8")
        path = base / "plant.aml"
        path.write_text(self.aml_text([self.interface(i, ref) for i, ref in enumerate(refs)]), encoding="utf-8")
        return [(f.code, f.message) for f in aml.check_aml(parse_bytes(path.read_bytes()), path)]

    def test_check_time_grows_linearly_with_the_links_to_one_file(self):
        # Every link to the same file parsed it again, so n links to the file itself (n links
        # in it) cost n parses of an n-link document: quadratic (about 16x for 4x).
        with tempfile.TemporaryDirectory() as d:
            def make(n):  # one file per size: the thunks run after both are built
                path = Path(d) / f"plant{n}.aml"
                path.write_text(self.aml_text([self.interface(i, f"{path.name}#zzz") for i in range(n)]), encoding="utf-8")
                root = parse_bytes(path.read_bytes())
                return lambda: aml.check_aml(root, path)
            self.assert_linear(make, 80, 320)

    def test_a_file_linked_many_times_is_parsed_once_whatever_the_spelling_of_its_path(self):
        refs = ["plc.xml#zz", "./plc.xml#zz", "sub/../plc.xml#zz", "plc.xml#yy"]
        with tempfile.TemporaryDirectory() as d, mock.patch.object(aml, "parse_file", wraps=aml.parse_file) as parse:
            got = self.check(d, refs, {"sub/x.xml": "<x/>"})
        self.assertEqual(parse.call_count, 1)
        self.assertEqual([code for code, _ in got], ["AM012"] * 4)

    def test_a_malformed_file_is_parsed_once_and_gives_no_finding(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(aml, "parse_file", wraps=aml.parse_file) as parse:
            got = self.check(d, ["bad.xml#a", "bad.xml#b", "bad.xml#c"], {"bad.xml": "<project><a></project>"})
        self.assertEqual(parse.call_count, 1)
        self.assertEqual(got, [])

    def test_each_file_is_checked_for_its_own_fragments(self):
        files = {"other.xml": '<project><a globalId="g2"/></project>'}
        refs = ["plc.xml#g1", "plc.xml#u1", "plc.xml#g2", "other.xml#g2", "other.xml#g1", "missing.xml#g1"]
        with tempfile.TemporaryDirectory() as d:
            got = self.check(d, refs, files)
        # plc.xml has globalId g1 and uuid u1 but not g2; other.xml has g2 only; missing.xml is AM011
        self.assertEqual(got, [
            ("AM012", "refURI fragment #g2 matches no globalId in plc.xml"),
            ("AM012", "refURI fragment #g1 matches no globalId in other.xml"),
            ("AM011", "refURI target missing.xml not found next to this file"),
        ])

    def test_only_plcopen_links_with_a_fragment_are_followed(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(aml, "parse_file", wraps=aml.parse_file) as parse:
            base = Path(d)
            (base / "plc.xml").write_text(self.PLCOPEN, encoding="utf-8")
            (base / "plant.aml").write_text(self.aml_text([
                self.interface(0, "plc.xml", "AMLBase/PLCopenXMLInterface"),
                self.interface(1, "plc.xml#zz", "AMLBase/COLLADAInterface"),
            ]), encoding="utf-8")
            got = aml.check_aml(parse_bytes((base / "plant.aml").read_bytes()), base / "plant.aml")
        self.assertEqual((parse.call_count, got), (0, []))


if __name__ == "__main__":
    unittest.main()
