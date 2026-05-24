"""Utilitários compartilhados para jobs AWS Glue."""

import json
import logging
import sys
from typing import Any, Dict, Optional

from awsglue.utils import getResolvedOptions


def get_job_parameters(required_keys: list, optional_keys: Optional[list] = None) -> Dict[str, str]:
    """Lê parâmetros do Glue Job a partir dos argumentos de execução."""
    optional_keys = optional_keys or []
    all_keys = required_keys + optional_keys

    if "--JOB_NAME" in sys.argv:
        return getResolvedOptions(sys.argv, all_keys)

    return {key: f"local-{key.lower()}" for key in all_keys}


def get_structured_logger(name: str = "aws-workload") -> logging.Logger:
    """Configura logger estruturado em JSON para CloudWatch."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredJsonFormatter())
        logger.addHandler(handler)

    return logger


class StructuredJsonFormatter(logging.Formatter):
    """Formata logs como JSON estruturado."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


def log_job_context(logger: logging.Logger, context: Dict[str, Any]) -> None:
    """Registra contexto inicial do job."""
    logger.info("Starting job", extra={"context": context})
