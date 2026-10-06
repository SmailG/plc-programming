"""DEXPI P&ID exchange: Proteus XML (DEXPI 1.x) and DEXPI XML (2.0), checked lightly."""

from __future__ import annotations

from .findings import Finding, error, warning
from .xmlutil import Node

REF_ATTRS = ("FromID", "ToID", "ItemID")


def check_dexpi(root: Node) -> list[Finding]:
    out: list[Finding] = []
    if root.tag == "PlantModel":
        info = root.find("PlantInformation")
        if info is None:
            out.append(error("DX001", "<PlantModel> requires <PlantInformation>", root.line))
        elif info.get("SchemaVersion") is None:
            out.append(warning("DX002", "<PlantInformation> has no SchemaVersion", info.line))
        id_attr = "ID"
    elif root.tag == "Model":
        id_attr = "id"
    else:
        return [error("DX001", f"root element is <{root.tag}>, expected <PlantModel> (DEXPI 1.x) or <Model> (DEXPI 2.0)", root.line)]

    ids: dict[str, int] = {}
    for node in root.iter():
        nid = node.get(id_attr) if node.tag != "Import" else None
        if nid is None:
            continue
        if nid in ids:
            out.append(error("DX003", f"duplicate {id_attr} '{nid}' (first at line {ids[nid]})", node.line))
        ids[nid] = node.line
    if root.tag == "PlantModel":
        for node in root.iter():
            for attr in REF_ATTRS:
                ref = node.get(attr)
                if ref and ref not in ids:
                    out.append(error("DX004", f"<{node.tag} {attr}=\"{ref}\"> refers to no element in this file", node.line))
    return out
