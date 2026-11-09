"""`info`, `diff` and `xref` of the CODESYS `.project` reader, tested on SYNTHETIC projects only.

Two versions of one project are built in codesys_synth.py (`build_version`) with known changes,
and a project made for xref (`build_xref`). Every guard has an input it must catch and a control
it must accept. Names and text are invented.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE))

import codesys_project  # noqa: E402
from codesysproj import buildinfo, diff, project, stscan, xref  # noqa: E402
from codesysproj.binary import FormatError  # noqa: E402
from codesys_synth import (  # noqa: E402
    Synthetic, slot, build_version, build_xref, decl_only_payload, devices_meta_xml, guid, make_object, st_payload,
    tools_versions_xml,
)


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = codesys_project.main(list(argv))
    return code, out.getvalue(), err.getvalue()


def write_entries(path, entries):
    """A project holding only the given extra entries (no objects) plus an empty string table."""
    s = Synthetic()
    s.write(path, extra=entries)


class Versions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.old = os.path.join(cls.tmp.name, "v1.project")
        cls.new = os.path.join(cls.tmp.name, "v2.project")
        cls.ids = build_version(cls.old, 1)
        cls.ids2 = build_version(cls.new, 2)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()


class Info(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "p.project")

    def test_reads_every_device_and_application(self):
        write_entries(self.path, {"devicesmetainformation.auxiliary": devices_meta_xml([
            ("DevA", [("App1", "11223344-0000-0000-0000-000000000000", "55667788-0000-0000-0000-000000000000"),
                      ("App2", "99aabbcc-0000-0000-0000-000000000000", "ddeeff00-0000-0000-0000-000000000000")]),
            ("DevB", [("App1", "01020304-0000-0000-0000-000000000000", "05060708-0000-0000-0000-000000000000")]),
        ])})
        info = buildinfo.read_info(self.path)
        self.assertEqual([d.name for d in info.devices], ["DevA", "DevB"])
        a = info.devices[0]
        self.assertEqual((a.device_type, a.device_id, a.device_version, a.device_name),
                         ("4096", "0000 0001", "1.2.3.4", "Model-DevA"))
        self.assertEqual([x.name for x in a.applications], ["App1", "App2"])
        self.assertEqual(a.applications[1].code_id, "99aabbcc-0000-0000-0000-000000000000")
        self.assertEqual(a.applications[1].data_id, "ddeeff00-0000-0000-0000-000000000000")
        self.assertEqual(len(info.devices[1].applications), 1)
        self.assertEqual(info.notes, [])

    def test_short_and_byte_swapped_forms(self):
        write_entries(self.path, {"devicesmetainformation.auxiliary": devices_meta_xml([
            ("DevA", [("App", "11223344-0000-0000-0000-000000000000", "55667788-0000-0000-0000-000000000000")])])})
        app = buildinfo.read_info(self.path).devices[0].applications[0]
        self.assertEqual(buildinfo.short_id(app.code_id), "11223344")
        self.assertEqual(buildinfo.swapped_id(app.code_id), "44332211")

    def test_short_and_swapped_refuse_what_is_not_a_guid(self):
        self.assertIsNone(buildinfo.short_id("not a guid"))
        self.assertIsNone(buildinfo.swapped_id("not a guid"))
        self.assertIsNone(buildinfo.short_id(None))

    def test_text_names_both_forms_and_the_limits(self):
        write_entries(self.path, {"devicesmetainformation.auxiliary": devices_meta_xml([
            ("DevA", [("App", "11223344-0000-0000-0000-000000000000", "55667788-0000-0000-0000-000000000000")])])})
        text = buildinfo.render_info_text(buildinfo.read_info(self.path))
        self.assertIn("CodeId 11223344-0000-0000-0000-000000000000", text)
        self.assertIn("44332211", text)
        self.assertIn("DataId 55667788", text)
        self.assertIn("no compile time", text)

    def test_missing_entry_is_a_note_and_exit_1(self):
        write_entries(self.path, {})
        info = buildinfo.read_info(self.path)
        self.assertEqual(info.devices, [])
        self.assertTrue(any("devicesmetainformation.auxiliary" in n for n in info.notes))
        code, out, err = run_cli("info", self.path)
        self.assertEqual(code, codesys_project.EXIT_PROBLEMS)
        self.assertIn("no build identity", err)

    def test_malformed_xml_is_a_note_not_a_crash(self):
        write_entries(self.path, {"devicesmetainformation.auxiliary": b"<Devices><Device>"})
        info = buildinfo.read_info(self.path)
        self.assertEqual(info.devices, [])
        self.assertTrue(any("not well-formed" in n for n in info.notes))

    def test_entity_declarations_are_refused_not_expanded(self):
        bomb = (b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY a "aaaa">]><Devices><Device>'
                b'<Data Key="Name" Type="System.String">&a;</Data></Device></Devices>')
        write_entries(self.path, {"devicesmetainformation.auxiliary": bomb})
        info = buildinfo.read_info(self.path)
        self.assertEqual(info.devices, [])
        self.assertTrue(any("DOCTYPE" in n for n in info.notes))

    def test_a_device_without_application_is_listed_with_none(self):
        write_entries(self.path, {"devicesmetainformation.auxiliary": devices_meta_xml([("Lone", [])])})
        info = buildinfo.read_info(self.path)
        self.assertEqual(info.devices[0].applications, [])
        self.assertIn("no application", buildinfo.render_info_text(info))

    def test_application_without_code_id_keeps_the_field_empty(self):
        xml = (b'<Devices><Device><Data Key="Name" Type="System.String">D</Data><Application>'
               b'<Data Key="Name" Type="System.String">A</Data></Application></Device></Devices>')
        write_entries(self.path, {"devicesmetainformation.auxiliary": xml})
        app = buildinfo.read_info(self.path).devices[0].applications[0]
        self.assertIsNone(app.code_id)
        self.assertIn("CodeId -", buildinfo.render_info_text(buildinfo.read_info(self.path)))

    def test_last_saved_is_the_newest_entry_whatever_the_order(self):
        saves = [("2021-01-01-00-00-00", "2021-06-30-10-00-00", 7, "2.0"),
                 ("2020-01-01-00-00-00", "2020-02-02-12-00-00", 5, "1.0"),
                 ("2022-01-01-00-00-00", "2021-12-31-23-59-59", 3, "3.0")]
        write_entries(self.path, {"engineeringtoolsversions.auxiliary": tools_versions_xml(saves, "Prod", "2.6")})
        info = buildinfo.read_info(self.path)
        self.assertEqual(info.last_saved, "2021-12-31 23:59:59")
        self.assertEqual((info.save_counter, info.core_version), (3, "3.0"))
        self.assertEqual((info.product, info.project_version), ("Prod", "2.6"))

    def test_a_malformed_save_stamp_is_ignored(self):
        saves = [("2020-01-01-00-00-00", "9999-bad", 5, "1.0"), ("2020-01-01-00-00-00", "2020-02-02-12-00-00", 4, "1.0")]
        write_entries(self.path, {"engineeringtoolsversions.auxiliary": tools_versions_xml(saves)})
        self.assertEqual(buildinfo.read_info(self.path).last_saved, "2020-02-02 12:00:00")

    def test_a_non_numeric_save_counter_is_left_empty(self):
        xml = (b'<Configuration><History><HistoryEntry CoreVersion="1" SaveCounter="x" '
               b'LastTimeSaved="2020-02-02-12-00-00" /></History></Configuration>')
        write_entries(self.path, {"engineeringtoolsversions.auxiliary": xml})
        info = buildinfo.read_info(self.path)
        self.assertEqual((info.last_saved, info.save_counter), ("2020-02-02 12:00:00", None))

    def test_no_history_is_not_a_note(self):
        write_entries(self.path, {"devicesmetainformation.auxiliary": devices_meta_xml([("D", [])])})
        info = buildinfo.read_info(self.path)
        self.assertIsNone(info.last_saved)
        self.assertEqual(info.notes, [])
        self.assertIn("last saved: not available", buildinfo.render_info_text(info))

    def test_not_a_project_is_a_format_error(self):
        bad = os.path.join(self.tmp.name, "bad.project")
        Path(bad).write_bytes(b"not a zip")
        with self.assertRaises(FormatError):
            buildinfo.read_info(bad)
        self.assertEqual(run_cli("info", bad)[0], codesys_project.EXIT_FATAL)

    def test_json_output(self):
        build_version(self.path, 2)
        code, out, _ = run_cli("info", self.path, "--json")
        data = json.loads(out)
        self.assertEqual(code, 0)
        app = data["devices"][0]["applications"][0]
        self.assertEqual(app["code_id"], "aaaa0002-0000-0000-0000-000000000000")
        self.assertEqual(app["code_id_short"], "aaaa0002")
        self.assertEqual(app["code_id_byte_swapped"], "0200aaaa")
        self.assertEqual(data["last_saved"], "2020-05-15 08:30:45")
        self.assertEqual(data["notes"], [])


class ObjectDiff(Versions):
    def diff(self, name, *extra):
        return run_cli("diff", self.old, self.new, name, *extra)

    def test_ids_and_offsets_alone_produce_no_difference(self):
        code, out, _ = self.diff("Shifted")
        self.assertEqual(code, 0)
        self.assertIn("no differences in the compared fields", out)
        self.assertNotIn("@@", out)

    def test_the_shifted_pair_really_differs_in_offsets_and_ids(self):
        """Control for the test above: the two objects are not byte-identical or id-identical."""
        a = project.load_project(self.old)
        b = project.load_project(self.new)
        ga = diff.graph_lines(a, a.objects[self.ids["shifted"]])
        gb = diff.graph_lines(b, b.objects[self.ids2["shifted"]])
        self.assertEqual(ga, gb)
        from codesysproj.graph import decode_graph
        ra = decode_graph(a.objects[self.ids["shifted"]], a.blobs[self.ids["shifted"]], a.strings)
        rb = decode_graph(b.objects[self.ids2["shifted"]], b.blobs[self.ids2["shifted"]], b.strings)
        self.assertNotEqual([i.offset for n in ra.networks for i in n.items], [i.offset for n in rb.networks for i in n.items])
        self.assertNotEqual([i.ids for n in ra.networks for i in n.items], [i.ids for n in rb.networks for i in n.items])

    def test_graph_changes_show_constant_modifier_comment_and_added_network(self):
        code, out, _ = self.diff("Ladder")
        self.assertEqual(code, 0)
        self.assertRegex(out, r"(?m)^-.*IN '500'")
        self.assertRegex(out, r"(?m)^\+.*IN '600'")
        self.assertRegex(out, r"(?m)^-.*OUT/coil 'Lamp' type=BOOL mod=2 ~set")
        self.assertRegex(out, r"(?m)^\+.*OUT/coil 'Lamp' type=BOOL mod=3 ~reset")
        self.assertRegex(out, r"(?m)^-network comment='start the lamp'$")
        self.assertRegex(out, r"(?m)^\+network comment='start the lamp slowly'$")
        self.assertRegex(out, r"(?m)^\+network comment='added later'$")
        self.assertRegex(out, r"(?m)^\+.*OUT 'Extra'")

    def test_graph_diff_carries_no_ids_offsets_or_header_ids(self):
        out = self.diff("Ladder")[1]
        for leak in ("ids~", "id=", "5111", "6034", "9011", "9020"):
            self.assertNotIn(leak, out)
        self.assertNotRegex(out, r"(?m)^.\s*\d+ ")  # no offset column

    def test_graph_diff_says_what_it_cannot_see(self):
        out = self.diff("Ladder")[1]
        self.assertIn("wiring", out)
        self.assertIn("not compared", out)

    def test_unreadable_record_and_empty_slot_bytes_do_not_make_a_difference(self):
        """An `unknown` item carries 16 raw bytes and an empty slot its id; neither is compared."""
        from codesys_synth import graphical_payload, network, vi, qword
        projects = []
        for n, follow in enumerate((100, 7000)):
            s = Synthetic()
            bad = b"\x0f\xdf\x02" + vi(9999) + qword(follow)
            s.add("G", guid(0), lambda g, s=s, bad=bad: make_object(graphical_payload(
                s.t, g, network(s.t, "c", bad), "PROGRAM G\nVAR\nEND_VAR")))
            path = os.path.join(self.tmp.name, "raw%d.project" % n)
            s.write(path)
            projects.append(project.load_project(path))
        lines = [diff.graph_lines(p, p.objects[guid(1)]) for p in projects]
        self.assertEqual(lines[0], lines[1])
        self.assertTrue(any(line.startswith("UNKNOWN") for line in lines[0]))

    def test_a_three_digit_constant_is_not_normalised_away(self):
        a = project.load_project(self.old)
        self.assertIn("IN '500'", "\n".join(diff.graph_lines(a, a.objects[self.ids["ladder"]])))

    def test_unchanged_graph_in_a_changed_object_has_no_graph_section(self):
        old = project.load_project(self.old)
        new = project.load_project(self.new)
        result = diff.object_diff(old, old.objects[self.ids["ladder"]], new, new.objects[self.ids2["ladder"]])
        self.assertEqual([s.label for s in result.sections], ["graph"])

    def test_st_declaration_and_implementation_are_diffed_separately(self):
        code, out, _ = self.diff("Edited")
        self.assertEqual(code, 0)
        self.assertIn("--- OLD Edited declaration", out)
        self.assertIn("+++ NEW Edited declaration", out)
        self.assertRegex(out, r"(?m)^\+\ty: INT;$")
        self.assertIn("--- OLD Edited implementation", out)
        self.assertRegex(out, r"(?m)^-x := x \+ 1;$")
        self.assertRegex(out, r"(?m)^\+x := x \+ 2;$")

    def test_unified_diff_keeps_context_and_st_has_no_graph_note(self):
        out = self.diff("Edited")[1]
        self.assertIn("\n VAR\n \tx: INT;\n+\ty: INT;", out)  # unchanged lines around the change
        self.assertNotIn("wiring", out)  # the limits note is for graphs

    def test_identical_st_has_no_difference(self):
        code, out, _ = self.diff("Same")
        self.assertEqual(code, 0)
        self.assertIn("no differences in the compared fields", out)

    def test_rename_is_announced_in_an_object_diff(self):
        out = run_cli("diff", self.old, self.new, self.ids["renamed"])[1]
        self.assertIn("# renamed: 'OldName' -> 'NewName'", out)
        self.assertIn("no differences in the compared fields", out)
        self.assertNotIn("# renamed", self.diff("Edited")[1])

    def test_a_graphical_slot_that_is_not_st_is_not_compared_as_implementation(self):
        from codesys_synth import graphical_payload, network, slot
        a, b = os.path.join(self.tmp.name, "gi1.project"), os.path.join(self.tmp.name, "gi2.project")
        for path, text in ((a, "one"), (b, "two")):
            s = Synthetic()
            s.add("G", guid(0), lambda g, s=s, text=text: make_object(
                graphical_payload(s.t, g, network(s.t, "c"), "PROGRAM G\nVAR\nEND_VAR") + slot(s.t, g, text, True)))
            s.write(path)
        rec = project.load_project(b).objects[guid(1)]
        self.assertEqual((rec.kind, rec.implementation), ("graphical", "two"))  # the slot exists and is read
        self.assertIn("no differences in the compared fields", run_cli("diff", a, b, "G")[1])

    def test_problem_in_the_new_object_sets_exit_1(self):
        a, b = os.path.join(self.tmp.name, "pn1.project"), os.path.join(self.tmp.name, "pn2.project")
        for path, twice in ((a, False), (b, True)):
            s = Synthetic()
            s.add("P", guid(0), lambda g, s=s, twice=twice: make_object(
                st_payload(s.t, g, "PROGRAM P\nVAR\nEND_VAR", "x := 1;")
                + (slot(s.t, g, "y := 2;", True) if twice else b"")))
            s.write(path)
        code, _, err = run_cli("diff", a, b, "P")
        self.assertEqual(code, codesys_project.EXIT_PROBLEMS)
        self.assertIn("PROBLEM", err)

    def test_line_ending_only_change_is_not_a_difference(self):
        old, new = os.path.join(self.tmp.name, "crlf1.project"), os.path.join(self.tmp.name, "crlf2.project")
        for path, impl in ((old, "a := 1;\r\nb := 2;\r\n"), (new, "a := 1;\nb := 2;\n")):
            s = Synthetic()
            s.add("P", guid(0), lambda g, impl=impl, s=s: make_object(st_payload(s.t, g, "PROGRAM P\nVAR\nEND_VAR", impl)))
            s.write(path)
        out = run_cli("diff", old, new, "P")[1]
        self.assertIn("no differences in the compared fields", out)

    def test_name_missing_from_one_side_is_an_error(self):
        for pou in ("Gone", "Fresh"):
            code, _, err = self.diff(pou)
            self.assertEqual(code, codesys_project.EXIT_FATAL)
            self.assertIn("not found in", err)
        self.assertIn("NEW", self.diff("Gone")[2])
        self.assertIn("OLD", self.diff("Fresh")[2])

    def test_a_guid_names_the_object_in_both_versions(self):
        code, out, _ = run_cli("diff", self.old, self.new, self.ids["edited"])
        self.assertEqual(code, 0)
        self.assertIn("implementation", out)

    def test_declaration_only_object_is_diffed(self):
        out = self.diff("Globals")[1]
        self.assertRegex(out, r"(?m)^\+\tmore: INT;$")
        self.assertNotIn("implementation", out)

    def test_object_that_is_not_comparable_is_an_error(self):
        code, _, err = self.diff("Tasks")
        self.assertEqual(code, codesys_project.EXIT_FATAL)
        self.assertIn("kind 'other'", err)

    def test_json_output(self):
        code, out, _ = self.diff("Ladder", "--json")
        data = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual([s["label"] for s in data["sections"]], ["graph"])
        self.assertTrue(any(line.startswith("+") for line in data["sections"][0]["diff"]))

    def test_kind_change_diffs_the_union_of_sections(self):
        a, b = os.path.join(self.tmp.name, "k1.project"), os.path.join(self.tmp.name, "k2.project")
        from codesys_synth import graphical_payload, network
        for path, graphical in ((a, False), (b, True)):
            s = Synthetic()
            decl = "PROGRAM K\nVAR\nEND_VAR"
            s.add("K", guid(0), lambda g, graphical=graphical, s=s: make_object(
                graphical_payload(s.t, g, network(s.t, "c"), decl) if graphical else st_payload(s.t, g, decl, "x := 1;")))
            s.write(path)
        out = run_cli("diff", a, b, "K")[1]
        self.assertIn("kind changed: st -> graphical", out)
        self.assertIn("implementation", out)
        self.assertIn("graph", out)

    def test_decode_notes_set_exit_1(self):
        """A recognised record that cannot be read is reported, and the exit code says so."""
        s = Synthetic()
        from codesys_synth import element, graphical_payload, network, vi
        bad = b"\x0f\xdf\x02" + vi(9999)  # element whose name index is not in the string table
        for name in ("n1.project", "n2.project"):
            s = Synthetic()
            s.add("G", guid(0), lambda g, s=s: make_object(graphical_payload(
                s.t, g, network(s.t, "c", bad), "PROGRAM G\nVAR\nEND_VAR")))
            s.write(os.path.join(self.tmp.name, name))
        code, out, err = run_cli("diff", os.path.join(self.tmp.name, "n1.project"),
                                 os.path.join(self.tmp.name, "n2.project"), "G")
        self.assertEqual(code, codesys_project.EXIT_PROBLEMS)
        self.assertIn("could not be decoded", err)
        code, _, err = run_cli("diff", os.path.join(self.tmp.name, "n1.project"), os.path.join(self.tmp.name, "n2.project"))
        self.assertEqual(code, codesys_project.EXIT_PROBLEMS)
        self.assertIn("could not be decoded", err)


class ProjectDiff(Versions):
    def lines(self):
        return run_cli("diff", self.old, self.new)[1].splitlines()

    def test_added_removed_and_changed_are_listed_by_guid(self):
        code, out, _ = run_cli("diff", self.old, self.new)
        self.assertEqual(code, 0)
        self.assertRegex(out, r"(?m)^\+ added +%s +st +.*Fresh$" % self.ids2["fresh"])
        self.assertRegex(out, r"(?m)^- removed +%s +st +.*Gone$" % self.ids["gone"])
        self.assertRegex(out, r"(?m)^~ changed +%s +st +.*Edited +\[declaration, implementation\]$" % self.ids["edited"])
        self.assertRegex(out, r"(?m)^~ changed +%s +graphical +.*Ladder +\[graph\]$" % self.ids["ladder"])
        self.assertRegex(out, r"(?m)^~ changed +%s +gvl +.*Globals +\[declaration\]$" % self.ids["globals"])

    def test_unchanged_objects_are_not_listed(self):
        out = run_cli("diff", self.old, self.new)[1]
        for name in ("Same", "Shifted"):
            self.assertNotRegex(out, r"(?m)^[~+-] .*\b%s$" % name)

    def test_rename_with_the_same_text_is_a_change_with_both_names(self):
        out = run_cli("diff", self.old, self.new)[1]
        self.assertRegex(out, r"(?m)^~ changed +%s +st +.*NewName +\[renamed from 'OldName'\]$" % self.ids["renamed"])

    def test_objects_that_are_not_compared_are_counted_not_hidden(self):
        out = run_cli("diff", self.old, self.new)[1]
        self.assertRegex(out, r"(?m)^= \d+ unchanged, 4 not compared \(kind other or unreadable\)")

    def test_summary_counts_add_up(self):
        a, b = project.load_project(self.old), project.load_project(self.new)
        result = diff.project_diff(a, b)
        self.assertEqual(len(result.added), 1)
        self.assertEqual(len(result.removed), 1)
        self.assertEqual(len(result.changed), 4)  # Edited, Ladder, Renamed, Globals
        both = set(a.objects) & set(b.objects)
        self.assertEqual(len(both), result.unchanged + result.not_compared + len(result.changed))

    def test_same_project_against_itself_lists_nothing(self):
        out = run_cli("diff", self.old, self.old)[1]
        self.assertNotRegex(out, r"(?m)^[~+-] ")

    def test_unreadable_on_one_side_is_not_compared_not_changed(self):
        a, b = os.path.join(self.tmp.name, "u1.project"), os.path.join(self.tmp.name, "u2.project")
        for path, payload in ((a, lambda s: lambda g: make_object(st_payload(s.t, g, "PROGRAM U\nVAR\nEND_VAR", "x := 1;"))),
                              (b, lambda s: lambda g: b"short")):
            s = Synthetic()
            s.add("U", guid(0), payload(s))
            s.write(path)
        out = run_cli("diff", a, b)[1]
        self.assertNotRegex(out, r"(?m)^~ changed")
        self.assertIn("1 not compared", out)

    def test_an_object_moved_to_another_parent_is_a_change(self):
        a, b = os.path.join(self.tmp.name, "m1.project"), os.path.join(self.tmp.name, "m2.project")
        for path, parent in ((a, 1), (b, 2)):
            s = Synthetic()
            s.add("Left", guid(0), make_object(b"\x0f\x01"))
            s.add("Right", guid(0), make_object(b"\x0f\x01"))
            s.add("Mover", guid(parent), lambda g, s=s: make_object(st_payload(s.t, g, "PROGRAM M\nVAR\nEND_VAR", "x := 1;")))
            s.write(path)
        out = run_cli("diff", a, b)[1]
        self.assertRegex(out, r"(?m)^~ changed +\S+ +st +Right/Mover +\[moved from 'Left'\]$")
        self.assertNotIn("renamed", out)

    def test_ambiguous_name_is_refused_with_the_candidates(self):
        from codesys_synth import build_standard
        std = os.path.join(self.tmp.name, "std.project")
        build_standard(std)
        code, _, err = run_cli("diff", std, std, "Main")
        self.assertEqual(code, codesys_project.EXIT_FATAL)
        self.assertIn("ambiguous", err)

    def test_json_output(self):
        code, out, _ = run_cli("diff", self.old, self.new, "--json")
        data = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual([c["name"] for c in data["added"]], ["Fresh"])
        self.assertEqual([c["name"] for c in data["removed"]], ["Gone"])
        self.assertEqual(sorted(c["name"] for c in data["changed"]), ["Edited", "Globals", "Ladder", "NewName"])
        self.assertEqual(data["not_compared"], 4)

    def test_problem_in_an_object_sets_exit_1(self):
        a = os.path.join(self.tmp.name, "pr1.project")
        s = Synthetic()
        s.add("Broken", guid(0), None)  # a meta entry without an object: reported as a problem
        s.write(a)
        code, _, err = run_cli("diff", a, a)
        self.assertEqual(code, codesys_project.EXIT_PROBLEMS)
        self.assertIn("PROBLEM", err)


class Xref(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = os.path.join(cls.tmp.name, "x.project")
        cls.ids = build_xref(cls.path)
        cls.project = project.load_project(cls.path)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def hits(self, query, name=None):
        result = xref.find_references(self.project, query)
        return [(h.name, h.where, h.role) for h in result.hits if name in (None, h.name)]

    def test_st_roles_by_line(self):
        got = self.hits("counter", "Writer")
        self.assertIn(("Writer", "implementation:3", "write"), got)
        self.assertIn(("Writer", "implementation:3", "read"), got)
        self.assertIn(("Writer", "implementation:4", "write"), got)  # Gvl.counter := 2
        self.assertIn(("Writer", "implementation:5", "read"), got)  # arr[counter] := 0: an index is a read
        self.assertIn(("Writer", "implementation:7", "arg"), got)  # IN := COUNTER > 3, any case
        self.assertIn(("Writer", "implementation:7", "write"), got)  # Q => counter
        self.assertIn(("Writer", "implementation:9", "write"), got)  # FOR counter := ...
        self.assertIn(("Writer", "implementation:10", "read"), got)  # Fb.Method(counter)

    def test_comments_strings_and_longer_names_do_not_match(self):
        lines = {w for _, w, _ in self.hits("counter", "Writer")}
        for noise in ("implementation:1", "implementation:2", "implementation:6", "implementation:8"):
            self.assertNotIn(noise, lines)  # comment, block comment, string, counter_total

    def test_assignment_target_is_not_also_a_read(self):
        on_line_4 = [r for _, w, r in self.hits("counter", "Writer") if w == "implementation:4"]
        self.assertEqual(on_line_4, ["write"])

    def test_the_array_is_written_and_its_index_read(self):
        got = self.hits("arr", "Writer")
        self.assertEqual(got, [("Writer", "implementation:5", "write")])

    def test_call_and_formal_parameter(self):
        got = self.hits("Timer1", "Writer")
        self.assertIn(("Writer", "implementation:7", "call"), got)
        self.assertIn(("Writer", "declaration:4", "declared"), got)  # `timer1 : TON;` any case
        self.assertEqual([r for _, w, r in self.hits("IN", "Writer") if w == "implementation:7"], ["param"])
        self.assertEqual([r for _, w, r in self.hits("Q", "Writer") if w == "implementation:7"], ["param"])  # Q => ...

    def test_qualified_query_matches_the_qualified_path_only(self):
        got = self.hits("Gvl.counter", "Writer")
        self.assertIn(("Writer", "implementation:4", "write"), got)
        self.assertNotIn(("Writer", "implementation:3", "write"), got)  # bare `counter`
        self.assertNotIn("implementation:11", {w for _, w, _ in got})  # `Gvl.other`: same first segment only

    def test_declaration_roles(self):
        got = self.hits("counter")
        self.assertIn(("Gvl", "declaration:1", "declared"), got)  # after `VAR_GLOBAL RETAIN` on the same line
        self.assertIn(("Writer", "declaration:3", "read"), got)  # initialiser `:= Gvl.counter`
        self.assertIn(("Lad", "declaration:3", "declared"), got)
        self.assertEqual([h for h in self.hits("spare") if h[0] == "Gvl"], [("Gvl", "declaration:2", "declared")])
        self.assertEqual([h for h in self.hits("other", "Gvl")], [("Gvl", "declaration:2", "declared")])
        self.assertEqual(self.hits("lone"), [("Gvl", "declaration:3", "declared")])  # `lone AT %MX0.0 : BOOL`

    def test_type_role(self):
        self.assertIn(("Writer", "declaration:4", "type"), self.hits("TON"))

    def test_qualified_declaration_needs_the_owning_object_name(self):
        self.assertIn(("Gvl", "declaration:1", "declared"), self.hits("Gvl.counter"))
        self.assertNotIn(("Lad", "declaration:3", "declared"), self.hits("Gvl.counter"))
        self.assertNotIn(("Gvl", "declaration:1", "declared"), self.hits("Other.counter"))

    def test_graphical_roles(self):
        got = self.hits("counter", "Lad")
        self.assertIn(("Lad", "network 1", "write"), got)  # OUT 'Gvl.counter'
        self.assertIn(("Lad", "network 1", "read"), got)  # IN 'arr[counter]': index
        self.assertEqual(self.hits("other", "Lad"), [("Lad", "network 1", "read")])  # IN
        self.assertEqual(self.hits("arr", "Lad"), [("Lad", "network 1", "read"), ("Lad", "network 2", "write")])
        self.assertEqual(self.hits("idx", "Lad"), [("Lad", "network 2", "read")])  # index of an OUT is a read

    def test_graphical_box_type_and_instance(self):
        self.assertIn(("Lad", "network 1", "type"), self.hits("TON", "Lad"))
        self.assertIn(("Lad", "network 1", "call"), self.hits("timer1", "Lad"))

    def test_literals_and_addresses_are_not_names(self):
        code = "x := 16#FF + T#5s + 1.5e3 + REAL#1.0 + %IX0.0 + a[1..n] + b.c + ptr^.field + d._e;"
        self.assertEqual([".".join(p.segments) for p in stscan.scan_paths(code)],
                         ["x", "a", "n", "b.c", "ptr.field", "d._e"])

    def test_unknown_name_has_no_hits(self):
        self.assertEqual(xref.find_references(self.project, "nothing_here").hits, [])

    def test_objects_not_searched_are_counted(self):
        result = xref.find_references(self.project, "counter")
        self.assertEqual(result.not_searched, 4)  # Dev, Plc Logic, Application, Tasks
        self.assertEqual(result.searched, 3)  # Gvl, Writer, Lad

    def test_text_output_marks_heuristics_and_limits(self):
        code, out, _ = run_cli("xref", self.path, "counter")
        self.assertEqual(code, 0)
        self.assertIn("heuristic", out)
        self.assertIn("no scope resolution", out)
        self.assertIn("not searched", out)
        self.assertRegex(out, r"Writer +\(st\) +implementation:3 +write")
        self.assertRegex(out, r"(?m)^\d+ reference\(s\) in 3 object\(s\)")

    def test_json_output(self):
        code, out, _ = run_cli("xref", self.path, "counter", "--json")
        data = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(data["query"], "counter")
        self.assertTrue(all(set(h) >= {"guid", "name", "kind", "where", "role", "text"} for h in data["hits"]))
        self.assertEqual(data["not_searched"], 4)

    def test_a_damaged_object_sets_exit_1(self):
        path = os.path.join(self.tmp.name, "dmg.project")
        s = Synthetic()
        s.add("Broken", guid(0), None)
        s.write(path)
        self.assertEqual(run_cli("xref", path, "x")[0], codesys_project.EXIT_PROBLEMS)

    def test_empty_query_is_an_error(self):
        self.assertEqual(run_cli("xref", self.path, "  ")[0], codesys_project.EXIT_FATAL)
        self.assertEqual(run_cli("xref", self.path, "a..b")[0], codesys_project.EXIT_FATAL)
        self.assertEqual(run_cli("xref", self.path, "5")[0], codesys_project.EXIT_FATAL)

    def test_unreadable_graph_records_are_reported(self):
        """A reference could hide in a record the decoder cannot read: say so."""
        from codesys_synth import graphical_payload, network, vi
        path = os.path.join(self.tmp.name, "u.project")
        s = Synthetic()
        s.add("G", guid(0), lambda g: make_object(graphical_payload(
            s.t, g, network(s.t, "c", b"\x0f\xdf\x02" + vi(9999)), "PROGRAM G\nVAR\nEND_VAR")))
        s.write(path)
        code, out, err = run_cli("xref", path, "anything")
        self.assertEqual(code, codesys_project.EXIT_PROBLEMS)
        self.assertIn("could not be decoded", out + err)


class Headers(unittest.TestCase):
    """A declaration whose header carries a `:` (a function's return type, a type's definition)."""

    @staticmethod
    def hits(decl, query, kind=project.KIND_GVL, name="Owner"):
        rec = project.ObjectRecord(guid=guid(1), name=name, kind=kind, declaration=decl,
                                   implementation="" if kind == project.KIND_ST else None)
        proj = project.Project(path="", strings={}, objects={rec.guid: rec}, blobs={})
        return [(h.where, h.role) for h in xref.find_references(proj, query).hits]

    def test_return_type_is_a_type_and_the_first_variable_is_declared(self):
        decl = "FUNCTION Func : BOOL\nVAR_INPUT\n\tx : INT;\nEND_VAR"
        self.assertEqual(self.hits(decl, "x"), [("declaration:3", "declared")])
        self.assertEqual(self.hits(decl, "BOOL"), [("declaration:1", "type")])
        self.assertEqual(self.hits(decl, "INT"), [("declaration:3", "type")])
        self.assertEqual(self.hits(decl, "FUNCTION"), [])
        self.assertEqual(self.hits(decl, "Func"), [("declaration:1", "declared")])

    def test_every_header_keyword_is_a_header(self):
        for keyword in ("FUNCTION", "FUNCTION_BLOCK", "METHOD", "PROPERTY", "PROGRAM", "INTERFACE", "ACTION",
                        "TRANSITION", "function", "Method"):
            decl = "%s Head : Ret\nVAR\n\tmember : INT;\nEND_VAR" % keyword
            with self.subTest(keyword):
                self.assertEqual(self.hits(decl, "member"), [("declaration:3", "declared")])
                self.assertEqual(self.hits(decl, "Ret"), [("declaration:1", "type")])
                self.assertEqual(self.hits(decl, keyword), [])

    def test_header_without_a_colon_leaves_the_variables_alone(self):
        decl = "PROGRAM Prog\nVAR\n\tmember : INT;\nEND_VAR"
        self.assertEqual(self.hits(decl, "member"), [("declaration:3", "declared")])
        self.assertEqual(self.hits(decl, "Prog"), [("declaration:1", "declared")])
        self.assertEqual(self.hits("PROGRAM Prog VAR x : INT; END_VAR", "x"), [("declaration:1", "declared")])

    def test_struct_members_after_a_type_header(self):
        multi = "TYPE Shape :\nSTRUCT\n\tcounter : INT;\n\tarea : REAL;\nEND_STRUCT\nEND_TYPE"
        self.assertEqual(self.hits(multi, "counter", project.KIND_DUT), [("declaration:3", "declared")])
        self.assertEqual(self.hits(multi, "area", project.KIND_DUT), [("declaration:4", "declared")])
        self.assertEqual(self.hits(multi, "Shape", project.KIND_DUT), [("declaration:1", "declared")])
        self.assertEqual(self.hits(multi, "STRUCT", project.KIND_DUT), [])  # a keyword, not a type
        one = "TYPE Pair : STRUCT counter : INT; second : INT; END_STRUCT END_TYPE"
        self.assertEqual(self.hits(one, "counter", project.KIND_DUT), [("declaration:1", "declared")])
        self.assertEqual(self.hits(one, "second", project.KIND_DUT), [("declaration:1", "declared")])
        both = "TYPE Pair : STRUCT\n\tcounter : INT;\nEND_STRUCT\nEND_TYPE"  # STRUCT comes before the line end
        self.assertEqual(self.hits(both, "STRUCT", project.KIND_DUT), [])
        self.assertEqual(self.hits(both, "counter", project.KIND_DUT), [("declaration:2", "declared")])

    def test_header_name_of_another_object_needs_the_qualifier(self):
        decl = "FUNCTION Func : BOOL\nVAR_INPUT\n\tx : INT;\nEND_VAR"
        self.assertEqual(self.hits(decl, "Other.Func"), [])
        self.assertEqual(self.hits(decl, "Owner.Func"), [("declaration:1", "declared")])

    def test_a_variable_named_like_a_header_keyword_is_still_a_variable(self):
        decl = "VAR_GLOBAL\n\taction : BOOL;\n\ttype : INT;\n\tmethod: INT;\nEND_VAR"
        self.assertEqual(self.hits(decl, "action"), [("declaration:2", "declared")])
        self.assertEqual(self.hits(decl, "type"), [("declaration:3", "declared")])
        self.assertEqual(self.hits(decl, "method"), [("declaration:4", "declared")])
        one = "VAR_GLOBAL a : INT; type : INT; action : BOOL; END_VAR"  # later chunks that start mid-line
        self.assertEqual(self.hits(one, "type"), [("declaration:1", "declared")])
        self.assertEqual(self.hits(one, "action"), [("declaration:1", "declared")])

    def test_a_header_alone_on_one_line_still_has_its_type(self):
        self.assertEqual(self.hits("FUNCTION F : BOOL", "BOOL"), [("declaration:1", "type")])
        self.assertEqual(self.hits("FUNCTION F : BOOL", "FUNCTION"), [])

    def test_a_declaration_with_no_colon_at_all(self):
        self.assertEqual(self.hits("PROGRAM Prog", "x"), [])
        self.assertEqual(self.hits("PROGRAM Prog", "Prog"), [("declaration:1", "declared")])
        self.assertEqual(self.hits("", "x"), [])

    def test_text_after_the_last_declaration_is_not_a_name(self):
        self.assertEqual(self.hits("VAR\n\tx : INT;\nEND_VAR", "END_VA"), [])


class StripNoise(unittest.TestCase):
    def test_comments_pragmas_and_strings_are_blanked_with_positions_kept(self):
        text = "a (* b\n (* nested *) c *) d // e\n{attr 'x'} f 'g $' h' i \"j\" k"
        out = stscan.strip_noise(text)
        self.assertEqual(len(out), len(text))
        self.assertEqual(out.count("\n"), 2)  # one inside the block comment, one after the line comment
        self.assertEqual(out.split(), ["a", "d", "f", "i", "k"])

    def test_unterminated_comment_and_string_blank_to_the_end(self):
        self.assertEqual(stscan.strip_noise("a (* b").split(), ["a"])
        self.assertEqual(stscan.strip_noise("a 'b").split(), ["a"])
        self.assertEqual(stscan.strip_noise("a {b").split(), ["a"])

    def test_comment_marker_inside_a_string_is_text(self):
        self.assertEqual(stscan.strip_noise("a '(* x' b").split(), ["a", "b"])


if __name__ == "__main__":
    unittest.main()
