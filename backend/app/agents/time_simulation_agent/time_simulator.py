
from typing import Optional

from app.services.browser_manager import BrowserManager


class TimeSimulator:

    def __init__(self, browser_manager: BrowserManager):
        self.browser = browser_manager
        self._faked_time_offset_ms = 0
        self._script_identifier: Optional[str] = None

    def _build_clock_script(self) -> str:
        script = r"""
        (() => {
            if (window.__aspenClockInstalled) {
                return;
            }

            const OriginalDate = window.Date;

            let virtualNow = OriginalDate.now() + __INITIAL_OFFSET__;
            let nextTimerId = 1;

            const timers = new Map();
            const timerErrors = [];

            function MockDate(...args) {
                if (!new.target) {
                    return new OriginalDate(virtualNow).toString();
                }

                if (args.length === 0) {
                    return new OriginalDate(virtualNow);
                }

                return new OriginalDate(...args);
            }

            MockDate.now = () => virtualNow;
            MockDate.UTC = OriginalDate.UTC;
            MockDate.parse = OriginalDate.parse;
            MockDate.prototype = OriginalDate.prototype;

            Object.setPrototypeOf(MockDate, OriginalDate);

            window.Date = MockDate;

            function scheduleTimer(callback, delay, args, repeating) {
                if (
                    typeof callback !== "function" &&
                    typeof callback !== "string"
                ) {
                    throw new TypeError("Timer callback must be a function or string.");
                }

                let normalizedDelay = Number(delay);

                if (!Number.isFinite(normalizedDelay)) {
                    normalizedDelay = 0;
                }

                normalizedDelay = Math.max(0, normalizedDelay);

                if (repeating) {
                    normalizedDelay = Math.max(1, normalizedDelay);
                }

                const id = nextTimerId++;

                const callbackFunction =
                    typeof callback === "function"
                        ? callback
                        : () => window.eval(callback);

                timers.set(id, {
                    id,
                    callback: callbackFunction,
                    args,
                    due: virtualNow + normalizedDelay,
                    interval: repeating ? normalizedDelay : 0,
                    repeating
                });

                return id;
            }

            window.setTimeout = (callback, delay = 0, ...args) => {
                return scheduleTimer(callback, delay, args, false);
            };

            window.setInterval = (callback, delay = 0, ...args) => {
                return scheduleTimer(callback, delay, args, true);
            };

            window.clearTimeout = (id) => {
                timers.delete(Number(id));
            };

            window.clearInterval = (id) => {
                timers.delete(Number(id));
            };

            window.__advanceAspenTime = (milliseconds) => {
                milliseconds = Number(milliseconds);

                if (!Number.isFinite(milliseconds) || milliseconds < 0) {
                    throw new Error("Invalid time advancement.");
                }

                const targetTime = virtualNow + milliseconds;

                let executed = 0;
                const MAX_TIMER_EXECUTIONS = 100000;

                while (true) {
                    let nextTimer = null;

                    for (const timer of timers.values()) {
                        if (timer.due <= targetTime) {
                            if (
                                nextTimer === null ||
                                timer.due < nextTimer.due ||
                                (
                                    timer.due === nextTimer.due &&
                                    timer.id < nextTimer.id
                                )
                            ) {
                                nextTimer = timer;
                            }
                        }
                    }

                    if (nextTimer === null) {
                        break;
                    }

                    if (executed >= MAX_TIMER_EXECUTIONS) {
                        virtualNow = targetTime;
                        throw new Error(
                            "Timer execution limit exceeded during time simulation."
                        );
                    }

                    virtualNow = nextTimer.due;

                    if (!nextTimer.repeating) {
                        timers.delete(nextTimer.id);
                    }

                    try {
                        nextTimer.callback.apply(window, nextTimer.args);
                    } catch (error) {
                        timerErrors.push({
                            timer_id: nextTimer.id,
                            message: String(error.message || error)
                        });
                    }

                    executed++;

                    if (
                        nextTimer.repeating &&
                        timers.get(nextTimer.id) === nextTimer
                    ) {
                        nextTimer.due += nextTimer.interval;
                    }
                }

                virtualNow = targetTime;

                return {
                    simulated_timestamp: virtualNow,
                    executed_timers: executed,
                    pending_timers: timers.size,
                    timer_errors: timerErrors.splice(0)
                };
            };

            window.__getAspenTimerState = () => ({
                simulated_timestamp: virtualNow,
                pending_timers: timers.size
            });

            window.__aspenClockInstalled = true;
        })();
        """

        return script.replace(
            "__INITIAL_OFFSET__",
            str(self._faked_time_offset_ms)
        )

    async def install_fake_clock(
        self,
        initial_offset_ms: int = 0
    ):
        if initial_offset_ms < 0:
            raise ValueError("Initial time offset cannot be negative.")

        if self._script_identifier:
            await self.browser.send_command(
                "Page.removeScriptToEvaluateOnNewDocument",
                {"identifier": self._script_identifier}
            )

            self._script_identifier = None

        self._faked_time_offset_ms = initial_offset_ms

        script = self._build_clock_script()

        registration = await self.browser.send_command(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": script}
        )

        self._script_identifier = registration.get("identifier")

        # Also install the clock in the currently loaded document.
        await self.browser.evaluate_script(script)

    async def fast_forward(self, milliseconds: int):
        if milliseconds <= 0:
            raise ValueError(
                "Time advancement must be greater than zero."
            )

        new_offset = self._faked_time_offset_ms + milliseconds

        if self._script_identifier:
            await self.browser.send_command(
                "Page.removeScriptToEvaluateOnNewDocument",
                {"identifier": self._script_identifier}
            )

            self._script_identifier = None

        self._faked_time_offset_ms = new_offset

        # Register the updated offset for future page navigations.
        registration = await self.browser.send_command(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": self._build_clock_script()}
        )

        self._script_identifier = registration.get("identifier")

        # Advance the virtual clock and execute due callbacks
        # in the currently loaded page.
        return await self.browser.evaluate_script(
            f"window.__advanceAspenTime({milliseconds})"
        )

    async def get_current_simulated_time(self) -> int:
        return await self.browser.evaluate_script("Date.now()")

    async def get_timer_state(self) -> dict:
        return await self.browser.evaluate_script(
            "window.__getAspenTimerState()"
        )

    async def reset(self):
        if self._script_identifier:
            await self.browser.send_command(
                "Page.removeScriptToEvaluateOnNewDocument",
                {"identifier": self._script_identifier}
            )

        self._script_identifier = None
        self._faked_time_offset_ms = 0

        await self.browser.navigate("about:blank")
