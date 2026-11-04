"""One active evaluation, progress and bounded logs, with explicit interruption."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path
from time import time
from uuid import uuid4

from thadam._json import validate_json
from thadam.baseline_review import evaluation_to_dict, load_evaluation
from thadam.dashboard.workspace import Workspace
from thadam.reporting import write_json_artifact


class Jobs:
    """Own subprocesses for a dashboard session; no agents run in the API process."""

    def __init__(self, workspace: Workspace):
        self.workspace = workspace
        self.lock = threading.RLock()
        self.process: subprocess.Popen | None = None
        self.active: dict | None = None
        self.directory: Path | None = None
        self.history: list[dict] = []
        self.shutdown = threading.Event()
        state = workspace.path(".thadam/dashboard/jobs", internal=True)
        if state.exists():
            for path in sorted(
                state.glob("*/state.json"), key=lambda p: p.stat().st_mtime, reverse=True
            ):
                try:
                    data = json.loads(path.read_text())
                    if data["state"] == "running":
                        data.update(
                            state="interrupted",
                            error="The dashboard session ended before this job completed",
                        )
                    self.history.append(data)
                except (ValueError, KeyError, OSError):
                    continue
        self.monitor = threading.Thread(target=self._watch, daemon=True)
        self.monitor.start()

    def _watch(self):
        while not self.shutdown.wait(0.2):
            with self.lock:
                self._refresh()

    @staticmethod
    def _capture(process: subprocess.Popen, path: Path):
        tail = b""
        try:
            while chunk := process.stdout.read1(4096):
                tail = (tail + chunk)[-65536:]
                path.write_bytes(tail)
        finally:
            process.stdout.close()

    def _save(self):
        if self.directory and self.active:
            write_json_artifact(self.active, self.directory / "state.json")

    def start(self, specification: dict) -> dict:
        with self.lock:
            self._refresh()
            if self.process is not None:
                raise ValueError("An evaluation is already running. Wait for it or stop it first.")
            allowed = {"suite", "reference", "mode", "attempts", "agent_revision", "report"}
            if not allowed <= specification.keys() or specification.keys() - allowed - {
                "async_execution",
                "max_concurrency",
            }:
                raise ValueError("Evaluation settings have missing or unknown fields")
            validate_json(specification, "evaluation settings")
            async_execution = specification.get("async_execution", False)
            limit = specification.get("max_concurrency", 1)
            if type(async_execution) is not bool:
                raise ValueError("async_execution must be a boolean")
            if type(limit) is not int or limit < 1:
                raise ValueError("max_concurrency must be a positive integer")
            if not async_execution and limit != 1:
                raise ValueError("Concurrency requires async execution")
            artifact = self.workspace.read(specification["suite"])
            if artifact["kind"] != "suite":
                raise ValueError("Choose a test suite")
            attempts = specification["attempts"]
            if type(attempts) is not int or attempts < 1:
                raise ValueError("Attempts must be an integer of at least 1")
            if specification["mode"] not in ("shared", "factory"):
                raise ValueError("Choose shared or factory mode")
            if specification["mode"] == "factory" and attempts < 2:
                raise ValueError(
                    "Factory mode uses repeated evaluations; choose at least 2 attempts"
                )
            reference = specification["reference"]
            if (
                not isinstance(reference, str)
                or reference.count(":") != 1
                or not all(reference.split(":"))
            ):
                raise ValueError("Use a module:callable reference")
            revision = specification["agent_revision"]
            if revision is not None and (not isinstance(revision, str) or not revision.strip()):
                raise ValueError("Application revision must be non-empty or omitted")
            self.workspace.output(specification["report"])
            identifier = uuid4().hex
            self.directory = self.workspace.path(
                f".thadam/dashboard/jobs/{identifier}", internal=True
            )
            self.directory.mkdir(parents=True)
            write_json_artifact(specification, self.directory / "spec.json")
            write_json_artifact(artifact["data"], self.directory / "suite.json")
            self.active = {
                "id": identifier,
                "state": "running",
                "started_at": time(),
                "settings": specification,
                "completed": 0,
                "total": len(artifact["data"]["cases"]) * attempts,
                "error": None,
            }
            self._save()
            environment = dict(os.environ)
            environment["PYTHONPATH"] = (
                str(Path(__file__).resolve().parents[2])
                + os.pathsep
                + environment.get("PYTHONPATH", "")
            )
            try:
                self.process = subprocess.Popen(
                    [
                        sys.executable,
                        "-u",
                        "-m",
                        "thadam.dashboard.worker",
                        str(self.directory),
                    ],
                    cwd=self.workspace.root,
                    env=environment,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    start_new_session=os.name != "nt",
                )
                threading.Thread(
                    target=self._capture,
                    args=(self.process, self.directory / "logs.txt"),
                    daemon=True,
                ).start()
            except OSError as error:
                self.active.update(state="error", error=str(error))
                self._save()
                raise
            return dict(self.active)

    def _refresh(self):
        if not self.process or not self.active or not self.directory:
            return
        progress = self.directory / "progress.jsonl"
        if progress.exists():
            try:
                with progress.open("rb") as stream:
                    stream.seek(max(0, progress.stat().st_size - 4096))
                    lines = stream.read().splitlines()
                last = json.loads(lines[-1])
                self.active.update(last)
            except (ValueError, OSError, IndexError):
                pass
        code = self.process.poll()
        if code is None:
            return
        if code in (0, 1):
            try:
                evaluation = load_evaluation(self.directory / "result.json")
                self.workspace.write_new(
                    self.active["settings"]["report"], evaluation_to_dict(evaluation)
                )
                self.active.update(
                    state="completed", exit_code=code, completed=self.active["total"]
                )
            except (ValueError, OSError) as error:
                self.active.update(state="error", error=str(error))
        else:
            self.active.update(
                state="error", error="Evaluation could not complete. Inspect its logs and settings."
            )
        self.active["finished_at"] = time()
        self._save()
        self.history.insert(0, dict(self.active))
        self.process = None

    def list(self) -> list[dict]:
        with self.lock:
            self._refresh()
            result = ([self.active] if self.process and self.active else []) + self.history
            return [dict(item) for item in result]

    def detail(self, identifier: str) -> dict:
        with self.lock:
            found = next((item for item in self.list() if item["id"] == identifier), None)
            if found is None:
                raise ValueError("Evaluation job not found")
            path = self.workspace.path(
                f".thadam/dashboard/jobs/{identifier}/logs.txt", internal=True
            )
            if path.exists():
                with path.open("rb") as stream:
                    stream.seek(max(0, path.stat().st_size - 65536))
                    found["logs"] = stream.read().decode("utf-8", errors="replace")
            else:
                found["logs"] = ""
            return found

    def stop(self) -> dict:
        with self.lock:
            self._refresh()
            if not self.process or not self.active:
                raise ValueError("No evaluation is running")
            if os.name == "nt":
                self.process.terminate()
            else:
                os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    self.process.kill()
                else:
                    os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=2)
            self.active.update(
                state="interrupted",
                finished_at=time(),
                error="Stopped by the user. No completed report was published.",
            )
            self._save()
            self.history.insert(0, dict(self.active))
            self.process = None
            return dict(self.active)

    def close(self):
        with self.lock:
            self._refresh()
            if self.process:
                self.stop()
        self.shutdown.set()
        self.monitor.join(timeout=1)
