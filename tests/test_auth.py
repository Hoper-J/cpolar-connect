"""
Tests for auth.py - CSRF extraction and login verification.
"""

import pytest
from unittest.mock import Mock
from bs4 import BeautifulSoup
from cpolar_connect.auth import CpolarAuth


class TestCsrfExtraction:
    """Test CSRF token extraction from login page."""

    def test_extract_csrf_from_hidden_input(self, sample_login_form_html):
        """Should extract CSRF token from hidden input field."""
        soup = BeautifulSoup(sample_login_form_html, 'html.parser')
        csrf_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_input is not None
        token = csrf_input.get("value")
        assert token == "1538662349.68##b5aa35f374452a6198004dab20d88b13583c7c2c"

    def test_extract_csrf_from_meta_tag(self):
        """Should extract CSRF token from meta tag as fallback."""
        html = '<html><head><meta name="csrf-token" content="meta_token_123"></head></html>'
        soup = BeautifulSoup(html, 'html.parser')
        meta = soup.find("meta", {"name": "csrf-token"})
        assert meta is not None
        assert meta.get("content") == "meta_token_123"

    def test_csrf_token_format(self, sample_login_form_html):
        """CSRF token should have expected format (timestamp##hash)."""
        soup = BeautifulSoup(sample_login_form_html, 'html.parser')
        csrf_input = soup.find("input", {"name": "csrf_token"})
        token = csrf_input.get("value")
        # Token format: timestamp##hash
        assert "##" in token
        parts = token.split("##")
        assert len(parts) == 2


class TestLoginVerification:
    """Test login success/failure verification logic."""

    def test_verify_success_redirect_away_from_login(self):
        """Should detect success when redirected away from /login."""
        mock_response = Mock()
        mock_response.url = "https://dashboard.cpolar.com/get-started"

        auth = CpolarAuth.__new__(CpolarAuth)
        result = auth._verify_authentication(mock_response)
        assert result is True

    def test_verify_success_redirect_to_status(self):
        """Should detect success when redirected to status page."""
        mock_response = Mock()
        mock_response.url = "https://dashboard.cpolar.com/status"

        auth = CpolarAuth.__new__(CpolarAuth)
        result = auth._verify_authentication(mock_response)
        assert result is True

    def test_verify_success_redirect_to_dashboard(self):
        """Should detect success when redirected to dashboard page."""
        mock_response = Mock()
        mock_response.url = "https://dashboard.cpolar.com/dashboard"

        auth = CpolarAuth.__new__(CpolarAuth)
        result = auth._verify_authentication(mock_response)
        assert result is True

    def test_verify_failure_still_on_login_page(self):
        """Should detect failure when still on login page."""
        mock_response = Mock()
        mock_response.url = "https://dashboard.cpolar.com/login"

        auth = CpolarAuth.__new__(CpolarAuth)
        result = auth._verify_authentication(mock_response)
        assert result is False
