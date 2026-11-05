
import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from app.services.llm_service import (
    GeminiLLMService,
    LLMQuotaExceededError,
    LLMUnavailableError,
)


class SimulatedAPIError(Exception):
    def __init__(self, status_code, message="Simulated API failure"):
        super().__init__(message)
        self.status_code = status_code


class TestGeminiReliability(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Avoid initializing the actual Gemini client.
        self.service = GeminiLLMService.__new__(GeminiLLMService)

    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_retries_then_succeeds(self, mock_sleep):
        attempts = 0

        async def simulated_request():
            nonlocal attempts
            attempts += 1

            if attempts < 3:
                raise SimulatedAPIError(503)

            return "Success"

        result = await self.service._invoke_with_retry(
            simulated_request,
            "Test request"
        )

        self.assertEqual(result, "Success")
        self.assertEqual(attempts, 3)
        self.assertEqual(mock_sleep.await_count, 2)

    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_stops_after_max_attempts(self, mock_sleep):
        attempts = 0

        async def simulated_request():
            nonlocal attempts
            attempts += 1
            raise SimulatedAPIError(503)

        with self.assertRaises(LLMUnavailableError):
            await self.service._invoke_with_retry(
                simulated_request,
                "Test request"
            )

        self.assertEqual(
            attempts,
            self.service.MAX_ATTEMPTS
        )

        self.assertEqual(
            mock_sleep.await_count,
            self.service.MAX_ATTEMPTS - 1
        )

    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_quota_exhaustion_does_not_retry(self, mock_sleep):
        attempts = 0

        async def simulated_request():
            nonlocal attempts
            attempts += 1

            raise SimulatedAPIError(
                429,
                "Daily quota exceeded"
            )

        with self.assertRaises(LLMQuotaExceededError):
            await self.service._invoke_with_retry(
                simulated_request,
                "Test request"
            )

        self.assertEqual(attempts, 1)
        mock_sleep.assert_not_awaited()


if __name__ == "__main__":
    unittest.main(verbosity=2)
