#!/usr/bin/env python3
"""Decode WinCC Tag Logging fast-archive blocks (`TagCompressed.BinValues`) offline.

    wincc_binvalues.py [DUMP]

DUMP is a file, or `-` or nothing for standard input. Each line is either one block as hex, or
four `|`-separated fields as `sqlcmd` prints them, the last being the hex (the first three are
ignored; the block's own header carries the start time). Output is CSV on standard output:
`timestamp,value,quality`, timestamps in UTC to the millisecond, quality as the decimal OPC
quality byte (192 = 0xC0 = good, 8 = 0x08 = bad / not connected).

The format is undocumented. It was reverse-engineered on WinCC 7.5 SP2 fast archives and is
untested on other versions; the decoder raises DecodeError on anything it does not recognise
rather than guessing. Established, guessed and undecoded parts are listed in
skills/other-platforms/references/wincc-tag-logging-archive.md.

As a library:

    from wincc_binvalues import decode_block
    rows = decode_block(binvalues_bytes)   # [(datetime, value, quality), ...]

Exit: 0 clean, 1 some blocks did not decode or none were found (the others are still written),
2 usage or unreadable input. Standard library only; Python 3.9 or later.
"""
import argparse
import csv
import datetime
import struct
import sys

HEADER_LEN = 37          # fixed byte header before the bit stream
MRU_SIZE = 19            # history depth (current + 18 back); index 19 is never referenced
OLE_EPOCH = datetime.datetime(1899, 12, 30)

# byte 4 of the header -> (kind, width in bits, signed). 'f' = IEEE float32 little-endian.
# Widths are established (bit accounting). Signedness of 4-7 follows from observed values;
# signedness of 8 is a guess (no value >= 2**31 was seen).
VALUE_CODES = {
    3: ('f', 32, True),
    4: ('i', 16, True),
    5: ('i', 8, True),
    6: ('i', 8, False),
    7: ('i', 16, False),
    8: ('i', 32, True),
}


class DecodeError(ValueError):
    pass


class _Bits:
    def __init__(self, data):
        self.s = ''.join(f'{x:08b}' for x in data)
        self.p = 0

    def take(self, n):
        if self.p + n > len(self.s):
            raise DecodeError(f'read past end at bit {self.p} (+{n})')
        v = self.s[self.p:self.p + n]
        self.p += n
        return v

    def peek(self, n):
        return self.s[self.p:self.p + n]


def _value(bitstr, kind, width, signed):
    raw = int(bitstr, 2).to_bytes(width // 8, 'big')   # bytes in stream order
    if kind == 'f':
        return struct.unpack('<f', raw)[0]
    return int.from_bytes(raw, 'little', signed=signed)


def _ole_date(b, offset):
    try:
        return OLE_EPOCH + datetime.timedelta(days=struct.unpack_from('<d', b, offset)[0])
    except (OverflowError, ValueError):
        raise DecodeError(f'start time at header byte {offset} is not a date')


def parse_header(b):
    n = int.from_bytes(b[9:13], 'little')
    t0 = _ole_date(b, 13)
    period_ms = int.from_bytes(b[21:25], 'little')
    return {
        'byte0': b[0], 'code': b[4], 'length': int.from_bytes(b[7:9], 'little'),
        'n': n, 't0': t0, 'period_ms': period_ms,
        'u32_33': int.from_bytes(b[33:37], 'little'),
    }


def _chunk_header(bs):
    m = int(bs.take(10), 2)
    qword = bs.take(32)
    m2 = int(bs.take(10), 2)
    tail = bs.take(32)
    if m != m2 or m == 0:
        raise DecodeError(f'chunk header count mismatch {m}/{m2} at bit {bs.p - 84}')
    # qword[31] is the daylight-saving flag (1 in summer-time segments); either value is accepted.
    q1 = int(qword[8:16], 2)
    q2 = int(tail[24:32], 2)
    if q1 != q2 or tail[:24] != '0' * 24 or qword[16:31] != '000100000000000' or qword[:8] != '0' * 8:
        raise DecodeError(f'unexpected chunk header {qword}/{tail} at bit {bs.p - 84}')
    return m, q1


def decode_values(b):
    """Return (values, qualities, info) for one block. Raises DecodeError on any inconsistency."""
    if len(b) < HEADER_LEN:
        raise DecodeError(f'block of {len(b)} bytes is shorter than the {HEADER_LEN}-byte header')
    xor = 0
    for x in b[1:]:
        xor ^= x
    if xor != b[0]:
        raise DecodeError(f'checksum byte 0 = {b[0]:#04x}, XOR of bytes 1.. = {xor:#04x}')
    h = parse_header(b)
    if h['length'] != len(b):
        raise DecodeError(f"length field {h['length']} != {len(b)}")
    if h['code'] not in VALUE_CODES:
        raise DecodeError(f"unknown value code {h['code']}")
    kind, width, signed = VALUE_CODES[h['code']]
    n = h['n']
    bs = _Bits(b[HEADER_LEN:])
    hist = []

    def push(v):
        if v in hist:
            hist.pop(hist.index(v))
        hist.insert(0, v)
        if len(hist) > MRU_SIZE:
            hist.pop()

    if bs.take(1) != '0':
        raise DecodeError('stream does not start with a value token')
    cur = _value(bs.take(width), kind, width, signed)
    push(cur)
    vals = [cur]
    left, q = _chunk_header(bs)
    chunks = [(left, q)]
    counts = {'same': 0, 'new': 1, 'ref': 0, 'chunks': 1}
    while len(vals) < n:
        if left == 0:
            left, q = _chunk_header(bs)
            chunks.append((left, q))
            counts['chunks'] += 1
            continue
        if bs.peek(2) == '11':
            bs.take(2)
            counts['same'] += 1
        elif bs.peek(1) == '0':
            bs.take(1)
            cur = _value(bs.take(width), kind, width, signed)
            push(cur)
            counts['new'] += 1
        else:
            bs.take(2)
            c = int(bs.take(2), 2)
            idx = c if c else 4 + int(bs.take(4), 2)
            if idx >= len(hist):
                raise DecodeError(f'history index {idx} beyond {len(hist)} at sample {len(vals)}')
            cur = hist[idx]
            push(cur)
            counts['ref'] += 1
        vals.append(cur)
        left -= 1
    if left == 0:
        # the chunk counts sum to n: a block whose last chunk filled up exactly ends with
        # an empty chunk header (m = 1, no tokens)
        left, q = _chunk_header(bs)
        chunks.append((left, q))
        counts['chunks'] += 1
    pad = bs.s[bs.p:]
    if len(pad) >= 8 or '1' in pad:
        raise DecodeError(f'{len(pad)} trailing bits left, ones={pad.count("1")}')
    if left != 1:
        raise DecodeError(f'last chunk left={left}, expected 1')
    # Chunk i covers m_i consecutive samples counted from sample 0, and the counts sum to n:
    # the tokens read are n - 1, which is sum(m) - left = sum(m) - 1 once left == 1, so no
    # separate check of the sum is needed. A chunk's header sits in the stream one token after
    # its first sample, so quality is assigned by these cumulative ranges, not by header position.
    quals = [q for m, q in chunks for _ in range(m)]
    info = dict(h, counts=counts, pad_bits=len(pad), chunks=chunks)
    return vals, quals, info


def decode_block(b, t0=None):
    """Bytes of one BinValues -> [(timestamp, value, quality)]. t0 defaults to the header's start."""
    vals, quals, info = decode_values(b)
    start = t0 or info['t0']
    step = datetime.timedelta(milliseconds=info['period_ms'])
    return [(start + k * step, v, q) for k, (v, q) in enumerate(zip(vals, quals))]


def format_timestamp(dt):
    """UTC to the millisecond, rounded: the header's start time is a double and carries microsecond noise."""
    dt = dt + datetime.timedelta(microseconds=500)
    return f'{dt:%Y-%m-%dT%H:%M:%S}.{dt.microsecond // 1000:03d}Z'


def format_value(v):
    return f'{v:.9g}' if isinstance(v, float) else str(v)   # 9 digits round-trip a float32


def block_from_line(line):
    """The block bytes from a bare hex line or from a dump line of four `|`-separated fields."""
    fields = [f.strip() for f in line.split('|')]
    if len(fields) == 1:
        text = fields[0]
    elif len(fields) == 4:
        text = fields[3]
    else:
        raise DecodeError(f'expected hex or three columns then hex, got {len(fields)} fields')
    try:
        return bytes.fromhex(text)
    except ValueError:
        raise DecodeError(f'not hex: {text[:30]!r}')


def convert(lines, out, err):
    """Write the CSV rows of every block in `lines`; return (blocks decoded, blocks failed)."""
    writer = csv.writer(out, lineterminator='\n')
    writer.writerow(['timestamp', 'value', 'quality'])
    ok = bad = 0
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            rows = decode_block(block_from_line(line))
        except DecodeError as e:
            bad += 1
            print(f'line {number}: {e}', file=err)
            continue
        ok += 1
        writer.writerows([format_timestamp(t), format_value(v), q] for t, v, q in rows)
    return ok, bad


def main(argv=None):
    parser = argparse.ArgumentParser(prog='wincc_binvalues.py', description=__doc__.split('\n\n')[0])
    parser.add_argument('dump', nargs='?', default='-', help='dump file, or - for standard input (default)')
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return e.code
    try:
        if args.dump != '-':
            with open(args.dump, encoding='utf-8') as fh:
                lines = fh.read().splitlines()
        else:
            lines = sys.stdin.read().splitlines()
    except (OSError, UnicodeDecodeError) as e:
        print(f'cannot read input: {e}', file=sys.stderr)
        return 2
    ok, bad = convert(lines, sys.stdout, sys.stderr)
    if ok == 0 and bad == 0:
        print('no blocks found in the input', file=sys.stderr)
    return 1 if bad or ok == 0 else 0


if __name__ == '__main__':
    sys.exit(main())
