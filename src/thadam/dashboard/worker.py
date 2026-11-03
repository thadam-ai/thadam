"""A single explicitly requested evaluation in a separate trusted-code process."""

import json
import os
import sys
import threading
import time
from pathlib import Path

from thadam.cli import _load_agent, _load_reference
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

        reference = specification["reference"]
        revision = specification.get("agent_revision") or None
        if specification["attempts"] > 1 or specification["mode"] == "factory":
            if specification["mode"] == "factory":
                result = run_repeated(
                    cases=cases,
                    agent_factory=_load_reference(reference),
                    attempts=specification["attempts"],
                    agent_revision=revision,
                    on_case_complete=progress,
                )
            else:
                result = run_repeated(
                    _load_agent(reference),
                    cases,
                    attempts=specification["attempts"],
                    agent_revision=revision,
                    on_case_complete=progress,
                )
            write_repeated(result, directory / "result.json")
        else:
            result = run_suite(
                _load_agent(reference), cases, agent_revision=revision, on_case_complete=progress
            )
            write_report(result, directory / "result.json")
        return int(result.has_failures)
    except (Exception, SystemExit) as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
