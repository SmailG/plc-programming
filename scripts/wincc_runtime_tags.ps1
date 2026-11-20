# Read current WinCC Runtime tag values. ASCII only.
#
# WinCC 7's HMIRuntime COM class is 32-bit and lives in the interactive logon
# where the runtime is running. A 64-bit PowerShell reports the class as not
# registered. An SSH session is not that logon: start this with 32-bit
# powershell from a one-shot task in the logged-on session
# (schtasks /it), or from the runtime's own desktop.
#
#   C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe -NoProfile -ExecutionPolicy Bypass -File wincc_runtime_tags.ps1 -List names.txt
#
# One name per line in the list file. A single name can also be passed as
# -Name SomeTag. Repeating -Name on powershell.exe -File does not bind.
#
# Output is one TSV line per tag: name, value, quality, error.
# Quality is the OPC quality byte. 192 (0xC0) is good. Any other known quality,
# including 4, is a failed read: the value column is not a measurement.
# Exit 0 every tag read good, 1 a tag threw or its quality is not good,
# 2 the list file or the runtime COM class failed.
param(
    [string[]]$Name,
    [string]$List
)

$ErrorActionPreference = 'Continue'
$names = New-Object System.Collections.Generic.List[string]
if ($List) {
    try {
        $listLines = Get-Content -Path $List -ErrorAction Stop
    } catch {
        Write-Error ("list not read: " + $_.Exception.Message)
        exit 2
    }
    foreach ($line in $listLines) {
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
        $lastError = ''
        $errorText = ''
        try { $quality = [string]$tag.QualityCode } catch { $quality = '' }
        try { $lastError = [string]$tag.LastError } catch { $lastError = '' }
        try { $errorText = [string]$tag.ErrorDescription } catch { $errorText = '' }
        $qualityNumber = 0
        $qualityKnown = [int]::TryParse($quality, [ref]$qualityNumber)
        $good = $qualityKnown -and (($qualityNumber -band 192) -eq 192)
        if ($good -and ($lastError -eq '' -or $lastError -eq '0') -and $errorText -eq '') {
            Write-Output ("{0}`t{1}`t{2}`t" -f $tagName, $value, $quality)
        } else {
            $failed = $failed + 1
            $parts = @()
            if (-not $good) { $parts += ("quality=" + $quality) }
            if ($lastError -ne '' -and $lastError -ne '0') { $parts += ("LastError=" + $lastError) }
            if ($errorText -ne '') { $parts += $errorText }
            $message = ($parts -join '; ') -replace "`t", ' ' -replace "`r|`n", ' '
            Write-Output ("{0}`t{1}`t{2}`t{3}" -f $tagName, $value, $quality, $message)
        }
    } catch {
        $failed = $failed + 1
        $message = $_.Exception.Message -replace "`t", ' ' -replace "`r|`n", ' '
        Write-Output ("{0}`t`t`t{1}" -f $tagName, $message)
    }
}
if ($failed -gt 0) { exit 1 }
exit 0
