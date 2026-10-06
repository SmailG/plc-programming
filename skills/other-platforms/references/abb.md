# ABB: Freelance (DCS), AC500 (Automation Builder), 800xA / AC 800M

## Freelance: what "PRT" and "CSV" are

The primary sources are the Freelance 2019 Engineering Manuals *System Configuration*
(3BDD012503-111 A) and *Bulk Data Manager* (2PAA105801-111 A). The engineering tool was
formerly called Control Builder F.

| File | Meaning |
|---|---|
| `*.pro` | the project database (`*.prs` when password-encrypted) |
| **`*.prt`** | **partial-project / block export.** Select a project-tree node, then *Edit › Export block…*: "Exports the entire content of the selected block to a PRT file which can reload by using the Import block command". *Import block* puts it in the **POOL**. From there you move it into the tree, and "imported variables are not allocated to a process station". Name collisions are resolved by registry keys (`AutoRenameEAM`/`AutoRenameMSR`): variable names are kept, and tag names get `…00`, `…01` suffixes if they collide. |
| **`*.csv`** (Project › Export…) | the **whole project** as a Unicode export. **This is the only export that can be re-imported.** It is guaranteed only within one main version or between two consecutive main versions. ABB warns that offline edits "are not recognized … and could possibly destroy the project database" |
| `*.plc` / `*.ple` | PLCopen and extended PLCopen exports "for transferring the project data to other systems, such as Maestro UX and System 800xA". They are not re-importable |
| `*.hwm` | hardware-structure block export |
| `.eam` / `.msr` | project files, inferred to be variables (EAM) and tags (MSR = *Mess-, Steuer-, Regel-*) |

Password protection encrypts these files to `.prts`, `.csvs` and so on.

### Structure of the CSV/PLC export

This comes from community reverse-engineering (the FreelanceAPI parser), not from ABB.
Treat it as provisional.

- The files are **semicolon-separated**. The first line is
  `[Program-Generated File -- DO NOT MODIFY]`, followed by `[DUMP_VERSION];…` and
  `[DUMP_FILETYPE];…`.
- They are divided into **bracketed sections**:
  - project: `[BEGIN_PROJECTHEADER]`, `[BEGIN_AREADEFINITION]`
  - hardware and tree: `[BEGIN_HARDWAREMANAGER]`, `[BEGIN_PBAUMSECTION]` (project tree),
    `[BEGIN_NODESECTION]`
  - tags and variables: `[BEGIN_MSRSECTION]` (tags), `[BEGIN_EAMSECTION]` (variables),
    `[BEGIN_EAMINITSECTION]`
  - connections and OPC: `[BEGIN_OPCADDRESSSECTION]`, `[BEGIN_CONNSECTION]`
  - each section closes with a matching `[END_…]`.
- Record lines look like `[MSR:RECORD];1;M1234;BST_LIB_MSR;M_BIN;short;long;;128;1;;;;2` and
  `[EAM:RECORD];1;54321_IN1;0;INT;Variabel;1;0`.
- **Row widths differ by record type.** That is why validator rule CS002 is a warning, not
  an error.
- **The internal layout of a `.prt` is unverified.** The glossary implies it is
  CSV-structured. One online claim of a `[BEGIN_PARTIALPROJECTHEADER]` header comes from
  AI-generated content and must not be trusted.

### Bulk engineering (what to recommend)

- **Bulk Data Manager (BDM)** is an Excel-based offline tool that works on the `.pro`.
  - **Supported:** program lists and programs, tasks, FBDs, function-block parameters,
    **tags**, **variables**, and graphic, group and trend displays. It can also replicate
    "project tree typicals" and do bulk renames and deletes.
  - **Not supported:** system tasks, **all hardware objects**, OPC and gateway objects,
    and the POOL.
- The **variable CSV** from the variable list has the columns Name, Comment, Type, Res.,
  X, Object, Location and P. According to a forum report, the resource, object and
  location columns do not re-import.

### How to help safely

1. **Read** `.csv` exports freely. That covers analysing tag lists, cross-referencing
   MSR/EAM names, drafting BDM sheets, and generating an I/O list.
2. For **changes**, prefer BDM or the engineering tool. If the user insists on editing an
   export for re-import:
   - make a byte-for-byte backup first;
   - keep the encoding (UTF-16/Unicode), the delimiter (`;`) and the section order;
   - change only field values that you understand;
   - test the import on a **copy** of the project.
3. **Never** claim to know the `.prt` layout. Ask for a sample and work from it.
4. **Freelance 2024** added Ethernet-APL, PROFINET, MTP via Module Designer, NOA via
   OPC UA, and Windows 11. Whether its export or BDM behaviour changed is unverified.

## AC500: Automation Builder (CODESYS-based)

- Exchange uses `*.export` ("completely compatible" with the CODESYS project format, but
  **it imports only into the same Automation Builder version**) and PLCopenXML `*.xml`
  (subset).
- The language and dialect are CODESYS; see [codesys.md](codesys.md). Help:
  <https://help.plc.abb.com/>

## 800xA / AC 800M: Control Builder M

- The project file is `*.prj`. In 800xA, the Import/Export tool moves aspect objects as
  **`.afw`** files, whose internal structure is unverified.
- The programming model is a 61131-3 dialect with **Control Modules**, a
  graphical/object-oriented construct beyond the standard, plus FBs, POUs and libraries.
  Do not assume CODESYS syntax. Ask for an export sample.
