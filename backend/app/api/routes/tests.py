import os
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
from app.services.browser_manager import BrowserManager
from app.agents.functionality_agent.functionality_agent import FunctionalityAgent
from app.agents.time_simulation_agent.time_simulator import TimeSimulator

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
    enable_time_simulation: bool = False
    time_jump_ms: int = 0

@router.post("/run-custom-test")
async def run_custom_test(payload: TestExecutionRequest):
    browser = BrowserManager(headless=True)
    try:
        await browser.start()
        await browser.enable_monitoring()

        if payload.enable_time_simulation:
            time_sim = TimeSimulator(browser)
            await time_sim.install_fake_clock()
            if payload.time_jump_ms > 0:
                await time_sim.install_fake_clock(initial_offset_ms=payload.time_jump_ms)

        agent = FunctionalityAgent(browser)
        full_steps = [{"action": "navigate", "params": {"url": payload.url}}] + payload.steps
        results = await agent.run_workflow(full_steps)

        current_file_dir = Path(__file__).resolve().parent
        backend_dir = current_file_dir.parents[1]
        static_dir = backend_dir / "static"
        os.makedirs(static_dir, exist_ok=True)
        screenshot_path = os.path.join(static_dir, "latest_screenshot.png")
        await browser.capture_screenshot(screenshot_path)

        simulated_time = None
        if payload.enable_time_simulation:
            simulated_time = await time_sim.get_current_simulated_time()

        return {
            "status": "completed",
            "url": payload.url,
            "simulated_timestamp": simulated_time,
            "results": results,
            "screenshot": screenshot_path
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await browser.stop()