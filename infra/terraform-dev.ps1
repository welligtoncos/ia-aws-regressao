# Terraform dev — rode a partir da pasta infra/
param(
    [ValidateSet("plan", "apply", "destroy")]
    [string]$Action = "apply",
    [string]$Env = "dev"
)

$ErrorActionPreference = "Stop"
$InfraDir = $PSScriptRoot
$VarFile = Join-Path $InfraDir "inventories\$Env\terraform.tfvars"

if (-not (Test-Path $VarFile)) {
    Write-Error "Arquivo nao encontrado: $VarFile"
}

Set-Location $InfraDir

terraform init -input=false

switch ($Action) {
    "plan"    { terraform plan "-var-file=$VarFile" }
    "apply"   { terraform apply "-var-file=$VarFile" }
    "destroy" { terraform destroy "-var-file=$VarFile" }
}
