---
name: packml-isa88-opcua
description: >-
  Structure machine and process control code with PackML (ANSI/ISA-TR88.00.02-2022: 17
  states, CntrlCmd commands, unit modes, PackTags Command/Status/Admin), ISA-88 / IEC
  61512 batch models (physical model, procedure/unit procedure/operation/phase, recipes,
  phase states; IEC 61512-1:2026), and expose or consume PLC data over OPC UA (OPC 30000
  PLCopen information model, OPC 30001 client FBs UA_Connect/UA_ReadList, OPC 30050
  PackML companion, and vendor symbol exposure in CODESYS/Machine Expert, TwinCAT TF6100,
  TIA S7-1500 and Logix). Use for state machines of machines/units, batch phases, control
  module architecture, and PLC-to-SCADA/MES/cloud data exchange via OPC UA.
---

# PackML, ISA-88 and OPC UA for PLC programmers

## PackML state model (ISA-TR88.00.02-2022 is current)

| # | State | Kind | # | State | Kind |
|---|---|---|---|---|---|
| 0 | Undefined | – | 9 | Aborted | wait |
| 1 | Clearing | acting | 10 | Holding | acting |
| 2 | Stopped | wait | 11 | Held | wait |
| 3 | Starting | acting | 12 | Unholding | acting |
| 4 | Idle | wait | 13 | Suspending | acting |
| 5 | Suspended | wait | 14 | Unsuspending | acting |
| 6 | Execute | acting ("dual") | 15 | Resetting | acting |
| 7 | Stopping | acting | 16 | Completing | acting |
| 8 | Aborting | acting | 17 | Complete (one source says renamed "Completed" in 2022) | wait |

**How states are left:**

- An **acting** state leaves on its own when its work is done: State Complete (SC).
- A **wait** state leaves only on a command.
- OPC 30050 adds the superstates 18 = Running and 19 = Cleared.

**`Command.CntrlCmd`** values: 1 Reset, 2 Start, 3 Stop, 4 Hold, 5 Unhold, 6 Suspend,
7 Unsuspend, 8 Abort, 9 Clear.

| Command | Accepted in | Goes to |
|---|---|---|
| Reset | Stopped, Complete | Resetting → Idle |
| Start | Idle | Starting → Execute |
| Hold / Unhold | Execute / Held | Holding → Held / Unholding → Execute |
| Suspend / Unsuspend | Execute / Suspended | Suspending → Suspended / Unsuspending → Execute |
| Stop | any except Stopping, Stopped, Aborting, Aborted, Clearing | Stopping → Stopped |
| Abort | any except Aborting, Aborted | Aborting → Aborted |
| Clear | Aborted | Clearing → Stopped |

- Execute leaves on SC through Completing → Complete. A "Complete" command, and Hold
  from Suspended, exist only as vendor or OPC UA extensions.
- **Unit modes:** 1 Production (formerly "Producing"), 2 Maintenance, 3 Manual, and 4–31
  user-defined. Each mode can disable states. Stopped, Execute and Aborted are mandatory
  in every mode (sources conflict on Aborted).
- **PackTags:**
  - `Command`: `UnitMode`, `UnitModeChangeRequest`, `MachSpeed`, `CntrlCmd`,
    `CmdChangeRequest`, `Parameter[]`, `Product[]`, …
  - `Status`: `StateCurrent`, `UnitModeCurrent`, `CurMachSpeed`, `EquipmentInterlock`, …
  - `Admin`: `StopReason`, `Alarm[]`, `Warning[]`, `ProdProcessedCount[]`,
    `ProdDefectiveCount[]`, …
- **No PLCopen FB library exists.** PLCopen has only a short paper that maps PackML to
  SFC. Use the vendor libraries instead:
  - **Schneider:** the Machine Expert PackML library (`FB_UnitModeManager2`).
  - **Beckhoff:** `Tc3_PackML`.
  - **Rockwell:** PhaseManager is ISA-88-style.

### Implementation pattern (ST)

```iecst
// One unit: the state machine owns transitions only; outputs derive from the state.
CASE eState OF
    E_PackML#Stopped:
        IF xCmdReset THEN eState := E_PackML#Resetting; END_IF;
    E_PackML#Resetting:
        IF xResetDone THEN eState := E_PackML#Idle; END_IF;                 // SC
    E_PackML#Idle:
        IF xCmdStart THEN eState := E_PackML#Starting; END_IF;
    E_PackML#Starting:
        IF xStartDone THEN eState := E_PackML#Execute; END_IF;              // SC
    E_PackML#Execute:
        IF xCmdHold THEN eState := E_PackML#Holding;
        ELSIF xCmdSuspend THEN eState := E_PackML#Suspending;
        ELSIF xBatchDone THEN eState := E_PackML#Completing; END_IF;
    // … Holding/Held/Unholding, Suspending/Suspended/Unsuspending, Completing/Complete …
    E_PackML#Clearing:
        IF xClearDone THEN eState := E_PackML#Stopped; END_IF;              // SC
END_CASE;
// Stop and Abort are global: evaluate them after the CASE so that they win.
IF xCmdAbort AND eState <> E_PackML#Aborting AND eState <> E_PackML#Aborted THEN
    eState := E_PackML#Aborting;
ELSIF xCmdStop AND eState <> E_PackML#Stopping AND eState <> E_PackML#Stopped
      AND eState <> E_PackML#Aborting AND eState <> E_PackML#Aborted
      AND eState <> E_PackML#Clearing THEN
    eState := E_PackML#Stopping;
END_IF;
```

Record the **first** stop or abort cause in `Admin.StopReason`. Mode-dependent disabled
states and the remaining branches are omitted here.

## ISA-88 / IEC 61512

- **IEC 61512-1:2026 (Ed.2.0, 2026-02-20)** replaced the 1997 edition. It adds UML state
  diagrams, an expanded procedural state model (Annex B) and conformance clauses. The ISA
  documents are 88.00.01-2010, .02-2001, .03-2003 and .04-2006.
- **Physical model:** Enterprise → Site → Area → Process cell → **Unit** → Equipment
  module → Control module. Levels may be omitted, except the Unit.
- **Procedural model:** Procedure → Unit procedure → Operation → **Phase**.
- **Recipes:** general → site → master → control.
- **Phase states (classic example model):** Idle, Running, Complete, Pausing, Paused,
  Holding, Held, Restarting, Stopping, Stopped, Aborting, Aborted. The commands are
  start, stop, hold, restart, abort, reset, pause and resume. **There is no Resetting
  state and no "complete" command**; phases self-complete. The exact 2010 and 2026 lists
  are paywalled, so verify them before claiming compliance.
- **How it maps to code:**
  - **Control module:** one FB or AOI instance per device (valve, motor, transmitter),
    with modes (Auto/Manual/Out-of-service), interlocks and alarms.
  - **Equipment module:** coordinates several control modules for a minor processing
    activity.
  - **Phase:** a state machine with one routine or action per acting state.
  - ISA-88 does not link procedural elements to control modules directly.

## OPC UA

- **OPC 30000 v1.02 (2020-11-25), the PLCopen information model:**
  - Namespace: `http://PLCopen.org/OpcUa/IEC61131-3/`.
  - Types:
    - `CtrlConfigurationType` (derives from TopologyElementType)
    - `CtrlResourceType` (derives from DeviceType)
    - `CtrlProgramType` and `CtrlFunctionBlockType` (both under
      `CtrlProgramOrganizationUnitType`)
    - `CtrlTaskType` (`Priority`, `Interval`, `Single`)
    - `SFCType`
  - Variables hang off `HasInputVar`, `HasOutputVar`, `HasLocalVar` and related references.
- **OPC 30001 v1.02 (2023-11-07), the client FBs:**
  - Current blocks: `UA_Connect`, `UA_NamespaceGetIndexList`, `UA_NodeGetHandleList`,
    `UA_ReadList`/`UA_WriteList`, `UA_MethodCall`, subscriptions and monitored items,
    `UA_NodeReleaseHandleList` and `UA_Disconnect`.
  - Every block follows the Execute/Done/Busy/Error/ErrorID pattern, with a `Timeout`.
  - **The single-item `UA_Read`, `UA_Write` and `UA_NodeGetHandle` are phased out.**
  - Recommended: WSTRING.
  - Sequence: connect → get namespace index → get handles → read/write loop → release
    handles → disconnect. Release the handles on error paths too.
- **OPC 30050 v1.01 (2020-11-11)** is the PackML companion specification.
- **OPC UA FX:** the C2C maintenance release V1.00.04 came out 2026-07-27. Controller to
  device was still at release-candidate stage in June 2026, so do not promise it.

### Exposing PLC variables

| Platform | Mechanism |
|---|---|
| CODESYS / Machine Expert (M262) | **Symbol Configuration** ("Support OPC UA features"), or, from SP18, the Communication Manager with IEC Symbol Sets. Per-variable `{attribute 'symbol' := 'read'}`. **On the M262, symbol changes reach the controller only with the next download**, and the OPC UA server restarts on every download, online change and reset. `%MX`/`%IX` bits cannot be exposed, and anonymous login is off by default. Details are in the `schneider` skill |
| TwinCAT (TF6100) | `{attribute 'OPC.UA.DA' := '1'}` above the declaration. `OPC.UA.DA.Access` 1 = read, 2 = write, 3 = read/write |
| S7-1500 (TIA) | DB/tag attributes "Accessible/Writable from HMI/OPC UA"; the standard SIMATIC server interface, or user-defined, reference-namespace or companion-spec interfaces (NodeSet import, then map tags). **Requires a runtime licence.** Details are in the `siemens` skill |
| Logix | `OpcUaAccess` tag attribute (Read Only / Read/Write / None) on controllers that support it |

**Design rules:**

- Expose **a curated interface struct** per unit, not every internal variable.
- Make it **read-only by default**. Every write path is a command that the PLC validates
  (range, state and permission) before acting.
- **Never let OPC UA write directly to an output or setpoint that bypasses interlocks.**

## Sources

- ISA-88 standards list: <https://www.isa.org/standards-and-publications/isa-standards/isa-88-standards>
- IEC 61512-1:2026: <https://webstore.iec.ch/en/publication/75287>
- OPC references: <https://reference.opcfoundation.org/PLCopen/v102/docs/>,
  <https://reference.opcfoundation.org/PLCopen-CFB/v102/docs/>,
  <https://reference.opcfoundation.org/PackML/v101/docs/>
- Schneider EcoStruxure Machine Expert PackML Library Guide, EIO0000002809.03 (12/2025).
- Beckhoff TF6100 pragma documentation:
  <https://infosys.beckhoff.com/content/1033/tf6100_tc3_opcua_server/15563857163.html>
