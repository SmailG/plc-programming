"""Compare objects between two versions of a project.

What is compared, per object kind: ST has a declaration and an implementation (text, line
by line, line endings ignored); a graphical POU has a declaration (text) and a `graph`, the
decoded networks rendered with everything that changes on a re-save left out: byte offsets,
element ids, box header ids, empty-slot ids and raw bytes. Names, types, constants, modifier
bytes, network comments, box types, instances, box nesting and the coil count stay in, so a
constant that changes from 500 to 600 shows.

Not compared, and therefore invisible here: the wiring (the graph decoder does not decode it),
and bytes the graph decoder does not recognise. "No differences" means no difference in the
fields above, not that the two objects are identical.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .graph import decode_graph
from .graphview import item_label
from .project import KIND_DUT, KIND_GRAPHICAL, KIND_GVL, KIND_ST, ObjectRecord, Project

COMPARABLE_KINDS = (KIND_ST, KIND_GRAPHICAL, KIND_GVL, KIND_DUT)
CONTEXT_LINES = 2
LIMITS_NOTE = ("# not compared: wiring (not decoded) and bytes the graph decoder does not recognise; "
               "an empty diff does not mean the objects are identical")


@dataclass
class SectionDiff:
    label: str  # declaration | implementation | graph
    lines: List[str]  # unified diff, header lines first


@dataclass
class ObjectDiff:
    old: ObjectRecord
    new: ObjectRecord
    sections: List[SectionDiff] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)  # graph decode notes, both versions


@dataclass
class Change:
    guid: str
    name: Optional[str]
    kind: str
    path: List[str]
    labels: List[str] = field(default_factory=list)  # the sections that differ
    moves: List[str] = field(default_factory=list)  # "renamed from 'X'", "moved from 'a/b'"


@dataclass
class ProjectDiff:
    added: List[ObjectRecord] = field(default_factory=list)
    removed: List[ObjectRecord] = field(default_factory=list)
    changed: List[Change] = field(default_factory=list)
    unchanged: int = 0
    not_compared: int = 0
    notes: List[str] = field(default_factory=list)


def graph_lines(project: Project, rec: ObjectRecord, notes: Optional[List[str]] = None) -> List[str]:
    """The decoded graph as comparable lines: one per network comment and one per item."""
    result = decode_graph(rec, project.blobs[rec.guid], project.strings)
    if notes is not None:
        notes.extend("%s: %s" % (rec.name, n) for n in result.notes)
    lines: List[str] = []
    for net in result.networks:
        lines.append("network comment=%s" % ("none" if net.comment is None else repr(net.comment)))
        lines += [item_label(item, stable=True) for item in net.items]
    return lines


def _text_lines(text: Optional[str]) -> List[str]:
    return text.splitlines() if text else []


def sections(project: Project, rec: ObjectRecord, notes: Optional[List[str]] = None) -> Dict[str, List[str]]:
    """Comparable parts of an object, by label."""
    parts: Dict[str, List[str]] = {"declaration": _text_lines(rec.declaration)}
    if rec.kind == KIND_ST:
        parts["implementation"] = _text_lines(rec.implementation)
    if rec.kind == KIND_GRAPHICAL:
        parts["graph"] = graph_lines(project, rec, notes)
    return parts


def _unified(label: str, old_name: Optional[str], new_name: Optional[str], old: List[str], new: List[str]) -> List[str]:
    return list(difflib.unified_diff(old, new, "OLD %s %s" % (old_name, label), "NEW %s %s" % (new_name, label),
                                     lineterm="", n=CONTEXT_LINES))


def differing_labels(old: Dict[str, List[str]], new: Dict[str, List[str]]) -> List[str]:
    order = ("declaration", "implementation", "graph")
    return [lbl for lbl in order if (lbl in old or lbl in new) and old.get(lbl, []) != new.get(lbl, [])]


def object_diff(old_project: Project, old: ObjectRecord, new_project: Project, new: ObjectRecord) -> ObjectDiff:
    result = ObjectDiff(old, new)
    old_parts = sections(old_project, old, result.notes)
    new_parts = sections(new_project, new, result.notes)
    for label in differing_labels(old_parts, new_parts):
        result.sections.append(SectionDiff(label, _unified(label, old.name, new.name, old_parts.get(label, []),
                                                           new_parts.get(label, []))))
    return result


def _is_comparable(rec: ObjectRecord) -> bool:
    return rec.kind in COMPARABLE_KINDS


def project_diff(old: Project, new: Project) -> ProjectDiff:
    """Objects matched by guid (a guid survives a save; the names are what people change)."""
    result = ProjectDiff()
    result.added = [new.objects[g] for g in sorted(set(new.objects) - set(old.objects))]
    result.removed = [old.objects[g] for g in sorted(set(old.objects) - set(new.objects))]
    for guid in sorted(set(old.objects) & set(new.objects)):
        a, b = old.objects[guid], new.objects[guid]
        if not (_is_comparable(a) and _is_comparable(b)):
            result.not_compared += 1
            continue
        labels = differing_labels(sections(old, a, result.notes), sections(new, b, result.notes))
        moves = []
        if a.name != b.name:
            moves.append("renamed from %r" % a.name)
        if a.path != b.path:
            moves.append("moved from %r" % "/".join(a.path))
        if labels or moves:
            result.changed.append(Change(guid, b.name, b.kind, b.path, labels, moves))
        else:
            result.unchanged += 1
    return result


def _where(name: Optional[str], path: List[str]) -> str:
    return "/".join(path + [name or "?"])


def render_object_diff(result: ObjectDiff) -> str:
    lines: List[str] = []
    if result.old.kind != result.new.kind:
        lines.append("# kind changed: %s -> %s" % (result.old.kind, result.new.kind))
    if result.old.name != result.new.name:
        lines.append("# renamed: %r -> %r" % (result.old.name, result.new.name))
    if KIND_GRAPHICAL in (result.old.kind, result.new.kind):
        lines.append(LIMITS_NOTE)
    if not result.sections:
        lines.append("no differences in the compared fields (%s)" % _where(result.new.name, result.new.path))
    for section in result.sections:
        lines += section.lines
    return "\n".join(lines)


def render_project_diff(result: ProjectDiff) -> str:
    lines = ["# objects matched by guid; ST text and decoded LD/FBD graphs compared, other kinds not. "
             "Give a POU name to see its diff."]
    for rec in result.added:
        lines.append("+ added   %s  %-9s %s" % (rec.guid, rec.kind, _where(rec.name, rec.path)))
    for rec in result.removed:
        lines.append("- removed %s  %-9s %s" % (rec.guid, rec.kind, _where(rec.name, rec.path)))
    for ch in result.changed:
        tags = (["[%s]" % ", ".join(ch.labels)] if ch.labels else []) + ["[%s]" % m for m in ch.moves]
        lines.append("~ changed %s  %-9s %s  %s" % (ch.guid, ch.kind, _where(ch.name, ch.path), " ".join(tags)))
    lines.append("= %d unchanged, %d not compared (kind other or unreadable); %d added, %d removed, %d changed"
                 % (result.unchanged, result.not_compared, len(result.added), len(result.removed), len(result.changed)))
    return "\n".join(lines)


def object_diff_to_dict(result: ObjectDiff) -> dict:
    return {
        "guid": result.new.guid, "name": result.new.name, "old_name": result.old.name,
        "old_kind": result.old.kind, "new_kind": result.new.kind, "notes": result.notes,
        "sections": [{"label": s.label, "diff": s.lines} for s in result.sections],
    }


def _record_dict(guid: str, name: Optional[str], kind: str, path: List[str]) -> dict:
    return {"guid": guid, "name": name, "kind": kind, "path": path}


def project_diff_to_dict(result: ProjectDiff) -> dict:
    return {
        "added": [_record_dict(r.guid, r.name, r.kind, r.path) for r in result.added],
        "removed": [_record_dict(r.guid, r.name, r.kind, r.path) for r in result.removed],
        "changed": [dict(_record_dict(c.guid, c.name, c.kind, c.path), labels=c.labels, moves=c.moves)
                    for c in result.changed],
        "unchanged": result.unchanged, "not_compared": result.not_compared, "notes": result.notes,
    }
