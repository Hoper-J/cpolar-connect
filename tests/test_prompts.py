"""
Tests for prompts.py - interactive prompt behavior.
"""

import pytest

from cpolar_connect.prompts import Prompts


class TestConfirm:
    """Test confirm() cancellation semantics."""

    def test_ctrl_c_cancels_instead_of_accepting_default(self, monkeypatch):
        """Ctrl+C must cancel (False), not silently accept the default."""

        def raise_interrupt(prompt=""):
            raise KeyboardInterrupt

        monkeypatch.setattr("builtins.input", raise_interrupt)
        p = Prompts()
        assert p.confirm("Continue?", default=True) is False

    def test_eof_cancels_instead_of_accepting_default(self, monkeypatch):
        """Closed stdin must cancel (False), not silently accept the default."""

        def raise_eof(prompt=""):
            raise EOFError

        monkeypatch.setattr("builtins.input", raise_eof)
        p = Prompts()
        assert p.confirm("Continue?", default=True) is False

    def test_skip_confirm_still_returns_default(self):
        """-y mode keeps returning the default without prompting."""
        p = Prompts(skip_confirm=True)
        assert p.confirm("Continue?", default=True) is True
        assert p.confirm("Continue?", default=False) is False


class TestSpinner:
    """A spinner leaves the cursor on its line until it is completed."""

    def test_done_overwrites_the_spinner_line(self, capsys):
        p = Prompts()
        p.spinner_message("Testing SSH connection")
        p.spinner_done("SSH connection OK")

        out = capsys.readouterr().out
        assert out.count("\n") == 1
        assert "Testing SSH connection...\r" in out

    @pytest.mark.parametrize(
        "method",
        [
            "log",
            "log_info",
            "log_warn",
            "log_error",
            "log_success",
            "step",
            "intro",
            "outro",
            "outro_cancel",
            "note",
            "spinner_message",
        ],
    )
    def test_output_after_an_unfinished_spinner_starts_a_new_line(self, capsys, method):
        """When the operation raises instead of completing, the next message
        must not be appended to the spinner line."""
        p = Prompts()
        p.spinner_message("Testing SSH connection")
        getattr(p, method)("Connection failed")

        lines = capsys.readouterr().out.split("\n")
        assert lines[0].endswith("Testing SSH connection...")
        assert any("Connection failed" in line for line in lines[1:])

    @pytest.mark.parametrize("prompt", ["text", "password", "confirm"])
    def test_prompt_after_an_unfinished_spinner_starts_a_new_line(
        self, capsys, monkeypatch, prompt
    ):
        monkeypatch.setattr("builtins.input", lambda text="": "y")
        monkeypatch.setattr("cpolar_connect.prompts.getpass", lambda text="": "pw")
        p = Prompts()
        p.spinner_message("Trying existing SSH keys")
        getattr(p, prompt)("Enter something")

        assert capsys.readouterr().out == (
            "│  \x1b[36m◌\x1b[0m Trying existing SSH keys...\n"
        )

    def test_no_blank_line_when_the_spinner_was_completed(self, capsys):
        p = Prompts()
        p.spinner_message("Testing SSH connection")
        p.spinner_done("SSH connection OK")
        p.log_error("Something else failed")

        assert capsys.readouterr().out.count("\n") == 2

    def test_quiet_mode_has_no_spinner_to_finish(self, capsys):
        p = Prompts(quiet=True)
        p.spinner_message("Testing SSH connection")
        p.log_error("Connection failed")

        out = capsys.readouterr().out
        assert out.count("\n") == 1 and not out.startswith("\n")
