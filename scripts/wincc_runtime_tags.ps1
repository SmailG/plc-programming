# Read current WinCC Runtime tag values. ASCII only.
#
# WinCC 7's HMIRuntime COM class is 32-bit and lives in the interactive logon
# where the runtime is running. A 64-bit PowerShell reports the class as not
# registered. An SSH session is not that logon: start this with 32-bit
# powershell from a one-shot task in the logged-on session
# (schtasks /it), or from the runtime's own desktop.
#
#   C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe -NoProfile -ExecutionPolicy Bypass -File wincc_runtime_tags.ps1 -Name TagA -Name TagB
#   ... -List names.txt
#
# Output is one TSV line per tag: name, value, quality, error.
# Quality is the OPC quality byte (192 good). Quality 4 was seen for a tag
# whose source node is not served; that row is a bad read, not a value of 0.
# Exit 0 every tag read, 1 runtime up but a tag failed, 2 runtime COM failed.
param(
    [string[]]$Name,
    [string]$List
)

$ErrorActionPreference = 'Continue'
$names = New-Object System.Collections.Generic.List[string]
if ($List) {
    foreach ($line in Get-Content -Path $List) {
        $trimmed = $line.Trim()
        if ($trimmed.Length -gt 0 -and -not $trimmed.StartsWith('#')) {
            $names.Add($trimmed)
        }
    }
}
if ($Name) {
    foreach ($one in $Name) { $names.Add($one) }
}
if ($names.Count -eq 0) {
    Write-Error 'pass -Name or -List'
    exit 2
}

try {
    $runtime = New-Object -ComObject CCHMIRuntime.HMIRuntime
} catch {
    Write-Error ("runtime COM failed: " + $_.Exception.Message)
    exit 2
}

$failed = 0
foreach ($tagName in $names) {
    try {
        $tag = $runtime.Tags.Item($tagName)
        $value = $tag.Read()
        $quality = ''
        try { $quality = [string]$tag.QualityCode } catch { $quality = '' }
        Write-Output ("{0}`t{1}`t{2}`t" -f $tagName, $value, $quality)
    } catch {
        $failed = $failed + 1
        $message = $_.Exception.Message -replace "`t", ' ' -replace "`r|`n", ' '
        Write-Output ("{0}`t`t`t{1}" -f $tagName, $message)
    }
}
if ($failed -gt 0) { exit 1 }
exit 0
