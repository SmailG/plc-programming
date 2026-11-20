# Reading current WinCC 7 tags, and the newest archive block

Use this when a value the controller is acting on is not in the control gateway's
read list, and a WinCC 7 runtime on the same PLC already has the tag. Do not open
another OPC UA session to that PLC. Read the tag through the runtime that is
already subscribed, or read the archive that runtime is already writing.

Two different questions, two tools:

| Question | Tool | What a miss looks like |
|---|---|---|
| What is the tag right now, including one that is not archived? | `scripts/wincc_runtime_tags.ps1` | quality other than 128 or 192, or the error column |
| What did an archived tag do in its newest block? | `scripts/wincc_latest_block.py` then `scripts/wincc_binvalues.py`, one tag per file | `check` says the line was cut; no rows means no samples in that segment, not that the tag held still |

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
C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe -NoProfile -ExecutionPolicy Bypass -File wincc_runtime_tags.ps1 -List names.txt
```

One name per line. Lines starting with `#` are comments. Repeating `-Name` on
`powershell.exe -File` does not bind, so a list file is the multi-tag form.
Output is TSV: name, value, quality, error. Exit 0 when every tag reads good,
1 when the runtime answered but a tag threw or its quality is not good, 2 when
the list file or the COM class failed. A missing list file stops before the
runtime object is created.

Quality is the OPC quality byte:

| Byte | Meaning here |
|---|---|
| 192 (`0xC0`) | good. Returned by a live WinCC 7 runtime read |
| 128 (`0x80`) | good. The OK code named in the WinCC scripting manual. A read of either 128 or 192 exits 0 |
| 8 (`0x08`) | bad / not connected, seen in the archive decoder's source data |
| 4 (`0x04`) | bad configuration. Seen on a tag the HMI project names and the PLC does not serve. The value column is then not a measurement; a displayed 0 is the failed read, and the script exits 1 |

A tab or newline inside a text value is written as `\t` or `\n`, so the four columns stay four columns. A numeric value is unchanged.

The quality table is what was seen, not a catalogue of OPC quality codes.

Alarm configuration is not an alarm. `CC_Alg_AnalogVar` and `CC_Alg_AnalogLimit`
empty, and `MSMsgs` holding only a template, means the HMI has no limit alarm
for those tags. A tag can still be read. An archived alarm bit with no rows in
the open segment has no samples there. That is not proof the tag held still:
cyclic-selective recording can be stopped while the source changes. Check the
tag's recording mode and that acquisition is running before treating the
absence as stability. The live read is the current value.

## Newest archive block

On the SQL instance WinCC is already using, print the query and let `sqlcmd`
write the file itself:

```text
python3 scripts/wincc_latest_block.py sql --database SEGMENT --id 171 > query.sql
sqlcmd -S localhost\WINCC -E -y 0 -s "|" -i query.sql -o dump.txt
python3 scripts/wincc_latest_block.py check dump.txt
python3 scripts/wincc_binvalues.py dump.txt > tag.csv
```

One `--id` per dump. The decoder drops the first three columns, including
`ValueID`, and writes only `timestamp,value,quality`. A second id in the same
file would mix two series with no tag identity.

`check` fails when the hex is shorter than the length column. That is a line
wrapped by a pipe into `Out-File` or by `sqlcmd -w`. `-y 0` and `-o` together
are the combination that kept a block intact. Do not add `-w`. Do not commit
the dump: it is plant data.

A tag listed in `Archive` with no `TagCompressed` rows has no samples in that
segment. It is not a reading of zero, and it is not proof the tag held still.
Confirm the recording mode and that acquisition is running before saying so.
