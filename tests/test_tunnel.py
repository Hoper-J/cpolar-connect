"""
Tests for tunnel.py - Tunnel URL parsing and extraction.
"""

import pytest
from cpolar_connect.tunnel import TunnelManager, TunnelInfo
from cpolar_connect.exceptions import TunnelError


class TestTunnelUrlParsing:
    """Test tunnel URL parsing from HTML."""

    def test_parse_ssh_tunnel_from_table(self, sample_status_html):
        """Should extract SSH tunnel (local port 22) from table."""
        manager = TunnelManager.__new__(TunnelManager)
        url = manager._parse_tunnel_url(sample_status_html)
        # Should find the 'default' tunnel with local port 22
        assert url == "tcp://7.tcp.vip.cpolar.cn:12766"

    def test_skip_remote_desktop_tunnel(self, sample_status_html):
        """Should skip remoteDesktop tunnel by default."""
        manager = TunnelManager.__new__(TunnelManager)
        url = manager._parse_tunnel_url(sample_status_html)
        # remoteDesktop tunnel port is 12211, should not be selected
        assert "12211" not in url

    def test_skip_http_tunnel(self, sample_status_html):
        """Should skip HTTP tunnels, only select TCP."""
        manager = TunnelManager.__new__(TunnelManager)
        url = manager._parse_tunnel_url(sample_status_html)
        # Should not select HTTP tunnel
        assert url.startswith("tcp://")
        assert "4cbb1683.r35.cpolar.top" not in url

    def test_fallback_to_non_ssh_tcp_tunnel(self, sample_status_html_only_remote_desktop):
        """Should fallback to any TCP tunnel if no SSH tunnel found."""
        manager = TunnelManager.__new__(TunnelManager)
        # When only remoteDesktop exists and skip_tunnels is empty
        url = manager._parse_tunnel_url(sample_status_html_only_remote_desktop, skip_tunnels=[])
        assert url == "tcp://35.tcp.cpolar.top:12211"

    def test_no_tunnel_found_raises_error(self):
        """Should raise TunnelError when no tunnel found."""
        manager = TunnelManager.__new__(TunnelManager)
        html = "<html><body><p>No tunnels here</p></body></html>"
        with pytest.raises(TunnelError):
            manager._parse_tunnel_url(html)

    def test_empty_table_raises_error(self):
        """Should raise TunnelError when table is empty."""
        manager = TunnelManager.__new__(TunnelManager)
        html = """
        <table class="table">
         <thead><tr><th>Name</th><th>URL</th></tr></thead>
         <tbody></tbody>
        </table>
        """
        with pytest.raises(TunnelError):
            manager._parse_tunnel_url(html)


class TestHostnamePortExtraction:
    """Test hostname and port extraction from tunnel URL."""

    def test_extract_hostname_and_port_standard(self):
        """Should extract hostname and port from standard URL."""
        manager = TunnelManager.__new__(TunnelManager)
        hostname, port = manager._extract_hostname_and_port("tcp://7.tcp.vip.cpolar.cn:12766")
        assert hostname == "7.tcp.vip.cpolar.cn"
        assert port == 12766

    def test_extract_hostname_and_port_different_domain(self):
        """Should handle different domain formats."""
        manager = TunnelManager.__new__(TunnelManager)
        hostname, port = manager._extract_hostname_and_port("tcp://35.tcp.cpolar.top:12211")
        assert hostname == "35.tcp.cpolar.top"
        assert port == 12211

    def test_extract_invalid_url_raises_error(self):
        """Should raise TunnelError for invalid URL format."""
        manager = TunnelManager.__new__(TunnelManager)
        with pytest.raises(TunnelError):
            manager._extract_hostname_and_port("invalid_url")

    def test_extract_url_missing_port_raises_error(self):
        """Should raise TunnelError when port is missing."""
        manager = TunnelManager.__new__(TunnelManager)
        with pytest.raises(TunnelError):
            manager._extract_hostname_and_port("tcp://example.com")

    def test_extract_url_invalid_port_raises_error(self):
        """Should raise TunnelError for non-numeric port."""
        manager = TunnelManager.__new__(TunnelManager)
        with pytest.raises(TunnelError):
            manager._extract_hostname_and_port("tcp://example.com:abc")


class TestTunnelInfo:
    """Test TunnelInfo data class."""

    def test_tunnel_info_creation(self):
        """Should create TunnelInfo with correct attributes."""
        info = TunnelInfo(
            url="tcp://example.com:1234",
            hostname="example.com",
            port=1234,
            name="ssh"
        )
        assert info.url == "tcp://example.com:1234"
        assert info.hostname == "example.com"
        assert info.port == 1234
        assert info.name == "ssh"
        assert info.active is True

    def test_tunnel_info_to_dict(self):
        """Should convert TunnelInfo to dictionary."""
        info = TunnelInfo(
            url="tcp://example.com:1234",
            hostname="example.com",
            port=1234,
            name="ssh"
        )
        data = info.to_dict()
        assert data["url"] == "tcp://example.com:1234"
        assert data["hostname"] == "example.com"
        assert data["port"] == 1234
        assert data["name"] == "ssh"
        assert data["active"] is True

    def test_tunnel_info_str(self):
        """Should have readable string representation."""
        info = TunnelInfo(
            url="tcp://example.com:1234",
            hostname="example.com",
            port=1234,
            name="ssh"
        )
        s = str(info)
        assert "ssh" in s
        assert "example.com" in s
        assert "1234" in s
