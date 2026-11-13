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


class TunnelNotFoundError(TunnelError):
    """No active tunnel exists (cpolar likely not running on the server)"""

    pass


class TunnelNameNotFoundError(TunnelNotFoundError):
    """The configured tunnel name is not online, although other tunnels are
    (a wrong tunnel.name, or that machine's cpolar is down)"""

    pass


class SSHError(CpolarConnectError):
    """SSH connection and key management errors"""

    pass


class ServerUnreachableError(SSHError):
    """No SSH session came about: the server's name did not resolve, nothing
    answered, or the handshake failed. Nothing was learned about the server"""

    pass


class HostKeyChangedError(SSHError):
    """Server host key differs from the recorded one (possible MITM)"""

    pass


class KeyInstallError(SSHError):
    """The public key could not be installed automatically; the user can
    still install it by hand"""

    def __init__(self, message: str, public_key_path):
        super().__init__(message)
        # The key the user has to install by hand instead
        self.public_key_path = public_key_path


class PasswordLoginUnavailableError(KeyInstallError):
    """The server does not offer password logins at all, so no password
    can get the key installed"""

    pass


class NetworkError(CpolarConnectError):
    """Network connectivity errors"""

    pass
