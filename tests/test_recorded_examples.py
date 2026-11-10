"""Strict previews and untrusted regression drafts for recorded examples."""

import json

import pytest

from thadam.recorded_examples import (
    normalize_mapping,
    normalize_masks,
    parse_recorded_examples,
    recorded_example_draft,
)
from thadam.regression import validate_regression_draft


def parse(content, *, format="jsonl", mapping=None, masks=None):
    return parse_recorded_examples(
        content,
        format=format,
        path="examples.jsonl",
        fingerprint="a" * 64,
        mapping=mapping or {"input": "input", "source_id": "id", "expected": "expected"},
        mask_fields=masks or [],
    )


def test_jsonl_import_projects_masks_and_proposes_unreviewed_expectations():
    content = (
        '{"id":"case-1","input":{"email":"person@example.com"},'
        '"expected":{"ok":true},"context":{"phone":"555-0100"},'
        '"extra":"must not be retained"}\n'
        '{"id":"case-2","input":{"email":"hello"},"context":{"phone":"555-0101"}}\n'
    ).encode()
    preview = parse(
        content,
        mapping={
            "source_id": "id",
            "input": "input",
            "expected": "expected",
            "context": "context",
            "actual": None,
            "events": None,
            "tags": None,
        },
        masks=["input.email", "context.phone"],
    )

    assert preview["summary"] == {
        "total": 2,
        "valid": 2,
        "invalid": 0,
        "duplicates": 0,
        "already_imported": 0,
    }
    first = preview["rows"][0]
    assert first["record"] == {
        "source_id": "case-1",
        "input": {"email": "[REDACTED]"},
        "expected": {"ok": True},
        "context": {"phone": "[REDACTED]"},
    }
    draft = recorded_example_draft(preview, first)
    assert draft["schema_version"] == 2
    assert draft["case"]["assertions"] == [
        {"id": "recorded-expected-output", "type": "output_equals", "expected": {"ok": True}}
    ]
    assert draft["reviewed"] is False
    assert draft["source"]["record"] == first["record"]
    second = recorded_example_draft(preview, preview["rows"][1])
    assert second["case"]["assertions"] == []
    with pytest.raises(ValueError, match="at least one check"):
        validate_regression_draft({**second, "reviewed": True})


def test_duplicate_review_tracks_source_id_even_after_an_input_duplicate():
    content = b"\n".join(
        json.dumps(item).encode()
        for item in [
            {"id": "first", "input": "same"},
            {"id": "second", "input": "same"},
            {"id": "second", "input": "different"},
        ]
    )
    preview = parse(content)
    assert [row["duplicate_reasons"] for row in preview["rows"]] == [
        [],
        ["input"],
        ["source_id"],
    ]
    assert [row["duplicate_of"] for row in preview["rows"]] == [None, 1, 2]
    duplicate = recorded_example_draft(preview, preview["rows"][2])
    assert duplicate["source"]["duplicate_of"] == 2
    assert duplicate["source"]["duplicate_reasons"] == ["source_id"]


def test_expected_mask_suppresses_proposed_assertion_and_preview_value():
    preview = parse(
        b'{"id":"a","input":"hi","expected":{"secret":"answer"}}',
        masks=["expected.secret"],
    )
    row = preview["rows"][0]
    assert row["record"]["expected"] == {"secret": "[REDACTED]"}
    assert "will not seed an output assertion" in row["warnings"][0]
    assert recorded_example_draft(preview, row)["case"]["assertions"] == []


def test_unmatched_masks_block_rows_and_whole_tag_masks_keep_tags_structured():
    preview = parse(
        b'{"id":"a","input":"hello","context":"phone: 555-0100","tags":["private-tag","other"]}',
        mapping={
            "source_id": "id",
            "input": "input",
            "context": "context",
            "tags": "tags",
        },
        masks=["context.phone", "tags"],
    )
    assert preview["rows"][0]["valid"] is False
    assert preview["rows"][0]["record"] == {}
    assert "does not match" in preview["rows"][0]["errors"][0]

    valid = parse(
        b'{"id":"a","input":"hello","tags":["private-tag","other"]}',
        mapping={"source_id": "id", "input": "input", "tags": "tags"},
        masks=["tags"],
    )
    draft = recorded_example_draft(valid, valid["rows"][0])
    assert draft["source"]["record"]["tags"] == ["[REDACTED]"]


def test_overlapping_masks_are_rejected_before_preview():
    mapping = normalize_mapping({"input": "prompt", "context": "metadata"})
    with pytest.raises(ValueError, match="overlap"):
        normalize_masks(["context.*", "context.phone"], mapping)


def test_csv_structure_and_cells_are_validated_without_guessing_types():
    content = b"example_id,prompt,answer\na-1,25,0\na-2\n"
    preview = parse(
        content,
        format="csv",
        mapping={"source_id": "example_id", "input": "prompt", "expected": "answer"},
    )
    assert preview["rows"][0]["record"] == {
        "source_id": "a-1",
        "input": "25",
        "expected": "0",
    }
    assert preview["rows"][1]["valid"] is False
    assert "different number of cells" in preview["rows"][1]["errors"][0]
    with pytest.raises(ValueError, match="unique"):
        parse(b"input,input\na,b\n", format="csv")


def test_malformed_jsonl_rows_are_visible_and_omitted_fields_stay_absent():
    preview = parse(b'{"id":"a","input":"hello"}\n{"input":\n')
    assert preview["summary"]["valid"] == 1
    assert preview["summary"]["invalid"] == 1
    assert preview["rows"][0]["record"] == {"source_id": "a", "input": "hello"}
    assert "expected" not in preview["rows"][0]["record"]


@pytest.mark.parametrize(
    "content,format,mapping,masks,message",
    [
        (b"input\na\n", "csv", {"input": "input"}, ["source_id.x"], "Mask paths"),
        (b"input\na\n", "csv", {"input": "input"}, ["context.phone"], "no source field"),
    ],
)
def test_import_rejects_ambiguous_or_unmapped_data(content, format, mapping, masks, message):
    with pytest.raises(ValueError, match=message):
        parse(content, format=format, mapping=mapping, masks=masks)


@pytest.mark.parametrize(
    "content,message",
    [
        (b'{"id":"a","input":"x","input":"y"}', "Duplicate JSON"),
        (b'{"id":"a","input":NaN}', "Non-finite"),
    ],
)
def test_ambiguous_jsonl_rows_are_reported_invalid(content, message):
    preview = parse(content)
    assert preview["summary"]["valid"] == 0
    assert preview["summary"]["invalid"] == 1
    assert message in preview["rows"][0]["errors"][0]


def test_normalizers_require_input_and_unique_reviewable_masks():
    with pytest.raises(ValueError, match="required input"):
        normalize_mapping({"expected": "answer"})
    mapping = normalize_mapping({"input": "prompt", "context": "metadata"})
    with pytest.raises(ValueError, match="unique"):
        normalize_masks(["context.phone", "context.phone"], mapping)
    with pytest.raises(ValueError, match="empty path"):
        normalize_masks(["context..phone"], mapping)
