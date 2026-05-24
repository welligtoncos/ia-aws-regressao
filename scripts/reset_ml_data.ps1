# Reset completo + carga Rafo044 inicial
# Uso: .\scripts\reset_ml_data.ps1
param(
    [switch]$PurgeDynamoDb,
    [int]$Customers = 2000
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$args = @("scripts/reset_ml_data.py", "--yes", "--seed-rafo044", "--upload", "--customers", "$Customers")
if ($PurgeDynamoDb) { $args += "--purge-dynamodb" }

python @args
