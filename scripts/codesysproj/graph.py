"""Decode the records of a graphical (LD/FBD) object into a flat, offset-ordered list.

Reverse-engineered from Machine Expert V2.x projects whose graphical POUs carry the editor
model string `Ld`. Nothing here is documented by the vendor. The split is deliberate:

* DECODED (read at fixed positions inside a recognised record, strings looked up in the
  string table): network comments, element name and type, box type and instance, the box
  header id, the modifier byte, pin names, the count byte of a coil record.
* HEURISTIC (an interpretation, marked `heuristic` in the output): IN or OUT direction
  (the byte before the element), the meaning of a modifier byte, which OUT elements are
  coils, box nesting (a box spans from its header id H to the next 8-byte id H+1), and the
  `ids` lists: qword-shaped runs found by scanning, where a one-byte id (below 256) can
  come out shifted by a byte (value times 256 plus the byte before it).
* NOT DECODED: which id connects to which, i.e. the wiring.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .binary import FormatError, read_varint
from .project import NETWORK_MARKERS, ObjectRecord

SENTINEL_ID = 733  # a constant filler id seen in every record of every project examined
MAX_ID = 0xFFFF  # ids are 8-byte little-endian qwords; only the low 16 bits were ever set
QWORD = 8
HEADER_LOOKAHEAD = 60  # bytes after a box's type/instance in which its header id must appear
MODIFIER_LOOKAHEAD = 40
BOX_TAGS = (0xE0, 0xE2, 0xE3, 0xE4, 0xE5)  # each followed by 02
ELEMENT_TAG = bytes.fromhex("df02")
INPUT_PREFIX = 0x69
COILS_TAG = bytes.fromhex("0f6f6c")
PARALLEL_TAG = bytes.fromhex("0fa601")
EMPTY_TAG = bytes.fromhex("9a01")
EMPTY_PAD = 5  # bytes between the empty-slot tag and its id (not decoded; shown raw)
INSTANCE_NONE = bytes.fromhex("de0200")
INSTANCE_TAG = bytes.fromhex("df02")
HEADER_ID_TAG = bytes.fromhex("dd02")
PINS_TAG, PINS_MID = 0x6A, 0x0E
EMPTY_STRING_INDEX = 0x27  # string-table index 39 is "" in every project examined
COMMENT_SKIP = 3 + 5  # network marker, then five bytes, then the comment varint
MODIFIER_MEANING = {0: "none", 1: "negated", 2: "set", 3: "reset"}  # unverified, see reference


@dataclass
class Item:
    offset: int
    kind: str  # element | box | coils | parallel_marker | empty | pins | unknown
    decoded: Dict[str, object] = field(default_factory=dict)
    heuristic: Dict[str, object] = field(default_factory=dict)
    ids: List[int] = field(default_factory=list)


@dataclass
class Network:
    offset: int
    comment: Optional[str]
    tag: str  # "e1 02" or "e7 02": two network record tags, difference not decoded
    items: List[Item] = field(default_factory=list)
    ids: List[int] = field(default_factory=list)


@dataclass
class GraphDecode:
    guid: str
    name: Optional[str]
    language: Optional[str]
    networks: List[Network] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def _string_at(data: bytes, pos: int, strings: Dict[int, str]) -> Tuple[Optional[str], int, int]:
    """(text, string index, position after). Text is None when the index is not in the table."""
    index, after = read_varint(data, pos)
    return strings.get(index), index, after


def _is_id(data: bytes, pos: int) -> bool:
    return (pos + QWORD <= len(data) and data[pos + 2:pos + QWORD] == b"\x00" * 6
            and (data[pos] != 0 or data[pos + 1] != 0))


def _parse_box(data: bytes, pos: int, strings: Dict[int, str]) -> Optional[Tuple[Item, int]]:
    if pos + 1 >= len(data) or data[pos] not in BOX_TAGS or data[pos + 1] != 2:
        return None
    try:
        box_type, _, after = _string_at(data, pos + 2, strings)
        if data[after:after + 3] == INSTANCE_NONE:
            instance: Optional[str] = ""
            after += 3
        elif data[after:after + 2] == INSTANCE_TAG:
            instance, _, after = _string_at(data, after + 2, strings)
        else:
            return None
    except FormatError:
        return None
    if box_type is None:
        return None
    window = data[after:after + HEADER_LOOKAHEAD]
    found = window.find(HEADER_ID_TAG)
    while found != -1:
        start = found + len(HEADER_ID_TAG) + QWORD
        if window[start:start + 1] == b"\x01" and len(window) >= start + 1 + QWORD:
            header_id = struct.unpack_from("<Q", window, start + 1)[0]
            if header_id != SENTINEL_ID and header_id <= MAX_ID:
                item = Item(pos, "box", {"tag": "%02x 02" % data[pos], "box_type": box_type,
                                          "instance": instance, "header_id": header_id})
                trailer = data.find(struct.pack("<Q", header_id + 1), after)
                if trailer != -1:
                    item.heuristic["span_end"] = trailer + QWORD
                return item, after
        found = window.find(HEADER_ID_TAG, found + 1)
    return None


def _unknown(data: bytes, pos: int, reason: str, after: int) -> Tuple[Item, int]:
    return Item(pos, "unknown", {"reason": reason, "hex": data[pos:pos + 16].hex(" ")}), after


def _parse_element(data: bytes, pos: int, strings: Dict[int, str]) -> Tuple[Item, int]:
    direction = "IN" if pos > 0 and data[pos - 1] == INPUT_PREFIX else "OUT"
    item = Item(pos, "element", {}, {"direction": direction})
    after = pos + len(ELEMENT_TAG)
    try:
        if data[after] == EMPTY_STRING_INDEX:
            item.decoded["name"] = ""
            after += 1
        else:
            name, index, after = _string_at(data, after, strings)
            if name is None:
                return _unknown(data, pos, "element name index %d is not in the string table" % index,
                                pos + len(ELEMENT_TAG))
            item.decoded["name"] = name
            if after < len(data) and data[after] != EMPTY_STRING_INDEX:
                item.decoded["type"], _, after = _string_at(data, after, strings)
    except (FormatError, IndexError):
        return _unknown(data, pos, "element record runs past the end of the object", len(data))
    at = data.find(HEADER_ID_TAG, after, after + MODIFIER_LOOKAHEAD)
    if at != -1 and at + 2 < len(data):
        item.decoded["modifier"] = data[at + 2]
        item.heuristic["modifier_meaning"] = MODIFIER_MEANING.get(data[at + 2], "unknown code")
    else:
        item.decoded["modifier"] = None
    return item, after


def _parse_pins(data: bytes, pos: int, strings: Dict[int, str]) -> Optional[Tuple[Item, int]]:
    if pos + 3 > len(data) or data[pos] != PINS_TAG or data[pos + 2] != PINS_MID:
        return None
    names: List[Optional[str]] = []
    after = pos + 3
    try:
        for _ in range(data[pos + 1]):
            text, _, after = _string_at(data, after, strings)
            names.append(text)
    except FormatError:
        return None
    return Item(pos, "pins", {"names": names}), after


def _next_item(data: bytes, pos: int, strings: Dict[int, str]) -> Optional[Tuple[Item, int]]:
    if data.startswith(COILS_TAG, pos) and pos + 4 <= len(data):
        return Item(pos, "coils", {"count": data[pos + 3]}), pos + 4
    if data.startswith(PARALLEL_TAG, pos) and pos + 4 <= len(data):
        return Item(pos, "parallel_marker", {"value": data[pos + 3]}), pos + 4
    if data.startswith(EMPTY_TAG, pos) and _is_id(data, pos + 2 + EMPTY_PAD):
        id_at = pos + 2 + EMPTY_PAD
        return Item(pos, "empty", {"raw": data[pos + 2:id_at].hex(" "),
                                   "id": struct.unpack_from("<Q", data, id_at)[0]}), id_at + QWORD
    parsed = _parse_box(data, pos, strings)
    if parsed is None and data.startswith(ELEMENT_TAG, pos):
        parsed = _parse_element(data, pos, strings)
    return parsed or _parse_pins(data, pos, strings)


def _scan_network(data: bytes, start: int, net: Network, strings: Dict[int, str]) -> None:
    pos = start
    owner: List[int] = net.ids
    coils_left = 0
    while pos < len(data):
        found = _next_item(data, pos, strings)
        if found is not None:
            item, after = found
            if item.kind == "coils":
                coils_left = int(item.decoded["count"])
            elif item.kind == "element" and coils_left and item.heuristic["direction"] == "OUT":
                item.heuristic["role"] = "coil"
                coils_left -= 1
            net.items.append(item)
            owner = item.ids
            pos = max(after, pos + 1)
        elif _is_id(data, pos):
            value = struct.unpack_from("<Q", data, pos)[0]
            if value != SENTINEL_ID:
                owner.append(value)
            pos += QWORD
        else:
            pos += 1


def _box_depths(net: Network) -> None:
    spans = [(i.offset, i.heuristic["span_end"]) for i in net.items
             if i.kind == "box" and "span_end" in i.heuristic]
    for item in net.items:
        item.heuristic["depth"] = sum(1 for lo, hi in spans if lo < item.offset < hi)


def _network_starts(data: bytes) -> List[int]:
    starts: List[int] = []
    for marker in NETWORK_MARKERS:
        at = data.find(marker)
        while at != -1:
            starts.append(at)
            at = data.find(marker, at + 1)
    return sorted(starts)


def decode_graph(rec: ObjectRecord, data: bytes, strings: Dict[int, str]) -> GraphDecode:
    """Decode networks and their records. Unrecognised bytes are skipped silently except
    where a record was recognised but could not be read: those become `unknown` items."""
    result = GraphDecode(rec.guid, rec.name, rec.language)
    starts = _network_starts(data)
    if not starts:
        result.notes.append("no network records found; not a graphical object in the observed layout")
        return result
    for number, start in enumerate(starts):
        end = starts[number + 1] if number + 1 < len(starts) else len(data)
        segment = data[:end]
        comment: Optional[str] = None
        body = start + COMMENT_SKIP
        if body < len(segment) and segment[body] != 0:
            try:
                comment, index, body = _string_at(segment, body, strings)
                if comment is None:
                    result.notes.append("network %d: comment index %d is not in the string table" % (number + 1, index))
            except FormatError:
                result.notes.append("network %d: record ends inside the comment" % (number + 1))
                body = end
        net = Network(start, comment, data[start + 1:start + 3].hex(" "))
        _scan_network(segment, body, net, strings)
        _box_depths(net)
        result.networks.append(net)
    unknown = sum(1 for n in result.networks for i in n.items if i.kind == "unknown")
    if unknown:
        result.notes.append("%d record(s) could not be decoded; see the `unknown` items" % unknown)
    return result


def graph_to_dict(result: GraphDecode) -> dict:
    return {
        "guid": result.guid, "name": result.name, "language": result.language,
        "legend": "decoded = read from the record by the observed layout; heuristic = interpretation, "
                  "including every ids list; wiring (which id connects to which) is not decoded; bytes that match no "
                  "recognised record are skipped without a note, so a clean run is not full coverage",
        "notes": result.notes,
        "networks": [
            {"offset": n.offset, "tag": n.tag, "comment": n.comment, "heuristic": {"ids": n.ids},
             "items": [{"offset": i.offset, "kind": i.kind, "decoded": i.decoded,
                        "heuristic": dict(i.heuristic, ids=i.ids)} for i in n.items]}
            for n in result.networks
        ],
    }


def _item_text(item: Item) -> str:
    d, h = item.decoded, item.heuristic
    indent = "  " * int(h.get("depth", 0))
    if item.kind == "element":
        text = "%s %r" % (h["direction"] + ("/coil" if h.get("role") else ""), d["name"])
        if d.get("type"):
            text += " type=%s" % d["type"]
        text += " mod=%s" % d["modifier"]
        if h.get("modifier_meaning") not in (None, "none"):
            text += " ~%s" % h["modifier_meaning"]
    elif item.kind == "box":
        text = "BOX %s" % d["box_type"] + (" instance=%s" % d["instance"] if d["instance"] else "")
        text += " id=%s" % d["header_id"]
    elif item.kind == "unknown":
        text = "UNKNOWN %s [%s]" % (d["reason"], d["hex"])
    else:
        text = "%s %s" % (item.kind, " ".join("%s=%s" % kv for kv in d.items()))
    ids = " ids~%s" % item.ids if item.ids else ""
    return "%5d %s%s%s" % (item.offset, indent, text, ids)


def render_graph_text(result: GraphDecode) -> str:
    lines = [
        "# graphical object %s  name=%s  language=%s (heuristic)" % (result.guid, result.name, result.language),
        "# decoded: names, types, modifier byte, box ids, comments. '~' marks a heuristic: direction "
        "(IN/OUT), '/coil', modifier meaning, indentation = box nesting, ids~ (a small id can be shifted by a byte).",
        "# NOT decoded: wiring (which id connects to which). Verify wiring in the IDE or a PLCopen XML export.",
        "# Bytes that match no recognised record are skipped without a note: a clean run is not full coverage.",
    ]
    lines += ["# note: " + note for note in result.notes]
    for number, net in enumerate(result.networks, 1):
        comment = "none" if net.comment is None else repr(net.comment)
        lines.append("")
        lines.append("network %d @%d tag=%s comment=%s%s" % (number, net.offset, net.tag, comment,
                                                           " ids~%s" % net.ids if net.ids else ""))
        lines += [_item_text(i) for i in net.items]
    return "\n".join(lines)
