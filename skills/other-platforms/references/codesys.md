# CODESYS V3.5

It is the base of Schneider Machine Expert, ABB Automation Builder (AC500), Beckhoff
TwinCAT (historically), WAGO e!COCKPIT, Festo and many others. **Always ask which OEM
flavour and which CODESYS SP is underneath.** Libraries, devices and some menus differ.

## Versions

- **SP21** was announced 2025-03-18.
- **SP22** is current (Patch 2). Its release date of 2026-03-24 comes from search
  metadata only.
- **SP23** is on the roadmap for Q1 2027.
- **CODESYS go!**, a web IDE that reuses the V3 compilers with textual storage, had a
  public beta planned for the end of 2025.
- **The Python 2 / IronPython scriptengine will not be upgraded.** A new scripting
  solution is planned as part of CODESYS go!.

## Storage and exchange

| Format | What it is |
|---|---|
| `.project` / `.library` | a single compressed file; binary as far as Git is concerned |
| `.compiled-library-v3` | an encrypted library with no source |
| `*.export` | native XML, "fully compatible" with the project format |
| `*.xml` PLCopenXML | namespace `tc6_0200`; methods, properties and folders live in `addData` (see the `exchange-formats` skill); "100% compatibility cannot be guaranteed" |
| `*.iec6113110.xml` | IEC 61131-10 export and import. The commands must be added through Tools → Customize |
| **File-Based Storage** (`*.fbsproj`) | one folder per object with `.st` files (`PLC_PRG.prg.st`, `X.fb.st`, `.meth`, `.prop.st`, `.gvl`, `.struct`, `.enum`); non-ST objects stay XML. It was a 0.9 preview (≥ SP20 Patch 4, Professional Developer Edition), with 1.0 planned on SP22. **Check which version the user has.** |

## Language extensions beyond the standard

- **POUs:** `PROPERTY` (Get/Set), `METHOD` (as separate objects), `INTERFACE`, `EXTENDS`,
  `IMPLEMENTS`, `SUPER^`, `THIS^`.
- **Pointers and references:** `POINTER TO`, `REFERENCE TO`, `__ISVALIDREF`, `ADR`, `SIZEOF`.
- **Variables:** `VAR_STAT`, `VAR_INST`, `PERSISTENT`.
- **Statements:** `AND_THEN`, `OR_ELSE`, `S=`/`R=` assignments, `__TRY`/`__CATCH` (on some
  targets), `__NEW`/`__DELETE`.
- **Pragmas:** `{attribute '…'}`, `{region}`, `{warning}`, `{IF defined(…)}`.
- **Graphical:** CFC and page-oriented CFC, and UML class and statechart diagrams (add-on)
  that compile to code.

## Static Analysis

- **Rules are numbered `SA<nnnn>`:**
  - SA0001: unreachable code.
  - SA0027: multiple uses of identifiers.
  - SA0033: unused variables. This one is also in the free *Static Analysis Light*.
  - SA0035 and SA0036: unused inputs and outputs.
- **Suppression:**
  - Per region: `{analysis -33}` … `{analysis +33}`.
  - Per object: `{attribute 'analysis' := '-33'}`.
- **Naming conventions** are set per scope and type, and violations report as `NC<n>`.
  `{attribute 'naming'}` controls exceptions.
- TwinCAT ships the same engine.
- SP22 reportedly added SARIF export (**unverified**).

## Scripting (headless export)

Scripts use `from scriptengine import projects`, `projects.primary`, `obj.get_children()`,
`obj.textual_declaration.text`, `obj.export_xml(...)` and `obj.export_native(...)`, and run
with `--runscript`. The exact parameter lists are unverified, so read the ScriptProject
documentation of the installed version.

## Git

CODESYS Git is part of the Professional Developer Edition and needs no local Git install.
Git with File-Based Storage as the backend was planned for Q2 2026.

## Sources

- CODESYS online help: <https://content.helpme-codesys.com/>
- The CODESYS release notes and the 2025 Q3 roadmap (PDF on codesys.com).
- The File-Based Storage whitepaper (store.codesys.com).
