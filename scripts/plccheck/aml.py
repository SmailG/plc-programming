"""AutomationML (IEC 62714) / CAEX (IEC 62424) checks, including links to PLCopen XML."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse

from .findings import Finding, error, warning
from .xmlutil import Node, XmlError, parse_file

CAEX3_NS = "http://www.dke.de/CAEX"
DATA_CONNECTORS = ("ExternalDataConnector", "PLCopenXMLInterface", "COLLADAInterface",
                   "ExternalDataReference", "LogicModelInterface")


def _resolve(ref: str, base: Path) -> tuple[Path | None, str]:
    u = urlparse(ref)
    if u.scheme and u.scheme != "file":
        return None, u.fragment
    p = unquote(u.path).lstrip("/") if u.scheme == "file" else unquote(u.path)
    return (base / p) if p else None, u.fragment


def _global_ids(target: Path, cache: dict[Path, set[str] | None]) -> set[str] | None:
    """The globalId and uuid values of a referenced PLCopen file, or None if it is not well-formed XML.

    Parsed once per file: every interface that links to the same file would otherwise parse and walk
    it again, so a file of n links to itself costs n parses of an n-link document.
    """
    key = target.resolve()  # `x.xml`, `./x.xml` and `a/../x.xml` are one file
    if key not in cache:
        try:
            doc = parse_file(target)
        except XmlError:
            cache[key] = None
        else:
            cache[key] = {v for n in doc.iter() for v in (n.get("globalId"), n.get("uuid")) if v is not None}
    return cache[key]


def check_aml(root: Node, path: Path | None = None) -> list[Finding]:
    out: list[Finding] = []
    if root.tag != "CAEXFile":
        return [error("AM001", f"root element is <{root.tag}>, expected <CAEXFile>", root.line)]
    ver = root.get("SchemaVersion")
    if ver == "3.0" and root.ns != CAEX3_NS:
        out.append(error("AM002", f"SchemaVersion 3.0 requires namespace {CAEX3_NS}", root.line))
    if ver == "2.15" and root.ns:
        out.append(error("AM002", "CAEX 2.15 files have no namespace", root.line))
    if ver not in ("2.15", "3.0"):
        out.append(warning("AM002", f"unexpected CAEX SchemaVersion '{ver}'", root.line))
    if ver == "3.0" and root.find("SourceDocumentInformation") is None:
        out.append(error("AM003", "CAEX 3.0 requires <SourceDocumentInformation>", root.line))

    ids: dict[str, int] = {}
    for node in root.iter():
        nid = node.get("ID")
        if nid is None:
            continue
        if nid in ids:
            out.append(error("AM004", f"duplicate ID {nid} (first at line {ids[nid]})", node.line))
        ids[nid] = node.line

    iface_names: set[str] = set()
    for node in root.iter("ExternalInterface"):
        owner = node.parent
        if owner is not None and owner.get("ID"):
            iface_names.add(f"{owner.get('ID')}:{node.get('Name')}")
    for link in root.iter("InternalLink"):
        for side in ("RefPartnerSideA", "RefPartnerSideB"):
            ref = link.get(side)
            if ref and ref not in ids and ref not in iface_names:
                out.append(warning("AM005", f"InternalLink {side} '{ref}' matches no interface ID in this file", link.line))

    base = path.parent if path is not None else None
    plcopen_ids: dict[Path, set[str] | None] = {}
    for iface in root.iter("ExternalInterface"):
        cls = iface.get("RefBaseClassPath") or ""
        if not any(cls.endswith(c) for c in DATA_CONNECTORS):
            continue
        uri_attr = next((a for a in iface.findall("Attribute") if a.get("Name") == "refURI"), None)
        value = uri_attr.find("Value") if uri_attr is not None else None
        if value is None or not value.text.strip():
            out.append(warning("AM010", f"{cls.rsplit('/', 1)[-1]} '{iface.get('Name')}' has no refURI value", iface.line))
            continue
        if base is None:
            continue
        target, fragment = _resolve(value.text.strip(), base)
        if target is None:
            continue
        if not target.exists():
            out.append(warning("AM011", f"refURI target {target.name} not found next to this file", value.line))
        elif fragment and cls.endswith("PLCopenXMLInterface") and target.is_file():
            # An absolute refURI can name a directory, FIFO or device; only a regular file is read.
            ids = _global_ids(target, plcopen_ids)
            if ids is not None and fragment not in ids:
                out.append(warning("AM012", f"refURI fragment #{fragment} matches no globalId in {target.name}", value.line))
    for ext in root.findall("ExternalReference"):
        if base is not None and ext.get("Path") and not (base / ext.get("Path")).exists():
            out.append(warning("AM013", f"ExternalReference '{ext.get('Path')}' not found next to this file", ext.line))
    return out
