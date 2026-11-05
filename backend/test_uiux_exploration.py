import asyncio

from app.services.browser_manager import BrowserManager
from app.agents.uiux.uiux_agent import UIUXAgent


async def main():
    browser = BrowserManager(headless=False)

    try:
        await browser.start()

        agent = UIUXAgent(browser)

        exploration_result = await agent.explore_website(
            url="https://the-internet.herokuapp.com/",
            max_steps=3
        )

        print("\nUIUX EXPLORATION RESULT")
        print(exploration_result)

        evaluation_result = await agent.evaluate_exploration(
            exploration=exploration_result
        )

        print("\nCONSOLIDATED UX EVALUATION")
        print(evaluation_result)

    finally:
        await browser.stop()


if __name__ == "__main__":
    asyncio.run(main())