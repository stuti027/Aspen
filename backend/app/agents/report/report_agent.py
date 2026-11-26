import re
from typing import Any

from app.schemas.report import (
    FindingAnalysis,
    ReportFinding,
    ReportNarrative,
    SeveritySummary,
    TestReport,
    TestStatistics,
)

VALID_SEVERITIES = {"critical", "high", "medium", "low"}
SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip() or default
    return str(value).strip() or default


def _severity(value: Any) -> str:
    candidate = _text(value, "low").lower()
    return candidate if candidate in VALID_SEVERITIES else "low"


def _normalise(value: Any) -> str:
    return re.sub(r"\s+", " ", _text(value).lower())


class ReportAgent:
    """Builds evidence-based reports; Gemini enriches, never controls, metrics."""

    def __init__(self, llm_service=None):
        # Lazy initialisation keeps deterministic report generation available
        # when Gemini credentials or the provider are unavailable.
        self.llm = llm_service

    @staticmethod
    def _deduplicate(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: dict[tuple[str, str, str], dict[str, Any]] = {}

        for finding in findings:
            key = (
                _normalise(finding.get("category")),
                _normalise(finding.get("description")),
                _normalise(finding.get("affected_url")),
            )
            current = merged.get(key)
            if current is None:
                current = dict(finding)
                current["_sources"] = []
                current["viewports"] = list(finding.get("viewports") or [])
                merged[key] = current

            source = _text(finding.get("source"), "unknown")
            if source not in current["_sources"]:
                current["_sources"].append(source)

            if SEVERITY_RANK[_severity(finding.get("severity"))] > SEVERITY_RANK[_severity(current.get("severity"))]:
                current["severity"] = _severity(finding.get("severity"))

            for field in ("title", "evidence", "recommendation", "screenshot", "element", "selector"):
                if not current.get(field) and finding.get(field):
                    current[field] = finding[field]

            if finding.get("viewport"):
                current["viewports"].append(finding["viewport"])
            current["viewports"].extend(finding.get("viewports") or [])

        output = []
        for finding in merged.values():
            finding["source"] = ", ".join(finding.pop("_sources"))
            finding["viewports"] = list(dict.fromkeys(
                value for value in finding.get("viewports", []) if value
            ))
            if not finding.get("viewport") and finding["viewports"]:
                finding["viewport"] = finding["viewports"][0]
            output.append(finding)
        return output

    def _collect(
        self,
        execution_result: dict[str, Any],
        url: str,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        findings: list[dict[str, Any]] = []
        strengths: list[str] = []

        def add(
            source: str,
            title: Any,
            category: Any,
            severity: Any,
            description: Any,
            **extra: Any,
        ) -> None:
            description_text = _text(description)
            if not description_text:
                return
            findings.append({
                "title": _text(title, "Test finding"),
                "source": source,
                "category": _text(category, "general"),
                "severity": _severity(severity),
                "description": description_text,
                "evidence": _text(extra.get("evidence")),
                "recommendation": _text(extra.get("recommendation")),
                "affected_url": _text(extra.get("affected_url"), url),
                "selector": extra.get("selector"),
                "element": extra.get("element"),
                "viewport": extra.get("viewport"),
                "viewports": extra.get("viewports") or [],
                "screenshot": extra.get("screenshot"),
            })

        results = execution_result.get("results", [])
        if not isinstance(results, list):
            results = []

        for item in results:
            if not isinstance(item, dict):
                continue

            agent = _text(item.get("agent"), "unknown")
            result = item.get("result")

            if agent == "uiux":
                if not isinstance(result, dict):
                    result = {}
                for finding in result.get("findings", []) or []:
                    if not isinstance(finding, dict):
                        continue
                    description = finding.get("description", "")
                    add(
                        "uiux",
                        finding.get("title") or description,
                        finding.get("category", "usability"),
                        finding.get("severity", "low"),
                        description,
                        evidence=finding.get("evidence"),
                        recommendation=finding.get("recommendation"),
                        affected_url=finding.get("affected_url") or result.get("url") or url,
                        selector=finding.get("selector"),
                        element=finding.get("element"),
                        viewport=finding.get("viewport"),
                        viewports=finding.get("viewports", []),
                        screenshot=finding.get("screenshot"),
                    )

                evaluation = result.get("llm_evaluation") or {}
                if not isinstance(evaluation, dict):
                    evaluation = {}
                for finding in evaluation.get("findings", []) or []:
                    if not isinstance(finding, dict):
                        continue
                    add(
                        "uiux_llm_evaluation",
                        finding.get("title", "UX issue"),
                        finding.get("category", "usability"),
                        finding.get("severity", "low"),
                        finding.get("description", ""),
                        evidence=finding.get("evidence"),
                        recommendation=finding.get("recommendation"),
                        affected_url=finding.get("affected_url") or url,
                    )
                strengths.extend(
                    _text(value) for value in evaluation.get("strengths", []) or []
                    if _text(value)
                )

            if agent == "functionality":
                steps = result if isinstance(result, list) else (
                    result.get("steps", []) if isinstance(result, dict) else []
                )
                for step in steps or []:
                    if not isinstance(step, dict):
                        continue
                    if step.get("status") in {"error", "failed"}:
                        action = _text(step.get("action"), "action")
                        step_index = step.get("step_index", "?")
                        add(
                            "functionality",
                            f"Functionality step {step_index} failed: {action}",
                            "functionality",
                            "high",
                            step.get("message") or step.get("error") or "A functionality action failed.",
                            evidence=str(step),
                            recommendation="Inspect the failed action, verify its selector and preconditions, then rerun the test.",
                        )
                    for timer_error in step.get("timer_errors", []) or []:
                        if isinstance(timer_error, dict):
                            add(
                                "time_simulation",
                                "Simulated timer callback failed",
                                "time_simulation",
                                "high",
                                timer_error.get("message") or "A simulated timer callback failed.",
                                evidence=str(timer_error),
                                recommendation="Inspect the timer callback and rerun the time simulation.",
                            )

            if agent == "time_simulation" and isinstance(result, dict):
                for timer_error in result.get("timer_errors", []) or []:
                    if isinstance(timer_error, dict):
                        add(
                            "time_simulation",
                            "Simulated timer callback failed",
                            "time_simulation",
                            "high",
                            timer_error.get("message") or "A simulated timer callback failed.",
                            evidence=str(timer_error),
                            recommendation="Inspect the timer callback and rerun the time simulation.",
                        )

            if item.get("status") == "failed":
                failure = item.get("failure_analysis") or {}
                if not isinstance(failure, dict):
                    failure = {}

                # Functionality failures may contain a structured insight for
                # each failed action. Preserve those individual details.
                insights = failure.get("failures", []) or []
                if agent == "functionality" and insights:
                    for insight in insights:
                        if not isinstance(insight, dict):
                            continue
                        step_index = insight.get("step_index", "?")
                        action = _text(insight.get("action"), "action")
                        add(
                            agent,
                            f"Functionality step {step_index} failed: {action}",
                            "functionality",
                            "high",
                            insight.get("explanation") or insight.get("likely_cause") or "A functionality action failed.",
                            evidence=f"Step {step_index}; action: {action}; likely cause: {_text(insight.get('likely_cause'))}",
                            recommendation=insight.get("recommendation") or "Inspect the failed action and rerun the test.",
                        )

                if not (agent == "functionality" and insights):
                    add(
                        agent,
                        f"{agent.replace('_', ' ').title()} test failed",
                        "test_execution",
                        "high",
                        failure.get("explanation")
                        or failure.get("overall_assessment")
                        or item.get("error")
                        or "Agent execution failed.",
                        evidence=_text(item.get("error")),
                        recommendation=failure.get("recommendation")
                        or "Review the execution error and supporting logs, correct the issue, and rerun the agent.",
                    )

        return self._deduplicate(findings), list(dict.fromkeys(strengths))

    async def _generate_narrative(
        self,
        url: str,
        status: str,
        findings: list[dict[str, Any]],
        strengths: list[str],
        statistics: TestStatistics,
    ) -> ReportNarrative | None:
        try:
            if self.llm is None:
                from app.services.llm_service import GeminiLLMService
                self.llm = GeminiLLMService()

            prompt = f"""
Prepare the narrative for this software testing report.
Target URL: {url}
Execution status: {status}
Deterministic agent statistics: {statistics.model_dump()}
Findings in stable index order: {findings}
Observed strengths: {strengths}

Return one finding_analysis item for each supplied finding index when useful.
Only state a root cause when supported by the evidence. Otherwise explicitly
say it cannot be determined. Describe impact conservatively. Provide
reproduction steps only when the evidence supports specific steps; otherwise
use an empty list. Do not invent pages, selectors, actions, evidence, or test
outcomes. Do not change findings, severities, or statistics. Recommendations
must be directly grounded in the supplied findings.
"""
            response = await self.llm.generate_structured(
                prompt=prompt,
                output_schema=ReportNarrative,
                system_instruction=(
                    "You are a careful senior QA analyst. Never fabricate "
                    "evidence, causes, reproduction steps, or test outcomes."
                ),
            )
            return response if isinstance(response, ReportNarrative) else ReportNarrative.model_validate(response)
        except Exception:
            # Reporting must still succeed when Gemini is unconfigured,
            # rate-limited, unavailable, or returns an invalid response.
            return None

    @staticmethod
    def _fallback_recommendation(finding: dict[str, Any]) -> str:
        category = _text(finding.get("category")).lower()
        if category in {"accessibility", "ui_analysis"}:
            return "Review the affected page structure and apply appropriate semantic HTML and accessibility practices."
        if category in {"interaction", "usability", "interaction_quality"}:
            return "Review the affected interaction and provide a clear, usable interaction pattern."
        if category == "functionality":
            return "Verify the failed action's selector, target element, and preconditions before rerunning the test."
        if category in {"test_execution", "time_simulation"}:
            return "Inspect the execution error and supporting logs, correct the underlying issue, and rerun the affected agent."
        return "Review the finding's evidence, address the identified issue, and rerun the relevant test."

    async def generate_report(self, execution_result: dict[str, Any]) -> TestReport:
        if not isinstance(execution_result, dict):
            raise TypeError("execution_result must be a dictionary.")

        url = _text(execution_result.get("url"))
        if not url:
            raise ValueError("execution_result must contain a target URL.")

        results = execution_result.get("results", [])
        if not isinstance(results, list):
            results = []
        valid_results = [item for item in results if isinstance(item, dict)]

        completed = sum(item.get("status") == "completed" for item in valid_results)
        failed = sum(item.get("status") == "failed" for item in valid_results)
        planned_agents = execution_result.get("planned_agents")
        if isinstance(planned_agents, list):
            total = len(set(_text(agent) for agent in planned_agents if _text(agent)))
        else:
            total = execution_result.get("total_tasks", len(valid_results))
        if not isinstance(total, int) or total < completed + failed:
            total = completed + failed
        not_run = max(0, total - completed - failed)

        findings, strengths = self._collect(execution_result, url)
        severity_counts = {
            level: sum(finding["severity"] == level for finding in findings)
            for level in ("critical", "high", "medium", "low")
        }
        statistics = TestStatistics(
            total_agents=total,
            completed_agents=completed,
            failed_agents=failed,
            not_run_agents=not_run,
            total_findings=len(findings),
            severity_breakdown=SeveritySummary(**severity_counts),
        )

        status = _text(execution_result.get("status"), "unknown")
        narrative = await self._generate_narrative(
            url, status, findings, strengths, statistics
        )

        analysis_by_index: dict[int, FindingAnalysis] = {}
        if narrative:
            for analysis in narrative.finding_analysis:
                if 0 <= analysis.finding_index < len(findings):
                    analysis_by_index[analysis.finding_index] = analysis

        validated_findings = []
        for index, finding in enumerate(findings):
            analysis = analysis_by_index.get(index)
            validated_findings.append(ReportFinding(
                **finding,
                root_cause=(analysis.root_cause if analysis and _text(analysis.root_cause)
                            else "Not determined from the available evidence."),
                impact=(analysis.impact if analysis and _text(analysis.impact)
                        else "Impact could not be determined from the available evidence."),
                reproduction_steps=(analysis.reproduction_steps if analysis else []),
            ))

        recommendations = []
        for finding in findings:
            recommendation = _text(finding.get("recommendation")) or self._fallback_recommendation(finding)
            if recommendation not in recommendations:
                recommendations.append(recommendation)
        if narrative:
            for recommendation in narrative.recommendations:
                recommendation = _text(recommendation)
                if recommendation and recommendation not in recommendations:
                    recommendations.append(recommendation)

        severity = statistics.severity_breakdown
        fallback_summary = (
            f"Testing of {url} finished with status '{status}'. "
            f"{completed} of {total} planned agents completed, {failed} failed, "
            f"and {not_run} were not run. The report contains {len(findings)} "
            f"unique findings: {severity.critical} critical, {severity.high} high, "
            f"{severity.medium} medium and {severity.low} low."
        )

        return TestReport(
            url=url,
            overall_status=status,
            executive_summary=(
                (
                    _text(narrative.executive_summary)
                    if "were not run" in _text(narrative.executive_summary).lower()
                    else (
                        _text(narrative.executive_summary)
                        + f" Additionally, {not_run} were not run."
                    )
                )
                if narrative and not_run > 0
                else (
                    _text(narrative.executive_summary)
                    if narrative
                    else fallback_summary
                )
            ),
            statistics=statistics,
            strengths=strengths,
            findings=validated_findings,
            recommendations=recommendations,
        )
