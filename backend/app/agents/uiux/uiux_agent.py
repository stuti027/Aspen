
import asyncio
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.services.browser_manager import BrowserManager


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
            },
            "viewports": results,
            "findings": findings,
        }
