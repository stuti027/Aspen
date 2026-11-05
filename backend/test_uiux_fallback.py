import asyncio
from unittest.mock import AsyncMock, patch

from app.services.browser_manager import BrowserManager
from app.services.llm_service import (
    GeminiLLMService,
    LLMUnavailableError,
)
from app.agents.uiux.uiux_agent import UIUXAgent


async def main():
    browser = BrowserManager(headless=False)

    try:
        await browser.start()
        agent = UIUXAgent(browser)

        with patch.object(
            GeminiLLMService,
            "generate_structured",
            new_callable=AsyncMock,
            side_effect=LLMUnavailableError("Simulated Gemini 503"),
        ):
            result = await agent.run(
                url="https://example.com",
                evidence_dir="artifacts/test_uiux_run_fallback",
            )

        print("\nFULL UIUX AGENT RESULT")
        print("Viewport count:", result["summary"]["viewport_count"])
        print("Deterministic findings:", result["summary"]["total_findings"])
        print("Exploration status:", result["exploration"]["status"])
        print("LLM evaluation status:",
              result["summary"]["llm_evaluation_status"])

        assert result["summary"]["viewport_count"] == 3
        assert len(result["viewports"]) == 3
        assert result["exploration"]["status"] == "partial"
        assert result["summary"]["llm_evaluation_status"] == "unavailable"
        assert "findings" in result

        print("\nFull UIUX fallback integration test passed!")

    finally:
        await browser.stop()


if __name__ == "__main__":
    asyncio.run(main())