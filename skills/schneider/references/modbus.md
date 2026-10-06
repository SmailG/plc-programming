# Modbus: protocol facts that decide whether values arrive right

Sources: the Modbus Application Protocol V1.1b3, the Modbus Messaging Implementation
Guide, and Modbus over Serial Line (modbus.org). Platform mappings are in
[machine-expert-communication.md](machine-expert-communication.md) (M2xx),
[control-expert.md](control-expert.md) (M340/M580), and the `siemens` skill's
`references/communication.md`.

## Data model and addressing

| Table | Size | Access | Conventional reference |
|---|---|---|---|
| Coils | 1 bit | read/write | 0xxxx |
| Discrete inputs | 1 bit | read | 1xxxx |
| Input registers | 16 bit | read | 3xxxx |
| Holding registers | 16 bit | read/write | 4xxxx |

- **The spec says "data numbered X is addressed in the PDU X-1".** Reference 40001 is
  holding register #1, which is **PDU address 0**. Every "off by one" comes from mixing
  these two conventions. Before trusting a mapping, check which one each tool shows,
  using a known value.
- **Byte order within a register is big-endian.**
- **32-bit values** (DINT, REAL) span two registers, and **the word order is decided by
  the device.** Common orders are ABCD and CDAB. Test with a known value such as
  `16#12345678` or `1.0` = `16#3F800000`.
- **Schneider:** `DINT AT %MW10` occupies `%MW10`–`%MW11`. Which word is the low word was
  not stated in the sources read, so verify it.

## Function codes and limits

| FC | Function | Quantity |
|---|---|---|
| 01 | Read Coils | 1–2000 |
| 02 | Read Discrete Inputs | 1–2000 |
| 03 | Read Holding Registers | 1–125 |
| 04 | Read Input Registers | 1–125 |
| 05 | Write Single Coil | – |
| 06 | Write Single Register | – |
| 08 | Diagnostics | serial only |
| 15 | Write Multiple Coils | 1–1968 |
| 16 | Write Multiple Registers | 1–123 |
| 22 | Mask Write Register | – |
| 23 | Read/Write Multiple Registers | read 1–125, write 1–121 |
| 43/14 | Read Device Identification | – |

**Exceptions** set the function code + 0x80:

| Code | Meaning |
|---|---|
| 01 | illegal function |
| **02** | **illegal data address** (usually an off-by-one or a range error) |
| 03 | illegal data value |
| 04 | server device failure |
| 06 | busy |

**Size limits:** the PDU is at most 253 bytes; the TCP ADU at most 260.

## Modbus TCP and serial

- **Modbus TCP:**
  - A 7-byte MBAP header (transaction, protocol 0, length, **unit id**) on **TCP 502**.
  - For a server addressed directly, **Unit ID 0xFF (255)** is recommended, and 0 is also
    accepted.
  - Gateways use the Unit ID to select the serial slave.
  - **Schneider M262:** the embedded server uses Unit ID 255, and the Slave Device object
    uses 1–247.
- **Serial (RTU/ASCII):**
  - RTU is the default mode (CRC). ASCII uses LRC. The default parity is **even**.
  - Slave addresses are 1–247, with 0 as broadcast.
  - Frames are separated by ≥ 3.5 character times, and a gap over 1.5 character times
    inside a frame breaks it. Above 19 200 baud the timers are fixed.

## Design rules

- **Keep one source of truth for the register map.** Keep it in a table with columns for
  the reference, PDU address, PLC variable, type, word order, scaling, units and access.
  Generate code or documentation from it.
- **Every read value needs freshness.** Use a heartbeat register or a timestamp, and have
  a defined reaction when it goes stale.
- **Writes from SCADA/BMS are requests, not commands to outputs.** Validate the range,
  state and permission in the PLC.
- **Modbus has no security.** Restrict the port, the source IPs and the writable range,
  or use Modbus/TCP Security (TLS) where the device supports it; the M580 lists "Modbus
  TLS".
