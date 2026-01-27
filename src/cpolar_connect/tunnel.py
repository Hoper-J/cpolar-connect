"""
Tunnel management module for Cpolar Connect
"""

import re
import logging
from typing import Dict, List, Optional, Tuple, Any
from bs4 import BeautifulSoup
import requests
from rich.console import Console
from pathlib import Path
from datetime import datetime

from .exceptions import TunnelError, NetworkError
from .i18n import _

console = Console()
logger = logging.getLogger(__name__)


class TunnelInfo:
    """Data class for tunnel information"""
    
    def __init__(self, url: str, hostname: str, port: int, name: str = "ssh"):
        self.url = url  # Full URL like tcp://xxx:port
        self.hostname = hostname
        self.port = port
        self.name = name
        self.active = True
    
    def __str__(self):
        return f"Tunnel(name={self.name}, url={self.url}, host={self.hostname}, port={self.port})"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'url': self.url,
            'hostname': self.hostname,
            'port': self.port,
            'name': self.name,
            'active': self.active
        }


class TunnelManager:
    """Manage cpolar tunnel information"""
    
    def __init__(self, session: requests.Session, base_url: str = "https://dashboard.cpolar.com"):
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
    
    def get_tunnel_info(self) -> TunnelInfo:
        """
        Get tunnel information from cpolar status page
        
        Returns:
            TunnelInfo object containing tunnel details
        """
        try:
            console.print("[dim]Fetching tunnel information...[/dim]")
            
            # Get status page
            response = self.session.get(self.status_url, timeout=10)
            response.raise_for_status()
            
            # Check if we're still authenticated
            if '/login' in response.url:
                raise TunnelError(_('error.session_expired'))
            
            # Parse tunnel information
            tunnel_url = self._parse_tunnel_url(response.text)
            
            # Extract hostname and port
            hostname, port = self._extract_hostname_and_port(tunnel_url)
            
            # Create TunnelInfo object
            tunnel_info = TunnelInfo(
                url=tunnel_url,
                hostname=hostname,
                port=port,
                name="ssh"
            )
            
            console.print(f"[green]✅ Found tunnel: {tunnel_url}[/green]")
            logger.info(f"Tunnel info: {tunnel_info}")
            
            return tunnel_info
            
        except requests.RequestException as e:
            logger.error(f"Network error while fetching tunnel info: {e}")
            raise NetworkError(_('error.network', error=e))
        except TunnelError:
            raise
        except Exception as e:
            logger.error(f"Error getting tunnel info: {e}")
            raise TunnelError(_('error.tunnel', error=e))
    
    def _parse_tunnel_url(self, html_content: str, skip_tunnels: Optional[list] = None) -> str:
        """
        Parse tunnel URL from status page HTML

        Args:
            html_content: HTML content of status page
            skip_tunnels: List of tunnel names to skip (default: ['remoteDesktop'])

        Returns:
            Tunnel URL (e.g., "tcp://x.tcp.vip.cpolar.cn:12345")
        """
        if skip_tunnels is None:
            skip_tunnels = ['remoteDesktop']

        soup = BeautifulSoup(html_content, 'html.parser')
        tcp_pattern = re.compile(r'tcp://[a-zA-Z0-9\.\-]+:\d+')

        # Method 1: Parse table to find SSH tunnel (local port 22)
        # Table structure: 隧道名称(td) | URL(th) | 地区(td) | 本地地址(td) | 创建时间(td)
        # Note: URL column uses <th scope="row"> instead of <td>
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                # Get all cells (both td and th)
                all_cells = row.find_all(['td', 'th'])
                # Skip header row (all th)
                if len(all_cells) >= 5 and all_cells[0].name == 'td':
                    tunnel_name = all_cells[0].get_text(strip=True)
                    tunnel_url = all_cells[1].get_text(strip=True)
                    local_addr = all_cells[3].get_text(strip=True)

                    # Skip tunnels in the skip list
                    if tunnel_name in skip_tunnels:
                        logger.debug(f"Skipping tunnel: {tunnel_name}")
                        continue

                    # Prefer SSH tunnel (local port 22)
                    if tunnel_url.startswith('tcp://') and ':22' in local_addr:
                        logger.debug(f"Found SSH tunnel via table: {tunnel_url} (name={tunnel_name})")
                        return tunnel_url

        # Method 2: Fallback - find any TCP tunnel not in skip list
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                all_cells = row.find_all(['td', 'th'])
                if len(all_cells) >= 2 and all_cells[0].name == 'td':
                    tunnel_name = all_cells[0].get_text(strip=True)
                    tunnel_url = all_cells[1].get_text(strip=True)

                    if tunnel_name in skip_tunnels:
                        continue

                    if tunnel_url.startswith('tcp://') and tcp_pattern.match(tunnel_url):
                        logger.debug(f"Found TCP tunnel via table fallback: {tunnel_url}")
                        return tunnel_url

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
        raise TunnelError(_('tunnel.not_found'))
    
    def _extract_hostname_and_port(self, tunnel_url: str) -> Tuple[str, int]:
        """
        Extract hostname and port from tunnel URL
        
        Args:
            tunnel_url: Full tunnel URL (e.g., "tcp://x.tcp.vip.cpolar.cn:12345")
            
        Returns:
            Tuple of (hostname, port)
        """
        # Pattern for tcp://hostname:port
        pattern = r'^tcp://([a-zA-Z0-9\.\-]+):(\d+)$'
        match = re.match(pattern, tunnel_url)
        
        if not match:
            # Try without tcp:// prefix
            pattern = r'^([a-zA-Z0-9\.\-]+):(\d+)$'
            match = re.match(pattern, tunnel_url)
        
        if match:
            hostname = match.group(1)
            port = int(match.group(2))
            logger.debug(f"Extracted hostname={hostname}, port={port}")
            return hostname, port
        else:
            logger.error(f"Failed to parse tunnel URL: {tunnel_url}")
            raise TunnelError(_('error.tunnel_url_invalid', url=tunnel_url))
    
    def get_auth_token(self) -> Optional[str]:
        """
        Get authentication token from cpolar auth page
        
        Returns:
            Auth token string or None if not found
        """
        try:
            response = self.session.get(self.auth_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for authtoken input field
            authtoken_input = soup.find("input", {"id": "authtoken"})
            if authtoken_input:
                token = authtoken_input.get("value", "").strip()
                if token:
                    logger.debug("Successfully obtained auth token")
                    return token
            
            # Alternative: look for token in different places
            # Sometimes it might be in a code block or pre tag
            for element in soup.find_all(['code', 'pre']):
                text = element.text.strip()
                if text.startswith('authtoken:') or 'authtoken' in text:
                    # Extract token from text
                    token_match = re.search(r'authtoken:\s*([a-zA-Z0-9_\-]+)', text)
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
