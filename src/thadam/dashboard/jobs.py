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
from thadam.comparison import compare_reports
from thadam.comparison_reporting import comparison_to_dict
from thadam.dashboard.workspace import Workspace
from thadam.limits import limits_from_dict
from thadam.models import RunReport
from thadam.reliability import compare_repeated, validate_tolerance
from thadam.reliability_reporting import reliability_to_dict
from thadam.repetition import RepeatedReport
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
                "verification",
                "execution_limits",
                "environment",
            }:
                raise ValueError("Evaluation settings have missing or unknown fields")
            validate_json(specification, "evaluation settings")
            limits_from_dict(specification.get("execution_limits"))
            environment = specification.get("environment")
            if environment is not None and (
                specification["mode"] != "fixtures"
                or not isinstance(environment, str)
                or environment.count(":") != 1
                or not all(environment.split(":"))
            ):
                raise ValueError(
                    "Environment hooks require fixtures mode and a module:hooks reference"
                )
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
            if specification["mode"] not in ("shared", "factory", "fixtures"):
                raise ValueError("Choose shared, factory, or fixtures mode")
            if artifact["data"]["schema_version"] in (3, 4) and specification["mode"] != "fixtures":
                raise ValueError("Fixture and simulation suites require Tool fixture factory mode")
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
            report_path = self.workspace.output(specification["report"])
            verification = specification.get("verification")
            if verification is not None:
                self._validate_verification(
                    verification,
                    artifact["data"],
                    attempts=attempts,
                    mode=specification["mode"],
                    report_path=report_path,
                )
            return self._spawn(
                specification, len(artifact["data"]["cases"]) * attempts, artifact["data"]
            )

    def _validate_verification(
        self,
        verification: object,
        suite: dict,
        *,
        attempts: int,
        mode: str,
        report_path: Path,
    ) -> None:
        if not isinstance(verification, dict) or verification.keys() != {
            "baseline",
            "baseline_fingerprint",
            "report",
            "max_pass_rate_drop",
        }:
            raise ValueError(
                "Verification needs a baseline, fingerprint, comparison path, and policy"
            )
        baseline_path = verification["baseline"]
        fingerprint = verification["baseline_fingerprint"]
        comparison_path = verification["report"]
        if not all(isinstance(value, str) and value for value in (baseline_path, fingerprint)):
            raise ValueError("Choose a baseline and its current fingerprint")
        if not isinstance(comparison_path, str) or not comparison_path:
            raise ValueError("Choose a new comparison report path")
        comparison_output = self.workspace.output(comparison_path)
        if comparison_output == report_path:
            raise ValueError("Candidate and comparison reports need different paths")
        tolerance = validate_tolerance(verification["max_pass_rate_drop"])
        baseline_artifact = self.workspace.read(baseline_path)
        if baseline_artifact["fingerprint"] != fingerprint:
            raise ValueError("Baseline changed; reload it before verifying a fix")
        baseline = load_evaluation(self.workspace.path(baseline_path))
        if self.workspace.read(baseline_path)["fingerprint"] != fingerprint:
            raise ValueError("Baseline changed while it was being loaded")
        repeated_candidate = attempts > 1 or mode == "factory"
        if repeated_candidate:
            if not isinstance(baseline, RepeatedReport):
                raise ValueError("Choose a repeated baseline with matching attempts and mode")
            expected_mode = mode
            if mode == "fixtures":
                simulated = any(
                    case.get("conversation") or case.get("state_fixture") is not None
                    for case in suite["cases"]
                )
                expected_mode = "simulations" if simulated else "fixtures"
            if baseline.attempts != attempts or baseline.execution_mode != expected_mode:
                raise ValueError("Choose a repeated baseline with matching attempts and mode")
        elif not isinstance(baseline, RunReport):
            raise ValueError("Choose a single-run baseline for a single candidate run")
        verification.update(
            baseline=baseline_path,
            baseline_fingerprint=fingerprint,
            report=comparison_path,
            max_pass_rate_drop=tolerance,
        )

    def _save_verification(self, candidate, verification: dict) -> None:
        baseline_artifact = self.workspace.read(verification["baseline"])
        if baseline_artifact["fingerprint"] != verification["baseline_fingerprint"]:
            raise ValueError("Baseline changed while the candidate was running")
        baseline = load_evaluation(self.workspace.path(verification["baseline"]))
        if isinstance(baseline, RepeatedReport) and isinstance(candidate, RepeatedReport):
            artifact = reliability_to_dict(
                compare_repeated(
                    baseline,
                    candidate,
                    max_pass_rate_drop=verification["max_pass_rate_drop"],
                )
            )
        elif isinstance(baseline, RunReport) and isinstance(candidate, RunReport):
            artifact = comparison_to_dict(compare_reports(baseline, candidate))
        else:
            raise ValueError("Baseline and candidate evaluation kinds do not match")
        self.workspace.write_new(verification["report"], artifact)

    def start_generation(self, specification: dict) -> dict:
        from thadam.generation import validate_request
        from thadam.providers.openai import OpenAIProvider

        with self.lock:
            self._refresh()
            if self.process is not None:
                raise ValueError("A job is already running. Wait for it or stop it first.")
            if specification.keys() != {
                "kind",
                "connection",
                "model",
                "request",
                "source",
                "report",
            }:
                raise ValueError("Generation settings have missing or unknown fields")
            specification = dict(specification)
            specification["request"] = validate_request(specification["request"])
            OpenAIProvider(connection=specification["connection"], model=specification["model"])
            if specification["source"] is not None:
                source = specification["source"]
                if not isinstance(source, dict) or source.keys() != {"path", "fingerprint"}:
                    raise ValueError("Choose a source suite and its fingerprint")
                artifact = self.workspace.read(source["path"])
                if artifact["kind"] != "suite" or source["fingerprint"] != artifact["fingerprint"]:
                    raise ValueError("Source suite changed; reload before generating")
                specification["source"] = {**source, "data": artifact["data"]}
            self.workspace.output(specification["report"])
            return self._spawn(specification, 1)

    def _spawn(self, specification: dict, total: int, suite: dict | None = None) -> dict:
        identifier = uuid4().hex
        self.directory = self.workspace.path(f".thadam/dashboard/jobs/{identifier}", internal=True)
        self.directory.mkdir(parents=True)
        write_json_artifact(specification, self.directory / "spec.json")
        if suite is not None:
            write_json_artifact(suite, self.directory / "suite.json")
        self.active = {
            "id": identifier,
            "state": "running",
            "started_at": time(),
            "settings": specification,
            "completed": 0,
            "total": total,
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
                if self.active["settings"].get("kind") == "generation":
                    from thadam.generation import load_draft

                    result = load_draft(self.directory / "result.json")
                else:
                    evaluation = load_evaluation(self.directory / "result.json")
                    result = evaluation_to_dict(evaluation)
                self.workspace.write_new(self.active["settings"]["report"], result)
                self.active.update(
                    state="completed", exit_code=code, completed=self.active["total"]
                )
                verification = self.active["settings"].get("verification")
                if verification is not None:
                    try:
                        self._save_verification(evaluation, verification)
                    except (ValueError, OSError) as error:
                        self.active["verification_error"] = str(error)
            except (ValueError, OSError) as error:
                self.active.update(state="error", error=str(error))
        else:
            message = "Job could not complete. Inspect its logs and settings."
            if self.active["settings"].get("kind") == "generation":
                try:
                    message = json.loads((self.directory / "error.json").read_text())["error"]
                except (ValueError, OSError, KeyError):
                    pass
            self.active.update(state="error", error=message)
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
            # A child may ignore SIGTERM after its parent exits. Finish stopping
            # the owned process group even when waiting for the parent succeeded.
            if os.name != "nt":
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
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
