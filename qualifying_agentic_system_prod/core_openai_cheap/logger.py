"""
Logging Module for Qualifying Agentic System (OpenAI Version)

Provides structured logging to files for debugging API calls and parse failures.
"""

import os
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any


class PipelineLogger:
    """
    Thread-safe logger that writes to domain-specific log files.

    Creates logs in: {output_dir}/logs/{domain}.log
    """

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.logs_dir = self.output_dir / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

        # Also create a master log
        self.master_log = self.logs_dir / "pipeline.log"

    def _timestamp(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    def _get_domain_log(self, domain: str) -> Path:
        """Get path to domain-specific log file."""
        safe_domain = domain.replace("/", "_").replace(":", "_")
        return self.logs_dir / f"{safe_domain}.log"

    def _write(self, filepath: Path, message: str):
        """Thread-safe write to file."""
        with self.lock:
            with open(filepath, 'a', encoding='utf-8') as f:
                f.write(message + "\n")

    def log_api_request(
        self,
        domain: str,
        request_type: str,  # "filter", "qualification", "page_selection", "requalify"
        prompt: str,
        model: str
    ):
        """Log an outgoing API request."""
        log_file = self._get_domain_log(domain)

        msg = f"""
{'='*80}
[{self._timestamp()}] API REQUEST: {request_type.upper()}
{'='*80}
Domain: {domain}
Model: {model}
Prompt Length: {len(prompt)} chars

--- PROMPT START ---
{prompt[:2000]}{'...[TRUNCATED]' if len(prompt) > 2000 else ''}
--- PROMPT END ---
"""
        self._write(log_file, msg)
        self._write(self.master_log, f"[{self._timestamp()}] [{domain}] API REQUEST: {request_type}")

    def log_api_response(
        self,
        domain: str,
        request_type: str,
        success: bool,
        response_text: str,
        input_tokens: int,
        output_tokens: int,
        error: Optional[str] = None,
        duration_ms: Optional[int] = None
    ):
        """Log an API response."""
        log_file = self._get_domain_log(domain)

        status = "SUCCESS" if success else "FAILED"
        msg = f"""
[{self._timestamp()}] API RESPONSE: {request_type.upper()} - {status}
Tokens: {input_tokens} in / {output_tokens} out
Duration: {duration_ms}ms
Error: {error or 'None'}

--- RESPONSE START ---
{response_text}
--- RESPONSE END ---
"""
        self._write(log_file, msg)
        self._write(self.master_log, f"[{self._timestamp()}] [{domain}] API RESPONSE: {request_type} - {status}")

    def log_parse_failure(
        self,
        domain: str,
        request_type: str,
        raw_response: str,
        parse_error: Optional[str] = None
    ):
        """Log a parse failure with full response for debugging."""
        log_file = self._get_domain_log(domain)

        msg = f"""
{'!'*80}
[{self._timestamp()}] PARSE FAILURE: {request_type.upper()}
{'!'*80}
Domain: {domain}
Parse Error: {parse_error or 'Unknown'}
Response Length: {len(raw_response)} chars

--- FULL RAW RESPONSE ---
{raw_response}
--- END RAW RESPONSE ---
{'!'*80}
"""
        self._write(log_file, msg)
        self._write(self.master_log, f"[{self._timestamp()}] [{domain}] PARSE FAILURE: {request_type}")

        # Also write to a dedicated parse_failures.log for easy review
        failures_log = self.logs_dir / "parse_failures.log"
        self._write(failures_log, msg)

    def log_parse_success(
        self,
        domain: str,
        request_type: str,
        parsed_data: Dict[str, Any]
    ):
        """Log successful parse with extracted data."""
        log_file = self._get_domain_log(domain)

        msg = f"""
[{self._timestamp()}] PARSE SUCCESS: {request_type.upper()}
Parsed Data: {json.dumps(parsed_data, indent=2, default=str)[:1000]}
"""
        self._write(log_file, msg)

    def log_event(
        self,
        domain: str,
        event_type: str,
        message: str,
        data: Optional[Dict] = None
    ):
        """Log a general event."""
        log_file = self._get_domain_log(domain)

        msg = f"[{self._timestamp()}] {event_type}: {message}"
        if data:
            msg += f"\n  Data: {json.dumps(data, default=str)[:500]}"

        self._write(log_file, msg)

    def log_scrape(
        self,
        domain: str,
        url: str,
        success: bool,
        content_length: int = 0,
        error: Optional[str] = None
    ):
        """Log a scrape operation."""
        log_file = self._get_domain_log(domain)

        status = "SUCCESS" if success else "FAILED"
        msg = f"[{self._timestamp()}] SCRAPE {status}: {url} ({content_length} chars)"
        if error:
            msg += f"\n  Error: {error}"

        self._write(log_file, msg)


# Global logger instance (will be set by pipeline)
_logger: Optional[PipelineLogger] = None


def init_logger(output_dir: Path) -> PipelineLogger:
    """Initialize the global logger."""
    global _logger
    _logger = PipelineLogger(output_dir)
    return _logger


def get_logger() -> Optional[PipelineLogger]:
    """Get the global logger instance."""
    return _logger
