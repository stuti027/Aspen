import json
from typing import Optional
from app.services.browser_manager import BrowserManager

class TimeSimulator:
    def __init__(self, browser_manager: BrowserManager):
        self.browser = browser_manager
        self._faked_time_offset_ms = 0

    async def install_fake_clock(self, initial_epoch_ms: Optional[int] = None):
        time_patch_script = f"""
        (() => {{
            const OriginalDate = window.Date;
            let currentOffset = 0;
            
            window.__setAspenTimeOffset = (offset) => {{
                currentOffset = offset;
            }};

            function MockDate(...args) {{
                if (args.length === 0) {{
                    return new OriginalDate(OriginalDate.now() + currentOffset);
                }}
                return new OriginalDate(...args);
            }}

            MockDate.now = () => OriginalDate.now() + currentOffset;
            MockDate.UTC = OriginalDate.UTC;
            MockDate.parse = OriginalDate.parse;
            MockDate.prototype = OriginalDate.prototype;

            window.Date = MockDate;

            const originalSetTimeout = window.setTimeout;
            const originalSetInterval = window.setInterval;
            
            window.__aspenTimers = window.__aspenTimers || [];
            
            window.setTimeout = (callback, delay, ...args) => {{
                return originalSetTimeout(callback, delay, ...args);
            }};
        }})();
        """

        await self.browser.send_command("Page.addScriptToEvaluateOnNewDocument", {
            "source": time_patch_script
        })

    async def fast_forward(self, milliseconds: int):
        self._faked_time_offset_ms += milliseconds
        script = f"window.__setAspenTimeOffset && window.__setAspenTimeOffset({self._faked_time_offset_ms});"
        await self.browser.evaluate_script(script)

    async def get_current_simulated_time(self) -> int:
        script = "Date.now()"
        return await self.browser.evaluate_script(script)