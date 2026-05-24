# Terraform apply dev (PowerShell) — evita erro de parsing do .tfvars
param(
    [ValidateSet("plan", "apply", "destroy")]
    [string]$Action = "apply",
    [string]$Env = "dev"
)

$ErrorActionPreference = "Stop"
$InfraDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VarFile = Join-Path $InfraDir "inventories\$Env\terraform.tfvars"

if (-not (Test-Path $VarFile)) {
    Write-Error "Arquivo nao encontrado: $VarFile"
}

Set-Location $InfraDir

switch ($Action) {
    "plan" {
        terraform init -input=false
        terraform plan "-var-file=$VarFile"
    }
    "apply" {
        terraform init -input=false
        terraform apply "-var-file=$VarFile"
    }
    "destroy" {
        terraform init -input=false
        terraform destroy "-var-file=$VarFile"
    }
}
