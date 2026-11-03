
import asyncio

from app.services.browser_manager import BrowserManager
from app.agents.time_simulation_agent import TimeSimulator


async def main():
    browser = BrowserManager(headless=True)
    simulator = TimeSimulator(browser)

    try:
        await browser.start()

        await simulator.install_fake_clock()
        await browser.navigate("https://example.com")

        await browser.evaluate_script("""
            window.timerTest = {
                timeout: 0,
                interval: 0
            };

            window.timeoutId = setTimeout(() => {
                window.timerTest.timeout++;
            }, 5000);

            window.intervalId = setInterval(() => {
                window.timerTest.interval++;
            }, 2000);
        """)

        before = await simulator.get_current_simulated_time()

        advancement = await simulator.fast_forward(6000)

        after = await simulator.get_current_simulated_time()

        timer_results = await browser.evaluate_script(
            "window.timerTest"
        )

        print("Before:", before)
        print("After:", after)
        print("Advancement:", advancement)
        print("Timer results:", timer_results)

        assert timer_results["timeout"] == 1
        assert timer_results["interval"] == 3
        assert after - before >= 6000

        print("TIMER SIMULATION TEST PASSED")

    finally:
        await browser.stop()


if __name__ == "__main__":
    asyncio.run(main())
