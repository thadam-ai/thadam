"""Verify an installed wheel from outside the checkout, using only the standard library."""

from importlib.metadata import distribution
from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory

from thadam import (
    OutputEquals,
    TestCase,
    __version__,
    compare_reports,
    load_report,
    run_suite,
    write_report,
)


def main() -> None:
    """Check distribution identity, packaged types, and a real SDK/report round trip."""
    installed = distribution("thadam-ai")
    if installed.metadata["Name"] != "thadam-ai" or installed.version != __version__:
        raise SystemExit("Installed distribution name/version differs from the SDK")
    if not files("thadam").joinpath("py.typed").is_file():
        raise SystemExit("Installed package is missing its type marker")
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
    print(f"thadam-ai {installed.version}: installed SDK and report comparison passed")


if __name__ == "__main__":
    main()
