---
description: Generate a valid PLCopen XML v2.01 file and run the validator on it.
tags: [generate, exchange-formats]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
---

Create motor.xml in the current directory: a PLCopen XML v2.01 project containing a function block FB_Motor with BOOL inputs Start and Stop and a BOOL output Run, implementing a stop-dominant start/stop seal-in in Structured Text. It must import into a PLCopen-compliant tool, so check the file before you finish.
