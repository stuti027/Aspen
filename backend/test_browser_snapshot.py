import asyncio

from app.services.browser_manager import BrowserManager


async def main():
    browser = BrowserManager(headless=False)

    try:
        await browser.start()

        await browser.navigate("https://example.com")

        snapshot = await browser.get_interaction_snapshot()

        print("\nPAGE INFORMATION")
        print("Title:", snapshot["title"])
        print("URL:", snapshot["url"])

        print("\nHEADINGS")
        for heading in snapshot["headings"]:
            print(heading)

        print("\nAVAILABLE INTERACTIONS")
        for control in snapshot["controls"]:
            print(control)

        print("\nPAGE TEXT")
        print(snapshot["page_text"][:1000])

        print("\nBROWSER SNAPSHOT TEST PASSED")

    except Exception as e:
        print("\nBROWSER SNAPSHOT TEST FAILED:", e)

    finally:
        await browser.stop()


if __name__ == "__main__":
    asyncio.run(main())