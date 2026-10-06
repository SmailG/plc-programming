---
name: iec-61499
description: >-
  Design, write and review IEC 61499 event-driven distributed function-block applications:
  basic FBs with an Execution Control Chart (ECC states, EI[guard] transitions, EC actions),
  composite FBs, service interface FBs, adapters (plug/socket), subapplications, and the
  system/device/resource/mapping model. Covers the 61499-2 XML files (.fbt .adp .sub .sys
  .res .dev) as written by Eclipse 4diac (IDE + FORTE runtime) and the Schneider
  EcoStruxure Automation Expert context (CATs). Use when the user mentions IEC 61499,
  4diac, FORTE, ECC, event-driven function blocks or distributed control applications, or
  wants 61131-3 logic moved to 61499.
---

# IEC 61499

## Status (verified 2026-09)

- **IEC 61499-1 and -2 are Ed.2.0 (2012-11-07); -4 is Ed.2.0 (2013-01-30).** All three have
  stability date 2028. **No Ed.3 has been published**, so treat any claim of one as wrong.
- **Eclipse 4diac:** 3.0 was released 2025-12-10 and 3.3 on 2026-09-09. It now releases
  every three months, has a new ST editor and interpreter, and has all 61131-3 standard
  functions in FORTE.
- **Schneider EcoStruxure Automation Expert** is 61499-based and adds **CATs** (Composite
  Automation Types). A CAT bundles logic, HMI faceplate, I/O, simulation and
  documentation under a type/instance relation. Its current version was not verified; the
  newest source read was the v22.1 catalog from Jan 2023.

## Execution model: why it is not a PLC scan

- FBs have **event inputs and outputs** as well as data. Data is sampled **only for the
  variables tied to the arriving event by `WITH`**, and only when that event arrives.
- A resource delivers **one input event at a time** to an FB. An input event is valid
  **only on the first evaluation** of the transitions. After that, only eventless
  transitions (`1` or a pure guard) can fire, which prevents infinite loops.
- Transition syntax is `EI_name[guard]`, a bare `[guard]`, or `1`. Evaluation follows the
  transitions' priority order.
- **Runtimes differ.** FORTE, FBRT, ISaGRAF (cyclic underneath) and others can run the
  same application differently. The consensus reading is sequential run-to-completion.
  Before relying on timing, state which runtime the application targets.

## Design rules that prevent the usual bugs

1. **Every data input you read in an algorithm must be `WITH`-associated with the event
   that triggered it.** Otherwise you read a stale sample. This is the single most common
   61499 bug, and validator rule FB005 checks the WITH targets exist.
2. **Every output event must carry (`WITH`) the data it announces.**
3. **The ECC's first state is the initial state**, conventionally `START`. Every other
   state needs an incoming transition, which rule FB016 checks.
4. **Name algorithms after what they do, and keep them short.** Put state logic in the
   ECC, not in `IF` ladders inside one algorithm.
5. **Composite FBs are for reuse; subapplications are for distribution.** An FB cannot
   be split across devices, but a subapplication can.
6. **Use an adapter** when a pair of FBs exchanges several events and data in both
   directions. The provider side is the plug, and the side that accepts it is the socket.

## Minimal basic FB

This is trimmed from 4diac's `E_SR.fbt`. Modern 4diac writes no DOCTYPE and puts ST in CDATA.

```xml
<FBType Name="E_SR" Comment="Event-driven bistable">
  <Identification Standard="61499-1 Annex A"/>
  <VersionInfo Version="3.0" Author="…" Date="2025-04-14"/>
  <InterfaceList>
    <EventInputs><Event Name="S" Type="Event"/><Event Name="R" Type="Event"/></EventInputs>
    <EventOutputs><Event Name="EO" Type="Event"><With Var="Q"/></Event></EventOutputs>
    <OutputVars><VarDeclaration Name="Q" Type="BOOL"/></OutputVars>
  </InterfaceList>
  <BasicFB>
    <ECC>
      <ECState Name="START"/>
      <ECState Name="SET"><ECAction Algorithm="SET" Output="EO"/></ECState>
      <ECState Name="RESET"><ECAction Algorithm="RESET" Output="EO"/></ECState>
      <ECTransition Source="START" Destination="SET" Condition="S"/>
      <ECTransition Source="SET" Destination="RESET" Condition="R"/>
      <ECTransition Source="RESET" Destination="SET" Condition="S"/>
    </ECC>
    <Algorithm Name="SET"><ST><![CDATA[Q := TRUE;]]></ST></Algorithm>
    <Algorithm Name="RESET"><ST><![CDATA[Q := FALSE;]]></ST></Algorithm>
  </BasicFB>
</FBType>
```

- **Older FBDK/Holobloc files** carry `<!DOCTYPE FBType SYSTEM "http://www.holobloc.com/xml/LibraryElement.dtd">`
  and write `<ST Text="Q:=TRUE;"/>`. Both forms are valid under the DTD.
- **A composite FB** has an `<FBNetwork>` with `<FB Name Type>`, `<EventConnections>`,
  `<DataConnections>` and `<AdapterConnections>`. Each `<Connection Source Destination>`
  names either an interface pin (`START`) or `Instance.Pin`.
- **A system file (`.sys`)** holds `Application`, `Device` → `Resource`, and
  `<Mapping From="App.FB" To="Device.Resource"/>`.
- **4diac file extensions:** `.fbt` FB, `.adp` adapter, `.sub` subapp type, `.sys` system,
  `.dev` device, `.res` resource, `.seg` segment, `.dtp` data type, `.atp` attribute type,
  `.fct` function and `.gcf` global constants. The last two are 4diac extensions.

Validate with `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/plc_validate.py file.fbt`, which runs
rules FB0xx and lints the ST in each algorithm.

## Porting 61131-3 logic to 61499

- **ST algorithms and the elementary types carry over.** `VAR_TEMP` exists since Ed.2.
- **Scan-based idioms do not.** An `R_TRIG` becomes an event, and a `TON` becomes an
  `E_DELAY`/`E_CYCLE` service FB driven by events.
- **Each PROGRAM becomes a network.** Split it into control-module FBs that fire on
  events, and map them to resources.
- **Interlocks that must be evaluated continuously** need a cyclic event source, such as
  `E_CYCLE`, or a resource that runs cyclically. Say which one you chose.

## Sources

- IEC webstore: publications 5506, 5507 and 5508.
- Christensen et al., "The IEC 61499 Function Block Standard: Overview of the Second
  Edition" (2012): <https://www.holobloc.com/papers/iec61499/61499_ED2_OVW.pdf>
- Eclipse 4diac documentation and type library: <https://eclipse.dev/4diac/>
