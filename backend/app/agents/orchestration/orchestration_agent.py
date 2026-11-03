from typing import Any
from app.services.browser_manager import BrowserManager
from app.agents.functionality_agent.functionality_agent import FunctionalityAgent
from app.agents.time_simulation_agent import TimeSimulator
from app.agents.uiux import UIUXAgent


class OrchestrationAgent:

    AVAILABLE_AGENTS = {
        "functionality",
        "time_simulation",
        "uiux"
    }

    EXECUTION_ORDER = {
        "functionality": 1,
        "uiux": 2,
        "time_simulation": 3
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
        time_jump_ms: int = 0
    ) -> dict[str, Any]:

        if not url:
            raise ValueError("A target URL is required.")

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
            steps = task_input.get("steps", [])

            if not steps or steps[0].get("action") != "navigate":
                steps = [
                    {
                        "action": "navigate",
                        "params": {"url": url}
                    }
                ] + steps

            result = await self.functionality_agent.run_workflow(steps)
            if any(step.get("status") == "error" for step in result):
                raise RuntimeError("One or more functionality steps failed.")

        elif agent == "uiux":
            result = await self.uiux_agent.run(
                url,
                context=task.get("context", {})
            )

        elif agent == "time_simulation":
            await self.time_simulator.install_fake_clock()

            await self.browser.navigate(url)

            time_jump_ms = task_input.get("time_jump_ms", 0)

            if time_jump_ms > 0:
                await self.time_simulator.fast_forward(time_jump_ms)

            simulated_time = (
                await self.time_simulator.get_current_simulated_time()
            )

            result = {
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

            # Share previously completed results with the next task.
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

                    execution_results.append({
                        **result,
                        "attempts": task["attempts"]
                    })

                    shared_context["completed_results"][
                        task["agent"]
                    ] = result["result"]

                    break

                except Exception as error:
                    task["error"] = str(error)

                    if attempt == max_retries:
                        task["status"] = "failed"

                        execution_results.append({
                            "agent": task["agent"],
                            "status": "failed",
                            "attempts": task["attempts"],
                            "error": str(error)
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