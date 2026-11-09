#!/usr/bin/env python3
"""Read a CODESYS 3.5 / EcoStruxure Machine Expert `.project` file offline (no IDE).

    codesys_project.py list PROJECT [--json] [--kind KIND]
    codesys_project.py st PROJECT NAME_OR_GUID [--decl | --impl]
    codesys_project.py dump-st PROJECT OUTDIR
    codesys_project.py graph PROJECT NAME_OR_GUID [--json]
    codesys_project.py info PROJECT [--json]
    codesys_project.py diff OLD NEW [NAME_OR_GUID] [--json]
    codesys_project.py xref PROJECT NAME [--json]

The `.project` format is undocumented; this reader is reverse-engineered and was checked
on Machine Expert V2.x projects only. ST text and the object inventory are decoded from
the file's own structure. Graphical wiring is NOT decoded: `graph` lists element records
and ids, and every interpretation is marked as a heuristic. Prefer a PLCopen XML export
from the IDE when you can get one, and confirm graphical logic in the IDE before acting
on it. See skills/other-platforms/references/codesys-project-files.md.

`info` prints each application's CodeId / DataId (the build identity) and the project's last
save time. `diff` compares two versions: with a POU it prints the unified diff of its text or
of its decoded graph with ids and offsets left out; without one it lists the objects added,
removed and changed. `xref` lists every ST and LD/FBD use of a name, by name only (heuristic).

Exit: 0 clean (a difference between two projects is not a problem), 1 result printed but some
objects had problems, 2 usage or unreadable input.
Standard library only; Python 3.9 or later.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codesysproj import buildinfo, diff, xref  # noqa: E402
from codesysproj.binary import FormatError  # noqa: E402
from codesysproj.export import dump_st  # noqa: E402
from codesysproj.graph import decode_graph  # noqa: E402
from codesysproj.graphview import graph_to_dict, render_graph_text  # noqa: E402
from codesysproj.project import (  # noqa: E402
    KIND_GRAPHICAL, KIND_ST, KINDS, ObjectRecord, Project, find_objects, load_project,
)

EXIT_OK, EXIT_PROBLEMS, EXIT_FATAL = 0, 1, 2


def record_dict(rec: ObjectRecord) -> dict:
    return {
        "guid": rec.guid, "name": rec.name, "kind": rec.kind, "subtype": rec.subtype,
        "language": rec.language, "path": rec.path, "device": rec.device,
        "application": rec.application, "parent_guid": rec.parent_guid, "problems": rec.problems,
    }


def format_list(records: List[ObjectRecord]) -> str:
    lines = ["# guid  kind(subtype)  name  ancestors   (kind and subtype are heuristics)"]
    for rec in records:
        where = "/".join(rec.path) if rec.path else "-"
        kind = rec.kind + ("(%s)" % rec.subtype if rec.subtype else "")
        lines.append("%s  %-26s %s  %s" % (rec.guid, kind, rec.name if rec.name is not None else "?", where))
    return "\n".join(lines)


def resolve_one(project: Project, query: str) -> ObjectRecord:
    """The single object a NAME_OR_GUID names; FormatError if none or several."""
    matches = find_objects(project, query)
    if not matches:
        raise FormatError("no object with guid, guid prefix or name %r" % query)
    if len(matches) > 1:
        lines = ["%r is ambiguous (%d objects); give a guid or a guid prefix:" % (query, len(matches))]
        lines += ["  %s  %s  %s" % (r.guid, r.kind, "/".join(r.path + [r.name or "?"])) for r in matches]
        raise FormatError("\n".join(lines))
    return matches[0]


def report_problems(records: List[ObjectRecord]) -> int:
    """Print each object's problems to stderr; return how many objects had any."""
    bad = [r for r in records if r.problems]
    for rec in bad:
        for problem in rec.problems:
            print("PROBLEM %s (%s): %s" % (rec.guid, rec.name or "?", problem), file=sys.stderr)
    return len(bad)


def cmd_list(project: Project, args: argparse.Namespace) -> int:
    records = [r for r in project.records() if args.kind in (None, r.kind)]
    if args.json:
        print(json.dumps([record_dict(r) for r in records], indent=2, ensure_ascii=False))
    else:
        print(format_list(records))
    return EXIT_PROBLEMS if report_problems(records) else EXIT_OK


def cmd_st(project: Project, args: argparse.Namespace) -> int:
    rec = resolve_one(project, args.target)
    if rec.kind not in (KIND_ST, KIND_GRAPHICAL) or rec.declaration is None:
        raise FormatError("%s (%s) is kind %r: there is no ST text to print" % (rec.guid, rec.name, rec.kind))
    if args.decl:
        sys.stdout.write(rec.declaration)
    elif args.impl:
        if rec.kind == KIND_GRAPHICAL:
            raise FormatError("%s (%s) is graphical: its implementation is not ST; use `graph`" % (rec.guid, rec.name))
        sys.stdout.write(rec.implementation or "")
    else:
        print("(* declaration: %s %s *)" % (rec.name, rec.guid))
        print(rec.declaration)
        if rec.kind == KIND_ST:
            print("(* implementation *)")
            print(rec.implementation or "")
        else:
            print("(* implementation: graphical (%s), not ST; use `graph` *)" % rec.language)
    return EXIT_PROBLEMS if report_problems([rec]) else EXIT_OK


def cmd_dump_st(project: Project, args: argparse.Namespace) -> int:
    written = dump_st(project, args.outdir)
    for rec, files in written:
        print("%s  %s" % (rec.guid, "  ".join(files)))
    print("wrote %d ST object(s) to %s" % (len(written), args.outdir))
    return EXIT_PROBLEMS if report_problems([r for r, _ in written]) else EXIT_OK


def cmd_graph(project: Project, args: argparse.Namespace) -> int:
    rec = resolve_one(project, args.target)
    if rec.kind != KIND_GRAPHICAL:
        raise FormatError("%s (%s) is kind %r, not graphical" % (rec.guid, rec.name, rec.kind))
    result = decode_graph(rec, project.blobs[rec.guid], project.strings)
    print(json.dumps(graph_to_dict(result), indent=2, ensure_ascii=False) if args.json else render_graph_text(result))
    return EXIT_PROBLEMS if (report_problems([rec]) or result.notes) else EXIT_OK


def cmd_info(args: argparse.Namespace) -> int:
    info = buildinfo.read_info(args.project)
    print(json.dumps(buildinfo.info_to_dict(info), indent=2, ensure_ascii=False) if args.json
          else buildinfo.render_info_text(info))
    for note in info.notes:
        print("NOTE %s" % note, file=sys.stderr)
    return EXIT_PROBLEMS if info.notes else EXIT_OK


def resolve_in(project: Project, query: str, label: str) -> ObjectRecord:
    """The one object `query` names in this version of the project; the error names the version."""
    if not find_objects(project, query):
        raise FormatError("%r not found in %s (%s)" % (query, label, project.path))
    rec = resolve_one(project, query)
    if rec.kind not in diff.COMPARABLE_KINDS:
        raise FormatError("%s (%s) is kind %r in %s: there is nothing to compare" % (rec.guid, rec.name, rec.kind, label))
    return rec


def report_notes(notes: List[str]) -> int:
    for note in notes:
        print("NOTE %s" % note, file=sys.stderr)
    return len(notes)


def cmd_diff(args: argparse.Namespace) -> int:
    old, new = load_project(args.old), load_project(args.new)
    if args.target is None:
        result = diff.project_diff(old, new)
        print(json.dumps(diff.project_diff_to_dict(result), indent=2, ensure_ascii=False) if args.json
              else diff.render_project_diff(result))
        problems = report_problems(old.records()) + report_problems(new.records())
        return EXIT_PROBLEMS if problems or report_notes(result.notes) else EXIT_OK
    a, b = resolve_in(old, args.target, "OLD"), resolve_in(new, args.target, "NEW")
    result = diff.object_diff(old, a, new, b)
    print(json.dumps(diff.object_diff_to_dict(result), indent=2, ensure_ascii=False) if args.json
          else diff.render_object_diff(result))
    return EXIT_PROBLEMS if report_problems([a, b]) or report_notes(result.notes) else EXIT_OK


def cmd_xref(project: Project, args: argparse.Namespace) -> int:
    result = xref.find_references(project, args.name)
    print(json.dumps(xref.xref_to_dict(result), indent=2, ensure_ascii=False) if args.json
          else xref.render_xref_text(result))
    return EXIT_PROBLEMS if report_problems(project.records()) or result.notes else EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codesys_project.py", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p_list = sub.add_parser("list", help="every object: guid, kind, name, ancestors")
    p_list.add_argument("project")
    p_list.add_argument("--json", action="store_true")
    p_list.add_argument("--kind", choices=KINDS, help="only objects of this (heuristic) kind")
    p_st = sub.add_parser("st", help="print a POU's declaration and implementation text")
    p_st.add_argument("project")
    p_st.add_argument("target", help="object name, guid or unique guid prefix (8+ characters)")
    part = p_st.add_mutually_exclusive_group()
    part.add_argument("--decl", action="store_true", help="print only the declaration, raw")
    part.add_argument("--impl", action="store_true", help="print only the implementation, raw")
    p_dump = sub.add_parser("dump-st", help="write every ST POU as <Device>_<Name>.decl.st / .impl.st")
    p_dump.add_argument("project")
    p_dump.add_argument("outdir")
    p_graph = sub.add_parser("graph", help="element records and network comments of an LD/FBD POU")
    p_graph.add_argument("project")
    p_graph.add_argument("target", help="object name, guid or unique guid prefix (8+ characters)")
    p_graph.add_argument("--json", action="store_true")
    p_info = sub.add_parser("info", help="CodeId / DataId per device application, and the last save time")
    p_info.add_argument("project")
    p_info.add_argument("--json", action="store_true")
    p_diff = sub.add_parser("diff", help="what changed between two versions: one POU, or every object")
    p_diff.add_argument("old")
    p_diff.add_argument("new")
    p_diff.add_argument("target", nargs="?", help="object name, guid or unique guid prefix; omit to list every change")
    p_diff.add_argument("--json", action="store_true")
    p_xref = sub.add_parser("xref", help="every ST and LD/FBD use of a variable, instance or type name (heuristic)")
    p_xref.add_argument("project")
    p_xref.add_argument("name", help="a name or dotted path such as Gvl.Counter; case-insensitive")
    p_xref.add_argument("--json", action="store_true")
    return parser


COMMANDS = {"list": cmd_list, "st": cmd_st, "dump-st": cmd_dump_st, "graph": cmd_graph, "xref": cmd_xref}
STANDALONE = {"info": cmd_info, "diff": cmd_diff}  # load their own project(s)


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command in STANDALONE:
            return STANDALONE[args.command](args)
        return COMMANDS[args.command](load_project(args.project), args)
    except FormatError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return EXIT_FATAL


if __name__ == "__main__":
    sys.exit(main())
