# M262 / Machine Expert diagnostics, typical faults, safety and motion

## System variables

`PLC_R` comes from `SE_PLCSystem` (namespace `SEC`). `PLC_W` and the enums come from
`PLCSystemBase`. They are global, and `PLC_R` is also readable over Modbus from `%MW60000`.

| Field | Values |
|---|---|
| `PLC_R.i_wStatus` | EMPTY 0, STOPPED 1, RUNNING 2, HALT 4, BREAKPOINT 8 |
| `PLC_R.i_wLastStopCause` | 01 hardware watchdog, 02 reset, **03 exception**, 04 user, 05 IEC program, 06 delete |
| `PLC_R.i_wLastApplicationError` | **16#0010 task watchdog**, 0011 hardware watchdog, 0012 I/O config, 0018 unresolved external refs, 0025 task config, 0026 target mismatch, 0050 illegal instruction, **0051 access violation**, **0102 integer ÷ 0**, **0105 processor-load watchdog**, 0152 REAL ÷ 0, 4E21 application version mismatch |
| `PLC_R.i_lwSystemFault_1` | **active-low** bit field: 1 I/O bus, 2/3 Ethernet interfaces, 10 SD card, 11 firewall, 12 DHCP/FDR, **13 OPC UA server**, 23 NTP, 24 Syslog |
| other | `i_dwLastStopTime`, `i_dwLastPowerOffDate` (s since 1970 UTC), `i_dwAppliSignature1..4`, `i_wBootProjectStatus`, `i_wSdCardStatus` |

**`PLC_W`:** set `q_wPLCControl` (STOP, RUN, RESET_COLD or RESET_WARM), then move
`q_uiOpenPLCControl` from 0 to **6699** to execute. **Stopping a machine from code is a
safety decision**, so ask before generating it.

## Error classes and logs

- **Error classes:**
  - **External error:** the controller stays RUNNING or STOPPED, and the I/O LED is red.
  - **Application error** (bad code or a task watchdog): **HALT**, with the ERR LED red.
  - **System error:** **BOOTING → EMPTY**, with the ERR LED flashing fast.
- **Logs in `/usr/Syslog`:** `FwLog`, `PlcLog` (runtime), `LoggerFile_*.mel` and
  `crash.txt`. View them in the ME device editor's **Log** tab, the web server's
  Diagnostics menu, or the **Diagnostic** node in the Devices tree. Examples: 7236 system
  watchdog, 7240 application in error.

## Typical M262 faults

| Symptom | Cause / fix |
|---|---|
| HALT after running fine | Task watchdog (`i_wLastApplicationError = 16#0010`). Reduce the load or raise Time/Sensitivity, then reset |
| Reboot to EMPTY | System watchdog: tasks 0–24 at 100 % for more than 1 s, or a background task starved for 10 s |
| Persistent values lost | Download from an SD card, a reset origin, or a renamed or retyped persistent variable |
| `%MW` not retained | The M262 does not retain `%MW` implicitly. Use `VAR_GLOBAL RETAIN … AT %MWn` |
| OPC UA client cannot see a variable | Not in the Symbol Configuration; a GVL with no used variable; a `%MX`/`%IX` bit; or **no download since the edit** |
| OPC UA clients drop after a change | **The server restarts on download, online change and reset** |
| OPC UA login refused | Anonymous is refused by default; user rights are on; the certificate is untrusted (`/usr/pki/untrusted`); or the security policy does not match |
| Cannot log in the first time | There are no default credentials; the first ME connection must create an administrator |
| Firewall settings "ignored" | The default firewall script overrides them on download; or an SD-card security script is present |
| Modbus TCP not answering | TCP 502 is not enabled by default; wrong Unit ID (255 for the embedded server, 1–247 for the Slave Device); or a changed port reset by a power cycle |
| ME cannot log in, memory high | Memory use above 85 %; restart the controller |
| Event task HALT | More than 10 or 16 events per ms (`ISR Count Exceeded`) |
| Download refused | The firmware and device-description X.Y do not match, or the controller's Z is too low; update the firmware |

## Safety

- **M262 embedded safety:**
  - A TM5CSLC100FS/200FS safety logic controller sits on Sercos III as openSAFETY
    nodes, with TM5/TM7 "FS" I/O.
  - **Only one SLC is allowed under the Sercos master.**
  - The safety application is written in **EcoStruxure Machine Expert – Safety**.
  - Rated up to **SIL 3 (IEC 61508), PL e / Cat 4 (ISO 13849-1)**.
  - **ME V2.5 supports neither ME-Safety nor these devices.**
- **M580 Safety** (BMEP58…S):
  - A periodic **SAFE** task runs alongside the PROCESS tasks.
  - Rated SIL 3 (IEC 61508/61511) and SILCL 3 (IEC 62061).
  - It needs Control Expert XL (or L) with the Safety add-on.
  - `%S0` applies to PROCESS tasks only.
- **PLCopen Safety FB descriptions ship with ME** for ME-Safety, including
  `SF_EmergencyStop` and `SF_GuardMonitoring`. **Never present standard-task code as a
  safety function.**

## Motion

- **M262 + Sercos (Lexium 32S, Lexium 62/ILM62):**
  - Library "PLCopen MC Part 1", namespace **`PLCO`**, plus MotionInterface.
  - Single-axis FBs: `MC_Power`, `MC_Home`, `MC_MoveAbsolute`/`Relative`/`Additive`/`Velocity`,
    `MC_Halt`, `MC_Stop`, `MC_Reset`, `MC_SetPosition`, `MC_TorqueControl`,
    `MC_TouchProbe` and the `MC_Read*` blocks.
  - Multi-axis FBs: `MC_CamIn`, `MC_GearIn`, `MC_PhasingAbsolute`.
  - Homing FBs: `FB_HomingDigitalInput`, `FB_HomingTorque` and others.
- **Rules:**
  - **SoftMotion `SMC_*` POUs are not available on the M262.**
  - Motion FBs run in an application task, separate from the real-time motion task.
    **To start in the same Sercos cycle, buffer the command ahead.**
  - **Absolute moves need a homed axis.**
  - `MC_CamOut` and `MC_GearOut` are not needed. `MC_GearInPos` becomes `MC_CamIn` with a
    straight line.
- **Independent drives over CANopen, EtherNet/IP or Modbus TCP** (M241, M251 and the M262
  logic variants) use the GMC libraries:
  - `GIPLC`: PLCopen MC V2.00.
  - `GIATV` / `GILXM`: Altivar and Lexium vendor blocks, such as `Home_LXM32`.
