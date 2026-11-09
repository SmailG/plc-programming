"""Text and JSON renderings of a decoded graph (see graph.py for what is decoded and what is a heuristic)."""

from __future__ import annotations

from .graph import GraphDecode, Item


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


def item_label(item: Item, stable: bool = False) -> str:
    """One item as text, indented by box depth. `stable` leaves out everything that changes when the
    project is saved again without a logic change: header ids, empty-slot bytes and ids, raw bytes."""
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
        text += "" if stable else " id=%s" % d["header_id"]
    elif item.kind == "unknown":
        text = "UNKNOWN %s" % d["reason"] + ("" if stable else " [%s]" % d["hex"])
    elif item.kind == "empty" and stable:
        text = "empty"
    else:
        text = "%s %s" % (item.kind, " ".join("%s=%s" % kv for kv in d.items()))
    return indent + text


def _item_text(item: Item) -> str:
    ids = " ids~%s" % item.ids if item.ids else ""
    return "%5d %s%s" % (item.offset, item_label(item), ids)


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
