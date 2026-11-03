"""Progress observes completed snapshots without changing evaluation evidence."""

import pytest

from thadam import OutputEquals, SuiteValidationError, run_repeated, run_suite
from thadam import TestCase as Case


def test_progress_is_ordered_and_separate_from_recorded_inputs_outputs():
    calls = []

    def observe(case):
        calls.append((case.id, case.status))
        case.input["changed"] = True
        case.output["changed"] = True

    cases = [
        Case("first", {}, (OutputEquals("out", {}),)),
        Case("second", {}, (OutputEquals("out", {}),)),
    ]
    report = run_repeated(lambda value: value, cases, attempts=3, on_case_complete=observe)
    assert calls == [("first", "passed"), ("second", "passed")] * 3
    assert all(case.input == case.output == {} for run in report.runs for case in run.cases)


@pytest.mark.parametrize("execute", [run_suite, run_repeated])
def test_invalid_progress_fails_before_user_code(execute):
    calls = []
    with pytest.raises(SuiteValidationError, match="on_case_complete"):
        execute(
            lambda value: calls.append(value),
            [Case("x", 1, (OutputEquals("out", 1),))],
            on_case_complete=1,
        )
    assert not calls


def test_progress_retains_errors_and_callbacks_do_not_become_agent_errors():
    seen = []

    def broken(_):
        raise RuntimeError("agent failed")

    report = run_suite(
        broken, [Case("x", 1, (OutputEquals("out", 1),))], on_case_complete=seen.append
    )
    assert seen[0].errors == report.cases[0].errors

    def failed_callback(_):
        raise RuntimeError("observer failed")

    with pytest.raises(RuntimeError, match="observer failed"):
        run_suite(
            lambda value: value,
            [Case("x", 1, (OutputEquals("out", 1),))],
            on_case_complete=failed_callback,
        )
