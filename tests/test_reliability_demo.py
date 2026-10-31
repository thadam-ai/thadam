"""The runnable SDK demo follows terminal color policy and preserves plain artifacts."""

import sys

import pytest

from examples.reliability_demo import main
from thadam import load_reliability_comparison


@pytest.mark.parametrize(
    "tty,no_color,term,colorterm,expected",
    [
        (True, "", "xterm-256color", "truecolor", "\x1b[38;2;251;191;36mREGRESSION"),
        (True, "", "xterm-256color", "", "\x1b[33mREGRESSION"),
        (False, "", "xterm-256color", "truecolor", "REGRESSION"),
        (True, "1", "xterm-256color", "truecolor", "REGRESSION"),
        (True, "", "dumb", "truecolor", "REGRESSION"),
    ],
)
def test_demo_color_policy_and_gate(
    tmp_path, monkeypatch, capsys, tty, no_color, term, colorterm, expected
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: tty)
    monkeypatch.setenv("NO_COLOR", no_color)
    monkeypatch.setenv("TERM", term)
    monkeypatch.setenv("COLORTERM", colorterm)
    monkeypatch.setenv("COLORFGBG", "0;0")
    assert main() == 1
    output = capsys.readouterr().out
    assert expected in output
    if expected == "REGRESSION":
        assert "\x1b[" not in output
    destination = tmp_path / "artifacts/reliability-demo/comparison.json"
    assert "\x1b[" not in destination.read_text()
    assert load_reliability_comparison(destination).exit_code == 1
