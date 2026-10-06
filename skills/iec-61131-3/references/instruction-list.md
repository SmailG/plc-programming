# Instruction List (IL): for legacy code only

**Status:** deprecated in Ed.3 (2013) and **removed in Ed.4 (2025)**. The committee's
rationale, via IEC TR 61131-8, was that "an assembler-like language is not up-to-date in
modern development environments". Read IL to maintain or migrate it. Never write new IL.

## Model

IL works on a single accumulator, the "current result" (CR), using
`result := result OP operand`. Each line holds an optional label, an operator with
modifiers, and an operand.

| Operator | Modifiers | Meaning |
|---|---|---|
| `LD` | N | load the operand into CR |
| `ST` | N | store CR to the operand |
| `S`, `R` | – | set / reset the BOOL operand when CR = 1 |
| `AND` / `&`, `OR`, `XOR` | N, `(` | logic |
| `NOT` | – | complement CR |
| `ADD` `SUB` `MUL` `DIV` `MOD` | `(` | arithmetic |
| `GT` `GE` `EQ` `NE` `LE` `LT` | `(` | compare; CR is the left operand |
| `JMP` | C, N | jump to a label |
| `CAL` | C, N | call an FB instance |
| `RET` | C, N | return |
| `)` | – | evaluate the deferred operation |
| `ST?` | – | assignment attempt (Ed.3) |

Modifiers:

- `N` negates the operand: `ANDN %IX2` means `CR AND NOT %IX2`.
- `C` makes the operator conditional on CR = 1. `CN` makes it conditional on CR = 0,
  as in `JMPCN`.
- `(` defers the operation until the matching `)`.

## Example and its ST equivalent

```
       LD    xStart
       OR    xRunning
       ANDN  xStop
       ST    xRunning      (* seal-in circuit *)
       LD    xRunning
       JMPCN SkipTimer
       CAL   tonRun(IN := TRUE, PT := T#5S)
SkipTimer:
       LD    tonRun.Q
       ST    xRunLong
```

```iecst
xRunning := (xStart OR xRunning) AND NOT xStop;
tonRun(IN := xRunning, PT := T#5S);   // migration fix: the IL called the timer conditionally
xRunLong := tonRun.Q;
```

**Migration traps:**

- `JMPCN` around a `CAL` means a timer or counter is called only conditionally. That
  is usually a latent bug, so fix it rather than copy it (see the `debug` skill).
- CR carries across lines. Make sure every `ST` stores the value you think it does,
  especially after a `)`.
- Vendor IL (Siemens STL/AWL, Schneider/Modicon, Rockwell) is **not** IEC IL. For
  example, STL has status bits, accumulators 1 and 2, and `A`/`AN`/`O`/`=`. Identify
  the dialect before translating.
