"""
Custom exceptions for Cpolar Connect
"""


class CpolarConnectError(Exception):
    """Base exception for all cpolar connect errors"""

    pass


class ConfigError(CpolarConnectError):
    """Configuration related errors"""

    pass


class AuthenticationError(CpolarConnectError):
    """Authentication and login errors"""

    pass


class TunnelError(CpolarConnectError):
    """Tunnel information retrieval errors"""

    pass


class SSHError(CpolarConnectError):
    """SSH connection and key management errors"""

    pass


class HostKeyChangedError(SSHError):
    """Server host key differs from the recorded one (possible MITM)"""

    pass


class NetworkError(CpolarConnectError):
    """Network connectivity errors"""

    pass
