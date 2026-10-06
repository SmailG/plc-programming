"""Minimal namespace-aware XML tree with line numbers (expat, stdlib only).

ElementTree drops line numbers, and a finding without a line is half as useful.
External entities and DTDs are never fetched.
"""

from __future__ import annotations

import xml.parsers.expat
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(eq=False)
class Node:
    tag: str  # local name
    ns: str  # namespace URI, "" when none
    attrib: dict[str, str]
    line: int
    parent: "Node | None" = None
    children: list["Node"] = field(default_factory=list)
    text: str = ""
    text_line: int = 0  # line where the first character data chunk started

    def find(self, tag: str) -> "Node | None":
        return next((c for c in self.children if c.tag == tag), None)

    def findall(self, tag: str) -> list["Node"]:
        return [c for c in self.children if c.tag == tag]

    def iter(self, tag: str | None = None):
        stack = [self]
        while stack:
            node = stack.pop()
            if tag is None or node.tag == tag:
                yield node
            stack.extend(reversed(node.children))

    def ancestor(self, tag: str) -> "Node | None":
        p = self.parent
        while p is not None and p.tag != tag:
            p = p.parent
        return p

    def get(self, name: str, default: str | None = None) -> str | None:
        if name in self.attrib:
            return self.attrib[name]
        # namespaced attributes arrive as "uri}local"; match on the local part
        for key, value in self.attrib.items():
            if key.rsplit("}", 1)[-1] == name:
                return value
        return default

    def all_text(self) -> str:
        return self.text + "".join(c.all_text() for c in self.children)


class XmlError(Exception):
    def __init__(self, message: str, line: int | None):
        super().__init__(message)
        self.line = line


def parse_bytes(data: bytes) -> Node:
    parser = xml.parsers.expat.ParserCreate(namespace_separator="}")
    parser.SetParamEntityParsing(xml.parsers.expat.XML_PARAM_ENTITY_PARSING_NEVER)
    root: list[Node] = []
    stack: list[Node] = []

    def split(name: str) -> tuple[str, str]:
        if "}" in name:
            ns, local = name.rsplit("}", 1)
            return ns, local
        return "", name

    def start(name, attrs):
        ns, local = split(name)
        node = Node(local, ns, dict(attrs), parser.CurrentLineNumber, stack[-1] if stack else None)
        if stack:
            stack[-1].children.append(node)
        else:
            root.append(node)
        stack.append(node)

    def end(_name):
        stack.pop()

    def chars(data):
        if stack:
            node = stack[-1]
            if not node.text:
                node.text_line = parser.CurrentLineNumber
            node.text += data

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = chars
    try:
        parser.Parse(data, True)
    except xml.parsers.expat.ExpatError as exc:
        raise XmlError(f"XML is not well-formed: {xml.parsers.expat.ErrorString(exc.code)}", exc.lineno) from exc
    if not root:
        raise XmlError("empty document", None)
    return root[0]


def parse_file(path: Path) -> Node:
    return parse_bytes(path.read_bytes())


def sniff_root(path: Path) -> tuple[str, str] | None:
    """(namespace, local name) of the root element, or None if it is not XML."""
    try:
        head = path.read_bytes()[:4096]
    except OSError:
        return None
    stripped = head.lstrip(b"\xef\xbb\xbf \t\r\n")
    if not stripped.startswith(b"<"):
        return None
    parser = xml.parsers.expat.ParserCreate(namespace_separator="}")
    found: list[str] = []

    def start(name, _attrs):
        found.append(name)
        raise StopIteration

    parser.StartElementHandler = start
    try:
        parser.Parse(head, False)
    except StopIteration:
        pass
    except xml.parsers.expat.ExpatError:
        return None
    if not found:
        return None
    name = found[0]
    if "}" in name:
        ns, local = name.rsplit("}", 1)
        return ns, local
    return "", name
