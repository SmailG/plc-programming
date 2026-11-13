"""WinCC Tag Logging fast-archive decoder, tested on SYNTHETIC blocks only.

The encoder below is written from the format notes in
skills/other-platforms/references/wincc-tag-logging-archive.md. It has its own value table and bit
packing, but it is still the same author's reading of the format, and it shares the decoder's idea
of the stream layout: a round trip proves the decoder and this encoder agree and that every guard
fires, not that the format is understood correctly. Only `test_history_compares_raw_bits` is
written out by hand, without the encoder; it is still the same reading of the format. Whether the
format is understood correctly is checked on real archives, which are never committed here.
"""

from __future__ import annotations

import contextlib
import datetime
import io
import math
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "wincc_binvalues.py"
sys.path.insert(0, str(HERE.parent / "scripts"))

import wincc_binvalues as W  # noqa: E402
from wincc_binvalues import DecodeError  # noqa: E402

GOOD, BAD = 0xC0, 0x08
OLE_EPOCH = datetime.datetime(1899, 12, 30)
T0 = datetime.datetime(2024, 1, 1, 6, 0, 0)  # a fraction of a day that is exact in a double
MAX_CHUNK = 1023
HIST = 19
# value code -> struct format of one value (independent of the decoder's table)
FORMATS = {3: "<f", 4: "<h", 5: "<b", 6: "<B", 7: "<H", 8: "<i"}
CHUNK_CONST = "0001000000000000"


def bits_of(data: bytes) -> str:
    return "".join(f"{x:08b}" for x in data)


def value_bits(code, v):
    return bits_of(struct.pack(FORMATS[code], v))


def chunk_header(m, q, dst=False, m2=None, q2=None, lead="0" * 8, const=None, tail="0" * 24):
    """84 bits: m(10) lead(8) q(8) const(16, last bit = DST) m(10) tail(24) q(8)."""
    const = const if const is not None else CHUNK_CONST[:-1] + ("1" if dst else "0")
    return (f"{m:010b}" + lead + f"{q:08b}" + const + f"{m if m2 is None else m2:010b}" + tail
            + f"{q if q2 is None else q2:08b}")


NEW = "0"
SAME = "11"


def ref_token(index):
    if 1 <= index <= 3:
        return "10" + f"{index:02b}"
    return "10" + "00" + f"{index - 4:04b}"


def split_chunks(quals):
    """Chunks are cut at a quality change and at 1023 samples."""
    chunks, run_q, run = [], None, 0
    for q in quals:
        if q == run_q and run < MAX_CHUNK:
            run += 1
        else:
            if run:
                chunks.append((run, run_q))
            run_q, run = q, 1
    chunks.append((run, run_q))
    return chunks


def encode_stream(code, values, quals, dst=False):
    """Initial value, then one token per later sample; chunk j's header follows S_(j-1) tokens."""
    chunks = split_chunks(quals)
    starts = [0]
    for m, _ in chunks:
        starts.append(starts[-1] + m)
    out, hist, nxt = [NEW + value_bits(code, values[0])], [value_bits(code, values[0])], 0

    def headers(done):
        nonlocal nxt
        if nxt < len(chunks) and starts[nxt] == done:
            out.append(chunk_header(chunks[nxt][0], chunks[nxt][1], dst))
            nxt += 1

    headers(0)
    for k in range(1, len(values)):
        key = value_bits(code, values[k])   # the history compares raw value bits, not Python equality
        if key == hist[0]:
            out.append(SAME)
        elif key in hist:
            out.append(ref_token(hist.index(key)))
            hist.remove(key)
            hist.insert(0, key)
        else:
            out.append(NEW + key)
            hist.insert(0, key)
            del hist[HIST:]
        headers(k)
    return "".join(out)


def assemble(code, n, stream_bits, t0=T0, period_ms=1000, length=None, t0_days=None):
    """37-byte header plus the bit stream (zero padded to a byte), with a correct XOR checksum."""
    body = bytes(int((stream_bits + "0" * (-len(stream_bits) % 8))[i:i + 8], 2)
                 for i in range(0, len(stream_bits) + (-len(stream_bits) % 8), 8))
    days = t0_days if t0_days is not None else (t0 - OLE_EPOCH).total_seconds() / 86400
    head = bytearray(37)
    head[1:4] = b"\x05\x04\x00"
    head[4] = code
    head[5:7] = b"\x20\x20"
    head[7:9] = (length if length is not None else 37 + len(body)).to_bytes(2, "little")
    head[9:13] = n.to_bytes(4, "little")
    head[13:21] = struct.pack("<d", days)
    head[21:25] = period_ms.to_bytes(4, "little")
    head[25:33] = struct.pack("<d", days + 1 / 24)
    return seal(bytes(head) + body)


def seal(raw):
    """Set byte 0 to the XOR of bytes 1.. ."""
    x = 0
    for b in raw[1:]:
        x ^= b
    return bytes([x]) + raw[1:]


def encode_block(values, code=3, quals=None, dst=False, **kw):
    quals = quals if quals is not None else [GOOD] * len(values)
    return assemble(code, len(values), encode_stream(code, values, quals, dst), **kw)


def with_byte(raw, offset, value):
    return seal(raw[:offset] + bytes([value]) + raw[offset + 1:])


class RoundTrip(unittest.TestCase):
    def check(self, code, values):
        vals, quals, info = W.decode_values(encode_block(values, code=code))
        self.assertEqual(vals, values)
        return info

    def test_float32(self):
        self.check(3, [0.5, 1.25, -3.0, 1.25, 1000.0])

    def test_int16_is_signed(self):
        self.check(4, [-11111, 7, 32767, -32768])

    def test_int8_is_signed(self):
        self.check(5, [-90, 0, 127, -128])

    def test_uint8_is_unsigned(self):
        self.check(6, [200, 201, 255, 0])

    def test_uint16_is_unsigned(self):
        self.check(7, [60000, 32768, 65535, 1])

    def test_int32_negative_is_a_guess_pinned_as_signed(self):
        # Signedness of code 8 is NOT established (no value >= 2**31 was ever seen); this pins the guess.
        self.check(8, [-100000, 70000, 2 ** 31 - 1, -(2 ** 31)])

    def test_a_single_sample(self):
        self.check(3, [2.5])

    def test_constant_block_uses_only_same_tokens(self):
        info = self.check(4, [5] * 50)
        self.assertEqual((info["counts"]["same"], info["counts"]["new"]), (49, 1))

    def test_every_new_value_costs_a_full_value(self):
        info = self.check(4, [1, 2, 3, 4, 5, 6])
        self.assertEqual((info["counts"]["new"], info["counts"]["ref"]), (6, 0))

    def test_header_fields(self):
        info = W.decode_values(encode_block([1.0, 2.0, 3.0], period_ms=500))[2]
        self.assertEqual((info["n"], info["period_ms"], info["code"], info["t0"]), (3, 500, 3, T0))


class Header(unittest.TestCase):
    def test_sample_count_and_period_are_four_bytes_wide(self):
        head = bytearray(37)
        head[9:13] = (0x00010000).to_bytes(4, "little")
        head[21:25] = (0x00010000).to_bytes(4, "little")
        h = W.parse_header(bytes(head))
        self.assertEqual((h["n"], h["period_ms"]), (65536, 65536))


class Chunks(unittest.TestCase):
    def test_quality_per_sample_follows_the_chunk_ranges(self):
        quals = [GOOD, GOOD, BAD, BAD, GOOD]
        got = W.decode_values(encode_block([1, 2, 3, 4, 5], code=4, quals=quals))[1]
        self.assertEqual(got, quals)

    def test_quality_change_cuts_a_chunk(self):
        quals = [GOOD, GOOD, BAD, BAD, GOOD]
        info = W.decode_values(encode_block([1, 2, 3, 4, 5], code=4, quals=quals))[2]
        self.assertEqual(info["chunks"], [(2, GOOD), (2, BAD), (1, GOOD)])

    def test_chunk_is_cut_at_1023_samples(self):
        values = [float(i % 7) for i in range(1030)]
        vals, quals, info = W.decode_values(encode_block(values))
        self.assertEqual((info["chunks"], vals), ([(1023, GOOD), (7, GOOD)], values))

    def test_a_block_that_fills_its_last_chunk_exactly_ends_with_an_empty_header(self):
        values = [float(i % 5) for i in range(1024)]
        vals, quals, info = W.decode_values(encode_block(values))
        self.assertEqual((info["chunks"], vals), ([(1023, GOOD), (1, GOOD)], values))

    def test_timestamps_step_by_the_period(self):
        rows = W.decode_block(encode_block([1.0, 2.0, 3.0], period_ms=500))
        self.assertEqual([r[0] for r in rows], [T0 + datetime.timedelta(milliseconds=500 * k) for k in range(3)])

    def test_start_time_can_be_overridden(self):
        later = datetime.datetime(2030, 5, 6, 7, 8, 9)
        self.assertEqual(W.decode_block(encode_block([1.0, 2.0]), t0=later)[0][0], later)


class History(unittest.TestCase):
    def test_short_index_references_a_recent_value(self):
        vals, quals, info = W.decode_values(encode_block([1, 2, 1], code=4))
        self.assertEqual((vals, info["counts"]["ref"]), ([1, 2, 1], 1))

    def test_each_short_index(self):
        # after 1,2,3,4 the history is [4,3,2,1]: referencing 3, 2 and 1 uses indexes 1, 2 and 3
        # (each reference moves its value to the front, so re-reading the list is part of the test)
        values = [1, 2, 3, 4, 3, 3, 2, 1, 4]
        vals, quals, info = W.decode_values(encode_block(values, code=4))
        self.assertEqual((vals, info["counts"]["ref"]), (values, 4))

    def test_long_index_references_an_older_value(self):
        values = [1, 2, 3, 4, 5, 6, 1]  # history [6..1]: the 1 sits at index 5 = 4 + 1
        vals, quals, info = W.decode_values(encode_block(values, code=4))
        self.assertEqual((vals, info["counts"]["ref"]), (values, 1))

    def test_oldest_entry_is_index_18(self):
        values = list(range(1, 20)) + [1]  # 19 distinct values, then the first one again
        vals, quals, info = W.decode_values(encode_block(values, code=4))
        self.assertEqual((vals, info["counts"]["ref"]), (values, 1))

    def test_history_compares_raw_bits(self):
        # Written out by hand, not by the encoder. float32 0.0 is four zero bytes, -0.0 is
        # 00 00 00 80 (stream order). Python says 0.0 == -0.0; by raw bits they are two entries, so
        # after NEW 0.0 and NEW -0.0 index 1 is the 0.0 again.
        stream = (
            "0" + "00000000" * 4                          # initial value: 0.0
            + "0000000011" + "00000000" + "11000000"      # chunk header: m = 3, lead 0, q = 0xC0
            + "0001000000000000"                          # constant, DST bit clear
            + "0000000011" + "0" * 24 + "11000000"        # m again, tail, q again
            + "0" + "00000000" * 3 + "10000000"           # NEW: -0.0
            + "10" + "01"                                 # reference, index 1
        )
        vals = W.decode_values(assemble(3, 3, stream))[0]
        self.assertEqual([math.copysign(1, v) for v in vals], [1.0, -1.0, 1.0])
        self.assertEqual(vals, [0.0, 0.0, 0.0])

    def test_index_19_is_rejected(self):
        # 20 distinct values; the 20th pushes the first out, so a reference to index 19 has no entry
        stream = NEW + value_bits(4, 1) + chunk_header(21, GOOD)
        stream += "".join(NEW + value_bits(4, v) for v in range(2, 21)) + "10" + "00" + "1111"
        with self.assertRaisesRegex(DecodeError, "history index 19"):
            W.decode_values(assemble(4, 21, stream))

    def test_index_beyond_the_history_is_rejected(self):
        stream = NEW + value_bits(4, 1) + chunk_header(2, GOOD) + ref_token(1)
        with self.assertRaisesRegex(DecodeError, "history index 1 beyond 1"):
            W.decode_values(assemble(4, 2, stream))


class DaylightSavingFlag(unittest.TestCase):
    VALUES = [1, 2, 2, 3]

    def test_flag_set_decodes(self):
        self.assertEqual(W.decode_values(encode_block(self.VALUES, code=4, dst=True))[0], self.VALUES)

    def test_flag_clear_decodes(self):
        self.assertEqual(W.decode_values(encode_block(self.VALUES, code=4, dst=False))[0], self.VALUES)

    def test_the_two_blocks_really_differ(self):
        self.assertNotEqual(encode_block(self.VALUES, code=4, dst=True), encode_block(self.VALUES, code=4, dst=False))


class Rejects(unittest.TestCase):
    GOOD_BLOCK = encode_block([1.0, 2.0, 3.0, 2.0])

    def decode(self, raw):
        return W.decode_values(raw)

    def test_the_control_block_decodes(self):
        self.assertEqual(self.decode(self.GOOD_BLOCK)[0], [1.0, 2.0, 3.0, 2.0])

    def test_input_shorter_than_the_header(self):
        for raw in (b"", self.GOOD_BLOCK[:36]):
            with self.subTest(length=len(raw)), \
                    self.assertRaisesRegex(DecodeError, "shorter than the 37-byte header"):
                self.decode(raw)

    def test_bad_checksum(self):
        raw = bytes([self.GOOD_BLOCK[0] ^ 0x01]) + self.GOOD_BLOCK[1:]
        with self.assertRaisesRegex(DecodeError, "checksum"):
            self.decode(raw)

    def test_bad_length_field(self):
        raw = encode_block([1.0, 2.0], length=999)
        with self.assertRaisesRegex(DecodeError, "length field 999"):
            self.decode(raw)

    def test_unknown_value_code(self):
        with self.assertRaisesRegex(DecodeError, "unknown value code 9"):
            self.decode(with_byte(self.GOOD_BLOCK, 4, 9))

    def test_unrepresentable_start_time(self):
        raw = encode_block([1.0, 2.0], t0_days=1e300)
        with self.assertRaisesRegex(DecodeError, "start time"):
            self.decode(raw)

    def test_start_time_that_is_not_a_number(self):
        with self.assertRaisesRegex(DecodeError, "start time"):
            self.decode(encode_block([1.0, 2.0], t0_days=float("nan")))

    def test_a_block_with_zero_samples_is_rejected_even_with_one_sample_in_the_stream(self):
        raw = assemble(3, 0, encode_stream(3, [1.0], [GOOD]))
        with self.assertRaisesRegex(DecodeError, "sample count 0"):
            self.decode(raw)

    def test_a_period_of_zero_is_rejected(self):
        with self.assertRaisesRegex(DecodeError, "period of 0"):
            self.decode(encode_block([1.0, 2.0], period_ms=0))

    def test_garbage_in_the_unknown_header_bytes_does_not_fail_a_block(self):
        # bytes 25-36 are not understood and not needed: a NaN there must not cost the block
        raw = seal(self.GOOD_BLOCK[:25] + struct.pack("<d", float("nan")) + self.GOOD_BLOCK[33:])
        self.assertEqual(self.decode(raw)[0], [1.0, 2.0, 3.0, 2.0])

    def test_stream_must_start_with_a_value_token(self):
        stream = SAME + "0" * 40
        with self.assertRaisesRegex(DecodeError, "does not start with a value token"):
            self.decode(assemble(4, 2, stream))

    def test_truncated_stream(self):
        raw = self.GOOD_BLOCK[:-1]
        raw = seal(raw[:7] + (len(raw)).to_bytes(2, "little") + raw[9:])
        with self.assertRaisesRegex(DecodeError, "read past end"):
            self.decode(raw)

    def test_a_whole_zero_byte_after_the_stream(self):
        raw = seal(self.GOOD_BLOCK[:7] + (len(self.GOOD_BLOCK) + 1).to_bytes(2, "little")
                   + self.GOOD_BLOCK[9:] + b"\x00")
        with self.assertRaisesRegex(DecodeError, "trailing bits"):
            self.decode(raw)

    def test_a_whole_zero_byte_after_a_byte_aligned_stream(self):
        # 8 padding bits, all zero: rejected by the length of the padding alone
        bits = encode_stream(6, [1, 2, 2], [GOOD] * 3)
        self.assertEqual(len(bits) % 8, 0, "the test needs a stream that ends on a byte boundary")
        self.assertEqual(self.decode(assemble(6, 3, bits))[0], [1, 2, 2])
        with self.assertRaisesRegex(DecodeError, "8 trailing bits"):
            self.decode(assemble(6, 3, bits + "0" * 8))

    def test_seven_zero_padding_bits_are_accepted(self):
        bits = encode_stream(6, [1, 1, 1], [GOOD] * 3)
        self.assertEqual(-len(bits) % 8, 7, "the test needs 7 padding bits")
        self.assertEqual(self.decode(assemble(6, 3, bits))[0], [1, 1, 1])

    def test_a_one_bit_in_the_padding(self):
        values, code = [1, 2, 1, 3, 1], 4
        bits = encode_stream(code, values, [GOOD] * len(values))
        self.assertNotEqual(len(bits) % 8, 0, "the test needs padding bits to put a one in")
        padded = bits + "1"
        self.assertLess(-len(padded) % 8 + 1, 8)
        with self.assertRaisesRegex(DecodeError, "trailing bits"):
            self.decode(assemble(code, len(values), padded))

    def test_last_chunk_must_have_one_left(self):
        values, code = [1, 2, 3], 4
        stream = NEW + value_bits(code, 1) + chunk_header(4, GOOD) + NEW + value_bits(code, 2) + NEW + value_bits(code, 3)
        with self.assertRaisesRegex(DecodeError, "last chunk left=2"):
            self.decode(assemble(code, len(values), stream))

    def chunk_fault(self, **kw):
        stream = NEW + value_bits(4, 1) + chunk_header(2, GOOD, **kw) + SAME
        return self.decode(assemble(4, 2, stream))

    def test_chunk_header_with_two_different_counts(self):
        with self.assertRaisesRegex(DecodeError, "count mismatch 2/3"):
            self.chunk_fault(m2=3)

    def test_chunk_header_with_a_zero_count(self):
        stream = NEW + value_bits(4, 1) + chunk_header(0, GOOD) + SAME
        with self.assertRaisesRegex(DecodeError, "count mismatch 0/0"):
            self.decode(assemble(4, 2, stream))

    def test_chunk_header_with_two_different_qualities(self):
        with self.assertRaisesRegex(DecodeError, "unexpected chunk header"):
            self.chunk_fault(q2=BAD)

    def test_chunk_header_with_a_nonzero_tail(self):
        with self.assertRaisesRegex(DecodeError, "unexpected chunk header"):
            self.chunk_fault(tail="0" * 23 + "1")

    def test_chunk_header_with_a_wrong_constant(self):
        with self.assertRaisesRegex(DecodeError, "unexpected chunk header"):
            self.chunk_fault(const="0010000000000000")

    def test_chunk_header_with_a_nonzero_leading_byte(self):
        with self.assertRaisesRegex(DecodeError, "unexpected chunk header"):
            self.chunk_fault(lead="00000001")

    def test_chunk_header_with_the_top_bit_of_the_leading_byte_set(self):
        with self.assertRaisesRegex(DecodeError, "unexpected chunk header"):
            self.chunk_fault(lead="10000000")

    def test_chunk_header_constant_that_differs_only_in_its_second_last_bit(self):
        with self.assertRaisesRegex(DecodeError, "unexpected chunk header"):
            self.chunk_fault(const="0001000000000010")


def run_cli(*argv, stdin=""):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
            mock.patch.object(sys, "stdin", io.StringIO(stdin)):
        code = W.main(list(argv))
    return code, out.getvalue(), err.getvalue()


def dump_line(raw, begin="2024-01-01 06:00:00.000", end="2024-01-01 06:00:03.000"):
    """One line in the shape the documented sqlcmd command prints: padded columns joined by |."""
    return f"{begin} |{end} |{len(raw):<11}|{raw.hex().upper()}  "


class Cli(unittest.TestCase):
    BLOCK = encode_block([0.5, 0.5, 1.25], quals=[GOOD, GOOD, BAD])
    CSV = ("timestamp,value,quality\n"
           "2024-01-01T06:00:00.000Z,0.5,192\n"
           "2024-01-01T06:00:01.000Z,0.5,192\n"
           "2024-01-01T06:00:02.000Z,1.25,8\n")

    def write(self, text):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        p = Path(d.name) / "dump.txt"
        p.write_text(text)
        return str(p)

    def write_bytes(self, data):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        p = Path(d.name) / "dump.txt"
        p.write_bytes(data)
        return str(p)

    def test_a_file_with_a_byte_order_mark_decodes(self):
        path = self.write_bytes(b"\xef\xbb\xbf" + self.BLOCK.hex().encode() + b"\n")
        self.assertEqual(run_cli(path)[:2], (0, self.CSV))

    def test_a_block_that_runs_past_the_last_date_fails_alone(self):
        late = encode_block([1.0, 2.0, 3.0], t0=datetime.datetime(9999, 12, 31, 23, 59, 59))
        code, out, err = run_cli(stdin=late.hex() + "\n" + self.BLOCK.hex() + "\n")
        self.assertEqual((code, out, "line 1" in err, "Traceback" in err), (1, self.CSV, True, False))

    def test_a_block_whose_first_row_cannot_be_formatted_fails_alone(self):
        # the sample is representable; adding the half millisecond used for rounding is not
        late = encode_block([1.0], t0=datetime.datetime(9999, 12, 31, 23, 59, 59, 999800))
        self.assertEqual(len(W.decode_block(late)), 1)
        code, out, err = run_cli(stdin=late.hex() + "\n" + self.BLOCK.hex() + "\n")
        self.assertEqual((code, out, "line 1" in err, "Traceback" in err), (1, self.CSV, True, False))

    def test_hex_on_stdin(self):
        self.assertEqual(run_cli(stdin=self.BLOCK.hex() + "\n")[:2], (0, self.CSV))

    def test_dash_means_stdin(self):
        self.assertEqual(run_cli("-", stdin=self.BLOCK.hex() + "\n")[:2], (0, self.CSV))

    def test_dump_file_in_the_sqlcmd_shape(self):
        self.assertEqual(run_cli(self.write(dump_line(self.BLOCK) + "\n"))[:2], (0, self.CSV))

    def test_blocks_are_concatenated_under_one_header(self):
        second = encode_block([7], code=4, t0=T0 + datetime.timedelta(hours=1))
        code, out, err = run_cli(stdin=self.BLOCK.hex() + "\n" + second.hex() + "\n")
        self.assertEqual(out, self.CSV + "2024-01-01T07:00:00.000Z,7,192\n")

    def test_floats_print_with_float32_precision(self):
        out = run_cli(stdin=encode_block([0.1, 0.1]).hex())[1]
        self.assertEqual(out.splitlines()[1], "2024-01-01T06:00:00.000Z,0.100000001,192")

    def test_a_bad_block_is_reported_with_its_line_and_exit_1(self):
        bad = bytes([self.BLOCK[0] ^ 1]) + self.BLOCK[1:]
        code, out, err = run_cli(stdin=self.BLOCK.hex() + "\n" + bad.hex() + "\n")
        self.assertEqual((code, "line 2" in err, "checksum" in err), (1, True, True))

    def test_good_blocks_are_still_written_when_another_fails(self):
        bad = bytes([self.BLOCK[0] ^ 1]) + self.BLOCK[1:]
        code, out, err = run_cli(stdin=bad.hex() + "\n" + self.BLOCK.hex() + "\n")
        self.assertEqual(out, self.CSV)

    def test_text_that_is_not_hex_is_a_message_not_a_traceback(self):
        code, out, err = run_cli(stdin="Changed database context to 'x'.\n")
        self.assertEqual((code, "line 1" in err, "Traceback" in err), (1, True, False))

    def test_a_dump_line_with_too_few_fields_is_reported(self):
        code, out, err = run_cli(stdin="a|b|c\n")
        self.assertEqual((code, "line 1" in err), (1, True))

    def test_a_dump_line_with_too_many_fields_is_an_error(self):
        with self.assertRaises(DecodeError):
            W.block_from_line("a|b|c|" + self.BLOCK.hex() + "|extra")

    def test_input_with_no_blocks_exits_1(self):
        code, out, err = run_cli(stdin="\n\n")
        self.assertEqual((code, "no blocks" in err), (1, True))

    def test_blank_lines_are_skipped(self):
        self.assertEqual(run_cli(stdin="\n" + self.BLOCK.hex() + "\n\n")[:2], (0, self.CSV))

    def test_a_binary_file_exits_2(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        path = Path(d.name) / "segment.mdf"
        path.write_bytes(b"\xff\xfe\x00\x80" * 8)
        self.assertEqual(run_cli(str(path))[0], 2)

    def test_missing_file_exits_2(self):
        self.assertEqual(run_cli("/nonexistent/dump.txt")[0], 2)

    def test_too_many_arguments_exit_2(self):
        self.assertEqual(run_cli("a", "b")[0], 2)

    def test_timestamp_is_rounded_to_the_millisecond(self):
        dt = datetime.datetime(2024, 1, 1, 12, 0, 0, 999600)
        self.assertEqual(W.format_timestamp(dt), "2024-01-01T12:00:01.000Z")

    def test_timestamp_below_half_a_millisecond_rounds_down(self):
        dt = datetime.datetime(2024, 1, 1, 12, 0, 0, 400)
        self.assertEqual(W.format_timestamp(dt), "2024-01-01T12:00:00.000Z")

    def test_script_runs_as_a_program(self):
        r = subprocess.run([sys.executable, "-B", "-I", str(SCRIPT)], input=self.BLOCK.hex(),
                           capture_output=True, text=True, timeout=60)
        self.assertEqual((r.returncode, r.stdout), (0, self.CSV))


if __name__ == "__main__":
    unittest.main()
