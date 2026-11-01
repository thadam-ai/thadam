"""User-visible report hierarchy, adaptive layouts, grouping, and verbose evidence."""

import json
import re
import unicodedata
from dataclasses import replace

import pytest

from thadam import (
    AgentResult,
    ExecutionEvent,
    OutputEquals,
    TokenUsage,
    ToolCalled,
    compare_repeated,
    compare_reports,
    comparison_to_dict,
    reliability_to_dict,
    repeated_to_dict,
    report_to_dict,
    run_repeated,
)
from thadam import TestCase as AgentCase
from thadam.cli import main
from thadam.comparison_reporting import format_comparison
from thadam.reliability_reporting import format_reliability_comparison
from thadam.repetition_reporting import format_repeated
from thadam.reporting import format_summary
from thadam.terminal import TerminalStyle

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def repeated(values, cases=None):
    answers = iter(values)
    return run_repeated(
        lambda _: next(answers),
        cases or [AgentCase("case", None, (OutputEquals("answer", 1),))],
        attempts=len(values),
    )


@pytest.fixture
def reports():
    baseline = repeated([1, 1, 1])
    candidate = repeated([0, 0, 2])
    return [
        (format_summary, candidate.runs[0], report_to_dict),
        (
            format_comparison,
            compare_reports(baseline.runs[0], candidate.runs[0]),
            comparison_to_dict,
        ),
        (format_repeated, candidate, repeated_to_dict),
        (format_reliability_comparison, compare_repeated(baseline, candidate), reliability_to_dict),
    ]


@pytest.mark.parametrize("width", [20, 40, 88, 96])
@pytest.mark.parametrize("verbose", [False, True])
def test_every_view_preserves_evidence_and_colorless_layout(reports, width, verbose):
    for formatter, report, serialize in reports:
        before = json.dumps(serialize(report), sort_keys=True)
        plain = formatter(report, width=width, verbose=verbose)
        colored = formatter(
            report, width=width, verbose=verbose, style=TerminalStyle(enabled=True, truecolor=True)
        )
        assert ANSI.sub("", colored) == plain
        assert all(len(line) <= width for line in plain.splitlines())
        assert plain.count("THADAM") == 1
        assert before == json.dumps(serialize(report), sort_keys=True)


def test_result_and_counts_precede_cases_and_narrow_rows_keep_values(reports):
    for formatter, report, _ in reports:
        output = formatter(report, width=96)
        verdict = "BLOCKED" if "comparison" in formatter.__name__ else "FAILED"
        assert output.index(verdict) < output.index("CASE")
        assert "1 failed" in output or "3 failed" in output or "regression" in output
        narrow = formatter(report, width=30)
        assert "CASE  " not in narrow
        assert "case" in narrow
        assert "Result" in narrow or "Candidate" in narrow or "Passed" in narrow


def test_identical_evidence_groups_but_different_values_stay_distinct():
    report = repeated([0, 0, 2])
    output = format_repeated(report)
    assert output.count("FAILED: case / answer") == 2
    assert "attempts 1-2 / 2 occurrences" in output
    assert "attempts 3 / 1 occurrence" in output
    assert "actual:   0" in output and "actual:   2" in output
    assert "--verbose" in output
    verbose = format_repeated(report, verbose=True)
    assert verbose.count("FAILED: case / answer") == 3
    assert all(f"Attempt {number}" in verbose for number in (1, 2, 3))
    assert all(run.run_id in verbose for run in report.runs)
    assert verbose.count("THADAM") == 1


def test_baseline_and_candidate_failure_groups_remain_separate():
    comparison = compare_repeated(repeated([1, 0, 0]), repeated([0, 0, 2]))
    output = format_reliability_comparison(comparison)
    assert "Baseline attempts 2-3 / 2 occurrences" in output
    assert "Candidate attempts 1-2 / 2 occurrences" in output
    assert "Candidate attempts 3 / 1 occurrence" in output
    assert output.count("FAILED: case / answer") == 3


def test_grouped_trace_is_representative_and_verbose_shows_every_span():
    calls = []

    def agent(_):
        calls.append(1)
        index = len(calls)
        return AgentResult(
            0,
            (
                ExecutionEvent(
                    f"event-{index}",
                    "tool",
                    "lookup",
                    "completed",
                    0,
                    duration_ms=1,
                    input={"attempt": index},
                    input_available=True,
                    output=None,
                    output_available=True,
                ),
                ExecutionEvent(
                    f"model-{index}",
                    "model",
                    "model",
                    "completed",
                    1,
                    duration_ms=1,
                    output=None,
                    output_available=True,
                    usage=TokenUsage(total_tokens=0),
                ),
            ),
        )

    report = run_repeated(
        agent,
        [
            AgentCase(
                "case",
                None,
                (
                    OutputEquals("answer", 1),
                    ToolCalled("lookup", "lookup"),
                ),
            )
        ],
        attempts=3,
    )
    output = format_repeated(report)
    assert output.count("FAILED: case / answer") == 1
    assert "Representative attempt 1" in output
    assert "event-1" in output and "event-2" not in output
    verbose = format_repeated(report, verbose=True)
    assert all(f"event-{index}" in verbose for index in (1, 2, 3))
    assert "PASSED: case / lookup" in verbose
    assert '"total_tokens": 0' in verbose and "output: null" in verbose
    assert len(calls) == 3


def test_verbose_single_run_and_comparison_expand_passing_checks():
    report = repeated([1, 1])
    assert "PASSED: case / answer" not in format_summary(report.runs[0])
    assert "PASSED: case / answer" in format_summary(report.runs[0], verbose=True)
    comparison = compare_reports(report.runs[0], report.runs[1])
    assert "answer:" not in format_comparison(comparison)
    assert "answer: UNCHANGED PASS" in format_comparison(comparison, verbose=True)


def test_different_error_messages_are_not_merged():
    messages = iter(["service A", "service A", "service B"])

    def agent(_):
        raise TimeoutError(next(messages))

    report = run_repeated(
        agent, [AgentCase("case", None, (OutputEquals("answer", 1),))], attempts=3
    )
    output = format_repeated(report)
    assert output.count("ERROR: case") == 2
    assert "attempts 1-2 / 2 occurrences" in output
    assert "service A" in output and "service B" in output
    assert report.cases[0].counts.errors == 3


def test_trace_warnings_and_unavailable_versus_observed_empty_remain_explicit():
    cases = [AgentCase("case", None, (OutputEquals("answer", 1),))]
    report = run_repeated(lambda _: AgentResult(1, (), False, ("callback gap",)), cases, attempts=2)
    output = format_repeated(report)
    assert "PASSED" in output and "TRACE WARNING: case" in output
    assert "FAILED:" not in output
    assert output.count("trace: callback gap") == 1
    assert "No events observed" in output
    plain = run_repeated(lambda _: 1, cases, attempts=2)
    assert "Trace      unavailable" in format_repeated(plain, verbose=True)


def test_check_regression_inside_always_failed_cases_stays_visible():
    cases = [AgentCase("case", None, (OutputEquals("always-fails", 9), OutputEquals("answer", 1)))]
    comparison = compare_repeated(repeated([1, 1], cases), repeated([0, 0], cases))
    output = format_reliability_comparison(comparison)
    assert "BLOCKED" in output and "check answer:" in output
    assert "-100.00 pp; REGRESSION" in output
    assert comparison.exit_code == 1


def test_long_metadata_and_control_characters_remain_inert():
    case = AgentCase("long-case-" * 10 + "\x1b[31m", None, (OutputEquals("answer", 1),))
    report = repeated([0, 0], [case])
    report = replace(
        report, runs=tuple(replace(run, agent_revision="revision/" * 20) for run in report.runs)
    )
    for verbose in (False, True):
        output = format_repeated(report, width=30, verbose=verbose)
        assert "\x1b" not in output and "\\x1b[31m" in "".join(output.split())
        assert "long-case-" * 10 in "".join(output.split())
        assert all(len(line) <= 30 for line in output.splitlines())


def test_wide_case_names_wrap_without_losing_characters():
    name = "退款条件" * 12
    cases = [AgentCase(name, None, (OutputEquals("answer", 1),))]
    output = format_repeated(repeated([0, 0], cases), width=30)
    assert name in "".join(output.split())
    assert all(
        sum(2 if unicodedata.east_asian_width(char) in ("W", "F") else 1 for char in line) <= 30
        for line in output.splitlines()
    )


@pytest.mark.parametrize("command", ["run", "compare", "repeat", "compare-repeated"])
@pytest.mark.parametrize("placement", ["before", "after"])
def test_cli_verbose_keeps_artifact_and_exit_code(tmp_path, capsys, command, placement):
    from thadam import write_repeated, write_report

    suite = tmp_path / "cases.json"
    suite.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "cases": [
                    {
                        "id": "case",
                        "input": {"order_id": "order-001", "days_since_purchase": 7},
                        "assertions": [
                            {"id": "fields", "type": "output_has_keys", "keys": ["approved"]}
                        ],
                    }
                ],
            }
        )
    )
    baseline, candidate = repeated([1, 1]), repeated([0, 0])
    for side, report in (("baseline", baseline), ("candidate", candidate)):
        if command == "compare":
            write_report(report.runs[0], tmp_path / f"{side}.json")
        else:
            write_repeated(report, tmp_path / f"{side}.json")
    if command in ("run", "repeat"):
        args = [command, str(suite), "--agent", "examples.refund_agent:run"]
        if command == "repeat":
            args.extend(["--attempts", "2"])
    else:
        args = [command, str(tmp_path / "baseline.json"), str(tmp_path / "candidate.json")]
    outputs, artifacts, codes = [], [], []
    for verbose in (False, True):
        destination = tmp_path / f"report-{verbose}.json"
        arguments = [*args, "--report", str(destination)]
        if verbose:
            arguments = (
                ["--verbose", *arguments] if placement == "before" else [*arguments, "--verbose"]
            )
        codes.append(main(arguments))
        outputs.append(capsys.readouterr().out)
        artifacts.append(json.loads(destination.read_text()))
    assert codes[0] == codes[1] == (0 if command in ("run", "repeat") else 1)
    assert len(outputs[1]) > len(outputs[0])
    if command in ("compare", "compare-repeated"):
        assert artifacts[0] == artifacts[1]
    else:
        assert artifacts[0]["summary"]["passed"] == artifacts[1]["summary"]["passed"]
        for artifact in artifacts:
            runs = [artifact] if command == "run" else artifact["runs"]
            assert all(run["cases"][0]["output"]["approved"] is True for run in runs)
