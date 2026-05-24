{
  "Comment": "Pipeline genérico: validação Lambda -> processamento Glue",
  "StartAt": "AssignRunId",
  "States": {
    "AssignRunId": {
      "Type": "Pass",
      "Parameters": {
        "run_id.$": "$$.Execution.Name",
        "source_prefix.$": "$.source_prefix"
      },
      "Next": "ValidateInput"
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
          "--DYNAMODB_TABLE": "${dynamodb_table_name}"
        }
      },
      "ResultPath": "$.glue",
      "Next": "FinalizeRun"
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
          "glue.$": "$.glue"
        }
      },
      "End": true
    }
  }
}
