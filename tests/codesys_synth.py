"""Builders for SYNTHETIC CODESYS `.project` files, used by test_codesys_project.py.

The encoder lives here and not in the reader on purpose: the tests check the reader against
the layout it documents, written down a second time. All names and text are invented.
"""

from __future__ import annotations

import struct
import zipfile

from codesysproj import project

FILLER = 300  # string indices below this are filler, so real text gets two-byte varint indices
MAGIC = bytes.fromhex("02200928")


def vi(n: int) -> bytes:
    out = bytearray()
    while True:
        byte, n = n & 0x7F, n >> 7
        out.append(byte | 0x80 if n else byte)
        if not n:
            return bytes(out)


def qword(n: int) -> bytes:
    return struct.pack("<Q", n)


def guid(n: int) -> str:
    return "%08x-0000-4000-8000-%012x" % (n, n)


class Table:
    def __init__(self):
        self.texts = ["filler-%d" % i for i in range(FILLER)]
        self.index = {}

    def add(self, text: str) -> int:
        if text not in self.index:
            self.index[text] = len(self.texts)
            self.texts.append(text)
        return self.index[text]

    def v(self, text: str) -> bytes:
        return vi(self.add(text))

    def dump(self, declared=None) -> bytes:
        body = b"".join(vi(i) + vi(len(t.encode())) + t.encode() for i, t in enumerate(self.texts))
        return vi(len(self.texts) if declared is None else declared) + body


def make_object(payload: bytes) -> bytes:
    return MAGIC + b"\x00" * 12 + struct.pack("<I", len(payload)) + payload


def make_meta(table: Table, own: str, parent: str, name: str, repeat_own=False) -> bytes:
    head = bytes([2, 0x20, 9, 0x28]) + b"\x00" * 12
    ids = table.v(own) * (2 if repeat_own else 1) + table.v(parent) + table.v(name)
    return head + ids + b"\x00\x00" + table.v("7777") + b"\x80" * 11  # a broken tail varint


def slot(table: Table, owner: str, text: str, impl: bool) -> bytes:
    marker = b"\x5b\xe5\x02" if impl else b"\x41\xe5\x02"
    ref = owner + ("_Impl_LineIds" if impl else "_Decl_LineIds")
    return marker + table.v(text) + table.v(ref)


def st_payload(table: Table, owner: str, decl: str, impl: str) -> bytes:
    return (b"\x0f\xe6\x02\x48" + slot(table, owner, impl, True) + slot(table, owner, decl, False)
            + b"\xd0\x01\x00\x00\x00")


def decl_only_payload(table: Table, owner: str, decl: str) -> bytes:
    return b"\x0f\x80\x01" + slot(table, owner, decl, False) + b"\x00\x00\x00"


def network(table: Table, comment, items: bytes = b"", tag: bytes = b"\xe1\x02") -> bytes:
    comment_bytes = b"\x00" if comment is None else table.v(comment)
    return b"\x0f" + tag + b"\x00" * 5 + comment_bytes + b"\x27\x27\x00\x01" + items


def graphical_payload(table: Table, owner: str, networks: bytes, decl: str, lang="Ld", pad=b"") -> bytes:
    return (b"\x0f\xe6\x02\x48\x9c\x01\x27" + table.v(lang) + b"\x04" + pad + networks
            + slot(table, owner, decl, False) + b"\xd0\x01\x00\x00\x00")


def coils(count: int) -> bytes:
    return b"\x0f\x6f\x6c" + bytes([count])


def element(table: Table, name: str, typ: str, modifier: int, ident: int, is_input=False) -> bytes:
    head = (b"\x0f\x69" if is_input else b"") + b"\xdf\x02"
    return (head + table.v(name) + table.v(typ) + b"\x27\x27\x27\xdd\x02" + bytes([modifier])
            + b"\x00" * 5 + b"\x01\x00\x00" + qword(ident))


def box(table: Table, box_type: str, instance: str, header_id: int, tag=b"\xe0\x02") -> bytes:
    inst = b"\xde\x02\x00" if not instance else b"\xdf\x02" + table.v(instance)
    return (b"\x0f" + tag + table.v(box_type) + inst + b"\x27\x27\x27\x27\xdd\x02" + b"\x00" * 8
            + b"\x01" + qword(header_id))


def pins(table: Table, *names: str) -> bytes:
    return bytes([0x6A, len(names), 0x0E]) + b"".join(table.v(n) for n in names)


class Synthetic:
    """Two devices that each hold an Application with a same-named POU, plus one object of every kind."""

    def __init__(self):
        self.t = Table()
        self.files = {}
        self.guids = {}
        self._n = 0

    def add(self, name: str, parent: str, payload: bytes = None, raw: bytes = None, meta=True, **kw) -> str:
        self._n += 1
        g = guid(self._n)
        self.guids[name + str(self._n)] = g
        self.files[g] = {}
        if meta:
            self.files[g]["meta"] = (parent, name, kw.get("repeat_own", False))
        if raw is not None:
            self.files[g]["object"] = raw
        elif payload is not None:
            self.files[g]["object"] = payload
        return g

    def write(self, path: str, declared=None, extra=None) -> None:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for name, data in (extra or {}).items():
                z.writestr(name, data)
            for g, parts in self.files.items():
                if "meta" in parts:
                    parent, name, repeat = parts["meta"]
                    z.writestr(g + ".meta", make_meta(self.t, g, parent, name, repeat))
                if "object" in parts:
                    obj = parts["object"]
                    z.writestr(g + ".object", obj(g) if callable(obj) else obj)
            z.writestr(project.STRING_TABLE_NAME, self.t.dump(declared))


def build_standard(path: str) -> dict:
    """The project most tests read. Returns the guids by role."""
    s = Synthetic()
    t = s.t
    null = guid(0)
    ids = {}
    for dev in ("DevA", "DevB"):
        d = s.add(dev, null, make_object(b"\x0f\x01"))
        pl = s.add("Plc Logic", d, make_object(b"\x0f\x02"))
        app = s.add("Application", pl, make_object(b"\x0f\x03"))
        ids[dev] = app
        ids[dev + ".device"] = d
        ids[dev + ".pou"] = s.add("Main", app, lambda g, dev=dev: make_object(
            st_payload(t, g, "PROGRAM Main\nVAR\n\tx: INT;\nEND_VAR\r\n", "x := x + 1; // %s\r\n" % dev)))
    ids["gvl"] = s.add("Globals", ids["DevA"], lambda g: make_object(
        decl_only_payload(t, g, "VAR_GLOBAL\n\tcount: INT;\nEND_VAR")))
    ids["dut"] = s.add("Point", ids["DevA"], lambda g: make_object(decl_only_payload(t, g, "TYPE Point :\nSTRUCT\nEND_STRUCT\nEND_TYPE")))
    ids["pragma"] = s.add("Pragma", ids["DevA"], lambda g: make_object(
        st_payload(t, g, "{attribute 'hide'}\n// note\n(* block *)\nFUNCTION_BLOCK Pragma\nVAR\nEND_VAR", "")))
    items = (coils(1) + element(t, "Lamp", "BOOL", 2, 5111)
             + element(t, "Start", "BOOL", 1, 5230, is_input=True)
             + box(t, "TON", "Timer1", 6034) + element(t, "Preset", "TIME", 0, 5340, is_input=True)
             + qword(6035) + pins(t, "IN", "PT") + b"\x9a\x01\x42\x00\x00\x00\x00" + qword(7451))
    nets = network(t, "start the lamp", items) + network(t, None, element(t, "Y", "INT", 0, 5450), tag=b"\xe7\x02")
    ids["graph"] = s.add("Ladder", ids["DevA"], lambda g: make_object(
        graphical_payload(t, g, nets, "PROGRAM Ladder\nVAR\nEND_VAR", "Ld")))
    ids["other"] = s.add("Tasks", ids["DevA.device"], make_object(b"\x0f\x01\x02\x03"))
    # entries that are not a `<guid>.meta` / `<guid>.object` pair are ignored
    s.write(path, extra={"notes.meta": b"x", "readme.object": b"x", guid(4242) + ".txt": b"x"})
    return ids


# ---- two versions of one project, a build-identity entry, and a project made for xref ----

def devices_meta_xml(devices) -> bytes:
    """`devicesmetainformation.auxiliary`: [(name, [(app name, code id, data id), ...]), ...]."""
    out = ['<?xml version="1.0" encoding="utf-8"?><Devices>']
    for name, apps in devices:
        out.append('<Device><Data Key="Name" Type="System.String">%s</Data>' % name)
        out.append('<Data Key="DeviceType" Type="System.Int32">4096</Data>')
        out.append('<Data Key="DeviceId" Type="System.String">0000 0001</Data>')
        out.append('<Data Key="DeviceVersion" Type="System.String">1.2.3.4</Data>')
        out.append('<Data Key="DeviceName" Type="System.String">Model-%s</Data>' % name)
        for app, code, data in apps:
            out.append('<Application><Data Key="Name" Type="System.String">%s</Data>' % app)
            out.append('<Data Key="CodeId" Type="System.Guid">%s</Data>' % code)
            out.append('<Data Key="DataId" Type="System.Guid">%s</Data></Application>' % data)
        out.append("</Device>")
    out.append("</Devices>")
    return "".join(out).encode()


def tools_versions_xml(saves, product="Test IDE", version="2.6") -> bytes:
    """`engineeringtoolsversions.auxiliary`: saves = [(first, last, save counter, core version), ...]."""
    entries = "".join(
        '<HistoryEntry CoreVersion="%s" OpenCounter="1" SaveCounter="%d" FirstTimeSaved="%s" LastTimeSaved="%s" '
        'EnvironmentType="Test" />' % (core, counter, first, last) for first, last, counter, core in saves)
    return ('<Configuration EngineeringProjectVersion="%s" EnvironmentType="Test" InformationalProductName="%s">'
            '<Tool Name="Core" Version="9.9.9.9"><Plugins /></Tool><History>%s</History></Configuration>'
            % (version, product, entries)).encode()


def _ladder(t: Table, version: int, shifted: bool) -> bytes:
    """Version 1 and 2 of a ladder with one constant, one modifier, one comment and one element changed."""
    base = 100 if version == 1 else 9000  # element ids: all different between versions
    const = "500" if version == 1 else "600"
    lamp_mod = 2 if version == 1 else 3
    comment = "start the lamp" if version == 1 else "start the lamp slowly"
    items = (coils(1) + element(t, "Lamp", "BOOL", lamp_mod, base + 11)
             + element(t, "Start", "BOOL", 1, base + 12, is_input=True)
             + box(t, "TON", "Timer1", base + 20) + element(t, const, "", 0, base + 13, is_input=True)
             + qword(base + 21) + pins(t, "IN", "PT"))
    nets = network(t, comment, items)
    nets += network(t, None, element(t, "Y", "INT", 0, base + 40), tag=b"\xe7\x02")
    if version == 2:
        nets += network(t, "added later", element(t, "Extra", "INT", 0, base + 50))
    return nets


def _shifted(t: Table, version: int) -> bytes:
    """The same content in both versions; only the element ids and the byte offsets differ."""
    base = 200 if version == 1 else 7000
    items = (coils(1) + element(t, "Out1", "BOOL", 0, base + 1) + element(t, "In1", "BOOL", 1, base + 2, is_input=True)
             + b"\x9a\x01" + bytes([0x40 + version]) + b"\x00\x00\x00\x00" + qword(base + 3))  # an empty slot
    return network(t, "same network", items)


def build_version(path: str, version: int, meta=True) -> dict:
    """Version 1 or 2 of one project. Objects present in both keep their guid.

    Changes 1 -> 2: `Edited` (declaration and implementation), `Ladder` (constant, modifier, network
    comment, one network added), `Renamed` (name only), `Globals` (declaration), `Tasks` (opaque bytes).
    Unchanged: `Same`, `Shifted` (ids and offsets differ, content does not). `Gone` exists only in 1,
    `Fresh` only in 2.
    """
    s = Synthetic()
    t = s.t
    v = version
    null = guid(0)
    dev = s.add("DevA", null, make_object(b"\x0f\x01"))
    pl = s.add("Plc Logic", dev, make_object(b"\x0f\x02"))
    app = s.add("Application", pl, make_object(b"\x0f\x03"))
    ids = {"device": dev, "app": app}

    def st(name, decl, impl):
        return s.add(name, app, lambda g: make_object(st_payload(t, g, decl, impl)))

    ids["same"] = st("Same", "PROGRAM Same\nVAR\nEND_VAR", "a := 1;\r\n")
    ids["edited"] = st("Edited", "PROGRAM Edited\nVAR\n\tx: INT;\n%sEND_VAR" % ("\ty: INT;\n" if v == 2 else ""),
                       "x := x + %d;\r\n" % v)
    ids["ladder"] = s.add("Ladder", app, lambda g: make_object(
        graphical_payload(t, g, _ladder(t, v, False), "PROGRAM Ladder\nVAR\nEND_VAR")))
    ids["shifted"] = s.add("Shifted", app, lambda g: make_object(
        graphical_payload(t, g, _shifted(t, v), "PROGRAM Shifted\nVAR\nEND_VAR", pad=b"\x00" * (3 * v))))
    ids["renamed"] = st("OldName" if v == 1 else "NewName", "PROGRAM R\nVAR\nEND_VAR", "r := 1;\r\n")
    ids["globals"] = s.add("Globals", app, lambda g: make_object(
        decl_only_payload(t, g, "VAR_GLOBAL\n\tcount: INT;\n%sEND_VAR" % ("\tmore: INT;\n" if v == 2 else ""))))
    ids["tasks"] = s.add("Tasks", app, make_object(b"\x0f\x01\x02" + bytes([v])))
    if v == 1:
        ids["gone"] = st("Gone", "PROGRAM Gone\nVAR\nEND_VAR", "g := 1;\r\n")
        s._n += 1  # the guid `Fresh` takes in version 2
    else:
        s._n += 1  # the guid `Gone` had in version 1
        ids["fresh"] = st("Fresh", "PROGRAM Fresh\nVAR\nEND_VAR", "f := 1;\r\n")
    extra = {}
    if meta:
        code, data = ("aaaa%04x-0000-0000-0000-000000000000" % v, "bbbb%04x-0000-0000-0000-000000000000" % v)
        extra["devicesmetainformation.auxiliary"] = devices_meta_xml([("DevA", [("Application", code, data)])])
        extra["engineeringtoolsversions.auxiliary"] = tools_versions_xml(
            [("2020-01-01-00-00-00", "2020-02-02-12-00-00", 5, "1.0.0.0"),
             ("2020-03-01-00-00-00", "2020-0%d-15-08-30-45" % (v + 3), 9, "2.0.0.0")])
    s.write(path, extra=extra)
    return ids


def build_xref(path: str) -> dict:
    """ST, graphical and declaration-only objects that mention `counter` in every way xref classifies."""
    s = Synthetic()
    t = s.t
    null = guid(0)
    dev = s.add("Dev", null, make_object(b"\x0f\x01"))
    app = s.add("Application", s.add("Plc Logic", dev, make_object(b"\x0f\x02")), make_object(b"\x0f\x03"))
    ids = {}
    ids["gvl"] = s.add("Gvl", app, lambda g: make_object(
        decl_only_payload(
        t, g, "VAR_GLOBAL RETAIN counter : INT;\n\tother, spare : INT;\n\tlone AT %MX0.0 : BOOL;\nEND_VAR")))
    impl = ("// counter in a comment\n"
            "(* counter := 9; *)\n"
            "counter := counter + 1;\n"
            "Gvl.counter := 2;\n"
            "arr[counter] := 0;\n"
            "msg := 'counter in a string';\n"
            "Timer1(IN := COUNTER > 3, PT := T#5s, Q => counter);\n"
            "IF other = 1 THEN counter_total := 0; END_IF\n"
            "FOR counter := 0 TO 9 DO other := other + 1; END_FOR\n"
            "Fb.Method(counter);\n"
            "Gvl.other := 3;\n")
    ids["writer"] = s.add("Writer", app, lambda g: make_object(st_payload(
        t, g, "PROGRAM Writer\nVAR\n\tlocal : INT := Gvl.counter;\n\ttimer1 : TON;\nEND_VAR", impl)))
    items = (coils(1) + element(t, "Gvl.counter", "BOOL", 0, 5111) + element(t, "other", "BOOL", 0, 5230, is_input=True)
             + box(t, "TON", "Timer1", 6034) + element(t, "arr[counter]", "INT", 0, 5340, is_input=True)
             + element(t, "5", "", 0, 5341, is_input=True) + qword(6035) + pins(t, "IN", "PT"))
    nets = network(t, "first", items) + network(t, None, element(t, "arr[idx]", "INT", 0, 5450), tag=b"\xe7\x02")
    ids["lad"] = s.add("Lad", app, lambda g: make_object(
        graphical_payload(t, g, nets, "PROGRAM Lad\nVAR\n\tcounter : INT;\nEND_VAR")))
    ids["tasks"] = s.add("Tasks", dev, make_object(b"\x0f\x01\x02\x03"))
    s.write(path)
    return ids
