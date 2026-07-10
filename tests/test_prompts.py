"""
Tests for prompts.py - interactive prompt behavior.
"""

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
