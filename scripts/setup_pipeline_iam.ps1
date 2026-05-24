# Cria IAM roles para pipeline saldo-previsto (SFN + Lambda)
param(
    [string]$AccountId = "303238378103",
    [string]$Region = "us-east-1",
    [string]$Project = "saldo-previsto",
    [string]$Env = "prod"
)

$ErrorActionPreference = "Stop"
$GlueJob = "$Project-glue-job-$Env"
$LambdaFn = "$Project-lambda-$Env"
$SfnName = "$Project-sfn-$Env"
$Table = "$Project-results-$Env"
$Bucket = "$Project-data-$Env"
$ScheduleRule = "$Project-schedule-$Env"

function Ensure-Role {
    param([string]$Name, [string]$TrustJson, [string]$PolicyJson)
    aws iam get-role --role-name $Name 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        aws iam create-role --role-name $Name --assume-role-policy-document $TrustJson | Out-Null
        Write-Host "Role criada: $Name"
    } else {
        Write-Host "Role existe: $Name"
    }
    aws iam put-role-policy --role-name $Name --policy-name "$Name-inline" --policy-document $PolicyJson | Out-Null
}

$sfnTrust = '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":["states.amazonaws.com","events.amazonaws.com"]},"Action":"sts:AssumeRole"}]}'

$sfnPolicy = @"
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["lambda:InvokeFunction"],
      "Resource": "arn:aws:lambda:${Region}:${AccountId}:function:${LambdaFn}"
    },
    {
      "Effect": "Allow",
      "Action": [
        "glue:StartJobRun", "glue:GetJobRun", "glue:GetJobRuns", "glue:BatchStopJobRun"
      ],
      "Resource": [
        "arn:aws:glue:${Region}:${AccountId}:job/${GlueJob}",
        "arn:aws:glue:${Region}:${AccountId}:catalog",
        "arn:aws:glue:${Region}:${AccountId}:database/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "arn:aws:iam::${AccountId}:role/${Project}-glue-role-${Env}",
      "Condition": {
        "StringEquals": { "iam:PassedToService": "glue.amazonaws.com" }
      }
    },
    {
      "Effect": "Allow",
      "Action": "states:StartExecution",
      "Resource": "arn:aws:states:${Region}:${AccountId}:stateMachine:${SfnName}"
    },
    {
      "Effect": "Allow",
      "Action": ["events:PutTargets", "events:PutRule", "events:DescribeRule"],
      "Resource": "arn:aws:events:${Region}:${AccountId}:rule/${ScheduleRule}"
    }
  ]
}
"@

$lambdaTrust = '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

$lambdaPolicy = @"
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
      "Resource": "arn:aws:logs:${Region}:${AccountId}:*"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:ListBucket", "s3:GetObject"],
      "Resource": [
        "arn:aws:s3:::${Bucket}",
        "arn:aws:s3:::${Bucket}/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem"],
      "Resource": "arn:aws:dynamodb:${Region}:${AccountId}:table/${Table}"
    }
  ]
}
"@

Ensure-Role -Name "$Project-sfn-role-$Env" -TrustJson $sfnTrust -PolicyJson $sfnPolicy
Ensure-Role -Name "$Project-lambda-role-$Env" -TrustJson $lambdaTrust -PolicyJson $lambdaPolicy

Write-Host "IAM pronto."
