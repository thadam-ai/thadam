"""Project-confined discovery, validation, and explicit suite/settings writes."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path
from tempfile import NamedTemporaryFile

from thadam._json import read_json, validate_json
from thadam.baseline_review import approved_from_dict, review_from_dict, review_to_dict
from thadam.comparison_loading import comparison_from_dict
from thadam.comparison_reporting import comparison_to_dict
from thadam.reliability_loading import load_reliability_comparison
from thadam.reliability_reporting import reliability_to_dict
from thadam.repetition_loading import repeated_from_dict
from thadam.repetition_reporting import repeated_to_dict
from thadam.report_loading import report_from_dict
from thadam.reporting import report_to_dict, write_json_artifact
from thadam.result_reviews import (
    result_reviews,
    review_path,
    revision_review_path,
    validate_result_reviews,
)
from thadam.suites import load_suite

SKIP = {".git", ".venv", "venv", "node_modules", "build", "dist", "__pycache__"}
MAX_FILE = 32 * 1024 * 1024


def fingerprint(path: Path) -> str | None:
    """Fingerprint exact current bytes, or None for an absent destination."""
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


class Workspace:
    """Confine all browser-accessible files to one explicit local project."""

    def __init__(self, root: str | Path):
        self.lock = threading.RLock()
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError("Choose an existing project directory")

    def path(self, reference: str, *, internal: bool = False) -> Path:
        if not isinstance(reference, str) or not reference or Path(reference).is_absolute():
            raise ValueError("Use a relative project file path")
        parts = Path(reference).parts
        if ".." in parts or any(part.startswith(".") for part in parts) and not internal:
            raise ValueError("Hidden and parent paths are not available in the dashboard")
        current = self.root
        for part in parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("Symbolic links are not available in the dashboard")
        result = current.resolve()
        if not result.is_relative_to(self.root) or result == self.root:
            raise ValueError("Choose a file inside this project")
        return result

    def read(self, reference: str) -> dict:
        path = self.path(reference)
        if path.stat().st_size > MAX_FILE:
            raise ValueError(
                "This file exceeds the dashboard's 32 MiB file limit; inspect it with the SDK"
            )
        before = fingerprint(path)
        raw = read_json(path, max_depth=125)
        if not isinstance(raw, dict):
            raise ValueError("Expected a Thadam JSON object")
        kind = raw.get("kind")
        digest = None
        if kind == "regression_draft":
            from thadam.regression import validate_regression_draft

            data = validate_regression_draft(raw)
        elif kind == "result_reviews":
            data = validate_result_reviews(raw)
        elif kind == "scenario_draft":
            from thadam.generation import validate_draft

            data = validate_draft(raw)
        elif kind == "repeated_run":
            data = repeated_to_dict(repeated_from_dict(raw))
        elif kind == "reliability_comparison":
            data = reliability_to_dict(load_reliability_comparison(path))
        elif kind == "comparison":
            data = comparison_to_dict(comparison_from_dict(raw))
        elif kind == "baseline_review":
            review = review_from_dict(raw)
            data, digest = review_to_dict(review), review.digest
        elif kind == "approved_baseline":
            approved_from_dict(raw)
            data = raw
            digest = raw["review_digest"]
        elif "cases" in raw and "summary" in raw:
            data = report_to_dict(report_from_dict(raw))
            kind = "run"
        elif "cases" in raw:
            load_suite(path)
            data, kind = raw, "suite"
        else:
            raise ValueError("Not a supported Thadam artifact")
        if fingerprint(path) != before:
            raise ValueError("This file changed while loading. Refresh and try again.")
        return {
            "path": reference,
            "kind": kind,
            "data": data,
            "review_digest": digest,
            "fingerprint": before,
            "modified_ns": path.stat().st_mtime_ns,
        }

    def catalog(self) -> dict:
        items, invalid = [], []
        paths = []
        for directory, folders, files in os.walk(self.root, followlinks=False):
            folders[:] = sorted(
                name
                for name in folders
                if name not in SKIP
                and not name.startswith(".")
                and not (Path(directory) / name).is_symlink()
            )
            paths.extend(
                Path(directory) / name
                for name in sorted(files)
                if name.endswith(".json")
                and not name.startswith(".")
                and not (Path(directory) / name).is_symlink()
            )
        for path in paths:
            relative = path.relative_to(self.root)
            try:
                artifact = self.read(relative.as_posix())
                data = artifact.pop("data")
                evaluation = data
                if artifact["kind"] == "approved_baseline":
                    evaluation = data["review"]["candidate"]
                elif artifact["kind"] == "baseline_review":
                    evaluation = data["candidate"]
                runs = evaluation.get("runs", [])
                suite = evaluation.get("suite") or (runs[0].get("suite") if runs else None)
                artifact.update(
                    id=evaluation.get("report_id") or evaluation.get("run_id") or data.get("id"),
                    suite=suite,
                    summary=evaluation.get("summary"),
                    exit_code=data.get("exit_code"),
                    attempts=evaluation.get("attempts"),
                    execution_mode=evaluation.get("execution_mode"),
                    agent_revision=evaluation.get("agent_revision"),
                    duration_ms=(
                        evaluation.get("summary", {}).get("duration_ms")
                        if evaluation.get("kind") == "repeated_run"
                        else sum(case["duration_ms"] for case in evaluation["cases"])
                        if "run_id" in evaluation
                        else None
                    ),
                    cases=(
                        len(data["reviews"])
                        if artifact["kind"] == "result_reviews"
                        else 1
                        if artifact["kind"] == "regression_draft"
                        else len(evaluation.get("candidates", evaluation.get("cases", [])))
                    ),
                )
                if artifact["kind"] == "regression_draft":
                    source = data["source"]
                    record = source.get("record", {})
                    artifact.update(
                        case_id=data["case"]["id"],
                        source_id=source.get("source_id"),
                        review_state="reviewed" if data["reviewed"] else "unreviewed",
                        review_tags=record.get("tags", []),
                    )
                if artifact["kind"] == "result_reviews":
                    reviews = data["reviews"]
                    artifact.update(
                        source=data["source"],
                        review_state="reviewed" if reviews else "unreviewed",
                        review_verdicts=sorted({item["verdict"] for item in reviews}),
                        review_case_ids=sorted({item["case_id"] for item in reviews}),
                        review_tags=sorted({tag for item in reviews for tag in item["tags"]}),
                        review_labels=reviews,
                    )
                if artifact["kind"] == "suite":
                    artifact["suite"] = data.get("suite")
                items.append(artifact)
            except (ValueError, OSError, RecursionError) as error:
                # Unrelated project JSON is ignored; malformed recognizable reports
                # and invalid suites stay visible without breaking other results.
                try:
                    raw_text = path.read_text(encoding="utf-8")[:2048]
                    if any(
                        marker in raw_text for marker in ('"schema_version"', '"cases"', '"kind"')
                    ):
                        invalid.append({"path": relative.as_posix(), "error": str(error)})
                except (OSError, UnicodeError):
                    continue
        items.sort(key=lambda item: item["modified_ns"], reverse=True)
        reviews_by_source = {
            (
                item["source"]["path"],
                item["source"]["fingerprint"],
                item["source"]["kind"],
                item["source"]["id"],
            ): item
            for item in items
            if item["kind"] == "result_reviews"
        }
        for item in items:
            if item["kind"] in ("run", "repeated_run"):
                identity = (item["path"], item["fingerprint"], item["kind"], item["id"])
                review = reviews_by_source.get(identity)
                labels = review.get("review_labels", []) if review else []
                total = (
                    item.get("summary", {}).get("total_invocations", 0)
                    if item["kind"] == "repeated_run"
                    else item.get("cases", 0)
                )
                item.update(
                    review_state=(
                        "reviewed"
                        if labels and len(labels) == total
                        else "in progress"
                        if labels
                        else "unreviewed"
                    ),
                    review_verdicts=sorted({label["verdict"] for label in labels}),
                    review_case_ids=sorted({label["case_id"] for label in labels}),
                    review_tags=sorted({tag for label in labels for tag in label["tags"]}),
                    review_artifact=review["path"] if review else None,
                )
        source_states = {
            (item["path"], item["fingerprint"], item["kind"], item["id"]): item.get(
                "review_state", "unreviewed"
            )
            for item in items
            if item["kind"] in ("run", "repeated_run")
        }
        for item in items:
            if item["kind"] == "result_reviews":
                identity = (
                    item["source"]["path"],
                    item["source"]["fingerprint"],
                    item["source"]["kind"],
                    item["source"]["id"],
                )
                item["review_state"] = source_states.get(identity, item["review_state"])
        return {"name": self.root.name, "root": str(self.root), "items": items, "invalid": invalid}

    def save_result_reviews(
        self,
        source_reference: str,
        source_fingerprint: str,
        review_reference: str,
        reviews: list[dict],
        expected_fingerprint: str | None,
    ) -> dict:
        """Save labels separately while guarding both source and sidecar revisions."""
        with self.lock:
            source = self.read(source_reference)
            if source["kind"] not in ("run", "repeated_run"):
                raise ValueError("Choose a saved run or repeated run")
            if source["fingerprint"] != source_fingerprint:
                raise ValueError("Source result changed; reload before saving labels")
            source_data = {"kind": source["kind"], **source["data"]}
            artifact = result_reviews(
                source_data,
                path=source_reference,
                fingerprint=source_fingerprint,
                reviews=reviews,
            )
            artifact = validate_result_reviews(artifact, source=source_data)
            report_id = source_data.get("report_id") or source_data.get("run_id")
            current_identity = {
                "path": source_reference,
                "fingerprint": source_fingerprint,
                "kind": source["kind"],
                "id": report_id,
            }
            revision_reference = revision_review_path(
                source_reference, source_fingerprint, source["kind"], report_id
            )
            legacy_reference = review_path(source_reference)
            if review_reference == revision_reference:
                reference = revision_reference
            elif review_reference == legacy_reference:
                reference = legacy_reference
            else:
                raise ValueError("Review labels path does not match the selected source")
            destination = self.path(reference)
            current_fingerprint = fingerprint(destination)
            if current_fingerprint != expected_fingerprint:
                raise ValueError("Review labels changed; reload before saving")
            if reference == legacy_reference and not destination.exists():
                raise ValueError("Legacy review labels can only be updated in place")
            if destination.exists():
                current = self.read(reference)
                if current["kind"] != "result_reviews":
                    raise ValueError("Review path is occupied by another artifact")
                if current["data"]["source"] != current_identity:
                    raise ValueError("Review labels belong to a different source result")
            write_json_artifact(artifact, destination)
            return self.read(reference)

    def save_suite(self, reference: str, data: dict, expected: str | None) -> dict:
        with self.lock:
            return self._save_suite(reference, data, expected)

    def _save_suite(self, reference: str, data: dict, expected: str | None) -> dict:
        from thadam.suite_writing import save_suite

        path = self.path(reference)
        save_suite(data, path, expected_fingerprint=expected)
        return self.read(reference)

    def output(self, reference: str) -> Path:
        path = self.path(reference)
        if path.suffix != ".json" or path.exists():
            raise ValueError("Choose a new .json report path; existing evidence is preserved")
        return path

    def write_new(self, reference: str, data: dict) -> None:
        with self.lock:
            write_json_artifact(data, self.output(reference))

    def settings(self, agents: list[dict] | None = None) -> list[dict]:
        with self.lock:
            return self._settings(agents)

    def _settings(self, agents: list[dict] | None = None) -> list[dict]:
        path = self.path(".thadam/dashboard/agents.json", internal=True)
        writing = agents is not None
        if not writing:
            agents = read_json(path) if path.exists() else []
        if not isinstance(agents, list):
            raise ValueError(
                "Agent settings must be an array. Correct .thadam/dashboard/agents.json."
            )
        names = set()
        validate_json(agents, "agent settings")
        for item in agents:
            if not isinstance(item, dict) or item.keys() != {"name", "reference", "mode"}:
                raise ValueError("Agent entries need name, reference, and mode")
            if (
                not isinstance(item["name"], str)
                or not item["name"].strip()
                or item["name"] in names
            ):
                raise ValueError("Use a unique non-empty agent name")
            names.add(item["name"])
            if (
                not isinstance(item["reference"], str)
                or item["reference"].count(":") != 1
                or not all(item["reference"].split(":"))
            ):
                raise ValueError("Use a module:callable reference")
            if item["mode"] not in ("shared", "factory", "fixtures"):
                raise ValueError("Choose shared, factory, or fixtures mode")
        if not writing:
            return agents
        # Settings are private application state, not a report format.
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent, delete=False
            ) as stream:
                temporary = Path(stream.name)
                stream.write(json.dumps(agents, ensure_ascii=False) + "\n")
            temporary.replace(path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return agents
