# Experimento completo Rafo044: todos os lotes + treino + relatório
param(
    [switch]$ForceInit,
    [int]$Customers = 2000
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$args = @(
    "scripts/run_rafo044_experiment.py",
    "--run-all",
    "--upload",
    "--wait-glue",
    "--max-customers", "$Customers"
)
if ($ForceInit) { $args += "--force-init" }

python @args
