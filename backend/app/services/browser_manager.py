import asyncio
import json
import subprocess
import urllib.request
from typing import Optional, Dict, Any
import websockets

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
        chrome_path = "chrome"  # whatever is the path to your Chrome/Chromium exe
        
        args = [
            chrome_path,
            f"--remote-debugging-port={self.debugging_port}",
            "--no-first-run",
            "--no-default-browser-check",
            "about:blank"
        ]
        if self.headless:
            args.append("--headless=new")

        self.browser_process = subprocess.Popen(
            args, 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL
        )
        
        await asyncio.sleep(2)

        ws_url = self._get_websocket_target_url()
        if not ws_url:
            raise RuntimeError("Could not retrieve Chrome DevTools Protocol WebSocket URL.")

        # Establish WebSocket connection
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
        result = await self.send_command("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        return result.get("result", {}).get("value")

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