"""The shared XML parser refuses what multiplies its memory: a long namespace URI.

Expat copies a namespace URI into every element name and namespaced attribute name, so one
declaration of a long URI costs its length times the number of elements or attributes under it
(a 35 KB file reached 82 MB). Real URIs are short (the longest one the checkers know is 77
characters, a Siemens StructuredText namespace), so a declaration over MAX_NS_URI is refused.
"""

from __future__ import annotations

import sys
import tempfile
import tracemalloc
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import plc_validate  # noqa: E402
from plccheck import simaticml, xmlutil  # noqa: E402

SIEMENS_URI = simaticml.NS_BASE + "NetworkSource/StructuredText/v4"
CAP = 256
PEAK_LIMIT = 5_000_000  # bytes; the unfixed parser peaks at tens of MB on the shapes below
LONG_URI_ERROR = "namespace URI longer than 256 characters"
ENTITY_ERROR = "XML entity declarations are not supported"


def uri(length: int) -> str:
    return "http://x/" + "a" * (length - len("http://x/"))


class NamespaceUriCap(unittest.TestCase):
    def refused(self, data: bytes) -> xmlutil.XmlError:
        with self.assertRaises(xmlutil.XmlError) as ctx:
            xmlutil.parse_bytes(data)
        return ctx.exception

    def peak(self, data: bytes) -> int:
        tracemalloc.start()
        try:
            try:
                xmlutil.parse_bytes(data)
            except xmlutil.XmlError:
                pass
            return tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()

    def test_the_cap_is_well_above_the_longest_namespace_the_checkers_know(self):
        known = [simaticml.NS_BASE + f"{family}/{ver}" for exp in simaticml.EXPECTED_NS.values() for family, ver in exp.items()]
        self.assertEqual(max(map(len, known)), 77)
        self.assertEqual(xmlutil.MAX_NS_URI, CAP)

    def test_uris_up_to_the_cap_parse_and_longer_ones_are_refused(self):
        for length in (len(SIEMENS_URI), CAP):
            with self.subTest(length=length):
                root = xmlutil.parse_bytes(f'<r xmlns="{uri(length)}"><c/></r>'.encode())
                self.assertEqual((root.ns, root.children[0].ns), (uri(length), uri(length)))
        exc = self.refused(f'<r xmlns="{uri(CAP + 1)}"/>'.encode())
        self.assertEqual(str(exc), LONG_URI_ERROR)

    def test_a_prefixed_declaration_is_capped_too(self):
        self.assertEqual(xmlutil.parse_bytes(f'<r xmlns:p="{uri(CAP)}"><p:c/></r>'.encode()).children[0].ns, uri(CAP))
        self.assertEqual(str(self.refused(f'<r xmlns:p="{uri(CAP + 1)}"><p:c/></r>'.encode())), LONG_URI_ERROR)

    def test_a_long_value_of_an_attribute_that_only_starts_with_xmlns_is_not_a_declaration(self):
        for name in ("xmlnsx", "xmlns_p", "p:xmlns"):
            with self.subTest(attribute=name):
                self.assertEqual(xmlutil.parse_bytes(f'<r xmlns:p="{SIEMENS_URI}" {name}="{uri(300)}"/>'.encode()).tag, "r")

    def test_the_error_names_the_line_of_the_declaring_element(self):
        exc = self.refused(f'<r xmlns="{SIEMENS_URI}">\n<a>\n<b xmlns:q="{uri(CAP + 1)}"/></a></r>'.encode())
        self.assertEqual((str(exc), exc.line), (LONG_URI_ERROR, 3))

    def test_a_long_default_namespace_over_many_elements_is_refused_in_little_memory(self):
        # 36 KB: one 20,000-character URI, 4000 empty children (82 MB unfixed).
        data = f'<r xmlns="{uri(20_000)}">{"<c/>" * 4000}</r>'.encode()
        self.assertLess(len(data), 40_000)
        self.assertEqual(str(self.refused(data)), LONG_URI_ERROR)
        self.assertLess(self.peak(data), PEAK_LIMIT)

    def test_a_long_prefix_over_many_distinct_attributes_is_refused_in_little_memory(self):
        # The declaring element's own attributes each carry the URI too, so a cap in a namespace
        # declaration handler would come too late. 33 KB: one 16,000-character URI, 1200 attributes.
        attrs = " ".join(f'p:a{i}="1"' for i in range(1200))
        data = f'<r xmlns:p="{uri(16_000)}" {attrs}/>'.encode()
        self.assertLess(len(data), 40_000)
        self.assertEqual(str(self.refused(data)), LONG_URI_ERROR)
        self.assertLess(self.peak(data), PEAK_LIMIT)

    def test_the_cap_holds_in_utf16(self):
        # The check reads attribute values from the parser, so the encoding does not matter.
        data = f'<?xml version="1.0" encoding="utf-16"?><r xmlns="{uri(CAP + 1)}"/>'.encode("utf-16")
        self.assertEqual(str(self.refused(data)), LONG_URI_ERROR)
        ok = f'<?xml version="1.0" encoding="utf-16"?><r xmlns="{uri(CAP)}"/>'.encode("utf-16")
        self.assertEqual(xmlutil.parse_bytes(ok).ns, uri(CAP))

    def test_an_entity_in_a_namespace_value_is_refused_as_an_entity(self):
        # The first pass does not process namespaces but still expands entities in attribute values,
        # so it refuses entity declarations itself, before the entity can be expanded: one entity
        # whose value is over the cap would otherwise be reported as a long URI.
        data = f'<!DOCTYPE r [<!ENTITY e "{uri(CAP + 1)}">]>\n<r xmlns="&e;"/>'.encode()
        exc = self.refused(data)
        self.assertEqual((str(exc), exc.line), (ENTITY_ERROR, 1))

    def test_a_malformed_document_is_still_reported_by_the_parse(self):
        self.assertTrue(str(self.refused(b"<r><a></r>")).startswith("XML is not well-formed"))
        self.assertTrue(str(self.refused(b'<r xmlns="http://x/"><p:a/></r>')).startswith("XML is not well-formed"))  # unbound prefix

    def test_a_file_with_a_long_uri_is_an_xml001_finding(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "a.xml"
            path.write_text(f'<project xmlns="{uri(CAP + 1)}"/>', encoding="utf-8")
            fmt, findings = plc_validate.check_file(path, "plcopen")
        self.assertEqual((fmt, [(f.code, f.line, f.message) for f in findings]), ("plcopen", [("XML001", 1, LONG_URI_ERROR)]))


if __name__ == "__main__":
    unittest.main()
