from typing import Any

from app.schemas.report import (
    TestReport,
    ReportFinding,
    TestStatistics,
    SeveritySummary,
)
from app.services.llm_service import GeminiLLMService


class ReportAgent:

    def __init__(self):
        self.llm = GeminiLLMService()

    async def generate_report(
        self,
        execution_result: dict[str, Any]
    ) -> TestReport:

        url = execution_result.get("url", "")
        results = execution_result.get("results", [])

        completed = sum(
            1 for item in results
            if item.get("status") == "completed"
        )

        failed = sum(
            1 for item in results
            if item.get("status") == "failed"
        )

        raw_findings = []
        strengths = []

        for item in results:
            agent = item.get("agent", "unknown")
            result = item.get("result", {})

            if agent == "uiux" and isinstance(result, dict):

                # Extract deterministic UI/UX findings
                for finding in result.get("findings", []):
                    raw_findings.append({
                        "title": finding.get(
                            "description", "UI issue"
                        ),
                        "source": "uiux",
                        "category": finding.get(
                            "category", "usability"
                        ),
                        "severity": finding.get(
                            "severity", "low"
                        ).lower(),
                        "description": finding.get(
                            "description", ""
                        ),
                        "evidence": finding.get("evidence", ""),
                        "recommendation": "",
                        "affected_url": result.get("url", url),
                        "selector": finding.get("selector"),
                        "element": finding.get("element"),
                        "viewport": finding.get("viewport"),
                        "viewports": finding.get("viewports", []),
                        "screenshot": finding.get("screenshot"),
                    })

                # Extract Gemini UX evaluation
                evaluation = result.get("llm_evaluation", {})

                for finding in evaluation.get("findings", []):
                    raw_findings.append({
                        "title": finding.get(
                            "title", "UX issue"
                        ),
                        "source": "uiux_llm_evaluation",
                        "category": finding.get(
                            "category", "usability"
                        ),
                        "severity": finding.get(
                            "severity", "low"
                        ).lower(),
                        "description": finding.get(
                            "description", ""
                        ),
                        "evidence": finding.get("evidence", ""),
                        "recommendation": finding.get(
                            "recommendation", ""
                        ),
                        "affected_url": finding.get(
                            "affected_url", url
                        ),
                    })

                strengths.extend(
                    evaluation.get("strengths", [])
                )

            # Extract agent execution failures
            if item.get("status") == "failed":
                failure = item.get("failure_analysis") or {}

                raw_findings.append({
                    "source": agent,
                    "title": f"{agent.capitalize()} test failed",
                    "category": "test_execution",
                    "severity": "high",
                    "description": (
                        failure.get("explanation")
                        or item.get(
                            "error",
                            "Agent execution failed."
                        )
                    ),
                    "evidence": item.get("error", ""),
                    "recommendation": (
                        failure.get("recommendation")
                        or "Review the failure details and rerun the test."
                    ),
                    "affected_url": url,
                })

        # Calculate severity counts deterministically
        severity_counts = {
            severity: sum(
                1 for finding in raw_findings
                if finding["severity"] == severity
            )
            for severity in (
                "critical",
                "high",
                "medium",
                "low",
            )
        }

        statistics = TestStatistics(
            total_agents=len(results),
            completed_agents=completed,
            failed_agents=failed,
            total_findings=len(raw_findings),
            severity_breakdown=SeveritySummary(
                **severity_counts
            ),
        )

        # Generate written analysis using Gemini
        prompt = f"""
You are generating a professional software testing report.

Website: {url}

Execution status:
{execution_result.get("status", "unknown")}

Execution statistics:
{statistics.model_dump()}

Collected findings:
{raw_findings}

Observed strengths:
{strengths}

Requirements:

1. Write a concise, professional executive summary.
2. Consolidate duplicate findings where appropriate.
3. Preserve the original severity of every finding.
4. Do not invent issues, evidence, or test results.
5. Include only strengths supported by the execution data.
6. Provide actionable recommendations based on actual findings.
7. Distinguish between agents and evaluation sources.
8. Use the exact agent count from the execution statistics.
9. Never describe multiple evaluation sources as separate agents.
10. Do not claim an agent passed if it failed or was not executed.

Return only the requested structured report.
"""

        report = await self.llm.generate_structured(
            prompt=prompt,
            output_schema=TestReport,
            system_instruction=(
                "You are a senior QA report analyst. "
                "Generate accurate, evidence-based software "
                "testing reports. Never fabricate test results."
            ),
        )

        # Validate findings and preserve deterministic statistics
        validated_findings = [
            ReportFinding(**finding)
            for finding in raw_findings
        ]

        return TestReport(
            url=url,
            overall_status=execution_result.get(
                "status", "unknown"
            ),
            executive_summary=report.executive_summary,
            statistics=statistics,
            strengths=list(dict.fromkeys(strengths)),
            findings=validated_findings,
            recommendations=report.recommendations,
        )
