# Machine Expert and M2xx: platform, tasks, memory, online change

**Sources** (Schneider, current as of 2026-09):

- M262 Programming Guide EIO0000003651.**14** (04/2026, "updated for ME V2.6"), cited as PG14.
- M262 System Library Guide EIO0000003667.**09** (04/2026).
- ME V2.5 Compatibility & Migration Guide EIO0000005500.01 (12/2025).
- Software Installer (SESI) guide EIO0000002848.07.
- The Machine Expert online help at <https://product-help.se.com/docs/Machine%20Expert/>.

## Versions

| ME | CODESYS compiler | Notes |
|---|---|---|
| V2.2.x | 3.5.19.30 | the last version with online help published on product-help.se.com |
| V2.3 | 3.5.20.30 (SP20) | J1939_Manager removed |
| **V2.5** | 3.5.21.30 | **platform change** (below) |
| **V2.6** | unverified | release notes dated 2026-04-30; PG14 is "updated for V2.6" |

- **No V2.4 appears** in Schneider's compiler map, and Machine Expert has **no "26.x" naming**.
- **ME V2.5:**
  - Applications are created through the **"Machine Expert Portal (Platform)"** and use
    **file-based storage**. Projects from V2.3 or earlier are converted on import; a
    `.projectarchive` is the preferred vehicle.
  - **Dropped:** SVN, **EcoStruxure Machine Expert – Safety**, Vijeo-Designer and Motion
    Sizer.
  - **Unsupported devices:** the TM5CSLC safety logic controller, TM5/TM7 safety I/O,
    LXM62 "Safety via Sercos" (hardwired STO variants are fine), TM238/TM258,
    LMC058/078, and others. The new M660 motion controller replaces PacDrive LMC.
  - **Consequence:** an M262 with embedded safety, or with a Vijeo-Designer HMI in the
    same project, **cannot move to V2.5**. Whether V2.6 restores this is unverified.
- **Firmware vs device description** (X.Y.Z.T): X.Y must match, the controller's Z must
  be ≥ the description's Z, and T is ignored. A mismatch shows as
  `Version: in project=3.5.20.30, in target device=3.5.16.90`.
- **Licences:**
  - **Free:** 1 seat, **no simulation, no breakpoints, no online change**, no
    communication libraries, and no MQTT/JSON.
  - **Standard:** up to 10 seats.
  - **Professional:** includes floating licences.
  - **Trial:** 42 days.
  
  **Before recommending online change or simulation, ask which licence the user has.**

## M262 hardware

| Reference | Speed / role |
|---|---|
| TM262L01 / L10 | logic, 5 µs per 1000 instructions |
| TM262L20 | logic, 3 µs per 1000 instructions |
| TM262M05 / M15 | motion, 5 µs per 1000 instructions |
| TM262M25 / M35 | motion, 3 µs per 1000 instructions |

- **Ports:** on the motion variants **Eth1 is Sercos III**. On the logic variants Eth1 is
  10/100 and Eth2 is a dual-port gigabit switch.
- **Memory:** 256 MB RAM (32 MB for the application), 1 GB flash, **NVRAM 64 kB Retain +
  64 kB Persistent**.
- **Motion capacity** in the V2.6 guide: M35 handles up to **24 axes at a 4 ms Sercos
  cycle**. Older help said 16, and it depends on firmware.
- **Embedded services:**
  - Web, HTTPS and WebVisu.
  - Modbus TCP client, server and IOScanner; Modbus serial.
  - EtherNet/IP adapter and scanner (up to 64 targets).
  - CANopen master via a TMS module.
  - **OPC UA server and client, and MQTT, both with TLS.**
  - The SQL client appears in the L20 data sheet.

## Tasks and watchdogs (M262)

| Item | Value |
|---|---|
| Tasks | at most 16: 8 cyclic, 1 freewheeling, 8 event, 8 external event |
| Priority | 0–31 (0 highest), **must be unique** or the build fails. 0–24 are controller tasks, 25–31 background |
| Default MAST | cyclic, priority 15, **10 ms**, task watchdog **50 ms**, sensitivity 1. Do not rename or delete MAST |
| Event task | fires on the rising edge of a global BOOL. At most 10 events/ms (L10/M15) or 16/ms (L20/M25/M35); beyond that you get `ISR Count Exceeded` and HALT |
| Bus cycle task | TM3 and CANopen exchange run in MAST by default. **Outputs in the same byte written from different tasks give a build error** |

**Task watchdog** (Time × Sensitivity):

- It raises an application error: **HALT**, with `PLC_R.i_wLastApplicationError = 16#0010`.
- A reset is needed to leave HALT.
- **Watchdogs are not active in simulation.** A design that passes simulation can still
  trip on the real controller.

**System watchdogs** (not configurable):

| Condition | Result |
|---|---|
| All tasks above 85 % CPU for more than 3 s | HALT |
| Tasks at priority 0–24 at 100 % for more than 1 s | reboot to **EMPTY** |
| Lowest-priority task starved for 10 s | reboot to **EMPTY** |

**Other task rules:**

- **Referencing a PROPERTY in an event task causes a watchdog exception at download.**
- CANopen heartbeat, node-guarding and SYNC times should be multiples of the task cycle.

## Remanence (PG14; X = kept, – = re-initialised)

| Event | VAR | VAR RETAIN | VAR GLOBAL RETAIN PERSISTENT |
|---|---|---|---|
| Online change | X | X | X |
| Online change that modifies the boot application | – | X only for code-only changes | X |
| Stop | X | X | X |
| Power cycle / reset warm | – | X | X |
| Reset cold | – | – | X |
| Reset origin (device) | – | – | – |
| **Download from ME** | – | – | **X** |
| Download from SD card | – | – | – |

- **Only PERSISTENT survives a download**, and only when the new application contains the
  same persistent variables. **Renaming a persistent variable or changing its type
  re-initialises it.**
- The "Persistent Variables" object is a GVL with `VAR_GLOBAL PERSISTENT RETAIN`. "Add all
  instance paths" collects the PERSISTENT declarations found in POUs.
- **Every retain or persistent access is an NVRAM access.** Reading 1000 INT takes about
  0.4 ms, so copy these values to RAM when they are read often.
- **The M262 does not retain `%MW` implicitly**, unlike older M2xx controllers. Declare
  retained registers explicitly (FA409837):

```iecst
VAR_GLOBAL RETAIN
    iRecipeNo AT %MW100 : INT;
END_VAR
```

## %MW map and Relocation Table (M262)

| %MW range | Use |
|---|---|
| 0–59999 | user |
| 60000–60199 | system / diagnostic, **read-only via Modbus** (`PLC_R`; `i_wStatus` at 60012) |
| 60200–61999 | **Read Relocation Table**, filled every cycle |
| 62000–62199 | system / diagnostic, read/write via Modbus |
| 62200–63999 | **Write Relocation Table**, copied to its variables every cycle |

There is one Relocation Table per controller, and its name is fixed. It gathers scattered
variables into contiguous Modbus registers.

**If controller memory use exceeds 85 %, Machine Expert may fail to log in. Restart the
controller.**

## Login, download and online change

- **Login dialog choices:**
  - **Login with online change** (the default): loads only what changed, and the machine
    keeps its state.
  - **Login with download**: full download and re-initialisation (see the remanence table).
  - **Login without any change**: monitoring may then be misleading ("Program modified").
- **Online change rules:**
  - **Pointers keep their old values, so reassign pointers every cycle.**
  - Removing implicit checks such as CheckBounds forces a full download.
  - **After Build › Clean, online change is impossible.**
  - Device and module settings cannot be changed online.
- **Other rules:**
  - From V2.2 only **one ME instance** can be logged into an application.
  - Downloads require the operating mode **Debug**.
  - A **memory reserve** (View › Online Change Memory Reserve Settings) makes online
    change of FBs faster.
- **The M262 OPC UA server restarts on every download, online change and reset.** OPC UA
  clients must reconnect, so design SCADA and MES clients to reconnect and resubscribe.
- **Reconnecting from another PC without a download** needs pinned library and compiler
  versions and a project archive that includes the download information.
- **The boot application** is `/usr/App/Application.app`. "Update boot project" is off by
  default for online change.

## Debugging, simulation, static analysis

- **Breakpoints** stop **only the debug task**, and other tasks keep running.
  - The I/O handled by the stopped task is **not updated**, even with "Update IO while in
    stop".
  - Conditional breakpoints, stepping and flow control are available.
  - You cannot debug several tasks at the same time.
- **Simulation** needs a paid licence and has no watchdogs.
- **Trace** acts as an oscilloscope. It keeps running after logoff and **adds cycle
  time**. A traced property needs `{attribute 'monitoring'}`.
- **Core dumps** (`<app>.core`, Debug › Load Core Dump) and `__TRY`/`__CATCH` are
  controller-dependent. Whether the M262 supports them is unverified.
- **Forcing:** "Generate force variables for IO mapping" is listed as *not used* on the
  M262. Use watch lists with write/force.
- **Static Analysis Light** runs on every code generation and reports `SA<nnn>`.
  - Suppress rules with `{analysis -24}` … `{analysis +24}` or
    `{attribute 'analysis' := '-33, -31'}`.
  - **SA0004, multiple write access on an output, cannot be suppressed.**

## Cybersecurity (M262)

- **User rights are on by default** (V2.2 and later), and **there are no default
  credentials.**
  - The first ME connection must create an administrator.
  - Until then web, FTP and OPC UA reject logins.
  - The function groups include **Symbol Configuration** and **OPC UA**.
- **Cybersecurity Admin Expert (CAE)** can manage RBAC (ENGINEER, INSTALLER, OPERATOR,
  SECADM, VIEWER) and per-port service masks. **Do not create users in ME while CAE
  manages security.**
- **Firewall:** a default script (`/usr/Cfg/FirewallDefault.cmd`) overrides the
  application's settings on download. An SD card carrying a cybersecurity script can
  **block boot**.
- **Default port states** (PG14 "Used Ports"):
  - **Modbus TCP 502 is not enabled by default.**
  - HTTP 80 redirects to HTTPS 443.
  - The programming protocol uses TCP 11740 and UDP 1740, for at most 5 clients.
  - WebVisu uses 8080/8089.
  - FTPS is on by default.
  - SNMP is off.
