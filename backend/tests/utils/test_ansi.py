"""Tests for ANSI escape code stripping utility."""

import pytest

from app.utils.ansi import strip_ansi


class TestStripAnsi:
    """Tests for the strip_ansi function."""

    def test_empty_string(self) -> None:
        """Empty string returns empty string."""
        assert strip_ansi("") == ""

    def test_string_without_ansi(self) -> None:
        """String without ANSI codes is returned unchanged."""
        text = "Normal text without any escape codes"
        assert strip_ansi(text) == text

    def test_single_color_code(self) -> None:
        """Single color code is stripped."""
        # Red text
        assert strip_ansi("\x1b[31mRed text\x1b[0m") == "Red text"

    def test_multiple_color_codes(self) -> None:
        """Multiple color codes are all stripped."""
        # Red then green then reset
        text = "\x1b[31mRed\x1b[32mGreen\x1b[0mNormal"
        assert strip_ansi(text) == "RedGreenNormal"

    def test_bold_code(self) -> None:
        """Bold formatting code is stripped."""
        assert strip_ansi("\x1b[1mBold text\x1b[0m") == "Bold text"

    def test_combined_attributes(self) -> None:
        """Combined attributes (bold + color) are stripped."""
        # Bold red: \x1b[1;31m
        assert strip_ansi("\x1b[1;31mBold Red\x1b[0m") == "Bold Red"

    def test_multi_parameter_code(self) -> None:
        """Multi-parameter codes are stripped."""
        # SGR with multiple parameters: bold, underline, blue foreground
        assert strip_ansi("\x1b[1;4;34mStyled\x1b[0m") == "Styled"

    def test_cursor_movement_codes(self) -> None:
        """Cursor movement codes are stripped."""
        # Move cursor up: \x1b[2A
        assert strip_ansi("\x1b[2AText after cursor move") == "Text after cursor move"

        # Move cursor to position: \x1b[10;5H
        assert strip_ansi("\x1b[10;5HPositioned text") == "Positioned text"

    def test_clear_screen_code(self) -> None:
        """Clear screen codes are stripped."""
        # Clear screen: \x1b[2J
        assert strip_ansi("\x1b[2JCleared") == "Cleared"

    def test_reset_code_only(self) -> None:
        """Reset code alone is stripped."""
        assert strip_ansi("\x1b[0m") == ""

    def test_code_at_start(self) -> None:
        """Code at start of string is stripped."""
        assert strip_ansi("\x1b[33mYellow at start") == "Yellow at start"

    def test_code_at_end(self) -> None:
        """Code at end of string is stripped."""
        assert strip_ansi("Text then reset\x1b[0m") == "Text then reset"

    def test_code_in_middle(self) -> None:
        """Code in middle of string is stripped."""
        assert strip_ansi("Before\x1b[31mcolored\x1b[0mAfter") == "BeforecoloredAfter"

    def test_consecutive_codes(self) -> None:
        """Multiple consecutive codes are all stripped."""
        # Reset then bold then red
        assert strip_ansi("\x1b[0m\x1b[1m\x1b[31mText") == "Text"

    def test_preserves_newlines(self) -> None:
        """Newlines in text are preserved."""
        text = "\x1b[31mLine 1\n\x1b[32mLine 2\x1b[0m\nLine 3"
        assert strip_ansi(text) == "Line 1\nLine 2\nLine 3"

    def test_preserves_tabs(self) -> None:
        """Tabs in text are preserved."""
        text = "\x1b[31mColumn1\t\x1b[32mColumn2\x1b[0m"
        assert strip_ansi(text) == "Column1\tColumn2"

    def test_unicode_content_preserved(self) -> None:
        """Unicode characters in text are preserved."""
        text = "\x1b[31m日本語テキスト\x1b[0m"
        assert strip_ansi(text) == "日本語テキスト"

    def test_emoji_preserved(self) -> None:
        """Emoji characters are preserved."""
        text = "\x1b[33m⚠️ Warning!\x1b[0m"
        assert strip_ansi(text) == "⚠️ Warning!"

    def test_partial_escape_sequence_preserved(self) -> None:
        """Incomplete escape sequences are preserved (not valid ANSI)."""
        # Just the escape character without the full sequence
        text = "Text with partial \x1b sequence"
        assert strip_ansi(text) == "Text with partial \x1b sequence"

    def test_bracket_without_escape(self) -> None:
        """Brackets without escape are preserved."""
        text = "[31m This looks like ANSI but isn't"
        assert strip_ansi(text) == "[31m This looks like ANSI but isn't"

    def test_real_world_esp32_log(self) -> None:
        """Real-world ESP32 log message with colors is cleaned."""
        # Typical ESP32 log format with colors
        log = "\x1b[0;32mI (12345) main: Device started successfully\x1b[0m"
        assert strip_ansi(log) == "I (12345) main: Device started successfully"

    def test_multiple_lines_mixed_content(self) -> None:
        """Multi-line log with mixed colored and plain content."""
        log = """\x1b[0;32mI (100) app: Starting...\x1b[0m
\x1b[0;33mW (200) wifi: Connecting...\x1b[0m
Plain log line
\x1b[0;31mE (300) app: Error occurred!\x1b[0m"""

        expected = """I (100) app: Starting...
W (200) wifi: Connecting...
Plain log line
E (300) app: Error occurred!"""

        assert strip_ansi(log) == expected

    @pytest.mark.parametrize(
        "code,name",
        [
            ("\x1b[30m", "black"),
            ("\x1b[31m", "red"),
            ("\x1b[32m", "green"),
            ("\x1b[33m", "yellow"),
            ("\x1b[34m", "blue"),
            ("\x1b[35m", "magenta"),
            ("\x1b[36m", "cyan"),
            ("\x1b[37m", "white"),
        ],
    )
    def test_standard_colors(self, code: str, name: str) -> None:
        """All standard foreground colors are stripped."""
        text = f"{code}{name} text\x1b[0m"
        assert strip_ansi(text) == f"{name} text"

    @pytest.mark.parametrize(
        "code,name",
        [
            ("\x1b[40m", "black bg"),
            ("\x1b[41m", "red bg"),
            ("\x1b[42m", "green bg"),
            ("\x1b[43m", "yellow bg"),
            ("\x1b[44m", "blue bg"),
            ("\x1b[45m", "magenta bg"),
            ("\x1b[46m", "cyan bg"),
            ("\x1b[47m", "white bg"),
        ],
    )
    def test_background_colors(self, code: str, name: str) -> None:
        """Background color codes are stripped."""
        text = f"{code}{name}\x1b[0m"
        assert strip_ansi(text) == name
