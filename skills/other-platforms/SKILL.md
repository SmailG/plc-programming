---
name: other-platforms
description: >-
  Platform knowledge for Beckhoff TwinCAT 3 (.TcPOU/.TcDUT/.TcGVL/.TcIO XML with CDATA,
  pragmas/attributes, FB_init, __NEW, PLC++), CODESYS V3.5 (SP22, PLCopenXML and .export,
  File-Based Storage, Static Analysis SA/NC rules, scriptengine), ABB Freelance (DCS: .prt
  block export, whole-project Unicode .csv, .plc/.ple, Bulk Data Manager) plus ABB
  Automation Builder (AC500) and 800xA Control Builder M, and Rockwell Studio 5000 Logix
  Designer (L5X/L5K, RLL neutral text XIC/XIO/OTE/TON, v36 IEC mnemonic renames, AOIs,
  FBD_TIMER in ST). Also reading a CODESYS/Machine Expert binary `.project` without the IDE
  (ST text, object inventory, build identity with `info`, comparing two versions with `diff`,
  where a name is used with `xref`). Also decoding the fast-archive blocks of a Siemens WinCC
  Tag Logging segment (`TagCompressed.BinValues`) to CSV without WinCC. Use when working with
  any of these tools or files. For Siemens PLCs (TIA Portal, S7) and Schneider use their
  dedicated skills.
---

# Other platforms: Beckhoff, CODESYS, ABB, Rockwell, WinCC archives

Load the reference for the platform in play. Each one lists the file format, the dialect's
differences from IEC 61131-3, and the traps.

| Platform | Current as of 2026-09 | Text/XML an assistant can safely write | Reference |
|---|---|---|---|
| Beckhoff TwinCAT 3 | 3.1 Build 4026; PLC++ announced (plain-text files, "almost fully compliant" with 61131-3 Ed.4), GA unverified | `.TcPOU` / `.TcDUT` / `.TcGVL` / `.TcIO` with **ST** bodies only | [references/beckhoff-twincat.md](references/beckhoff-twincat.md) |
| CODESYS V3.5 | SP22 (Patch 2); SP23 planned Q1 2027 | PLCopenXML (`tc6_0200`), `.export` (native), File-Based Storage `*.st` (preview) | [references/codesys.md](references/codesys.md) |
| CODESYS / Machine Expert `.project` (binary, no IDE) | undocumented format, reverse-engineered | **read only**: ST text and inventory by script; graphical wiring is a lead, not a fact | [references/codesys-project-files.md](references/codesys-project-files.md) |
| ABB Freelance (DCS) | Freelance 2024 (announced 2024-10-02); manuals read: 2019 | read the `.csv` export; bulk-edit via BDM Excel; **never hand-edit `.prt`/`.csv` for re-import without a backup** | [references/abb.md](references/abb.md) |
| ABB AC500 (Automation Builder) | CODESYS-based | PLCopenXML, `.export` (same-version only) | [references/abb.md](references/abb.md) |
| Rockwell Studio 5000 | v38 (Sept 2025) | L5X component exports, RLL neutral text, L5K | [references/rockwell-logix.md](references/rockwell-logix.md) |
| Siemens WinCC 7 Tag Logging fast archive (SQL Server segment files, no WinCC) | derived on 7.5 SP2; other versions untested | **read only**: `TagCompressed.BinValues` blocks to CSV by script; undocumented format, the compressed archive type is not decoded, and the int32 signedness is a guess | [references/wincc-tag-logging-archive.md](references/wincc-tag-logging-archive.md) |

## Cross-platform rules

- **Never hand-generate a graphical object archive.** That covers TwinCAT
  `<NWL>`/`<SFC>`/`<CFC>` `XmlArchive` implementations and CODESYS CFC XML. Write ST, or
  go through PLCopenXML import.
- **Version-pin every exchange file:**
  - The TwinCAT `ProductVersion` is optional, but keep it when editing.
  - Automation Builder `.export` imports only into the same version.
  - An L5X names its `SoftwareRevision`.
- **Qualify names the way the target expects:**
  - TwinCAT/CODESYS GVLs and enums with `{attribute 'qualified_only'}` need `GVL.x` and
    `E_X.Member`.
  - Logix has no qualifier: tags are controller- or program-scoped.

## Reading a CODESYS `.project` without the IDE

A repository that commits only the binary `.project` (CODESYS 3.5, Machine Expert) is not
opaque to the plugin. The format is **undocumented**; the reader is reverse-engineered and
checked on Machine Expert V2.x files only.

- `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/codesys_project.py list <file.project>` inventories
  the objects; `st <file.project> <name|guid>` prints a POU's declaration and implementation;
  `dump-st <file.project> <outdir>` writes every ST POU and GVL/DUT declaration; `graph <file.project> <name|guid>`
  lists the element records of an LD/FBD POU; `info <file.project>` prints each application's
  CodeId / DataId and the last save time (a lead to which saved project a PLC runs; the IDE decides);
  `diff <old> <new> [<name|guid>]` compares two versions; `xref <file.project> <name>` lists every
  use of a name (heuristic, by name only).
- **Prefer a PLCopen XML export from the IDE when one can be had.** Use the reader for ST
  text, inventories and as a lead, and **verify graphical wiring in the IDE** before acting
  on `graph`: wiring is not decoded.
- Details, what is decoded and what is a heuristic:
  [references/codesys-project-files.md](references/codesys-project-files.md).

## Reading a WinCC Tag Logging fast archive without WinCC

Process history that lives in swapped-out segment files (`.mdf` / `.ldf`) of a WinCC 7 Tag
Logging fast archive is stored as compressed blocks in `TagCompressed.BinValues`. The format is
**undocumented**; the decoder is reverse-engineered on WinCC 7.5 SP2 and untested on other
versions.

- Attach copies of the segment to a **separate** SQL Server instance (never a live WinCC),
  dump the blocks of one tag, then
  `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/wincc_binvalues.py dump.txt > tag.csv`
  (`timestamp,value,quality`; standard input works too). The query, the `sqlcmd -y` trap that
  truncates long blocks, and the exit codes are in the reference.
- **Exclude quality other than 192 (`0xC0`) when averaging**; a bad chunk repeats the last good value.
- A block that fails is reported by line and skipped, and about 0.1 % of blocks failed in a
  large run (not investigated). A decoded value is not proof the archive was undamaged.
- **Not decoded**: archives of the compressed type, and the signedness of the 32-bit integer
  code is a guess. Details and what is established:
  [references/wincc-tag-logging-archive.md](references/wincc-tag-logging-archive.md).

Validate: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/plc_validate.py <file-or-dir>`.

- TwinCAT rules: TC0xx.
- Logix rules: LX0xx. The operand counts accept both the v36 IEC names and the older
  mnemonics.
- CSV lists: CS0xx.

For a new TwinCAT POU, start from [assets/FB_Template.TcPOU](assets/FB_Template.TcPOU).
