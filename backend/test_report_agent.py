import asyncio
import os
import unittest

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_report.db")
os.environ.setdefault("SECRET_KEY", "test-secret")

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.agents.report.report_agent import ReportAgent
from app.core.database import Base
from app.models.report_record import ReportRecord
from app.schemas.report import FindingAnalysis, ReportNarrative


class FakeLLM:
    async def generate_structured(self, **kwargs):
        return ReportNarrative(
            executive_summary="The test identified one accessibility issue.",
            recommendations=["Add a semantic heading to the page."],
            finding_analysis=[
                FindingAnalysis(
                    finding_index=0,
                    root_cause="The page markup does not contain a heading element.",
                    impact="The document structure may be harder to navigate with assistive technology.",
                    reproduction_steps=["Open the target page.", "Inspect its heading structure."],
                )
            ],
        )


class ReportAgentTests(unittest.TestCase):
    def test_deduplicates_viewports_and_calculates_counts(self):
        execution = {
            "url": "https://example.com",
            "status": "partially_completed",
            "total_tasks": 3,
            "planned_agents": ["functionality", "time_simulation", "uiux"],
            "results": [
                {
                    "agent": "uiux",
                    "status": "completed",
                    "result": {
                        "url": "https://example.com",
                        "findings": [
                            {"category": "accessibility", "severity": "medium", "description": "Missing heading", "selector": "body", "viewport": "desktop"},
                            {"category": "accessibility", "severity": "medium", "description": "Missing heading", "selector": "body", "viewport": "mobile"},
                        ],
                        "llm_evaluation": {
                            "findings": [{"category": "accessibility", "severity": "low", "description": "Missing heading", "affected_url": "https://example.com"}],
                            "strengths": ["Readable layout"],
                        },
                    },
                },
                {
                    "agent": "functionality",
                    "status": "failed",
                    "error": "Button timeout",
                    "failure_analysis": {"explanation": "Button did not respond"},
                },
            ],
        }

        report = asyncio.run(ReportAgent(llm_service=FakeLLM()).generate_report(execution))

        self.assertEqual(report.statistics.total_agents, 3)
        self.assertEqual(report.statistics.completed_agents, 1)
        self.assertEqual(report.statistics.failed_agents, 1)
        self.assertEqual(report.statistics.not_run_agents, 1)
        self.assertEqual(report.statistics.total_findings, 2)
        self.assertEqual(report.statistics.severity_breakdown.medium, 1)
        self.assertEqual(report.statistics.severity_breakdown.high, 1)
        self.assertEqual(report.findings[0].viewports, ["desktop", "mobile"])
        self.assertTrue(report.findings[0].root_cause)
        self.assertEqual(report.findings[0].reproduction_steps[0], "Open the target page.")

    def test_functionality_action_error_becomes_finding(self):
        execution = {
            "url": "https://example.com",
            "status": "completed",
            "planned_agents": ["functionality"],
            "results": [{
                "agent": "functionality",
                "status": "completed",
                "result": [{"status": "error", "action": "click", "message": "Element not found", "step_index": 2}],
            }],
        }
        report = asyncio.run(ReportAgent().generate_report(execution))
        self.assertEqual(report.statistics.total_findings, 1)
        self.assertEqual(report.findings[0].category, "functionality")
        self.assertEqual(report.statistics.severity_breakdown.high, 1)

    def test_functionality_failure_analysis_preserves_each_step(self):
        execution = {
            "url": "https://example.com",
            "status": "failed",
            "planned_agents": ["functionality"],
            "results": [{
                "agent": "functionality",
                "status": "failed",
                "error": "One or more functionality steps failed.",
                "failure_analysis": {
                    "overall_assessment": "A click action failed.",
                    "failures": [{
                        "step_index": 3,
                        "action": "click",
                        "likely_cause": "The target was not found.",
                        "explanation": "The selector did not match an element.",
                        "recommendation": "Check the selector.",
                    }],
                },
            }],
        }
        report = asyncio.run(ReportAgent().generate_report(execution))
        self.assertEqual(report.statistics.total_findings, 1)
        self.assertEqual(report.findings[0].category, "functionality")
        self.assertIn("step 3", report.findings[0].title.lower())
        self.assertEqual(report.findings[0].recommendation, "Check the selector.")

    def test_time_simulation_timer_errors_become_findings(self):
        execution = {
            "url": "https://example.com",
            "status": "completed",
            "planned_agents": ["time_simulation"],
            "results": [{
                "agent": "time_simulation",
                "status": "completed",
                "result": {"mode": "standalone", "timer_errors": [{"timer_id": 2, "message": "Callback crashed"}]},
            }],
        }
        report = asyncio.run(ReportAgent().generate_report(execution))
        self.assertEqual(report.statistics.total_findings, 1)
        self.assertEqual(report.findings[0].source, "time_simulation")

    def test_empty_results_fallback_and_not_run_agents(self):
        report = asyncio.run(ReportAgent().generate_report({
            "url": "https://example.com",
            "status": "failed",
            "total_tasks": 2,
            "planned_agents": ["functionality", "uiux"],
            "results": [],
        }))
        self.assertEqual(report.statistics.total_agents, 2)
        self.assertEqual(report.statistics.not_run_agents, 2)
        self.assertEqual(report.statistics.total_findings, 0)
        self.assertIn("2 were not run", report.executive_summary)

    def test_report_record_persists_json(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        payload = {"url": "https://example.com", "overall_status": "completed", "findings": []}
        with Session(engine) as session:
            record = ReportRecord(url=payload["url"], overall_status=payload["overall_status"], report_json=payload)
            session.add(record)
            session.commit()
            session.refresh(record)
            loaded = session.get(ReportRecord, record.id)
            self.assertEqual(loaded.report_json, payload)
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
