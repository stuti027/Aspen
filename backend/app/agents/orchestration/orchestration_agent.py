
import os
from typing import Any

from app.services.browser_manager import BrowserManager
from app.agents.functionality_agent.functionality_agent import FunctionalityAgent
from app.agents.time_simulation_agent import TimeSimulator
from app.agents.uiux import UIUXAgent
import json


class OrchestrationAgent:

    AVAILABLE_AGENTS = {
        "functionality",
        "time_simulation",
        "uiux"
    }

    EXECUTION_ORDER = {
        "functionality": 1,
        "time_simulation": 2,
        "uiux": 3
    }

    def __init__(self, browser_manager: BrowserManager):
        self.browser = browser_manager

        self.functionality_agent = FunctionalityAgent(browser_manager)
        self.time_simulator = TimeSimulator(browser_manager)
        self.uiux_agent = UIUXAgent(browser_manager)

    def create_test_plan(
        self,
        url: str,
        selected_agents: list[str],
        functionality_steps: list[dict[str, Any]] | None = None,
        time_jump_ms: int = 0,
        functionality_objective: str | None = None
    ) -> dict[str, Any]:

        if not url:
            raise ValueError("A target URL is required.")

        if not selected_agents:
            raise ValueError("At least one agent must be selected.")

        selected_agents = list(dict.fromkeys(
            agent.lower() for agent in selected_agents
        ))

        invalid_agents = [
            agent for agent in selected_agents
            if agent not in self.AVAILABLE_AGENTS
        ]

        if invalid_agents:
            raise ValueError(
                f"Unsupported agents: {invalid_agents}"
            )

        if time_jump_ms < 0:
            raise ValueError("Time jump cannot be negative.")

        tasks = []

        for agent in sorted(
            selected_agents,
            key=lambda item: self.EXECUTION_ORDER[item]
        ):
            task = {
                "agent": agent,
                "execution_order": self.EXECUTION_ORDER[agent],
                "status": "pending",
                "input": {
                    "url": url
                }
            }

            if agent == "functionality":
                task["input"]["steps"] = functionality_steps or []
                if functionality_objective:
                    task["input"]["objective"] = functionality_objective

            if agent == "time_simulation":
                task["input"]["time_jump_ms"] = time_jump_ms

            tasks.append(task)

        return {
            "url": url,
            "total_tasks": len(tasks),
            "execution_plan": tasks
        }

    async def execute_task(
        self,
        task: dict[str, Any]
    ) -> dict[str, Any]:

        agent = task["agent"]
        task_input = task["input"]
        url = task_input["url"]

        if agent == "functionality":

            steps = list(task_input.get("steps", []))
            generated_plan = None

            if not steps and task_input.get("objective"):
                generated_plan = await self.functionality_agent.generate_test_steps(
                    url=url,
                    objective=task_input["objective"]
                )
                steps = generated_plan["steps"]

            if not steps or steps[0].get("action") != "navigate":
                steps.insert(
                    0,
                    {"action": "navigate", "params": {"url": url}}
                )

            has_time_steps = any(
                step.get("action") == "advance_time"
                for step in steps
            )

            if has_time_steps:
                await self.time_simulator.install_fake_clock()

            result = []

            for step_index, step in enumerate(steps, start=1):
                action = step.get("action")
                params = step.get("params", {})

                if action == "advance_time":
                    milliseconds = params.get("milliseconds", 0)

                    if milliseconds <= 0:
                        raise ValueError(
                            "Time advancement must be greater than zero."
                        )

                    await self.time_simulator.fast_forward(milliseconds)

                    current_time = (
                        await self.time_simulator.get_current_simulated_time()
                    )

                    result.append({
                        "status": "success",
                        "action": "advance_time",
                        "milliseconds": milliseconds,
                        "simulated_timestamp": current_time
                    })

                else:
                    step_result = await self.functionality_agent.run_workflow(
                        [step]
                    )
                    for item in step_result:
                        item["step_index"] = step_index

                    result.extend(step_result)

                    if any(
                        item.get("status") == "error"
                        for item in step_result
                    ):
                        failure_analysis = (
                            await self.functionality_agent.analyze_failures(
                                url=url,
                                steps=steps,
                                results=result
                            )
                        )

                        raise RuntimeError(
                            json.dumps({
                                "message": "One or more functionality steps failed.",
                                "failure_analysis": failure_analysis
                            })
                        )

        elif agent == "uiux":

            os.makedirs("static/uiux", exist_ok=True)

            result = await self.uiux_agent.run(
                url,
                evidence_dir="static/uiux",
                context=task.get("context", {})
            )

        elif agent == "time_simulation":

            functionality_results = task.get("context", {}).get(
                "completed_results", {}
            ).get("functionality", [])

            time_advancements = [
                item for item in functionality_results
                if (
                    item.get("action") == "advance_time"
                    and item.get("status") == "success"
                )
            ]

            if time_advancements:

                result = {
                    "mode": "integrated",
                    "time_advancements": time_advancements
                }

            else:

                await self.time_simulator.install_fake_clock()
                await self.browser.navigate(url)

                time_jump_ms = task_input.get("time_jump_ms", 0)

                if time_jump_ms > 0:
                    await self.time_simulator.fast_forward(time_jump_ms)

                simulated_time = (
                    await self.time_simulator.get_current_simulated_time()
                )

                result = {
                    "mode": "standalone",
                    "time_jump_ms": time_jump_ms,
                    "simulated_timestamp": simulated_time
                }

        else:
            raise ValueError(f"Unsupported agent: {agent}")

        return {
            "agent": agent,
            "status": "completed",
            "result": result
        }

    async def execute_plan(
        self,
        test_plan: dict[str, Any],
        max_retries: int = 1
    ) -> dict[str, Any]:

        if max_retries < 0:
            raise ValueError("max_retries cannot be negative.")

        execution_results = []

        shared_context = {
            "url": test_plan["url"],
            "completed_results": {}
        }

        for task in test_plan["execution_plan"]:

            task["status"] = "running"
            task["attempts"] = 0

            task["context"] = {
                "url": shared_context["url"],
                "completed_results": dict(
                    shared_context["completed_results"]
                )
            }

            for attempt in range(max_retries + 1):

                task["attempts"] += 1

                try:
                    result = await self.execute_task(task)

                    task["status"] = "completed"
                    task.pop("error", None)
                    task.pop("reset_error", None)

                    execution_results.append({
                        **result,
                        "attempts": task["attempts"]
                    })

                    shared_context["completed_results"][
                        task["agent"]
                    ] = result["result"]

                    break

                except Exception as e:
                    error_message = str(e)

                    try:
                        error_data = json.loads(error_message)
                    except (json.JSONDecodeError, TypeError):
                        error_data = {"message": error_message}

                    task["error"] = error_data.get("message", error_message)

                    if "failure_analysis" in error_data:
                        task["failure_analysis"] = error_data["failure_analysis"]

                    task["status"] = "failed"

                    reset_failed = False

                    try:
                        await self.time_simulator.reset()

                    except Exception as reset_error:
                        task["reset_error"] = str(reset_error)
                        reset_failed = True

                    if reset_failed:

                        if attempt == max_retries:
                            execution_results.append({
                                "agent": task["agent"],
                                "status": "failed",
                                "error": task.get("error", str(e)),
                                "reset_error": task["reset_error"],
                                "attempts": task["attempts"],
                                "failure_analysis": task.get("failure_analysis")
                            })

                        break

                    if attempt == max_retries:

                        execution_results.append({
                            "agent": task["agent"],
                            "status": "failed",
                            "error": task.get("error", str(e)),
                            "attempts": task["attempts"],
                            "failure_analysis": task.get("failure_analysis")
                        })

        completed = sum(
            1 for result in execution_results
            if result["status"] == "completed"
        )

        failed = sum(
            1 for result in execution_results
            if result["status"] == "failed"
        )

        return {
            "url": test_plan["url"],
            "status": (
                "completed" if failed == 0
                else "partially_completed" if completed > 0
                else "failed"
            ),
            "total_tasks": len(test_plan["execution_plan"]),
            "completed_tasks": completed,
            "failed_tasks": failed,
            "results": execution_results,
            "shared_context": shared_context
        }