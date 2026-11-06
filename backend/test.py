
import asyncio
import json

from app.agents.orchestration.orchestration_agent import (
    OrchestrationAgent,
)
from app.services.browser_manager import BrowserManager


async def main():
    browser = BrowserManager()
    await browser.start()
    orchestrator = OrchestrationAgent(browser)

    test_plan = orchestrator.create_test_plan(
        url="https://the-internet.herokuapp.com/",
        selected_agents=[
            "functionality",
            "time_simulation",
            "uiux",
        ],
        functionality_objective=(
            "Navigate to the website and inspect "
            "the available links."
        ),
        time_jump_ms=60000,
    )

    result = await orchestrator.execute_plan(
        test_plan,
        max_retries=1,
    )

    print("\n========== INTEGRATION TEST RESULT ==========")
    print(json.dumps(result, indent=4, default=str))

    assert result["completed_tasks"] == 3
    assert result["failed_tasks"] == 0
    assert len(result["results"]) == 3
    assert "report" in result
    assert result["report"]["statistics"]["total_agents"] == 3

    report = result["report"]

    assert report["url"] == test_plan["url"]
    assert "executive_summary" in report
    assert "statistics" in report
    assert "findings" in report
    assert "recommendations" in report

    print("\nREPORT INTEGRATION TEST PASSED")


if __name__ == "__main__":
    asyncio.run(main())
