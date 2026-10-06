"""PLCopen XML (TC6 v2.0 / v2.01) and IEC 61131-10 semantic checks.

The XSD cannot catch what these check: duplicate localIds, dangling connections,
missing SFC durations, broken ST inside a body, POUs hidden in vendor addData.
Schema validation is separate (plc_validate.py --xsd), because neither schema can be
redistributed with this plugin.
"""

from __future__ import annotations

from .findings import Finding, error, warning, with_context
from .st import lint_st, scan_call_findings
from .xmlutil import Node

TC6_NAMESPACES = {
    "http://www.plcopen.org/xml/tc6_0200": "2.0",
    "http://www.plcopen.org/xml/tc6_0201": "2.01",
    "http://www.plcopen.org/xml/tc6.xsd": "1.x",
}
IEC_61131_10_NS = "www.iec.ch/public/TC65SC65BWG7TF10"
XHTML_NS = "http://www.w3.org/1999/xhtml"
BODY_LANGS = ("IL", "ST", "FBD", "LD", "SFC")
QUALIFIERS = {"P1", "N", "P0", "R", "S", "L", "D", "P", "DS", "DL", "SD", "SL"}
TIMED = {"L", "D", "DS", "DL", "SD", "SL"}
STANDARD_FBS = {
    "TON", "TOF", "TP", "R_TRIG", "F_TRIG", "CTU", "CTD", "CTUD", "SR", "RS",
    "LTON", "LTOF", "LTP", "CTU_DINT", "CTU_LINT", "CTU_UDINT", "CTU_ULINT",
    "CTD_DINT", "CTD_LINT", "CTD_UDINT", "CTD_ULINT", "CTUD_DINT", "CTUD_LINT",
    "CTUD_UDINT", "CTUD_ULINT",
}
VENDOR_POU_DATA = "http://www.3s-software.com/plcopenxml/pou"


def _formatted_text(node: Node) -> tuple[str, int]:
    """Text of a formattedText element (ST/IL body, xhtml:p or xhtml wrapper)."""
    parts = [c for c in node.children if c.ns == XHTML_NS]
    if not parts:
        return node.text, node.text_line or node.line
    first = parts[0]
    return "".join(p.all_text() for p in parts), first.text_line or first.line


def _derived_type(var: Node) -> str | None:
    t = var.find("type")
    if t is None:
        return None
    d = t.find("derived")
    return d.get("name") if d is not None else None


def check_plcopen(root: Node) -> list[Finding]:
    out: list[Finding] = []
    if root.tag != "project":
        return [error("PX001", f"root element is <{root.tag}>, expected <project>", root.line)]
    if root.ns not in TC6_NAMESPACES:
        out.append(warning("PX002", f"unknown namespace '{root.ns}' (expected tc6_0200 or tc6_0201)", root.line))

    fh = root.find("fileHeader")
    if fh is None:
        out.append(error("PX003", "missing <fileHeader>", root.line))
    else:
        for attr in ("companyName", "productName", "productVersion", "creationDateTime"):
            if fh.get(attr) is None:
                out.append(error("PX003", f"<fileHeader> lacks required attribute {attr}", fh.line))

    ch = root.find("contentHeader")
    if ch is None:
        out.append(error("PX004", "missing <contentHeader>", root.line))
    else:
        if ch.get("name") is None:
            out.append(error("PX004", "<contentHeader> lacks required attribute name", ch.line))
        ci = ch.find("coordinateInfo")
        if ci is None:
            out.append(error("PX004", "<contentHeader> lacks <coordinateInfo>", ch.line))
        else:
            for lang in ("fbd", "ld", "sfc"):
                el = ci.find(lang)
                if el is None or el.find("scaling") is None:
                    out.append(error("PX004", f"<coordinateInfo> lacks <{lang}><scaling/>", ci.line))

    types = root.find("types")
    pous: list[Node] = []
    type_names: set[str] = set()
    if types is None or types.find("dataTypes") is None or types.find("pous") is None:
        out.append(error("PX005", "<types> must contain <dataTypes> and <pous> (both may be empty)", (types or root).line))
    if types is not None:
        seen: dict[str, int] = {}
        for dt in types.find("dataTypes").findall("dataType") if types.find("dataTypes") is not None else []:
            name = dt.get("name", "")
            if name.upper() in seen:
                out.append(warning("PX011", f"data type '{name}' defined twice (identifiers are case-insensitive)", dt.line))
            seen[name.upper()] = dt.line
            type_names.add(name.upper())
        pous = types.find("pous").findall("pou") if types.find("pous") is not None else []
        seen = {}
        for pou in pous:
            name = pou.get("name", "")
            if name.upper() in seen:
                out.append(warning("PX011", f"POU '{name}' defined twice (identifiers are case-insensitive)", pou.line))
            seen[name.upper()] = pou.line
            type_names.add(name.upper())
    inst = root.find("instances")
    if inst is None or inst.find("configurations") is None:
        out.append(error("PX005", "missing <instances><configurations/> (may be empty)", root.line))

    for data in root.iter("data"):
        if data.get("name") is None or data.get("handleUnknown") is None:
            out.append(error("PX006", "<addData><data> requires name and handleUnknown", data.line))

    if not pous and any(d.get("name") == VENDOR_POU_DATA for d in root.iter("data")):
        out.append(warning(
            "PX050",
            "the standard <pous> list is empty; the POUs live in CODESYS/TwinCAT vendor <addData>. "
            "Only a CODESYS-family importer will see them", root.line))

    for pou in pous:
        out.extend(_check_pou(pou, type_names))

    if inst is not None:
        pou_names = {p.get("name", "").upper() for p in pous}
        for task in inst.iter("task"):
            interval = task.get("interval")
            if interval and interval.upper() in ("PT0S", "T#0S", "T#0MS"):
                out.append(warning("PX051", f"task '{task.get('name')}' has interval {interval}; the real cycle may be in vendor addData (TaskSettings)", task.line))
        for pi in inst.iter("pouInstance"):
            tn = pi.get("typeName", "")
            if pous and tn and tn.upper() not in pou_names:
                out.append(warning("PX052", f"pouInstance '{pi.get('name')}' refers to unknown POU type '{tn}'", pi.line))
    return out


def _check_pou(pou: Node, type_names: set[str]) -> list[Finding]:
    out: list[Finding] = []
    name = pou.get("name")
    ptype = pou.get("pouType")
    ctx = f"POU {name}"
    if not name:
        out.append(error("PX010", "<pou> without a name", pou.line))
    if ptype not in ("function", "functionBlock", "program"):
        out.append(error("PX010", f"pouType '{ptype}' is not function | functionBlock | program", pou.line, ctx))
    iface = pou.find("interface")
    instances: dict[str, tuple[str, str, int]] = {}
    if iface is not None:
        if ptype == "function" and iface.find("returnType") is None:
            out.append(warning("PX012", "function has no <returnType>", iface.line, ctx))
        declared: dict[str, int] = {}
        for section in iface.children:
            for var in section.findall("variable"):
                vname = var.get("name", "")
                if vname.upper() in declared:
                    out.append(error("PX014", f"variable '{vname}' declared twice (first at line {declared[vname.upper()]})", var.line, ctx))
                declared[vname.upper()] = var.line
                dname = _derived_type(var)
                if dname:
                    if dname.upper() in STANDARD_FBS:
                        instances[vname.upper()] = (vname, dname.upper(), var.line)
                    elif dname.upper() not in type_names:
                        out.append(warning("PX023", f"type '{dname}' of '{vname}' is not defined in this file (fine if a library provides it)", var.line, ctx))

    analyses = []
    bodies = [(b, ctx) for b in pou.findall("body")]
    for group, label in (("actions", "action"), ("transitions", "transition")):
        g = pou.find(group)
        for item in g.findall(label) if g is not None else []:
            bodies += [(b, f"{ctx} {label} {item.get('name')}") for b in item.findall("body")]
    if not pou.findall("body"):
        out.append(error("PX013", "POU has no <body>", pou.line, ctx))
    for body, bctx in bodies:
        langs = [c for c in body.children if c.tag in BODY_LANGS]
        if len(langs) != 1:
            out.append(error("PX013", f"<body> must contain exactly one of IL/ST/FBD/LD/SFC, found {len(langs)}", body.line, bctx))
            continue
        out.extend(_check_lang(langs[0], bctx, analyses))
    if analyses:
        out.extend(with_context(scan_call_findings(analyses, instances), f"{ctx} (ST)"))
    return out


def _check_lang(lang: Node, ctx: str, analyses: list) -> list[Finding]:
    if lang.tag == "ST":
        text, line0 = _formatted_text(lang)
        f, an = lint_st(text, "body")
        analyses.append(an.shifted(line0 - 1))
        return with_context(f, f"{ctx} (ST)", line0 - 1)
    if lang.tag in ("FBD", "LD", "SFC"):
        return _check_graph(lang, ctx, analyses)
    return []


def _own_nodes(graph: Node):
    """Nodes of this graph, not descending into nested <inline> bodies (their own scope)."""
    stack = list(reversed(graph.children))
    while stack:
        node = stack.pop()
        yield node
        if node.tag != "inline":
            stack.extend(reversed(node.children))


def _check_graph(graph: Node, ctx: str, analyses: list) -> list[Finding]:
    out: list[Finding] = []
    ids: dict[str, int] = {}
    nodes = list(_own_nodes(graph))
    for node in nodes:
        lid = node.get("localId")
        if lid is None:
            continue
        if lid in ids:
            out.append(error("PX020", f"duplicate localId {lid} (<{node.tag}>; first at line {ids[lid]})", node.line, ctx))
        else:
            ids[lid] = node.line
    for conn in (n for n in nodes if n.tag == "connection"):
        ref = conn.get("refLocalId")
        if ref is None:
            out.append(error("PX021", "<connection> without refLocalId", conn.line, ctx))
        elif ref not in ids:
            out.append(error("PX021", f"connection refers to localId {ref}, which does not exist in this body", conn.line, ctx))
    for block in (n for n in nodes if n.tag == "block"):
        if not block.get("typeName"):
            out.append(error("PX022", "<block> without typeName", block.line, ctx))
    if graph.tag == "SFC":
        steps = [n for n in nodes if n.tag == "step"]
        initial = [s for s in steps if s.get("initialStep") in ("true", "1")]
        if steps and len(initial) != 1:
            out.append(error("PX032", f"an SFC needs exactly one initial step, found {len(initial)}", graph.line, ctx))
        for action in (n for n in nodes if n.tag == "action"):
            q = action.get("qualifier", "N")
            if q not in QUALIFIERS:
                out.append(error("PX030", f"unknown action qualifier '{q}'", action.line, ctx))
            elif q in TIMED and not action.get("duration"):
                out.append(error("PX031", f"qualifier {q} needs a duration", action.line, ctx))
    for inline in (n for n in nodes if n.tag == "inline"):
        for lang in (c for c in inline.children if c.tag in BODY_LANGS):
            out.extend(_check_lang(lang, f"{ctx} inline", analyses))
    return out


def check_iec61131_10(root: Node) -> list[Finding]:
    """IEC 61131-10:2019. A different schema from TC6 v2.01, checked lightly."""
    out: list[Finding] = []
    if root.tag != "Project":
        return [error("PX101", f"root element is <{root.tag}>, expected <Project>", root.line)]
    if root.get("schemaVersion") is None:
        out.append(warning("PX102", "<Project> has no schemaVersion", root.line))
    for bc in root.iter("BodyContent"):
        kind = (bc.get("type") or "").rsplit(":", 1)[-1]
        st = bc.find("ST")
        if kind == "ST" and st is not None:
            f, _ = lint_st(st.text, "body")
            out.extend(with_context(f, "IEC 61131-10 ST body", (st.text_line or st.line) - 1))
        outs = {n.get("connectionPointOutId") for n in bc.iter() if n.get("connectionPointOutId")}
        for conn in bc.iter("Connection"):
            ref = conn.get("refConnectionPointOutId")
            if ref and ref not in outs:
                out.append(warning("PX121", f"Connection refers to connectionPointOutId {ref}, not found in this body", conn.line))
    return out
