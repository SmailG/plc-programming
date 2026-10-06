---
description: Siemens MB_SERVER register numbering (40001 = first word of MB_HOLD_REG).
tags: [knowledge, siemens, modbus]
max_turns: 10
allowed_tools: [Skill, Read, Glob, Grep]
---

S7-1500 as Modbus TCP server: MB_SERVER with MB_HOLD_REG pointing at "MbRegs".regs, an Array[0..99] of Word in an optimized global DB, HR_Start_Offset left at 0. Our SCADA reads holding register 40001 and 40002. Which array elements does it get? Also, can the same MB_SERVER instance serve a second SCADA client?
