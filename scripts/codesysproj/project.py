"""Open a `.project` zip: object inventory, parent chains, kinds and ST text.

Observed container layout (reverse-engineered; see the reference page):

* the `.project` is an ordinary zip; entries are flat: `<guid>.meta`, `<guid>.object`,
  `<guid>_decl_lineids.auxiliary`, ..., and one shared string table;
* `.meta` is a varint stream; the string-table text of one value equals the object's own
  guid, and the next two values are the parent guid and the object name;
* `.object` starts with a 20-byte header (magic 02 20 09 28, then a uint32 at offset 16
  holding the number of bytes that follow). Source text is not in the object: the object
  holds string-table indices. A text slot is `<marker> e5 02 <text index> <reference index>`
  where the reference string is `<guid>_Decl_LineIds` (declaration, marker 41) or
  `<guid>_Impl_LineIds` (implementation, marker 5b).

What is a fact and what is a guess is spelled out per field on `ObjectRecord`.
"""

from __future__ import annotations

import re
import struct
import zipfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .binary import FormatError, parse_string_table, read_varint
from . import zipread
from .zipread import entry_name, open_archive, read_entry

STRING_TABLE_NAME = "__shared_data_storage_string_table__.auxiliary"
OBJECT_MAGIC = bytes.fromhex("02200928")
OBJECT_HEADER_LEN = 20
LENGTH_FIELD_OFFSET = 16
DECL_MARKER = bytes.fromhex("41e502")
IMPL_MARKER = bytes.fromhex("5be502")
DECL_REF_SUFFIX = "_Decl_LineIds"
IMPL_REF_SUFFIX = "_Impl_LineIds"
NETWORK_MARKERS = (bytes.fromhex("0fe102"), bytes.fromhex("0fe702"))  # two network record tags
LANGUAGE_PREFIX = bytes.fromhex("0fe60248")
LANGUAGE_VARINT_INDEX = 5  # counted in varints from the start of the payload
PLC_LOGIC_NAME = "plc logic"

GUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_DECL_START_RE = re.compile(
    r"\s*(?:(?://[^\n]*\n|\(\*(?:(?!\*\)).)*\*\)|\{[^}]*\})\s*)*"
    r"(PROGRAM|FUNCTION_BLOCK|FUNCTION|METHOD|PROPERTY|ACTION|INTERFACE|TRANSITION|TYPE"
    r"|VAR_GLOBAL|VAR_CONFIG|VAR)\b",
    re.S,
)

KIND_ST = "st"
KIND_GRAPHICAL = "graphical"
KIND_GVL = "gvl"
KIND_DUT = "dut"
KIND_OTHER = "other"
KIND_UNREADABLE = "unreadable"
KINDS = (KIND_ST, KIND_GRAPHICAL, KIND_GVL, KIND_DUT, KIND_OTHER, KIND_UNREADABLE)


@dataclass
class ObjectRecord:
    """One object of the project.

    Decoded (read from the bytes by the observed layout): guid, name, parent_guid, path,
    declaration, implementation, problems. Heuristic (a classification of those bytes):
    kind, subtype, language, device, application.
    """

    guid: str
    name: Optional[str] = None
    parent_guid: Optional[str] = None
    path: List[str] = field(default_factory=list)  # ancestor names, root first
    kind: str = KIND_OTHER
    subtype: Optional[str] = None  # the declaration keyword: PROGRAM, FUNCTION_BLOCK, ...
    language: Optional[str] = None  # graphical objects: the editor-model string
    declaration: Optional[str] = None
    implementation: Optional[str] = None
    has_meta: bool = False
    has_object: bool = False
    problems: List[str] = field(default_factory=list)

    @property
    def device(self) -> Optional[str]:
        """Root-most ancestor (heuristic: the controller / device node)."""
        return self.path[0] if self.path else None

    @property
    def application(self) -> Optional[str]:
        """The node under 'Plc Logic' (heuristic; None when no ancestor has that name)."""
        for i, name in enumerate(self.path[:-1]):
            if name.lower() == PLC_LOGIC_NAME:
                return self.path[i + 1]
        return None


@dataclass
class Project:
    path: str
    strings: Dict[int, str]
    objects: Dict[str, ObjectRecord]
    blobs: Dict[str, bytes]  # guid -> raw .object bytes

    def records(self) -> List[ObjectRecord]:
        """Objects in tree order (by ancestor names, then name, then guid)."""
        return sorted(self.objects.values(), key=lambda r: (r.path, r.name or "", r.guid))


def _scan_varints(data: bytes, start: int = 0) -> List[int]:
    """Varints from `start` until the data stops being a clean varint stream."""
    values: List[int] = []
    pos = start
    while pos < len(data):
        try:
            value, pos = read_varint(data, pos)
        except FormatError:
            break
        values.append(value)
    return values


def parse_meta(data: bytes, guid: str, strings: Dict[int, str]) -> Tuple[str, str]:
    """Return (parent guid, name) read after the object's own guid in the varint stream."""
    texts = [strings.get(v) for v in _scan_varints(data)]
    if guid not in texts:
        raise FormatError("own guid not found in the meta stream")
    at = texts.index(guid)
    while at + 1 < len(texts) and texts[at + 1] == guid:  # some objects repeat their own guid
        at += 1
    parent, name = (texts[at + 1], texts[at + 2]) if at + 2 < len(texts) else (None, None)
    if parent is None or not GUID_RE.match(parent) or name is None:
        raise FormatError("own guid is not followed by a parent guid and a name")
    return parent, name


def _text_slot(data: bytes, marker: bytes, suffix: str, guid: str, strings: Dict[int, str],
               label: str, problems: List[str]) -> Optional[str]:
    """Text behind the slot `marker e5 02 <text> <reference>`; None if absent or undecodable.

    A marker whose reference string is not `<guid><suffix>` is data that happens to look
    like the marker, and is ignored.
    """
    hits: List[int] = []
    at = data.find(marker, OBJECT_HEADER_LEN)
    while at != -1:
        try:
            text_index, pos = read_varint(data, at + len(marker))
            ref_index, _ = read_varint(data, pos)
        except FormatError:
            text_index = ref_index = -1
        if strings.get(ref_index) == guid + suffix:
            hits.append(text_index)
        at = data.find(marker, at + 1)
    if not hits:
        return None
    if len(set(hits)) > 1:
        problems.append("%d %s slots with different text; using the first" % (len(set(hits)), label))
    if hits[0] not in strings:
        problems.append("%s text index %d is not in the string table" % (label, hits[0]))
        return None
    return strings[hits[0]]


def _language(data: bytes, strings: Dict[int, str]) -> Optional[str]:
    payload = data[OBJECT_HEADER_LEN:]
    if not payload.startswith(LANGUAGE_PREFIX):
        return None
    values = _scan_varints(payload)
    if len(values) <= LANGUAGE_VARINT_INDEX:
        return None
    return strings.get(values[LANGUAGE_VARINT_INDEX])


def declaration_keyword(text: str) -> Optional[str]:
    match = _DECL_START_RE.match(text)
    return match.group(1) if match else None


def classify_object(rec: ObjectRecord, data: bytes, strings: Dict[int, str]) -> None:
    """Fill kind, subtype, language, declaration and implementation from `.object` bytes."""
    if len(data) < OBJECT_HEADER_LEN:
        rec.kind = KIND_UNREADABLE
        rec.problems.append("object is %d bytes, shorter than the %d-byte header" % (len(data), OBJECT_HEADER_LEN))
        return
    if data[:4] != OBJECT_MAGIC:
        rec.kind = KIND_UNREADABLE
        rec.problems.append("object does not start with the magic 02 20 09 28 (starts %s)" % data[:4].hex(" "))
        return
    declared = struct.unpack_from("<I", data, LENGTH_FIELD_OFFSET)[0]
    if declared != len(data) - OBJECT_HEADER_LEN:
        rec.kind = KIND_UNREADABLE
        rec.problems.append("header says %d payload bytes, the object has %d (truncated or corrupt)"
                            % (declared, len(data) - OBJECT_HEADER_LEN))
        return
    rec.declaration = _text_slot(data, DECL_MARKER, DECL_REF_SUFFIX, rec.guid, strings, "declaration", rec.problems)
    rec.implementation = _text_slot(data, IMPL_MARKER, IMPL_REF_SUFFIX, rec.guid, strings, "implementation", rec.problems)
    keyword = declaration_keyword(rec.declaration) if rec.declaration is not None else None
    if any(marker in data for marker in NETWORK_MARKERS):
        rec.kind = KIND_GRAPHICAL
        rec.language = _language(data, strings)
        rec.subtype = keyword
    elif rec.declaration is not None and rec.implementation is not None:
        rec.kind = KIND_ST
        rec.subtype = keyword
    elif keyword is not None and keyword.startswith("VAR"):
        rec.kind = KIND_GVL
        rec.subtype = keyword
    elif keyword == "TYPE":
        rec.kind = KIND_DUT
        rec.subtype = keyword
    else:
        rec.kind = KIND_OTHER


def _link_parents(objects: Dict[str, ObjectRecord]) -> None:
    for rec in objects.values():
        chain: List[str] = []
        seen = {rec.guid}
        parent = rec.parent_guid
        while parent in objects and parent not in seen:
            seen.add(parent)
            chain.append(objects[parent].name or parent)
            parent = objects[parent].parent_guid
        if parent in seen:
            rec.problems.append("parent chain loops back on itself")
        rec.path = list(reversed(chain))


def load_project(path: str) -> Project:
    """Read every object of the `.project`. Per-object problems go to `ObjectRecord.problems`;
    a file that is not a project at all raises FormatError."""
    archive = open_archive(path)
    with archive:
        entries: Dict[str, Dict[str, zipfile.ZipInfo]] = {}
        table_info = None
        for info in archive.infolist():
            name = entry_name(info)
            if name == STRING_TABLE_NAME:
                table_info = info
                continue
            stem, dot, ext = name.rpartition(".")
            if dot and ext in ("meta", "object") and GUID_RE.match(stem):
                entries.setdefault(stem, {})[ext] = info
        if table_info is None:
            raise FormatError("%s: no %s entry; not a CODESYS 3.5 project" % (path, STRING_TABLE_NAME))
        strings = parse_string_table(read_entry(archive, table_info))
        objects: Dict[str, ObjectRecord] = {}
        blobs: Dict[str, bytes] = {}
        total = 0
        for guid, parts in entries.items():
            rec = ObjectRecord(guid=guid, has_meta="meta" in parts, has_object="object" in parts)
            objects[guid] = rec
            if rec.has_meta:
                try:
                    rec.parent_guid, rec.name = parse_meta(read_entry(archive, parts["meta"]), guid, strings)
                except FormatError as exc:
                    rec.problems.append("meta: %s" % exc)
            else:
                rec.problems.append("no .meta entry: name and parent unknown")
            if rec.has_object:
                try:
                    blobs[guid] = read_entry(archive, parts["object"])
                    total += len(blobs[guid])
                except FormatError as exc:
                    rec.kind = KIND_UNREADABLE
                    rec.problems.append("object: %s" % exc)
                else:
                    if total > zipread.TOTAL_CAP:
                        raise FormatError("%s: objects inflate past %d bytes in total; not read" % (path, zipread.TOTAL_CAP))
                    classify_object(rec, blobs[guid], strings)
            else:
                rec.problems.append("no .object entry")
    _link_parents(objects)
    return Project(path=path, strings=strings, objects=objects, blobs=blobs)


def find_objects(project: Project, query: str) -> List[ObjectRecord]:
    """Objects matching a full guid, a unique guid prefix (8+ chars), or a name (IEC names ignore case)."""
    exact = project.objects.get(query.lower())
    if exact is not None:
        return [exact]
    if len(query) >= 8:
        prefix = [r for g, r in project.objects.items() if g.startswith(query.lower())]
        if prefix:
            return sorted(prefix, key=lambda r: r.guid)
    return [r for r in project.records() if (r.name or "").lower() == query.lower()]
