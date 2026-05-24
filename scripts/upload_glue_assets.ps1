# Upload bundle flat para AWS Glue Python Shell
param(
    [string]$Bucket = "sample-data-dev",
    [string]$Region = "us-east-1"
)

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$ZipPath = Join-Path $env:TEMP "glue-libs.zip"
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }

Write-Host "==> Empacotando glue_bundle (flat)..."
Compress-Archive -Path "glue_bundle/train_pipeline.py","glue_bundle/preprocessor.py","glue_bundle/model.py","glue_bundle/catalog_sync.py","glue_bundle/incremental_data.py","glue_bundle/metrics_history.py" -DestinationPath $ZipPath -Force
aws s3 cp $ZipPath "s3://$Bucket/libs/app.zip" --region $Region

Write-Host "==> Enviando glue_train.py..."
aws s3 cp "glue_bundle/glue_train.py" "s3://$Bucket/scripts/glue_train.py" --region $Region

Write-Host "Concluido. Disparar: aws glue start-job-run --job-name saldo-previsto-glue-job-prod"
