"""A single explicitly requested evaluation in a separate trusted-code process."""

import asyncio
import json
import os
import sys
import threading
import time
from pathlib import Path

from thadam.async_runner import run_repeated_async, run_suite_async
from thadam.cli import _load_agent, _load_reference
from thadam.fixtures import FixtureAgent
from thadam.repetition import run_repeated
from thadam.repetition_reporting import write_repeated
from thadam.reporting import write_report
from thadam.runner import run_suite
from thadam.suites import load_suite


def main() -> int:
    directory = Path(sys.argv[1])
    specification = json.loads((directory / "spec.json").read_text())
    parent = os.getppid()

    def watch_parent():
        while True:
            time.sleep(1)
            if os.getppid() != parent:
                os._exit(2)

    threading.Thread(target=watch_parent, daemon=True).start()
    try:
        if specification.get("kind") == "generation":
            from thadam.generation import suggest_cases, write_draft
            from thadam.providers.openai import OpenAIProvider

            provider = OpenAIProvider(
                connection=specification["connection"], model=specification["model"]
            )
            try:
                draft = suggest_cases(
                    provider, specification["request"], source=specification["source"]
                )
                write_draft(draft, directory / "result.json")
                return 0
            except ValueError as error:
                from thadam.reporting import write_json_artifact

                write_json_artifact({"error": str(error)}, directory / "error.json")
                return 2
        cases = load_suite(directory / "suite.json")
        completed = 0

        def progress(case):
            nonlocal completed
            completed += 1
            with (directory / "progress.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(
                    json.dumps(
                        {
                            "completed": completed,
                            "case": case.id,
                            "status": case.status,
                            "attempt": (completed - 1) // len(cases) + 1,
                        }
                    )
                    + "\n"
                )

        async_execution = specification.get("async_execution", False)
        options = (
            {"max_concurrency": specification.get("max_concurrency", 1)} if async_execution else {}
        )
        repeat_runner = run_repeated_async if async_execution else run_repeated
        suite_runner = run_suite_async if async_execution else run_suite
        reference = specification["reference"]
        revision = specification.get("agent_revision") or None
        fixture_agent = (
            FixtureAgent(_load_reference(reference))
            if specification["mode"] == "fixtures"
            else None
        )
        if specification["attempts"] > 1 or specification["mode"] == "factory":
            if specification["mode"] == "factory":
                result = repeat_runner(
                    cases=cases,
                    agent_factory=_load_reference(reference),
                    attempts=specification["attempts"],
                    agent_revision=revision,
                    on_case_complete=progress,
                    **options,
                )
            else:
                result = repeat_runner(
                    fixture_agent or _load_agent(reference, allow_async=async_execution),
                    cases,
                    attempts=specification["attempts"],
                    agent_revision=revision,
                    on_case_complete=progress,
                    **options,
                )
            if async_execution:
                result = asyncio.run(result)
            write_repeated(result, directory / "result.json")
        else:
            result = suite_runner(
                fixture_agent or _load_agent(reference, allow_async=async_execution),
                cases,
                agent_revision=revision,
                on_case_complete=progress,
                **options,
            )
            if async_execution:
                result = asyncio.run(result)
            write_report(result, directory / "result.json")
        return int(result.has_failures)
    except (Exception, SystemExit) as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
