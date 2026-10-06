---
type: llm
---

PASS if the answer maps 40001 to regs[0] (Modbus address 0, the first word of the MB_HOLD_REG buffer) and 40002 to regs[1], and says a second client connection needs its own MB_SERVER instance (instance DB) with its own connection ID.
FAIL if it maps 40001 to regs[1], or says one MB_SERVER instance can serve several client connections.
