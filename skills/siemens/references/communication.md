# Siemens communication from the program side

## PROFINET / PROFIBUS

- Third-party devices come in through **GSDML**.
- **IRT** uses a sync domain with reserved bandwidth.
- An **I-Device** is a CPU acting as an IO device with configured transfer areas,
  exported as a GSD for other projects. A **shared device** serves several controllers.
  An S7-1200 I-device area is at most 1024 bytes.
- `ModuleStates` (addressed by `HW_DEVICE`) reads module status, cyclically or in OB82.
- PROFIBUS DP uses `HW_DPMASTER`/`HW_DPSLAVE`. It was not researched further.

## S7 communication (PUT/GET), S7comm-plus, access control

- **PUT/GET is answered only if the server CPU has "Permit access with PUT/GET
  communication from remote partner"** enabled (Protection & Security), plus an access
  level above "No access".
  - On an **S7-1200 G2** you also need a UMAC Anonymous user with a suitable role.
    Addressing there is absolute only, so optimized DBs of a remote G2 cannot be reached.
  - **Siemens states that PUT/GET, PROFINET I/O exchange, T-blocks and CMs "have no
    security features".** Recommend OPC UA with security, or an isolated network.
- **S7comm-plus** is the symbolic protocol of TIA, HMI and PLCSIM. PG/HMI communication
  can use **TLS** ("Secure PG/HMI communication") on S7-1500 FW ≥ 2.9 and S7-1200 FW ≥ 4.5.
- **Access control:** S7-1500 FW ≥ 3.1 and S7-1200 FW ≥ 4.7 use **UMAC** (users and
  roles) unless the legacy access levels are selected.

## Open User Communication (TCP/UDP)

- **Instructions:**
  - Compact: `TSEND_C`/`TRCV_C`.
  - Separate: `TCON`, `TSEND`, `TRCV`, `TDISCON`.
  - UDP: `TUSEND`/`TURCV`.
- **Connection parameters, `TCON_IP_v4`:**
  - `InterfaceId : HW_ANY` (default 64)
  - `ID : CONN_OUC` (1..4095, matching the instruction's ID)
  - `ConnectionType : BYTE`: 16#0B TCP, 16#11 TCP, 16#13 UDP
  - `ActiveEstablished : BOOL`
  - `RemoteAddress : ARRAY[1..4] OF BYTE`
  - `RemotePort`, `LocalPort : UINT`
- **Secure variants:** `TCON_IP_V4_SEC`, `TCON_QDN`, `TCON_QDN_SEC`.

## Modbus

**Modbus TCP:** `MB_CLIENT` / `MB_SERVER` (and `MB_RED_*` for redundancy).

- **Every server connection needs its own instance DB and its own connection ID.**
- `MB_HOLD_REG` (VARIANT) points to an **optimized global DB** or the M area.
  - Function codes 3, 6, 16 and 23 operate on it.
  - **Modbus address 0 is the first WORD of that buffer**, which clients usually call
    "40001".
  - `HR_Start_Offset` shifts the base.
- Function codes 1, 2, 4, 5 and 15 access the process image directly (1 KB on S7-1200,
  32 KB on S7-1500), limited by statics such as `QB_Start`/`QB_Count`.
- **Security:** every client gets read and write access to the process image and the
  holding registers. Restrict access by IP, and expose a dedicated buffer rather than
  the machine's working data.

**Modbus RTU:** `Modbus_Comm_Load` (port, baud, parity, and an `MB_DB` pointing to the
master or slave instance), then `Modbus_Master` or `Modbus_Slave`.

- The legacy names are `MB_COMM_LOAD`, `MB_MASTER` and `MB_SLAVE`.
- **Keep `Modbus_Comm_Load` enabled until it completes.** It works asynchronously.

## OPC UA

- **Servers** exist on S7-1500, S7-1200 (G1) and S7-1200 G2.
  - The **standard SIMATIC server interface** exposes tags marked "Accessible/Writable
    from HMI/OPC UA". Style guide ES006 says that access should be **off by default**,
    so enable it per tag deliberately.
  - **Additional server interfaces:** user-defined, a reference namespace, or a
    **companion specification** imported as NodeSet XML (for example from SiOME) with
    PLC tags mapped to nodes.
  - Server methods use `OPC_UA_ServerMethodPre`/`Post`.
  - S7-1200 G2 limits: 2 interfaces, 2000 nodes, 5 subscriptions per session,
    1000 monitored items, 20 methods.
- **Client instructions** (S7-1500, and S7-1200 G2 in V21):
  - Connection: `OPC_UA_Connect`, `OPC_UA_Disconnect`, `OPC_UA_ConnectionGetStatus`.
  - Addressing: `OPC_UA_NamespaceGetIndexList`, `OPC_UA_NodeGetHandleList`,
    `OPC_UA_TranslatePathList`, and the `…ReleaseHandleList` instructions.
  - Data: `OPC_UA_ReadList`, `OPC_UA_WriteList`.
  - Methods: `OPC_UA_MethodGetHandleList`, `OPC_UA_MethodCall`.
  - Compact variants: `OPC_UA_ReadList_C`, `OPC_UA_WriteList_C`, `OPC_UA_MethodCall_C`.
  - This mirrors the PLCopen OPC 30001 list-based sequence (see the
    `packml-isa88-opcua` skill).
- **Both server and client need a runtime licence**, tiered by CPU:
  - Basic: S7-1200 and G2.
  - Small: up to CPU 1513 / 1505S.
  - Medium: up to CPU 1516 / 1507S.
  - Large: up to CPU 1518 / 1507D / 1508S.

## Other

- **MQTT on the CPU:** Siemens offers an "LMQTT" library through SIOS. Its entry ID,
  version and TLS support are unverified, and community SCL implementations exist.
  V21's MQTT features belong to WinCC Unified, not the CPU.
- **Web server:** the JSON **Web API** replaces the AWP/`WWW` user pages on S7-1500
  FW 4.0, S7-1200 G2, S7-1500V and the software controller.
- **PROFIenergy:** `PE_I_DEV` in an I-device, plus the `PE_*_RSP` helpers. Responses must
  arrive within 10 s.

## Data consistency

- An S7-1500 copies communication data consistently in blocks of up to **512 bytes**.
  PUT/GET and HMI have no coordination point, so keep those areas **≤ 512 bytes**.
- For larger data, copy with **`UMOVE_BLK`/`UFILL_BLK`** (uninterruptible, consistent up
  to 16 KB) and handshake with a done flag.
- A higher-priority OB can interrupt a multi-word copy in user code in the same way.
  Protect such copies with `UMOVE_BLK`.
