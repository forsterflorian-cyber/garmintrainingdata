from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Mapping


class ErrorCategory(str, Enum):
    AUTH = "AUTH"
    API = "API"
    DB = "DB"
    VALIDATION = "VALIDATION"
    NETWORK = "NETWORK"
    SYNC = "SYNC"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        structured = getattr(record, "structured", None)
        if isinstance(structured, Mapping):
            payload.update(structured)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=True)


def configure_structured_logging(logger: logging.Logger) -> logging.Logger:
    if getattr(logger, "_structured_logging_ready", False):
        return logger

    logger.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger._structured_logging_ready = True  # type: ignore[attr-defined]
    return logger


def get_logger(name: str) -> logging.Logger:
    return configure_structured_logging(logging.getLogger(name))


def log_event(
    logger: logging.Logger,
    level: int,
    *,
    category: ErrorCategory,
    event: str,
    message: str,
    **context: Any,
) -> None:
    logger.log(
        level,
        message,
        extra={
            "structured": {
                "category": category.value,
                "event": event,
                **context,
            }
        },
    )


def log_exception(
    logger: logging.Logger,
    *,
    category: ErrorCategory,
    event: str,
    message: str,
    exc: BaseException,
    level: int = logging.ERROR,
    **context: Any,
) -> None:
    logger.log(
        level,
        message,
        exc_info=(type(exc), exc, exc.__traceback__),
        extra={
            "structured": {
                "category": category.value,
                "event": event,
                **context,
            }
        },
    )


@dataclass
class ServiceError(Exception):
    public_message: str
    status_code: int = 500
    category: ErrorCategory = ErrorCategory.API
    event: str = "service_error"
    context: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.public_message
