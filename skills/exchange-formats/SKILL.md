---
name: exchange-formats
description: >-
  Read, write, convert and validate vendor-neutral PLC and engineering exchange files.
  Covers PLCopen XML (TC6 v2.0 tc6_0200 and v2.01 tc6_0201: project/fileHeader/
  contentHeader/types/pous/instances, interface variables, ST/IL bodies in XHTML, LD/FBD/SFC
  graphs with localId/connection/refLocalId, and vendor addData), IEC 61131-10:2019 (which
  is a different schema, not v2.01 renamed), AutomationML IEC 62714 and CAEX IEC 62424
  (InstanceHierarchy, PLCopenXMLInterface refURI links, logic via Part 4), and DEXPI P&ID
  data (Proteus 1.x PlantModel, DEXPI 2.0, ISO 15926) for deriving I/O lists and control
  modules. Use when a file is .xml/.aml/.amlx from PLCopen, CODESYS, TwinCAT, Machine
  Expert, AutomationML or DEXPI, or when moving logic between PLC tools.
---

# Exchange formats: PLCopen XML, IEC 61131-10, AutomationML, DEXPI

## First, identify the format by root element and namespace

| Root + namespace | Format | Checked by |
|---|---|---|
| `<project xmlns="http://www.plcopen.org/xml/tc6_0201">` | PLCopen XML v2.01 (2009) | `plc_validate.py`, rules PX0xx |
| `<project xmlns="http://www.plcopen.org/xml/tc6_0200">` | PLCopen XML v2.0 (2008), which CODESYS, TwinCAT and Machine Expert still write | PX0xx |
| `<Project xmlns="www.iec.ch/public/TC65SC65BWG7TF10">` | **IEC 61131-10:2019**, with PascalCase elements. **Not compatible** with v2.01 | PX1xx (light) |
| `<CAEXFile xmlns="http://www.dke.de/CAEX" SchemaVersion="3.0">` | AutomationML Ed.2 / CAEX 3.0 | AM0xx |
| `<CAEXFile SchemaVersion="2.15">`, no namespace | AutomationML Ed.1 / CAEX 2.15 | AM0xx |
| `<PlantModel>` + `<PlantInformation SchemaVersion="4.1">` | DEXPI 1.3 (Proteus 4.1); 1.4 uses Proteus 4.2.0 | DX0xx |
| `<Model>` | DEXPI 2.0 "DEXPI XML" (2025-10-10), a generic object model | DX0xx with `--format dexpi` |

## Non-negotiables when you generate PLCopen XML

1. **Required skeleton:**
   - `fileHeader` with `companyName`, `productName`, `productVersion` and `creationDateTime`.
   - `contentHeader` with `name` and **all three** `coordinateInfo/{fbd,ld,sfc}/scaling`.
   - `types/dataTypes` and `types/pous`, which may be empty.
   - `instances/configurations`, which may be empty.
   
   Start from [assets/plcopen-st-pou.xml](assets/plcopen-st-pou.xml).
2. **ST and IL go in the XHTML namespace:** either `<ST><xhtml:p><![CDATA[…]]></xhtml:p></ST>`
   as Beremiz writes it, or `<ST><xhtml xmlns="http://www.w3.org/1999/xhtml">…</xhtml></ST>`
   as CODESYS writes it. Read both. Write CDATA.
3. **Graphical bodies:**
   - `localId` is unique **per body**.
   - Every `connection/@refLocalId` points to an existing `localId` in the same body.
   - `formalParameter` names the producer's output pin. When it is omitted on a block,
     the first output that is not ENO is used.
   
   See [assets/plcopen-ld-rung.xml](assets/plcopen-ld-rung.xml).
4. **Match the namespace to the importer.** CODESYS-family tools export `tc6_0200`. The
   v2.0 → v2.01 changes are minor, but a strict importer can reject the other namespace.
5. **Never trust XSD validation alone.** A duplicate `localId`, a dangling `refLocalId`,
   an unknown `derived` type and broken ST all pass the XSD. Always run
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/plc_validate.py file.xml`.
6. **Task intervals come in two incompatible spellings.** Beremiz writes `T#100ms`,
   while TwinCAT and CODESYS write ISO `PT0.1S`, and **TwinCAT rejects `t#10ms`**. Ask
   which tool will import the file.

## CODESYS / TwinCAT / Machine Expert exports hide the project in addData

A CODESYS-family export can have an **empty** standard `<pous/>`, with every POU inside
`<addData><data name="http://www.3s-software.com/plcopenxml/pou">`. The standard task
interval can read `PT0S` while the real cycle sits in `…/plcopenxml/tasksettings`.
Validator rules PX050 and PX051 flag both cases.

- When **reading** such a file, look inside those vendor blocks. Methods, properties,
  folders and object IDs live there too.
- When **writing** for a non-CODESYS consumer, put the POUs in the standard elements.
- **Known loss:** a GVL cannot hold both `VAR_GLOBAL` and `VAR_GLOBAL CONSTANT` through
  PLCopenXML, so the constants come back as plain globals.
- **TwinCAT to TwinCAT:** use the ZIP export, not PLCopenXML.

Both templates in `assets/` validate against the official `tc6_xml_v201.xsd`, and they are
re-checked by the plugin's test suite.

## Schemas and licences

Neither XSD may be bundled with this plugin:

- The TC6 v2.01 document says "All rights reserved".
- The IEC 61131-10 schema is an IEC Code Component under the CCv1 licence.

Download them from <https://www.plcopen.org/downloads/> ("XML Exchange": the TC6 v2.01 zip,
and "Code Components of IEC 61131-10"). Then run
`plc_validate.py file.xml --xsd tc6_xml_v201.xsd`, which uses xmllint or lxml.

## References

- [references/plcopen-xml.md](references/plcopen-xml.md): the full element model
  (interface sections, the graphical element table, SFC elements and qualifiers,
  instances, addData) and the IEC 61131-10 differences.
- [references/automationml.md](references/automationml.md): IEC 62714 parts and
  editions, CAEX 2.15 vs 3.0, how logic is linked, AR APC, tools.
- [references/dexpi.md](references/dexpi.md): DEXPI versions, the Proteus structure,
  the instrumentation classes, ISO 15926 parts, and a method to derive an I/O list.

## Converting logic between tools

Load the `convert` skill. In short:

- Graphical logic is portable only as PLCopen LD/FBD (with the CODESYS subset caveat),
  SIMATIC SD rungs or Rockwell neutral text.
- **Never hand-write** TwinCAT `XmlArchive` graphs or Control Expert `.XBD`/`.XLD` files.
- **Siemens TIA has no PLCopen XML import for logic**: it uses SimaticML or SIMATIC SD
  (see the `siemens` skill). This rests on a secondary source, so confirm it against
  the user's TIA version.
