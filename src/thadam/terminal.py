"""Terminal color roles inspired by the Thadam logo; no rendering side effects."""

import os
from dataclasses import dataclass
from typing import Literal, TextIO

ColorMode = Literal["auto", "always", "never"]
ColorRole = Literal["brand", "info", "muted", "failed", "error"]

# Use the terminal's native palette when RGB support is not advertised.
ANSI_COLORS: dict[ColorRole, str] = {
    "brand": "36",
    "info": "34",
    "muted": "90",
    "failed": "33",
    "error": "31",
}
DARK_COLORS: dict[ColorRole, tuple[int, int, int]] = {
    "brand": (45, 212, 191),
    "info": (56, 189, 248),
    "muted": (148, 163, 184),
    "failed": (251, 191, 36),
    "error": (248, 113, 113),
}
LIGHT_COLORS: dict[ColorRole, tuple[int, int, int]] = {
    "brand": (0, 112, 107),
    "info": (3, 105, 161),
    "muted": (71, 85, 105),
    "failed": (146, 64, 14),
    "error": (185, 28, 28),
}


@dataclass(frozen=True)
class TerminalStyle:
    """Optional terminal styling; a default instance produces plain text."""

    enabled: bool = False
    truecolor: bool = False
    light_background: bool = False

    def paint(self, text: str, role: ColorRole, *, bold: bool = False) -> str:
        if not self.enabled:
            return text
        code = ANSI_COLORS[role]
        if self.truecolor:
            palette = LIGHT_COLORS if self.light_background else DARK_COLORS
            red, green, blue = palette[role]
            code = f"38;2;{red};{green};{blue}"
        weight = "1;" if bold else ""
        return f"\033[{weight}{code}m{text}\033[0m"


def terminal_style(mode: ColorMode, stream: TextIO) -> TerminalStyle:
    """Choose color per output stream, honoring explicit flags before NO_COLOR.

    Auto mode requires a TTY and disables color for TERM=dumb or a non-empty
    NO_COLOR. RGB is used only when COLORTERM advertises support. COLORFGBG's
    conventional white background values select the darker RGB palette.
    """
    enabled = mode == "always" or (
        mode == "auto"
        and stream.isatty()
        and os.environ.get("TERM") != "dumb"
        and not os.environ.get("NO_COLOR")
    )
    return TerminalStyle(
        enabled=enabled,
        truecolor=os.environ.get("COLORTERM", "").lower() in {"truecolor", "24bit"},
        light_background=os.environ.get("COLORFGBG", "").split(";")[-1] in {"7", "15"},
    )


def display_text(value: str) -> str:
    """Keep terminal control characters in user-supplied text visible and inert."""
    return "".join(
        f"\\x{ord(character):02x}"
        if ord(character) < 32 or 127 <= ord(character) < 160
        else character
        for character in value
    )
