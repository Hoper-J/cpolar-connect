"""
Tunnel management module for Cpolar Connect
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

from .exceptions import (
    NetworkError,
    TunnelError,
    TunnelNameNotFoundError,
    TunnelNotFoundError,
)
from .i18n import _

logger = logging.getLogger(__name__)


class TunnelInfo:
    """Data class for tunnel information"""

    def __init__(
        self,
        url: str,
        hostname: str,
        port: int,
        name: str = "ssh",
        other_candidates: Optional[List[str]] = None,
        is_ssh: bool = True,
    ):
        self.url = url  # Full URL like tcp://xxx:port
        self.hostname = hostname
        self.port = port
        self.name = name
        # Names of the other tunnels the selection could equally have picked:
        # same-named ones, or the rest of the tier when auto-picking
        self.other_candidates = other_candidates or []
        # Whether the tunnel leads to local port 22 on the server. False for
        # a pick from the other TCP tunnels, made when no such tunnel is online
        self.is_ssh = is_ssh

    def __str__(self):
        return f"Tunnel(name={self.name}, url={self.url}, host={self.hostname}, port={self.port})"

    def to_dict(self) -> Dict[str, Any]:
        """The tunnel as `status -f json` reports it"""
        return {
            "name": self.name,
            "url": self.url,
            "hostname": self.hostname,
            "port": self.port,
            "other_candidates": self.other_candidates,
        }


def selection_warnings(tunnel_info: TunnelInfo, account: str) -> List[str]:
    """Warnings to show when the choice of tunnel was ambiguous.

    Several machines can share one cpolar account. Tunnels with different
    names are told apart with tunnel.name; identically named ones are not.
    """
    others = tunnel_info.other_candidates
    duplicates = [name for name in others if name == tunnel_info.name]
    alternatives = [name for name in others if name != tunnel_info.name]

    warnings = []
    if duplicates:
        warnings.append(
            _(
                "warning.duplicate_tunnel_name",
                name=tunnel_info.name,
                count=len(duplicates) + 1,
                url=tunnel_info.url,
            )
        )
    if alternatives:
        warnings.append(
            _(
                (
                    "warning.multiple_ssh_tunnels"
                    if tunnel_info.is_ssh
                    else "warning.multiple_tcp_tunnels"
                ),
                chosen=tunnel_info.name,
                others=", ".join(alternatives),
                command=_("hint.set_tunnel_name_command", account=account),
            )
        )
    return warnings


class TunnelManager:
    """Manage cpolar tunnel information"""

    def __init__(
        self, session: requests.Session, base_url: str = "https://dashboard.cpolar.com"
    ):
        """
        Initialize tunnel manager with authenticated session

        Args:
            session: Authenticated requests.Session from CpolarAuth
            base_url: Base URL for cpolar dashboard
        """
        self.session = session
        self.base_url = base_url
        self.status_url = f"{base_url}/status"
        self.auth_url = f"{base_url}/auth"

    def get_tunnel_info(self, tunnel_name: Optional[str] = None) -> TunnelInfo:
        """
        Get tunnel information from cpolar status page

        Args:
            tunnel_name: Use the tunnel with this dashboard name (needed when
                several machines share one cpolar account); None picks the
                first tunnel forwarding to local port 22

        Returns:
            TunnelInfo object containing tunnel details
        """
        try:
            # Get status page
            response = self.session.get(self.status_url, timeout=10)
            response.raise_for_status()

            # Check if we're still authenticated
            if "/login" in response.url:
                raise TunnelError(_("error.session_expired"))

            # Parse tunnel information
            name, tunnel_url, others, is_ssh = self._find_tunnel(
                response.text, tunnel_name
            )

            # Extract hostname and port
            hostname, port = self._extract_hostname_and_port(tunnel_url)

            # Create TunnelInfo object
            tunnel_info = TunnelInfo(
                url=tunnel_url,
                hostname=hostname,
                port=port,
                name=name,
                other_candidates=others,
                is_ssh=is_ssh,
            )

            logger.info(f"Tunnel info: {tunnel_info}")
            if others:
                logger.warning(f"Other tunnels that qualified equally: {others}")

            return tunnel_info

        except requests.RequestException as e:
            logger.error(f"Network error while fetching tunnel info: {e}")
            raise NetworkError(_("error.network", error=e))
        except TunnelError:
            raise
        except Exception as e:
            logger.error(f"Error getting tunnel info: {e}")
            raise TunnelError(_("error.tunnel", error=e))

    def _find_tunnel(
        self,
        html_content: str,
        tunnel_name: Optional[str] = None,
        skip_tunnels: Optional[list] = None,
    ) -> Tuple[str, str, List[str], bool]:
        """
        Pick the tunnel to connect to from status page HTML

        Args:
            html_content: HTML content of status page
            tunnel_name: Use the tunnel with exactly this name; None picks
                among all tunnels. Either way a tunnel to the SSH port
                (local port 22) comes before any other TCP tunnel
            skip_tunnels: Tunnel names never auto-picked
                (default: ['remoteDesktop'])

        Returns:
            (name, URL, names of the other tunnels that qualified equally:
            same-named ones, or the rest of the auto-pick tier, whether the
            pick leads to the SSH port)

        Raises:
            TunnelNameNotFoundError: tunnel_name is not online, although
                other tunnels are
            TunnelNotFoundError: No usable tunnel on the page
        """
        if skip_tunnels is None:
            skip_tunnels = ["remoteDesktop"]

        tunnels = self._parse_tcp_tunnels(html_content)

        if tunnel_name:
            candidates = [t for t in tunnels if t[0] == tunnel_name]
        else:
            candidates = [t for t in tunnels if t[0] not in skip_tunnels]
        # Prefer SSH tunnels (local port 22) over other TCP tunnels
        ssh_tunnels = [t for t in candidates if t[2].endswith(":22")]
        matches = ssh_tunnels or candidates

        if matches:
            name, url, _local = matches[0]
            logger.debug(f"Selected tunnel {name!r}: {url}")
            return name, url, [t[0] for t in matches[1:]], bool(ssh_tunnels)

        if tunnel_name and tunnels:
            available = ", ".join(t[0] for t in tunnels)
            logger.error(f"Tunnel {tunnel_name!r} not found (online: {available})")
            raise TunnelNameNotFoundError(
                _("error.tunnel_name_not_found", name=tunnel_name, available=available)
            )

        # Save page content for debugging to logs directory
        try:
            log_dir = Path.home() / ".cpolar_connect" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            debug_path = log_dir / f"tunnel_status_debug_{ts}.html"
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(html_content)
        except Exception:
            # Best-effort; ignore file errors
            pass

        logger.error("Could not find tunnel URL in status page")
        raise TunnelNotFoundError(_("tunnel.not_found"))

    def _parse_tcp_tunnels(self, html_content: str) -> List[Tuple[str, str, str]]:
        """
        List every TCP tunnel on the status page, in page order

        Table structure: 隧道名称(td) | URL(th) | 地区(td) | 本地地址(td) | 创建时间(td)
        Note: URL column uses <th scope="row"> instead of <td>

        Returns:
            (name, URL, local address) tuples; local address is "" when the
            row has no such column
        """
        soup = BeautifulSoup(html_content, "html.parser")
        tcp_pattern = re.compile(r"tcp://[a-zA-Z0-9\.\-]+:\d+")

        tunnels = []
        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                # Get all cells (both td and th); header rows are all th
                cells = row.find_all(["td", "th"])
                if len(cells) < 2 or cells[0].name != "td":
                    continue
                url = cells[1].get_text(strip=True)
                if not tcp_pattern.match(url):
                    continue
                local_addr = cells[3].get_text(strip=True) if len(cells) >= 5 else ""
                tunnels.append((cells[0].get_text(strip=True), url, local_addr))
        return tunnels

    def _extract_hostname_and_port(self, tunnel_url: str) -> Tuple[str, int]:
        """
        Extract hostname and port from tunnel URL.

        Args:
            tunnel_url: Full tunnel URL (e.g., "tcp://x.tcp.vip.cpolar.cn:12345")

        Returns:
            Tuple of (hostname, port)
        """
        pattern = r"^tcp://([a-zA-Z0-9\.\-]+):(\d+)$"
        match = re.match(pattern, tunnel_url)

        if match:
            hostname = match.group(1)
            port = int(match.group(2))
            logger.debug(f"Extracted hostname={hostname}, port={port}")
            return hostname, port

        logger.error(f"Failed to parse tunnel URL: {tunnel_url}")
        raise TunnelError(_("error.tunnel_url_invalid", url=tunnel_url))

    def get_auth_token(self) -> Optional[str]:
        """
        Get authentication token from cpolar auth page

        Returns:
            Auth token string or None if not found
        """
        try:
            response = self.session.get(self.auth_url, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            # Look for authtoken input field
            authtoken_input = soup.find("input", {"id": "authtoken"})
            if authtoken_input:
                token = authtoken_input.get("value", "").strip()
                if token:
                    logger.debug("Successfully obtained auth token")
                    return token

            # Alternative: look for token in different places
            # Sometimes it might be in a code block or pre tag
            for element in soup.find_all(["code", "pre"]):
                text = element.text.strip()
                if text.startswith("authtoken:") or "authtoken" in text:
                    # Extract token from text
                    token_match = re.search(r"authtoken:\s*([a-zA-Z0-9_\-]+)", text)
                    if token_match:
                        token = token_match.group(1)
                        logger.debug("Found auth token in code block")
                        return token

            logger.warning("Auth token not found on auth page")
            return None

        except Exception as e:
            logger.error(f"Error getting auth token: {e}")
            return None

    def get_all_tunnels(self) -> Dict[str, TunnelInfo]:
        """
        Get all tunnel information (for future multi-tunnel support)

        Returns:
            Dictionary of tunnel name -> TunnelInfo
        """
        # For now, just return single SSH tunnel
        # Future implementation could parse multiple tunnels
        tunnel_info = self.get_tunnel_info()
        return {tunnel_info.name: tunnel_info}

    def verify_tunnel_active(self, tunnel_info: TunnelInfo) -> bool:
        """
        Verify that a tunnel is active

        Args:
            tunnel_info: TunnelInfo object to verify

        Returns:
            True if tunnel is active, False otherwise
        """
        try:
            # Re-fetch status page
            response = self.session.get(self.status_url, timeout=10)
            response.raise_for_status()

            # Check if tunnel URL is still present
            return tunnel_info.url in response.text

        except Exception as e:
            logger.error(f"Error verifying tunnel: {e}")
            return False
