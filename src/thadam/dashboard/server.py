"""Optional loopback API and bundled React application for one local workspace."""

from __future__ import annotations

import hmac
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from thadam.baseline_approval import write_approved_baseline
from thadam.baseline_review import (
    approve_review,
    load_baseline_review,
    load_evaluation,
    review_baseline,
    review_to_dict,
)
from thadam.comparison import compare_reports
from thadam.comparison_reporting import comparison_to_dict
from thadam.dashboard.jobs import Jobs
from thadam.dashboard.workspace import Workspace
from thadam.models import RunReport
from thadam.reliability import compare_repeated
from thadam.reliability_reporting import reliability_to_dict
from thadam.repetition import RepeatedReport


def create_app(root: str | Path, *, token: str | None = None) -> FastAPI:
    """Build a local app with explicit session authentication and project confinement.

    No agents execute during discovery, loading, or comparison. Execution is only
    available through a deliberate authenticated request, in a managed subprocess.
    Dependencies are optional; import this module only for dashboard use.
    """
    workspace = Workspace(root)
    jobs = Jobs(workspace)
    secret = token or secrets.token_urlsafe(32)

    @asynccontextmanager
    async def lifespan(_app):
        yield
        jobs.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.token, app.state.jobs, app.state.workspace = secret, jobs, workspace

    @app.middleware("http")
    async def local_session(request: Request, call_next):
        if request.url.hostname not in ("127.0.0.1", "localhost", "::1", "testserver"):
            return JSONResponse({"error": "Use the local dashboard address"}, status_code=403)
        if request.method not in ("GET", "HEAD"):
            origin = request.headers.get("origin")
            if origin and (
                urlsplit(origin).netloc != request.url.netloc
                or urlsplit(origin).scheme != request.url.scheme
            ):
                return JSONResponse(
                    {"error": "Cross-origin actions are not allowed"}, status_code=403
                )
            try:
                length = int(request.headers.get("content-length", "0"))
            except ValueError:
                return JSONResponse({"error": "Invalid content length"}, status_code=400)
            if length > 8 * 1024 * 1024:
                return JSONResponse({"error": "Request exceeds the 8 MiB limit"}, status_code=413)
        if request.url.path.startswith("/api/") and request.url.path != "/api/session":
            supplied = request.cookies.get(f"thadam_session_{request.url.port or 80}", "")
            if not hmac.compare_digest(supplied.encode(), secret.encode()):
                return JSONResponse(
                    {
                        "error": "Open the dashboard link printed in your terminal to connect this browser"
                    },
                    status_code=401,
                )
        try:
            response = await call_next(request)
        except (ValueError, OSError, TypeError, KeyError, RecursionError) as error:
            return JSONResponse({"error": str(error)}, status_code=400)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/api/session")
    def session(request: Request):
        if not hmac.compare_digest(
            request.headers.get("x-thadam-token", "").encode(), secret.encode()
        ):
            return JSONResponse(
                {"error": "Open the current terminal dashboard link"}, status_code=401
            )
        response = JSONResponse({"connected": True})
        response.set_cookie(
            f"thadam_session_{request.url.port or 80}", secret, httponly=True, samesite="strict"
        )
        return response

    @app.get("/api/workspace")
    def catalog():
        return workspace.catalog()

    @app.get("/api/artifact")
    def artifact(path: str):
        return workspace.read(path)

    @app.get("/api/agents")
    def agents():
        return workspace.settings()

    @app.put("/api/agents")
    def save_agents(body: list[dict]):
        return workspace.settings(body)

    @app.put("/api/suite")
    def save_suite(body: dict):
        return workspace.save_suite(body["path"], body["data"], body.get("fingerprint"))

    @app.get("/api/jobs")
    def list_jobs():
        return jobs.list()

    @app.get("/api/jobs/{identifier}")
    def job(identifier: str):
        return jobs.detail(identifier)

    @app.post("/api/jobs")
    def start_job(body: dict):
        return jobs.start(body)

    @app.post("/api/stop")
    def stop_job():
        return jobs.stop()

    @app.post("/api/compare")
    def compare(body: dict):
        destination = workspace.output(body["report"]) if body.get("report") else None
        baseline = load_evaluation(workspace.path(body["baseline"]))
        candidate = load_evaluation(workspace.path(body["candidate"]))
        if isinstance(baseline, RepeatedReport) and isinstance(candidate, RepeatedReport):
            result = reliability_to_dict(
                compare_repeated(
                    baseline, candidate, max_pass_rate_drop=body.get("max_pass_rate_drop", 0)
                )
            )
        elif isinstance(baseline, RunReport) and isinstance(candidate, RunReport):
            result = comparison_to_dict(compare_reports(baseline, candidate))
        else:
            raise ValueError("Choose two single evaluations or two repeated evaluations")
        if destination:
            workspace.write_new(body["report"], result)
        return result

    @app.post("/api/review")
    def review(body: dict):
        workspace.output(body["report"])
        candidate = load_evaluation(workspace.path(body["candidate"]))
        baseline = (
            load_evaluation(workspace.path(body["baseline"])) if body.get("baseline") else None
        )
        result = review_baseline(candidate, baseline)
        workspace.write_new(body["report"], review_to_dict(result))
        return workspace.read(body["report"])

    @app.post("/api/approve")
    def approve(body: dict):
        source, destination = workspace.path(body["review"]), workspace.path(body["baseline"])
        if source == destination or (
            source.exists() and destination.exists() and source.samefile(destination)
        ):
            raise ValueError("Approval destination must differ from the review file")
        approval = approve_review(
            load_baseline_review(source),
            review_digest=body["review_digest"],
            reviewer=body["reviewer"],
            reason=body["reason"],
            accept_failures=body.get("accept_failures", False),
        )
        with workspace.lock:
            write_approved_baseline(approval, destination)
        return workspace.read(body["baseline"])

    static = Path(__file__).parent / "static"

    @app.get("/{path:path}")
    def frontend(path: str):
        candidate = (static / path).resolve()
        if path and candidate.is_relative_to(static.resolve()) and candidate.is_file():
            return FileResponse(candidate)
        if not path:
            return FileResponse(static / "index.html")
        return JSONResponse({"error": "Page not found"}, status_code=404)

    return app
