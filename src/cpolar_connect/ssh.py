"""
SSH management module for Cpolar Connect
"""

import base64
import binascii
import functools
import io
import logging
import os
import platform
import re
import shlex
import socket
import stat
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

import paramiko
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from paramiko.hostkeys import HostKeyEntry

from .config import ACCOUNTS_DIR_NAME, CpolarConfig, resolve_account
from .exceptions import (
    HostKeyChangedError,
    PasswordLoginUnavailableError,
    ServerUnreachableError,
    SSHError,
    WindowsServerKeyError,
)
from .i18n import _
from .tunnel import TunnelInfo

logger = logging.getLogger(__name__)

# What OpenSSH's config tokenizer treats specially: whitespace and "=" end an
# argument, quotes group, "#" can start a comment, and a backslash escapes a
# following quote or backslash
_CONFIG_SPECIAL = re.compile(r'[\s"\'#=]|\\(?=[\\"\'])')


def _config_token(value: str) -> str:
    """Render a value as one ssh_config argument (also valid for `ssh -o`).

    A value with none of the tokenizer's special characters is written as it
    is, byte for byte what earlier versions wrote; that covers ordinary
    paths on every platform, including Windows paths (a lone backslash is
    literal to OpenSSH) and non-ASCII names. Only a value that used to break
    the config is double-quoted, with quotes and the backslashes that would
    act as escapes escaped.
    """
    if value and not _CONFIG_SPECIAL.search(value):
        return value
    escaped = re.sub(r'\\(?=[\\"\']|$)|"', lambda m: "\\" + m.group(0), value)
    return f'"{escaped}"'


def _config_path(path: Path) -> str:
    """Render a path for IdentityFile/UserKnownHostsFile.

    Both directives expand %-tokens, so a literal percent sign is doubled.
    """
    return _config_token(str(path).replace("%", "%%"))


# How ~/.ssh/config is read and written back. It is the user's file and need
# not be UTF-8 (a comment saved by an older Windows editor is GBK or the
# like): such bytes pass through unchanged instead of stopping the run
_USER_FILE = {"encoding": "utf-8", "errors": "surrogateescape"}

# How long a remote command may stay silent. Each of them finishes at once,
# so a longer silence means that the connection has died without a word
_REMOTE_COMMAND_TIMEOUT = 60


def _reason(error: Exception) -> str:
    """What an exception says, for use inside a message; some say nothing."""
    text = str(error).strip()
    if text:
        return text
    if isinstance(error, EOFError):
        return _("error.reason_connection_closed")
    return type(error).__name__


def _reports_config_file_errors(method):
    """Turn an OSError about ~/.ssh/config into an SSHError that names the file.

    It is the user's file and may be anything: read-only, a directory,
    someone else's. That has to end as a message, not as a traceback.
    """

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except OSError as e:
            logger.error(f"Cannot read or update {self.ssh_config_path}: {e}")
            raise SSHError(
                _(
                    "error.ssh_config_unusable",
                    path=self.ssh_config_path,
                    # The system's wording alone: str(e) repeats the path
                    error=e.strerror or _reason(e),
                )
            )

    return wrapper


# Key types accepted for ssh_key_path; generated keys are always RSA
_KEY_CLASSES = (paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey)


def _load_pkcs8_key(path: Path) -> Optional[paramiko.PKey]:
    """Load a private key in PKCS#8 PEM form ("BEGIN PRIVATE KEY").

    openssl writes keys in this form. `ssh` takes an RSA or ECDSA key in it
    as IdentityFile, but paramiko cannot read it: the key is handed to
    paramiko in the OpenSSH form instead. An Ed25519 key in this form is
    refused, because most builds of ssh cannot read it either (it takes a
    recent OpenSSH built against a libcrypto that knows Ed25519).

    Returns:
        The key, or None if the file holds no such key of a supported type

    Raises:
        SSHError: The key is passphrase-protected, or an Ed25519 key
    """
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"-----BEGIN ENCRYPTED PRIVATE KEY-----" in data:
        raise SSHError(_("error.ssh_key_passphrase", path=path))
    if b"-----BEGIN PRIVATE KEY-----" not in data:
        return None
    try:
        key = serialization.load_pem_private_key(data, password=None)
        if isinstance(key, ed25519.Ed25519PrivateKey):
            raise SSHError(_("error.ssh_key_pkcs8_ed25519", path=path))
        openssh_form = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.OpenSSH,
            serialization.NoEncryption(),
        ).decode("ascii")
    except (ValueError, TypeError, UnsupportedAlgorithm) as e:
        logger.debug(f"{path} is not a usable PKCS#8 key: {e}")
        return None
    for key_class in _KEY_CLASSES:
        try:
            return key_class.from_private_key(io.StringIO(openssh_form))
        except Exception as e:
            # As in load_private_key: a key of another type
            logger.debug(f"{path} (PKCS#8) is not a {key_class.__name__}: {e}")
    return None


def load_private_key(path: Path) -> paramiko.PKey:
    """Load an unencrypted RSA, Ed25519 or ECDSA private key.

    Raises:
        FileNotFoundError: No key at this path
        SSHError: The file is unreadable, passphrase-protected, or not a
            supported private key
    """
    for key_class in _KEY_CLASSES:
        try:
            return key_class.from_private_key_file(str(path))
        except FileNotFoundError:
            raise
        except paramiko.PasswordRequiredException:
            raise SSHError(_("error.ssh_key_passphrase", path=path))
        except OSError as e:
            raise SSHError(_("error.ssh_key_load_failed", path=path, error=e))
        except Exception as e:
            # A key of another type (or a file that is no key at all) shows
            # up as SSHException, ValueError, UnicodeDecodeError...; that is
            # only an error once every supported type has been tried
            logger.debug(f"{path} is not a {key_class.__name__}: {e}")
    key = _load_pkcs8_key(path)
    if key is None:
        raise SSHError(_("error.ssh_key_unsupported", path=path))
    return key


def _public_key_line(key: paramiko.PKey) -> str:
    """The authorized_keys line for a key."""
    return f"{key.get_name()} {key.get_base64()} cpolar-connect"


# How every key type name starts; no authorized_keys option starts like this
_KEY_TYPE_PREFIX = re.compile(r"(ssh-|ecdsa-|sk-)")


def _authorized_key(line: str) -> Tuple[str, str]:
    """Key type and key data of one authorized_keys line, as sshd reads it.

    The key stands at the start of the line, or after one field of options
    in which blanks inside double quotes do not separate. Only space and tab
    are blanks. Whatever follows the key data is comment, even another key.
    The line is a C string to sshd: it ends at the first NUL byte, as found
    in a file that was saved as UTF-16.
    """
    line = line.split("\x00", 1)[0].strip(" \t\r")
    if not line or line.startswith("#"):
        return "", ""
    if not _KEY_TYPE_PREFIX.match(line):
        quoted = False
        end = 0
        while end < len(line) and (quoted or line[end] not in " \t"):
            if line[end] == "\\" and line[end + 1 : end + 2] == '"':
                end += 1  # an escaped quote does not open or close anything
            elif line[end] == '"':
                quoted = not quoted
            end += 1
        if quoted:
            return "", ""  # sshd gives up on a line with an unclosed quote
        line = line[end:].lstrip(" \t")
    fields = re.split(r"[ \t]+", line)
    return (fields[0], fields[1]) if len(fields) >= 2 else ("", "")


def _is_authorized(public_key_line: str, authorized_keys: str) -> bool:
    """Whether authorized_keys text has an entry for this public key.

    Only what sshd itself would accept counts. A key that was glued onto
    the end of another line is part of that line's comment to sshd, with or
    without a blank in between; if it counted as installed, the upload
    would be skipped and the entry never repaired.
    """
    key_type, key_data = public_key_line.split()[:2]
    return any(
        _authorized_key(line) == (key_type, key_data)
        for line in authorized_keys.split("\n")
    )


def _make_ssh_dir(path: Path) -> None:
    """Create a directory for SSH files that only the user can access.

    On Windows a new directory inherits just that from the user profile.
    Asking for mode 0o700 there makes things worse: Python (3.12.4 and
    later) then grants access through an "OWNER RIGHTS" entry, which is
    handed down to every file created in the directory and which ssh.exe
    counts as somebody else, so it refuses the private keys and the config
    file in it.
    """
    if platform.system() == "Windows":
        path.mkdir(parents=True, exist_ok=True)
    else:
        path.mkdir(parents=True, mode=0o700, exist_ok=True)


def _restrict_to_user(*paths: Path) -> None:
    """Leave files that ssh checks the access rights of to the user alone.

    POSIX: mode 600. Windows: an access list of the user, SYSTEM and the
    administrators, with nothing inherited from the directory. That is what
    ssh.exe accepts for a private key and for ~/.ssh/config, and what
    ssh-keygen gives the keys it writes.

    The "OWNER RIGHTS" entry is removed by name as well: a file created in
    a directory that Python made with mode 0o700 carries it as an entry of
    its own, which dropping the inherited entries does not touch.
    """
    if platform.system() != "Windows":
        for path in paths:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        return

    whoami = subprocess.run(
        ["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, check=True
    )
    # "machine\name","S-1-5-21-..."; only the SID is needed, and it is ASCII
    sid = whoami.stdout.decode("ascii", errors="replace").strip()
    sid = sid.rsplit(",", 1)[-1].strip('"')
    if not re.fullmatch(r"S-1-[0-9-]+", sid):
        raise ValueError(f"cannot tell the current user's SID from whoami: {sid!r}")
    for path in paths:
        subprocess.run(
            [
                "icacls",
                str(path),
                "/inheritance:r",
                "/grant:r",
                f"*{sid}:F",
                "*S-1-5-18:F",  # SYSTEM
                "*S-1-5-32-544:F",  # administrators
                "/remove",
                "*S-1-3-4",  # OWNER RIGHTS
            ],
            capture_output=True,
            check=True,
        )


def _is_windows_server(ssh: paramiko.SSHClient) -> bool:
    """Whether the server introduced itself as OpenSSH for Windows."""
    transport = ssh.get_transport()
    return transport is not None and "windows" in transport.remote_version.lower()


# Installs one public key on a Windows server and reports the outcome on a
# single line. Windows keeps the keys of administrator accounts in one file
# under ProgramData for as long as sshd_config says so (the default); every
# other account has its own file in the user profile. The key lands on a line
# of its own and is not added twice, as on a POSIX server; an existing entry
# is recognized by the rule of _authorized_key. The file is taken byte for
# byte, the way sshd reads it, whatever its encoding: PowerShell 5.1 writes
# UTF-16 with `>`, and in such a file sshd finds no entry, nor a key that is
# appended straight after its last line break. The shared file
# gets the access rights sshd insists on (administrators and SYSTEM only,
# named by their well-known SIDs so that it works in every display language).
_WINDOWS_INSTALL_SCRIPT = "\n".join(line.strip() for line in r"""
    $ErrorActionPreference = 'Stop'
    function Report($status, $detail) {
        $bytes = [Text.Encoding]::UTF8.GetBytes([string]$detail)
        Write-Output ('cpolar-connect: ' + $status + ' ' + [Convert]::ToBase64String($bytes))
    }
    try {
        $key = '__PUBLIC_KEY__'
        $file = Join-Path $env:USERPROFILE '.ssh\authorized_keys'
        $shared = Join-Path $env:ProgramData 'ssh\administrators_authorized_keys'
        $config = Join-Path $env:ProgramData 'ssh\sshd_config'
        $isAdmin = (whoami.exe /groups | Out-String) -match 'S-1-5-32-544\b'
        if ($isAdmin -and (Test-Path $config)) {
            $pattern = '^\s*AuthorizedKeysFile\s.*administrators_authorized_keys'
            if (Select-String -Path $config -Pattern $pattern -Quiet) { $file = $shared }
        }
        $folder = Split-Path $file
        if (-not (Test-Path $folder)) { New-Item -ItemType Directory -Path $folder | Out-Null }
        $bytes = New-Object byte[] 0
        if (Test-Path $file) { $bytes = [IO.File]::ReadAllBytes($file) }
        $text = [Text.Encoding]::GetEncoding(28591).GetString($bytes)
        $wanted = $key -split '[ \t]+'
        foreach ($line in ($text -split "`n")) {
            $entry = $line.Split([char]0)[0].Trim(" `t`r")
            if ($entry.StartsWith('#')) { continue }
            if ($entry -notmatch '^(ssh-|ecdsa-|sk-)') {
                $entry = $entry -replace '^(\\"|"(\\"|[^"])*"|[^ \t"])+[ \t]+', ''
            }
            $fields = @($entry -split '[ \t]+')
            if ($fields.Count -ge 2 -and $fields[0] -ceq $wanted[0] -and $fields[1] -ceq $wanted[1]) {
                Report 'present' $file
                exit 0
            }
        }
        $lineBreak = ''
        if ($bytes.Length -gt 0 -and $bytes[$bytes.Length - 1] -ne 10) { $lineBreak = "`r`n" }
        $utf8 = New-Object Text.UTF8Encoding $false
        [IO.File]::AppendAllText($file, $lineBreak + $key + "`r`n", $utf8)
        if ($file -eq $shared) {
            icacls.exe $file /inheritance:r /grant '*S-1-5-32-544:F' /grant '*S-1-5-18:F' | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "icacls.exe failed with exit code $LASTEXITCODE" }
        }
        Report 'installed' $file
    } catch {
        Report 'failed' $_.Exception.Message
        exit 1
    }
    """.strip().splitlines())

_WINDOWS_REPORT = re.compile(
    r"^cpolar-connect: (installed|present|failed) ([A-Za-z0-9+/=]*)\s*$", re.M
)

# cmd.exe, the default shell of OpenSSH for Windows, takes at most 8191
# characters; the rest is headroom for how sshd wraps the command
_WINDOWS_MAX_COMMAND = 8000


def _powershell_literal(text: str) -> str:
    """Escape text for a PowerShell single-quoted string.

    PowerShell reads the typographic single quotes as string delimiters
    too; like the plain one, each is escaped by doubling it.
    """
    return re.sub("['\u2018\u2019\u201a\u201b]", lambda m: m.group(0) * 2, text)


def _powershell_command(script: str) -> str:
    """A command line that runs a PowerShell script from any shell.

    The script travels base64-encoded, so that the server's default shell
    (cmd, PowerShell or a POSIX shell) finds nothing in it to interpret.
    """
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return f"powershell.exe -NoProfile -NonInteractive -EncodedCommand {encoded}"


class AliasHostKeyPolicy(paramiko.MissingHostKeyPolicy):
    """TOFU host key policy keyed by a stable alias.

    The tunnel hostname/port change on every cpolar restart, so host keys
    are recorded and verified under the configured ssh_host_alias instead
    of the (ever-changing) real hostname. The same file is used by the ssh
    CLI via HostKeyAlias + UserKnownHostsFile.

    Once a key is on record, only a key on record is accepted. A key of
    another type is no exception: whoever sits on the tunnel's path could
    otherwise get in by presenting just that. A server with a key per type
    still passes, because it is asked for a type that is on record
    (`transport`); `ssh` works the same way.
    """

    def __init__(self, alias: str, known_hosts_path: Path):
        self.alias = alias
        self.known_hosts_path = known_hosts_path
        # True once a server key was accepted, i.e. the SSH handshake is done
        self.accepted = False
        self._known: Optional[paramiko.HostKeys] = None

    @staticmethod
    def _algorithms(key_type: str) -> List[str]:
        """The names under which a server can present a host key of this type."""
        if key_type == "ssh-rsa":
            return ["rsa-sha2-512", "rsa-sha2-256", "ssh-rsa"]
        return [key_type]

    def recorded_keys(self) -> List[paramiko.PKey]:
        """The keys on record for the alias; none before the first connection.

        Raises:
            SSHError: The host key file is unusable
        """
        known = self._load()
        try:
            entry = known.lookup(self.alias)
        except Exception as e:
            # Comparing with a hashed name fails if that record is damaged
            raise self._unusable(e)
        return list(entry.values()) if entry is not None else []

    def transport(self, sock, **kwargs) -> paramiko.Transport:
        """Create the transport, asking first for the key types on record.

        Passed to SSHClient.connect as transport_factory. Left to its
        defaults, the handshake could settle on a key of a type that is not
        on record although the server has the recorded one as well.
        """
        transport = paramiko.Transport(sock, **kwargs)
        options = transport.get_security_options()
        on_record = [
            algorithm
            for key in self.recorded_keys()
            for algorithm in self._algorithms(key.get_name())
            if algorithm in options.key_types
        ]
        options.key_types = list(dict.fromkeys(on_record)) + [
            algorithm for algorithm in options.key_types if algorithm not in on_record
        ]
        return transport

    def missing_host_key(self, client, hostname, key) -> None:
        recorded = self.recorded_keys()

        if not recorded:
            # Trust on first use: record under the alias
            known = self._load()
            known.add(self.alias, key.get_name(), key)
            self._save(known)
            logger.info(f"Recorded host key for {self.alias} ({key.get_name()})")
        elif any(known_key.asbytes() == key.asbytes() for known_key in recorded):
            logger.debug(f"Host key for {self.alias} verified")
        else:
            logger.error(f"Host key mismatch for {self.alias} ({key.get_name()})")
            raise HostKeyChangedError(_("error.host_key_changed"))

        self.accepted = True

    def _unusable(self, error: Exception) -> SSHError:
        logger.error(f"Cannot use host key file {self.known_hosts_path}: {error}")
        return SSHError(
            _("error.known_hosts_unusable", path=self.known_hosts_path, error=error)
        )

    def _load(self) -> paramiko.HostKeys:
        if self._known is not None:
            return self._known
        known = paramiko.HostKeys()
        path = self.known_hosts_path
        try:
            if path.exists():
                # paramiko passes over a record it cannot parse. If that were
                # the alias's record, the server would be trusted anew as on
                # a first connection, so every record has to be sound
                lines = path.read_text(encoding="utf-8").splitlines()
                for number, line in enumerate(lines, 1):
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if HostKeyEntry.from_line(line, number) is None:
                        raise ValueError(f"line {number} is not a host key record")
                known.load(str(path))
        except Exception as e:
            # paramiko raises assorted types for an unreadable or corrupt
            # file. Stopping is deliberate, for the same reason
            raise self._unusable(e)
        self._known = known
        return known

    def _save(self, known: paramiko.HostKeys) -> None:
        try:
            self.known_hosts_path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            self.known_hosts_path.parent.chmod(0o700)
            known.save(str(self.known_hosts_path))
            self.known_hosts_path.chmod(0o600)
        except OSError as e:
            logger.error(f"Cannot write host key file {self.known_hosts_path}: {e}")
            raise SSHError(
                _("error.known_hosts_unusable", path=self.known_hosts_path, error=e)
            )


def _ssh_offers_agent_keys(user: str, hostname: str, port: int) -> bool:
    """Whether `ssh` would offer ssh-agent keys on a connection to this host.

    It does unless the user's own ssh configuration says IdentitiesOnly or
    turns the agent off, typically for all hosts. `ssh -G` evaluates that
    configuration without connecting. When it cannot be asked, the answer
    is the default of `ssh`: yes.
    """
    try:
        result = subprocess.run(
            ["ssh", "-G", "-p", str(port), f"{user}@{hostname}"],
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as e:
        logger.debug(f"Could not ask ssh for its configuration: {e}")
        return True
    if result.returncode != 0:
        return True
    options = {}
    for line in result.stdout.decode("utf-8", errors="replace").splitlines():
        name, _separator, value = line.partition(" ")
        options[name.lower()] = value.strip().lower()
    return (
        options.get("identitiesonly") != "yes"
        and options.get("identityagent") != "none"
    )


class SSHManager:
    """Manage SSH keys and connections"""

    def __init__(self, config: CpolarConfig, known_hosts_path: Optional[Path] = None):
        """
        Initialize SSH manager with configuration

        Args:
            config: CpolarConfig object
            known_hosts_path: Host key store (defaults to the resolved
                account's known_hosts under ~/.cpolar_connect/accounts/)
        """
        self.config = config
        self.private_key_path = Path(os.path.expanduser(config.ssh_key_path))
        self.public_key_path = Path(str(self.private_key_path) + ".pub")
        self.ssh_dir = self.private_key_path.parent
        self.ssh_config_path = Path.home() / ".ssh" / "config"
        if known_hosts_path is not None:
            self.known_hosts_path = known_hosts_path
        else:
            self.known_hosts_path = (
                Path.home()
                / ".cpolar_connect"
                / ACCOUNTS_DIR_NAME
                / resolve_account(None)
                / "known_hosts"
            )
        self.host_alias = config.ssh_host_alias
        self.server_user = config.server_user
        self.key_size = config.ssh_key_size

    def _host_key_policy(self) -> AliasHostKeyPolicy:
        return AliasHostKeyPolicy(self.host_alias, self.known_hosts_path)

    def ensure_ssh_directory(self) -> None:
        """Ensure .ssh directory exists with correct permissions"""
        if not self.ssh_dir.exists():
            try:
                _make_ssh_dir(self.ssh_dir)
                logger.info(f"Created SSH directory: {self.ssh_dir}")
            except Exception as e:
                logger.error(f"Failed to create SSH directory: {e}")
                raise SSHError(_("error.ssh_dir_failed", error=e))

    def generate_ssh_key(self, force: bool = False) -> bool:
        """
        Generate SSH key pair if not exists

        Args:
            force: Force regeneration even if key exists

        Returns:
            True if key was generated, False if already exists
        """
        self.ensure_ssh_directory()

        # Check if private key exists
        if self.private_key_path.exists() and not force:
            logger.info(f"SSH key already exists: {self.private_key_path}")

            # Ensure public key exists
            if not self.public_key_path.exists():
                self._regenerate_public_key()

            return False

        # Generate new key pair
        try:
            key = paramiko.RSAKey.generate(self.key_size)

            # Save private key
            key.write_private_key_file(str(self.private_key_path))

            # ssh ignores a private key that others can access
            try:
                _restrict_to_user(self.private_key_path)
            except Exception as e:
                logger.warning(f"Failed to set private key permissions: {e}")

            # Save public key
            with open(self.public_key_path, "w", encoding="utf-8") as f:
                f.write(_public_key_line(key) + "\n")

            logger.info(f"Generated new SSH key pair at {self.private_key_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to generate SSH key: {e}")
            raise SSHError(_("error.ssh_key_gen_failed", error=e))

    def _regenerate_public_key(self) -> None:
        """Regenerate public key from existing private key"""
        try:
            key = load_private_key(self.private_key_path)

            with open(self.public_key_path, "w", encoding="utf-8") as f:
                f.write(_public_key_line(key) + "\n")

            logger.info(f"Regenerated public key: {self.public_key_path}")

        except Exception as e:
            logger.error(f"Failed to regenerate public key: {e}")
            raise SSHError(_("error.ssh_pubkey_regen_failed", error=e))

    def _open_client(
        self, hostname: str, port: int, timeout: int, **credentials
    ) -> Optional[paramiko.SSHClient]:
        """Connect and authenticate with the given paramiko credentials.

        Failures are classified by phase rather than by exception type: once
        the host key policy has accepted the server, the SSH handshake is
        complete, so what goes wrong afterwards concerns the credentials,
        unless the connection itself broke.

        Returns:
            The connected client, or None when the server was reached but
            did not accept the credentials

        Raises:
            HostKeyChangedError: The server host key changed
            PasswordLoginUnavailableError: A password was given, but the
                server does not offer password logins
            ServerUnreachableError: No SSH session came about: the server's
                name does not resolve, nothing answers, or the handshake
                failed. Nothing was learned about the server
            SSHError: The connection was lost while authenticating, or the
                local host key file is unusable
        """
        policy = self._host_key_policy()
        policy.recorded_keys()  # an unusable host key file stops the run here
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(policy)
        try:
            ssh.connect(
                hostname=hostname,
                port=port,
                username=self.server_user,
                timeout=timeout,
                transport_factory=policy.transport,
                **credentials,
            )
            return ssh
        except SSHError:
            # Raised by the host key policy; includes HostKeyChangedError
            ssh.close()
            raise
        except Exception as e:
            # paramiko and its crypto backend raise many unrelated types
            # here; each one must end as a clear message, not a traceback
            ssh.close()
            if (
                isinstance(e, paramiko.BadAuthenticationType)
                and credentials.get("password") is not None
                and not {"password", "keyboard-interactive"} & set(e.allowed_types)
            ):
                # Not a wrong password: the server takes none at all
                logger.error(f"Password login not offered by the server: {e}")
                raise PasswordLoginUnavailableError(
                    _(
                        "error.ssh_password_login_unavailable",
                        methods=", ".join(e.allowed_types),
                    ),
                    self.public_key_path,
                )
            if isinstance(e, paramiko.AuthenticationException):
                logger.warning(f"SSH authentication failed: {e}")
                return None
            if policy.accepted and isinstance(e, OSError):
                # A reset or a timeout says nothing about the credentials
                logger.error(f"Connection lost while authenticating: {e}")
                raise SSHError(
                    _(
                        "error.ssh_connection_lost",
                        hostname=hostname,
                        port=port,
                        error=_reason(e),
                    )
                )
            if policy.accepted:
                logger.warning(f"SSH authentication failed: {e}")
                return None
            logger.error(f"SSH connection to {hostname}:{port} failed: {e}")
            if isinstance(e, socket.gaierror):
                # The name does not resolve here. That is this network's DNS
                # (some do not resolve tunnel host names), not the server
                raise ServerUnreachableError(
                    _("error.ssh_host_unresolved", hostname=hostname, error=_reason(e))
                )
            message = (
                "error.ssh_unreachable"
                if isinstance(e, (OSError, EOFError))
                else "error.ssh_handshake_failed"
            )
            raise ServerUnreachableError(
                _(message, hostname=hostname, port=port, error=_reason(e))
            )

    def test_ssh_connection(self, hostname: str, port: int, timeout: int = 10) -> bool:
        """
        Test key authentication the way the generated ssh config performs it

        Offers the configured key, then any ssh-agent keys: the Host block
        sets IdentityFile without IdentitiesOnly, so `ssh` uses both, unless
        the user's own ssh configuration keeps the agent out of it (see
        _ssh_offers_agent_keys). Default key files (~/.ssh/id_*) are left
        out, because an explicit IdentityFile makes `ssh` skip them too.

        Args:
            hostname: Remote hostname
            port: SSH port
            timeout: Connection timeout in seconds

        Returns:
            True if the server accepts one of those keys; False if the
            configured key does not exist yet or no key is accepted (i.e.
            bootstrap is needed)

        Raises:
            HostKeyChangedError: The server host key changed
            ServerUnreachableError: The server cannot be reached
            SSHError: The key cannot be loaded (like an unreachable server,
                not fixed by uploading a key, so never bootstrap)
        """
        try:
            key = load_private_key(self.private_key_path)
        except FileNotFoundError:
            key = None
        else:
            self._require_key_file_ssh_accepts()

        if key is None:
            # Nothing to offer yet: still make sure the server is there, so a
            # network problem is not mistaken for a first connection
            client = self._open_client(
                hostname, port, timeout, allow_agent=False, look_for_keys=False
            )
        else:
            client = self._open_client(
                hostname,
                port,
                timeout,
                pkey=key,
                allow_agent=_ssh_offers_agent_keys(self.server_user, hostname, port),
                look_for_keys=False,
            )

        if client is None:
            return False
        client.close()
        logger.info("SSH key authentication successful")
        return True

    def _require_key_file_ssh_accepts(self) -> None:
        """Stop if `ssh` would refuse the key file for who can read it.

        ssh ignores a private key of the user's own that group or others can
        access. paramiko does not look, so the check would pass with a key
        that `ssh` then does not use. A key owned by someone else (shared
        through a group) is not judged, by ssh or here. On Windows the
        access rights are put right instead: _keep_acceptable_to_windows_ssh.

        Raises:
            SSHError: The key file is too widely accessible
        """
        if platform.system() == "Windows":
            return
        try:
            info = self.private_key_path.stat()
        except OSError:
            return
        mode = stat.S_IMODE(info.st_mode)
        if info.st_uid == os.getuid() and mode & 0o077:
            raise SSHError(
                _(
                    "error.ssh_key_too_open",
                    path=self.private_key_path,
                    mode=f"{mode:03o}",
                    command=f"chmod 600 {shlex.quote(str(self.private_key_path))}",
                )
            )

    def _public_key_to_install(self) -> str:
        """The line of the .pub file, checked against the private key.

        What is installed must be the public half of the key this account
        connects with. A .pub left over from another key would authorize
        that key instead (and `ssh` refuses a pair that does not match).

        Raises:
            SSHError: The .pub file is missing, unreadable, not a public
                key, or belongs to another private key
        """
        path = self.public_key_path
        if not path.exists():
            raise SSHError(_("error.ssh_pubkey_not_found", path=path))
        try:
            # utf-8-sig: Windows tools like to put a byte order mark first
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        except (OSError, UnicodeDecodeError) as e:
            logger.error(f"Cannot read public key file {path}: {e}")
            raise SSHError(_("error.ssh_pubkey_invalid", path=path))
        line = next((line.strip() for line in lines if line.strip()), "")
        fields = line.split()
        if len(fields) < 2 or not _KEY_TYPE_PREFIX.match(fields[0]):
            raise SSHError(_("error.ssh_pubkey_invalid", path=path))

        try:
            key = load_private_key(self.private_key_path)
        except FileNotFoundError as e:
            raise SSHError(
                _("error.ssh_key_load_failed", path=self.private_key_path, error=e)
            )
        if (fields[0], fields[1]) != (key.get_name(), key.get_base64()):
            raise SSHError(
                _("error.ssh_pubkey_mismatch", path=path, key=self.private_key_path)
            )
        return line

    def _exec(self, ssh: paramiko.SSHClient, command: str) -> Tuple[int, str, str]:
        """Run a remote command: (exit status, output, error output).

        Raises:
            SSHError: The server stopped answering (a tunnel can die without
                a word; unlimited, the wait for it would never end)
        """
        timeout = _REMOTE_COMMAND_TIMEOUT
        try:
            stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout)
            output = stdout.read()
            error_output = stderr.read()
            if not stdout.channel.status_event.wait(timeout):
                raise socket.timeout()
        except socket.timeout:
            logger.error(f"No reply from the server within {timeout} seconds")
            raise SSHError(_("error.ssh_remote_timeout", seconds=timeout))
        return (
            stdout.channel.recv_exit_status(),
            output.decode("utf-8", errors="replace"),
            error_output.decode("utf-8", errors="replace"),
        )

    def _run_remote(self, ssh: paramiko.SSHClient, command: str) -> str:
        """Run a remote command and raise SSHError on non-zero exit status."""
        exit_status, output, error = self._exec(ssh, command)
        if exit_status != 0:
            raise SSHError(
                _(
                    "error.ssh_remote_command_failed",
                    command=command,
                    error=error.strip() or exit_status,
                )
            )
        return output

    def _install_key_on_windows(
        self, ssh: paramiko.SSHClient, public_key_text: str
    ) -> bool:
        """Install the public key on a Windows server through PowerShell.

        The POSIX commands used elsewhere mean nothing to cmd or PowerShell,
        and Windows keeps keys in other places: see _WINDOWS_INSTALL_SCRIPT.

        Returns:
            True if the key was added, False if it was already there

        Raises:
            WindowsServerKeyError: The key could not be installed
        """
        script = _WINDOWS_INSTALL_SCRIPT.replace(
            "__PUBLIC_KEY__", _powershell_literal(public_key_text)
        )
        command = _powershell_command(script)
        if len(command) > _WINDOWS_MAX_COMMAND:
            raise WindowsServerKeyError(
                _("error.ssh_windows_key_too_long"), self.public_key_path
            )

        exit_status, output, error_output = self._exec(ssh, command)
        reports = _WINDOWS_REPORT.findall(output)
        status, detail = reports[-1] if reports else ("failed", "")
        try:
            detail = base64.b64decode(detail).decode("utf-8", errors="replace")
        except binascii.Error:
            detail = ""

        if exit_status == 0 and status == "installed":
            logger.info(f"Public key installed on the Windows server in {detail}")
            return True
        if exit_status == 0 and status == "present":
            logger.info(f"Public key already present on the Windows server in {detail}")
            return False

        # No report at all: PowerShell did not get to run the script
        error = detail or error_output.strip() or output.strip() or exit_status
        logger.error(f"Installing the public key on the Windows server failed: {error}")
        raise WindowsServerKeyError(
            _("error.ssh_windows_install_failed", error=error), self.public_key_path
        )

    def _upload_public_key(
        self, hostname: str, port: int, password: Optional[str]
    ) -> Optional[bool]:
        """Install the public key; password=None logs in with agent/default keys.

        Returns:
            True if the key was added, False if it was already there, or
            None if the server did not accept the login

        Raises:
            HostKeyChangedError: The server host key changed
            WindowsServerKeyError: The key could not be installed on a
                Windows server
            SSHError: The server cannot be reached, or a remote command failed
        """
        public_key_text = self._public_key_to_install()

        if password is not None:
            ssh = self._open_client(
                hostname,
                port,
                30,
                password=password,
                allow_agent=False,
                look_for_keys=False,
            )
        else:
            ssh = self._open_client(
                hostname, port, 30, allow_agent=True, look_for_keys=True
            )
        if ssh is None:
            return None

        try:
            if _is_windows_server(ssh):
                return self._install_key_on_windows(ssh, public_key_text)

            # Ensure .ssh directory exists
            self._run_remote(ssh, "mkdir -p ~/.ssh && chmod 700 ~/.ssh")

            # Read what is there. No `2>/dev/null || true`: csh and tcsh
            # take that for a redirection of the output and return nothing,
            # which would switch off both checks below. A missing file just
            # leaves the output empty (the exit status is not looked at)
            _status, existing_keys, _error = self._exec(
                ssh, "test -f ~/.ssh/authorized_keys && cat ~/.ssh/authorized_keys"
            )

            if _is_authorized(public_key_text, existing_keys):
                logger.info("Public key already exists in authorized_keys")
                return False

            # Appended to an unterminated last line, our key would be glued
            # onto it: sshd would not see the new key, and a last entry
            # without a comment would stop working as well. The line break
            # goes in with the key, in one write
            unterminated = bool(existing_keys) and not existing_keys.endswith("\n")
            line_break = "\\n" if unterminated else ""

            # printf, not echo: the key's comment is free text, and the echo
            # of zsh, dash and sh expands backslash sequences in it (\n, \t,
            # \c, \U...). printf leaves an argument printed with %s alone
            escaped_key = public_key_text.replace("'", "'\"'\"'")
            self._run_remote(
                ssh,
                f"printf '{line_break}%s\\n' '{escaped_key}'"
                " >> ~/.ssh/authorized_keys",
            )
            self._run_remote(ssh, "chmod 600 ~/.ssh/authorized_keys")

            logger.info("Public key uploaded to remote server")
            return True
        except SSHError:
            raise
        except Exception as e:
            # Channel-level failures after a successful login
            logger.error(f"Failed to upload public key: {e}")
            raise SSHError(_("error.ssh_upload_failed", error=_reason(e)))
        finally:
            ssh.close()

    def upload_public_key(self, hostname: str, port: int, password: str) -> bool:
        """
        Upload public key to remote server's authorized_keys using a password

        Args:
            hostname: Remote hostname
            port: SSH port
            password: Server password

        Returns:
            True if key was uploaded, False if already exists

        Raises:
            HostKeyChangedError: The server host key changed
            WindowsServerKeyError: The key could not be installed on a
                Windows server
            SSHError: Wrong password, unreachable server, or a failed
                remote command
        """
        uploaded = self._upload_public_key(hostname, port, password)
        if uploaded is None:
            logger.error("SSH password authentication failed")
            raise SSHError(
                _(
                    "error.ssh_auth_failed_detail",
                    username=self.server_user,
                    hostname=hostname,
                )
            )
        return uploaded

    def upload_public_key_with_existing_keys(
        self, hostname: str, port: int
    ) -> Optional[bool]:
        """
        Try uploading the public key using agent/default keys (no password).

        Returns:
            True if uploaded, False if already present, or None when the
            existing keys were not accepted (caller should fall back to
            password authentication)

        Raises:
            HostKeyChangedError: The server host key changed
            WindowsServerKeyError: The key could not be installed on a
                Windows server
            SSHError: Unreachable server or a failed remote command; a
                password would not help with either
        """
        return self._upload_public_key(hostname, port, password=None)

    def _ssh_options(self) -> List[Tuple[str, str]]:
        """What `ssh` is told besides where to connect, as (name, value).

        The same for the Host block and for the direct command line, which
        lead to the same server and must not drift apart.
        """
        return [
            ("IdentityFile", _config_path(self.private_key_path)),
            ("PreferredAuthentications", "publickey"),
            ("HostKeyAlias", self.host_alias),
            ("StrictHostKeyChecking", "accept-new"),
            ("UserKnownHostsFile", _config_path(self.known_hosts_path)),
            ("ServerAliveInterval", "30"),
            ("ServerAliveCountMax", "3"),
        ]

    @_reports_config_file_errors
    def update_ssh_config(
        self, tunnel_info: TunnelInfo, ports: Optional[List[int]] = None
    ) -> None:
        """
        Update ~/.ssh/config with tunnel information

        Args:
            tunnel_info: TunnelInfo object with hostname and port
            ports: Optional list of local ports to forward

        Raises:
            SSHError: The config file cannot be read or written
        """
        if not self.ssh_config_path.parent.exists():
            _make_ssh_dir(self.ssh_config_path.parent)

        # Create config file if not exists
        if not self.ssh_config_path.exists():
            self.ssh_config_path.touch(mode=0o600)
            with open(self.ssh_config_path, "w", **_USER_FILE) as f:
                f.write("# SSH config file\n")
            logger.info(f"Created SSH config file: {self.ssh_config_path}")

        # Read existing config
        with open(self.ssh_config_path, "r", **_USER_FILE) as f:
            lines = f.readlines()

        # Find and update/create host block
        host_block_start, host_block_end = self._find_host_block(lines)

        # Prepare new host block
        new_block = [
            f"Host {self.host_alias}\n",
            f"\tHostName {tunnel_info.hostname}\n",
            f"\tPort {tunnel_info.port}\n",
            f"\tUser {_config_token(self.server_user)}\n",
            *(f"\t{name} {value}\n" for name, value in self._ssh_options()),
        ]

        # Add port forwarding if specified
        if ports:
            for port in ports:
                new_block.append(f"\tLocalForward {port} localhost:{port}\n")

        # Update or append host block
        if host_block_start >= 0:
            lines[host_block_start:host_block_end] = new_block
        else:
            # Append new block - add leading newline for separation if file is not empty
            if lines and lines[-1].strip():
                lines.append("\n")
            lines.extend(new_block)

        # Write updated config
        with open(self.ssh_config_path, "w", **_USER_FILE) as f:
            f.writelines(lines)

        logger.info(f"Updated SSH config: {self.ssh_config_path}")
        self._keep_acceptable_to_windows_ssh()

    def _keep_acceptable_to_windows_ssh(self) -> None:
        """Windows: give the key and ~/.ssh/config access rights ssh.exe accepts.

        ssh.exe ignores a private key, and stops at a config file, that
        anyone but the user can access. A config file created just now needs
        its inherited entries removed. Both files need repair if they date
        from a version up to 0.3.0, which created ~/.ssh in a way that left
        every file in it with an entry ssh.exe rejects (see _make_ssh_dir).
        """
        if platform.system() != "Windows":
            return
        paths = [
            path
            for path in (self.private_key_path, self.ssh_config_path)
            if path.is_file()
        ]
        try:
            _restrict_to_user(*paths)
        except Exception as e:
            logger.warning(f"Failed to set access rights of {paths}: {e}")

    def _find_host_block(self, lines: List[str]) -> Tuple[int, int]:
        """Locate this alias's Host block; returns (start, end) or (-1, -1)."""
        for i, line in enumerate(lines):
            if line.strip() == f"Host {self.host_alias}":
                # Find end: empty line, next Host block, or Match block
                for j in range(i + 1, len(lines)):
                    stripped = lines[j].strip()
                    if not stripped or stripped.startswith(("Host ", "Match ")):
                        return i, j
                return i, len(lines)
        return -1, -1

    @_reports_config_file_errors
    def remove_host_block(self) -> bool:
        """Remove this alias's Host block from ~/.ssh/config.

        Returns:
            True if a block was removed, False if none existed

        Raises:
            SSHError: The config file cannot be read or written
        """
        if not self.ssh_config_path.exists():
            return False
        with open(self.ssh_config_path, "r", **_USER_FILE) as f:
            lines = f.readlines()
        start, end = self._find_host_block(lines)
        if start < 0:
            return False
        del lines[start:end]
        with open(self.ssh_config_path, "w", **_USER_FILE) as f:
            f.writelines(lines)
        logger.info(f"Removed SSH config block for {self.host_alias}")
        return True

    def build_ssh_command(
        self,
        tunnel_info: Optional[TunnelInfo] = None,
        ports: Optional[List[int]] = None,
    ) -> List[str]:
        """Build the ssh command line for a direct or alias-based connection."""
        if tunnel_info:
            # Direct connection with tunnel info. -o values are parsed like
            # ssh_config lines, so the options are those of the Host block
            # (IdentityFile rather than -i, which would choke on a percent
            # sign in the path)
            ssh_command = [
                "ssh",
                f"{self.server_user}@{tunnel_info.hostname}",
                "-p",
                str(tunnel_info.port),
            ]
            for name, value in self._ssh_options():
                ssh_command.extend(["-o", f"{name}={value}"])
        else:
            # Use configured alias
            ssh_command = ["ssh", self.host_alias]

        # Add port forwarding
        if ports:
            for port in ports:
                ssh_command.extend(["-L", f"{port}:localhost:{port}"])

        return ssh_command

    def connect(
        self,
        tunnel_info: Optional[TunnelInfo] = None,
        ports: Optional[List[int]] = None,
    ) -> int:
        """
        Connect to server using SSH

        Args:
            tunnel_info: Optional TunnelInfo (uses config alias if not provided)
            ports: Optional list of ports to forward

        Returns:
            SSH process return code
        """
        ssh_command = self.build_ssh_command(tunnel_info, ports)

        logger.info(f"Executing SSH command: {' '.join(ssh_command)}")

        try:
            # Use subprocess to maintain interactive session
            result = subprocess.run(ssh_command)

            if result.returncode != 0:
                logger.warning(f"SSH exited with code {result.returncode}")

            return result.returncode

        except KeyboardInterrupt:
            logger.info("SSH connection interrupted by user")
            return 130  # Standard exit code for Ctrl+C
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            raise SSHError(_("error.ssh_connect_failed", error=e))
