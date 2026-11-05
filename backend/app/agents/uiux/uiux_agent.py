import asyncio
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.services.browser_manager import BrowserManager
from pydantic import BaseModel, Field
from typing import Literal
import json

from app.services.llm_service import (
    GeminiLLMService,
    LLMServiceError
)


UI_SCAN_SCRIPT = r"""
(() => {
    const findings = [];

    const selectorFor = (el) => {
        if (el.id) return `#${CSS.escape(el.id)}`;

        const tag = el.tagName.toLowerCase();
        const classes = Array.from(el.classList)
            .slice(0, 2)
            .map(c => `.${CSS.escape(c)}`)
            .join("");

        return `${tag}${classes}`;
    };

    const add = (category, severity, description, el, evidence = "") => {
        findings.push({
            category,
            severity,
            description,
            selector: el ? selectorFor(el) : "document",
            element: el ? el.outerHTML.slice(0, 250) : null,
            evidence
        });
    };

    const isVisible = (el) => {
        const style = getComputedStyle(el);
        const rect = el.getBoundingClientRect();

        return style.display !== "none"
            && style.visibility !== "hidden"
            && Number(style.opacity) > 0
            && rect.width > 0
            && rect.height > 0;
    };

    // Page structure and landmarks
    if (!document.title.trim()) {
        add("ui_analysis", "high", "Page has no document title.", null);
    }

    if (!document.documentElement.lang) {
        add("accessibility", "medium",
            "HTML element is missing its language attribute.", null);
    }

    if (!document.querySelector('meta[name="viewport"]')) {
        add("responsiveness", "medium",
            "Page is missing the viewport meta tag.", null);
    }

    if (!document.querySelector("main, [role='main']")) {
        add("ui_analysis", "low",
            "Page has no main landmark.", null);
    }

    // Heading structure
    const allHeadings = Array.from(
        document.querySelectorAll("h1, h2, h3, h4, h5, h6")
    );

    const headings = allHeadings.filter(isVisible);

    if (allHeadings.length === 0) {
        add(
            "ui_analysis",
            "medium",
            "Page contains no heading elements.",
            null
        );
    } else if (headings.length === 0) {
        add(
            "ui_analysis",
            "low",
            "Heading elements exist, but none are visible.",
            null
        );
    }

    let previousLevel = 0;

    for (const heading of headings) {
        const level = Number(heading.tagName.substring(1));

        if (previousLevel && level > previousLevel + 1) {
            add("accessibility", "low",
                `Heading hierarchy skips from h${previousLevel} to h${level}.`,
                heading);
        }

        if (!heading.textContent.trim()) {
            add("accessibility", "medium",
                "Heading has no text content.", heading);
        }

        previousLevel = level;
    }

    // Images
    for (const img of document.querySelectorAll("img")) {
        if (!img.hasAttribute("alt")) {
            add("accessibility", "medium",
                "Image is missing its alt attribute.", img);
        }

        if (img.complete && img.naturalWidth === 0 && img.src) {
            add(
                "visual_issue",
                "medium",
                "Image appears broken or failed to load.",
                img,
                img.src
            );
        } else if (
            !img.complete &&
            img.src &&
            img.loading !== "lazy" &&
            isVisible(img)
        ) {
            add(
                "visual_issue",
                "low",
                "Visible image has not finished loading.",
                img,
                img.src
            );
        }

        if (isVisible(img) &&
            img.getBoundingClientRect().right > window.innerWidth + 1) {
            add("layout", "medium",
                "Image extends beyond the viewport width.", img);
        }
    }

    // Form labels and accessible names
    for (const input of document.querySelectorAll(
        "input:not([type='hidden']):not([type='submit']):not([type='button']), textarea, select"
    )) {
        const hasLabel =
            Array.from(input.labels || []).some(
                label => label.textContent.trim().length > 0
            ) ||
            Boolean(input.closest("label")?.textContent.trim()) ||
            Boolean(input.getAttribute("aria-label")?.trim()) ||
            Boolean(
                input.getAttribute("aria-labelledby")
                    ?.split(/\s+/)
                    .some(id => document.getElementById(id)?.textContent.trim())
            );

        if (!hasLabel) {
            add("accessibility", "high",
                "Form control has no detectable accessible label.", input);
        }
    }

    const getAccessibleName = (el) => {
        const labelledBy = (el.getAttribute("aria-labelledby") || "")
            .split(/\s+/)
            .filter(Boolean)
            .map(id => {
                const referenced = document.getElementById(id);
                return referenced?.textContent
                    ?.replace(/\s+/g, " ")
                    .trim() || "";
            })
            .filter(Boolean)
            .join(" ");

        const ariaLabel = el.getAttribute("aria-label")?.trim();
        const title = el.getAttribute("title")?.trim();

        const visibleText = (
            el.innerText ||
            el.textContent ||
            ""
        ).replace(/\s+/g, " ").trim();

        const textContent = (
            el.textContent || ""
        ).replace(/\s+/g, " ").trim();

        const value = (
            el.matches("input[type='button'], input[type='submit'], input[type='reset']")
                ? el.value
                : ""
        ).trim();

        const imageAlt = Array.from(el.querySelectorAll("img[alt]"))
            .map(img => img.alt.trim())
            .filter(Boolean)
            .join(" ");

        const svgTitle = Array.from(el.querySelectorAll("svg title"))
            .map(titleElement => titleElement.textContent.trim())
            .filter(Boolean)
            .join(" ");

        return (
            ariaLabel ||
            labelledBy ||
            visibleText ||
            textContent ||
            value ||
            imageAlt ||
            svgTitle ||
            title ||
            ""
        );
    };

    // Buttons and interactive targets
    for (const button of document.querySelectorAll(
        "button, input[type='submit'], input[type='button'], [role='button']"
    )) {
        if (!getAccessibleName(button).trim()) {
            add("accessibility", "high",
                "Button has no detectable accessible name.", button);
        }

        if (isVisible(button)) {
            const rect = button.getBoundingClientRect();

            if (rect.width < 24 || rect.height < 24) {
                add(
                    "usability",
                    "low",
                    "Interactive target is smaller than 24 by 24 CSS pixels.",
                    button,
                    `${Math.round(rect.width)}x${Math.round(rect.height)} px`
                );
            }

            if (
                rect.right < 0 ||
                rect.bottom < 0 ||
                rect.left > window.innerWidth ||
                rect.top > window.innerHeight
            ) {
                add(
                    "layout",
                    "medium",
                    "Interactive element is positioned outside the visible viewport.",
                    button,
                    `Position: left=${Math.round(rect.left)}, top=${Math.round(rect.top)}, width=${Math.round(rect.width)}, height=${Math.round(rect.height)}`
                );
            }
        }

        if (button.disabled) {
            add("interaction_quality", "low",
                "Visible control is disabled.", button);
        }
    }

    // Links
    for (const link of document.querySelectorAll("a")) {
        if (!getAccessibleName(link).trim()) {
            add(
                "accessibility",
                "medium",
                "Link has no detectable accessible name.",
                link
            );
        }

        if (
            !link.getAttribute("href") &&
            !link.hasAttribute("role") &&
            !link.hasAttribute("onclick")
        ) {
            add(
                "usability",
                "low",
                "Link has no href or detectable interaction handler.",
                link
            );
        }

        const href = link.getAttribute("href")?.trim();

        if (
            href === "#" ||
            href === "" ||
            href?.toLowerCase().startsWith("javascript:")
        ) {
            add(
                "usability",
                "medium",
                "Link has a placeholder or non-navigational destination.",
                link,
                `href="${href}"`
            );
        }
    }

    // Layout overflow and offending elements
    const doc = document.documentElement;

    if (doc.scrollWidth > window.innerWidth + 1) {
        add(
            "layout",
            "high",
            "Page has horizontal overflow at this viewport.",
            doc,
            `Content width: ${doc.scrollWidth}px; viewport width: ${window.innerWidth}px`
        );

        const overflowingElements = Array.from(
            document.querySelectorAll("body *")
        ).filter(el => {
            if (!isVisible(el)) return false;

            const rect = el.getBoundingClientRect();

            return (
                rect.right > window.innerWidth + 1 ||
                rect.left < -1
            );
        });

        for (const el of overflowingElements.slice(0, 10)) {
            const rect = el.getBoundingClientRect();

            add(
                "layout",
                "medium",
                "Element extends beyond the horizontal viewport boundary.",
                el,
                `Element bounds: left=${Math.round(rect.left)}px, right=${Math.round(rect.right)}px, viewport=${window.innerWidth}px`
            );
        }
    }

    // Potential text visibility issues
    for (const el of document.querySelectorAll("p, span, label, li, a, button")) {
        if (!isVisible(el) || !el.textContent.trim()) continue;

        const style = getComputedStyle(el);
        const fontSize = parseFloat(style.fontSize);

        if (fontSize > 0 && fontSize < 12) {
            add("visual_issue", "low",
                "Text uses a font size below 12 CSS pixels.", el,
                `Font size: ${style.fontSize}`);
        }
        const parseColor = (color) => {
            const match = color.match(
                /rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([\d.]+))?\s*\)/
            );

            if (!match) return null;

            return {
                r: Number(match[1]),
                g: Number(match[2]),
                b: Number(match[3]),
                a: match[4] === undefined ? 1 : Number(match[4])
            };
        };

        const foreground = parseColor(style.color);
        const background = parseColor(style.backgroundColor);

        if (
            foreground &&
            background &&
            background.a === 1 &&
            foreground.a === 1
        ) {
            const luminance = (color) => {
                const channels = [color.r, color.g, color.b].map(value => {
                    const channel = value / 255;
                    return channel <= 0.04045
                        ? channel / 12.92
                        : Math.pow((channel + 0.055) / 1.055, 2.4);
                });

                return (
                    0.2126 * channels[0] +
                    0.7152 * channels[1] +
                    0.0722 * channels[2]
                );
            };

            const l1 = luminance(foreground);
            const l2 = luminance(background);
            const contrast = (Math.max(l1, l2) + 0.05) /
                            (Math.min(l1, l2) + 0.05);

            if (contrast < 4.5) {
                add(
                    "accessibility",
                    "medium",
                    "Text may have insufficient color contrast.",
                    el,
                    `Contrast ratio: ${contrast.toFixed(2)}:1`
                );
            }
        }
    }

    return {
        title: document.title,
        url: window.location.href,
        viewport: {
            width: window.innerWidth,
            height: window.innerHeight
        },
        findings
    };
})()
"""

class BrowserAction(BaseModel):
    action: Literal[
        "click",
        "scroll",
        "fill",
        "finish"
    ]

    selector: str | None = None
    value: str | None = None

    direction: Literal["up", "down"] | None = None
    amount: int = Field(default=500, ge=100, le=1500)

    reason: str


class ExplorationDecision(BaseModel):
    observation: str
    actions: list[BrowserAction] = Field(max_length=1)
    evaluation: str

class UXFinding(BaseModel):
    title: str
    category: Literal[
        "navigation",
        "visual_hierarchy",
        "clarity",
        "interaction",
        "content",
        "usability",
        "user_friction"
    ]
    severity: Literal["critical", "high", "medium", "low"]
    description: str
    evidence: str
    recommendation: str
    affected_url: str


class UXEvaluation(BaseModel):
    overall_summary: str
    strengths: list[str]
    findings: list[UXFinding]

class UIUXAgent:
    VIEWPORTS = [
        {"name": "desktop", "width": 1440, "height": 900},
        {"name": "tablet", "width": 768, "height": 1024},
        {"name": "mobile", "width": 390, "height": 844},
    ]

    SEVERITY_ORDER = {
        "critical": 0,
        "high": 1,
        "medium": 2,
        "low": 3,
    }

    def __init__(self, browser: BrowserManager):
        self.browser = browser

    async def run(
        self,
        url: str,
        evidence_dir: str = "artifacts/uiux",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        parsed_url = urlparse(url)

        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("A valid HTTP or HTTPS URL is required.")

        output_dir = Path(evidence_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        await self.browser.navigate(url)
        results = []
        findings = []

        try:
            for viewport in self.VIEWPORTS:
                await self.browser.send_command(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": viewport["width"],
                        "height": viewport["height"],
                        "deviceScaleFactor": 1,
                        "mobile": viewport["name"] == "mobile",
                    },
                )

                await self.browser.evaluate_script("""
                    new Promise(resolve => {
                        const timeout = setTimeout(resolve, 3000);

                        const waitForResources = async () => {
                            try {
                                await document.fonts.ready;

                                await Promise.all(
                                    Array.from(document.images).map(img => {
                                        if (img.complete) return Promise.resolve();

                                        return new Promise(resolveImage => {
                                            img.addEventListener("load", resolveImage, {once: true});
                                            img.addEventListener("error", resolveImage, {once: true});
                                        });
                                    })
                                );
                            } catch (error) {
                                // Continue scanning even if a resource fails.
                            }

                            clearTimeout(timeout);
                            resolve();
                        };

                        waitForResources();
                    })
                """)

                screenshot_path = (
                    output_dir / f"{viewport['name']}.png"
                ).resolve()

                scan = await self.browser.evaluate_script(UI_SCAN_SCRIPT)

                if not isinstance(scan, dict):
                    raise RuntimeError(
                        f"UI scan returned an unexpected result for {viewport['name']}."
                    )

                await self.browser.capture_screenshot(str(screenshot_path))

                if not isinstance(scan, dict):
                    raise RuntimeError(
                        f"UI scan returned an unexpected result for {viewport['name']}."
                    )

                viewport_findings = []

                for finding in scan.get("findings", []):
                    finding["viewport"] = viewport["name"]
                    finding["screenshot"] = str(screenshot_path)
                    viewport_findings.append(finding)

                for finding in viewport_findings:
                    existing = next(
                        (
                            item for item in findings
                            if item["category"] == finding["category"]
                            and item["description"] == finding["description"]
                            and item["selector"] == finding["selector"]
                        ),
                        None,
                    )

                    if existing:
                        existing.setdefault("viewports", [existing["viewport"]])
                        if finding["viewport"] not in existing["viewports"]:
                            existing["viewports"].append(finding["viewport"])
                    else:
                        finding["viewports"] = [finding["viewport"]]
                        findings.append(finding)

                results.append({
                    "name": viewport["name"],
                    "width": viewport["width"],
                    "height": viewport["height"],
                    "screenshot": str(screenshot_path),
                    "finding_count": sum(
                        1 for finding in findings
                        if viewport["name"] in finding.get("viewports", [])
                    ),
                    "finding_occurrences": len(viewport_findings)
                })

        finally:
            await self.browser.send_command(
                "Emulation.clearDeviceMetricsOverride"
            )

        exploration_result = await self.explore_website(
            url=url,
            evidence_dir=str(output_dir / "exploration"),
            max_steps=4
        )

        llm_evaluation = await self.evaluate_exploration(
            exploration=exploration_result
        )

        findings.sort(
            key=lambda item: self.SEVERITY_ORDER.get(
                item["severity"], 99
            )
        )

        counts = {
            severity: sum(
                1 for finding in findings
                if finding["severity"] == severity
            )
            for severity in self.SEVERITY_ORDER
        }

        return {
            "agent": "uiux",
            "url": url,
            "page_title": await self.browser.get_page_title(),

            "summary": {
                "viewport_count": len(results),
                "total_findings": len(findings),
                "severity_counts": counts,
                "llm_findings": len(llm_evaluation.get("findings", [])),
                "llm_strengths": len(llm_evaluation.get("strengths", [])),
                "llm_evaluation_status": llm_evaluation.get(
                    "status", "completed"
                )
            },

            "viewports": results,

            "findings": findings,

            "llm_evaluation": llm_evaluation,

            "exploration": exploration_result,

            "upstream_context": context or {}
        }

    async def explore_website(
        self,
        url: str,
        evidence_dir: str = "artifacts/uiux/exploration",
        max_steps: int = 8
    ) -> dict[str, Any]:

        parsed_url = urlparse(url)

        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("A valid HTTP or HTTPS URL is required.")

        if not 1 <= max_steps <= 12:
            raise ValueError("max_steps must be between 1 and 12.")

        output_dir = Path(evidence_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        await self.browser.navigate(url)
        llm_service = GeminiLLMService()

        history = []
        executed_actions = []
        screenshots = []

        forbidden_actions = (
            "delete", "remove", "purchase", "buy now",
            "checkout", "payment", "pay now", "place order",
            "submit", "confirm", "cancel", "logout",
            "sign out", "unsubscribe", "book now"
        )

        initial_origin = (
            parsed_url.scheme,
            parsed_url.netloc
        )

        for step in range(max_steps):

            snapshot = await self.browser.get_interaction_snapshot()

            screenshot_path = (
                output_dir / f"step_{step + 1}.png"
            ).resolve()

            await self.browser.capture_screenshot(str(screenshot_path))
            screenshots.append(str(screenshot_path))

            prompt = f"""
You are an experienced human UX tester exploring a website.

Your objective is to understand how a real visitor experiences
this website, not to repeat automated accessibility checks.

Evaluate:
- Whether the interface is intuitive.
- Whether important information is easy to find.
- Whether navigation is understandable.
- Whether interactive elements communicate their purpose.
- Whether the page creates confusion or unnecessary friction.
- Whether the visual presentation supports the user's goals.

You can request ONE browser action at a time.

Available actions:
1. click: Click a visible, safe interactive element.
2. scroll: Explore additional page content.
3. fill: Enter harmless sample text into a safe text input.
4. finish: Finish exploration when sufficient information is collected.

Rules:
- Use only selectors provided in the interaction snapshot.
- Do not request form submission.
- Do not perform purchases, payments, deletion or account changes.
- Do not enter personal or sensitive information.
- Do not navigate to external websites.
- Prefer meaningful exploration over random clicking.
- Examine what is already visible before choosing an action.
- If an interaction is unnecessary, choose finish.
- Return only ONE action.

Current step: {step + 1} of {max_steps}

Previous exploration:
{json.dumps(history[-5:], ensure_ascii=False)}

Current page information:
{json.dumps(snapshot, ensure_ascii=False)}

Evaluate the screenshot and current page state.
Explain your observation and choose the next action.
"""

            try:
                decision = await llm_service.generate_structured(
                    prompt=prompt,
                    output_schema=ExplorationDecision,
                    system_instruction=(
                        "You are an autonomous human-centered UX evaluator. "
                        "Be observant, evidence-driven and conservative "
                        "with browser interactions."
                    ),
                    image_paths=[str(screenshot_path)]
                )

            except LLMServiceError as exc:
                history.append({
                    "step": step + 1,
                    "url": snapshot["url"],
                    "observation": "UX exploration could not continue.",
                    "evaluation": (
                        "Gemini was temporarily unavailable or the request failed."
                    ),
                    "status": "llm_error",
                    "error": type(exc).__name__
                })
                break

            history.append({
                "step": step + 1,
                "url": snapshot["url"],
                "observation": decision.observation,
                "evaluation": decision.evaluation
            })

            if not decision.actions:
                break

            action = decision.actions[0]

            if action.action == "finish":
                break

            try:
                if action.action == "scroll":

                    result = await self.browser.scroll_page(
                        direction=action.direction or "down",
                        amount=action.amount
                    )

                elif action.action == "click":

                    control = next(
                        (
                            item for item in snapshot["controls"]
                            if item["selector"] == action.selector
                        ),
                        None
                    )

                    if not control or control["disabled"]:
                        raise ValueError("Invalid or disabled control.")

                    if control["tag"] == "a":
                        target = urlparse(control.get("href") or "")

                        if (
                            target.scheme not in {"http", "https"}
                            or target.hostname != parsed_url.hostname
                            or target.port != parsed_url.port
                            or target.username is not None
                            or target.password is not None
                        ):
                            raise ValueError(
                                "External or unsafe navigation is not permitted."
                            )

                    elif control["tag"] == "button":
                        if control["type"] == "submit":
                            raise ValueError(
                                "Form submission is not permitted."
                            )

                    elif control["tag"] != "summary":
                        raise ValueError(
                            "This interactive element is not permitted."
                        )

                    label = control.get("text", "").lower()

                    if any(term in label for term in forbidden_actions):
                        raise ValueError(
                            "Potentially destructive action blocked."
                        )

                    result = await self.browser.click_element(
                        action.selector
                    )

                elif action.action == "fill":

                    control = next(
                        (
                            item for item in snapshot["controls"]
                            if item["selector"] == action.selector
                        ),
                        None
                    )

                    if not control or not control["fillable"]:
                        raise ValueError(
                            "Input is not approved for automatic filling."
                        )

                    if not action.value or len(action.value) > 200:
                        raise ValueError("Invalid test input.")

                    result = await self.browser.fill_input(
                        action.selector,
                        action.value
                    )

                else:
                    raise ValueError("Unsupported browser action.")

                executed_actions.append({
                    "step": step + 1,
                    "action": action.action,
                    "selector": action.selector,
                    "reason": action.reason,
                    "result": result
                })

                await asyncio.sleep(1)

                current_url = await self.browser.evaluate_script(
                    "window.location.href"
                )

                current = urlparse(current_url)

                if (
                    current.scheme,
                    current.netloc
                ) != initial_origin:
                    executed_actions[-1]["warning"] = (
                        "Navigation left the original website."
                    )
                    break

            except Exception as exc:
                executed_actions.append({
                    "step": step + 1,
                    "action": action.action,
                    "reason": action.reason,
                    "error": str(exc)
                })
                continue

        return {
            "url": url,
            "agent": "uiux_exploration",
            "steps_completed": len(history),
            "actions_executed": len(executed_actions),
            "observations": history,
            "actions": executed_actions,
            "screenshots": screenshots,
            "status": (
                "partial"
                if any(item.get("status") == "llm_error" for item in history)
                else "completed"
            ),
        }

    async def evaluate_exploration(
        self,
        exploration: dict[str, Any]
    ) -> dict[str, Any]:

        if exploration.get("agent") != "uiux_exploration":
            raise ValueError("Invalid UIUX exploration result.")

        observations = exploration.get("observations", [])
        if any(
            item.get("status") == "llm_error"
            for item in observations
        ):
            return {
                "agent": "uiux_llm_evaluation",
                "url": exploration.get("url"),
                "status": "unavailable",
                "pages_evaluated": len(observations),
                "screenshots_used": 0,
                "overall_summary": (
                    "Consolidated evaluation skipped because "
                    "exploration encountered an LLM failure."
                ),
                "strengths": [],
                "findings": [],
                "error": "ExplorationLLMFailure"
            }

        if not observations:
            raise ValueError("No exploration observations available.")

        screenshots = exploration.get("screenshots", [])

        valid_screenshots = [
            str(Path(path).resolve())
            for path in screenshots
            if Path(path).is_file()
        ]

        llm_service = GeminiLLMService()

        prompt = f"""
You are an experienced human-centered UX evaluator.

Analyze the complete website exploration performed by an autonomous UX tester.

Your task is to identify meaningful usability strengths and problems across
the explored pages.

Do not repeat deterministic accessibility or technical checks such as:
- Missing alt attributes
- Color contrast ratios
- Missing form labels
- HTML structure
- Technical layout overflow

Focus on human experience:

1. Navigation clarity and consistency.
2. Visual hierarchy and information prioritization.
3. Clarity of content and instructions.
4. Discoverability and intuitiveness of interactions.
5. Interaction feedback and user expectations.
6. Unnecessary friction in completing user goals.

Evidence requirements:
- Base every finding on the supplied observations, actions or screenshots.
- Do not invent problems or assume interactions that were not tested.
- Identify the specific page affected by each finding.
- Do not report the same issue multiple times.
- Include positive UX strengths when supported by evidence.
- If no significant usability problems were observed, return an empty findings list.
- Recommendations must address the actual issue identified.

Website URL:
{exploration.get("url")}

Exploration observations:
{json.dumps(observations, ensure_ascii=False, indent=2)}

Executed browser actions:
{json.dumps(exploration.get("actions", []), ensure_ascii=False, indent=2)}

Produce a consolidated evaluation of the explored website.
"""

        try:
            evaluation = await llm_service.generate_structured(
                prompt=prompt,
                output_schema=UXEvaluation,
                system_instruction=(
                    "You are a rigorous human-centered UX evaluator. "
                    "Base conclusions on observed evidence. "
                    "Never invent usability problems."
                ),
                image_paths=valid_screenshots
            )

        except LLMServiceError as exc:
            return {
                "agent": "uiux_llm_evaluation",
                "url": exploration.get("url"),
                "status": "unavailable",
                "pages_evaluated": len({
                    item.get("url") for item in observations
                }),
                "screenshots_used": len(valid_screenshots),
                "overall_summary": (
                    "Consolidated UX evaluation could not be completed "
                    "because the LLM service was unavailable."
                ),
                "strengths": [],
                "findings": [],
                "error": type(exc).__name__
            }

        return {
            "agent": "uiux_llm_evaluation",
            "url": exploration.get("url"),
            "pages_evaluated": len({
                item.get("url") for item in observations
            }),
            "screenshots_used": len(valid_screenshots),
            **evaluation.model_dump()
        }
