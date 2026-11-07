"""Explicit regression draft review and guarded suite composition."""

from copy import deepcopy

from thadam.regression import regression_draft, validate_regression_draft
from thadam.reporting import write_json_artifact
from thadam.suites import suite_from_dict


def register_regression(app, workspace):
    """Register project-confined actions without importing agents or providers."""

    def current(body):
        artifact = workspace.read(body["path"])
        if artifact["kind"] != "regression_draft" or artifact["fingerprint"] != body["fingerprint"]:
            raise ValueError("Draft changed; reload before reviewing or saving")
        return artifact

    @app.post("/api/regression/create")
    def create(body: dict):
        if body.keys() != {"path", "fingerprint", "case_id", "attempt"}:
            raise ValueError("Supply source path, fingerprint, case ID and attempt")
        with workspace.lock:
            artifact = workspace.read(body["path"])
            if artifact["fingerprint"] != body["fingerprint"]:
                raise ValueError("Source report changed; reload before creating a draft")
            data = artifact["data"]
            if artifact["kind"] == "run":
                if body["attempt"] is not None:
                    raise ValueError("Single runs have no attempt selector")
            elif artifact["kind"] == "repeated_run":
                attempt = body["attempt"]
                if type(attempt) is not int or not 1 <= attempt <= len(data["runs"]):
                    raise ValueError("Choose an individual attempt")
                data = data["runs"][attempt - 1]
            else:
                raise ValueError("Choose a saved run or repeated run")
            draft = regression_draft(
                data,
                path=artifact["path"],
                fingerprint=artifact["fingerprint"],
                case_id=body["case_id"],
                attempt=body["attempt"],
            )
            destination = f"regression-drafts/{draft['id']}.json"
            workspace.write_new(destination, draft)
            return workspace.read(destination)

    @app.post("/api/regression/review")
    def review(body: dict):
        if body.keys() != {"path", "fingerprint", "case", "reviewed"}:
            raise ValueError("Supply draft identity, case and explicit review status")
        with workspace.lock:
            artifact = current(body)
            draft = validate_regression_draft(
                {**artifact["data"], "case": body["case"], "reviewed": body["reviewed"]}
            )
            write_json_artifact(draft, workspace.path(body["path"]))
            return workspace.read(body["path"])

    def compose(body):
        draft = current(body)["data"]
        if not draft["reviewed"]:
            raise ValueError("Review the input and expectations before saving a suite")
        source = draft["source"]
        original = next(case for case in source["run"]["cases"] if case["id"] == source["case_id"])
        fixture_case = "tool_fixtures" in original
        simulation_case = source["run"]["schema_version"] == 6
        case = deepcopy(draft["case"])
        if fixture_case:
            # Include the retained scripts in the explicit suite preview so
            # saving cannot silently remove the original failure setup.
            case["tool_fixtures"] = deepcopy(original["tool_fixtures"])
        if simulation_case:
            case.setdefault("conversation", deepcopy(original["conversation"]))
            case.setdefault("state_fixture", deepcopy(original["state_fixture"]))
        destination = workspace.path(body["destination"])
        if destination.exists():
            target = workspace.read(body["destination"])
            if target["kind"] != "suite" or target["fingerprint"] != body["expected_fingerprint"]:
                raise ValueError("Destination changed or is not a suite; reload before saving")
            data = deepcopy(target["data"])
            if simulation_case and data["schema_version"] != 4:
                raise ValueError(
                    "Simulation regression cases require an identified simulation suite (schema 4)"
                )
            if fixture_case and data["schema_version"] not in (3, 4):
                raise ValueError(
                    "Fixture regression cases require a fixture suite. Create a new suite or enable tool fixtures in the destination editor first."
                )
            if data.get("suite"):
                if body["suite_id"] != data["suite"]["id"]:
                    raise ValueError("Keep the existing suite ID")
                if body["revision"] == data["suite"]["revision"]:
                    raise ValueError("Change the suite revision before adding a case")
                data["suite"]["revision"] = body["revision"]
            if data["schema_version"] == 3:
                case.setdefault("tool_fixtures", {})
            elif data["schema_version"] == 4:
                case.setdefault("tool_fixtures", {})
                case.setdefault("conversation", [])
                case.setdefault("state_fixture", None)
            data["cases"].append(case)
        else:
            if body["expected_fingerprint"] is not None:
                raise ValueError("Destination changed; reload before saving")
            data = {
                "schema_version": 4 if simulation_case else 3 if fixture_case else 2,
                "suite": {"id": body["suite_id"], "revision": body["revision"]},
                "cases": [case],
            }
        suite_from_dict(data)
        return data

    fields = {"path", "fingerprint", "destination", "expected_fingerprint", "suite_id", "revision"}

    @app.post("/api/regression/preview")
    def preview(body: dict):
        if body.keys() != fields:
            raise ValueError("Invalid suite preview fields")
        with workspace.lock:
            return compose(body)

    @app.post("/api/regression/publish")
    def publish(body: dict):
        if body.keys() != fields | {"confirmed"} or body["confirmed"] is not True:
            raise ValueError("Confirm the reviewed suite and destination")
        with workspace.lock:
            data = compose(body)
            return workspace.save_suite(body["destination"], data, body["expected_fingerprint"])
