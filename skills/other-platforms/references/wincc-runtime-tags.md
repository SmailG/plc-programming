# Reading current WinCC 7 tags, and the newest archive block

Use this when a value the controller is acting on is not in the control gateway's
read list, and a WinCC 7 runtime on the same PLC already has the tag. Do not open
another OPC UA session to that PLC. Read the tag through the runtime that is
already subscribed, or read the archive that runtime is already writing.

Two different questions, two tools:

| Question | Tool | What a miss looks like |
|---|---|---|
| What is the tag right now, including one that is not archived? | `scripts/wincc_runtime_tags.ps1` | quality other than 192, or the error column |
| What did an archived tag do in its newest block? | `scripts/wincc_latest_block.py` then `scripts/wincc_binvalues.py` | `check` says the line was cut; a tag with no rows did not change in that segment |

The archive format and the rule against attaching a segment to a live WinCC are in
[wincc-tag-logging-archive.md](wincc-tag-logging-archive.md). This page does not repeat them.

## Live read

`CCHMIRuntime.HMIRuntime` is a 32-bit COM class in the interactive logon where
WinCC Runtime is running. 64-bit PowerShell reports the class as not registered
(`REGDB_E_CLASSNOTREG`). An SSH session is a different logon, so the class can
be registered and still fail from SSH. Run 32-bit PowerShell in the runtime's
session. A disconnected logon still counts. A one-shot scheduled task with
`/it` runs there:

```bat
C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe -NoProfile -ExecutionPolicy Bypass -File wincc_runtime_tags.ps1 -Name SomeTag -Name OtherTag
```

A name per line in a file works as `-List names.txt`. Lines starting with `#` are
comments. Output is TSV: name, value, quality, error. Exit 0 when every tag
read, 1 when the runtime answered but a tag did not, 2 when the COM class did not.

Quality is the OPC quality byte:

| Byte | Meaning here |
|---|---|
| 192 (`0xC0`) | good |
| 8 (`0x08`) | bad / not connected, seen in the archive decoder's source data |
| 4 (`0x04`) | bad configuration. Seen on a tag the HMI project names and the PLC does not serve. The value column is then not a measurement; a displayed 0 is the failed read |

The quality table is what was seen, not a catalogue of OPC quality codes.

Alarm configuration is not an alarm. `CC_Alg_AnalogVar` and `CC_Alg_AnalogLimit`
empty, and `MSMsgs` holding only a template, means the HMI has no limit alarm
for those tags. A tag can still be read. An archived alarm bit with no rows in
the open segment did not change during that segment; the live read is its
current value.

## Newest archive block

On the SQL instance WinCC is already using, print the query and let `sqlcmd`
write the file itself:

```text
python3 scripts/wincc_latest_block.py sql --database SEGMENT --id 171 --id 170 > query.sql
sqlcmd -S localhost\WINCC -E -y 0 -s "|" -i query.sql -o dump.txt
python3 scripts/wincc_latest_block.py check dump.txt
python3 scripts/wincc_binvalues.py dump.txt > tag.csv
```

`check` fails when the hex is shorter than the length column. That is a line
wrapped by a pipe into `Out-File` or by `sqlcmd -w`. `-y 0` and `-o` together
are the combination that kept a block intact. Do not add `-w`. Do not commit
the dump: it is plant data.

A tag listed in `Archive` with no `TagCompressed` rows in the open segment did
not change in that segment. It is not a reading of zero.
