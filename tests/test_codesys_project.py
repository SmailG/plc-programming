"""Reader for CODESYS 3.5 `.project` files, tested on SYNTHETIC projects only.

The projects are built here from the layout the reader documents (string table, `.meta`,
`.object`), with an encoder in codesys_synth.py and not in the reader. The format is
undocumented and reverse-engineered, so the tests pin the reader's own rules: every guard has
an input it must catch and a control it must accept. Names and text are invented.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))

import codesys_project  # noqa: E402
from codesysproj import export, graph, graphview, project  # noqa: E402
from codesysproj.binary import FormatError, parse_string_table, read_varint  # noqa: E402
from codesys_synth import (  # noqa: E402
    FILLER, Synthetic, Table, box, build_standard, coils, decl_only_payload, element, graphical_payload, guid,
    make_meta, make_object, network, qword, slot, st_payload, vi,
)

class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = os.path.join(cls.tmp.name, "std.project")
        cls.ids = build_standard(cls.path)
        cls.project = project.load_project(cls.path)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def rec(self, role):
        return self.project.objects[self.ids[role]]


class Varints(unittest.TestCase):
    def test_multi_byte_value(self):
        self.assertEqual(read_varint(vi(300) + b"\xff", 0), (300, 2))

    def test_truncated_varint_is_an_error_not_an_index_error(self):
        with self.assertRaises(FormatError):
            read_varint(b"\xac", 0)

    def test_overlong_varint_is_rejected_but_ten_bytes_pass(self):
        self.assertEqual(read_varint(vi(1 << 62), 0)[0], 1 << 62)  # 9 bytes
        with self.assertRaises(FormatError):
            read_varint(b"\x80" * 11 + b"\x01", 0)


class StringTable(unittest.TestCase):
    def test_round_trip(self):
        t = Table()
        t.add("héllo")
        parsed = parse_string_table(t.dump())
        self.assertEqual(parsed[FILLER], "héllo")
        self.assertEqual(len(parsed), FILLER + 1)

    def test_entry_longer_than_file_is_an_error(self):
        data = vi(1) + vi(0) + vi(50) + b"abc"
        with self.assertRaisesRegex(FormatError, "runs past the end"):
            parse_string_table(data)

    def test_declared_count_must_match(self):
        with self.assertRaisesRegex(FormatError, "declares"):
            parse_string_table(Table().dump(declared=FILLER + 3))

    def test_duplicate_index_is_an_error(self):
        with self.assertRaisesRegex(FormatError, "twice"):
            parse_string_table(vi(2) + vi(5) + vi(1) + b"a" + vi(5) + vi(1) + b"b")


class EntryNames(unittest.TestCase):
    def test_plain_and_directory_prefix(self):
        self.assertEqual(project._entry_name(zipfile.ZipInfo("a.meta")), "a.meta")
        self.assertEqual(project._entry_name(zipfile.ZipInfo("dir\\x.meta")), "x.meta")

    def test_gbk_bytes_and_flagged_utf8(self):
        gbk = zipfile.ZipInfo(b"\xc4\xe3.meta".decode("cp437"))
        self.assertEqual(project._entry_name(gbk), "你.meta")
        utf8 = zipfile.ZipInfo("é.meta")
        utf8.flag_bits |= 0x800
        self.assertEqual(project._entry_name(utf8), "é.meta")


class Meta(unittest.TestCase):
    def setUp(self):
        self.t = Table()
        self.own, self.parent = guid(1), guid(2)

    def test_parent_and_name(self):
        data = make_meta(self.t, self.own, self.parent, "Name")
        self.assertEqual(project.parse_meta(data, self.own, dict(enumerate(self.t.texts))), (self.parent, "Name"))

    def test_own_guid_repeated_still_gives_parent_and_name(self):
        data = make_meta(self.t, self.own, self.parent, "Name", repeat_own=True)
        self.assertEqual(project.parse_meta(data, self.own, dict(enumerate(self.t.texts))), (self.parent, "Name"))

    def test_own_guid_missing_is_an_error(self):
        data = make_meta(self.t, guid(9), self.parent, "Name")
        with self.assertRaisesRegex(FormatError, "own guid not found"):
            project.parse_meta(data, self.own, dict(enumerate(self.t.texts)))

    def test_parent_must_be_guid_shaped(self):
        data = make_meta(self.t, self.own, "not-a-guid", "Name")
        with self.assertRaisesRegex(FormatError, "not followed by a parent guid"):
            project.parse_meta(data, self.own, dict(enumerate(self.t.texts)))

    def test_name_index_outside_the_table_is_an_error(self):
        data = bytes([2]) + self.t.v(self.own) + self.t.v(self.parent) + vi(99999)
        with self.assertRaisesRegex(FormatError, "not followed by a parent guid"):
            project.parse_meta(data, self.own, dict(enumerate(self.t.texts)))

    def test_stream_ending_right_after_own_guid_is_an_error(self):
        data = bytes([2]) + self.t.v(self.own)
        with self.assertRaisesRegex(FormatError, "not followed by a parent guid"):
            project.parse_meta(data, self.own, dict(enumerate(self.t.texts)))


class ObjectHeader(Base):
    def classify(self, data, owner=None):
        rec = project.ObjectRecord(guid=owner or guid(77))
        project.classify_object(rec, data, self.project.strings)
        return rec

    def test_short_object_is_reported(self):
        rec = self.classify(b"\x02\x20\x09")
        self.assertEqual(rec.kind, "unreadable")
        self.assertIn("shorter than", rec.problems[0])

    def test_bad_magic_is_reported(self):
        rec = self.classify(b"\xff" + make_object(b"\x01\x02")[1:])
        self.assertEqual((rec.kind, "magic" in rec.problems[0]), ("unreadable", True))

    def test_length_field_mismatch_is_reported_for_a_truncated_object(self):
        rec = self.classify(make_object(b"\x01\x02\x03\x04")[:-2])
        self.assertEqual(rec.kind, "unreadable")
        self.assertIn("truncated or corrupt", rec.problems[0])

    def test_well_formed_object_with_no_slots_is_other_without_problems(self):
        rec = self.classify(make_object(b"\x0f\x01\x02\x03"))
        self.assertEqual((rec.kind, rec.problems), ("other", []))


class TextSlots(unittest.TestCase):
    def setUp(self):
        self.t = Table()
        self.owner = guid(5)

    def classify(self, payload):
        rec = project.ObjectRecord(guid=self.owner)
        project.classify_object(rec, make_object(payload), dict(enumerate(self.t.texts)))
        return rec

    def test_st_text_is_read_with_line_endings_intact(self):
        rec = self.classify(st_payload(self.t, self.owner, "PROGRAM P\r\nVAR\r\nEND_VAR", "a := 1;\r\n"))
        self.assertEqual((rec.kind, rec.declaration, rec.implementation),
                         ("st", "PROGRAM P\r\nVAR\r\nEND_VAR", "a := 1;\r\n"))

    def test_marker_with_the_wrong_back_reference_is_ignored(self):
        decoy = b"\x41\xe5\x02" + self.t.v("DECOY TEXT") + self.t.v(guid(99) + "_Decl_LineIds")
        rec = self.classify(decoy + st_payload(self.t, self.owner, "PROGRAM P", "real;"))
        self.assertEqual((rec.declaration, rec.implementation), ("PROGRAM P", "real;"))

    def test_decl_reference_does_not_satisfy_an_impl_slot(self):
        wrong = b"\x5b\xe5\x02" + self.t.v("x") + self.t.v(self.owner + "_Decl_LineIds")
        rec = self.classify(wrong + decl_only_payload(self.t, self.owner, "VAR_GLOBAL"))
        self.assertEqual((rec.kind, rec.implementation), ("gvl", None))

    def test_text_index_outside_the_table_is_reported(self):
        ref = self.t.v(self.owner + "_Decl_LineIds")
        rec = self.classify(b"\x41\xe5\x02" + vi(99999) + ref)
        self.assertEqual(rec.declaration, None)
        self.assertIn("not in the string table", rec.problems[0])

    def test_two_different_slots_use_the_first_and_say_so(self):
        payload = (decl_only_payload(self.t, self.owner, "VAR_GLOBAL a")
                   + slot(self.t, self.owner, "VAR_GLOBAL b", False))
        rec = self.classify(payload)
        self.assertEqual(rec.declaration, "VAR_GLOBAL a")
        self.assertIn("using the first", rec.problems[0])

    def test_truncated_slot_after_the_marker_is_not_a_crash(self):
        rec = self.classify(b"\x0f\x41\xe5\x02\x80")
        self.assertEqual((rec.kind, rec.problems), ("other", []))


class Kinds(Base):
    def test_kinds_by_payload(self):
        self.assertEqual(self.rec("DevA.pou").kind, "st")
        self.assertEqual(self.rec("gvl").kind, "gvl")
        self.assertEqual(self.rec("dut").kind, "dut")
        self.assertEqual(self.rec("other").kind, "other")
        self.assertEqual(self.rec("graph").kind, "graphical")

    def test_subtype_skips_comments_and_pragmas(self):
        self.assertEqual(self.rec("pragma").subtype, "FUNCTION_BLOCK")
        self.assertEqual(self.rec("DevA.pou").subtype, "PROGRAM")

    def test_declaration_keyword_needs_a_declaration(self):
        self.assertIsNone(project.declaration_keyword("x := 1;"))
        self.assertEqual(project.declaration_keyword("  FUNCTION f : INT"), "FUNCTION")

    def test_graphical_language_is_read_and_a_declaration_survives(self):
        rec = self.rec("graph")
        self.assertEqual(rec.language, "Ld")
        self.assertTrue(rec.declaration.startswith("PROGRAM Ladder"))
        self.assertIsNone(rec.implementation)

    def test_language_is_none_without_the_header_prefix_or_with_too_few_values(self):
        t = Table()
        owner = guid(5)
        for payload in (b"\x0f\xe1\x02" + b"\x00" * 5 + b"\x27", b"\x0f\xe6\x02\x48\x0f\xe1\x02"):
            rec = project.ObjectRecord(guid=owner)
            project.classify_object(rec, make_object(payload), dict(enumerate(t.texts)))
            self.assertEqual((rec.kind, rec.language), ("graphical", None))

    def test_a_network_tag_other_than_e1_still_marks_graphical(self):
        t = Table()
        owner = guid(5)
        rec = project.ObjectRecord(guid=owner)
        payload = graphical_payload(t, owner, network(t, "c", tag=b"\xe7\x02"), "PROGRAM G")
        project.classify_object(rec, make_object(payload), dict(enumerate(t.texts)))
        self.assertEqual(rec.kind, "graphical")


class Tree(Base):
    def test_path_device_and_application(self):
        rec = self.rec("DevB.pou")
        self.assertEqual(rec.path, ["DevB", "Plc Logic", "Application"])
        self.assertEqual((rec.device, rec.application), ("DevB", "Application"))

    def test_non_guid_entries_are_not_objects(self):
        self.assertEqual(len(self.project.objects), 13)

    def test_object_outside_a_plc_logic_node_has_no_application(self):
        rec = self.rec("other")
        self.assertEqual((rec.path, rec.application), (["DevA"], None))

    def test_records_in_tree_order(self):
        names = [r.name for r in self.project.records() if r.kind == "st"]
        self.assertEqual(names, ["Main", "Pragma", "Main"])  # by ancestors (DevA before DevB), then name

    def test_parent_loop_is_reported_not_followed(self):
        a, b = guid(1), guid(2)
        objects = {a: project.ObjectRecord(a, "A", b), b: project.ObjectRecord(b, "B", a)}
        project._link_parents(objects)
        self.assertIn("loops back", objects[a].problems[0])
        self.assertEqual(objects[a].path, ["B"])

    def test_linear_chain_has_no_loop_problem(self):
        a, b = guid(1), guid(2)
        objects = {a: project.ObjectRecord(a, "A", guid(0)), b: project.ObjectRecord(b, "B", a)}
        project._link_parents(objects)
        self.assertEqual((objects[b].path, objects[b].problems, objects[a].problems), (["A"], [], []))


class Damaged(unittest.TestCase):
    def test_damaged_entries_are_reported_and_the_rest_still_read(self):
        s = Synthetic()
        t = s.t
        null = guid(0)
        s.add("Good", null, lambda g: make_object(st_payload(t, g, "PROGRAM Good", "x;")))
        s.add("Cut", null, lambda g: make_object(st_payload(t, g, "PROGRAM Cut", "x;"))[:-4])
        s.add("Orphan", null, meta=False, payload=make_object(b"\x01"))
        s.add("NoObject", null)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "d.project")
            s.write(path)
            with zipfile.ZipFile(path, "a") as z:  # a meta whose stream never names its own guid
                z.writestr(guid(99) + ".meta", bytes([2, 0x20]))
            proj = project.load_project(path)
        by_name = {r.name: r for r in proj.objects.values()}
        self.assertEqual(by_name["Good"].kind, "st")
        self.assertEqual(by_name["Good"].problems, [])
        self.assertEqual(by_name["Cut"].kind, "unreadable")
        orphan = proj.objects[guid(3)]
        self.assertEqual((orphan.name, orphan.has_meta), (None, False))
        self.assertIn("no .meta", orphan.problems[0])
        self.assertIn("no .object", by_name["NoObject"].problems[0])
        self.assertIn("meta:", proj.objects[guid(99)].problems[0])

    def test_not_a_zip_and_no_string_table_are_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = os.path.join(tmp, "x.project")
            Path(bad).write_bytes(b"not a zip")
            with self.assertRaisesRegex(FormatError, "not a readable zip"):
                project.load_project(bad)
            with self.assertRaisesRegex(FormatError, "not a readable zip"):
                project.load_project(os.path.join(tmp, "missing.project"))
            empty = os.path.join(tmp, "e.project")
            with zipfile.ZipFile(empty, "w") as z:
                z.writestr("readme.txt", b"x")
            with self.assertRaisesRegex(FormatError, "no __shared_data_storage_string_table__"):
                project.load_project(empty)

    def test_corrupt_string_table_is_fatal(self):
        s = Synthetic()
        s.add("A", guid(0))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "c.project")
            s.write(path, declared=FILLER + 50)
            with self.assertRaisesRegex(FormatError, "declares"):
                project.load_project(path)


class Lookup(Base):
    def test_full_guid_prefix_and_name(self):
        g = self.ids["gvl"]
        self.assertEqual([r.guid for r in project.find_objects(self.project, g)], [g])
        self.assertEqual([r.guid for r in project.find_objects(self.project, g[:8])], [g])
        self.assertEqual([r.guid for r in project.find_objects(self.project, "Globals")], [g])

    def test_short_prefix_is_not_a_guid(self):
        self.assertEqual(project.find_objects(self.project, self.ids["gvl"][:7]), [])

    def test_same_name_in_two_devices_returns_both(self):
        self.assertEqual(len(project.find_objects(self.project, "Main")), 2)

    def test_ambiguous_name_is_an_error_that_lists_the_candidates(self):
        with self.assertRaises(FormatError) as ctx:
            codesys_project.resolve_one(self.project, "Main")
        message = str(ctx.exception)
        self.assertIn("ambiguous", message)
        self.assertIn("DevA/Plc Logic/Application/Main", message)
        self.assertIn("DevB/Plc Logic/Application/Main", message)

    def test_unknown_name_is_an_error(self):
        with self.assertRaisesRegex(FormatError, "no object"):
            codesys_project.resolve_one(self.project, "Nope")


class FileNames(unittest.TestCase):
    def test_separators_and_leading_dots_are_neutralised(self):
        self.assertEqual(export.safe_filename_part("a/b\\c"), "a_b_c")
        self.assertEqual(export.safe_filename_part("../x"), "_x")
        self.assertEqual(export.safe_filename_part(".."), "_")
        self.assertEqual(export.safe_filename_part(""), "_")

    def test_ordinary_names_survive(self):
        self.assertEqual(export.safe_filename_part("Pumpa_1 ćš.v2-x"), "Pumpa_1 ćš.v2-x")

    def test_long_names_are_cut(self):
        self.assertEqual(len(export.safe_filename_part("n" * 500)), export.MAX_STEM_PART)


class DumpSt(Base):
    def test_only_st_objects_are_written_and_collisions_get_the_guid(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out")
            written = export.dump_st(self.project, out)
            names = sorted(os.listdir(out))
        self.assertEqual(len(written), 3)
        self.assertEqual(names, sorted([
            "DevA_Pragma.decl.st", "DevA_Pragma.impl.st",
            "DevA_Main.decl.st", "DevA_Main.impl.st", "DevB_Main.decl.st", "DevB_Main.impl.st"]))
        # Globals (gvl), Point (dut), Ladder (graphical) and Tasks (other) are not ST: none written

    def test_text_is_byte_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            export.dump_st(self.project, tmp)
            raw = Path(tmp, "DevB_Main.impl.st").read_bytes()
        self.assertEqual(raw, b"x := x + 1; // DevB\r\n")

    def test_same_device_same_name_gets_a_guid_suffix_and_nothing_is_overwritten(self):
        s = Synthetic()
        t = s.t
        d = s.add("Dev", guid(0))
        first = s.add("Dup", d, lambda g: make_object(st_payload(t, g, "PROGRAM Dup", "one;")))
        second = s.add("dup", d, lambda g: make_object(st_payload(t, g, "PROGRAM dup", "two;")))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "p.project")
            s.write(path)
            out = os.path.join(tmp, "o")
            export.dump_st(project.load_project(path), out)
            names = sorted(os.listdir(out))
            texts = sorted(Path(out, n).read_text() for n in names if n.endswith(".impl.st"))
        self.assertEqual(len(names), 4)
        self.assertTrue(all(g[:8] in n for g in (first, second) for n in names if g[:8] in n))
        self.assertTrue(all("_" + first[:8] in n or "_" + second[:8] in n for n in names))
        self.assertEqual(texts, ["one;", "two;"])

    def test_object_without_meta_and_object_without_ancestors_get_stable_names(self):
        s = Synthetic()
        t = s.t
        s.add("RootPou", guid(0), lambda g: make_object(st_payload(t, g, "PROGRAM R", "r;")))
        lost = s.add("x", guid(0), lambda g: make_object(st_payload(t, g, "PROGRAM L", "l;")), meta=False)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "p.project")
            s.write(path)
            out = os.path.join(tmp, "o")
            export.dump_st(project.load_project(path), out)
            names = sorted(os.listdir(out))
        self.assertEqual(names, sorted(["root_RootPou.decl.st", "root_RootPou.impl.st",
                                        "unnamed_%s.decl.st" % lost, "unnamed_%s.impl.st" % lost]))

    def test_hostile_names_stay_inside_the_output_directory(self):
        s = Synthetic()
        t = s.t
        d = s.add("../../dev", guid(0))
        s.add("../evil/x", d, lambda g: make_object(st_payload(t, g, "PROGRAM E", "e;")))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "p.project")
            s.write(path)
            out = os.path.join(tmp, "a", "b")
            export.dump_st(project.load_project(path), out)
            inside = os.listdir(out)
            outside = [n for root, _, files in os.walk(tmp) for n in files if os.path.dirname(os.path.join(root, n)) != out
                       and not n.endswith(".project")]
        self.assertEqual(len(inside), 2)
        self.assertEqual(outside, [])


class GraphDecode(Base):
    def decode(self):
        rec = self.rec("graph")
        return graph.decode_graph(rec, self.project.blobs[rec.guid], self.project.strings)

    def test_networks_comments_and_tags(self):
        result = self.decode()
        self.assertEqual([n.comment for n in result.networks], ["start the lamp", None])
        self.assertEqual([n.tag for n in result.networks], ["e1 02", "e7 02"])
        self.assertEqual(result.language, "Ld")

    def test_elements_carry_decoded_fields_and_heuristic_labels(self):
        items = {i.decoded.get("name"): i for i in self.decode().networks[0].items if i.kind == "element"}
        lamp, start, preset = items["Lamp"], items["Start"], items["Preset"]
        self.assertEqual((lamp.decoded["type"], lamp.decoded["modifier"]), ("BOOL", 2))
        self.assertEqual((lamp.heuristic["direction"], lamp.heuristic["modifier_meaning"], lamp.heuristic["role"]),
                         ("OUT", "set", "coil"))
        self.assertEqual((start.heuristic["direction"], start.heuristic["modifier_meaning"]), ("IN", "negated"))
        self.assertNotIn("role", start.heuristic)
        self.assertEqual(preset.heuristic["modifier_meaning"], "none")
        self.assertEqual((lamp.ids, start.ids, preset.ids), ([5111], [5230], [5340, 6035]))  # the 733 filler id is dropped

    def test_a_coil_role_stops_after_the_declared_count(self):
        t = Table()
        items = coils(1) + element(t, "A", "BOOL", 0, 5111) + element(t, "B", "BOOL", 0, 5112)
        rec = project.ObjectRecord(guid=guid(5))
        data = make_object(graphical_payload(t, rec.guid, network(t, "", items), "PROGRAM G"))
        roles = [i.heuristic.get("role") for i in graph.decode_graph(rec, data, dict(enumerate(t.texts))).networks[0].items
                 if i.kind == "element"]
        self.assertEqual(roles, ["coil", None])

    def test_coil_role_goes_only_to_outputs(self):
        result = self.decode_items(lambda t: coils(2) + element(t, "In", "BOOL", 0, 5111, is_input=True)
                                   + element(t, "Out", "BOOL", 0, 5112))
        roles = {i.decoded["name"]: i.heuristic.get("role") for i in result.networks[0].items if i.kind == "element"}
        self.assertEqual(roles, {"In": None, "Out": "coil"})

    def test_box_decodes_type_instance_header_id_and_nesting(self):
        t = Table()
        inner = element(t, "In1", "INT", 0, 5560, is_input=True)
        items = box(t, "ADD", "", 6034) + box(t, "TON", "Timer1", 6140) + inner + qword(6141) + qword(6035)
        rec = project.ObjectRecord(guid=guid(5))
        data = make_object(graphical_payload(t, rec.guid, network(t, "", items), "PROGRAM G"))
        net = graph.decode_graph(rec, data, dict(enumerate(t.texts))).networks[0]
        boxes = [i for i in net.items if i.kind == "box"]
        self.assertEqual([(b.decoded["box_type"], b.decoded["instance"], b.decoded["header_id"]) for b in boxes],
                         [("ADD", "", 6034), ("TON", "Timer1", 6140)])
        depth = {i.decoded.get("name") or i.decoded.get("box_type"): i.heuristic["depth"] for i in net.items
                 if i.kind in ("box", "element")}
        self.assertEqual(depth, {"ADD": 0, "TON": 1, "In1": 2})

    def test_box_header_id_sentinel_means_not_a_box(self):
        t = Table()
        items = box(t, "ADD", "", graph.SENTINEL_ID)
        rec = project.ObjectRecord(guid=guid(5))
        data = make_object(graphical_payload(t, rec.guid, network(t, "", items), "PROGRAM G"))
        self.assertEqual([i.kind for i in graph.decode_graph(rec, data, dict(enumerate(t.texts))).networks[0].items], [])

    def test_pins_and_empty_slots(self):
        kinds = [i.kind for i in self.decode().networks[0].items]
        self.assertIn("pins", kinds)
        empty = [i for i in self.decode().networks[0].items if i.kind == "empty"][0]
        self.assertEqual((empty.decoded["id"], empty.decoded["raw"]), (7451, "42 00 00 00 00"))
        pin_item = [i for i in self.decode().networks[0].items if i.kind == "pins"][0]
        self.assertEqual(pin_item.decoded["names"], ["IN", "PT"])

    def decode_items(self, items, comment=""):
        t = self.table = Table()
        rec = project.ObjectRecord(guid=guid(5))
        data = make_object(graphical_payload(t, rec.guid, network(t, comment, items(t) if callable(items) else items),
                                             "PROGRAM G"))
        return graph.decode_graph(rec, data, dict(enumerate(t.texts)))

    def decode_at_end(self, raw):
        """Records that run into the end of the object (no declaration slot after them)."""
        t = Table()
        rec = project.ObjectRecord(guid=guid(5))
        data = make_object(network(t, "") + raw)
        return graph.decode_graph(rec, data, dict(enumerate(t.texts))).networks[0].items

    def test_logic_box_tag_and_a_box_cannot_be_made_from_a_bare_type(self):
        result = self.decode_items(lambda t: box(t, "AND", "", 6034, tag=b"\xe2\x02"))
        self.assertEqual([(i.kind, i.decoded["tag"]) for i in result.networks[0].items], [("box", "e2 02")])
        bare = self.decode_items(lambda t: box(t, "AND", "", 6034).replace(b"\xde\x02\x00", b"\x11\x22\x33"))
        self.assertEqual(bare.networks[0].items, [])  # no instance marker after the type: not a box

    def test_box_header_needs_the_01_flag_and_an_id_within_range(self):
        flagless = lambda t: box(t, "AND", "", 6034).replace(b"\x01" + qword(6034), b"\x02" + qword(6034))
        self.assertEqual(self.decode_items(flagless).networks[0].items, [])
        self.assertEqual(self.decode_items(lambda t: box(t, "AND", "", graph.MAX_ID + 1)).networks[0].items, [])
        self.assertEqual(len(self.decode_items(lambda t: box(t, "AND", "", graph.MAX_ID)).networks[0].items), 1)

    def test_box_with_an_unresolved_type_is_not_a_box(self):
        raw = b"\x0f\xe0\x02" + vi(99999) + b"\xde\x02\x00\x27\x27\x27\x27\xdd\x02" + b"\x00" * 8 + b"\x01" + qword(6034)
        self.assertEqual(self.decode_items(raw).networks[0].items, [])

    def test_span_end_exists_only_when_the_closing_id_is_found(self):
        lone = self.decode_items(lambda t: box(t, "AND", "", 6034)).networks[0].items[0]
        closed = self.decode_items(lambda t: box(t, "AND", "", 6034) + qword(6035)).networks[0].items[0]
        self.assertNotIn("span_end", lone.heuristic)
        self.assertIn("span_end", closed.heuristic)

    def test_element_with_empty_name_or_empty_type_or_no_modifier(self):
        nameless = self.decode_items(b"\xdf\x02\x27\x27\x27\x27\xdd\x02\x00" + b"\x00" * 8).networks[0].items[0]
        self.assertEqual((nameless.decoded["name"], "type" in nameless.decoded), ("", False))
        typeless = self.decode_items(lambda t: b"\xdf\x02" + t.v("V") + b"\x27\x27\x27\xdd\x02\x00" + b"\x00" * 8)
        self.assertEqual((typeless.networks[0].items[0].decoded["name"], "type" in typeless.networks[0].items[0].decoded),
                         ("V", False))
        no_mod = self.decode_items(lambda t: b"\xdf\x02" + t.v("V") + t.v("INT") + b"\x01" * 60).networks[0].items[0]
        self.assertIsNone(no_mod.decoded["modifier"])
        self.assertNotIn("modifier_meaning", no_mod.heuristic)

    def test_unlisted_modifier_code_is_not_given_a_meaning(self):
        item = self.decode_items(lambda t: element(t, "A", "BOOL", 16, 5111)).networks[0].items[0]
        self.assertEqual((item.decoded["modifier"], item.heuristic["modifier_meaning"]), (16, "unknown code"))

    def test_markers_pins_and_empty_need_their_exact_shape(self):
        res = self.decode_items(b"\x0f\xa6\x01\x02").networks[0].items
        self.assertEqual([(i.kind, i.decoded["value"]) for i in res], [("parallel_marker", 2)])
        self.assertEqual(self.decode_at_end(b"\x0f\x6f\x6c"), [])  # cut off by the end of the object
        self.assertEqual(self.decode_at_end(b"\x0f\xa6\x01"), [])
        self.assertEqual([i.kind for i in self.decode_at_end(b"\x0f\x6f\x6c\x01")], ["coils"])
        self.assertEqual(self.decode_items(lambda t: bytes([0x6A, 2, 0x0F]) + t.v("A") + t.v("B")).networks[0].items, [])
        self.assertEqual(self.decode_at_end(b"\x6a\x02\x0e\x80"), [])  # truncated pin name
        self.assertEqual(self.decode_items(b"\x9a\x01\x42\x00\x00\x00\x00\x01\x02\x03").networks[0].items, [])

    def test_networks_come_out_in_file_order_whatever_their_tag(self):
        t = Table()
        rec = project.ObjectRecord(guid=guid(5))
        nets = network(t, "first", tag=b"\xe7\x02") + network(t, "second") + network(t, "third", tag=b"\xe7\x02")
        data = make_object(graphical_payload(t, rec.guid, nets, "PROGRAM G"))
        result = graph.decode_graph(rec, data, dict(enumerate(t.texts)))
        self.assertEqual([n.comment for n in result.networks], ["first", "second", "third"])

    def test_record_ending_inside_the_comment_is_noted(self):
        t = Table()
        rec = project.ObjectRecord(guid=guid(5))
        result = graph.decode_graph(rec, make_object(b"\x0f\xe1\x02" + b"\x00" * 5 + b"\x80"), dict(enumerate(t.texts)))
        self.assertIn("ends inside the comment", result.notes[0])

    def test_unresolved_element_name_is_an_unknown_record_not_a_guess(self):
        t = Table()
        broken = b"\xdf\x02" + vi(88888) + b"\x27\x27\x27\xdd\x02\x00" + b"\x00" * 8
        items = broken + element(t, "Fine", "INT", 0, 5111)
        rec = project.ObjectRecord(guid=guid(5))
        data = make_object(graphical_payload(t, rec.guid, network(t, "", items), "PROGRAM G"))
        result = graph.decode_graph(rec, data, dict(enumerate(t.texts)))
        kinds = [(i.kind, i.decoded.get("name")) for i in result.networks[0].items]
        self.assertEqual(kinds, [("unknown", None), ("element", "Fine")])
        self.assertIn("could not be decoded", result.notes[0])
        self.assertIn("88888", result.networks[0].items[0].decoded["reason"])

    def test_element_cut_off_by_the_end_of_the_object_is_unknown(self):
        t = Table()
        rec = project.ObjectRecord(guid=guid(5))
        data = make_object(network(t, "") + b"\xdf\x02\x80")
        result = graph.decode_graph(rec, data, dict(enumerate(t.texts)))
        self.assertEqual([i.kind for i in result.networks[0].items], ["unknown"])

    def test_unresolved_comment_index_is_noted(self):
        t = Table()
        rec = project.ObjectRecord(guid=guid(5))
        data = make_object(b"\x0f\xe1\x02" + b"\x00" * 5 + vi(77777) + b"\x27\x27")
        result = graph.decode_graph(rec, data, dict(enumerate(t.texts)))
        self.assertIn("comment index 77777", result.notes[0])

    def test_object_without_networks_says_so(self):
        rec = self.rec("DevA.pou")
        result = graph.decode_graph(rec, self.project.blobs[rec.guid], self.project.strings)
        self.assertEqual(result.networks, [])
        self.assertIn("no network records", result.notes[0])

    def test_text_and_json_labels(self):
        result = self.decode()
        text = graphview.render_graph_text(result)
        self.assertIn("NOT decoded: wiring", text)
        self.assertIn("not full coverage", text)
        self.assertIn("OUT/coil 'Lamp' type=BOOL mod=2 ~set", text)
        self.assertIn("IN 'Start' type=BOOL mod=1 ~negated", text)
        self.assertIn("comment='start the lamp'", text)
        data = graphview.graph_to_dict(result)
        item = data["networks"][0]["items"][1]
        self.assertIn("ids", item["heuristic"])
        self.assertNotIn("ids", item["decoded"])
        self.assertIn("wiring", data["legend"])
        self.assertIn("not full coverage", data["legend"])


class Cli(Base):
    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = codesys_project.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_list_json_has_every_object_with_kind_and_chain(self):
        code, out, _ = self.run_cli("list", self.path, "--json")
        rows = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(len(rows), len(self.project.objects))
        ladder = [r for r in rows if r["name"] == "Ladder"][0]
        self.assertEqual((ladder["kind"], ladder["language"], ladder["path"]), ("graphical", "Ld", ["DevA", "Plc Logic", "Application"]))

    def test_list_kind_filter(self):
        code, out, _ = self.run_cli("list", self.path, "--kind", "gvl")
        lines = [line for line in out.splitlines() if not line.startswith("#")]
        self.assertEqual((code, len(lines)), (0, 1))
        self.assertIn("Globals", lines[0])

    def test_st_prints_declaration_and_implementation(self):
        code, out, _ = self.run_cli("st", self.path, self.ids["DevA.pou"][:8])
        self.assertEqual(code, 0)
        self.assertIn("PROGRAM Main", out)
        self.assertIn("x := x + 1; // DevA", out)

    def test_st_decl_and_impl_flags_are_raw(self):
        _, decl, _ = self.run_cli("st", self.path, self.ids["DevA.pou"], "--decl")
        _, impl, _ = self.run_cli("st", self.path, self.ids["DevA.pou"], "--impl")
        self.assertTrue(decl.startswith("PROGRAM Main") and "x :=" not in decl)
        self.assertEqual(impl, "x := x + 1; // DevA\r\n")

    def test_st_of_a_graphical_pou_prints_the_declaration_only(self):
        code, out, _ = self.run_cli("st", self.path, "Ladder")
        self.assertEqual(code, 0)
        self.assertIn("PROGRAM Ladder", out)
        self.assertIn("graphical (Ld), not ST", out)
        code, _, err = self.run_cli("st", self.path, "Ladder", "--impl")
        self.assertEqual(code, 2)
        self.assertIn("graphical", err)

    def test_st_refuses_non_st_and_ambiguous_names(self):
        code, _, err = self.run_cli("st", self.path, "Tasks")
        self.assertEqual((code, "no ST text" in err), (2, True))
        code, _, err = self.run_cli("st", self.path, "Main")
        self.assertEqual((code, "ambiguous" in err), (2, True))

    def test_graph_refuses_non_graphical(self):
        code, _, err = self.run_cli("graph", self.path, "Globals")
        self.assertEqual((code, "not graphical" in err), (2, True))

    def test_graph_json_and_text(self):
        code, out, _ = self.run_cli("graph", self.path, "Ladder", "--json")
        self.assertEqual((code, json.loads(out)["networks"][0]["comment"]), (0, "start the lamp"))
        code, out, _ = self.run_cli("graph", self.path, "Ladder")
        self.assertEqual(code, 0)
        self.assertIn("network 2", out)

    def test_graph_exits_1_when_something_could_not_be_decoded(self):
        s = Synthetic()
        t = s.t
        s.add("Bad", guid(0), lambda g: make_object(graphical_payload(t, g, network(t, "", b"\xdf\x02" + vi(88888)), "PROGRAM Bad")))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "b.project")
            s.write(path)
            code, out, _ = self.run_cli("graph", path, "Bad")
        self.assertEqual(code, 1)
        self.assertIn("UNKNOWN", out)

    def test_dump_st_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, _ = self.run_cli("dump-st", self.path, tmp)
            self.assertEqual((code, len(os.listdir(tmp))), (0, 6))
        self.assertIn("wrote 3 ST object(s)", out)

    def test_exit_codes_for_problems_and_unreadable_input(self):
        s = Synthetic()
        t = s.t
        s.add("Good", guid(0), lambda g: make_object(st_payload(t, g, "PROGRAM Good", "x;")))
        s.add("Cut", guid(0), lambda g: make_object(st_payload(t, g, "PROGRAM Cut", "x;"))[:-3])
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "c.project")
            s.write(path)
            code, out, err = self.run_cli("list", path)
            self.assertEqual(code, 1)
            self.assertIn("Good", out)
            self.assertIn("PROBLEM", err)
            garbage = os.path.join(tmp, "g.project")
            Path(garbage).write_bytes(b"nope")
            code, _, err = self.run_cli("list", garbage)
        self.assertEqual((code, "not a readable zip" in err), (2, True))

    def test_script_runs_as_a_program(self):
        done = subprocess.run([sys.executable, "-B", str(SCRIPTS / "codesys_project.py"), "list", self.path, "--kind", "st"],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0)
        self.assertEqual(len([ln for ln in done.stdout.splitlines() if not ln.startswith("#")]), 3)


if __name__ == "__main__":
    unittest.main()
