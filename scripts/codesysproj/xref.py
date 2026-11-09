"""Where a variable, instance or type name is used: ST text and decoded LD/FBD elements.

EVERY result is a heuristic. The match is by name only (IEC 61131-3 is case-insensitive), with no
scope resolution: a local variable and a global with the same name both match, and `x.Foo` is
reported for the query `Foo` as well as `Foo.x`. A query of several segments (`Gvl.Foo`) matches
paths that contain those segments in a row.

Roles, per reference:

* ST implementation: `write` is the target before `:=` outside a call, or the variable after `=>`;
  `read` is any other use (an array index of a target is a read); `call` is a name followed by `(`;
  `param` is the formal name before `:=` or `=>` inside a call; `arg` is the value after `name :=`
  inside a call, whose direction depends on the callee's declaration, which is not read.
* Declarations: `declared` (the name before the `:`), `type` (the part after it, up to `:=`),
  `read` (an initial value).
* LD/FBD: `write` for an element the decoder labels OUT, `read` for IN (both heuristic: the byte
  before the element), `read` for names inside an index, `type` for a box type, `call` for a box
  instance. Wiring is not decoded.

Not searched: objects of kind other (devices, tasks, I/O mappings: a variable mapped to a channel
there is not found), and ST text that the object's slots do not carry. Graphical records the
decoder could not read are counted, since a reference may hide in one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .binary import FormatError
from .graph import decode_graph
from .project import KIND_DUT, KIND_GRAPHICAL, KIND_GVL, KIND_ST, ObjectRecord, Project
from .stscan import IDENT_RE, NameRef, scan_paths, strip_noise

_SECTION_WORDS = frozenset(w.lower() for w in (
    "VAR", "VAR_INPUT", "VAR_OUTPUT", "VAR_IN_OUT", "VAR_GLOBAL", "VAR_TEMP", "VAR_STAT", "VAR_EXTERNAL",
    "VAR_CONFIG", "VAR_INST", "CONSTANT", "RETAIN", "PERSISTENT", "END_VAR", "STRUCT", "END_STRUCT"))
_HEADER_RE = re.compile(
    r"\s*(?:FUNCTION_BLOCK|FUNCTION|METHOD|PROPERTY|PROGRAM|INTERFACE|TYPE|ACTION|TRANSITION)\b[ \t]*([A-Za-z_]\w*)?",
    re.I)
_STRUCT_RE = re.compile(r"\bSTRUCT\b", re.I)
SEARCHED_KINDS = (KIND_ST, KIND_GRAPHICAL, KIND_GVL, KIND_DUT)


@dataclass
class Reference:
    guid: str
    name: Optional[str]
    kind: str
    path: List[str]
    where: str  # "implementation:12", "declaration:3", "network 2"
    role: str
    text: str  # the source line, or the element label


@dataclass
class XrefResult:
    query: str
    hits: List[Reference] = field(default_factory=list)
    searched: int = 0
    not_searched: int = 0
    notes: List[str] = field(default_factory=list)


def _contains(segments: List[str], query: List[str]) -> bool:
    low = [s.lower() for s in segments]
    return any(low[k:k + len(query)] == query for k in range(len(low) - len(query) + 1))


def _st_role(code: str, path: NameRef) -> str:
    """Role of an ST path from the text around it (`code` is noise-free)."""
    head = code[:path.start]
    before = head.rstrip()
    after = code[path.end:].lstrip()
    in_call = head.count("(") > head.count(")")
    if after.startswith("=>"):
        return "param"
    if after.startswith(":="):
        return "param" if in_call else "write"
    if after.startswith("("):
        return "call"
    if before.endswith("=>"):
        return "write"
    if before.endswith(":=") and in_call:
        return "arg"
    return "read"


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _source_line(text: str, line: int) -> str:
    lines = text.splitlines()
    return lines[line - 1].strip() if 0 < line <= len(lines) else ""


def _scan_implementation(rec: ObjectRecord, query: List[str]) -> List[Reference]:
    text = rec.implementation or ""
    code = strip_noise(text)
    refs = []
    for path in scan_paths(code):
        if _contains(path.segments, query):
            line = _line_of(code, path.start)
            refs.append(Reference(rec.guid, rec.name, rec.kind, rec.path, "implementation:%d" % line,
                                  _st_role(code, path), _source_line(text, line)))
    return refs


def _declared_names(left: str) -> List[str]:
    """Variable names in the text before a declaration's `:`: `VAR x, y AT %MX0.0` gives x, y."""
    names = []
    for part in (left.splitlines() or [""])[-1].split(","):
        tokens = [t for t in part.split() if t.lower() not in _SECTION_WORDS]
        if tokens:
            names.append(tokens[0])
    return names


class _Declaration:
    """Scans one object's declaration text for a query, chunk by chunk (a chunk ends at `;`)."""

    def __init__(self, rec: ObjectRecord, query: List[str]):
        self.rec, self.query = rec, query
        self.text = rec.declaration or ""
        self.code = strip_noise(self.text)
        self.own_name_ok = len(query) == 1 or (rec.name or "").lower() == query[-2]
        self.refs: List[Reference] = []

    def add(self, at: int, role: str) -> None:
        line = _line_of(self.code, at)
        self.refs.append(Reference(self.rec.guid, self.rec.name, self.rec.kind, self.rec.path,
                                   "declaration:%d" % line, role, _source_line(self.text, line)))

    def declared(self, name: str, at: int) -> None:
        if name.lower() == self.query[-1] and self.own_name_ok:
            self.add(at, "declared")

    def paths(self, text: str, base: int, role_of) -> None:
        for path in scan_paths(text, base):
            if _contains(path.segments, self.query):
                self.add(path.start, role_of(path))

    def header(self, chunk: str, offset: int) -> int:
        """Handle a leading `FUNCTION F : T` / `TYPE T : STRUCT` header; return where the ordinary
        declarations in the chunk start. A header has a type only when its name is followed by the `:`
        (`PROGRAM P` has none; in `PROGRAM P VAR x : INT` the `:` is a variable's)."""
        match = _HEADER_RE.match(chunk) if offset == 0 else None  # only the first chunk can be the header
        if match is None:
            return 0
        if match.group(1):
            self.declared(match.group(1), offset + match.start(1))
        first_line_end = chunk.find("\n")
        colon = chunk.find(":")
        if colon == -1 or chunk[match.end():colon].strip():
            return match.end()
        struct = _STRUCT_RE.search(chunk, colon)
        ends = [e for e in (first_line_end, struct.start() if struct else -1) if e != -1]
        end = min(ends) if ends else len(chunk)
        self.paths(chunk[colon + 1:end], offset + colon + 1, lambda path: "type")
        return end

    def variables(self, chunk: str, offset: int) -> None:
        colon = chunk.find(":")
        if colon == -1:
            return
        for name in _declared_names(chunk[:colon]):
            self.declared(name, offset + colon)
        right_at = offset + colon + 1
        init = chunk.find(":=", colon)
        self.paths(chunk[colon + 1:], right_at,
                   lambda path: "type" if init == -1 or path.start < offset + init else "read")

    def scan(self) -> List[Reference]:
        offset = 0
        for chunk in self.code.split(";"):
            start = self.header(chunk, offset)
            self.variables(chunk[start:], offset + start)
            offset += len(chunk) + 1
        return self.refs


def _scan_declaration(rec: ObjectRecord, query: List[str]) -> List[Reference]:
    return _Declaration(rec, query).scan()


def _scan_graph(project: Project, rec: ObjectRecord, query: List[str], result: XrefResult) -> List[Reference]:
    decoded = decode_graph(rec, project.blobs[rec.guid], project.strings)
    unreadable = sum(1 for n in decoded.networks for i in n.items if i.kind == "unknown")
    if unreadable:
        result.notes.append("%s: %d record(s) could not be decoded; a reference there would be missed"
                            % (rec.name, unreadable))
    refs: List[Reference] = []
    for number, net in enumerate(decoded.networks, 1):
        for item in net.items:
            for role, label, expression in _graph_names(item):
                for path in scan_paths(expression):
                    if _contains(path.segments, query):
                        refs.append(Reference(rec.guid, rec.name, rec.kind, rec.path, "network %d" % number,
                                              "read" if path.in_index else role,
                                              label))
    return refs


def _graph_names(item) -> List[Tuple[str, str, str]]:
    """(role, label, expression) for each name an item carries."""
    d = item.decoded
    if item.kind == "element":
        label = "%s %r" % (item.heuristic["direction"], d["name"])
        return [("write" if item.heuristic["direction"] == "OUT" else "read", label, d["name"])]
    if item.kind == "box":
        label = "BOX %s" % d["box_type"] + (" instance=%s" % d["instance"] if d["instance"] else "")
        return [("type", label, d["box_type"]), ("call", label, d["instance"])]
    return []


def find_references(project: Project, query: str) -> XrefResult:
    """Every reference to `query` (a name or a dotted path) in the searched objects."""
    segments = [s.strip().lower() for s in query.split(".")]
    if not all(IDENT_RE.fullmatch(s) for s in segments):
        raise FormatError("not a name or dotted path: %r" % query)
    result = XrefResult(query)
    for rec in project.records():
        if rec.kind not in SEARCHED_KINDS:
            result.not_searched += 1
            continue
        result.searched += 1
        result.hits += _scan_declaration(rec, segments)
        if rec.kind == KIND_ST:
            result.hits += _scan_implementation(rec, segments)
        elif rec.kind == KIND_GRAPHICAL:
            result.hits += _scan_graph(project, rec, segments, result)
    return result


def render_xref_text(result: XrefResult) -> str:
    lines = [
        "# references to %r. Heuristic: matched by name (case-insensitive), no scope resolution; roles are read from the text "
        "around the name (ST) or from the element's IN/OUT label (LD/FBD, itself a heuristic); wiring is not decoded." % result.query,
        "# not searched: %d object(s) of kind other or unreadable (devices, tasks, I/O mappings: a variable "
        "mapped to a channel there is not found)." % result.not_searched,
    ]
    lines += ["# note: " + n for n in result.notes]
    for hit in result.hits:
        lines.append("%s (%s)  %s  %s  %s" % (
            "/".join(hit.path + [hit.name or "?"]), hit.kind, hit.where, hit.role, hit.text))
    objects = len({h.guid for h in result.hits})
    lines.append("%d reference(s) in %d object(s) of %d searched" % (len(result.hits), objects, result.searched))
    return "\n".join(lines)


def xref_to_dict(result: XrefResult) -> dict:
    return {
        "query": result.query, "heuristic": "matched by name, no scope resolution; roles are heuristics",
        "searched": result.searched, "not_searched": result.not_searched, "notes": result.notes,
        "hits": [{"guid": h.guid, "name": h.name, "kind": h.kind, "path": h.path, "where": h.where,
                  "role": h.role, "text": h.text} for h in result.hits],
    }
