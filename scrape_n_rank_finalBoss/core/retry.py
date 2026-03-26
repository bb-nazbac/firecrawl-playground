"""
Exponential Backoff Retry Logic (API-Agnostic)

Implements retry patterns for any HTTP API:
- Exponential backoff: delay = min(MAX_DELAY, INITIAL_DELAY * BACKOFF_FACTOR^attempt)
- Error classification for rate limits, timeouts, connection errors, HTTP 5xx
- Configurable max retries and delays
- Works with requests exceptions and generic Exception types
"""

import time
import functools
import threading
from typing import Tuple, Type, Callable, Optional, Any

import requests


# =====================================================================
# CONFIGURATION
# =====================================================================

MAX_RETRIES = 7
INITIAL_DELAY = 0.1  # seconds
MAX_DELAY = 3.0  # seconds
BACKOFF_FACTOR = 2.0

# Retryable exceptions (requests-based, API-agnostic)
RETRYABLE_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    requests.exceptions.Timeout,
    requests.exceptions.ConnectionError,
    requests.exceptions.ChunkedEncodingError,
    ConnectionError,
    TimeoutError,
)


# =====================================================================
# ERROR CLASSIFICATION
# =====================================================================

def classify_error(error: Exception, response=None) -> Tuple[str, bool]:
    """
    Classify an error and determine if it's retryable.

    Args:
        error: The exception that occurred
        response: Optional HTTP response object (requests.Response)

    Returns:
        Tuple of (error_type: str, is_retryable: bool)
    """
    error_str = str(error).lower()

    # Timeout errors
    if isinstance(error, (requests.exceptions.Timeout, TimeoutError)):
        return 'timeout', True
    if 'timeout' in error_str or 'timed out' in error_str:
        return 'timeout', True

    # Connection errors
    if isinstance(error, (requests.exceptions.ConnectionError, ConnectionError)):
        return 'connection_error', True
    if 'connection' in error_str:
        return 'connection_error', True

    # Rate limit from response
    if response is not None:
        status = getattr(response, 'status_code', None)
        if status == 429:
            return 'rate_limit', True
        if status is not None and 500 <= status < 600:
            return f'http_{status}', True
        if status is not None and 400 <= status < 500:
            return f'http_{status}', False

    # Rate limit from error string
    if '429' in error_str or 'rate limit' in error_str or 'rate_limit' in error_str:
        return 'rate_limit', True

    # Server errors from error string
    if '502' in error_str or '503' in error_str or '500' in error_str:
        return 'server_error', True
    if 'overloaded' in error_str or 'overload' in error_str:
        return 'overloaded', True

    # Chunked encoding (network interruption)
    if isinstance(error, requests.exceptions.ChunkedEncodingError):
        return 'connection_error', True

    return 'unknown', True


# =====================================================================
# DELAY CALCULATION
# =====================================================================

def calculate_retry_delay(attempt: int) -> float:
    """
    Calculate delay for retry with exponential backoff.

    Args:
        attempt: Zero-based attempt number (0 = first retry)

    Returns:
        Delay in seconds, capped at MAX_DELAY
    """
    delay = INITIAL_DELAY * (BACKOFF_FACTOR ** attempt)
    return min(delay, MAX_DELAY)


# =====================================================================
# RETRY DECORATOR
# =====================================================================

def retry_with_backoff(
    max_retries: int = MAX_RETRIES,
    initial_delay: float = INITIAL_DELAY,
    max_delay: float = MAX_DELAY,
    backoff_factor: float = BACKOFF_FACTOR,
    retryable_exceptions: Tuple[Type[Exception], ...] = RETRYABLE_EXCEPTIONS,
    on_retry: Optional[Callable[[int, Exception, float], None]] = None
):
    """
    Decorator for exponential backoff retry.

    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay cap in seconds
        backoff_factor: Multiplier for each retry (typically 2.0)
        retryable_exceptions: Tuple of exception types to retry on
        on_retry: Optional callback(attempt, exception, delay) called before each retry

    Usage:
        @retry_with_backoff()
        def call_api():
            return requests.post(...)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)

                except retryable_exceptions as e:
                    last_exception = e

                    # Last attempt - don't retry, raise
                    if attempt == max_retries - 1:
                        raise

                    # Calculate delay with exponential backoff
                    delay = min(max_delay, initial_delay * (backoff_factor ** attempt))

                    # Call retry callback if provided
                    if on_retry:
                        on_retry(attempt + 1, e, delay)

                    time.sleep(delay)

            # Should not reach here, but just in case
            if last_exception:
                raise last_exception

        return wrapper
    return decorator


# =====================================================================
# FUNCTIONAL RETRY HELPER
# =====================================================================

def call_with_retry(
    func: Callable,
    *args,
    max_retries: int = MAX_RETRIES,
    initial_delay: float = INITIAL_DELAY,
    max_delay: float = MAX_DELAY,
    backoff_factor: float = BACKOFF_FACTOR,
    retryable_exceptions: Tuple[Type[Exception], ...] = RETRYABLE_EXCEPTIONS,
    logger=None,
    context: str = "",
    **kwargs
) -> Any:
    """
    Call a function with exponential backoff retry.

    Args:
        func: Function to call
        *args: Positional arguments for func
        max_retries: Maximum retry attempts
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay cap
        backoff_factor: Backoff multiplier
        retryable_exceptions: Exception types to retry on
        logger: Optional logger with .log(msg, level) or .warning(msg) method
        context: Optional context string for log messages
        **kwargs: Keyword arguments for func

    Returns:
        Result of func(*args, **kwargs)

    Raises:
        Last exception if all retries exhausted
    """
    last_exception = None

    def _log(msg, level="WARN"):
        if logger is None:
            return
        if hasattr(logger, 'log'):
            logger.log(msg, level)
        elif hasattr(logger, 'warning') and level == "WARN":
            logger.warning(msg)
        elif hasattr(logger, 'error') and level == "ERROR":
            logger.error(msg)

    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)

        except retryable_exceptions as e:
            last_exception = e

            # Last attempt - don't retry
            if attempt == max_retries - 1:
                _log(
                    f"FAILED after {max_retries} attempts: {type(e).__name__}: {e} [{context}]",
                    "ERROR"
                )
                raise

            # Calculate delay
            delay = min(max_delay, initial_delay * (backoff_factor ** attempt))

            # Log retry
            _log(
                f"Retry {attempt + 1}/{max_retries} in {delay:.1f}s: "
                f"{type(e).__name__} [{context}]",
                "WARN"
            )

            time.sleep(delay)

        except Exception as e:
            # For non-listed exceptions, classify to check if retryable
            error_type, is_retryable = classify_error(e)
            last_exception = e

            if is_retryable and attempt < max_retries - 1:
                delay = min(max_delay, initial_delay * (backoff_factor ** attempt))
                _log(
                    f"Retry {attempt + 1}/{max_retries} in {delay:.1f}s: "
                    f"{type(e).__name__} ({error_type}) [{context}]",
                    "WARN"
                )
                time.sleep(delay)
                continue

            if attempt == max_retries - 1:
                _log(
                    f"FAILED after {max_retries} attempts: {type(e).__name__}: {e} [{context}]",
                    "ERROR"
                )
            raise

    # Should not reach here
    if last_exception:
        raise last_exception


# =====================================================================
# RETRY STATISTICS
# =====================================================================

class RetryStats:
    """Track retry statistics across multiple calls. Thread-safe."""

    def __init__(self):
        self._lock = threading.Lock()
        self.total_calls = 0
        self.total_retries = 0
        self.calls_with_retries = 0
        self.max_retries_per_call = 0
        self.total_retry_delay = 0.0
        self.errors_by_type = {}

    def record_success(self, attempts: int, total_delay: float = 0.0):
        """
        Record a successful call.

        Args:
            attempts: Total number of attempts (1 = no retries)
            total_delay: Total time spent waiting on retries
        """
        with self._lock:
            self.total_calls += 1
            if attempts > 1:
                retries = attempts - 1
                self.total_retries += retries
                self.calls_with_retries += 1
                self.max_retries_per_call = max(self.max_retries_per_call, retries)
                self.total_retry_delay += total_delay

    def record_error(self, error_type: str):
        """
        Record a final failure (all retries exhausted).

        Args:
            error_type: Classification of the error
        """
        with self._lock:
            self.errors_by_type[error_type] = self.errors_by_type.get(error_type, 0) + 1

    def get_summary(self) -> dict:
        """Get statistics summary."""
        with self._lock:
            return {
                "total_calls": self.total_calls,
                "total_retries": self.total_retries,
                "calls_with_retries": self.calls_with_retries,
                "max_retries_per_call": self.max_retries_per_call,
                "avg_retries_per_call": (
                    self.total_retries / self.total_calls if self.total_calls > 0 else 0
                ),
                "total_retry_delay_seconds": round(self.total_retry_delay, 2),
                "errors_by_type": dict(self.errors_by_type),
            }

    def reset(self):
        """Reset all statistics."""
        with self._lock:
            self.total_calls = 0
            self.total_retries = 0
            self.calls_with_retries = 0
            self.max_retries_per_call = 0
            self.total_retry_delay = 0.0
            self.errors_by_type = {}
