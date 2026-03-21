"""
Retry utilities with exponential backoff for resilient operations.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import time
from typing import Any, Callable, Optional, Type, Tuple

from observability import ErrorCategory, get_logger, log_event

LOGGER = get_logger(__name__)


class RetryConfig:
    """Configuration for retry behavior."""
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.retryable_exceptions = retryable_exceptions


def calculate_delay(attempt: int, config: RetryConfig) -> float:
    """Calculate delay with exponential backoff and optional jitter."""
    delay = config.base_delay * (config.exponential_base ** attempt)
    delay = min(delay, config.max_delay)
    
    if config.jitter:
        import random
        delay = delay * (0.5 + random.random())
    
    return delay


def retry_with_backoff(
    config: Optional[RetryConfig] = None,
    on_retry: Optional[Callable[[int, Exception, float], None]] = None,
):
    """
    Decorator for retrying functions with exponential backoff.
    
    Args:
        config: Retry configuration. Uses defaults if not provided.
        on_retry: Optional callback called on each retry attempt.
                 Signature: (attempt, exception, delay)
    """
    if config is None:
        config = RetryConfig()
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(config.max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except config.retryable_exceptions as exc:
                    last_exception = exc
                    
                    if attempt == config.max_retries:
                        log_event(
                            LOGGER,
                            logging.ERROR,
                            category=ErrorCategory.SYNC,
                            event="retry.max_retries_exceeded",
                            message=f"Max retries ({config.max_retries}) exceeded for {func.__name__}",
                            function=func.__name__,
                            attempt=attempt,
                            error=str(exc),
                        )
                        raise
                    
                    delay = calculate_delay(attempt, config)
                    
                    log_event(
                        LOGGER,
                        logging.WARNING,
                        category=ErrorCategory.SYNC,
                        event="retry.attempt",
                        message=f"Retry attempt {attempt + 1} for {func.__name__}",
                        function=func.__name__,
                        attempt=attempt + 1,
                        delay=delay,
                        error=str(exc),
                    )
                    
                    if on_retry:
                        try:
                            on_retry(attempt, exc, delay)
                        except Exception as callback_exc:
                            log_event(
                                LOGGER,
                                logging.WARNING,
                                category=ErrorCategory.SYNC,
                                event="retry.callback_failed",
                                message="Retry callback failed",
                                function=func.__name__,
                                error=str(callback_exc),
                            )
                    
                    time.sleep(delay)
            
            raise last_exception
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(config.max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except config.retryable_exceptions as exc:
                    last_exception = exc
                    
                    if attempt == config.max_retries:
                        log_event(
                            LOGGER,
                            logging.ERROR,
                            category=ErrorCategory.SYNC,
                            event="retry.max_retries_exceeded",
                            message=f"Max retries ({config.max_retries}) exceeded for {func.__name__}",
                            function=func.__name__,
                            attempt=attempt,
                            error=str(exc),
                        )
                        raise
                    
                    delay = calculate_delay(attempt, config)
                    
                    log_event(
                        LOGGER,
                        logging.WARNING,
                        category=ErrorCategory.SYNC,
                        event="retry.attempt",
                        message=f"Retry attempt {attempt + 1} for {func.__name__}",
                        function=func.__name__,
                        attempt=attempt + 1,
                        delay=delay,
                        error=str(exc),
                    )
                    
                    if on_retry:
                        try:
                            on_retry(attempt, exc, delay)
                        except Exception as callback_exc:
                            log_event(
                                LOGGER,
                                logging.WARNING,
                                category=ErrorCategory.SYNC,
                                event="retry.callback_failed",
                                message="Retry callback failed",
                                function=func.__name__,
                                error=str(callback_exc),
                            )
                    
                    await asyncio.sleep(delay)
            
            raise last_exception
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


class RetryableOperation:
    """
    Context manager for retryable operations with state tracking.
    """
    
    def __init__(
        self,
        operation_name: str,
        config: Optional[RetryConfig] = None,
        user_id: Optional[str] = None,
    ):
        self.operation_name = operation_name
        self.config = config or RetryConfig()
        self.user_id = user_id
        self.attempt = 0
        self.last_exception: Optional[Exception] = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val is None:
            return False
        
        if not isinstance(exc_val, self.config.retryable_exceptions):
            return False
        
        self.last_exception = exc_val
        self.attempt += 1
        
        if self.attempt > self.config.max_retries:
            log_event(
                LOGGER,
                logging.ERROR,
                category=ErrorCategory.SYNC,
                event="retry.operation_max_retries",
                message=f"Max retries exceeded for operation {self.operation_name}",
                operation=self.operation_name,
                user_id=self.user_id,
                attempt=self.attempt,
                error=str(exc_val),
            )
            return False
        
        delay = calculate_delay(self.attempt - 1, self.config)
        
        log_event(
            LOGGER,
            logging.WARNING,
            category=ErrorCategory.SYNC,
            event="retry.operation_attempt",
            message=f"Retrying operation {self.operation_name}",
            operation=self.operation_name,
            user_id=self.user_id,
            attempt=self.attempt,
            delay=delay,
            error=str(exc_val),
        )
        
        time.sleep(delay)
        return True  # Suppress the exception and retry


def create_sync_retry_config() -> RetryConfig:
    """Create retry configuration optimized for sync operations."""
    return RetryConfig(
        max_retries=3,
        base_delay=1.0,
        max_delay=30.0,
        exponential_base=2.0,
        jitter=True,
        retryable_exceptions=(
            ConnectionError,
            TimeoutError,
            OSError,
        ),
    )


def create_database_retry_config() -> RetryConfig:
    """Create retry configuration optimized for database operations."""
    return RetryConfig(
        max_retries=2,
        base_delay=0.5,
        max_delay=5.0,
        exponential_base=2.0,
        jitter=True,
        retryable_exceptions=(
            ConnectionError,
            TimeoutError,
            OSError,
        ),
    )