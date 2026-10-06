# AutomationML (IEC 62714) and CAEX (IEC 62424)

## Parts and editions

| Part | Title | Current edition |
|---|---|---|
| IEC 62714-1 | Architecture and general requirements | Ed.2.0, 2018-04-30. Adopts CAEX 3.0, the container format and multilingual expressions |
| IEC 62714-2 | Semantics libraries (previously "role class libraries") | Ed.2.0, 2022-10-20 |
| IEC 62714-3 | Geometry and kinematics (COLLADA) | Ed.1.0, 2017-01-25 |
| IEC 62714-4 | **Logic** | Ed.1.0, 2020-06-16 (a COR1:2020 exists). Stores logic "by using IEC 61131-10" |
| IEC 62714-5 | Communication | Ed.1.0, 2022-03-11 |

**CAEX versions:**

- **CAEX 3.0** is IEC 62424 Ed.2 (2016), with namespace `http://www.dke.de/CAEX` and
  `SchemaVersion="3.0"`. **`SourceDocumentInformation` is required.** `RefPartnerSideA/B`
  on `InternalLink` are mandatory, and `InterfaceIdMapping` replaces
  `InterfaceNameMapping`.
- **CAEX 2.15** has no namespace. It marks AML Ed.1 files with
  `<AdditionalInformation AutomationMLVersion="2.0"/>`.
- Several official libraries (the Part 4 logic library, AR APC 1.4.0) are still published
  in CAEX 2.15.

## Structure

- **InstanceHierarchy** is the project: a tree of `InternalElement`s, each carrying
  `RoleRequirements`, `SupportedRoleClass` and `ExternalInterface`s, and connected by
  `InternalLink`s.
- **SystemUnitClassLib** holds reusable classes.
- **RoleClassLib** holds semantics.
- **InterfaceClassLib** holds interface types.
- **AttributeTypeLib** (CAEX 3.0) holds attribute types.

## Linking PLC logic

- `ExternalDataConnector` → **`PLCopenXMLInterface`**, with an attribute
  `refURI = file:///plc.xml#<globalId>`. The fragment is the `globalId` of a POU or
  variable in the PLCopen file. The base library path is
  `AutomationMLInterfaceClassLib/AutomationMLBaseInterface/ExternalDataConnector/PLCopenXMLInterface`.
  The Ed.2.1 whitepaper table gives a shorter path, so both spellings appear in the wild.
- **Part 4 (2020)** stores logic in an "AML logic XML" document:
  - The root is `aml:AMLLogic`, with namespace `http://www.automationml.org/IEC62714-4Ed1`.
    It imports the IEC 61131-10 schema.
  - The link types are `LogicModelInterface`, with its subtypes Sequencing, Behaviour and
    Interlocking.
  - Variable links are `LogicModelElementInterface`, with `VariableInterface` and
    `InterlockingVariableInterface`.
  - Part 4 accepts PLCopen XML 2.0, 2.01 and IEC 61131-10 as targets.
- **The `.amlx` container** is an OPC (ECMA-376) package, with a relationship type for
  PLCopenXML documents.

Validator rules:

- **AM010–AM012:** every data-connector interface has a `refURI`, its file exists next to
  the `.aml`, and a PLCopen fragment matches a `globalId`.
- **AM005:** `InternalLink` sides resolve.

## Application recommendations and tools

- **AR APC** (Automation Project Configuration) V1.4.0, 2023, covers ECAD ↔ PLC tool
  exchange of **hardware configuration**: devices, subnets, I/O systems, tag tables.
  **It does not cover control code.**
- **TIA Portal CAx import/export** uses `.aml` for hardware and networks. An AML file from
  a newer TIA does not import into an older one. That TIA's `.aml` conforms to AR APC is
  unverified.
- **OPC UA for AutomationML** is OPC 30040 (2016).
- **Aml.Engine** (C#, MIT licence, NuGet, CAEX 2.15 and 3.0) and the **AutomationML
  Editor** are the reference tools.

## Sources

- IEC webstore publications 32339, 63231, 34158, 28979 and 65493; IEC 62424 is 25442.
- The AutomationML whitepapers and libraries:
  <https://www.automationml.org/> (Edition 2.1 whitepaper; Part 4 Logic V1.6.0).
