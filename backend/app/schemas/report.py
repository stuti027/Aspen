from typing import Literal

from pydantic import BaseModel, Field


Severity = Literal["critical", "high", "medium", "low"]


class ReportFinding(BaseModel):
    title: str
    source: str
    category: str
    severity: Severity
    description: str
    evidence: str = ""
    recommendation: str = ""
    affected_url: str = ""
    selector: str | None = None
    element: str | None = None
    viewport: str | None = None
    viewports: list[str] = Field(default_factory=list)
    screenshot: str | None = None


class SeveritySummary(BaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0


class TestStatistics(BaseModel):
    total_agents: int = 0
    completed_agents: int = 0
    failed_agents: int = 0
    total_findings: int = 0
    severity_breakdown: SeveritySummary = Field(
        default_factory=SeveritySummary
    )


class TestReport(BaseModel):
    url: str
    overall_status: str
    executive_summary: str
    statistics: TestStatistics
    strengths: list[str] = Field(default_factory=list)
    findings: list[ReportFinding] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)