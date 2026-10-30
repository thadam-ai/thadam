"""Saved evidence cannot silently drop checks or contradict its own contract."""

import json
from dataclasses import replace

import pytest

from thadam import (
    AgentResult,
    ExecutionEvent,
    OutputEquals,
    ReportValidationError,
    ToolArgumentsMatch,
    ToolCalled,
    Verifier,
    compare_reports,
    load_report,
    report_to_dict,
    run_suite,
    write_report,
)
from thadam import TestCase as AgentCase


@pytest.fixture
def raw_report():
    return report_to_dict(
        run_suite(
            lambda value: value,
            [
                AgentCase("echo", {"value": 1}, (OutputEquals("answer", {"value": 1}),)),
            ],
        )
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.update(schema_version=2),
        lambda r: r.update(schema_version=99),
        lambda r: r.update(schema_version=True),
        lambda r: r.update(evaluation_version=True),
        lambda r: r.update(evaluation_version=2),
        lambda r: r.update(agent_revision=""),
        lambda r: r.update(extra=True),
        lambda r: r.update(cases=[]),
        lambda r: r["cases"].append(r["cases"][0]),
        lambda r: r["summary"].update(total=2),
        lambda r: r["summary"].update(total=True),
        lambda r: r["cases"][0].update(status="failed"),
        lambda r: r["cases"][0].update(duration_ms=True),
        lambda r: r["cases"][0].update(duration_ms=-1),
        lambda r: r["cases"][0].update(output_available=False),
        lambda r: r["cases"][0].update(trace_complete=True),
        lambda r: r["cases"][0].update(trace_warnings=["missing"]),
        lambda r: r["cases"][0].update(assertions=[]),
        lambda r: r["cases"][0].update(check_definitions=[]),
        lambda r: r["cases"][0]["check_definitions"].append(r["cases"][0]["check_definitions"][0]),
        lambda r: r["cases"][0]["check_definitions"][0]["parameters"].update(id="override"),
        lambda r: r["cases"][0]["check_definitions"][0].update(type="unknown"),
        lambda r: r["cases"][0]["assertions"].append(r["cases"][0]["assertions"][0]),
        lambda r: r["cases"][0]["assertions"][0].update(passed=1),
        lambda r: r["cases"][0]["assertions"][0].update(id="not-declared"),
        lambda r: r["cases"][0]["assertions"][0].update(event_ids=["orphan"]),
        lambda r: r["cases"][0]["assertions"][0].update(actual={"value": 999}),
        lambda r: r["cases"][0]["assertions"][0].update(expected={"value": 999}),
    ],
)
def test_rejects_invalid_or_contradictory_reports(tmp_path, raw_report, mutate):
    mutate(raw_report)
    path = tmp_path / "report.json"
    path.write_text(json.dumps(raw_report))
    with pytest.raises(ReportValidationError):
        load_report(path)


@pytest.mark.parametrize(
    "text",
    [
        '{"schema_version":3,"schema_version":3}',
        '{"value":NaN}',
        '{"value":"\\ud800"}',
        "[]",
        "{}",
        "{",
        '{"cases":' + "[" * 110 + "0" + "]" * 110 + "}",
    ],
)
def test_malformed_json_and_duplicate_keys_are_rejected(tmp_path, text):
    path = tmp_path / "bad.json"
    path.write_text(text)
    with pytest.raises(ReportValidationError):
        load_report(path)


def test_missing_and_invalid_utf8_files_use_public_error(tmp_path):
    path = tmp_path / "missing.json"
    with pytest.raises(ReportValidationError):
        load_report(path)
    path.write_bytes(b"\xff")
    with pytest.raises(ReportValidationError):
        load_report(path)


def test_forged_success_cannot_override_failed_builtin_evidence(tmp_path):
    report = run_suite(lambda _: 0, [AgentCase("case", None, (OutputEquals("answer", 1),))])
    raw = report_to_dict(report)
    raw["cases"][0]["assertions"][0]["passed"] = True
    raw["cases"][0]["status"] = "passed"
    raw["summary"] = {"total": 1, "passed": 1, "failed": 0, "errors": 0}
    path = tmp_path / "forged.json"
    path.write_text(json.dumps(raw))
    with pytest.raises(ReportValidationError, match="contradicts"):
        load_report(path)


def test_partial_errors_and_versioned_verifiers_round_trip(tmp_path):
    def verifier(_i, _o):
        raise RuntimeError("cannot verify")

    cases = [
        AgentCase("verifier-error", None, verifiers=(Verifier("policy", verifier, "v1"),)),
        AgentCase("tool-error", None, (ToolCalled("lookup", "get_order"),)),
    ]
    report = run_suite(
        lambda _: AgentResult(None, trace_complete=False, trace_warnings=("gap",)), cases
    )
    path = tmp_path / "partial.json"
    write_report(report, path)
    assert load_report(path) == report
    assert compare_reports(report, load_report(path)).exit_code == 1


def test_trace_links_and_structured_tool_evidence_are_validated(tmp_path):
    event = ExecutionEvent(
        "call",
        "tool",
        "lookup",
        "completed",
        0,
        duration_ms=1,
        input={"id": 1},
        input_available=True,
    )
    case = AgentCase("tools", None, (ToolArgumentsMatch("args", "lookup", {"id": 1}),))
    report = run_suite(lambda _: AgentResult(None, (event,)), [case])
    path = tmp_path / "tools.json"
    write_report(report, path)
    assert load_report(path) == report
    raw = report_to_dict(report)
    raw["cases"][0]["events"][0]["input_available"] = False
    raw["cases"][0]["events"][0]["input"] = None
    path.write_text(json.dumps(raw))
    with pytest.raises(ReportValidationError, match="Unavailable tool evidence"):
        load_report(path)


def test_check_errors_cannot_replace_verdicts_or_reference_unknown_checks(tmp_path):
    report = run_suite(lambda _: None, [AgentCase("tools", None, (ToolCalled("tool", "lookup"),))])
    raw = report_to_dict(report)
    raw["cases"][0]["errors"][0]["assertion_id"] = "unknown"
    path = tmp_path / "error.json"
    path.write_text(json.dumps(raw))
    with pytest.raises(ReportValidationError):
        load_report(path)
    raw["cases"][0]["errors"][0]["assertion_id"] = "tool"
    raw["cases"][0]["errors"].append(raw["cases"][0]["errors"][0])
    path.write_text(json.dumps(raw))
    with pytest.raises(ReportValidationError, match="Duplicate check errors"):
        load_report(path)


def test_execution_error_retains_contracts_for_all_unexecuted_checks(tmp_path):
    def agent(_):
        raise SystemExit(0)

    report = run_suite(agent, [AgentCase("case", None, (OutputEquals("answer", 1),))])
    assert report.cases[0].check_definitions[0].parameters == {"expected": 1}
    path = tmp_path / "execution-error.json"
    write_report(report, path)
    assert load_report(path) == report
    corrupted = replace(report.cases[0], output_available=True)
    with pytest.raises(ReportValidationError, match="Execution errors"):
        compare_reports(report, replace(report, cases=(corrupted,)))


def test_report_wrappers_do_not_reduce_the_sdk_payload_depth_budget(tmp_path):
    value = 1
    for _ in range(100):
        value = [value]
    report = run_suite(
        lambda item: item,
        [
            AgentCase(
                "nested",
                value,
                (OutputEquals("echo", value),),
            )
        ],
    )
    path = tmp_path / "nested.json"
    write_report(report, path)
    assert compare_reports(report, load_report(path)).exit_code == 0
    raw = report_to_dict(report)
    raw["cases"][0]["input"] = [raw["cases"][0]["input"]]
    path.write_text(json.dumps(raw))
    with pytest.raises(ReportValidationError, match="100 levels"):
        load_report(path)
