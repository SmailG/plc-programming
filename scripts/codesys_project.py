#!/usr/bin/env python3
"""Read a CODESYS 3.5 / EcoStruxure Machine Expert `.project` file offline (no IDE).

    codesys_project.py list PROJECT [--json] [--kind KIND]
    codesys_project.py st PROJECT NAME_OR_GUID [--decl | --impl]
    codesys_project.py dump-st PROJECT OUTDIR
    codesys_project.py graph PROJECT NAME_OR_GUID [--json]

The `.project` format is undocumented; this reader is reverse-engineered and was checked
on Machine Expert V2.x projects only. ST text and the object inventory are decoded from
the file's own structure. Graphical wiring is NOT decoded: `graph` lists element records
and ids, and every interpretation is marked as a heuristic. Prefer a PLCopen XML export
from the IDE when you can get one, and confirm graphical logic in the IDE before acting
on it. See skills/other-platforms/references/codesys-project-files.md.

Exit: 0 clean, 1 result printed but some objects had problems, 2 usage or unreadable input.
Standard library only; Python 3.9 or later.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codesysproj.binary import FormatError  # noqa: E402
from codesysproj.export import dump_st  # noqa: E402
from codesysproj.graph import decode_graph, graph_to_dict, render_graph_text  # noqa: E402
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
    return parser


COMMANDS = {"list": cmd_list, "st": cmd_st, "dump-st": cmd_dump_st, "graph": cmd_graph}


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](load_project(args.project), args)
    except FormatError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return EXIT_FATAL


if __name__ == "__main__":
    sys.exit(main())
