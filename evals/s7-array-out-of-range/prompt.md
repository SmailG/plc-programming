---
description: S7-1500 vs S7-1200 reaction to an array index out of range.
tags: [knowledge, siemens]
max_turns: 10
allowed_tools: [Skill, Read, Glob, Grep]
---

In TIA Portal an SCL FB does `#buffer[#idx] := #value;` and #idx can occasionally exceed the array bounds. We have no OB121 in the project. What happens on an S7-1500 CPU, and would it be different on an S7-1200? How should I protect against it?
