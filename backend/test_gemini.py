import asyncio
from pathlib import Path

from pydantic import BaseModel, Field

from app.services.llm_service import GeminiLLMService


class VisualFinding(BaseModel):
    issue: str
    user_impact: str
    recommendation: str
    confidence: str = Field(
        description="High, medium, or low"
    )


class VisualEvaluation(BaseModel):
    overall_assessment: str
    strengths: list[str]
    findings: list[VisualFinding]


async def main():
    try:
        screenshot = Path("artifacts/uiux/desktop.png")

        if not screenshot.is_file():
            raise FileNotFoundError(
                f"Screenshot not found: {screenshot}. "
                "Run the existing UIUX test first."
            )

        llm_service = GeminiLLMService()

        result = await llm_service.generate_structured(
            prompt="""
            Evaluate this website screenshot from the perspective
            of a real human visitor.

            Assess:
            - Visual hierarchy and clarity
            - Layout balance and consistency
            - Ease of understanding the interface
            - Discoverability of important actions
            - Overall visual experience

            Identify genuine usability or visual experience problems.
            Do not invent issues that cannot be supported by the image.
            Do not repeat basic technical accessibility checks.

            Also identify what the website does well.
            """,
            output_schema=VisualEvaluation,
            system_instruction=(
                "You are an experienced UX researcher and "
                "human-centered website evaluator."
            ),
            image_paths=[str(screenshot)]
        )

        print("\nOverall Assessment:")
        print(result.overall_assessment)

        print("\nStrengths:")
        for strength in result.strengths:
            print(f"- {strength}")

        print("\nHuman UX Findings:")
        for finding in result.findings:
            print(f"\nIssue: {finding.issue}")
            print(f"User Impact: {finding.user_impact}")
            print(f"Recommendation: {finding.recommendation}")
            print(f"Confidence: {finding.confidence}")

        print("\nVISION EVALUATION TEST PASSED")

    except Exception as e:
        print(f"\nVISION EVALUATION TEST FAILED: {e}")


if __name__ == "__main__":
    asyncio.run(main())