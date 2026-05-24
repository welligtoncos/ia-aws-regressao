# Upload bundle flat para AWS Glue Python Shell
param(
    [string]$Bucket = "saldo-previsto-data-prod",
    [string]$Region = "us-east-1"
)

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$ZipPath = Join-Path $env:TEMP "glue-libs.zip"
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }

Write-Host "==> Empacotando glue_bundle (flat)..."
$bundleFiles = Get-ChildItem "glue_bundle\*.py" | Where-Object { $_.Name -ne "glue_train.py" }
if (-not $bundleFiles) { throw "Nenhum arquivo em glue_bundle/" }
Compress-Archive -Path $bundleFiles.FullName -DestinationPath $ZipPath -Force
aws s3 cp $ZipPath "s3://$Bucket/libs/app.zip" --region $Region

Write-Host "==> Enviando glue_train.py..."
aws s3 cp "glue_bundle/glue_train.py" "s3://$Bucket/scripts/glue_train.py" --region $Region

Write-Host "Concluido: s3://$Bucket/libs/app.zip"
Write-Host "Disparar: aws glue start-job-run --job-name saldo-previsto-glue-job-prod --region $Region"
