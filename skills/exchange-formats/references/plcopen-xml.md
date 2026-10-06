# PLCopen XML (TC6) and IEC 61131-10: element model

## Versions

| Version | Date | Namespace |
|---|---|---|
| TC6 v1.0 / v1.01 | 2005 | probably `http://www.plcopen.org/xml/tc6.xsd`, inferred from an unused prefix in the v2.01 XSD (**unverified**) |
| TC6 v2.0 | 2008-12-03 | `http://www.plcopen.org/xml/tc6_0200` |
| TC6 v2.01 | 2009-05-08 | `http://www.plcopen.org/xml/tc6_0201` (the XSD `targetNamespace`) |
| IEC 61131-10 Ed.1 | 2019-04-24 | `www.iec.ch/public/TC65SC65BWG7TF10`, root `<Project schemaVersion="1.0">` |

IEC's own preview says 61131-10 "extends PLCopen XML, adopts it to the features of IEC
61131-3:2013 and is therefore not compatible with previous versions of PLCopen XML". It
still targets 61131-3:2013, so it still includes IL.

## Tree (TC6 v2.01, from the XSD)

```
project
├─ fileHeader       companyName* productName* productVersion* creationDateTime*
│                   (companyURL, productRelease, contentDescription optional)
├─ contentHeader    name* (version, modificationDateTime, organization, author, language)
│  ├─ Comment?      (capital C)
│  ├─ coordinateInfo  pageSize?, fbd/scaling*, ld/scaling*, sfc/scaling*  ← all three required
│  └─ addDataInfo?, addData?
├─ types
│  ├─ dataTypes     (required, may be empty) dataType(name*)/baseType, initialValue?
│  └─ pous          (required, may be empty)
│     └─ pou name* pouType*=function|functionBlock|program  globalId?
│        ├─ interface?  returnType?, then localVars|tempVars|inputVars|outputVars|inOutVars|
│        │              externalVars|globalVars|accessVars → variable(name)/type/initialValue
│        ├─ actions?/action(name)/body   transitions?/transition(name)/body
│        ├─ body*       exactly one of IL | ST | FBD | LD | SFC, then addData?, documentation?
│        └─ addData?, documentation?
├─ instances/configurations   (required, may be empty)
│  └─ configuration(name*)/resource(name*)/task(name*, priority* 0..65535, interval?, single?)
│        /pouInstance(name*, typeName*)
└─ addData?, documentation?
```

- **Types** are written as elements: `<type><BOOL/></type>`, `<type><derived name="TON"/></type>`,
  `<type><array><dimension lower="1" upper="10"/><baseType><INT/></baseType></array></type>`.
- **Variable-list attributes:** `name`, `constant`, `retain`, `nonretain`, `persistent`,
  `nonpersistent` (all boolean).
- **`globalId` is `xsd:ID`**, so it must be an NCName: no leading digit, no spaces. This
  matters because AutomationML `refURI` fragments point at it.
- **Initial values:** `<initialValue><simpleValue value="0"/></initialValue>`.
- **Formatted text** (`IL`, `ST`, `documentation`) is `xsd:any` in the XHTML namespace,
  processed lax. Beremiz writes `<xhtml:p><![CDATA[…]]></xhtml:p>`. CODESYS writes
  `<xhtml xmlns="http://www.w3.org/1999/xhtml">…</xhtml>`.
- **The task `interval`** is an unconstrained string, "Vendor specific: Either a constant
  duration as defined in the IEC or variable name".

## Graphical model

**Coordinates:**

- The origin is the top-left corner; +x runs right and +y runs down.
- `<position x y>` is the anchor, which is the top-left of the object.
- `<relPosition>` on a connection point is relative to that anchor.
- **Scaling** is the minimum pin distance for FBD, the coil size for LD, and the
  transition size for SFC.
- Importers may ignore coordinates and auto-route.

| Element | Key attributes (* required) | Children |
|---|---|---|
| any graphical object | `localId*` (unsignedLong, not xsd:ID), `height`, `width`, `executionOrderId`, `globalId` | `position` |
| `connectionPointIn` | – | `relPosition?`, then `connection*` or `expression` |
| `connection` | `refLocalId*` (the producer), `formalParameter` (the producer's output pin) | `position*` (a path: the consumer pin first, the producer pin last) |
| `connectionPointOut` | `formalParameter` (required on `leftPowerRail`) | `relPosition?`, `expression?` |
| `block` | `typeName*`, `instanceName`, `localId*` | `inputVariables`/`inOutVariables`/`outputVariables` → `variable(formalParameter*, negated, edge, storage, hidden)` |
| `inVariable` / `outVariable` / `inOutVariable` | `negated`, `edge`, `storage` | `expression` (IEC expression text) |
| `label` / `jump` / `return` / `connector` / `continuation` | `label*` / `name*` | – |
| `contact` / `coil` | `negated`, `edge` = none/rising/falling, `storage` = none/set/reset | `variable` |
| `leftPowerRail` / `rightPowerRail` | – | `connectionPointOut formalParameter*` / `connectionPointIn*` |
| `step` | `name*`, `initialStep`, `negated` | `connectionPointOut`, `connectionPointOutAction` |
| `transition` | `priority` | `condition` → `reference(name)` or `inline` (body) or `connectionPointIn` |
| `selectionDivergence` / `selectionConvergence` / `simultaneousDivergence` / `simultaneousConvergence` | – | multiple `connectionPointOut formalParameter` / `connectionPointIn` |
| `jumpStep` | `targetName*` | – |
| `macroStep` | `name` | `body` |
| `actionBlock` → `action` | `qualifier` (default N; the schema allows `P1 N P0 R S L D P DS DL SD SL`), `duration`, `indicator` | `reference(name)` or `inline` (body) |
| `comment`, `error`, `vendorElement` | – | `content` (formattedText) |

**Documentation quirks:** the spec text §3.10 says "executionId", but the XSD attribute is
**`executionOrderId`**. The spec's own §9.4 SFC example has a duplicate `localId` and a
dangling reference.

## Extensions: addData

- `addDataInfo/info(name URI*, vendor URI*, version)` declares an extension.
  `addData/data(name*, handleUnknown*)` carries its content. `handleUnknown` is
  `preserve`, `discard` or `implementation`.
- CODESYS-family names start with `http://www.3s-software.com/plcopenxml/`. Seen:
  `projectinformation`, `application`, `pou`, `interfaceasplaintext`, `objectid`,
  `attributes`, `buildproperties`, `libraries`, `projectstructure`, `sfcsettings`,
  `tasksettings`.
- **Methods, properties and folders exist only in addData.** A non-CODESYS consumer
  drops them.

## IEC 61131-10 differences

| Aspect | TC6 v2.01 | IEC 61131-10 Ed.1 |
|---|---|---|
| Names | `project`, camelCase | `Project`, PascalCase (`FileHeader`, `ContentHeader`, `Types/GlobalNamespace/NamespaceDecl`) |
| POUs | `pou pouType=…` | separate `Program`, `FunctionBlock` (`Extends`, `Implements`, `Method`), `Function`, `Class`, `Method(accessSpecifier*, override)` |
| Body | `body/ST/xhtml:*` | `MainBody/BodyContent xsi:type="ST"/ST/<![CDATA[…]]>` |
| Wiring | `localId` + `connection refLocalId` + `formalParameter` | `ConnectionPointOut connectionPointOutId` + `Connection refConnectionPointOutId`; LD is grouped into `Rung evaluationOrder` with `LdObject xsi:type="Contact" operand="S1"` |
| Instances | `configuration/resource/task/pouInstance` | `Instances/Configuration/Resource(resourceTypeName)/Task xsi:type="StandardTask"` + `ProgramInstance associatedTaskName` |
| Extension | `addData/data` | `AddData` + abstract-type substitution |

**Tool support:** CODESYS has separate "Export IEC61131-10" and "Import IEC61131-10"
commands, which write `*.iec6113110.xml`. They are **not in any standard menu**; add them
through Tools → Customize. They do not handle CFC or the library manager.

## Sources

- PLCopen downloads (XSDs, the TC6 technical document v2.01, the IEC 61131-10 preview
  and Code Components): <https://www.plcopen.org/downloads/>
- A real v2.01 file that validates against the XSD: Beremiz
  `exemples/first_steps/plc.xml`.
- CODESYS PLCopenXML import help:
  <https://content.helpme-codesys.com/en/CODESYS%20Development%20System/_cds_cmd_import_plcopenxml.html>
- TwinCAT import rejecting `t#10ms`: Eclipse ESCET issue #75.
