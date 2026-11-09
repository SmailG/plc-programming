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


def graphical_payload(table: Table, owner: str, networks: bytes, decl: str, lang="Ld") -> bytes:
    return (b"\x0f\xe6\x02\x48\x9c\x01\x27" + table.v(lang) + b"\x04" + networks
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
