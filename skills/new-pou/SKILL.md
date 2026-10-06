---
name: new-pou
description: Scaffold a new POU (PROGRAM, FUNCTION_BLOCK, FUNCTION, DUT or GVL) for a chosen platform and file format, validated before delivery.
argument-hint: "<kind> <name> [platform/format]"
disable-model-invocation: true
---

# Scaffold a new POU

The request is: `$ARGUMENTS`. It usually reads `<kind> <name> [platform/format]`, for
example `fb FB_Pump m262`, `fb FB_Pump tia-scl`, `program Main twincat` or
`fb FB_Pump plcopen`.

1. **Resolve anything missing, in one question round:**
   - **Kind**: PROGRAM, FUNCTION_BLOCK, FUNCTION, a DUT (struct or enum), or a GVL.
   - **Target**:
     - IEC ST text
     - Siemens SCL source (`.scl`) or SIMATIC SD
     - TwinCAT `.TcPOU` / `.TcDUT` / `.TcGVL`
     - PLCopen XML (`tc6_0201`, or `tc6_0200` for CODESYS-family import)
     - Machine Expert or CODESYS (PLCopenXML or text)
     - Logix AOI (L5X)
     - Control Expert DFB
   - **Purpose**, in one sentence, plus its inputs and outputs, or "empty skeleton".
2. **Start from the closest template:**
   - The `other-platforms` skill assets `FB_Template.TcPOU` and `E_TemplateState.TcDUT`.
   - The `exchange-formats` skill asset `plcopen-st-pou.xml`.
   - The `siemens` and `schneider` skill assets.
   - The patterns in the `develop` skill's `references/code-patterns.md`.
3. **Apply the conventions:**
   - Use the project naming scheme if one exists; otherwise ask.
   - Make an explicit state enum for any sequential behaviour.
   - Call timers and edges unconditionally.
   - Write each output once.
   - Give every `CASE` an `ELSE`.
   - Write a header comment stating purpose, author placeholder and version.
4. **Generate fresh identifiers** where the format needs them: TwinCAT `Id` GUIDs,
   SimaticML `ID`/`UId` numbering, PLCopen `globalId` as an NCName.
5. **Run** `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/plc_validate.py <file>` and fix the
   findings.
6. **Deliver** the file, the import steps for the target IDE, and what was not verified
   (the file was never compiled).
