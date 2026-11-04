"""Explicit local provider connections, scenario drafts and reviewed suite saves."""

from thadam.generation import (
    INSTRUCTIONS,
    draft_issues,
    review_candidate,
    selected_suite,
    validate_request,
    write_draft,
)
from thadam.providers.chatgpt_auth import ChatGPTSignIn
from thadam.providers.credentials import CredentialStore
from thadam.providers.openai import connect_api_key, connection_status, list_models
from thadam.suite_writing import file_fingerprint


def register_generation(app, workspace, jobs):
    store = CredentialStore()
    signin = ChatGPTSignIn(store)
    app.state.signin = signin

    @app.get("/api/providers")
    def providers():
        return {**connection_status(store), "signin": signin.status()}

    @app.post("/api/providers/api-key")
    def api_key(body: dict):
        if body.keys() != {"key"}:
            raise ValueError("Supply only an API key")
        connect_api_key(body["key"], store)
        return connection_status(store)

    @app.post("/api/providers/chatgpt")
    def login():
        return {"url": signin.start()}

    @app.post("/api/providers/disconnect")
    def disconnect(body: dict):
        if body.keys() != {"connection"}:
            raise ValueError("Choose a connection")
        if body["connection"] == "chatgpt":
            signin.close()
        store.disconnect(body["connection"])
        return connection_status(store)

    @app.get("/api/providers/models")
    def models(connection: str):
        return list_models(connection, store=store)

    @app.post("/api/providers/notice")
    def acknowledge_notice():
        with store.locked():
            data = store.read()
            if data.get("chatgpt"):
                data["chatgpt"]["plan_notice_ack"] = True
                store.write(data)
        return {"acknowledged": True}

    @app.post("/api/generate/preview")
    def preview_context(body: dict):
        return {"instructions": INSTRUCTIONS, "request": validate_request(body)}

    @app.post("/api/generate")
    def generate(body: dict):
        if body.keys() != {"connection", "model", "request", "source", "report"}:
            raise ValueError("Generation settings have missing or unknown fields")
        return jobs.start_generation({**body, "kind": "generation"})

    def current(body):
        artifact = workspace.read(body["path"])
        if artifact["kind"] != "scenario_draft" or artifact["fingerprint"] != body["fingerprint"]:
            raise ValueError("Draft changed; reload before reviewing or saving")
        return artifact

    @app.post("/api/draft/review")
    def review(body: dict):
        if body.keys() != {"path", "fingerprint", "index", "decision", "case"}:
            raise ValueError("Review settings have missing or unknown fields")
        with workspace.lock:
            artifact = current(body)
            result = review_candidate(
                artifact["data"], body["index"], decision=body["decision"], case=body["case"]
            )
            write_draft(
                result, workspace.path(body["path"]), expected_fingerprint=body["fingerprint"]
            )
            return workspace.read(body["path"])

    @app.get("/api/draft/issues")
    def issues(path: str):
        artifact = workspace.read(path)
        if artifact["kind"] != "scenario_draft":
            raise ValueError("Choose a scenario draft")
        return [
            draft_issues(artifact["data"], i) for i in range(len(artifact["data"]["candidates"]))
        ]

    def preview(body):
        artifact = current(body)
        return selected_suite(
            artifact["data"], suite_id=body.get("suite_id"), revision=body.get("revision")
        )

    @app.post("/api/draft/preview")
    def preview_suite(body: dict):
        return preview(body)

    @app.post("/api/draft/publish")
    def publish(body: dict):
        if body.keys() != {
            "path",
            "fingerprint",
            "suite_id",
            "revision",
            "destination",
            "expected_fingerprint",
        }:
            raise ValueError("Save settings have missing or unknown fields")
        with workspace.lock:
            artifact = current(body)
            source = artifact["data"]["source"]
            if source and file_fingerprint(workspace.path(source["path"])) != source["fingerprint"]:
                raise ValueError(
                    "Source suite changed; generate a fresh draft against the current suite"
                )
            if source and workspace.path(body["destination"]) == workspace.path(source["path"]):
                if body["expected_fingerprint"] != source["fingerprint"]:
                    raise ValueError("Use the original source suite fingerprint")
            elif body["expected_fingerprint"] is not None:
                raise ValueError("Choose a new destination or the captured source suite")
            return workspace.save_suite(
                body["destination"], preview(body), body["expected_fingerprint"]
            )

    return signin
