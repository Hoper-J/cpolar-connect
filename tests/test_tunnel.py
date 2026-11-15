"""
Tests for tunnel.py - Tunnel URL parsing and extraction.
"""

import pytest

from cpolar_connect.exceptions import (
    TunnelError,
    TunnelNameNotFoundError,
    TunnelNotFoundError,
)
from cpolar_connect.tunnel import TunnelInfo, TunnelManager, selection_warnings


class TestTunnelUrlParsing:
    """Test tunnel URL parsing from HTML."""

    def test_parse_ssh_tunnel_from_table(self, sample_status_html):
        """Should extract SSH tunnel (local port 22) from table."""
        manager = TunnelManager.__new__(TunnelManager)
        url = manager._find_tunnel(sample_status_html)[1]
        # Should find the 'default' tunnel with local port 22
        assert url == "tcp://7.tcp.vip.cpolar.cn:12766"

    def test_skip_remote_desktop_tunnel(self, sample_status_html):
        """Should skip remoteDesktop tunnel by default."""
        manager = TunnelManager.__new__(TunnelManager)
        url = manager._find_tunnel(sample_status_html)[1]
        # remoteDesktop tunnel port is 12211, should not be selected
        assert "12211" not in url

    def test_skip_http_tunnel(self, sample_status_html):
        """Should skip HTTP tunnels, only select TCP."""
        manager = TunnelManager.__new__(TunnelManager)
        url = manager._find_tunnel(sample_status_html)[1]
        # Should not select HTTP tunnel
        assert url.startswith("tcp://")
        assert "4cbb1683.r35.cpolar.top" not in url

    def test_fallback_to_non_ssh_tcp_tunnel(
        self, sample_status_html_only_remote_desktop
    ):
        """Should fallback to any TCP tunnel if no SSH tunnel found."""
        manager = TunnelManager.__new__(TunnelManager)
        # When only remoteDesktop exists and skip_tunnels is empty
        url = manager._find_tunnel(
            sample_status_html_only_remote_desktop, skip_tunnels=[]
        )[1]
        assert url == "tcp://35.tcp.cpolar.top:12211"

    def test_local_port_2222_not_mistaken_for_ssh(self):
        """Local address port 2222 must not match the SSH (port 22) check."""
        html = """
<table class="table table-sm">
 <thead>
  <tr>
   <th scope="col">隧道名称</th>
   <th scope="col">URL</th>
   <th scope="col">地区</th>
   <th scope="col">本地地址</th>
   <th scope="col">创建时间</th>
  </tr>
 </thead>
 <tbody>
  <tr>
   <td>web</td>
   <th scope="row">
    <a href="#ZgotmplZ" target="_blank">tcp://1.tcp.cpolar.top:11111</a>
   </th>
   <td>cn_top</td>
   <td>tcp://127.0.0.1:2222</td>
   <td>2026-01-28 09:51:32 +0800 CST</td>
  </tr>
  <tr>
   <td>ssh</td>
   <th scope="row">
    <a href="#ZgotmplZ" target="_blank">tcp://2.tcp.cpolar.top:22222</a>
   </th>
   <td>cn_vip</td>
   <td>tcp://127.0.0.1:22</td>
   <td>2026-01-28 09:51:32 +0800 CST</td>
  </tr>
 </tbody>
</table>
"""
        manager = TunnelManager.__new__(TunnelManager)
        url = manager._find_tunnel(html)[1]
        assert url == "tcp://2.tcp.cpolar.top:22222"

    def test_no_tunnel_found_raises_error(self):
        """Should raise TunnelError when no tunnel found."""
        manager = TunnelManager.__new__(TunnelManager)
        html = "<html><body><p>No tunnels here</p></body></html>"
        with pytest.raises(TunnelError):
            manager._find_tunnel(html)

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
            manager._find_tunnel(html)


class TestHostnamePortExtraction:
    """Test hostname and port extraction from tunnel URL."""

    def test_extract_hostname_and_port_standard(self):
        """Should extract hostname and port from standard URL."""
        manager = TunnelManager.__new__(TunnelManager)
        hostname, port = manager._extract_hostname_and_port(
            "tcp://7.tcp.vip.cpolar.cn:12766"
        )
        assert hostname == "7.tcp.vip.cpolar.cn"
        assert port == 12766

    def test_extract_hostname_and_port_different_domain(self):
        """Should handle different domain formats."""
        manager = TunnelManager.__new__(TunnelManager)
        hostname, port = manager._extract_hostname_and_port(
            "tcp://35.tcp.cpolar.top:12211"
        )
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
            url="tcp://example.com:1234", hostname="example.com", port=1234, name="ssh"
        )
        assert info.url == "tcp://example.com:1234"
        assert info.hostname == "example.com"
        assert info.port == 1234
        assert info.name == "ssh"

    def test_tunnel_info_to_dict(self):
        """Should convert TunnelInfo to dictionary."""
        info = TunnelInfo(
            url="tcp://example.com:1234", hostname="example.com", port=1234, name="ssh"
        )
        data = info.to_dict()
        # What `status -f json` prints for the tunnel, in this order
        assert list(data.items()) == [
            ("name", "ssh"),
            ("url", "tcp://example.com:1234"),
            ("hostname", "example.com"),
            ("port", 1234),
            ("other_candidates", []),
        ]

    def test_tunnel_info_str(self):
        """Should have readable string representation."""
        info = TunnelInfo(
            url="tcp://example.com:1234", hostname="example.com", port=1234, name="ssh"
        )
        s = str(info)
        assert "ssh" in s
        assert "example.com" in s
        assert "1234" in s


class TestTunnelNotFound:
    def test_no_tunnel_raises_specific_error(self):
        """Absence of tunnels must be distinguishable from other tunnel errors."""
        manager = TunnelManager.__new__(TunnelManager)
        html = "<html><body><p>No tunnels here</p></body></html>"
        with pytest.raises(TunnelNotFoundError):
            manager._find_tunnel(html)


def _status_page(*rows):
    """A status table in the dashboard's layout, from (name, url, local) rows."""
    body = "".join(f"""
  <tr>
   <td>{name}</td>
   <th scope="row">
    <a href="#ZgotmplZ" target="_blank">{url}</a>
   </th>
   <td>cn_vip</td>
   <td>{local}</td>
   <td>2026-11-09 11:02:17 +0800 CST</td>
  </tr>""" for name, url, local in rows)
    return f"""
<table class="table table-sm">
 <thead>
  <tr>
   <th scope="col">隧道名称</th>
   <th scope="col">URL</th>
   <th scope="col">地区</th>
   <th scope="col">本地地址</th>
   <th scope="col">创建时间</th>
  </tr>
 </thead>
 <tbody>{body}
 </tbody>
</table>
"""


# One cpolar account, two machines: each exposes its own SSH tunnel
TWO_MACHINES_HTML = _status_page(
    ("default", "tcp://1.tcp.vip.cpolar.cn:10474", "tcp://127.0.0.1:22"),
    ("ssh", "tcp://1.tcp.vip.cpolar.cn:10252", "tcp://127.0.0.1:22"),
    ("remoteDesktop", "tcp://35.tcp.cpolar.top:12211", "tcp://127.0.0.1:3389"),
)


class TestTunnelSelection:
    """Several machines may share one cpolar account; pick by tunnel name."""

    def test_auto_pick_reports_other_ssh_tunnels(self):
        manager = TunnelManager.__new__(TunnelManager)
        assert manager._find_tunnel(TWO_MACHINES_HTML) == (
            "default",
            "tcp://1.tcp.vip.cpolar.cn:10474",
            ["ssh"],
            True,
        )

    def test_named_tunnel_is_used(self):
        manager = TunnelManager.__new__(TunnelManager)
        assert manager._find_tunnel(TWO_MACHINES_HTML, "ssh") == (
            "ssh",
            "tcp://1.tcp.vip.cpolar.cn:10252",
            [],
            True,
        )

    def test_single_ssh_tunnel_reports_no_others(self, sample_status_html):
        manager = TunnelManager.__new__(TunnelManager)
        assert manager._find_tunnel(sample_status_html)[2] == []

    def test_fallback_pick_reports_other_tcp_tunnels(self):
        """Without a port-22 tunnel the first TCP tunnel wins, but not silently."""
        html = _status_page(
            ("box-a", "tcp://1.tcp.cpolar.top:10001", "tcp://127.0.0.1:2222"),
            ("box-b", "tcp://1.tcp.cpolar.top:10002", "tcp://127.0.0.1:2222"),
        )
        manager = TunnelManager.__new__(TunnelManager)
        assert manager._find_tunnel(html) == (
            "box-a",
            "tcp://1.tcp.cpolar.top:10001",
            ["box-b"],
            False,  # ...and not as an SSH tunnel
        )

    def test_same_named_tunnels_are_reported_for_a_named_pick(self):
        """Two machines with the stock tunnel name: the name cannot choose."""
        html = _status_page(
            ("ssh", "tcp://1.tcp.cpolar.top:11111", "tcp://127.0.0.1:22"),
            ("ssh", "tcp://1.tcp.cpolar.top:22222", "tcp://127.0.0.1:22"),
        )
        manager = TunnelManager.__new__(TunnelManager)
        assert manager._find_tunnel(html, "ssh") == (
            "ssh",
            "tcp://1.tcp.cpolar.top:11111",
            ["ssh"],
            True,
        )

    def test_named_pick_prefers_the_tunnel_to_the_ssh_port(self):
        """Two tunnels share the name: the one to local port 22 is the one
        this tool can use, wherever it stands on the page."""
        html = _status_page(
            ("pc", "tcp://1.tcp.cpolar.top:11111", "tcp://127.0.0.1:3389"),
            ("pc", "tcp://1.tcp.cpolar.top:22222", "tcp://127.0.0.1:22"),
        )
        manager = TunnelManager.__new__(TunnelManager)
        assert manager._find_tunnel(html, "pc") == (
            "pc",
            "tcp://1.tcp.cpolar.top:22222",
            [],
            True,
        )

    def test_get_tunnel_info_uses_requested_name(self):
        class FakeResponse:
            url = "https://dashboard.cpolar.com/status"
            text = TWO_MACHINES_HTML

            def raise_for_status(self):
                pass

        class FakeSession:
            def get(self, url, timeout=None):
                return FakeResponse()

        info = TunnelManager(FakeSession()).get_tunnel_info("ssh")

        assert (info.name, info.hostname, info.port) == (
            "ssh",
            "1.tcp.vip.cpolar.cn",
            10252,
        )
        assert info.other_candidates == []


def _debug_dumps(home):
    return list((home / ".cpolar_connect").rglob("tunnel_status_debug_*.html"))


class TestTunnelNameNotFound:
    """A configured name that is not online is not the same as "no tunnels"."""

    def test_wrong_name_lists_online_tunnels_without_dumping_the_page(self, tmp_path):
        manager = TunnelManager.__new__(TunnelManager)
        with pytest.raises(
            TunnelNameNotFoundError, match="default, ssh, remoteDesktop"
        ):
            manager._find_tunnel(TWO_MACHINES_HTML, "winpc")
        assert _debug_dumps(tmp_path) == []  # the page parsed fine

    def test_matching_is_exact(self):
        manager = TunnelManager.__new__(TunnelManager)
        with pytest.raises(TunnelNameNotFoundError):
            manager._find_tunnel(TWO_MACHINES_HTML, "SSH")

    def test_still_handled_as_tunnel_not_found(self):
        """Callers that only know TunnelNotFoundError keep working."""
        assert issubclass(TunnelNameNotFoundError, TunnelNotFoundError)

    def test_named_lookup_on_page_without_tunnels_keeps_the_page(self, tmp_path):
        """Nothing parsed (cpolar down, or a layout change): generic error."""
        manager = TunnelManager.__new__(TunnelManager)
        html = "<html><body><p>No tunnels here</p></body></html>"
        with pytest.raises(TunnelNotFoundError) as excinfo:
            manager._find_tunnel(html, "ssh")
        assert not isinstance(excinfo.value, TunnelNameNotFoundError)
        assert len(_debug_dumps(tmp_path)) == 1


class TestSelectionWarnings:
    def _info(self, name, others, is_ssh=True):
        return TunnelInfo(
            url="tcp://1.tcp.cpolar.top:11111",
            hostname="1.tcp.cpolar.top",
            port=11111,
            name=name,
            other_candidates=others,
            is_ssh=is_ssh,
        )

    def test_unambiguous_pick_has_no_warnings(self):
        assert selection_warnings(self._info("ssh", []), "winpc") == []

    def test_other_tunnels_point_at_the_tunnel_name_setting(self):
        (warning,) = selection_warnings(self._info("default", ["ssh"]), "winpc")
        assert "'default'" in warning and "ssh" in warning
        assert "cpolar-connect -a winpc config set tunnel.name" in warning

    def test_tunnels_to_other_ports_are_not_called_ssh_tunnels(self):
        """No tunnel to local port 22 online: the first TCP tunnel is used."""
        (warning,) = selection_warnings(self._info("db", ["web"], False), "winpc")
        assert "SSH tunnels" not in warning
        assert "local port 22" in warning
        assert "'db'" in warning and "web" in warning
        assert "cpolar-connect -a winpc config set tunnel.name" in warning

    def test_same_named_tunnels_need_a_rename_not_tunnel_name(self):
        (warning,) = selection_warnings(self._info("ssh", ["ssh"]), "winpc")
        assert "2 tunnels are named 'ssh'" in warning
        assert "tcp://1.tcp.cpolar.top:11111" in warning
        assert "config set tunnel.name" not in warning

    def test_both_kinds_are_reported(self):
        warnings = selection_warnings(self._info("ssh", ["ssh", "default"]), "winpc")
        assert len(warnings) == 2
