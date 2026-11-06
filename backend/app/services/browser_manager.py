import asyncio
import json
import subprocess
import urllib.request
from typing import Optional, Dict, Any
import websockets
import os
import shutil

class BrowserManager:
    def __init__(self, headless: bool = False, debugging_port: int = 9222):
        self.headless = headless
        self.debugging_port = debugging_port
        self.browser_process: Optional[subprocess.Popen] = None
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self._message_id = 0

    def _get_next_id(self) -> int:
        self._message_id += 1
        return self._message_id

    async def start(self):
        chrome_path = (
            os.getenv("CHROME_PATH")
            or shutil.which("chrome")
            or r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        )

        if not os.path.isfile(chrome_path):
            raise FileNotFoundError(
                f"Chrome executable not found: {chrome_path}. "
                "Set the CHROME_PATH environment variable to its location."
            )
        
        args = [
            chrome_path,
            f"--remote-debugging-port={self.debugging_port}",
            "--no-first-run",
            "--no-default-browser-check",
            "--user-data-dir=C:\\temp\\chrome_dev_session",
            "about:blank"
        ]
        if self.headless:
            args.append("--headless=new")

        self.browser_process = subprocess.Popen(
            args, 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL
        )
        
        await asyncio.sleep(3)

        ws_url = self._get_websocket_target_url()
        if not ws_url:
            raise RuntimeError("Could not retrieve Chrome DevTools Protocol WebSocket URL.")

        self.websocket = await websockets.connect(ws_url)

    def _get_websocket_target_url(self) -> Optional[str]:
        try:
            url = f"http://127.0.0.1:{self.debugging_port}/json"
            with urllib.request.urlopen(url, timeout=3) as response:
                data = json.loads(response.read().decode())
                for target in data:
                    if target.get("type") == "page":
                        return target.get("webSocketDebuggerUrl")
        except Exception as e:
            print(f"Error fetching browser targets: {e}")
        return None

    async def send_command(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.websocket:
            raise RuntimeError("Browser session is not active. Call start() first.")

        msg_id = self._get_next_id()
        payload = {
            "id": msg_id,
            "method": method,
            "params": params or {}
        }

        await self.websocket.send(json.dumps(payload))

        while True:
            response_str = await self.websocket.recv()
            response = json.loads(response_str)
            if response.get("id") == msg_id:
                if "error" in response:
                    raise RuntimeError(f"CDP Error for {method}: {response['error']}")
                return response.get("result", {})

    async def stop(self):
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
        if self.browser_process:
            self.browser_process.terminate()
            self.browser_process.wait()
            self.browser_process = None

    async def navigate(self, url: str):
        await self.send_command("Page.enable")
        await self.send_command("Page.navigate", {"url": url})
        await asyncio.sleep(2)

    async def evaluate_script(self, expression: str) -> Any:
        result = await self.send_command(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True
            }
        )

        if result.get("exceptionDetails"):
            raise RuntimeError(
                f"JavaScript execution failed: {result['exceptionDetails']}"
            )

        remote_result = result.get("result", {})

        if remote_result.get("type") == "undefined":
            return None

        return remote_result.get("value")

    async def get_page_title(self) -> str:
        title = await self.evaluate_script("document.title")
        return title or ""

    async def capture_screenshot(self, filepath: str):
        import base64
        result = await self.send_command("Page.captureScreenshot", {"format": "png"})
        data = result.get("data")
        if data:
            binary_data = base64.b64decode(data)
            with open(filepath, "wb") as f:
                f.write(binary_data)

    async def inspect_dom(self) -> Dict[str, Any]:
        script = """
        (() => {
            const getElements = (selector, mapper) => Array.from(document.querySelectorAll(selector)).map(mapper);
            
            return {
                title: document.title,
                url: window.location.href,
                buttons: getElements('button, input[type="submit"], input[type="button"]', (el, idx) => ({
                    tag: el.tagName.toLowerCase(),
                    text: el.innerText || el.value || '',
                    selector: `button:nth-of-type(${idx + 1})`,
                    enabled: !el.disabled
                })),
                inputs: getElements('input:not([type="submit"]):not([type="button"]), textarea', el => ({
                    type: el.type || 'text',
                    name: el.name || '',
                    placeholder: el.placeholder || ''
                })),
                links: getElements('a[href]', el => ({
                    text: el.innerText.trim(),
                    href: el.href
                }))
            };
        })();
        """
        result = await self.evaluate_script(script)
        return result or {"title": "", "url": "", "buttons": [], "inputs": [], "links": []}

    async def get_interaction_snapshot(self) -> Dict[str, Any]:
        script = """
        (() => {
            const isVisible = (el) => {
                const style = getComputedStyle(el);
                const rect = el.getBoundingClientRect();

                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && Number(style.opacity) > 0
                    && rect.width > 0
                    && rect.height > 0;
            };

            const getSelector = (el) => {
                if (el.id) {
                    return `#${CSS.escape(el.id)}`;
                }

                const parts = [];
                let current = el;

                while (
                    current &&
                    current.nodeType === Node.ELEMENT_NODE &&
                    current !== document.documentElement
                ) {
                    let part = current.tagName.toLowerCase();

                    const parent = current.parentElement;

                    if (!parent) break;

                    const siblings = Array.from(parent.children)
                        .filter(child => child.tagName === current.tagName);

                    if (siblings.length > 1) {
                        part += `:nth-of-type(${
                            siblings.indexOf(current) + 1
                        })`;
                    }

                    parts.unshift(part);
                    current = parent;
                }

                return parts.join(" > ");
            };

            const controls = Array.from(
                document.querySelectorAll(
                    "button, a, input, textarea, select, " +
                    "[role='button'], summary"
                )
            )
            .filter(isVisible)
            .slice(0, 60)
            .map(el => {
                const type = (el.type || "").toLowerCase();

                const text = (
                    el.innerText ||
                    el.textContent ||
                    el.getAttribute("aria-label") ||
                    el.getAttribute("title") ||
                    el.placeholder ||
                    el.value ||
                    ""
                ).replace(/\\s+/g, " ").trim().slice(0, 150);

                const sensitiveName =
                    /password|email|phone|address|card|payment|token|secret|otp/i
                    .test(
                        `${el.name || ""} ${el.id || ""} ${el.placeholder || ""}`
                    );

                const fillable =
                    (
                        (el.tagName === "INPUT" &&
                            ["text", "search"].includes(type)) ||
                        el.tagName === "TEXTAREA"
                    ) &&
                    !el.disabled &&
                    !el.readOnly &&
                    !sensitiveName;

                return {
                    selector: getSelector(el),
                    tag: el.tagName.toLowerCase(),
                    type,
                    text,
                    href: el.href || null,
                    disabled: Boolean(el.disabled),
                    fillable
                };
            });

            return {
                title: document.title,
                url: window.location.href,
                viewport: {
                    width: window.innerWidth,
                    height: window.innerHeight
                },
                scroll: {
                    x: window.scrollX,
                    y: window.scrollY,
                    height: document.documentElement.scrollHeight
                },
                headings: Array.from(
                    document.querySelectorAll("h1, h2, h3")
                )
                .filter(isVisible)
                .map(el => ({
                    level: el.tagName.toLowerCase(),
                    text: el.innerText.trim().slice(0, 200)
                }))
                .slice(0, 30),
                page_text: (document.body.innerText || "")
                    .replace(/\\s+/g, " ")
                    .slice(0, 5000),
                controls
            };
        })();
        """

        result = await self.evaluate_script(script)

        if not isinstance(result, dict):
            raise RuntimeError(
                "Could not retrieve the browser interaction snapshot."
            )

        return result

    async def click_element(self, selector: str) -> Dict[str, Any]:
        selector_json = json.dumps(selector)

        element = await self.evaluate_script(f"""
            (() => {{
                const el = document.querySelector({selector_json});

                if (!el) {{
                    return {{ error: "Element not found" }};
                }}

                if (el.disabled) {{
                    return {{ error: "Element is disabled" }};
                }}

                el.scrollIntoView({{
                    behavior: "instant",
                    block: "center"
                }});

                const rect = el.getBoundingClientRect();

                return {{
                    x: rect.left + rect.width / 2,
                    y: rect.top + rect.height / 2
                }};
            }})()
        """)

        if not element or "error" in element:
            raise RuntimeError(
                element.get("error", "Unable to locate element")
            )

        x = element["x"]
        y = element["y"]

        await self.send_command(
            "Input.dispatchMouseEvent",
            {
                "type": "mouseMoved",
                "x": x,
                "y": y
            }
        )

        await self.send_command(
            "Input.dispatchMouseEvent",
            {
                "type": "mousePressed",
                "x": x,
                "y": y,
                "button": "left",
                "clickCount": 1
            }
        )

        await self.send_command(
            "Input.dispatchMouseEvent",
            {
                "type": "mouseReleased",
                "x": x,
                "y": y,
                "button": "left",
                "clickCount": 1
            }
        )

        return {"success": True, "selector": selector}

    async def fill_input(
        self,
        selector: str,
        value: str
    ) -> Dict[str, Any]:

        selector_json = json.dumps(selector)
        value_json = json.dumps(value)

        result = await self.evaluate_script(f"""
            (() => {{
                const el = document.querySelector({selector_json});

                if (!el) {{
                    return {{ error: "Input not found" }};
                }}

                if (
                    !el.matches("input, textarea") ||
                    el.disabled ||
                    el.readOnly
                ) {{
                    return {{ error: "Element cannot be filled" }};
                }}

                el.focus();

                const setter = el instanceof HTMLTextAreaElement
                    ? HTMLTextAreaElement.prototype.value
                    : HTMLInputElement.prototype.value;

                Object.getOwnPropertyDescriptor(
                    Object.getPrototypeOf(el), "value"
                ).set.call(el, {value_json});

                el.dispatchEvent(new Event("input", {{ bubbles: true }}));
                el.dispatchEvent(new Event("change", {{ bubbles: true }}));

                return {{ success: true }};
            }})()
        """)

        if not result or not result.get("success"):
            raise RuntimeError(
                result.get("error", "Unable to fill input")
            )

        return {"success": True, "selector": selector}

    async def scroll_page(
        self,
        direction: str = "down",
        amount: int = 500
    ) -> Dict[str, Any]:

        if direction not in {"up", "down"}:
            raise ValueError("Direction must be 'up' or 'down'.")

        if amount <= 0:
            raise ValueError("Scroll amount must be positive.")

        distance = amount if direction == "down" else -amount

        return await self.evaluate_script(f"""
            (() => {{
                window.scrollBy({{
                    top: {distance},
                    behavior: "instant"
                }});

                return {{
                    scrollY: window.scrollY,
                    scrollHeight: document.documentElement.scrollHeight
                }};
            }})()
        """)

    async def enable_monitoring(self):
        await self.send_command("Network.enable")
        await self.send_command("Log.enable")
        await self.send_command("Runtime.enable")

    async def get_console_errors(self) -> list:
        script = """
        (() => {
            // If we maintain an error log array on window or parse logs
            return window.__console_errors || [];
        })();
        """
        errors = await self.evaluate_script(script)
        return errors or []

    async def check_broken_links(self) -> list:
        script = """
        Array.from(document.querySelectorAll('a[href]')).map(a => a.href)
        """
        links = await self.evaluate_script(script) or []
        broken = []
        return broken  