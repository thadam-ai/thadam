"""Project-confined preview and import actions for recorded examples."""

from __future__ import annotations

import hashlib

from thadam.dashboard.workspace import fingerprint
from thadam.recorded_examples import (
    MAX_IMPORT_BYTES,
    normalize_mapping,
    normalize_masks,
    parse_recorded_examples,
    recorded_example_draft,
    recorded_example_draft_id,
)


def register_recorded_examples(app, workspace):
    """Register local import actions; previews never write project artifacts."""

    def preview_file(path_reference, format, mapping, mask_fields, expected_fingerprint=None):
        if not isinstance(path_reference, str) or not path_reference:
            raise ValueError("Choose a project-relative examples file")
        path = workspace.path(path_reference)
        if not path.is_file():
            raise ValueError("Choose an existing JSONL or CSV file")
        if path.stat().st_size > MAX_IMPORT_BYTES:
            raise ValueError("Recorded examples exceed the 8 MiB import limit")
        content = path.read_bytes()
        source_fingerprint = hashlib.sha256(content).hexdigest()
        if expected_fingerprint is not None and source_fingerprint != expected_fingerprint:
            raise ValueError("Recorded examples changed; preview the current file again")
        field_mapping = normalize_mapping(mapping)
        masks = normalize_masks(mask_fields, field_mapping)
        result = parse_recorded_examples(
            content,
            format=format,
            path=path_reference,
            fingerprint=source_fingerprint,
            mapping=field_mapping,
            mask_fields=masks,
        )
        if fingerprint(path) != source_fingerprint:
            raise ValueError("Recorded examples changed while loading; preview again")
        for row in result["rows"]:
            if not row["valid"]:
                continue
            identifier = recorded_example_draft_id(
                path_reference,
                source_fingerprint,
                format,
                row["line"],
                field_mapping,
                masks,
            )
            destination = workspace.path(f"regression-drafts/{identifier}.json")
            row["already_imported"] = destination.exists()
        result["summary"]["already_imported"] = sum(
            row["already_imported"] for row in result["rows"]
        )
        return result

    @app.post("/api/recorded-examples/preview")
    def preview(body: dict):
        if body.keys() != {"path", "format", "mapping", "mask_fields"}:
            raise ValueError("Supply a source file, format, field mapping and masks")
        return preview_file(body["path"], body["format"], body["mapping"], body["mask_fields"])

    @app.post("/api/recorded-examples/import")
    def import_examples(body: dict):
        if body.keys() != {
            "path",
            "format",
            "mapping",
            "mask_fields",
            "fingerprint",
            "selected_rows",
            "acknowledged_duplicates",
        }:
            raise ValueError("Supply the preview identity, selected rows and duplicate review")
        selected = _positive_rows(body["selected_rows"], "selected rows")
        acknowledged = _positive_rows(body["acknowledged_duplicates"], "duplicate acknowledgements")
        if not selected:
            raise ValueError("Select at least one valid example row")
        if not acknowledged <= selected:
            raise ValueError("A duplicate acknowledgement must be for a selected row")
        with workspace.lock:
            result = preview_file(
                body["path"],
                body["format"],
                body["mapping"],
                body["mask_fields"],
                expected_fingerprint=body["fingerprint"],
            )
            rows_by_line = {row["line"]: row for row in result["rows"]}
            chosen = []
            for line in selected:
                row = rows_by_line.get(line)
                if row is None or not row["valid"]:
                    raise ValueError(f"Source row {line} is invalid or absent from the preview")
                if row["already_imported"]:
                    raise ValueError(f"Source row {line} was already imported")
                if row["duplicate_reasons"] and line not in acknowledged:
                    raise ValueError(f"Review and acknowledge duplicate source row {line}")
                if not row["duplicate_reasons"] and line in acknowledged:
                    raise ValueError(f"Source row {line} is not a duplicate")
                chosen.append(row)
            artifacts = []
            references = []
            for row in chosen:
                draft = recorded_example_draft(result, row)
                reference = f"regression-drafts/{draft['id']}.json"
                if workspace.path(reference).exists():
                    raise ValueError(f"Source row {row['line']} was already imported")
                artifacts.append(draft)
                references.append(reference)
            source_path = workspace.path(body["path"])
            if fingerprint(source_path) != result["fingerprint"]:
                raise ValueError("Recorded examples changed before import; preview again")
            for reference, artifact in zip(references, artifacts):
                workspace.write_new(reference, artifact)
            return {"drafts": [workspace.read(reference) for reference in references]}


def _positive_rows(value: object, name: str) -> set[int]:
    if not isinstance(value, list) or any(type(row) is not int or row < 1 for row in value):
        raise ValueError(f"{name.capitalize()} must be positive row numbers")
    rows = set(value)
    if len(rows) != len(value):
        raise ValueError(f"{name.capitalize()} must not contain duplicates")
    return rows
