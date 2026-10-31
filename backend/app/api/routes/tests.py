
import os
from pathlib import Path
from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, HttpUrl

from app.services.browser_manager import BrowserManager
from app.agents.functionality_agent.functionality_agent import FunctionalityAgent
from app.agents.uiux import UIUXAgent
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


class UIUXTestRequest(BaseModel):
    url: HttpUrl


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

        full_steps = [
            {"action": "navigate", "params": {"url": payload.url}}
        ] + payload.steps

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
            "screenshot": screenshot_path,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        await browser.stop()


@router.post("/run-uiux-test")
async def run_uiux_test(
    payload: UIUXTestRequest,
    request: Request,
):
    evidence_dir = "static/uiux"
    os.makedirs(evidence_dir, exist_ok=True)

    browser = BrowserManager(headless=True)

    try:
        await browser.start()

        agent = UIUXAgent(browser)
        results = await agent.run(
            str(payload.url),
            evidence_dir=evidence_dir,
        )

        for viewport in results.get("viewports", []):
            screenshot_path = viewport.get("screenshot")

            if screenshot_path:
                filename = os.path.basename(screenshot_path)
                viewport["screenshot"] = str(request.base_url).rstrip("/") + f"/static/uiux/{filename}"

        for finding in results.get("findings", []):
            screenshot_path = finding.get("screenshot")

            if screenshot_path:
                filename = os.path.basename(screenshot_path)
                finding["screenshot"] = str(request.base_url).rstrip("/") + f"/static/uiux/{filename}"

        return {
            "status": "completed",
            **results,
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        await browser.stop()
