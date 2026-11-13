# Reading WinCC Tag Logging fast-archive blocks offline

For Siemens WinCC (classic, "WinCC 7") Tag Logging **fast archives** whose swapped-out segments
are SQL Server `.mdf` / `.ldf` files and where the values sit in `TagCompressed.BinValues` as a
compressed binary block. The plugin ships a decoder, `scripts/wincc_binvalues.py`, standard
library only, Python 3.9+. WinCC Unified, the WinCC OA product and the TIA Portal are different
products and are not covered here.

## Status: undocumented and reverse-engineered

**There is no Siemens documentation for this block format.** Everything below was worked out by
decoding real archives and checking the result against other data. Nothing is confirmed by
Siemens, and a newer or older WinCC may differ. Labels used on this page:

- **Established**: a check that can fail was run and passed (stated next to each item).
- **Guess**: chosen because nothing seen contradicts it; the decoder pins it in a test, and a
  value that would show the guess is wrong was never seen.
- **Not decoded**: the decoder does not try, or ignores the field.

Derived on **WinCC 7.5 SP2** fast archives (two single-day segments for the format itself, then
669 segments for a bulk run); "7.5 SP2" is the maintainer's statement, not read from the segment
files. **Other WinCC versions are untested.** When the user's version
differs, or a block fails to decode, say so and treat the output as unverified.

## Safe workflow

1. **Never attach a segment to a live WinCC instance** (maintainer's instruction): use a separate
   SQL Server instance, and work on **copies** of the `.mdf` / `.ldf` pair. Microsoft documents
   that attaching upgrades a database created by an older SQL Server version, and that it cannot
   then be attached to an earlier version again
   ([Database detach and attach](https://learn.microsoft.com/sql/relational-databases/databases/database-detach-and-attach-sql-server)).
   The work behind this page used SQL Server 2019; the lowest version that can attach WinCC 7.5
   segments was not checked.
2. Attach the pair. The segment files whose names contain `TLG_F` held the fast archive here.

   ```sql
   CREATE DATABASE [seg1] ON (FILENAME='<path>/seg1.mdf'), (FILENAME='<path>/seg1.ldf') FOR ATTACH;
   ```

3. Dump the blocks of one tag, in the line shape the decoder reads (three columns it ignores,
   then the hex). The table and column names `TagCompressed`, `Archive`, `ValueID`, `ValueName`,
   `Timebegin` and `BinValues` are **established** (used in the bulk run); `ValueName` held
   `<archive name>\<tag name>`, for example `Archive\Tag_1`.

   ```sql
   SET NOCOUNT ON;
   SELECT CONVERT(varchar(23), t.Timebegin, 121), t.ValueID, DATALENGTH(t.BinValues),
          CONVERT(varchar(max), t.BinValues, 2)
   FROM TagCompressed t JOIN Archive a ON a.ValueID = t.ValueID
   WHERE a.ValueName = N'Archive\Tag_1' ORDER BY t.Timebegin;
   ```

   ```text
   sqlcmd -S <server> -d seg1 -s '|' -h -1 -y 0 -Q "<the query above>" > dump.txt
   ```

   This is for a POSIX shell; the `'|'` quoting is shell-specific, so quote the `|` as your shell
   requires. **The dump must be UTF-8** (the decoder opens a file as UTF-8 and accepts a byte order
   mark). A UTF-16 file is refused with exit 2 and is not sniffed or converted: convert it first.
   Which `sqlcmd` and shell combinations write which encoding was **not checked** here.

   **`-y` matters.** `sqlcmd` cuts a `varchar(max)` column to `-y` characters (default 256;
   [sqlcmd utility](https://learn.microsoft.com/sql/tools/sqlcmd/sqlcmd-utility)), and a byte is
   two hex characters, while the block length field is 16 bits (up to 65 535 bytes). `-y 0` is
   unlimited (Microsoft warns it can be slow on large results). **Not run here:** the bulk run used
   `-y 8000`, which cuts a block at 4000 bytes. A cut block fails the checksum or the length
   check. The failing blocks of the bulk run were classified later (see Bulk run) and fell into
   other classes, so a cut block did not explain them; the checksum and length checks stay the
   guard against a cut.
4. Decode: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/wincc_binvalues.py dump.txt > tag.csv`, or one
   block as hex on standard input. The CSV columns are `timestamp,value,quality`: UTC to the
   millisecond, the value, the OPC quality byte in decimal (192 = `0xC0` good, 8 = `0x08` bad).
   Exit 0 clean, 1 if some blocks failed (their line numbers go to standard error, the others are
   still written) or none were found, 2 for unreadable input or a usage error (such as too many
   arguments).
5. **Exclude `quality != 192` when averaging.** **Established** (observed on an outage in the
   source data; no automated check): a bad-quality chunk carries the last good value frozen, not
   a gap.
6. Never commit real archive bytes, tag names or segment names to a public repository.

## Block header (37 bytes)

| Offset | Size | Meaning | Status |
|---|---|---|---|
| 0 | 1 | XOR of bytes 1 to the end (checksum) | **Established**: matched on all 3179 blocks examined |
| 1-3 | 3 | `05 04 00`, constant | constant; meaning guessed (byte 1 = 5 might be a compression mode) |
| 4 | 1 | value code, the representation of every value in the block (table below) | **Established** |
| 5-6 | 2 | `20 20`, constant | not decoded |
| 7-8 | 2 | uint16 little-endian total block length in bytes | **Established** |
| 9-12 | 4 | uint32 LE sample count `n` (the span in periods plus one) | **Established** |
| 13-20 | 8 | double, OLE automation date of the first sample (epoch 1899-12-30). It equals the segment table's `Timebegin`, which WinCC stores in UTC (vendor behaviour, not re-verified here), so the CSV is UTC | **Established** |
| 21-24 | 4 | uint32 LE period in ms (1000 in the two-day totals below; 500 was seen on a few binary-flag tags outside those totals). A period of 0 is rejected | **Established** |
| 25-36 | 12 | a double (a second timestamp) and a uint32 | **Not decoded**, ignored: a bad value there never fails a block |

## Value codes (header byte 4)

| Code | Value | Status |
|---|---|---|
| 3 | float32, little-endian | width **established** |
| 4 | int16 | width **established**; signed because negative values occurred |
| 5 | int8 | width **established**; signed because negative values occurred |
| 6 | uint8 | width **established**; unsigned (values above 127 occurred) |
| 7 | uint16 | width **established**; unsigned (a Wh counter matched a float kWh counter times 1000 on samples above 32 767) |
| 8 | int32 | width **established**; **signedness is a guess**: no value of 2^31 or more occurred |

Widths follow from bit accounting: the whole stream of every block is consumed exactly. A float
tag switches to code 4, 5, 6 or 8 for a block whose values are all whole numbers, so a block ends
when the value stops being integral. In the two days the format was derived on no other code was
seen; the bulk run later met code `1` (below). A float64 code presumably exists (a guess).

## Bit stream (from byte 37, read MSB-first)

A multi-byte value is its little-endian bytes in order, each byte MSB-first. **Established** by
decoding every block examined without a bit left over.

1. The initial value: a `0` bit, then the value (`w` bits).
2. A chunk header (84 bits, below).
3. One token per later sample:
   - `11`: the same value as the previous sample;
   - `0` then `w` bits: a new value;
   - `10` then `cc`: a value from the history (below). `cc` = `01`, `10`, `11` gives index 1, 2,
     3; `cc` = `00` is followed by 4 more bits `x` and gives index 4 + `x`.
4. Zero bits up to the byte boundary (fewer than 8).

### Chunk header (84 bits)

| Bits | Content |
|---|---|
| 10 | `m`, the samples in the chunk (at most 1023) |
| 8 | zeros |
| 8 | `q`, the OPC quality byte (`0xC0` good, `0x08` bad / not connected seen) |
| 16 | `0001000000000000`, **whose last bit is a daylight-saving flag** |
| 10 | `m` again |
| 24 | zeros |
| 8 | `q` again |

- A chunk is cut at 1023 samples or where the quality changes (**established**: every header's
  two counts and two quality bytes agreed).
- **Daylight-saving flag** (a late finding): across 669 segments the last bit of the 16-bit
  constant was 1 in every summer-time segment and 0 in every winter-time one. That is a
  correlation; Siemens does not document the bit. The decoder accepts both values and ignores it.
- **Bookkeeping**: the `m` of all chunks add up to `n`. Chunk *i* covers the samples from the sum of
  the earlier counts, counted from the initial value; its header sits immediately after its first
  sample, so quality is assigned by these ranges, not by where the header sits. A block whose
  last chunk filled exactly ends with an empty header (`m` = 1, no tokens).

### Value history (move-to-front, 19 entries)

A reference token reads from a list of the 19 most recent distinct values. Index 0 is the current
value; a new or referenced value moves to the front; the 19th is pushed out. **Established** by a
check that can fail: an encoder never spends a full value on one it could reference, so counting
the new-value tokens whose value was already in the decoder's history must give zero. With a
19-entry move-to-front list it did, on two days (0 of 382 021 and 0 of 292 581 tokens); a
FIFO of all changes gave 332 and 164, and a list of 20 gave 918 and 361. Index 19 (`x` = 15) never
occurs, and the decoder rejects it.

**Guess: the history compares raw bits.** Entries are kept and matched by their raw value bytes,
so `0.0` and `-0.0` are two entries and a NaN matches an identical NaN. WinCC's own rule is
**unverified**; a test pins the choice with a hand-written bit vector.

### Timestamps

There are no time tokens: sample *k* is at the header's first time plus *k* times the period
(**established**: for the tags checked, the last sample matched the block's end time and the
concatenated blocks had no gap).

## Evidence

- **Format**: all 3179 fast-archive blocks of two 24-hour segments (81 and 30 tags, 6 998 400 and
  2 592 000 samples) decode with the checksum matching, every chunk header consistent, exactly `n`
  samples, and fewer than 8 zero padding bits left.
- **Values**: the integral of an inverter's power tag matched the rise of its two energy counters
  to within 0.2 % (ratios 0.998 to 1.000) over four windows. The maintainer's check; the scripts
  and data are not in this repository.
- **Corruption control**: one flipped bit is caught by the checksum. With the checksum repaired, a
  flip inside a value field decodes without any error: **the stream checks cannot catch every
  corruption**, so a decoded value is not proof the archive was undamaged.
- **Bulk run**: 669 segments, 646 decode without a single failing block. The other 23 had a few
  failing blocks (about 540 of about 450 000, 0.1 %). The failing blocks were classified afterwards
  (see below): an unknown value code, and the first chunk header of a block written right after a
  runtime restart. Together these account for essentially all of the failing blocks seen. Those
  two classes are not decoded.

## What is not decoded or not established

- **Archives of the compressed type** (a second archive type in the same segments: header byte 4
  = 0, a 60 000 ms period, and a different chunk-header constant, `0001000010000000`): **not
  decoded**. The decoder rejects them rather than guess.
- **Value code `1`**: occurs in the bulk run, is not in the code table, and its width is
  unknown; the decoder rejects the block as an unknown value code.
- **Blocks written immediately after a runtime restart**: they fail the chunk-header check
  ("count mismatch" or "unexpected chunk header" at the first header). They have a different
  first-chunk layout, which is not decoded.
- Header bytes 1-3, 5-6 and 25-36: **not checked**, so a damaged value there does not fail a
  block. Nor are the value of a quality byte or the daylight-saving bit checked.
- **Signedness of code 8** (a guess), and codes other than 3 to 8.
- Qualities other than `0xC0` and `0x08` never occurred; any 8-bit value is passed through.
- Only two days were examined to derive the format; other years may hold codes or tokens not seen.
  The decoder raises `DecodeError` for a block that fails one of its checks (checksum, length,
  sample count and period, value code, chunk headers, stream consistency) instead of guessing; it
  accepts anything those checks and the unchecked fields above let through.
- The meaning of the daylight-saving bit beyond the correlation above.
- WinCC versions other than 7.5 SP2.

## Tests

`tests/test_wincc_binvalues.py` builds **synthetic** blocks with a small encoder written from this
page: each value code, a chunk split at 1023 samples, a quality change, short and long history
references, the daylight-saving bit set and clear, and the rejected inputs (checksum, length,
value code, chunk header, padding, truncation). The encoder is the same author's reading of the
format, so these tests show that the decoder and the page agree, not that the page matches
WinCC. One test, for the history rule, uses a bit vector written out by hand without the encoder;
it is still the same reading of the format. No real block, tag name or segment is committed.
