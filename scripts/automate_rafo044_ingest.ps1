# Automatiza ingestão Rafo044 (execute: .\scripts\automate_rafo044_ingest.ps1 -Mode init -Upload)
param(
    [ValidateSet("init", "tick", "loop")]
    [string]$Mode = "tick",
    [switch]$Upload,
    [switch]$TriggerSfn,
    [double]$IntervalMinutes = 3
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$argList = @("scripts/automate_rafo044_ingest.py")
switch ($Mode) {
    "init" { $argList += "--init" }
    "tick" { $argList += "--tick" }
    "loop" {
        $argList += "--loop"
        $argList += "--interval-minutes"
        $argList += "$IntervalMinutes"
    }
}
if ($Upload) { $argList += "--upload" }
if ($TriggerSfn) { $argList += "--trigger-sfn" }

python @argList
