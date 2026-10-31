"""Help follows Thadam's palette and color policy across every entry point."""

import re
import sys

import pytest

from thadam.cli import main
from thadam.cli_help import HEADING

ANSI = re.compile(r"\x1b\[[0-9;]*m")
PAGES = [
    [],
    ["--help"],
    *[
        [command, "--help"]
        for command in (
            "run",
            "compare",
            "repeat",
            "compare-repeated",
        )
    ],
]


def show(arguments, capsys):
    if not arguments:
        assert main(arguments) == 0
    else:
        with pytest.raises(SystemExit) as exit:
            main(arguments)
        assert exit.value.code == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    return captured.out


@pytest.mark.parametrize("page", PAGES)
@pytest.mark.parametrize(
    "colorterm,background,brand,info",
    [
        ("", "", "36", "34"),
        ("truecolor", "0;0", "38;2;45;212;191", "38;2;56;189;248"),
        ("24bit", "0;15", "38;2;0;112;107", "38;2;3;105;161"),
    ],
)
def test_all_help_pages_use_brand_palette_and_preserve_layout(
    page, colorterm, background, brand, info, monkeypatch, capsys
):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setenv("COLORTERM", colorterm)
    monkeypatch.setenv("COLORFGBG", background)
    monkeypatch.delenv("NO_COLOR", raising=False)
    colored = show(page, capsys)
    assert colored.startswith(f"\x1b[1;{brand}m{HEADING}\x1b[0m\n")
    assert f"\x1b[1;{info}moptions:" in colored
    if page in ([], ["--help"]):
        assert f"\x1b[1;{info}mGetting started" in colored
        assert f"\x1b[{brand}m  thadam run cases.json" in colored
    else:
        assert f"\x1b[1;{info}mExamples (" in colored
    monkeypatch.setenv("NO_COLOR", "1")
    plain = show(page, capsys)
    assert "\x1b[" not in plain
    assert ANSI.sub("", colored) == plain


@pytest.mark.parametrize("page", PAGES)
@pytest.mark.parametrize(
    "tty,term,no_color",
    [
        (False, "xterm-256color", ""),
        (True, "dumb", ""),
        (True, "xterm-256color", "1"),
    ],
)
def test_auto_plain_output_even_when_python_native_color_is_forced(
    page, tty, term, no_color, monkeypatch, capsys
):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: tty)
    monkeypatch.setenv("TERM", term)
    monkeypatch.setenv("NO_COLOR", no_color)
    monkeypatch.setenv("FORCE_COLOR", "1")
    assert "\x1b[" not in show(page, capsys)


@pytest.mark.parametrize("page", PAGES[1:])
@pytest.mark.parametrize("position", ["before", "after"])
def test_explicit_policy_before_or_after_help_overrides_environment(
    page, position, monkeypatch, capsys
):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("TERM", "dumb")
    monkeypatch.setenv("COLORTERM", "truecolor")
    for mode, colored in (("always", True), ("never", False)):
        arguments = ["--color", mode, *page] if position == "before" else [*page, "--color", mode]
        output = show(arguments, capsys)
        assert ("\x1b[" in output) == colored


def test_help_uses_last_explicit_color_policy(monkeypatch, capsys):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    output = show(["--color", "always", "run", "--help", "--color", "never"], capsys)
    assert "\x1b[" not in output
