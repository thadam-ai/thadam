"""Terminal presentation preserves result meaning with or without color."""

import io
import json
import re
from pathlib import Path

import pytest

from examples.refund_agent import run_buggy
from thadam import OutputEquals, load_suite, run_suite
from thadam import TestCase as AgentTestCase
from thadam.cli import main
from thadam.reporting import format_report_path, format_summary, write_report
from thadam.terminal import DARK_COLORS, LIGHT_COLORS, TerminalStyle, terminal_style

ROOT = Path(__file__).resolve().parents[1]
ANSI = re.compile(r"\x1b\[[0-9;]*m")


class Terminal(io.StringIO):
    def isatty(self):
        return True


@pytest.fixture
def clean_environment(monkeypatch):
    for key in ("NO_COLOR", "TERM", "COLORTERM", "COLORFGBG"):
        monkeypatch.delenv(key, raising=False)


def test_auto_color_requires_tty_and_honors_no_color(clean_environment, monkeypatch):
    assert terminal_style("auto", Terminal()).enabled
    assert not terminal_style("auto", io.StringIO()).enabled
    monkeypatch.setenv("NO_COLOR", "1")
    assert not terminal_style("auto", Terminal()).enabled
    assert terminal_style("always", Terminal()).enabled
    monkeypatch.setenv("NO_COLOR", "")
    assert terminal_style("auto", Terminal()).enabled
    monkeypatch.setenv("TERM", "dumb")
    assert not terminal_style("auto", Terminal()).enabled
    assert not terminal_style("never", Terminal()).enabled


def test_rgb_brand_palette_supports_light_backgrounds(clean_environment, monkeypatch):
    monkeypatch.setenv("COLORTERM", "truecolor")
    assert terminal_style("always", Terminal()).paint("PASSED", "brand") == (
        "\x1b[38;2;45;212;191mPASSED\x1b[0m"
    )
    monkeypatch.setenv("COLORFGBG", "0;15")
    assert terminal_style("always", Terminal()).paint("PASSED", "brand") == (
        "\x1b[38;2;0;112;107mPASSED\x1b[0m"
    )


def test_native_colors_are_fallback_without_rgb_support(clean_environment):
    assert terminal_style("always", Terminal()).paint("ERROR", "error", bold=True) == (
        "\x1b[1;31mERROR\x1b[0m"
    )


def test_semantic_colors_do_not_change_text_or_json(tmp_path):
    report = run_suite(run_buggy, load_suite(ROOT / "examples/refund_cases.json"))
    plain = format_summary(report)
    styled = format_summary(report, style=TerminalStyle(enabled=True, truecolor=True))
    assert ANSI.sub("", styled) == plain
    assert "\x1b[" not in plain
    assert "\x1b[1;38;2;45;212;191mPASSED" in styled
    assert "\x1b[1;38;2;251;191;36mFAILED" in styled
    assert "\x1b[1;38;2;248;113;113mERROR" in styled
    assert "\x1b[38;2;248;113;113magent: TimeoutError:" in styled
    assert "1 error" in plain
    assert "1 errors" not in plain
    destination = tmp_path / "report.json"
    write_report(report, destination)
    assert "\x1b" not in destination.read_text()
    assert json.loads(destination.read_text())["summary"] == {
        "total": 5,
        "passed": 3,
        "failed": 1,
        "errors": 1,
    }


@pytest.mark.parametrize("width", [20, 40, 80, 120])
def test_narrow_output_wraps_names_metadata_and_failure_evidence(width):
    case = AgentTestCase(
        "a-very-long-case-name-" * 4,
        None,
        (OutputEquals("wrong-answer", {"explanation": "long evidence " * 10}),),
    )
    report = run_suite(lambda _: {"actual": "different output " * 10}, [case])
    output = format_summary(
        report, width=width, suite="long-directory/" * 10, agent="long-agent-module-name:run"
    )
    assert all(len(line) <= min(width, 96) for line in output.splitlines())
    compact = "".join(output.split())
    assert "wrong-answer" in compact
    assert "expected:" in compact
    assert "actual:" in compact


def test_user_text_cannot_inject_terminal_status_colors():
    case = AgentTestCase("case\x1b[31m\nspoof", None, (OutputEquals("answer", "wanted"),))
    output = format_summary(run_suite(lambda _: "other", [case]))
    assert "\x1b" not in output
    assert "\\x1b[31m\\x0aspoof" in output


@pytest.mark.parametrize("width", [20, 80])
def test_report_location_has_spacing_and_wraps(width):
    output = format_report_path(
        "long-directory/" * 10 + "report.json", style=TerminalStyle(), width=width
    )
    assert output.startswith("  Report: ")
    assert all(len(line) <= width for line in output.splitlines())
    assert "long-directory/" * 10 + "report.json" in "".join(output.split())


@pytest.mark.parametrize("placement", ["before", "after"])
def test_cli_forced_color_keeps_json_plain(tmp_path, placement, clean_environment, capsys):
    path = tmp_path / "report.json"
    arguments = [
        "run",
        str(ROOT / "examples/refund_cases.json"),
        "--agent",
        "examples.refund_agent:run_buggy",
        "--report",
        str(path),
    ]
    if placement == "before":
        arguments = ["--color", "always", *arguments]
    else:
        arguments.extend(["--color", "always"])
    assert main(arguments) == 1
    captured = capsys.readouterr()
    assert "\x1b[" in captured.out
    assert "\x1b[1;31mERROR" in captured.out
    assert "\x1b[" not in path.read_text()


def test_cli_piped_and_never_output_are_plain(clean_environment, monkeypatch, capsys):
    monkeypatch.setenv("COLORTERM", "truecolor")
    arguments = [
        "run",
        str(ROOT / "examples/refund_cases.json"),
        "--agent",
        "examples.refund_agent:run",
    ]
    assert main(arguments) == 0
    assert "\x1b[" not in capsys.readouterr().out
    assert main(["--color", "never", *arguments]) == 0
    assert "\x1b[" not in capsys.readouterr().out


def test_cli_configuration_error_is_red(clean_environment, capsys):
    assert main(["run", "missing.json", "--agent", "agent:run", "--color", "always"]) == 2
    assert "\x1b[31mthadam:" in capsys.readouterr().err


def test_rgb_palettes_have_readable_contrast_on_reference_backgrounds():
    def luminance(color):
        channels = [channel / 255 for channel in color]
        linear = [
            part / 12.92 if part <= 0.04045 else ((part + 0.055) / 1.055) ** 2.4
            for part in channels
        ]
        return sum(part * weight for part, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

    for palette, background in [(DARK_COLORS, (7, 13, 19)), (LIGHT_COLORS, (255, 255, 255))]:
        for color in palette.values():
            darker, lighter = sorted((luminance(color), luminance(background)))
            assert (lighter + 0.05) / (darker + 0.05) >= 4.5
