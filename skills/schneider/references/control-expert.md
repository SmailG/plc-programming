# Control Expert (M340 / M580): structure, data, system bits, communication

Sources:

- *Program Languages & Structure* 35006144.27 (07/2026, "updated for Control Expert
  16.4"), cited as CE-PLS.
- *System Bits & Words* EIO0000002135.12 (07/2026).
- *Communication Block Library* 33002527.
- Product data sheets.

## Versions and editions

- The manuals dated 06–07/2026 are "updated for **Control Expert 16.4**". The full list of
  15.x/16.x releases is unverified.
- **Editions:** S, L, XL, and XL with M580 Safety. One installer serves all of them, and
  the licence decides the edition. Licences are node-locked or floating.
- **Platforms:** M340, M580 (including Safety and HSBY), Quantum, Momentum, Premium.
  Quantum reaches end of service on 2027-12-31 and Premium on 2026-12-31, per the data
  sheets.

## Program structure

- **Languages:** FBD, LD, IL, ST, SFC and **LL984**. All except LL984 follow IEC 61131-3,
  and IL is still listed in 16.4.
- **Tasks:**

  | Task | Period word | Range | Default | Watchdog (default) |
  |---|---|---|---|---|
  | **MAST** (mandatory) | `%SW0` (0 = cyclic) | 0–255 ms | cyclic | 10–1500 ms (250) |
  | **FAST** | `%SW1` | 1–255 ms | 5 ms | 10–500 ms (100) |
  | **AUX0–3** (**not on M340**, not on M580 HSBY) | `%SW2`–`%SW5` | 10 ms–2.55 s | 100–400 ms | 100–5000 ms (2000) |

  Event tasks are also available: TIMERi and EVTi, 64 on M340 and 128 on M580.
- **Overruns and watchdogs:**
  - A period overrun sets `%S19` for that task and execution continues.
  - **A watchdog overflow puts the CPU in HALT.** HALT cannot be left by switching to
    STOP; the application must be re-initialised.
- **Only the lowest-priority task may run cyclically**, so a cyclic MAST excludes AUX tasks.
- **Program units** (M580/M340) have their own public and local variables and sections.
  SFC is allowed only in MAST, and each unit runs in one task. Beneath them are
  **sections** and **SR subroutines**, which are usable only within one task.
- **Schneider's multitasking rules** (enforce these in reviews):
  - Each I/O belongs to **one** task.
  - Each global variable has **one writer task**.
  - Use handshake or validity flags between tasks.
  - Mask FAST (`%S31`) when updating data it shares.

## Data

- **Located variables:**

  | Kind | Objects |
  |---|---|
  | Internal | `%M`/`%MX` (EBOOL), `%MW` (INT), `%MWi.j` (bit), `%MD`, `%MF` |
  | Constants | `%KW`, `%KD`, `%KF` |
  | System | `%S`, `%SW` |
  | I/O | `%I`, `%Q`, `%IW`, `%QW`, `%ID`/`%QD` |
  | Network | `%NW` |

  - **`%MD`, `%MF`, `%KD` and `%KF` do not exist on the M340.**
  - `Var : DINT AT %MW10` occupies `%MW10` and `%MW11`.
- **Unlocated variables** are re-initialised on download and cold start. **To keep a
  value across an application transfer, give it a located address.**
- **M340 cold start:** `%MW` values are restored only if "Initialize %MW on cold restart"
  is deselected and a valid flash backup exists.
- **State RAM mapping** (M340 FW ≥ 02.40, Quantum):

  | Reference | Objects |
  |---|---|
  | 0x | `%Q`, `%M` |
  | 1x | `%I` |
  | 3x | `%IW` |
  | **4x** | **`%QW`, `%MW`** |

  This is Schneider's own statement of the 4x ↔ `%MW` convention.
- **DDT:** structures and arrays, nested up to 15 levels.
- **DFB** (user FB in LD, ST, IL, FBD or SFC):
  - Inputs are read-only inside it, and in/outs are read and written.
  - Outputs are read-only from the application. Publics are read/write. Privates can be
    seen only in animation tables.
- **EFB:** a vendor block written in C.
- **IODDT:** one variable with a module's complete I/O structure.
- **Device DDT:** the implicit instance per module in M580/M340 remote drops. `%KW` is not
  reachable through it.

## Key system bits and words (Control Expert 16.4)

| Bit / word | Meaning |
|---|---|
| `%S0` | cold start, set for the first restored cycle. **Not always set on the very first scan; use `%S21`** |
| `%S1` | warm start |
| `%S4`–`%S7` | 10 ms / 100 ms / 1 s / 1 min time bases |
| `%S9` | outputs to fallback |
| `%S10` | I/O OK (1) or error (0). Remote network errors are not reported here |
| `%S11` | watchdog overflow |
| `%S13` | first MAST cycle after STOP → RUN |
| `%S15` / `%S18` / `%S20` | string error / arithmetic overflow (including ÷ 0) / index overflow. **Per task; the application must reset them** |
| `%S19` | period overrun (per task) |
| `%S21` | first cycle of this task |
| `%S30`–`%S35`, `%S38` | enable MAST / FAST / AUX0–3 / events |
| `%S66` | application backup to the memory card |
| `%S78` | HALT on `%S15`/`%S18`/`%S20` |
| `%SW0`–`%SW5` | task periods |
| `%SW10` | first cycle after cold start (bit 0 MAST, bit 1 FAST…; 0 = first cycle). **Test `%SW10.0` to detect a cold start** |
| `%SW11` | MAST watchdog in ms |
| `%SW30`–`%SW47` | task execution times (current, max, min) |
| `%SW124` / `%SW125` | CPU error / last error type. `DEB0h` watchdog, `DEF0h` ÷ 0, `DEF3h` index overflow, `DE87h` float error, `2258h` HALT instruction |

Diagnostic buffer: `%S76`/`%S77` and `%SW76`–`%SW79`.

## Debugging

- **Tools:** animation tables (display, modify, force), inspection windows, **watch
  points** (values captured at an exact code location, which animation tables can be
  synchronised to) and breakpoints.
- The program is backed up to the memory card after a download or online modification, and
  on a rising edge of `%S66`.
- The rules for online modification ("Build Changes") are in *Operating Modes* 33003101
  and were not verified here. Check them before promising a change can go online.

## Communication EFs (`READ_VAR` / `WRITE_VAR`)

These are **procedures** driven by a 4-INT **management table**:

| Word | Content |
|---|---|
| 1 | exchange number; **bit 0 = activity bit**, bit 1 = cancel, bit 2 = immediate ack |
| 2 | operation report (MSB) and communication report (LSB) |
| 3 | **timeout, in 100 ms units** (0 = infinite; checked every second) |
| 4 | length in bytes |

The activity bit is TRUE while an exchange is in progress. A common pattern, written by us
rather than quoted from Schneider, issues a new request only when the previous one has
finished:

```text
IF NOT %MW40.0 THEN                 (* no exchange in progress *)
    READ_VAR(ADDM('0.0.0.6'), '%MW', 100, 10, %MW40:4, %MW10:10);
END_IF;
(* afterwards check the report in word 2 (%MW41) before using %MW10..%MW19 *)
```

The parameters are: address, object type, first object, count, management table, and
receive buffer.

- **The EF timeout must exceed the configured timeout × retries.**
- **ADDM forms:**

  | String | Meaning |
  |---|---|
  | `'0.0.3{192.168.2.3}'` | M580 CPU Ethernet port |
  | `'…{ip}TCP.MBS'` | Modbus TCP |
  | `'0.0.3{ip}CON.CIP'` / `UNC.CIP` | EtherNet/IP connected / unconnected |
  | `'r.m.c.e.MBS'` | serial slave, e = 1–247 |
  | `'0.0.2.e'` | M340 embedded CANopen |

- **M580 HSBY:**
  - The application is MAST + FAST only.
  - For communication EFs, untick "Exchange On STBY". Typical timeouts are 500 ms through
    the CPU and 2 s through a NOC.
- **I/O scanning** on M580/M340 is configured in DTMs (FDT/DTM, EDS import), not in code.
