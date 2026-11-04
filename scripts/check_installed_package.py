"""Verify an installed wheel from outside the checkout, using only the standard library."""

from importlib.metadata import distribution
from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory

from thadam import (
    GenerationResult,
    OutputEquals,
    SuiteIdentity,
    TestCase,
    __version__,
    approve_review,
    compare_repeated,
    compare_reports,
    load_baseline_review,
    load_draft,
    load_reliability_comparison,
    load_repeated,
    load_report,
    load_suite,
    publish_draft,
    review_baseline,
    review_candidate,
    run_repeated,
    run_suite,
    suggest_cases,
    write_approved_baseline,
    write_baseline_review,
    write_draft,
    write_reliability_comparison,
    write_repeated,
    write_report,
)


def main() -> None:
    """Check distribution identity, packaged types, and a real SDK/report round trip."""
    installed = distribution("thadam-ai")
    if installed.metadata["Name"] != "thadam-ai" or installed.version != __version__:
        raise SystemExit("Installed distribution name/version differs from the SDK")
    if not files("thadam").joinpath("py.typed").is_file():
        raise SystemExit("Installed package is missing its type marker")
    static = files("thadam.dashboard").joinpath("static")
    if (
        not static.joinpath("index.html").is_file()
        or not static.joinpath("THIRD_PARTY_NOTICES.txt").is_file()
    ):
        raise SystemExit("Installed package is missing its bundled dashboard")
    import re

    for asset in re.findall(
        r'(?:src|href)="(\./assets/[^\"]+)"', static.joinpath("index.html").read_text()
    ):
        if not static.joinpath(asset.removeprefix("./")).is_file():
            raise SystemExit(f"Installed dashboard asset is missing: {asset}")
    case = TestCase(
        id="installed-sdk",
        input={"value": 1},
        assertions=(OutputEquals("echo", {"value": 1}),),
    )
    report = run_suite(agent=lambda value: value, cases=[case])
    if report.summary.passed != 1:
        raise SystemExit("Installed SDK failed its test case")
    with TemporaryDirectory() as directory:
        path = Path(directory) / "report.json"
        write_report(report, path)
        comparison = compare_reports(report, load_report(path))
        if comparison.exit_code != 0:
            raise SystemExit("Installed report round trip failed comparison")
        repeated = run_repeated(agent=lambda value: value, cases=[case], attempts=2)
        repeated_path = Path(directory) / "repeated.json"
        write_repeated(repeated, repeated_path)
        reliability = compare_repeated(repeated, load_repeated(repeated_path))
        comparison_path = Path(directory) / "reliability.json"
        write_reliability_comparison(reliability, comparison_path)
        if load_reliability_comparison(comparison_path).exit_code != 0:
            raise SystemExit("Installed reliability round trip failed comparison")

        class ControlledProvider:
            def generate(self, request):
                return GenerationResult(
                    [
                        {
                            "category": "normal",
                            "rationale": "Controlled echo contract",
                            "uncertainty": "",
                            "case": {
                                "id": "generated-echo",
                                "input": 1,
                                "assertions": [
                                    {"id": "echo", "type": "output_equals", "expected": 1}
                                ],
                            },
                        }
                    ],
                    "installed_fixture",
                    "controlled",
                )

        draft = suggest_cases(
            ControlledProvider(),
            {
                "description": "Echo agent",
                "behavior": "Return input unchanged",
                "examples": [{"input": 1, "output": 1}],
                "count": 1,
            },
        )
        draft_path = Path(directory) / "draft.json"
        write_draft(draft, draft_path)
        accepted = review_candidate(load_draft(draft_path), 0, decision="accepted")
        suite_path = Path(directory) / "generated-suite.json"
        publish_draft(accepted, suite_path, suite_id="generated", revision="v1")
        if run_suite(lambda value: value, load_suite(suite_path)).summary.passed != 1:
            raise SystemExit("Installed generation/review/suite round trip failed")
        for is_repeated in (False, True):
            execute = run_repeated if is_repeated else run_suite
            candidate = execute(lambda value: value, [case], suite=SuiteIdentity("installed", "v1"))
            review = review_baseline(candidate)
            review_path = Path(directory) / "review.json"
            write_baseline_review(review, review_path)
            reviewed = load_baseline_review(review_path)
            approval = approve_review(
                reviewed,
                review_digest=review.digest,
                reviewer="Installation check",
                reason="Controlled fixture",
            )
            baseline_path = Path(directory) / f"approved-{is_repeated}.json"
            write_approved_baseline(approval, baseline_path)
            loader = load_repeated if is_repeated else load_report
            compare = compare_repeated if is_repeated else compare_reports
            if compare(loader(baseline_path), candidate).exit_code != 0:
                raise SystemExit("Installed suite/baseline review round trip failed")
    print(f"thadam-ai {installed.version}: installed SDK and report comparison passed")


if __name__ == "__main__":
    main()
