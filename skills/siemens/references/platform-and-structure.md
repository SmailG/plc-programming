# Siemens platform, program structure and memory model

Sources are the TIA Portal Information System (docs.tia.siemens.cloud, V20/V21), the
*Programming Guideline for S7-1200/S7-1500* V1.6 and the *Programming style guide* V2.1.0.
Where a claim rests on a secondary source it says so.

## TIA Portal and controllers (2026-09)

- **V21** (announced 2025-11-11):
  - **SIMATIC SD** now covers SCL, FBD and mixed-language blocks, and **SCL keeps its
    native syntax**.
  - **"Keep actual values"** keeps DB actual values across *structural* changes on
    download, for S7-1500 FW V4.1 with optimized DBs. It does not apply to changes of
    array dimension, string length, data type or retentivity, to DBs with a memory
    reserve, or to DBs holding references or "Set in IDB" tags.
  - Upgrades are accepted **only from V14 or later**. **STEP 7 V5.x projects cannot be
    migrated directly**: go through V14–V16 migration or the external tool for V17–V20.
  - **Openness add-ins built for V20 or earlier do not work in V21.**
- **V20**:
  - The first SD export (LAD, DB and UDT).
  - Named value types (NVTs) are allowed in the SCL textual interface.
  - Struct nesting depth rises from 8 to 26 on S7-1500 FW ≥ 4.0.
  - Adds S7-1200 G2 support.

| Family | Languages | Notes |
|---|---|---|
| S7-1200 (G1) | LAD, FBD, SCL, CEM (FW ≥ 4.2). **No STL, no GRAPH** | S5 timers not available |
| S7-1200 G2 | LAD, FBD, SCL, CEM (GRAPH not listed) | OPC UA server, Web API, PTO motion; firmware numbering is inconsistent in the sources |
| S7-1500 (standard, F, T/TF, R/H), ET 200SP CPU, software controller, S7-1500V | LAD, FBD, SCL, **STL, GRAPH**, CEM (FW ≥ 2.6) | STL is emulated on S7-1500; do not rely on accumulators or registers |
| S7-300 / S7-400 | LAD/FBD/STL/SCL/GRAPH (STEP 7 V5.x or TIA) | S7-300 delivery ended 2025-10-01 per secondary sources |

**Simulation and test:**

- **PLCSIM** and **PLCSIM Advanced V8.0** (with V21) cover S7-1500, ET 200SP, the
  software controller and S7-1200 G2 from FW V4.1. PLCSIM Advanced has an API for
  co-simulation.
- **TIA Portal Test Suite** has three parts: **Style guide** checks (Siemens publishes a
  rule set implementing its style guide), **Application test** against PLCSIM Advanced,
  and **System test** (Arrange/Wait/Assert over OPC UA, for HIL or SIL).
- **Openness** (.NET) automates export/import (SimaticML, SD), compile, download,
  libraries and VCI.
- **VCI** maps objects to directories for an external Git. **It does not support CEM
  blocks or know-how-protected blocks.**

## Organization blocks (S7-1500)

Priorities run from 1 (lowest) to 26. **Communication runs at priority 15**, so give
time-critical OBs a priority above 15.

| Event | OB | Default prio | If the OB is missing |
|---|---|---|---|
| Startup | 100 | 1 | ignore |
| Program cycle | 1 (and ≥ 123) | 1 | – |
| Time-of-day / time-delay | 10–17 / 20–23 | 2 / 3 | – |
| Cyclic interrupt | 30–38 | 8–17 | – |
| Hardware interrupt | 40–47 | 16 | ignore |
| **Time error** | **80** | 22 | **STOP on the first overrun.** A second overrun within one cycle means STOP even with OB80 |
| Diagnostic interrupt / pull-plug / rack error | 82 / 83 / 86 | 5 / 6 / 6 | ignore |
| MC-Servo / MC-Interpolator | 91 / 92 | 26 / 24 | added automatically with technology objects |
| **Programming error** | **121** | 7 | **STOP** |
| I/O access error | 122 | 7 | ignore |

- The cycle monitor defaults to **150 ms** (range 1–6000 ms). `RE_TRIGR` restarts it and
  `RT_INFO` gives runtime statistics.
- **OB121/OB122 are not called for a block that uses local `GET_ERROR`/`GET_ERR_ID`.**

## Blocks and instances

- **FB** has memory, in an instance DB or as a **multi-instance** in the caller's Static
  section. **FC** has none. There are also **global DBs**, **ARRAY DBs** (S7-1500,
  always optimized), **PLC data types** (UDTs), and **NVTs** (S7-1500, only inside
  software units).
- **Multi-instances** can be arrays indexed by a variable. **Parameter instances** are
  passed as InOut, including as a `DB_ANY`.
- **Software units** (S7-1500 FW ≥ 2.6, up to 255) have namespaces and can be downloaded
  independently.
- **Constants:**
  - Global constants live in the tag table and are written `"C"`.
  - Local constants live in `VAR CONSTANT` and are written `#C`.
  - A local constant wins on a name clash.

## Optimized vs standard access

| | Optimized (default on S7-1200/1500) | Standard |
|---|---|---|
| Addressing | symbolic only; no offsets, absolute access or ANY into it (use arrays or VARIANT) | symbolic plus absolute (`DB10.DBW2`), POINTER/ANY |
| `REF_TO` references | yes | no |
| Retentivity | per tag (set in the FB for instance data) | all or none |
| Layout | system-sorted; on S7-1500 a BOOL takes a byte and data is little-endian | declaration order, big-endian |
| Max size (S7-1500) | 16 MB | 64 KB |
| Download without reinitialization | yes | no |
| AT overlay | only for tags set to "Set in IDB" (sources conflict; the style guide discourages it) | yes |

Calling a block of the other access type passes the data **by copy**. That is slow and
can overflow the temp area.

## Initialisation, parameters and EN/ENO

- **Temp:**
  - In optimized blocks, temps start at their default value (the guideline says all
    temps; style guide SE002 says only elementary ones).
  - In standard blocks they are **undefined**.
  - **Always write a Temp before you read it.**
  - Temps cannot be monitored in watch tables.
- **Parameter passing** (style guide Table 10-1):
  - FC parameters: elementary types are copied, structured types go by reference.
  - FB Input and Output: **copied**, even for structures.
  - FB InOut: structures go **by reference**.
  - So pass large structures to FBs as **InOut**.
- **Outputs:** never read your own FB Output, and write each output once, near the end
  of the block.
- **EN/ENO in SCL:**
  - ENO is set automatically only if the block property **"Set ENO automatically"** is
    on. It is **off by default**; otherwise assign `ENO` yourself.
  - An FC's EN cannot be assigned in SCL; wrap the call in `IF` instead.
  - **Programming and I/O access errors never reach ENO.** Use OB121/OB122 or
    `GET_ERROR`/`GET_ERR_ID`.

## Pointers, references and arrays

- **VARIANT** (S7-1500; S7-1200 FW ≥ 4.1) is a type-checked pointer. Use it with
  `TypeOf`, `VariantGet`/`VariantPut`, `MOVE_BLK_VARIANT` and `CountOfElements`. Avoid it
  where performance matters (PE004).
- **DB_ANY** identifies any DB, including one that does not exist at programming time.
- **References (S7-1500):**
  - `REF_TO <type>` is allowed in an FC's Input, Output, Temp and Return, but **only in
    Temp for FBs and OBs**, and not in structs.
  - Targets are optimized global-DB tags or statics.
  - The initial value is `NULL`, and **dereferencing NULL is a programming error**
    (OB121 or STOP).
  - The operators are `REF()`, `^` and `?=`, checked with `IS_NULL`/`NOT_NULL`.
- **ARRAY:**
  - Up to 6 dimensions. The index is limited to −32768..32767 in standard blocks and
    to DINT in optimized ones.
  - `ARRAY[*]` parameters must always be supplied. Query their bounds with
    `LOWER_BOUND`/`UPPER_BOUND`, and pass them as InOut.
  - **An index out of range puts the S7-1500 into STOP** (unless OB121 or local
    `GET_ERROR` handles it). **The S7-1200 logs it and stays in RUN.** On both, **ENO is
    not cleared.** Validate indices explicitly.

## Download impact

- **Without "download without reinitialization"**, changing an FB interface
  re-initialises its instance DBs to their start values on the next download. This is
  the classic way setpoints and counters are lost on site.
- **Download without reinitialization** works for optimized LAD/FBD/STL/SCL blocks using
  a memory reserve, 100 bytes by default. It is **not available for GRAPH blocks, ARRAY
  DBs, ProDiag or CEM**.
- On V21 with S7-1500 FW 4.1, **"Keep actual values"** is the alternative, within the
  limits listed above.
- **Know-how-protected blocks** are excluded from SD, VCI and source export.
