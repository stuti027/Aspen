import asyncio
from typing import Dict, Any, List
from app.services.browser_manager import BrowserManager

class ToolExecutor:
    def __init__(self, browser_manager: BrowserManager):
        self.browser = browser_manager

    async def execute_action(self, action_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if action_type == "navigate":
                url = params.get("url")
                await self.browser.navigate(url)
                return {"status": "success", "action": "navigate", "url": url}

            elif action_type == "click":
                selector = params.get("selector")
                script = f"""
                (() => {{
                    const el = document.querySelector("{selector}");
                    if (el) {{
                        el.click();
                        return true;
                    }}
                    return false;
                }})();
                """
                clicked = await self.browser.evaluate_script(script)
                if not clicked:
                    return {"status": "error", "message": f"Element not found for selector: {selector}"}
                return {"status": "success", "action": "click", "selector": selector}

            elif action_type == "fill":
                selector = params.get("selector")
                value = params.get("value", "")
                script = f"""
                (() => {{
                    const el = document.querySelector("{selector}");
                    if (el) {{
                        el.value = "{value}";
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        return true;
                    }}
                    return false;
                }})();
                """
                filled = await self.browser.evaluate_script(script)
                if not filled:
                    return {"status": "error", "message": f"Input element not found for selector: {selector}"}
                return {"status": "success", "action": "fill", "selector": selector}

            elif action_type == "screenshot":
                path = params.get("path", "screenshot.png")
                await self.browser.capture_screenshot(path)
                return {"status": "success", "action": "screenshot", "path": path}

            else:
                return {"status": "error", "message": f"Unknown action type: {action_type}"}

        except Exception as e:
            return {"status": "error", "message": str(e)}

class FunctionalityAgent:
    def __init__(self, browser_manager: BrowserManager):
        self.browser = browser_manager
        self.executor = ToolExecutor(browser_manager)

    async def run_workflow(self, steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results = []
        for step in steps:
            action_type = step.get("action")
            params = step.get("params", {{}})
            
            print(f"Executing step: {action_type} with params {params}")
            result = await self.executor.execute_action(action_type, params)
            results.append(result)
            
            await asyncio.sleep(1)
            
        return results