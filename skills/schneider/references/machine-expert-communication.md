# Machine Expert (M2xx) communication from the program side

Sources: PG14 (M262 Programming Guide, 04/2026), the PLCCommunication library guide
EIO0000002962, the TcpUdpCommunication guide EIO0000002803.07, and the Machine Expert online
help. Protocol-level Modbus facts are in [modbus.md](modbus.md).

## Common Schneider FB behaviour

Most Schneider communication libraries share one behaviour model:

- `i_xEnable` activates the FB. `q_xActive` and `q_xReady` report its state.
- A rising edge on `i_xExecute` starts a job, reported through `q_xBusy`, then
  `q_xDone` or `q_xError`.
- **An error clears only when the FB is disabled.** Keep calling the FB while
  `q_xActive` is TRUE.
- Diagnostics come in three layers: `q_xError`, `q_etResult` (the library's `ET_Result`)
  and `q_sResultMsg`.

## OPC UA server (M262)

**Server parameters** (PG14):

| Parameter | Default |
|---|---|
| Server enabled (**this also enables the client**) | **disabled** |
| Anonymous login | **refused** |
| Security policy | **Basic256Sha256** (also None, and the deprecated Basic256) |
| Message security | **SignAndEncrypt** |
| Port | **4840** |
| Max sessions | **2** (1–4) |
| Max subscriptions per session | 20 |
| Min publishing interval | 1000 ms (200–5000) |
| Max monitored items per subscription | 100. The V2.6 range is 1–10 000; subscriptions × items must stay ≤ 10 000 |
| Node identifiers | **String** |

**Exposing variables (Symbol Configuration):**

- Add a Symbol Configuration under the Application, then tick variables, or use
  `{attribute 'symbol' := 'read'}`. The default access for OPC UA is **read-only**.
- Selecting `IoConfig_Globals_Mapping` exposes all mapped I/O.
- **A GVL's variables appear only if at least one of them is used in code.** For
  variables that are never compiled, use `{attribute 'linkalways'}`.
- **`%MX`, `%IX` and `%QX` bits cannot be exposed.** Pack them into words or BOOL
  variables first.
- Limits: at most **10 000 OPC UA variables**, arrays of up to 3 dimensions, no structures
  that contain a UNION, and STRING/WSTRING up to 255 characters.
- **The symbol file is generated at code generation and sent with the next download.**
  Editing the symbol set changes nothing on the controller until then.
- **Type mapping:**

  | IEC | OPC UA |
  |---|---|
  | BOOL | Boolean |
  | INT | Int16 |
  | WORD, UINT | UInt16 |
  | DINT, TIME, TOD | Int32 |
  | UDINT | UInt32 |
  | REAL | Float |
  | LREAL | Double |
  | DATE, DT | DateTime (1 s precision) |

- Do **not** enable "Configure synchronisation with IEC tasks" for motion or other
  time-critical applications, because it increases jitter.

**The server restarts on every download, online change and reset.** Clients must
reconnect and resubscribe.

**Performance:**

- The task cycle must be shorter than the publishing interval.
- Each extra session slows every session.
- An example read/write of 1000 symbols takes about 123–350 ms, depending on the model
  and configuration.
- Schneider warns **not to use OPC UA for safety-related or time-critical data**, or to
  change equipment state without a risk analysis.

**Certificates:**

- The own certificate is `TM262-XX-OPCUA`.
- **The PKI folders `/usr/pki/{issuer,trusted,untrusted}` are shared by the server and the
  client.**
- A certificate is trusted in the web server under Maintenance › Certificates.
- A rejected client certificate lands in `untrusted`.
- With DHCP, the self-signed certificate must be accepted without validation.

**Diagnostic IDs:**

| ID | Meaning |
|---|---|
| 7906 | maximum number of symbols reached; the rest are ignored |
| 7262 | configuration missing or corrupt (clean, rebuild, download) |
| 7269–7272 | out of memory |

`PLC_R.i_lwSystemFault_1` **bit 13 = 0** means an OPC UA server error. The fault bits are
active-low.

**The exact NodeId string format is not documented here.** Browse the server with a
client such as UaExpert rather than guessing `ns=…;s=…`.

## OPC UA client (OpcUaHandling)

- **FBs:** `UA_Connect`, `UA_ConnectionGetStatus`, `UA_NamespaceGetIndexList`,
  `UA_NodeGetHandleList`, `UA_ReadList`, `UA_WriteList`, `UA_Browse`,
  `UA_SubscriptionCreate…`, `UA_MonitoredItemAddList…`, `UA_TranslatePathList`,
  `UA_NodeReleaseHandleList`, `UA_Disconnect`. This is the PLCopen OPC 30001 list-based
  set.
- **The client works only when "OPC UA Server enabled" is ticked.**
- **Limits:** 5 servers, 5000 items per server, 15 000 in total.
- **Availability:** PG14 lists the client for the M262 generally. The V2.2 help limited
  it to L20/M25/M35, so check for L01/L10/M05/M15.

## Modbus

**Embedded Modbus TCP server:**

- It needs no configuration and answers in RUNNING, STOPPED and EMPTY.
- It is addressed with **Unit ID 255**. **TCP 502 is not enabled by default**; enable it
  in the Ethernet or security settings.
- **Function codes:**

  | FC | Operation |
  |---|---|
  | 1 | read `%Q` |
  | 2 | read `%I` |
  | 3 | read `%MW`, where holding register n = `%MWn` |
  | 6 / 16 | write `%MW` |
  | 15 | write multiple `%Q` |
  | 23 | read/write `%MW` |
  | 43/14 | device identification |

- The **system area** (`PLC_R` at `%MW60000`) and the **Relocation Tables** are also
  readable. See [machine-expert-platform.md](machine-expert-platform.md).

**Modbus TCP Slave Device** (an additional server object):

- Unit ID 1–247.
- `%IW` maps to registers 0…n-1 and is writable by the master. `%QW` maps to n…n+m-1 and
  is read-only.
- Only FC 3, 6, 16 and 23 are supported; anything out of range returns exception 02.
- An optional privileged master IP with a watchdog sets `i_byMasterIpLost`.

**Changing the port:** `changeModbusPort "1502"` from an SD-card `Script.cmd` or the
`ExecuteScript` FB. It works **only twice**, and the port **reverts to 502 after a power
cycle**.

**Modbus client (PLCCommunication):**

- **FBs:** `READ_VAR`, `WRITE_VAR`, `WRITE_READ_VAR`, `SINGLE_WRITE`, `SEND_RECV_MSG`,
  with `ADDM` to build addresses.
- **Common inputs:**
  - `Execute`, a rising edge. **Make the first call with Execute = FALSE**, because no
    edge is detected in the first cycle after a reset.
  - `Abort`.
  - `Timeout : WORD` in **100 ms units**, where 0 means infinite.
- **Outputs:** `Done`, `Busy`, `Aborted`, `Error`, and `CommError`:

  | Value | Meaning |
  |---|---|
  | 00 | OK |
  | 01 | timed out |
  | 02 | canceled |
  | 03 | bad address |
  | 04 | bad remote address |
  | 06 | bad parameters |
  | 07 | problem sending the request |
  | 09 | receive buffer too small |

  plus `OperError`.
- **Object types:**

  | Object | READ_VAR | WRITE_VAR | SINGLE_WRITE | WRITE_READ_VAR |
  |---|---|---|---|---|
  | `'MW'` | FC3 | FC16 | FC6 | FC23 |
  | `'I'` | FC2 | – | – | – |
  | `'Q'` | FC1 | FC15 | – | – |
  | `'IW'` | FC4 | – | – | – |

- **Quantities:** READ_VAR reads 1–125 registers or 1–2000 bits. WRITE_VAR writes 1–123
  registers.
- **`FirstObj : DINT`:** whether it is 0-based (the PDU address) or 1-based is not stated.
  It is most likely the PDU address, but test it against a known register before trusting
  the mapping.
- **`Buffer` is `ADR(array)`**, and the array must be at least as large as the data.
- **ADDM strings:**

  | String | Meaning |
  |---|---|
  | `'3{192.168.1.2}'` | embedded Ethernet, Unit ID 255 |
  | `'3{192.168.1.2}1'` | explicit Unit ID |
  | `'3{ip:port}'` | non-standard port |

  Link numbers: COM1 = 1, COM2 = 2, embedded Ethernet = 3, embedded CAN = 4, COM3 = 5.
  The exact serial address string is unverified.

**Modbus TCP IOScanner:**

- Up to 64 slaves, 8000 input and 8000 output words.
- Timeslot 20 ms (L01/L10/M05/M15) or 10 ms (L20/M25/M35).
- Configured in the device tree, not in code.

## EtherNet/IP (M262)

- **Adapter (target):**
  - Output assembly instance 150–189 and input assembly 100–149, 2–120 words each.
  - The originator's output lands in `%IW`, and its input comes from `%QW`.
  - Limits: **1 class-1 (I/O) connection**, 8 explicit connections, 16 sessions.
  - Cyclic only.
  - "Export as EDS" is on the EthernetIP node.
  - Choose the RPI and timeout to tolerate RSTP's ~100 ms convergence.
- **Scanner:** up to 64 targets. Mixed EIP and Modbus TCP devices: 96 on
  L01/L10/M05/M15, 128 on L20/M25/M35.
- **Ports:** TCP 44818, UDP 2222 and 44818.

## TCP/UDP sockets (TcpUdpCommunication)

- Namespace `TCPUDP`, qualified access only, IPv4 only.
- **FBs:**
  - `FB_TCPClient` / `FB_TCPClient2`, with TLS through `ConnectTls`.
  - `FB_TCPServer` / `FB_TCPServer2`.
  - `FB_UDPPeer`.
- **The FBs have no pins; use methods and properties.** After every call, check
  `Result`. **All methods block while `Result <> Ok` until you call `ResetResult`.**
- **Do not combine it with CAA Net Base Services** in one application, because they share
  system resources.

## MQTT (MqttHandling)

- Namespace `SE_MQTT`, with TLS where `FB_TCPClient2` TLS is available.
- **FBs:**
  - `FB_MqttClient`: `i_xEnable` on a rising edge, and `i_timTimeout` where T#0 means
    10 s. **It must be called every cycle.**
  - `FB_MqttPublish`: QoS 0 and 1 are documented.
  - `FB_MqttSubscribe`: a caller-supplied buffer, and `q_xNewMessage`.
- **Not documented:** QoS 2 and the MQTT protocol version.
- **The Free licence excludes MQTT.**

## CANopen, Sercos

- **CANopen master:** the M241 has one embedded. The M262 uses a TMS expansion module.
  Read slave state with the CiA 405 `GET_STATE` FBs; the old implicit `nStatus`
  variables are gone.
- **Sercos III** (M262 motion, Eth1): the TM5 islands and the safety logic controller
  synchronise with the motion task. Too much I/O on the bus overflows the cycle.
