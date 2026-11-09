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
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/codesys_project.py info PROJECT [--json]
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/codesys_project.py diff OLD NEW [NAME_OR_GUID] [--json]
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/codesys_project.py xref PROJECT NAME [--json]
```

| Command | Output |
|---|---|
| `list` | every object: guid, kind, subtype, name, ancestor names. `--kind` is one of `st`, `graphical`, `gvl`, `dut`, `other`, `unreadable` |
| `st` | declaration and implementation text of an ST POU. For a graphical POU, a GVL or a DUT: the declaration only. `--decl` / `--impl` print one part raw |
| `dump-st` | every ST POU as `<Device>_<Name>.decl.st` and `.impl.st`, and every GVL and DUT as `.decl.st`. Text is written byte for byte (CRLF kept) |
| `graph` | the element records and network comments of an LD/FBD POU, as text or `--json` |
| `info` | per device application: CodeId and DataId (the build identity), and the project's last save time. See [Which saved project matches a running PLC](#which-saved-project-matches-a-running-plc) |
| `diff` | with a POU name or guid: the unified diff of its declaration and implementation (ST) or of its decoded graph (LD/FBD) between two project files. Without one: the objects added, removed and changed. See [Comparing two versions](#comparing-two-versions) |
| `xref` | every ST and LD/FBD use of a variable, instance or type name, with a read / write role where one can be told. **Heuristic**, see [Finding where a name is used](#finding-where-a-name-is-used) |

- **Names are not unique.** Two devices can each have an `Application`, and a POU can
  exist once per device. `st` and `graph` refuse an ambiguous name (exit 2) and list the
  candidates with their ancestors; give the guid, or the first 8 or more characters of it.
  Names and guids match in any case. `diff OLD NEW <name>` takes a renamed POU's old or new
  name: it is resolved where it exists and found in the other version by guid.
- **`dump-st` file names** start with the root-most ancestor (the device), which is a
  heuristic. Names that collide, including by case, all get `_<first 8 of the guid>`, so no
  file is overwritten. Names come from the file and are made safe as one path component.
- **Exit codes:** 0 clean; 1 the result was printed but some objects had problems (listed on
  stderr, one `PROBLEM <guid>` line each) or a decoder note was raised; 2 usage error,
  unreadable file, unknown or ambiguous name, or the object has the wrong kind for the command.
  `diff` exits 0 when the two projects differ: a difference is its result, not a problem.
- A damaged object is reported and skipped; it does not stop the other objects from being read.
  A zip entry that fails its CRC, does not inflate, is encrypted, or inflates past 256 MiB is
  that object's problem; the same failure on the string table makes the file unreadable (exit 2).
  `info` refuses an XML entry that declares a DOCTYPE or an ENTITY, whatever its encoding.

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
| Build identity: CodeId, DataId, device model and firmware version | **Observed** | `devicesmetainformation.auxiliary` is plain XML: a `<Device>` per controller with `Name`, `DeviceType`, `DeviceId`, `DeviceVersion`, `DeviceName` and one `<Application>` with `Name`, `CodeId`, `DataId` (`System.Guid`). In all three files the id is a guid whose first group varies and whose other groups are zero |
| Last save time | **Observed** | `engineeringtoolsversions.auxiliary` holds a `<History>` of entries with `LastTimeSaved` (`YYYY-MM-DD-HH-MM-SS`, the saving machine's clock) and `SaveCounter`. The newest `LastTimeSaved` equalled the zip entries' own save time to within seconds in all three files. It is a **save**, not a compile |

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
| empty | raw bytes, id | what an empty slot means. An empty name is string-table index 39 (`""` in every project examined; **observed**, the reader does not look it up) |
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

## Comparing two versions

`diff OLD NEW POU` compares one POU between two project files; `diff OLD NEW` lists what
changed in the whole project. Objects are matched by **guid**, which stayed the same across
the saved versions of one project examined (**observed**: in three pairs of versions compared,
no object of the older file was missing by guid from the newer one); a renamed object keeps its guid and is listed as
`renamed from`, a moved one as `moved from`.

- **ST and declarations:** the text is compared line by line, line endings ignored.
- **LD/FBD:** the decoded graph is compared as text with everything that changes on a re-save
  left out: byte offsets, element ids, box header ids, the id and bytes of an empty slot, the
  raw bytes of an unreadable record. What stays in: element names and types, **constants**,
  the modifier byte, network comments, box type and instance, box nesting and the coil count.
  A constant that changes from 500 to 600 shows. A network inserted in the middle shows as an
  insertion, not as every later network changing.
- **Not compared, so not visible:** the **wiring** (the reader does not decode it), and bytes
  the graph decoder does not recognise. "No differences" means no difference in the fields above,
  never that the two POUs are identical. Where the wiring matters, use the IDE's own compare.
- Objects of kind `other` (devices, tasks, I/O mappings) are counted as "not compared", not
  diffed. The project-level summary lists what was added, removed and changed, with the sections
  that differ (`declaration`, `implementation`, `graph`).
- The modifier labels (`~negated`, `~set`, `~reset`) and `IN`/`OUT` are the same **heuristics**
  as in `graph`; a changed label means a changed modifier byte, not necessarily a changed meaning.
- **Checked on real files** (not part of this repository): the graph diff of one POU between two
  saved versions of one application found the same element, comment and box changes as an
  earlier text diff of two decoded dumps. It also showed two four-digit constant changes that
  the earlier diff had normalised away together with the ids, and it reported no difference for
  a POU whose bytes were identical in two versions. Between two versions of that application the
  six ST POUs that `diff` listed as changed were exactly the six whose `dump-st` files differ
  byte for byte. No real graphical object was
  found whose bytes differed while its normalised graph did not, so the id and offset
  normalisation is proven by the synthetic tests only.

## Finding where a name is used

`xref PROJECT NAME` lists every use of a variable, function block instance or type name in ST
text, declarations and decoded LD/FBD elements. **Everything it prints is a heuristic.**

- **By name only.** Matching is case-insensitive (IEC 61131-3 is) and has no scope resolution: a
  local variable and a global with the same name both match, and `x.Foo` matches the query `Foo`
  as well as `Foo.x`. A dotted query (`Gvl.Foo`) matches paths with those segments in a row.
- **Roles in ST:** `write` is the target before `:=` outside a call, or the variable after `=>`;
  `read` is any other use (an array index of a target is a read); `call` is a name followed by
  `(`; `param` is the formal name before `:=` or `=>` inside a call; `arg` is the value after
  `name :=` inside a call. **`arg` is not a read:** whether the callee writes it depends on the
  parameter's declaration (`VAR_IN_OUT`, `VAR_OUTPUT`), which is not read.
- **Roles in declarations:** `declared`, `type` (after the `:`, and a header's return type or `TYPE` definition), `read` (an initial value). A header (`FUNCTION F : BOOL`, `TYPE T : STRUCT`) declares its own name.
- **LD/FBD:** `write` for an element the decoder labels OUT, `read` for IN (both resting on the
  heuristic direction), `read` for names inside an index, `type` for a box type, `call` for a
  box instance. A constant is not a name. Wiring is not decoded.
- **What it cannot see:** objects of kind `other` (the device tree: a variable mapped to an I/O
  channel there is not found), graphical records the decoder could not read (the output says
  how many), and names built at run time (pointers, `ADR` arithmetic). A name that does not
  appear in the output may still be used; treat "no hits" as "none found", not as "unused".
- Comments, pragmas and string literals are skipped; nested block comments are handled.

## Which saved project matches a running PLC

When several saved copies of a program exist and one controller runs one of them, `info`
prints what the IDE uses to tell: the **CodeId** and **DataId** of each device's application,
as stored in the project. The IDE compares them with the controller's (**not verified here**:
the vendor does not document the comparison).

1. In the IDE, online with the controller, read the application's CodeId (the menu differs
   between versions; which one shows it was not checked here).
2. Run `info` on each candidate `.project`. A candidate whose CodeId equals the controller's is
   the build that runs. Equal DataIds across two versions suggest the retained and persistent
   variables did not change (**inferred**, one lineage; what DataId encodes is not documented).
3. **Both byte orders are printed.** The boot image the IDE writes beside the project
   (`.bootinfo_guids`, not part of the zip) stores the id with its first four bytes reversed
   (**observed**: of 8 ids, the CodeId and DataId of two applications in each of two projects, 7
   occur in that file in the reversed order and none in the plain order). Which order the IDE
   *displays* was **not checked**: compare against both before concluding "no match".
4. **A mismatch is not proof.** In the same check one CodeId from the project metadata occurred
   in the boot image beside it in neither order, and the cause is unknown. The IDE's comparison
   with the real controller is what decides, never this reader.
5. **If none matches,** the controller may run a build that was never saved (an edit downloaded
   and the project closed unsaved: a possibility, not observed here). Say so rather than naming
   the nearest candidate.

**There is no compile time in the project.** `info` prints the last **save** time, which can
be earlier or later than the build that runs. The compile time is written by the IDE next to the
project file (**unverified**: `.compileinfo` and `.bootinfo` files beside the project were seen,
and are not part of the zip and not decoded here), and by the IDE's build messages. When the identity cannot be read off the
controller, match the build to **logged data** instead: find when a logged signal's behaviour
changed, take the compile time of each candidate (**unverified**: that the `.compileinfo` file's
modification time is the compile time was not checked; this reader does not read the file), and use
`diff` between consecutive candidates to see which POU changes could explain the change. Name the
evidence tier: a timestamp match is a coincidence candidate until a CodeId confirms it.

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
- The tests in `tests/test_codesys_project.py` and `tests/test_codesys_tools.py` use **synthetic** projects built from this
  layout. They show the reader implements what is written here; they do not show that the
  layout matches every file the IDE produces.
