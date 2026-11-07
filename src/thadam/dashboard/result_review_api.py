"""Project-confined routes for independent evaluation labels."""

from thadam.result_reviews import result_reviews, review_path, validate_result_reviews


def register_result_reviews(app, workspace):
    """Register explicit label read/write actions without changing saved runs."""

    @app.get("/api/result-reviews")
    def load(path: str):
        source = workspace.read(path)
        if source["kind"] not in ("run", "repeated_run"):
            raise ValueError("Choose a saved run or repeated run")
        source_data = {"kind": source["kind"], **source["data"]}
        reference = review_path(path)
        destination = workspace.path(reference)
        if destination.exists():
            artifact = workspace.read(reference)
            if artifact["kind"] != "result_reviews":
                raise ValueError("Review path is occupied by another artifact")
            if artifact["data"]["source"] != {
                "path": path,
                "fingerprint": source["fingerprint"],
                "kind": source["kind"],
                "id": source_data.get("report_id") or source_data.get("run_id"),
            }:
                raise ValueError("Source result changed; create labels for the current result")
            data = validate_result_reviews(artifact["data"], source=source_data)
            return {
                "path": reference,
                "fingerprint": artifact["fingerprint"],
                "data": data,
            }
        data = result_reviews(
            source_data,
            path=path,
            fingerprint=source["fingerprint"],
        )
        return {"path": reference, "fingerprint": None, "data": data}

    @app.post("/api/result-reviews")
    def save(body: dict):
        if body.keys() != {"path", "fingerprint", "review_fingerprint", "reviews"}:
            raise ValueError("Supply source identity, current label fingerprint, and reviews")
        return workspace.save_result_reviews(
            body["path"],
            body["fingerprint"],
            body["reviews"],
            body["review_fingerprint"],
        )
