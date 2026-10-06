# Ladder Diagram (LD) and Function Block Diagram (FBD)

## LD elements

**Rails, links and evaluation:**

- The left power rail is always ON. The right rail may be drawn implicitly.
- Series links are AND. A vertical link is the OR of the links to its left.
- Rungs are evaluated from top to bottom, and each rung from left to right, unless a
  jump or return intervenes.

| Symbol | Name | Behaviour |
|---|---|---|
| `--\| \|--` | normally open contact | passes power when the variable is TRUE |
| `--\|/\|--` | normally closed contact | passes power when the variable is FALSE |
| `--\|P\|--` | positive transition-sensing contact | passes power for **one evaluation** on a FALSE→TRUE change, while the left link is ON |
| `--\|N\|--` | negative transition-sensing contact | one evaluation on a TRUE→FALSE change |
| compare contact (Ed.3) | typed or overloaded comparison | passes power when the comparison is true |
| `--( )--` | coil | variable := left link |
| `--(/)--` | negated coil | variable := NOT left link |
| `--(S)--` | set (latch) coil | variable := TRUE when the left link is ON |
| `--(R)--` | reset (unlatch) coil | variable := FALSE when the left link is ON |
| `--(P)--` / `--(N)--` | transition-sensing coils | the variable is TRUE for one evaluation after the left link rises or falls |

Rules and conventions:

- An FB or function placed in LD must expose at least one BOOL input and one BOOL output
  so that power can flow, usually `EN`/`ENO`.
- **Write each coil once.** Two `( )` coils on the same variable make the later rung
  win, so the earlier rung silently does nothing ("double coil"). PLCopen CP12 says to
  write physical outputs once per cycle.
- Pair `S` and `R` coils deliberately. If both rungs are true in the same scan, the
  **later rung wins**, so put the dominant one last. Better still, use the `SR` or `RS`
  FB, which makes the dominance explicit.
- **PLCopen L5:** do not follow a coil with a contact on the same rung.
- Keep rungs short (roughly 7–10 contacts across) and name every rung with a comment.

## Seal-in (start/stop) rung

```
|  xStart      xStop         xMotor |
|---| |----+----|/|-----------( )---|
|  xMotor  |                        |
|---| |----+                        |
```

This is equivalent to `xMotor := (xStart OR xMotor) AND NOT xStop;`, which is
stop-dominant. For a safety function, the stop input should be wired normally closed,
so that a broken wire stops the machine. The contact in the program then reads the
healthy-TRUE signal, and its symbol name should say so, for example `xStopOk`.

## FBD

- Blocks are connected by signal lines, and their evaluation order follows data flow,
  or execution order where the IDE lets you set it.
- **Outputs must never be wired together.** There is no wired-OR; use an explicit OR block.
- Execution control:
  - A block with `EN` = FALSE does not execute, and its `ENO` is FALSE.
  - Jumps are drawn `--->>LABEL`, and returns `<RETURN>`.
- Feedback loops need an explicit variable. The IDE decides where the loop breaks, so
  make that point visible.

## EN/ENO semantics

`ENO` = FALSE means either that the block did not execute (`EN` = FALSE) or that it
detected an error. Siemens LAD/FBD relies heavily on ENO (the "Set ENO automatically"
block property), while CODESYS and TwinCAT rarely show EN/ENO in ST. When converting
between them, decide how each ENO error path is represented, for example as an explicit
`xError` output.
