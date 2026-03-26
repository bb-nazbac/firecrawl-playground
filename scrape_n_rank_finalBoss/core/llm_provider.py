"""
LLM Provider - Thin Adapter for Claude (Anthropic), OpenAI, and Perplexity

Provides a unified interface for calling different LLM APIs.
Each provider handles authentication, request formatting, and response parsing.
Includes retry logic for transient failures.
"""

import os
import time
import requests
from dataclasses import dataclass
from typing import Optional

from core.retry import (
    MAX_RETRIES,
    calculate_retry_delay,
    classify_error,
)


# =====================================================================
# RESPONSE DATACLASS
# =====================================================================

@dataclass
class LLMResponse:
    """Unified response from any LLM provider."""
    success: bool
    content: str  # raw text response
    input_tokens: int
    output_tokens: int
    error: Optional[str]
    duration_ms: int


# =====================================================================
# BASE PROVIDER
# =====================================================================

class LLMProvider:
    """
    Base class for LLM providers.

    Subclasses implement the actual API calls for each provider.
    """

    def __init__(self, model_name: str):
        self.model_name = model_name

    @staticmethod
    def from_model(model_name: str) -> 'LLMProvider':
        """
        Factory method to create the appropriate provider based on model name.

        Args:
            model_name: Name of the model (e.g. "claude-haiku-4-5-20251001", "gpt-4o", "sonar")

        Returns:
            Appropriate LLMProvider subclass instance
        """
        model_lower = model_name.lower()

        if 'claude' in model_lower:
            return AnthropicProvider(model_name)
        elif model_lower.startswith(('gpt', 'o1', 'o3')):
            return OpenAIProvider(model_name)
        elif 'sonar' in model_lower:
            return PerplexityProvider(model_name)
        else:
            # Default fallback to OpenAI-compatible
            return OpenAIProvider(model_name)

    def complete(
        self,
        prompt: str,
        system: str = None,
        max_tokens: int = 2000,
        temperature: float = 0,
    ) -> LLMResponse:
        """
        Send a completion request to the LLM.

        Args:
            prompt: User prompt text
            system: Optional system prompt
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0 = deterministic)

        Returns:
            LLMResponse with success/failure and content
        """
        raise NotImplementedError("Subclasses must implement complete()")


# =====================================================================
# ANTHROPIC PROVIDER (Claude)
# =====================================================================

class AnthropicProvider(LLMProvider):
    """
    Anthropic Claude provider using direct HTTP requests.

    Uses the Messages API at https://api.anthropic.com/v1/messages
    """

    API_URL = "https://api.anthropic.com/v1/messages"
    API_VERSION = "2023-06-01"

    def __init__(self, model_name: str):
        super().__init__(model_name)
        self.api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment variables")

    def complete(
        self,
        prompt: str,
        system: str = None,
        max_tokens: int = 2000,
        temperature: float = 0,
    ) -> LLMResponse:
        start_time = time.time()

        headers = {
            'x-api-key': self.api_key,
            'anthropic-version': self.API_VERSION,
            'content-type': 'application/json',
        }

        body = {
            'model': self.model_name,
            'max_tokens': max_tokens,
            'temperature': temperature,
            'messages': [{'role': 'user', 'content': prompt}],
        }

        if system:
            body['system'] = system

        for attempt in range(MAX_RETRIES):
            try:
                response = requests.post(
                    self.API_URL,
                    headers=headers,
                    json=body,
                    timeout=120,
                )

                # Rate limit or overloaded - retry
                if response.status_code in (429, 529):
                    if attempt < MAX_RETRIES - 1:
                        delay = calculate_retry_delay(attempt)
                        time.sleep(delay)
                        continue

                data = response.json()

                if 'content' in data and data['content']:
                    text = data['content'][0].get('text', '')
                    input_tokens = data.get('usage', {}).get('input_tokens', 0)
                    output_tokens = data.get('usage', {}).get('output_tokens', 0)

                    return LLMResponse(
                        success=True,
                        content=text,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        error=None,
                        duration_ms=int((time.time() - start_time) * 1000),
                    )
                else:
                    error_msg = data.get('error', {}).get('message', 'Unknown error')
                    error_type, can_retry = classify_error(Exception(error_msg), response)

                    if can_retry and attempt < MAX_RETRIES - 1:
                        delay = calculate_retry_delay(attempt)
                        time.sleep(delay)
                        continue

                    return LLMResponse(
                        success=False,
                        content='',
                        input_tokens=0,
                        output_tokens=0,
                        error=error_msg,
                        duration_ms=int((time.time() - start_time) * 1000),
                    )

            except requests.exceptions.Timeout:
                if attempt < MAX_RETRIES - 1:
                    delay = calculate_retry_delay(attempt)
                    time.sleep(delay)
                    continue

                return LLMResponse(
                    success=False,
                    content='',
                    input_tokens=0,
                    output_tokens=0,
                    error=f"Timeout after {MAX_RETRIES} attempts",
                    duration_ms=int((time.time() - start_time) * 1000),
                )

            except Exception as e:
                error_type, can_retry = classify_error(e)

                if can_retry and attempt < MAX_RETRIES - 1:
                    delay = calculate_retry_delay(attempt)
                    time.sleep(delay)
                    continue

                return LLMResponse(
                    success=False,
                    content='',
                    input_tokens=0,
                    output_tokens=0,
                    error=str(e),
                    duration_ms=int((time.time() - start_time) * 1000),
                )

        return LLMResponse(
            success=False,
            content='',
            input_tokens=0,
            output_tokens=0,
            error="Max retries exceeded",
            duration_ms=int((time.time() - start_time) * 1000),
        )


# =====================================================================
# OPENAI PROVIDER
# =====================================================================

class OpenAIProvider(LLMProvider):
    """
    OpenAI provider using the openai SDK.

    Supports GPT-4o, GPT-5-mini, o1, o3, and other OpenAI models.
    """

    def __init__(self, model_name: str):
        super().__init__(model_name)
        self.api_key = os.environ.get('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")

        try:
            import openai
            self.client = openai.OpenAI(api_key=self.api_key)
        except ImportError:
            raise ImportError("openai package is required for OpenAIProvider. Install with: pip install openai")

    def complete(
        self,
        prompt: str,
        system: str = None,
        max_tokens: int = 2000,
        temperature: float = 0,
    ) -> LLMResponse:
        import openai

        start_time = time.time()

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )

                content = response.choices[0].message.content or ''
                usage = response.usage

                return LLMResponse(
                    success=True,
                    content=content,
                    input_tokens=usage.prompt_tokens if usage else 0,
                    output_tokens=usage.completion_tokens if usage else 0,
                    error=None,
                    duration_ms=int((time.time() - start_time) * 1000),
                )

            except openai.RateLimitError:
                if attempt < MAX_RETRIES - 1:
                    delay = calculate_retry_delay(attempt)
                    time.sleep(delay)
                    continue

                return LLMResponse(
                    success=False,
                    content='',
                    input_tokens=0,
                    output_tokens=0,
                    error=f"Rate limited after {MAX_RETRIES} attempts",
                    duration_ms=int((time.time() - start_time) * 1000),
                )

            except openai.APITimeoutError:
                if attempt < MAX_RETRIES - 1:
                    delay = calculate_retry_delay(attempt)
                    time.sleep(delay)
                    continue

                return LLMResponse(
                    success=False,
                    content='',
                    input_tokens=0,
                    output_tokens=0,
                    error=f"Timeout after {MAX_RETRIES} attempts",
                    duration_ms=int((time.time() - start_time) * 1000),
                )

            except openai.APIConnectionError:
                if attempt < MAX_RETRIES - 1:
                    delay = calculate_retry_delay(attempt)
                    time.sleep(delay)
                    continue

                return LLMResponse(
                    success=False,
                    content='',
                    input_tokens=0,
                    output_tokens=0,
                    error=f"Connection error after {MAX_RETRIES} attempts",
                    duration_ms=int((time.time() - start_time) * 1000),
                )

            except openai.InternalServerError:
                if attempt < MAX_RETRIES - 1:
                    delay = calculate_retry_delay(attempt)
                    time.sleep(delay)
                    continue

                return LLMResponse(
                    success=False,
                    content='',
                    input_tokens=0,
                    output_tokens=0,
                    error=f"Server error after {MAX_RETRIES} attempts",
                    duration_ms=int((time.time() - start_time) * 1000),
                )

            except Exception as e:
                error_type, can_retry = classify_error(e)

                if can_retry and attempt < MAX_RETRIES - 1:
                    delay = calculate_retry_delay(attempt)
                    time.sleep(delay)
                    continue

                return LLMResponse(
                    success=False,
                    content='',
                    input_tokens=0,
                    output_tokens=0,
                    error=str(e),
                    duration_ms=int((time.time() - start_time) * 1000),
                )

        return LLMResponse(
            success=False,
            content='',
            input_tokens=0,
            output_tokens=0,
            error="Max retries exceeded",
            duration_ms=int((time.time() - start_time) * 1000),
        )


# =====================================================================
# PERPLEXITY PROVIDER
# =====================================================================

class PerplexityProvider(LLMProvider):
    """
    Perplexity provider using the openai SDK with custom base_url.

    Supports sonar and sonar-pro models.
    """

    BASE_URL = "https://api.perplexity.ai"

    def __init__(self, model_name: str):
        super().__init__(model_name)
        self.api_key = os.environ.get('PERPLEXITY_API_KEY')
        if not self.api_key:
            raise ValueError("PERPLEXITY_API_KEY not found in environment variables")

        try:
            import openai
            self.client = openai.OpenAI(
                api_key=self.api_key,
                base_url=self.BASE_URL,
            )
        except ImportError:
            raise ImportError("openai package is required for PerplexityProvider. Install with: pip install openai")

    def complete(
        self,
        prompt: str,
        system: str = None,
        max_tokens: int = 2000,
        temperature: float = 0,
    ) -> LLMResponse:
        import openai

        start_time = time.time()

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )

                content = response.choices[0].message.content or ''
                usage = response.usage

                return LLMResponse(
                    success=True,
                    content=content,
                    input_tokens=usage.prompt_tokens if usage else 0,
                    output_tokens=usage.completion_tokens if usage else 0,
                    error=None,
                    duration_ms=int((time.time() - start_time) * 1000),
                )

            except openai.RateLimitError:
                if attempt < MAX_RETRIES - 1:
                    delay = calculate_retry_delay(attempt)
                    time.sleep(delay)
                    continue

                return LLMResponse(
                    success=False,
                    content='',
                    input_tokens=0,
                    output_tokens=0,
                    error=f"Rate limited after {MAX_RETRIES} attempts",
                    duration_ms=int((time.time() - start_time) * 1000),
                )

            except openai.APITimeoutError:
                if attempt < MAX_RETRIES - 1:
                    delay = calculate_retry_delay(attempt)
                    time.sleep(delay)
                    continue

                return LLMResponse(
                    success=False,
                    content='',
                    input_tokens=0,
                    output_tokens=0,
                    error=f"Timeout after {MAX_RETRIES} attempts",
                    duration_ms=int((time.time() - start_time) * 1000),
                )

            except openai.APIConnectionError:
                if attempt < MAX_RETRIES - 1:
                    delay = calculate_retry_delay(attempt)
                    time.sleep(delay)
                    continue

                return LLMResponse(
                    success=False,
                    content='',
                    input_tokens=0,
                    output_tokens=0,
                    error=f"Connection error after {MAX_RETRIES} attempts",
                    duration_ms=int((time.time() - start_time) * 1000),
                )

            except openai.InternalServerError:
                if attempt < MAX_RETRIES - 1:
                    delay = calculate_retry_delay(attempt)
                    time.sleep(delay)
                    continue

                return LLMResponse(
                    success=False,
                    content='',
                    input_tokens=0,
                    output_tokens=0,
                    error=f"Server error after {MAX_RETRIES} attempts",
                    duration_ms=int((time.time() - start_time) * 1000),
                )

            except Exception as e:
                error_type, can_retry = classify_error(e)

                if can_retry and attempt < MAX_RETRIES - 1:
                    delay = calculate_retry_delay(attempt)
                    time.sleep(delay)
                    continue

                return LLMResponse(
                    success=False,
                    content='',
                    input_tokens=0,
                    output_tokens=0,
                    error=str(e),
                    duration_ms=int((time.time() - start_time) * 1000),
                )

        return LLMResponse(
            success=False,
            content='',
            input_tokens=0,
            output_tokens=0,
            error="Max retries exceeded",
            duration_ms=int((time.time() - start_time) * 1000),
        )
