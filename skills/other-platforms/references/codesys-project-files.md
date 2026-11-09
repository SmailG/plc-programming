# Reading a CODESYS `.project` without the IDE

For a CODESYS 3.5 or EcoStruxure Machine Expert `.project` that is the only copy of a
program (a repository that commits the binary and nothing else). The plugin ships a
reader, `scripts/codesys_project.py`, standard library only, Python 3.9+.

## Status: undocumented and reverse-engineered

**There is no vendor documentation for this format.** The layout below was worked out by
looking at real project files. Nothing in it is confirmed by CODESYS or Schneider Electric,
and a newer IDE may change it. Labels used on this page:

- **Observed**: seen in the files examined, and implemented that way.
- **Heuristic**: an interpretation of observed bytes, not confirmed against the IDE.
- **Not decoded**: the reader does not try.

Files examined (**observed**): three Machine Expert V2.x `.project` files of one application
lineage, each holding Structured Text and LD/FBD POUs, saved by an IDE built on CODESYS
3.5.21.50 (that version string occurs in the files' `.auxiliary` entries; the Machine Expert
version itself is the maintainer's statement, not read from the files). **Nothing else was
checked**: other CODESYS vendors (Beckhoff, WAGO, ABB), other service packs, CFC, SFC, IL,
methods, actions, properties, visualisations and encrypted or compiled-library files are
**unverified**. When the user's version differs, say so and ask for a PLCopen XML export.

## Safe workflow

1. **Prefer a PLCopen XML export from the IDE** (or the scriptengine on a machine that has
   the IDE; formats and trade-offs in [codesys.md](codesys.md)). Connections between
   graphical elements are explicit there. The reader cannot give you that.
2. If only the `.project` exists, use the reader for **ST text, the object inventory, names,
   declarations and as a lead** for graphical POUs.
3. **Verify graphical wiring in the IDE** before acting on anything from `graph`. The reader
   lists which elements a network contains; it does not say which output feeds which input.
4. Never write back into a `.project`. The reader is read-only, and the format is not
   understood well enough to write.

## Commands

```text
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/codesys_project.py list PROJECT [--json] [--kind KIND]
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/codesys_project.py st PROJECT NAME_OR_GUID [--decl | --impl]
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/codesys_project.py dump-st PROJECT OUTDIR
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/codesys_project.py graph PROJECT NAME_OR_GUID [--json]
```

| Command | Output |
|---|---|
| `list` | every object: guid, kind, subtype, name, ancestor names. `--kind` is one of `st`, `graphical`, `gvl`, `dut`, `other`, `unreadable` |
| `st` | declaration and implementation text of an ST POU. For a graphical POU: the declaration only. `--decl` / `--impl` print one part raw |
| `dump-st` | every ST object as `<Device>_<Name>.decl.st` and `.impl.st`. Text is written byte for byte (CRLF kept) |
| `graph` | the element records and network comments of an LD/FBD POU, as text or `--json` |

- **Names are not unique.** Two devices can each have an `Application`, and a POU can
  exist once per device. `st` and `graph` refuse an ambiguous name (exit 2) and list the
  candidates with their ancestors; give the guid, or the first 8 or more characters of it.
- **`dump-st` file names** start with the root-most ancestor (the device), which is a
  heuristic. Names that collide, including by case, all get `_<first 8 of the guid>`, so no
  file is overwritten. Names come from the file and are made safe as one path component.
- **Exit codes:** 0 clean; 1 the result was printed but some objects had problems (listed on
  stderr, one `PROBLEM <guid>` line each); 2 usage error, unreadable file, unknown or
  ambiguous name, or the object has the wrong kind for the command.
- A damaged object is reported and skipped; it does not stop the other objects from being read.

## What is decoded

| Item | Status | How |
|---|---|---|
| Zip container, shared string table | **Observed** | `.project` is an ordinary zip. `__shared_data_storage_string_table__.auxiliary` is a varint count, then (index, byte length, UTF-8 bytes) entries. A count that does not match, a duplicate index or an entry past the end of the file is an error |
| Object guid, parent guid, name | **Observed** | each object is `<guid>.meta` plus `<guid>.object`. The `.meta` is a varint stream; mapped through the string table, the object's own guid is followed by its parent guid and its name |
| Object header | **Observed** | 20 bytes: `02 20 09 28`, 12 zero bytes, then a little-endian uint32 equal to the number of bytes that follow. All objects of the three files satisfied it. A violation marks the object `unreadable` |
| ST declaration and implementation text | **Observed** | the object holds string-table indices, not text. A text slot is `<marker> e5 02 <text index> <reference index>`, marker `41` for the declaration and `5b` for the implementation; the reference string is `<guid>_Decl_LineIds` or `<guid>_Impl_LineIds`. A marker whose reference does not match is treated as data. 32 of 32 ST files of one project were byte-identical to an earlier extraction that located the text by fixed varint positions instead (a different rule, same file) |
| Network comments, element name and type, box type, instance and header id, pin names, modifier byte | **Observed** | see Graphical objects |
| Kind (`st`, `graphical`, `gvl`, `dut`, `other`) | **Heuristic** | from the payload: a network record means graphical; a declaration slot and an implementation slot mean ST; a declaration slot only is a GVL (`VAR…`) or a DUT (`TYPE`); anything else is `other`. Vendor type guids are not used because their position in the `.meta` varied |
| `subtype` | **Heuristic** | the first keyword of the declaration after comments and pragmas: `PROGRAM`, `FUNCTION_BLOCK`, `FUNCTION`, `METHOD`, ... |
| Device, application | **Heuristic** | device is the root-most ancestor; application is the node under a node named `Plc Logic` (case-insensitive) |

## Graphical objects

**Observed:** a graphical (LD/FBD) object holds its declaration in a text slot near the end,
a language string in its header (only `Ld` was seen, on 12 of 12 graphical objects; the
reader prints it and does not tell LD from FBD), and one record per network. A network record
starts `0f e1 02` or `0f e7 02` (both are networks with a comment; what separates the two
tags is **not decoded**).

`graph` scans each network and lists, in file order:

| Record | Decoded fields | Heuristic fields |
|---|---|---|
| element | name, type, modifier byte (raw) | `IN`/`OUT` (the byte before the record is `69` for an input), `coil` (an output right after a coil-count record), the modifier meaning |
| box | type, instance name, header id | nesting depth (a box spans from its header id H to the next 8-byte id H+1) |
| coils | count byte | |
| pins | pin names | |
| empty | raw bytes, id | what an empty slot means |
| parallel_marker | value byte | what it means (**unverified**) |
| unknown | the reason and 16 raw bytes | a record that was recognised but could not be read (a name index not in the string table, a record that runs past the end) |

Modifier meanings are **unverified** against the IDE. The reader always shows the raw code
and adds the labels `negated` (1), `set` (2) and `reset` (3) as a heuristic. What was
observed in the three files: `2` and `3` only on coil outputs, `1` on inputs and on coils,
`16` and `32` only on inputs. The labels fit the usual LD coil and contact kinds, but no
manual or IDE check confirms them, and `16` and `32` have no label. An `IN` is either an LD
contact or an FBD input; the file does not say which.

**Not decoded: the wiring.** `ids` are 8-byte little-endian values found by scanning, and
the filler id `733` is dropped. They are a **heuristic**: a one-byte id (below 256) can come
out shifted by a byte (value times 256 plus the byte before it). Use them to compare within
one object, never as an absolute id, and never to claim that one element feeds another.
Bytes that match no recognised record are skipped without a note, so a clean `graph` run
does not mean every byte was understood. The notes list only records that were recognised
and could not be read.

## Checking a decode

`graph` output is a lead. To use it:

1. Compare the element list and the network comments with the network in the IDE.
2. If a PLCopen XML export exists, the explicit connections there take precedence.
3. Treat a missing element as possible: an element whose record shape was not recognised is
   skipped silently.

## Sources and checks

- **No vendor source exists** for the container, string table, `.meta`, `.object`, text
  slots or graphical records. Everything above is **observed** on the files named in Status.
- The reader was compared locally with earlier ad-hoc extraction scripts on the real files
  (not part of this repository): the text of all 32 ST files of one project matched byte for
  byte. For the 12 graphical objects of that project the reader found all 2189 element, box,
  coil and empty-slot records of the earlier tree decoder (offset, kind, names, box id); 5
  differ only in the label for modifier 32, and the reader found 35 more empty slots, which
  the earlier tool's pattern missed.
- The tests in `tests/test_codesys_project.py` use **synthetic** projects built from this
  layout. They show the reader implements what is written here; they do not show that the
  layout matches every file the IDE produces.
