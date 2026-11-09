"""Hostile and damaged input, and the CLI contracts around it, tested on SYNTHETIC projects only.

A reader handed a file it did not write must answer with a message and an exit code, never a
traceback or a hang: damaged or encrypted zip entries, an entry that inflates past the cap, an
XML entity declaration in any encoding, and declarations that make a regex backtrack.
"""

from __future__ import annotations

import dataclasses
import os
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE))

import codesys_project  # noqa: E402
from codesysproj import buildinfo, diff, project, stscan, xref, zipread  # noqa: E402
from codesys_synth import (  # noqa: E402
    Synthetic, build_version, decl_only_payload, devices_meta_xml, guid, make_object, st_payload,
)
from test_codesys_tools import run_cli  # noqa: E402


def _entry_data_offset(path: str, name: str) -> int:
    with zipfile.ZipFile(path) as z:
        info = z.getinfo(name)
    with open(path, "rb") as f:
        f.seek(info.header_offset)
        header = f.read(30)
    name_len, extra_len = struct.unpack_from("<HH", header, 26)
    return info.header_offset + 30 + name_len + extra_len


def _corrupt_entry(path: str, name: str) -> None:
    """Flip bytes inside the entry's compressed data: the inflate or the CRC check then fails."""
    start = _entry_data_offset(path, name)
    with open(path, "r+b") as f:
        f.seek(start + 2)
        chunk = f.read(4)
        f.seek(start + 2)
        f.write(bytes(b ^ 0xFF for b in chunk))


def _mark_encrypted(path: str, name: str) -> None:
    """Set the 'encrypted' flag of the entry's central-directory record."""
    data = bytearray(Path(path).read_bytes())
    at = data.index(b"PK\x01\x02")
    while True:
        name_len = struct.unpack_from("<H", data, at + 28)[0]
        if data[at + 46:at + 46 + name_len].decode() == name:
            data[at + 8] |= 0x01
            break
        extra_len, comment_len = struct.unpack_from("<HH", data, at + 30)
        at += 46 + name_len + extra_len + comment_len
    Path(path).write_bytes(bytes(data))


class Project(unittest.TestCase):
    """Two ST POUs; damage one entry and the other must still be listed."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "p.project")
        s = Synthetic()
        t = s.t
        self.good = s.add("Good", guid(0), lambda g: make_object(st_payload(t, g, "PROGRAM Good", "x := 1;" * 40)))
        self.bad = s.add("Bad", guid(0), lambda g: make_object(st_payload(t, g, "PROGRAM Bad", "y := 2;" * 40)))
        s.write(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def assert_bad_object_is_a_problem(self):
        code, out, err = run_cli("list", self.path)
        self.assertEqual(code, codesys_project.EXIT_PROBLEMS)
        self.assertIn(self.good, out)
        self.assertRegex(err, r"PROBLEM %s \(Bad\): object: entry .* could not be read" % self.bad)
        loaded = project.load_project(self.path)
        self.assertEqual((loaded.objects[self.good].kind, loaded.objects[self.bad].kind),
                         (project.KIND_ST, project.KIND_UNREADABLE))

    def test_a_corrupt_object_entry_is_that_objects_problem(self):
        _corrupt_entry(self.path, self.bad + ".object")
        self.assert_bad_object_is_a_problem()

    def test_an_encrypted_object_entry_is_that_objects_problem(self):
        _mark_encrypted(self.path, self.bad + ".object")
        self.assert_bad_object_is_a_problem()

    def test_a_corrupt_string_table_is_fatal(self):
        _corrupt_entry(self.path, project.STRING_TABLE_NAME)
        code, _, err = run_cli("list", self.path)
        self.assertEqual(code, codesys_project.EXIT_FATAL)
        self.assertIn("could not be read", err)

    def test_an_object_past_the_cap_is_that_objects_problem_and_a_string_table_past_it_is_fatal(self):
        s = Synthetic()
        t = s.t
        good = s.add("Good", guid(0), lambda g: make_object(st_payload(t, g, "PROGRAM Good", "x;")))
        big = s.add("Big", guid(0), raw=b"\x00" * 50000)  # deflates to almost nothing
        s.write(self.path)
        with mock.patch.object(zipread, "ENTRY_CAP", 20000):  # above the string table, below Big
            loaded = project.load_project(self.path)
        self.assertEqual((loaded.objects[good].kind, loaded.objects[big].kind), (project.KIND_ST, project.KIND_UNREADABLE))
        self.assertIn("inflates past 20000 bytes", loaded.objects[big].problems[0])
        self.assertNotIn(big, loaded.blobs)
        with mock.patch.object(zipread, "ENTRY_CAP", 100):
            code, _, err = run_cli("list", self.path)
        self.assertEqual(code, codesys_project.EXIT_FATAL)
        self.assertIn("inflates past 100 bytes", err)

    def test_objects_past_the_total_cap_are_fatal(self):
        with mock.patch.object(zipread, "TOTAL_CAP", 50):  # each object is 43 bytes: the second crosses it
            code, _, err = run_cli("list", self.path)
        self.assertEqual(code, codesys_project.EXIT_FATAL)
        self.assertIn("inflate past 50 bytes in total", err)
        with mock.patch.object(zipread, "TOTAL_CAP", 86):  # exactly both objects: still read
            self.assertEqual(run_cli("list", self.path)[0], 0)

    def test_the_cap_reads_an_entry_of_exactly_the_cap(self):
        with zipfile.ZipFile(self.path) as z:
            info = z.getinfo(self.good + ".object")
            self.assertEqual(len(zipread.read_entry(z, info, cap=info.file_size)), info.file_size)
            with self.assertRaises(project.FormatError):
                zipread.read_entry(z, info, cap=info.file_size - 1)

    def test_a_utf8_flagged_entry_name_that_is_not_utf8_is_fatal_not_a_traceback(self):
        data = bytearray(Path(self.path).read_bytes())
        at = data.index(b"PK\x01\x02")
        data[at + 8] |= 0x08  # flag bit 11 lives in the high byte: set it there
        data[at + 9] |= 0x08
        data[at + 46] = 0xFF  # first byte of the entry name: invalid UTF-8
        Path(self.path).write_bytes(bytes(data))
        code, _, err = run_cli("list", self.path)
        self.assertEqual(code, codesys_project.EXIT_FATAL)
        self.assertIn("not a readable zip archive", err)


class DeclarationKeyword(unittest.TestCase):
    def test_a_commented_out_declaration_does_not_backtrack(self):
        text = "(* x : INT; *)\n" * 60
        start = time.perf_counter()
        self.assertIsNone(project.declaration_keyword(text))
        self.assertIsNotNone(project.declaration_keyword(text + "PROGRAM P"))
        self.assertLess(time.perf_counter() - start, 1.0)

    def test_a_keyword_after_comments_and_pragmas_is_found(self):
        self.assertEqual(project.declaration_keyword("(* a *) // b\n{attribute 'x'}\nFUNCTION_BLOCK F"), "FUNCTION_BLOCK")


class Info(unittest.TestCase):
    def info_of(self, devices_xml: bytes):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "i.project")
            Synthetic().write(path, extra={buildinfo.DEVICES_ENTRY: devices_xml})
            return buildinfo.read_info(path)

    def test_an_entity_declaration_is_refused_in_utf16_too(self):
        doc = '<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE d [<!ENTITY e "x">]><Devices><Device>' \
              '<Data Key="Name">&e;</Data></Device></Devices>'
        for data in (doc.replace("UTF-16", "utf-8").encode("utf-8"), doc.encode("utf-16")):
            info = self.info_of(data)
            self.assertEqual(info.devices, [])
            self.assertIn("DOCTYPE or ENTITY", " ".join(info.notes))

    def test_a_plain_document_is_still_read(self):
        info = self.info_of(devices_meta_xml([("Ctrl", [("App", "ab000000-0000-0000-0000-000000000000", None)])]))
        self.assertEqual([d.name for d in info.devices], ["Ctrl"])
        self.assertEqual(info.notes, [])

    def test_a_devices_entry_with_no_device_is_a_note(self):
        info = self.info_of(b'<?xml version="1.0"?><Devices/>')
        self.assertIn("no <Device> element", " ".join(info.notes))

    def test_a_non_ascii_digit_save_counter_is_not_a_number(self):
        root = buildinfo.ET.fromstring('<Configuration><History><HistoryEntry SaveCounter="²" '
                                       'LastTimeSaved="2020-01-02-03-04-05"/></History></Configuration>')
        info = buildinfo.ProjectInfo()
        buildinfo._newest_save(root, info)
        self.assertEqual((info.last_saved, info.save_counter), ("2020-01-02 03:04:05", None))


class Versions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.old = os.path.join(cls.tmp.name, "v1.project")
        cls.new = os.path.join(cls.tmp.name, "v2.project")
        cls.ids = build_version(cls.old, 1)
        build_version(cls.new, 2)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_a_renamed_pou_is_found_by_its_old_and_its_new_name(self):
        for name in ("OldName", "NewName"):
            code, out, err = run_cli("diff", self.old, self.new, name)
            self.assertEqual((code, err), (0, ""), name)
            self.assertIn("# renamed: 'OldName' -> 'NewName'", out)

    def test_a_pou_missing_on_one_side_names_that_side(self):
        self.assertRegex(run_cli("diff", self.old, self.new, "Gone")[2], r"is not in NEW .*: it was removed")
        self.assertRegex(run_cli("diff", self.old, self.new, "Fresh")[2], r"is not in OLD .*: it was added")
        self.assertIn("not found in OLD", run_cli("diff", self.old, self.new, "Nowhere")[2])

    def test_the_headers_carry_each_versions_own_name(self):
        old_p, new_p = project.load_project(self.old), project.load_project(self.new)
        a = old_p.objects[self.ids["renamed"]]
        b = dataclasses.replace(new_p.objects[self.ids["renamed"]], implementation="changed;")
        lines = diff.object_diff(old_p, a, new_p, b).sections[0].lines
        self.assertEqual(lines[:2], ["--- OLD OldName implementation", "+++ NEW NewName implementation"])


class ProblemsAndNotes(unittest.TestCase):
    def test_a_note_is_printed_even_when_an_object_has_a_problem(self):
        from codesys_synth import graphical_payload, network, vi
        bad = b"\x0f\xdf\x02" + vi(9999)  # element whose name index is not in the string table
        with tempfile.TemporaryDirectory() as tmp:
            paths = [os.path.join(tmp, "n%d.project" % n) for n in (1, 2)]
            for path in paths:
                s = Synthetic()
                s.add("G", guid(0), lambda g, s=s: make_object(graphical_payload(
                    s.t, g, network(s.t, "c", bad), "PROGRAM G\nVAR\nEND_VAR")))
                s.add("NoMeta", guid(0), lambda g, s=s: make_object(st_payload(s.t, g, "PROGRAM N", "x;")), meta=False)
                s.write(path)
            code, _, err = run_cli("diff", *paths)
        self.assertEqual(code, codesys_project.EXIT_PROBLEMS)
        self.assertIn("NOTE ", err)
        self.assertIn("could not be decoded", err)
        self.assertRegex(err, r"PROBLEM OLD .*no \.meta entry")
        self.assertRegex(err, r"PROBLEM NEW .*no \.meta entry")

    def test_a_problem_only_in_one_version_is_reported_with_its_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for n, cut in ((1, False), (2, True)):
                s = Synthetic()
                t = s.t
                obj = make_object(st_payload(t, guid(1), "PROGRAM P", "x;"))
                s.add("P", guid(0), raw=obj[:-3] if cut else obj)
                paths.append(os.path.join(tmp, "v%d.project" % n))
                s.write(paths[-1])
            code, _, err = run_cli("diff", *paths)
            code_rev, _, err_rev = run_cli("diff", *reversed(paths))
        self.assertEqual((code, code_rev), (codesys_project.EXIT_PROBLEMS,) * 2)
        self.assertIn("PROBLEM NEW ", err)
        self.assertNotIn("PROBLEM OLD ", err)
        self.assertIn("PROBLEM OLD ", err_rev)
        self.assertNotIn("PROBLEM NEW ", err_rev)


class StForDeclarations(unittest.TestCase):
    def test_a_gvl_declaration_prints_and_has_no_implementation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "g.project")
            s = Synthetic()
            t = s.t
            s.add("Vars", guid(0), lambda g: make_object(decl_only_payload(t, g, "VAR_GLOBAL\n\tg : INT;\nEND_VAR")))
            s.write(path)
            code, out, _ = run_cli("st", path, "Vars")
            self.assertEqual(code, 0)
            self.assertIn("g : INT;", out)
            self.assertNotIn("(* implementation", out)
            self.assertEqual(run_cli("st", path, "Vars", "--decl")[0], 0)
            code, _, err = run_cli("st", path, "Vars", "--impl")
        self.assertEqual(code, codesys_project.EXIT_FATAL)
        self.assertIn("declaration only", err)


class ListJson(unittest.TestCase):
    def test_every_record_carries_the_full_key_set(self):
        rec = project.ObjectRecord(guid=guid(1))
        self.assertEqual(set(codesys_project.record_dict(rec)), {
            "guid", "name", "kind", "subtype", "language", "path", "device", "application", "parent_guid", "problems"})


class ConsoleEncoding(unittest.TestCase):
    def test_a_non_ascii_comment_prints_on_a_cp1252_console(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "e.project")
            s = Synthetic()
            t = s.t
            s.add("P", guid(0), lambda g: make_object(st_payload(t, g, "PROGRAM P // đ č 中", "x;")))
            s.write(path)
            env = dict(os.environ, PYTHONIOENCODING="cp1252", PYTHONDONTWRITEBYTECODE="1")
            proc = subprocess.run([sys.executable, str(HERE.parent / "scripts" / "codesys_project.py"), "st", path, "P"],
                                  capture_output=True, env=env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(b"\\u4e2d", proc.stdout)


class Survivors(unittest.TestCase):
    """One test per guard a mutant showed no test pinned."""

    def test_a_varint_of_ten_bytes_reads_and_one_of_eleven_does_not(self):
        from codesysproj.binary import read_varint
        self.assertEqual(read_varint(b"\x80" * 9 + b"\x01", 0), (1 << 63, 10))
        with self.assertRaises(project.FormatError):
            read_varint(b"\x80" * 10 + b"\x01", 0)

    def test_two_slots_with_the_same_text_are_not_a_problem_and_different_text_is(self):
        from codesys_synth import Table, slot
        for second, expected in (("PROGRAM P", 0), ("PROGRAM Q", 1)):
            t = Table()
            g = guid(1)
            data = make_object(slot(t, g, "PROGRAM P", False) + slot(t, g, second, False) + slot(t, g, "x;", True))
            rec = project.ObjectRecord(guid=g)
            project.classify_object(rec, data, dict(enumerate(t.texts)))
            self.assertEqual((rec.declaration, len(rec.problems)), ("PROGRAM P", expected), second)

    def test_every_var_section_alone_is_a_gvl(self):
        from codesys_synth import Table
        for keyword in ("VAR_GLOBAL", "VAR_CONFIG", "VAR"):
            t = Table()
            rec = project.ObjectRecord(guid=guid(1))
            project.classify_object(rec, make_object(decl_only_payload(t, rec.guid, keyword + "\n\tv : INT;\nEND_VAR")),
                                    dict(enumerate(t.texts)))
            self.assertEqual((rec.kind, rec.subtype), (project.KIND_GVL, keyword))

    def test_a_guid_and_a_name_resolve_in_any_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "c.project")
            s = Synthetic()
            g = s.add("Motor", guid(0), lambda g: make_object(st_payload(s.t, g, "PROGRAM Motor", "x;")))
            s.write(path)
            loaded = project.load_project(path)
        for query in (g.upper(), g[:9].upper(), "MOTOR", "motor"):
            self.assertEqual([r.guid for r in project.find_objects(loaded, query)], [g], query)

    def test_a_kind_change_is_compared_and_flagged_in_both_directions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "v.project")
            ids = build_version(path, 1)
            old_p = project.load_project(path)
        ladder, st = old_p.objects[ids["ladder"]], old_p.objects[ids["edited"]]
        for a, b in ((ladder, st), (st, ladder)):
            result = diff.object_diff(old_p, a, old_p, b)
            self.assertIn("graph", [sec.label for sec in result.sections])
            text = diff.render_object_diff(result)
            self.assertIn("# kind changed: %s -> %s" % (a.kind, b.kind), text)
            self.assertIn(diff.LIMITS_NOTE, text)

    def test_a_stable_label_keeps_the_coil_count(self):
        from codesysproj.graph import Item
        from codesysproj.graphview import item_label
        self.assertEqual(item_label(Item(0, "coils", {"count": 3}), stable=True), "coils count=3")
        self.assertEqual(item_label(Item(0, "empty", {"slot_id": 9}), stable=True), "empty")


def _hits(decl=None, impl=None, query="x", kind=project.KIND_ST, name="Owner"):
    rec = project.ObjectRecord(guid=guid(1), name=name, kind=kind, declaration=decl, implementation=impl)
    proj = project.Project(path="", strings={}, objects={rec.guid: rec}, blobs={})
    return [(h.where, h.role, h.text) for h in xref.find_references(proj, query).hits]


class XrefNames(unittest.TestCase):
    def test_a_non_ascii_identifier_is_scanned_not_a_crash(self):
        impl = "caf\u00e9 := 1;\na.\u00e9 := 2;\n\u010d_start := caf\u00e9;"
        self.assertEqual([h[:2] for h in _hits(impl=impl, query="caf\u00e9")],
                         [("implementation:1", "write"), ("implementation:3", "read")])
        self.assertEqual([h[:2] for h in _hits(impl=impl, query="a.\u00e9")], [("implementation:2", "write")])
        self.assertEqual(stscan.scan_paths("\u00b2 + 1"), [])  # a superscript digit is a number, not a name

    def test_every_name_of_a_multi_line_list_is_declared(self):
        decl = "VAR\n\ta,\n\tb : INT;\n\tc\n\t: BOOL;\nEND_VAR"
        for query, line in (("a", 2), ("b", 3), ("c", 4)):
            self.assertEqual([h[:2] for h in _hits(decl, query=query, kind=project.KIND_GVL)],
                             [("declaration:%d" % line, "declared")], query)

    def test_every_section_word_is_skipped(self):
        for word in sorted(xref._SECTION_WORDS):
            self.assertEqual([n for n, _ in xref._declared_names("%s CONSTANT n" % word.upper())], ["n"], word)

    def test_extends_and_implements_are_types(self):
        decl = "FUNCTION_BLOCK Fb EXTENDS Base IMPLEMENTS Iface, Other\nVAR\n\tm : INT;\nEND_VAR"
        for query in ("Base", "Iface", "Other"):
            self.assertEqual([h[:2] for h in _hits(decl, impl="", query=query)], [("declaration:1", "type")], query)
        self.assertEqual([h[:2] for h in _hits(decl, impl="", query="m")], [("declaration:3", "declared")])
        self.assertEqual(_hits(decl, impl="", query="extends"), [])
        struct = "TYPE T EXTENDS U :\nSTRUCT\n\tf : INT;\nEND_STRUCT\nEND_TYPE"
        self.assertEqual([h[:2] for h in _hits(struct, query="U", kind=project.KIND_DUT)], [("declaration:1", "type")])
        self.assertEqual([h[:2] for h in _hits(struct, query="f", kind=project.KIND_DUT)], [("declaration:3", "declared")])

    def test_an_inheritance_clause_on_its_own_line_is_types_not_a_declaration(self):
        for keyword in ("EXTENDS", "IMPLEMENTS"):
            decl = "FUNCTION_BLOCK P\n\t%s Base\nVAR\n\tx : INT;\nEND_VAR" % keyword
            self.assertEqual([h[:2] for h in _hits(decl, impl="", query="x")], [("declaration:4", "declared")], keyword)
            self.assertEqual([h[:2] for h in _hits(decl, impl="", query="Base")], [("declaration:2", "type")], keyword)
            self.assertEqual(_hits(decl, impl="", query=keyword), [], keyword)

    def test_a_pragma_line_before_the_header_leaves_the_header_intact(self):
        decl = "{attribute 'qualified_only'}\nFUNCTION Func : BOOL\nVAR_INPUT\n\tx : INT;\nEND_VAR"
        self.assertEqual([h[:2] for h in _hits(decl, impl="", query="Func")], [("declaration:2", "declared")])
        self.assertEqual([h[:2] for h in _hits(decl, impl="", query="BOOL")], [("declaration:2", "type")])
        self.assertEqual([h[:2] for h in _hits(decl, impl="", query="x")], [("declaration:4", "declared")])

    def test_an_initializer_is_read_and_the_type_is_a_type(self):
        decl = "VAR\n\tv : Lim := Lim;\nEND_VAR"
        self.assertEqual([h[:2] for h in _hits(decl, query="Lim", kind=project.KIND_GVL)],
                         [("declaration:2", "type"), ("declaration:2", "read")])

    def test_a_hit_carries_its_own_source_line(self):
        impl = "first;\n  y := x;  \nlast := x"
        self.assertEqual(_hits(impl=impl), [("implementation:2", "read", "y := x;"), ("implementation:3", "read", "last := x")])

    def test_a_quoted_constant_in_a_graph_element_is_not_a_name(self):
        from codesys_synth import element, graphical_payload, network
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "q.project")
            s = Synthetic()
            t = s.t
            items = element(t, "'abc counter'", "STRING", 0, 5111, is_input=True) + element(t, "counter", "INT", 0, 5222)
            s.add("G", guid(0), lambda g: make_object(graphical_payload(t, g, network(t, None, items),
                                                                        "PROGRAM G\nVAR\nEND_VAR")))
            s.write(path)
            hits = xref.find_references(project.load_project(path), "counter").hits
        self.assertEqual([h.text for h in hits], ["OUT 'counter'"])


if __name__ == "__main__":
    unittest.main()
