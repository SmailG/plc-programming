"""Siemens TIA Portal Openness export XML ("SimaticML") and SIMATIC SD checks.

Namespace versions per TIA version come from genuine exports (see the siemens skill,
references/simaticml-and-sources.md). TIA refuses to import a namespace version it
does not expect, so a mismatch is the most expensive mistake in generated SimaticML.
"""

from __future__ import annotations

import re

from .findings import Finding, error, warning
from .xmlutil import Node

NS_BASE = "http://www.siemens.com/automation/Openness/SW/"
# TIA version -> {schema family: expected vN}. Only versions seen in real exports.
EXPECTED_NS = {
    "V15.1": {"Interface": "v3", "NetworkSource/FlgNet": "v3"},
    "V16": {"Interface": "v4", "NetworkSource/StructuredText": "v3"},
    "V17": {"Interface": "v5", "NetworkSource/FlgNet": "v4", "NetworkSource/StructuredText": "v3"},
    "V18": {"Interface": "v5", "NetworkSource/FlgNet": "v4", "NetworkSource/StructuredText": "v3", "NetworkSource/Graph": "v5"},
    "V19": {"Interface": "v5", "NetworkSource/FlgNet": "v5", "NetworkSource/StructuredText": "v4"},
    "V20": {"Interface": "v5", "NetworkSource/FlgNet": "v5", "NetworkSource/StructuredText": "v4"},
}
BLOCK_TAGS = {
    "SW.Blocks.OB", "SW.Blocks.FB", "SW.Blocks.FC", "SW.Blocks.GlobalDB", "SW.Blocks.InstanceDB",
    "SW.Blocks.ArrayDB", "SW.Types.PlcStruct", "SW.Tags.PlcTagTable",
}
LANGUAGES = {"LAD", "FBD", "SCL", "STL", "GRAPH", "DB", "F_LAD", "F_FBD", "F_DB", "CEM"}
SECTIONS = {
    "SW.Blocks.FC": {"Input", "Output", "InOut", "Temp", "Constant", "Return"},
    "SW.Blocks.FB": {"Input", "Output", "InOut", "Static", "Temp", "Constant", "Base"},
    "SW.Blocks.OB": {"Input", "Temp", "Constant"},
    "SW.Blocks.GlobalDB": {"Static"},
    "SW.Types.PlcStruct": {"None"},
}
_NS_RE = re.compile(re.escape(NS_BASE) + r"(?P<family>.+)/(?P<ver>v\d+)$")


def _norm_version(v: str) -> str:
    v = v.strip().upper()
    return v if v.startswith("V") else "V" + v


def check_simaticml(root: Node) -> list[Finding]:
    out: list[Finding] = []
    if root.tag != "Document":
        return [error("SM001", f"root element is <{root.tag}>, expected <Document>", root.line)]
    eng = root.find("Engineering")
    tia = _norm_version(eng.get("version", "")) if eng is not None else ""
    if not tia:
        out.append(warning("SM002", "no <Engineering version=…/>; TIA cannot tell which schema generation this is", root.line))
    expected = EXPECTED_NS.get(tia, {})
    seen_ns: set[tuple[str, str, int]] = set()
    for node in root.iter():
        m = _NS_RE.match(node.ns) if node.ns else None
        if m and (m.group("family"), m.group("ver")) not in {(f, v) for f, v, _ in seen_ns}:
            seen_ns.add((m.group("family"), m.group("ver"), node.line))
    for family, ver, line in sorted(seen_ns, key=lambda x: x[2]):
        want = expected.get(family)
        if want and want != ver:
            out.append(warning("SM003", f"{family} namespace is {ver} but TIA {tia} exports use {want}; import may be rejected", line))

    ids: dict[str, int] = {}
    for node in root.iter():
        if node.ns:  # inner namespaced payloads have their own UId scheme
            continue
        nid = node.get("ID")
        if nid is None:
            continue
        if not re.fullmatch(r"[0-9A-Fa-f]+", nid):
            out.append(warning("SM004", f"ID '{nid}' is not hexadecimal", node.line))
        if nid.upper() in ids:
            out.append(error("SM004", f"duplicate ID {nid} (first at line {ids[nid.upper()]})", node.line))
        ids[nid.upper()] = node.line

    blocks = [c for c in root.children if c.tag in BLOCK_TAGS]
    if not blocks:
        out.append(warning("SM010", "no SW.Blocks.* / SW.Types.* / SW.Tags.* element under <Document>", root.line))
    for block in blocks:
        out.extend(_check_block(block))
    return out


def _check_block(block: Node) -> list[Finding]:
    out: list[Finding] = []
    attrs = block.find("AttributeList")
    name_node = attrs.find("Name") if attrs is not None else None
    name = name_node.text.strip() if name_node is not None else ""
    ctx = f"{block.tag} {name}".strip()
    if not name:
        out.append(error("SM010", f"<{block.tag}> has no AttributeList/Name", block.line))
    if attrs is not None:
        lang = attrs.find("ProgrammingLanguage")
        if lang is not None and lang.text.strip() not in LANGUAGES:
            out.append(warning("SM011", f"unknown ProgrammingLanguage '{lang.text.strip()}'", lang.line, ctx))
        num = attrs.find("Number")
        if num is not None and not num.text.strip().isdigit():
            out.append(error("SM012", f"block Number '{num.text.strip()}' is not an integer", num.line, ctx))
        iface = attrs.find("Interface")
        if iface is not None:
            out.extend(_check_interface(block.tag, iface, ctx))
    for cu in block.iter("SW.Blocks.CompileUnit"):
        out.extend(_check_compile_unit(cu, ctx))
    return out


def _check_interface(kind: str, iface: Node, ctx: str) -> list[Finding]:
    out: list[Finding] = []
    allowed = SECTIONS.get(kind)
    sections = [s for s in iface.iter("Section")]
    names = {s.get("Name") for s in sections if s.parent is not None and s.parent.tag == "Sections"}
    if allowed:
        for s in sections:
            if s.parent is not None and s.parent.tag == "Sections" and s.get("Name") not in allowed:
                out.append(error("SM013", f"section '{s.get('Name')}' is not valid in {kind}", s.line, ctx))
    if kind == "SW.Blocks.FC" and "Return" not in names:
        out.append(warning("SM013", "FC interface has no Return section (use Datatype=\"Void\" for none)", iface.line, ctx))
    # duplicate member names among siblings (nested struct members included)
    for parent in iface.iter():
        seen: dict[str, int] = {}
        for m in parent.findall("Member"):
            key = (m.get("Name") or "").upper()
            if key in seen:
                out.append(error("SM014", f"member '{m.get('Name')}' declared twice (first at line {seen[key]})", m.line, ctx))
            seen[key] = m.line
    # a name may appear in only one top-level section of a block interface
    top: dict[str, str] = {}
    for s in sections:
        if s.parent is None or s.parent.tag != "Sections":
            continue
        for m in s.findall("Member"):
            key = (m.get("Name") or "").upper()
            if key in top and top[key] != s.get("Name"):
                out.append(error("SM014", f"member '{m.get('Name')}' exists in sections {top[key]} and {s.get('Name')}", m.line, ctx))
            top.setdefault(key, s.get("Name") or "")
            if not m.get("Datatype"):
                out.append(error("SM015", f"member '{m.get('Name')}' has no Datatype", m.line, ctx))
    return out


PAYLOAD_ROOTS = ("FlgNet", "StructuredText", "StatementList", "Graph")


def _check_compile_unit(cu: Node, ctx: str) -> list[Finding]:
    """UIds are unique per network payload; GRAPH nests one FlgNet per condition, each its own scope."""
    out: list[Finding] = []
    scopes: dict[int, Node] = {}
    for node in cu.iter():
        if node.tag in PAYLOAD_ROOTS:
            scopes[id(node)] = node
    for scope in scopes.values():
        nodes = []
        stack = list(scope.children)
        while stack:  # stop at nested payload roots: they are separate scopes
            n = stack.pop()
            nodes.append(n)
            if n.tag not in PAYLOAD_ROOTS:
                stack.extend(n.children)
        uids: dict[str, int] = {}
        wires: set[str] = set()
        for node in nodes:
            uid = node.get("UId")
            if uid is None or node.tag in ("IdentCon", "NameCon", "OpenCon", "Powerrail"):
                continue
            if uid in uids:
                out.append(error("SM020", f"duplicate UId {uid} in one network (first at line {uids[uid]})", node.line, ctx))
            uids[uid] = node.line
            if node.tag == "Wire":
                wires.add(uid)
        for con in (n for n in nodes if n.tag in ("IdentCon", "NameCon")):
            ref = con.get("UId")
            if ref and (ref not in uids or ref in wires):
                out.append(error("SM021", f"<{con.tag} UId=\"{ref}\"> refers to no part in this network", con.line, ctx))
    return out


def check_simatic_sd(text: str) -> list[Finding]:
    """SIMATIC SD (.s7dcl): only NETWORK/RUNG nesting and brace balance are checked."""
    out: list[Finding] = []
    stack: list[tuple[str, int]] = []
    depth = 0
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = re.sub(r"//.*$", "", raw)
        line = re.sub(r"'[^']*'|\"[^\"]*\"", "", line)
        depth += line.count("{") - line.count("}")
        for word in re.findall(r"\b(END_NETWORK|END_RUNG|NETWORK|RUNG)\b", line):
            if word in ("NETWORK", "RUNG"):
                stack.append((word, lineno))
                continue
            opener = word[4:]
            pos = next((k for k in range(len(stack) - 1, -1, -1) if stack[k][0] == opener), None)
            if pos is None:
                out.append(error("SD001", f"{word} without matching {opener}", lineno))
                continue
            for inner, ln in stack[pos + 1:]:
                out.append(error("SD001", f"{inner} opened at line {ln} is not closed before {word}", ln))
            del stack[pos:]
    for word, lineno in stack:
        out.append(error("SD001", f"{word} opened here is never closed", lineno))
    if depth:
        out.append(error("SD002", "unbalanced { } braces", None))
    return out
