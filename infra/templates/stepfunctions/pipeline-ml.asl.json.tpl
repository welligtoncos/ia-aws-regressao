{
  "Comment": "Pipeline ML: checa dados novos -> valida -> Glue -> finaliza",
  "StartAt": "CheckNewData",
  "States": {
    "CheckNewData": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${lambda_function_name}",
        "Payload": {
          "action": "check_new_data",
          "run_id.$": "$.run_id",
          "source_prefix.$": "$.source_prefix"
        }
      },
      "ResultSelector": {
        "parsed.$": "States.StringToJson($.Payload.body)"
      },
      "ResultPath": "$.check",
      "Next": "HasNewData"
    },
    "HasNewData": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.check.parsed.has_new_data",
          "BooleanEquals": true,
          "Next": "ValidateInput"
        }
      ],
      "Default": "SkipNoNewData"
    },
    "SkipNoNewData": {
      "Type": "Succeed",
      "Comment": "Sem arquivos novos em incoming/ nem lote simulado pendente"
    },
    "ValidateInput": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${lambda_function_name}",
        "Payload": {
          "action": "validate",
          "run_id.$": "$.run_id",
          "source_prefix.$": "$.source_prefix"
        }
      },
      "ResultPath": "$.validation",
      "Next": "RunGlueJob"
    },
    "RunGlueJob": {
      "Type": "Task",
      "Resource": "arn:aws:states:::glue:startJobRun.sync",
      "Parameters": {
        "JobName": "${glue_job_name}",
        "Arguments": {
          "--run_id.$": "$.run_id",
          "--DYNAMODB_TABLE": "${dynamodb_table_name}",
          "--INCOMING_KEYS.$": "States.JsonToString($.check.parsed.new_file_keys)"
        }
      },
      "ResultPath": "$.glue",
      "Next": "FinalizeRun",
      "Catch": [
        {
          "ErrorEquals": ["Glue.ConcurrentRunsExceededException"],
          "ResultPath": "$.glue_error",
          "Next": "SkipGlueBusy"
        }
      ]
    },
    "SkipGlueBusy": {
      "Type": "Succeed",
      "Comment": "Glue ocupado (MaxConcurrentRuns=1); retentar no próximo ciclo"
    },
    "FinalizeRun": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${lambda_function_name}",
        "Payload": {
          "action": "finalize",
          "run_id.$": "$.run_id",
          "validation.$": "$.validation",
          "glue.$": "$.glue",
          "check.$": "$.check"
        }
      },
      "End": true
    }
  }
}
