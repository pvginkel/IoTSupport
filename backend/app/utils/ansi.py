"""ANSI escape code stripping utility.

Provides functions for removing ANSI escape sequences from strings,
commonly used for cleaning terminal output before logging or storage.
"""

import re

# ANSI escape sequence pattern
# Matches escape sequences like:
# - Color codes: \x1b[31m, \x1b[1;32m, \x1b[0m
# - Cursor movement: \x1b[2J, \x1b[H
# - Other SGR (Select Graphic Rendition) codes
_ANSI_ESCAPE_PATTERN = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from a string.

    This function strips terminal formatting codes like colors, cursor
    movement, and other SGR sequences, leaving only the plain text content.

    Args:
        text: Input string that may contain ANSI escape sequences

    Returns:
        String with all ANSI escape sequences removed

    Examples:
        >>> strip_ansi("\\x1b[31mRed text\\x1b[0m")
        'Red text'
        >>> strip_ansi("Normal text")
        'Normal text'
        >>> strip_ansi("")
        ''
    """
    return _ANSI_ESCAPE_PATTERN.sub("", text)
