"""
Tests for cli._verify_cpolar_credentials - init-time credential verification.

The helper must delegate to CpolarAuth (single login implementation) and
support a custom base_url instead of hardcoding the official dashboard.
"""

from cpolar_connect import cli as cli_module
from cpolar_connect.exceptions import AuthenticationError


class FakeAuth:
    """Stands in for CpolarAuth; records constructor args."""

    captured = {}

    def __init__(self, config_manager=None, base_url=None):
        FakeAuth.captured["base_url"] = base_url
        self.login_error = None

    def login(self, username=None, password=None):
        FakeAuth.captured["username"] = username
        if FakeAuth.captured.get("fail"):
            raise AuthenticationError("bad credentials")
        return object()


def test_passes_base_url_through(monkeypatch):
    FakeAuth.captured = {}
    monkeypatch.setattr(cli_module, "CpolarAuth", FakeAuth)
    cli_module._verify_cpolar_credentials("u", "p", base_url="https://example.com")
    assert FakeAuth.captured["base_url"] == "https://example.com"


def test_returns_true_on_successful_login(monkeypatch):
    FakeAuth.captured = {}
    monkeypatch.setattr(cli_module, "CpolarAuth", FakeAuth)
    assert cli_module._verify_cpolar_credentials("u", "p") is True
    assert FakeAuth.captured["username"] == "u"


def test_returns_false_on_authentication_error(monkeypatch):
    FakeAuth.captured = {"fail": True}
    monkeypatch.setattr(cli_module, "CpolarAuth", FakeAuth)
    assert cli_module._verify_cpolar_credentials("u", "p") is False
