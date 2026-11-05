
import asyncio
import base64
import mimetypes
import random
import re

from pathlib import Path
from typing import Any, Awaitable, Callable, Type, TypeVar

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, ValidationError

from app.core.config import settings


T = TypeVar("T", bound=BaseModel)


class LLMServiceError(RuntimeError):
    """Base exception for LLM service failures."""


class LLMQuotaExceededError(LLMServiceError):
    """The provider's allocated quota has been exhausted."""


class LLMRateLimitError(LLMServiceError):
    """The provider is temporarily rate limiting requests."""


class LLMUnavailableError(LLMServiceError):
    """The model is temporarily unavailable."""


class LLMRequestTimeoutError(LLMServiceError):
    """The LLM request exceeded its timeout."""


class LLMRequestError(LLMServiceError):
    """A non-retryable LLM request failure."""


class LLMResponseError(LLMServiceError):
    """The LLM returned an invalid or unusable response."""


class GeminiLLMService:

    MAX_ATTEMPTS = 3
    REQUEST_TIMEOUT = 45
    BASE_RETRY_DELAY = 1
    MAX_RETRY_DELAY = 8

    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(self):
        if not settings.gemini_api_key:
            raise ValueError(
                "GEMINI_API_KEY environment variable is not configured."
            )

        self.llm = ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            google_api_key=settings.gemini_api_key,
            max_output_tokens=2048
        )

    @staticmethod
    def _get_error_category(exc: Exception) -> str:
        message = str(exc).lower()
        exception_name = type(exc).__name__.lower()

        # Detect exhausted quota before treating a 429 as temporary.
        if any(term in message for term in (
            "quota exceeded",
            "quotaexceeded",
            "daily quota",
            "per day",
            "billing",
            "insufficient quota"
        )):
            return "quota"

        status_code = getattr(exc, "status_code", None)

        if status_code is None:
            status_code = getattr(exc, "code", None)

        if isinstance(status_code, int):
            code = status_code
        else:
            match = re.search(
                r"\b(429|500|502|503|504)\b",
                message
            )
            code = int(match.group(1)) if match else None

        if code == 429:
            return "rate_limit"

        if code in {500, 502, 503, 504}:
            return "unavailable"

        if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
            return "timeout"

        if any(term in exception_name for term in (
            "timeout",
            "connection",
            "network"
        )):
            return "network"

        if isinstance(exc, (ConnectionError, OSError)):
            return "network"

        return "request"

    async def _invoke_with_retry(
        self,
        operation: Callable[[], Awaitable[Any]],
        operation_name: str
    ) -> Any:

        for attempt in range(self.MAX_ATTEMPTS):

            try:
                return await asyncio.wait_for(
                    operation(),
                    timeout=self.REQUEST_TIMEOUT
                )

            except Exception as exc:
                category = self._get_error_category(exc)

                if category == "quota":
                    raise LLMQuotaExceededError(
                        "Gemini quota has been exhausted. "
                        "No further retries will be attempted."
                    ) from exc

                retryable = category in {
                    "rate_limit",
                    "unavailable",
                    "timeout",
                    "network"
                }

                if not retryable:
                    raise LLMRequestError(
                        f"{operation_name} failed: "
                        f"{type(exc).__name__}"
                    ) from exc

                if attempt == self.MAX_ATTEMPTS - 1:
                    if category == "rate_limit":
                        raise LLMRateLimitError(
                            f"{operation_name} failed after "
                            f"{self.MAX_ATTEMPTS} attempts."
                        ) from exc

                    if category == "timeout":
                        raise LLMRequestTimeoutError(
                            f"{operation_name} timed out after "
                            f"{self.MAX_ATTEMPTS} attempts."
                        ) from exc

                    raise LLMUnavailableError(
                        f"{operation_name} could not complete after "
                        f"{self.MAX_ATTEMPTS} attempts."
                    ) from exc

                delay = min(
                    self.BASE_RETRY_DELAY * (2 ** attempt),
                    self.MAX_RETRY_DELAY
                )

                delay *= random.uniform(0.8, 1.2)

                await asyncio.sleep(delay)

    async def generate_text(
        self,
        prompt: str,
        system_instruction: str | None = None
    ) -> str:

        if not prompt.strip():
            raise ValueError("Prompt cannot be empty.")

        messages = []

        if system_instruction:
            messages.append(
                SystemMessage(content=system_instruction)
            )

        messages.append(
            HumanMessage(content=prompt)
        )

        response = await self._invoke_with_retry(
            lambda: self.llm.ainvoke(messages),
            "Gemini text generation"
        )

        if isinstance(response.content, str):
            result = response.content.strip()
        else:
            text_parts = [
                block["text"]
                for block in response.content
                if isinstance(block, dict)
                and block.get("type") == "text"
            ]

            result = "\n".join(text_parts).strip()

        if not result:
            raise LLMResponseError(
                "Gemini returned an empty response."
            )

        return result

    async def generate_structured(
        self,
        prompt: str,
        output_schema: Type[T],
        system_instruction: str | None = None,
        image_paths: list[str] | None = None
    ) -> T:

        if not prompt.strip():
            raise ValueError("Prompt cannot be empty.")

        structured_llm = self.llm.with_structured_output(
            output_schema
        )

        messages = []

        if system_instruction:
            messages.append(
                SystemMessage(content=system_instruction)
            )

        content = [
            {
                "type": "text",
                "text": prompt
            }
        ]

        for image_path in image_paths or []:
            path = Path(image_path)

            if not path.is_file():
                raise FileNotFoundError(
                    f"Image not found: {path}"
                )

            mime_type, _ = mimetypes.guess_type(str(path))

            if not mime_type or not mime_type.startswith("image/"):
                raise ValueError(
                    f"Unsupported image format: {path}"
                )

            image_base64 = base64.b64encode(
                path.read_bytes()
            ).decode("utf-8")

            content.append({
                "type": "image",
                "base64": image_base64,
                "mime_type": mime_type
            })

        messages.append(
            HumanMessage(content=content)
        )

        response = await self._invoke_with_retry(
            lambda: structured_llm.ainvoke(messages),
            "Gemini structured generation"
        )

        try:
            if isinstance(response, output_schema):
                return response

            return output_schema.model_validate(response)

        except (ValidationError, TypeError, ValueError) as exc:
            raise LLMResponseError(
                "Gemini returned an invalid structured response."
            ) from exc
