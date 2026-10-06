# PLC failure patterns: symptom → cause → discriminating observation → fix

Ordered roughly by how often each turns out to be the cause.

## 1. Timer / edge / counter instance not called every scan

- **Symptom:** a timer never reaches Q, or finishes "early" on a later cycle. An edge is
  "missed". A counter skips counts.
- **Cause:** the instance call sits inside `IF`/`CASE`, an SFC action, a skipped
  subroutine (Logix `JSR` inside a condition) or a jump-around (IL `JMPCN`). When it is not
  called, `ET` and `Q` freeze, and the edge memory holds a stale value.
- **Discriminator:** with `IN` TRUE, watch `ET`. If it does not increase, the call is not
  executing. Also check a call counter or the branch condition.
- **Fix:** call it unconditionally and gate `IN`/`CLK`. Validator rules: ST030–ST033.

## 2. Output written in more than one place

- **Symptom:** an output flickers, ignores its rung, or works only in one mode.
- **Cause:** double coil or several `:=` writers; the last writer in the scan wins. An HMI
  or OPC UA write may be fighting the program. A force may be active.
- **Discriminator:** cross-reference every writer, and check the force list.
- **Fix:** keep one writer that combines the conditions. Rules: LX040, PLCopen CP12.

## 3. Set/Reset priority or seal-in logic

- **Symptom:** a device will not stop, or will not stay on.
- **Cause:** S and R are both true, and the later rung wins. The seal-in path bypasses the
  stop. A permissive is placed in the hold path, so the device drops out.
- **Fix:** use SR/RS to make dominance explicit, and make it stop-dominant for stops.

## 4. Stuck sequence (SFC step or state machine)

- **Symptom:** the machine "waits forever".
- **Cause:** the transition condition can never be true (a sensor failed, a condition
  was inverted, an edge was consumed elsewhere). There is no timeout supervision. A
  simultaneous branch never converges. A stored action is still set.
- **Discriminator:** read the current step or state and each term of its exit condition
  online.
- **Fix:** repair the condition, and add a timeout and fault state on every waiting step.

## 5. Values lost or reset after a download or power cycle

- **Symptom:** counters and recipes are zero after a change, or the machine starts by
  itself after power returns.
- **Cause:**
  - The variable is not RETAIN/PERSISTENT.
  - The interface changed, which forced instance re-initialisation (Siemens DB
    re-initialisation without "download without reinitialization"; a CODESYS layout
    change).
  - Commands were made retentive by mistake.
- **Fix:** classify every variable (see design-method §7). Back up retain data before an
  interface change.

## 6. Numeric errors

| Symptom | Cause | Fix |
|---|---|---|
| Value jumps or wraps negative | INT/DINT overflow, narrowing conversion, TIME wrap | wider type, `LIMIT`, overflow check |
| Comparison "never true" | exact `=` on REAL | tolerance |
| Totaliser stops increasing | REAL precision (about 7 digits): small increments lost in a large sum | LREAL, or split totals |
| Off by 0.5 | REAL→INT rounds half to even, not up | explicit `TRUNC` or rounding |
| CPU fault or exception | division by zero, array out of range (CODESYS exception, Siemens OB121 or `GetError`, Logix major fault) | guard it |

## 7. Wrong analog value

- **Cause:**
  - The raw range is wrong (module-specific; e.g. Siemens nominal 0…27648).
  - Signal type or module configuration mismatch (0–10 V vs 4–20 mA).
  - Scaling EU min and max are swapped.
  - A wire break reads as a plausible value.
  - Filtering is too heavy.
- **Discriminator:** compare the raw value with a calibrator or meter, at 0 %, 50 % and
  100 %.

## 8. Communication values wrong or stale

- **Off by one register:** a Modbus "40001" reference is PDU address 0. Tools differ in
  whether they display 0- or 1-based addresses.
- **Garbage for a 32-bit value:** word or byte order (ABCD / CDAB / BADC / DCBA).
- **Value frozen:** the connection dropped and the program keeps the last value without
  a quality flag. Add a heartbeat or timestamp and a stale-data reaction.
- **OPC UA node missing or read-only:** the symbol set or configuration was not
  downloaded, or the variable is not marked accessible or writable (see the platform
  skill).

## 9. Cycle-time overrun, watchdog, task starvation

- **Symptom:** the CPU stops (for example S7 OB80 time error, or a CODESYS/Machine Expert
  watchdog exception), or other tasks start jittering.
- **Cause:** unbounded loops, large string or array work, too many communication blocks
  per scan, heavy logging, a priority inversion.
- **Fix:** bound the work per scan (process N items per cycle), move it to a slower task,
  and measure the cycle-time statistics.

## 10. Multi-task data consistency

- **Symptom:** a rare, "impossible" combination of values, such as a setpoint paired
  with the wrong recipe.
- **Cause:** the reader task preempted the writer mid-update.
- **Fix:** copy the data consistently (a single struct copy in a protected section, or a
  sequence number), or keep producer and consumer in the same task.

## 11. Signal shorter than the scan

- **Symptom:** occasional missed pulses from encoders, proximity sensors or photo-eyes.
- **Fix:** use hardware counters, interrupt or event tasks, or a latching input module.
  Stretch the pulse at the source.

## 12. Environment and process (not the code)

This covers forced I/O left active, online edits not saved to the project, running code
that differs from the offline project, a wrong project version on the controller, and
wiring (NO/NC swapped). **Compare the online checksum or version with the offline
project before debugging the logic.**
