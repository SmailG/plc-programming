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
  (ST text, object inventory). Use when working with any of these tools or files. For
  Siemens and Schneider use their dedicated skills.
---

# Other platforms: Beckhoff, CODESYS, ABB, Rockwell

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
  `dump-st <file.project> <outdir>` writes every ST POU; `graph <file.project> <name|guid>`
  lists the element records of an LD/FBD POU; `info <file.project>` prints each application's
  CodeId / DataId and the last save time (which saved project matches a running PLC);
  `diff <old> <new> [<name|guid>]` compares two versions; `xref <file.project> <name>` lists every
  use of a name (heuristic, by name only).
- **Prefer a PLCopen XML export from the IDE when one can be had.** Use the reader for ST
  text, inventories and as a lead, and **verify graphical wiring in the IDE** before acting
  on `graph`: wiring is not decoded.
- Details, what is decoded and what is a heuristic:
  [references/codesys-project-files.md](references/codesys-project-files.md).

Validate: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/plc_validate.py <file-or-dir>`.

- TwinCAT rules: TC0xx.
- Logix rules: LX0xx. The operand counts accept both the v36 IEC names and the older
  mnemonics.
- CSV lists: CS0xx.

For a new TwinCAT POU, start from [assets/FB_Template.TcPOU](assets/FB_Template.TcPOU).
