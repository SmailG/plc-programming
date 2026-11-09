"""Low-level primitives: the varint, the shared string table.

Observed layout (reverse-engineered, not documented by the vendor):

* a varint is LEB128: 7 data bits per byte, low group first, high bit = "more follows";
* `__shared_data_storage_string_table__.auxiliary` is `count`, then `count` entries of
  (index, byte length, UTF-8 bytes), all three as varints.
"""

from __future__ import annotations

from typing import Dict, Tuple

MAX_VARINT_BYTES = 10  # 70 bits: far past any index or length seen in a real project


class FormatError(ValueError):
    """The bytes do not follow the layout this reader understands."""


def read_varint(buf: bytes, pos: int) -> Tuple[int, int]:
    """Return (value, position after it). Raises FormatError on EOF or an overlong varint."""
    value = 0
    shift = 0
    start = pos
    while True:
        if pos >= len(buf):
            raise FormatError("varint at offset %d runs past the end of the data" % start)
        if pos - start >= MAX_VARINT_BYTES:
            raise FormatError("varint at offset %d is longer than %d bytes" % (start, MAX_VARINT_BYTES))
        byte = buf[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        shift += 7
        if not byte & 0x80:
            return value, pos


def parse_string_table(data: bytes) -> Dict[int, str]:
    """Parse the shared string table into {index: text}."""
    declared, pos = read_varint(data, 0)
    table: Dict[int, str] = {}
    while pos < len(data):
        index, pos = read_varint(data, pos)
        length, pos = read_varint(data, pos)
        if pos + length > len(data):
            raise FormatError("string table entry %d (%d bytes) runs past the end of the file" % (index, length))
        if index in table:
            raise FormatError("string table index %d appears twice" % index)
        table[index] = data[pos:pos + length].decode("utf-8", "replace")
        pos += length
    if len(table) != declared:
        raise FormatError("string table declares %d entries but holds %d" % (declared, len(table)))
    return table
