# Validator demo for the README (recorded against v0.2.0 with vhs 0.12.1).
# Re-record: from an empty directory that holds a clone of this repository at ./plc-programming,
#   run `vhs plc-programming/docs/assets/plc-demo.tape`. It writes plc-demo.gif to the current directory.
# The hidden setup writes the buggy and the fixed pump.st. The "AI edit" step is scripted:
# the fixed file is copied in off-screen and the diff shows the change. Both validator runs are real.
Output plc-demo.gif

Set Shell "bash"
Set FontFamily "DejaVu Sans Mono"
Set FontSize 13
Set Width 800
Set Height 480
Set Padding 14
Set Theme "Dracula"
Set TypingSpeed 35ms
Set WindowBar Colorful
Set CursorBlink false

Hide
Type `export PS1='$ ' PROMPT_COMMAND= HISTFILE=/dev/null; printf '%b' 'FUNCTION_BLOCK FB_Pump\nVAR_INPUT\n    LevelHigh : BOOL;\n    LevelLow  : BOOL;\nEND_VAR\nVAR_OUTPUT\n    PumpOn : BOOL;\nEND_VAR\n\nIF LevelLow THEN\n    PumpOn := TRUE;\nELSIF LevelHigh THEN\n    PumpOn := FALSE;\n\nEND_FUNCTION_BLOCK\n' > pump.st.buggy; printf '%b' 'FUNCTION_BLOCK FB_Pump\nVAR_INPUT\n    LevelHigh : BOOL;\n    LevelLow  : BOOL;\nEND_VAR\nVAR_OUTPUT\n    PumpOn : BOOL;\nEND_VAR\n\nIF LevelLow THEN\n    PumpOn := TRUE;\nELSIF LevelHigh THEN\n    PumpOn := FALSE;\nEND_IF;\n\nEND_FUNCTION_BLOCK\n' > pump.st.fixed; mkdir -p before && cp pump.st.buggy pump.st && cp pump.st before/pump.st && touch -d '2026-11-10 09:00' pump.st before/pump.st && clear`
Enter
Sleep 500ms
Show

Type "cat -n pump.st"
Sleep 300ms
Enter
Sleep 3.5s

Type "python3 plc-programming/scripts/plc_validate.py pump.st"
Sleep 300ms
Enter
Sleep 4s

# Scripted AI edit: the fixed file is copied in off-screen; the diff below shows exactly what changed.
Hide
Type "cp pump.st.fixed pump.st && touch -d '2026-11-10 09:01' pump.st && clear"
Enter
Sleep 300ms
Show

Type "# AI edit (Claude Code + plc-programming): close the IF block"
Sleep 400ms
Enter
Sleep 800ms

Type "diff -u --color=always before/pump.st pump.st"
Sleep 300ms
Enter
Sleep 4s

Type "python3 plc-programming/scripts/plc_validate.py pump.st"
Sleep 300ms
Enter
Sleep 4.5s
