import os
from pathlib import Path
from typing import List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, HttpUrl

from app.services.browser_manager import BrowserManager
from app.agents.functionality_agent.functionality_agent import FunctionalityAgent
from app.agents.uiux import UIUXAgent
from app.agents.time_simulation_agent.time_simulator import TimeSimulator
from pydantic import Field
from sqlalchemy import desc
from app.agents.orchestration import OrchestrationAgent
from app.core.database import get_db
from app.models.report_record import ReportRecord
from sqlalchemy.orm import Session

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

class OrchestrationRequest(BaseModel):
    url: str
    selected_agents: List[str]
    functionality_steps: List[Dict[str, Any]] = Field(default_factory=list)
    time_jump_ms: int = Field(default=0, ge=0)
    max_retries: int = Field(default=1, ge=0)


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
        backend_dir = current_file_dir.parents[2]
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

@router.post("/run-orchestration-test")
async def run_orchestration_test(
    payload: OrchestrationRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    browser = BrowserManager(headless=True)

    try:
        await browser.start()
        orchestrator = OrchestrationAgent(browser)

        test_plan = orchestrator.create_test_plan(
            url=payload.url,
            selected_agents=payload.selected_agents,
            functionality_steps=payload.functionality_steps,
            time_jump_ms=payload.time_jump_ms,
        )
        results = await orchestrator.execute_plan(
            test_plan,
            max_retries=payload.max_retries,
        )

        base_url = str(request.base_url).rstrip("/")

        def convert_screenshot_urls(uiux_result: dict[str, Any]) -> None:
            if not isinstance(uiux_result, dict):
                return
            for viewport in uiux_result.get("viewports", []):
                screenshot_path = viewport.get("screenshot")
                if screenshot_path:
                    filename = os.path.basename(screenshot_path.replace("\\", "/"))
                    viewport["screenshot"] = f"{base_url}/static/uiux/{filename}"
            for finding in uiux_result.get("findings", []):
                screenshot_path = finding.get("screenshot")
                if screenshot_path:
                    filename = os.path.basename(screenshot_path.replace("\\", "/"))
                    finding["screenshot"] = f"{base_url}/static/uiux/{filename}"

        for item in results.get("results", []):
            if item.get("agent") == "uiux":
                convert_screenshot_urls(item.get("result", {}))

        shared_uiux = (
            results.get("shared_context", {})
            .get("completed_results", {})
            .get("uiux")
        )
        if shared_uiux:
            convert_screenshot_urls(shared_uiux)

        # The report is generated inside orchestration before URL conversion.
        # Rewrite its screenshot paths before returning and persisting it.
        report_data = results.get("report")
        if isinstance(report_data, dict):
            for finding in report_data.get("findings", []):
                screenshot_path = finding.get("screenshot")
                if screenshot_path:
                    filename = os.path.basename(screenshot_path.replace("\\", "/"))
                    finding["screenshot"] = f"{base_url}/static/uiux/{filename}"

            record = ReportRecord(
                url=report_data["url"],
                overall_status=report_data["overall_status"],
                report_json=report_data,
            )
            try:
                db.add(record)
                db.commit()
                db.refresh(record)
            except Exception:
                db.rollback()
                raise
            results["report_id"] = record.id

        return {
            "status": results["status"],
            "agent": "orchestration",
            "test_plan": test_plan,
            "execution_results": results,
        }

    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        await browser.stop()


@router.get("/reports")
async def list_test_reports(
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 100.")
    if offset < 0:
        raise HTTPException(status_code=422, detail="offset cannot be negative.")

    records = (
        db.query(ReportRecord)
        .order_by(desc(ReportRecord.created_at), desc(ReportRecord.id))
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "items": [
            {
                "id": record.id,
                "url": record.url,
                "overall_status": record.overall_status,
                "created_at": record.created_at.isoformat(),
            }
            for record in records
        ],
        "limit": limit,
        "offset": offset,
    }


@router.get("/reports/{report_id}")
async def get_test_report(
    report_id: int,
    db: Session = Depends(get_db),
):
    report_record = db.get(ReportRecord, report_id)
    if report_record is None:
        raise HTTPException(status_code=404, detail="Test report not found.")

    return {
        "id": report_record.id,
        "url": report_record.url,
        "overall_status": report_record.overall_status,
        "created_at": report_record.created_at.isoformat(),
        "report": report_record.report_json,
    }
