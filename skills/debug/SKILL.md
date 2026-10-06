---
name: debug
description: >-
  Diagnose misbehaving PLC programs and machines by conversation: a timer that never
  finishes, an output that flickers or will not switch, a stuck SFC step or state machine,
  wrong analog values, lost retain data after download, watchdog/cycle-time faults, Modbus
  or OPC UA values that are off by one or byte-swapped, intermittent faults. Guides
  evidence gathering (online values, watch/trace, diagnostic buffer), maps symptoms to
  known PLC failure patterns, and proposes minimal, safe fixes. Use whenever the user
  reports that PLC logic, a sequence, a device or PLC communication does not behave as
  expected, on any platform (Siemens, Schneider, CODESYS, TwinCAT, Rockwell, ABB).
---

# Debugging PLC programs

**Safety first.** The user may be looking at a live machine.

- **Never** tell them to force outputs, bypass interlocks or download to a running process
  without first stating the consequence and asking whether it is safe (people, product,
  equipment).
- Prefer observation (monitoring, trace) over intervention (forcing, online change).

## Method

1. **Pin down the symptom.** Get the expected behaviour and the actual behaviour, when it
   happens (always, intermittently, after a download, after a power cycle, in one mode
   only), what changed recently, and on which platform and firmware.
2. **Collect evidence before theorising.** Ask for the relevant code, which is the POU
   that writes the misbehaving signal, not just the one that reads it. Also ask for
   online values at the moment of failure: a watch table, trace or logic-analyzer
   capture, the diagnostic buffer or alarm log, the task cycle time, and any forces
   that are active.
3. **Find every writer.** Search the whole project for assignments to the signal: coils,
   `:=`, S/R, block outputs, HMI and OPC UA writes, forces. Several writers is the
   first suspect. Validator rules ST031 and LX040 help.
4. **Match against known patterns.** Check
   [references/failure-patterns.md](references/failure-patterns.md), which is ordered by
   how often each pattern turns out to be the cause. Run
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/plc_validate.py <export>` on any code the
   user shares. It catches several patterns mechanically: conditional timers, double
   OTE, `=` used as assignment, REAL equality.
5. **Form one hypothesis at a time, and ask for the observation that separates it from
   the others.** Before accepting any check, ask what it would show if the hypothesis
   were false. If both answers look the same, the check proves nothing. For example,
   "the timer's ET stays at 0 while IN is TRUE" separates *not called* from *preset
   too long*.
6. **Fix minimally**, following the `develop` skill's rules. State the deployment impact
   (online change or full download, instance re-initialisation, retain loss) and how to
   verify the fix: the exact values to watch and the expected result.
7. **Close the loop.** Ask for the result, and do not declare the problem fixed until
   the user reports it.

## Platform tools to ask for

| Platform | Evidence |
|---|---|
| Siemens TIA | watch/force tables, S7-1500 trace, **diagnostic buffer**, **call environment** for monitoring multi-instances, `GetError`/`GetErrorID`, OB80/OB121 entries, PLCSIM |
| Schneider Machine Expert (M2xx) | watch lists, trace, breakpoints (these stop only the debug task, and its I/O is not updated), `PLC_R.i_wLastApplicationError` / `i_wLastStopCause` / `i_lwSystemFault_1`, the device **Log** tab (`/usr/Syslog`), the web server's Diagnostics menu, simulation (no watchdogs, paid licence) |
| Schneider Control Expert (M340/M580) | animation tables, watch points, breakpoints, the diagnostic viewer, `%S`/`%SW` (`%S19` overrun, `%S15`/`%S18`/`%S20` error flags, `%SW125` last error, `%SW30`–`%SW47` task times) |
| CODESYS / TwinCAT | watch lists, trace/Scope, breakpoints and flow control, the device log, exception call stack |
| Rockwell | trend, cross-reference, controller fault log (major/minor faults), `GSV` fault info |

See the platform skills for details (`siemens`, `schneider`, `other-platforms`).
