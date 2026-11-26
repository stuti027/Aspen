
import asyncio
import json
from typing import Any, Dict, List, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from app.services.browser_manager import BrowserManager
from app.services.llm_service import GeminiLLMService, LLMServiceError


class FunctionalityStep(BaseModel):
    action: Literal["navigate", "click", "fill", "screenshot"]
    params: Dict[str, Any] = Field(default_factory=dict)


class GeneratedTestPlan(BaseModel):
    objective: str
    steps: List[FunctionalityStep] = Field(min_length=1, max_length=12)


class FailureInsight(BaseModel):
    step_index: int
    action: str
    likely_cause: str
    explanation: str
    recommendation: str


class FailureAnalysis(BaseModel):
    overall_assessment: str
    failures: List[FailureInsight]


class ToolExecutor:

    def __init__(self, browser_manager: BrowserManager):
        self.browser = browser_manager

    async def execute_action(
        self,
        action_type: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:

        try:
            if not isinstance(params, dict):
                return {
                    "status": "error",
                    "message": "Action parameters must be an object."
                }

            if action_type == "navigate":

                url = params.get("url")

                if not isinstance(url, str):
                    return {
                        "status": "error",
                        "message": "A valid URL string is required."
                    }

                url = url.strip()
                parsed = urlparse(url)

                if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                    return {
                        "status": "error",
                        "message": "A valid HTTP or HTTPS URL is required."
                    }

                await self.browser.navigate(url)

                return {
                    "status": "success",
                    "action": "navigate",
                    "url": url
                }

            elif action_type == "click":

                selector = params.get("selector")

                if not isinstance(selector, str) or not selector.strip():
                    return {
                        "status": "error",
                        "message": "A valid CSS selector is required."
                    }

                selector_json = json.dumps(selector)

                script = f"""
                    (() => {{
                        const selector = {selector_json};
                        const element = document.querySelector(selector);

                        if (!element || element.disabled) return false;

                        element.click();

                        return true;
                    }})()
                """

                clicked = await self.browser.evaluate_script(script)

                if not clicked:
                    return {
                        "status": "error",
                        "message": f"Element not found or disabled: {selector}"
                    }

                return {
                    "status": "success",
                    "action": "click",
                    "selector": selector
                }

            elif action_type == "fill":

                selector = params.get("selector")
                value = params.get("value", "")

                if not isinstance(selector, str) or not selector.strip():
                    return {
                        "status": "error",
                        "message": "A valid CSS selector is required."
                    }

                if not isinstance(value, str):
                    return {
                        "status": "error",
                        "message": "Input value must be a string."
                    }

                await self.browser.fill_input(selector, value)

                return {
                    "status": "success",
                    "action": "fill",
                    "selector": selector
                }

            elif action_type == "screenshot":

                path = params.get("path", "screenshot.png")

                if not isinstance(path, str) or not path.strip():
                    return {
                        "status": "error",
                        "message": "A valid screenshot path is required."
                    }

                await self.browser.capture_screenshot(path)

                return {
                    "status": "success",
                    "action": "screenshot",
                    "path": path
                }

            else:

                return {
                    "status": "error",
                    "message": f"Unknown action type: {action_type}"
                }

        except Exception as exc:

            return {
                "status": "error",
                "message": str(exc)
            }


class FunctionalityAgent:

    def __init__(self, browser_manager: BrowserManager):
        self.browser = browser_manager
        self.executor = ToolExecutor(browser_manager)

    async def generate_test_steps(
        self,
        url: str,
        objective: str,
        max_steps: int = 8
    ) -> Dict[str, Any]:

        parsed = urlparse(url)

        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("A valid HTTP or HTTPS URL is required.")

        if not objective.strip():
            raise ValueError("A testing objective is required.")

        if not 1 <= max_steps <= 12:
            raise ValueError("max_steps must be between 1 and 12.")

        await self.browser.navigate(url)

        snapshot = await self.browser.get_interaction_snapshot()

        if not isinstance(snapshot, dict):
            raise RuntimeError("Browser returned an invalid page snapshot.")

        page_context = {
            "url": snapshot.get("url", url),
            "title": snapshot.get("title", ""),
            "headings": snapshot.get("headings", []),
            "controls": snapshot.get("controls", [])[:40],
            "page_text": str(snapshot.get("page_text", ""))[:5000]
        }

        prompt = f"""
Generate a practical browser functionality test plan.

Target URL:
{url}

Testing objective:
{objective}

Current page information:
{json.dumps(page_context, ensure_ascii=False, default=str)}

Requirements:

- Generate at most {max_steps} steps.
- Use only these actions: navigate, click, fill, screenshot.
- Start with a navigate action using the target URL.
- Use selectors that exist in the supplied page controls.
- Only fill safe, ordinary text inputs with harmless sample data.
- Never submit forms, make purchases, perform payments,
  delete data, change account settings or enter sensitive information.
- Do not invent selectors or assume controls that are not present.
- Include screenshots when useful as evidence.
- Keep the tests relevant to the stated objective.
- Return executable steps with the required action parameters.
"""

        llm_service = GeminiLLMService()

        plan = await llm_service.generate_structured(
            prompt=prompt,
            output_schema=GeneratedTestPlan,
            system_instruction=(
                "You are a software QA engineer. "
                "Generate concise, safe, evidence-based browser test plans. "
                "Never invent page controls."
            )
        )

        steps = [step.model_dump() for step in plan.steps]

        return {
            "url": url,
            "objective": plan.objective,
            "steps": steps,
            "step_count": len(steps),
            "generated_by": "gemini"
        }

    async def run_workflow(
        self,
        steps: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:

        results = []

        for index, step in enumerate(steps, start=1):

            action_type = step.get("action")
            params = step.get("params", {})

            print(
                f"Executing step {index}: "
                f"{action_type} with params {params}"
            )

            result = await self.executor.execute_action(
                action_type,
                params
            )

            result["step_index"] = index
            results.append(result)

            await asyncio.sleep(1)

        return results

    async def analyze_failures(
        self,
        url: str,
        steps: List[Dict[str, Any]],
        results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:

        failures = [
            {
                "step_index": index,
                "step": steps[index - 1] if index <= len(steps) else {},
                "result": result
            }
            for index, result in enumerate(results, start=1)
            if result.get("status") == "error"
        ]

        if not failures:
            return {
                "status": "no_failures",
                "overall_assessment": "All functionality steps succeeded.",
                "failures": []
            }

        prompt = f"""
Analyze the following browser functionality test failures.

Website:
{url}

Failed steps and execution results:
{json.dumps(failures, ensure_ascii=False, indent=2, default=str)}

For each failure:

- Identify the most likely cause based on the available evidence.
- Explain why the action may have failed.
- Recommend a specific next debugging or corrective step.
- Refer to the original step index.
- Do not invent browser behaviour or claim certainty without evidence.

Provide an overall assessment and structured failure insights.
"""

        try:

            llm_service = GeminiLLMService()

            analysis = await llm_service.generate_structured(
                prompt=prompt,
                output_schema=FailureAnalysis,
                system_instruction=(
                    "You are an experienced software debugging engineer. "
                    "Analyze execution evidence carefully. "
                    "Distinguish confirmed errors from likely causes."
                )
            )

            return {
                "status": "completed",
                **analysis.model_dump()
            }

        except LLMServiceError as exc:

            return {
                "status": "unavailable",
                "overall_assessment": (
                    "Failure analysis could not be completed because "
                    "the LLM service was unavailable."
                ),
                "failures": [],
                "error": type(exc).__name__
            }
