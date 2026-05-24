# Empacota handler Lambda (workloads) para deploy no S3
param(
    [string]$Bucket = "saldo-previsto-data-prod",
    [string]$Key = "builds/handler.zip",
    [string]$Region = "us-east-1",
    [switch]$Upload
)

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$BuildDir = Join-Path $env:TEMP "lambda-build-saldo"
$ZipPath = Join-Path $env:TEMP "handler.zip"

if (Test-Path $BuildDir) { Remove-Item $BuildDir -Recurse -Force }
New-Item -ItemType Directory -Path "$BuildDir\workloads" -Force | Out-Null

Copy-Item "$Root\workloads\aws_lambda\src\handler.py" $BuildDir
Copy-Item "$Root\workloads\shared" "$BuildDir\workloads\shared" -Recurse

if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path "$BuildDir\*" -DestinationPath $ZipPath -Force

Write-Host "Pacote: $ZipPath"

if ($Upload) {
    aws s3 cp $ZipPath "s3://$Bucket/$Key" --region $Region
    Write-Host "Enviado para s3://$Bucket/$Key"
}
