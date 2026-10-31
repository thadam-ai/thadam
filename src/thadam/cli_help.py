"""Help presentation using Thadam's palette after argparse has laid out plain text."""

import argparse
import re
import sys

from thadam.terminal import ColorMode, TerminalStyle

HEADING = "THADAM - Testing and reliability for AI agents"


class HelpParser(argparse.ArgumentParser):
    """Render help with an explicitly supplied style and consistent Python-version behavior."""

    def __init__(self, *args, help_style: TerminalStyle, **kwargs) -> None:
        # Python 3.14 introduced its own help colors. Disable those so our palette
        # and --color/NO_COLOR policy own every help page, including redirected output.
        if sys.version_info >= (3, 14):
            kwargs["color"] = False
        self.help_style = help_style
        super().__init__(*args, **kwargs)

    def format_help(self) -> str:
        """Style completed help text without letting ANSI codes affect wrapping/alignment."""
        plain = super().format_help()
        style = self.help_style
        lines = [style.paint(HEADING, "brand", bold=True), ""]
        usage = False
        for line in plain.splitlines():
            text = line.strip()
            if text.startswith("usage:"):
                usage = True
                prefix, rest = line.split(":", 1)
                line = style.paint(prefix + ":", "info") + style.paint(rest, "muted")
            elif not text:
                usage = False
            elif usage:
                line = style.paint(line, "muted")
            elif text in (
                "positional arguments:",
                "options:",
                "optional arguments:",
                "Getting started",
                "Choose a workflow",
                "Learn more",
            ) or text.startswith(("Examples (", "Repository example (")):
                line = style.paint(line, "info", bold=True)
            elif text.startswith("thadam "):
                line = style.paint(line, "brand")
            elif text.startswith(("-", "{")) or text.split()[0] in (
                "run",
                "compare",
                "repeat",
                "compare-repeated",
                "suite",
                "baseline",
                "candidate",
            ):
                # Color action names without coloring the explanation column.
                match = re.match(r"(\s*)(.*?)(\s{2,}.*)?$", line)
                indent, label, explanation = match.groups()
                role = "info" if text.startswith("-") else "brand"
                line = indent + style.paint(label, role) + (explanation or "")
            lines.append(line)
        return "\n".join(lines) + "\n"


def help_color_mode(arguments: list[str]) -> ColorMode:
    """Read the color policy before --help exits, including flags after --help.

    This parser reads only terminal policy; it does not import application modules
    or load files. The full CLI parser remains responsible for command arguments.
    """
    parser = HelpParser(prog="thadam", add_help=False, help_style=TerminalStyle())
    parser.add_argument("--color", choices=("auto", "always", "never"), default="auto")
    known, _ = parser.parse_known_args(arguments)
    return known.color
