"""Complete review and approval workflows through the real consumer CLI."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from thadam import (
    OutputEquals,
    ReportWriteError,
    SuiteIdentity,
    approve_review,
    load_baseline_review,
    load_report,
    review_baseline,
    run_suite,
    write_approved_baseline,
    write_report,
)
from thadam import TestCase as Case
from thadam import TestSuite as Suite

ROOT = Path(__file__).resolve().parents[1]


def invoke(*args, cwd):
    environment = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    return subprocess.run(
        [sys.executable, "-m", "thadam", *map(str, args)],
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        timeout=15,
    )


def create_suite(path, revision="1", value=1):
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "suite": {"id": "consumer", "revision": revision},
                "cases": [
                    {
                        "id": "echo",
                        "input": value,
                        "assertions": [
                            {"id": "output", "type": "output_equals", "expected": value}
                        ],
                    }
                ],
            }
        )
    )


@pytest.mark.parametrize("command,compare", [("run", "compare"), ("repeat", "compare-repeated")])
def test_real_consumer_initial_then_changed_contract_approval(tmp_path, command, compare):
    (tmp_path / "my_agent.py").write_text("def run(value):\n    return value\n")
    suite = tmp_path / "suite.json"
    create_suite(suite)
    result = invoke(
        command, suite, "--agent", "my_agent:run", "--report", "candidate.json", cwd=tmp_path
    )
    assert result.returncode == 0, result.stderr
    result = invoke("review-baseline", "candidate.json", "--report", "review.json", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "REVIEW REQUIRED" in result.stdout
    review = load_baseline_review(tmp_path / "review.json")
    options = [
        "--baseline",
        "baseline.json",
        "--review-digest",
        review.digest,
        "--reviewer",
        "Developer",
        "--reason",
        "Reviewed initial coverage",
    ]
    result = invoke("approve-baseline", "review.json", *options, cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "APPROVED" in result.stdout
    assert invoke(compare, "baseline.json", "candidate.json", cwd=tmp_path).returncode == 0
    original = (tmp_path / "baseline.json").read_bytes()
    create_suite(suite, revision="2", value=2)
    assert (
        invoke(
            command, suite, "--agent", "my_agent:run", "--report", "candidate.json", cwd=tmp_path
        ).returncode
        == 0
    )
    assert invoke(compare, "baseline.json", "candidate.json", cwd=tmp_path).returncode == 2
    result = invoke(
        "review-baseline",
        "candidate.json",
        "--baseline",
        "baseline.json",
        "--report",
        "review.json",
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "INPUT CHANGED" in result.stdout and "CHECK CHANGED" in result.stdout
    assert (tmp_path / "baseline.json").read_bytes() == original
    assert (
        invoke("approve-baseline", "review.json", *options, cwd=tmp_path).returncode == 2
    )  # stale digest
    review = load_baseline_review(tmp_path / "review.json")
    options[3] = review.digest
    result = invoke("approve-baseline", "review.json", *options, cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert invoke(compare, "baseline.json", "candidate.json", cwd=tmp_path).returncode == 0
    # Saved reviews reopen without agents or their source module.
    (tmp_path / "my_agent.py").unlink()
    result = invoke("review-baseline", "review.json", "--verbose", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "Attempt 1" in result.stdout


def test_failed_expectation_and_error_cli_guards(tmp_path):
    (tmp_path / "my_agent.py").write_text("def run(value):\n    return 0\n")
    create_suite(tmp_path / "suite.json")
    assert (
        invoke(
            "run",
            "suite.json",
            "--agent",
            "my_agent:run",
            "--report",
            "candidate.json",
            cwd=tmp_path,
        ).returncode
        == 1
    )
    result = invoke("review-baseline", "candidate.json", "--report", "review.json", cwd=tmp_path)
    assert result.returncode == 0
    assert "ACKNOWLEDGEMENT" in result.stdout
    review = load_baseline_review(tmp_path / "review.json")
    options = [
        "--baseline",
        "baseline.json",
        "--review-digest",
        review.digest,
        "--reviewer",
        "Developer",
        "--reason",
        "Known failure reviewed",
    ]
    assert invoke("approve-baseline", "review.json", *options, cwd=tmp_path).returncode == 2
    assert not (tmp_path / "baseline.json").exists()
    result = invoke("approve-baseline", "review.json", *options, "--accept-failures", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    (tmp_path / "my_agent.py").write_text("def run(value):\n    raise RuntimeError('offline')\n")
    assert (
        invoke(
            "run",
            "suite.json",
            "--agent",
            "my_agent:run",
            "--report",
            "candidate.json",
            cwd=tmp_path,
        ).returncode
        == 1
    )
    result = invoke("review-baseline", "candidate.json", "--report", "review.json", cwd=tmp_path)
    assert result.returncode == 1 and "BLOCKED" in result.stdout
    review = load_baseline_review(tmp_path / "review.json")
    options[1] = "other-baseline.json"
    options[3] = review.digest
    assert (
        invoke(
            "approve-baseline", "review.json", *options, "--accept-failures", cwd=tmp_path
        ).returncode
        == 2
    )
    assert not (tmp_path / "other-baseline.json").exists()


@pytest.mark.parametrize("alias", ["direct", "symlink", "hardlink"])
def test_cli_and_sdk_normal_writes_cannot_replace_approved_baseline(tmp_path, alias):
    candidate = run_suite(
        lambda x: x, Suite(SuiteIdentity("s", "1"), (Case("x", 1, (OutputEquals("out", 1),)),))
    )
    review = review_baseline(candidate)
    path = tmp_path / "baseline.json"
    write_approved_baseline(
        approve_review(review, review_digest=review.digest, reviewer="Me", reason="Reviewed"), path
    )
    original = path.read_bytes()
    target = path
    if alias != "direct":
        target = tmp_path / "alias.json"
        if alias == "symlink":
            target.symlink_to(path)
        else:
            os.link(path, target)
    with pytest.raises(ReportWriteError, match="Approved baselines"):
        write_report(candidate, target)
    create_suite(tmp_path / "suite.json")
    # Refuse before trying to import the user's agent.
    result = invoke("run", "suite.json", "--agent", "missing:run", "--report", target, cwd=tmp_path)
    assert result.returncode == 2 and "Approved baselines" in result.stderr
    assert path.read_bytes() == original
    assert load_report(path) == candidate


@pytest.mark.parametrize("alias", ["direct", "symlink", "hardlink"])
def test_review_cannot_clobber_source_via_alias(tmp_path, alias):
    path = tmp_path / "candidate.json"
    write_report(run_suite(lambda _: 1, [Case("x", 1, (OutputEquals("o", 1),))]), path)
    original = path.read_bytes()
    target = path
    if alias != "direct":
        target = tmp_path / "alias.json"
        if alias == "symlink":
            target.symlink_to(path)
        else:
            os.link(path, target)
    result = invoke("review-baseline", path, "--report", target, cwd=tmp_path)
    assert result.returncode == 2 and "must differ" in result.stderr
    assert path.read_bytes() == original


def test_approval_cannot_replace_review(tmp_path):
    candidate = run_suite(
        lambda _: 1, Suite(SuiteIdentity("s", "1"), (Case("x", None, (OutputEquals("o", 1),)),))
    )
    write_report(candidate, tmp_path / "candidate.json")
    assert (
        invoke(
            "review-baseline", "candidate.json", "--report", "review.json", cwd=tmp_path
        ).returncode
        == 0
    )
    review = load_baseline_review(tmp_path / "review.json")
    result = invoke(
        "approve-baseline",
        "review.json",
        "--baseline",
        "review.json",
        "--review-digest",
        review.digest,
        "--reviewer",
        "Me",
        "--reason",
        "Reviewed",
        cwd=tmp_path,
    )
    assert result.returncode == 2 and "must differ" in result.stderr


@pytest.mark.parametrize("contents", ["{", "{}", "[]", '{"x":1,"x":2}', '{"x":"\\ud800"}'])
def test_invalid_cli_review_is_configuration_error(tmp_path, contents):
    (tmp_path / "input.json").write_text(contents)
    result = invoke("review-baseline", "input.json", cwd=tmp_path)
    assert result.returncode == 2 and "Traceback" not in result.stderr
