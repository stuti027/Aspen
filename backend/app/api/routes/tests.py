import os
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
from app.services.browser_manager import BrowserManager
from app.agents.functionality_agent import FunctionalityAgent

router = APIRouter(
    prefix="/tests",
    tags=["Tests"],
)

@router.get("/")
async def get_tests():
    return {"message": "Tests endpoint"}

class TestExecutionRequest(BaseModel):
    url: str
    steps: List[Dict[str, Any]]

@router.post("/run-custom-test")
async def run_custom_test(payload: TestExecutionRequest):
    os.makedirs("backend/static", exist_ok=True)
    browser = BrowserManager(headless=True)
    try:
        await browser.start()
        await browser.enable_monitoring()

        agent = FunctionalityAgent(browser)
        
        full_steps = [{"action": "navigate", "params": {"url": payload.url}}] + payload.steps
        results = await agent.run_workflow(full_steps)

        screenshot_path = "backend/static/latest_screenshot.png"
        await browser.capture_screenshot(screenshot_path)

        return {
            "status": "completed",
            "url": payload.url,
            "results": results,
            "screenshot": screenshot_path
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await browser.stop()