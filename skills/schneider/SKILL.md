---
name: schneider
description: >-
  Schneider Electric PLC programming: EcoStruxure Machine Expert (CODESYS-based; Modicon
  M241/M251/M262 logic and motion; V2.5/V2.6 platform changes), EcoStruxure Control
  Expert 16.x (ex-Unity Pro; M340/M580 incl. HSBY and Safety; MAST/FAST/AUX, DFB/DDT,
  %MW/%S/%SW), Machine Expert – Basic (M221) and Automation Expert (IEC 61499). Covers
  tasks and watchdogs, retain/persistent behaviour on download, online change, OPC UA
  server/client and Symbol Configuration, Modbus TCP/RTU (READ_VAR/WRITE_VAR, ADDM, unit
  IDs, 4x↔%MW), EtherNet/IP, MQTT, TCP/UDP, PLC_R diagnostics, cybersecurity defaults and
  exchange files (XEF/XSY/PLCopenXML). Use whenever the target is a Schneider/Modicon
  controller or Machine Expert/Control Expert/SoMachine/Unity Pro is mentioned.
---

# Schneider Electric: Machine Expert, Control Expert, Automation Expert

## Which tool and dialect (as of 2026-09)

| Controller | Tool | Dialect | Exchange |
|---|---|---|---|
| **M241 / M251 / M262** | **EcoStruxure Machine Expert**. V2.3 uses CODESYS 3.5.20 and V2.5 uses 3.5.21; release notes exist for **V2.6** (2026-04-30), but its CODESYS base is unverified | CODESYS IL/ST/FBD/SFC/LD/CFC with OOP, plus Schneider libraries | PLCopenXML (`tc6_0200`); file-based storage from V2.5 |
| **M340 / M580** (plus Quantum, Premium, Momentum) | **EcoStruxure Control Expert 16.4** (manuals dated 07/2026) | IEC LD/FBD/ST/SFC/IL, plus LL984; DFB/DDT; located `%M`/`%MW` | XEF/ZEF/XSY and section files |
| M221 | Machine Expert – Basic 1.4 | Ladder / IL / Grafcet | `.smbp` |
| distributed | EcoStruxure Automation Expert (IEC 61499, CATs) | 61499 + ST | see the `iec-61499` skill |

**Ask which tool and version the user runs.** "Schneider PLC" alone is ambiguous: the two
main worlds have different languages, memory models and file formats. For Machine Expert,
also ask about the licence, because the Free licence has **no online change, simulation or
breakpoints**.

## M262 / Machine Expert: the traps that cost the most

1. **Only PERSISTENT survives a download from ME.** VAR and RETAIN are re-initialised.
   PERSISTENT values are also lost on an SD-card download or reset origin, and **when a
   persistent variable is renamed or retyped.**
2. **The M262 does not retain `%MW` implicitly**, unlike older M2xx controllers. Use
   `VAR_GLOBAL RETAIN … AT %MWn`.
3. **The OPC UA server restarts on every download, online change and reset**, so clients
   must reconnect and resubscribe.
4. **Symbol Configuration changes reach the controller only with the next download.**
   `%MX`/`%IX`/`%QX` bits cannot be exposed. A GVL appears only if one of its variables
   is used in code. The default access is read-only, the limit is 10 000 variables, and
   there are at most 2 sessions by default.
5. **Anonymous OPC UA login is refused by default.** User rights are on, the policy is
   Basic256Sha256 with SignAndEncrypt, and the PKI in `/usr/pki` is **shared by the
   server and the client.**
6. **There are no default credentials.** The first ME connection must create an
   administrator. **Modbus TCP 502 is disabled by default.**
7. **A task watchdog means HALT** (`PLC_R.i_wLastApplicationError = 16#0010`).
   **Watchdogs are off in simulation.** A system watchdog reboots to EMPTY.
8. **Task priorities must be unique** (0–31). Outputs in one byte written from two tasks
   fail the build. Referencing a PROPERTY in an event task causes a watchdog exception.
9. **Online change:** pointers keep their old values, so reassign them every cycle.
   After Build › Clean no online change is possible. Only one ME instance can log in.
10. **ME V2.5 dropped ME-Safety, SVN and Vijeo-Designer.** An M262 with embedded safety
    cannot move to V2.5.
11. **Schneider communication FBs** (Modbus, TCP/UDP, MQTT, OPC UA client) must keep
    being called while active. Errors clear only by disabling the FB. The TCP/UDP
    methods block until `ResetResult` is called.

## Control Expert (M340/M580): the traps that cost the most

1. **A watchdog overflow means HALT**, which STOP cannot clear; the application must be
   re-initialised. **A period overrun only sets `%S19`.**
2. **`%S15`, `%S18` and `%S20`** (string error, arithmetic error or ÷ 0, index overflow)
   are per task, and **the application must reset them.** `%S78` turns them into a HALT.
3. **Unlocated variables are re-initialised on download.** Give a variable a located
   address to keep it across an application transfer.
4. **The M340 has no AUX tasks and no `%MD`/`%MF`/`%KD`/`%KF`.** M580 HSBY runs MAST +
   FAST only.
5. **Use `%S21` (first cycle of the task) or `%SW10.0`, not `%S0`, to detect the first
   scan.**
6. **`READ_VAR`/`WRITE_VAR`:** respect the activity bit, set the timeout in 100 ms units,
   and make the EF timeout longer than the configured timeout × retries.
7. **One writer task per variable, and one task per I/O.** Use handshake flags between
   tasks.

## References

- [references/machine-expert-platform.md](references/machine-expert-platform.md):
  versions and the V2.5 changes, licences, M262 hardware, tasks and watchdogs, the
  remanence table, the `%MW` map and Relocation Table, online change, debugging, static
  analysis, cybersecurity.
- [references/machine-expert-communication.md](references/machine-expert-communication.md):
  the OPC UA server (parameters, Symbol Configuration, certificates, diagnostic IDs) and
  client, the Modbus server/Slave Device/client (`READ_VAR`, `ADDM`, `CommError`),
  EtherNet/IP, TCP/UDP, MQTT, CANopen.
- [references/machine-expert-diagnostics.md](references/machine-expert-diagnostics.md):
  `PLC_R`/`PLC_W`, error classes and logs, a table of typical M262 faults, safety
  (TM5CSLC / M580 Safety), motion (`PLCO` / GMC).
- [references/control-expert.md](references/control-expert.md): Control Expert tasks,
  data, DFB/DDT/IODDT, the `%S`/`%SW` tables, debugging, the `READ_VAR` management table,
  `ADDM`, HSBY.
- [references/modbus.md](references/modbus.md): the protocol-level data model,
  addressing (40001 = PDU 0), function codes and limits, exceptions, Unit ID, serial
  timing, word order.
- [references/exchange-files.md](references/exchange-files.md): Machine Expert
  PLCopenXML limits, Control Expert XEF/ZEF/XSY with a skeleton, Machine Expert – Basic.

Language syntax, pragmas and Static Analysis for Machine Expert are the CODESYS ones:
[../other-platforms/references/codesys.md](../other-platforms/references/codesys.md).
Validate XEF/XSY and PLCopenXML with
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/plc_validate.py` (rules CX0xx and PX0xx).
