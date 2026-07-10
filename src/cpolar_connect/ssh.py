"""
SSH management module for Cpolar Connect
"""

import logging
import os
import stat
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

import paramiko

from .config import ACCOUNTS_DIR_NAME, CpolarConfig, resolve_account
from .exceptions import HostKeyChangedError, SSHError
from .i18n import _
from .tunnel import TunnelInfo

logger = logging.getLogger(__name__)


class AliasHostKeyPolicy(paramiko.MissingHostKeyPolicy):
    """TOFU host key policy keyed by a stable alias.

    The tunnel hostname/port change on every cpolar restart, so host keys
    are recorded and verified under the configured ssh_host_alias instead
    of the (ever-changing) real hostname. The same file is used by the ssh
    CLI via HostKeyAlias + UserKnownHostsFile.
    """

    def __init__(self, alias: str, known_hosts_path: Path):
        self.alias = alias
        self.known_hosts_path = known_hosts_path

    def missing_host_key(self, client, hostname, key) -> None:
        known = paramiko.HostKeys()
        if self.known_hosts_path.exists():
            known.load(str(self.known_hosts_path))

        entry = known.lookup(self.alias)
        recorded = None
        if entry is not None and key.get_name() in entry:
            recorded = entry[key.get_name()]

        if recorded is None:
            # Trust on first use: record under the alias
            known.add(self.alias, key.get_name(), key)
            self.known_hosts_path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            self.known_hosts_path.parent.chmod(0o700)
            known.save(str(self.known_hosts_path))
            self.known_hosts_path.chmod(0o600)
            logger.info(f"Recorded host key for {self.alias} ({key.get_name()})")
            return

        if recorded.asbytes() != key.asbytes():
            logger.error(f"Host key mismatch for {self.alias}")
            raise HostKeyChangedError(_("error.host_key_changed"))

        logger.debug(f"Host key for {self.alias} verified")


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
                self.ssh_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
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

            # Set correct permissions (600)
            try:
                os.chmod(self.private_key_path, stat.S_IRUSR | stat.S_IWUSR)
            except Exception as e:
                logger.warning(f"Failed to set private key permissions: {e}")

            # Save public key
            public_key_text = f"ssh-rsa {key.get_base64()} cpolar-connect"
            with open(self.public_key_path, "w", encoding="utf-8") as f:
                f.write(public_key_text + "\n")

            logger.info(f"Generated new SSH key pair at {self.private_key_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to generate SSH key: {e}")
            raise SSHError(_("error.ssh_key_gen_failed", error=e))

    def _regenerate_public_key(self) -> None:
        """Regenerate public key from existing private key"""
        try:
            key = paramiko.RSAKey.from_private_key_file(str(self.private_key_path))
            public_key_text = f"ssh-rsa {key.get_base64()} cpolar-connect"

            with open(self.public_key_path, "w", encoding="utf-8") as f:
                f.write(public_key_text + "\n")

            logger.info(f"Regenerated public key: {self.public_key_path}")

        except Exception as e:
            logger.error(f"Failed to regenerate public key: {e}")
            raise SSHError(_("error.ssh_pubkey_regen_failed", error=e))

    def test_ssh_connection(self, hostname: str, port: int, timeout: int = 10) -> bool:
        """
        Test SSH connection with key authentication

        Args:
            hostname: Remote hostname
            port: SSH port
            timeout: Connection timeout in seconds

        Returns:
            True if connection successful, False otherwise
        """
        try:
            key = paramiko.RSAKey.from_private_key_file(str(self.private_key_path))
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(self._host_key_policy())

            try:
                ssh.connect(
                    hostname=hostname,
                    port=port,
                    username=self.server_user,
                    pkey=key,
                    timeout=timeout,
                )
            finally:
                ssh.close()

            logger.info("SSH key authentication successful")
            return True

        except HostKeyChangedError:
            # A mismatch must abort; never treat it as "no key yet"
            raise
        except paramiko.AuthenticationException:
            logger.warning("SSH key authentication failed")
            return False
        except Exception as e:
            logger.error(f"SSH connection test failed: {e}")
            return False

    def _run_remote(self, ssh: paramiko.SSHClient, command: str) -> str:
        """Run a remote command and raise SSHError on non-zero exit status."""
        stdin, stdout, stderr = ssh.exec_command(command)
        exit_status = stdout.channel.recv_exit_status()
        output = stdout.read().decode("utf-8", errors="replace")
        if exit_status != 0:
            error = stderr.read().decode("utf-8", errors="replace").strip()
            raise SSHError(
                _(
                    "error.ssh_remote_command_failed",
                    command=command,
                    error=error or exit_status,
                )
            )
        return output

    def _upload_public_key(
        self, hostname: str, port: int, password: Optional[str]
    ) -> bool:
        """Upload the public key; password=None uses agent/default keys.

        Raises raw paramiko exceptions on connection/auth failure so callers
        can decide the fallback semantics; raises SSHError for remote command
        failures.
        """
        if not self.public_key_path.exists():
            raise SSHError(_("error.ssh_pubkey_not_found", path=self.public_key_path))

        with open(self.public_key_path, "r", encoding="utf-8") as f:
            public_key_text = f.read().strip()

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(self._host_key_policy())

        try:
            if password is not None:
                ssh.connect(
                    hostname=hostname,
                    port=port,
                    username=self.server_user,
                    password=password,
                    timeout=30,
                    allow_agent=False,
                    look_for_keys=False,
                )
            else:
                ssh.connect(
                    hostname=hostname,
                    port=port,
                    username=self.server_user,
                    timeout=30,
                    allow_agent=True,
                    look_for_keys=True,
                )

            # Ensure .ssh directory exists
            self._run_remote(ssh, "mkdir -p ~/.ssh && chmod 700 ~/.ssh")

            # Check if key already exists (|| true: absence is not an error)
            stdin, stdout, stderr = ssh.exec_command(
                "cat ~/.ssh/authorized_keys 2>/dev/null || true"
            )
            existing_keys = stdout.read().decode("utf-8")

            if public_key_text in existing_keys:
                logger.info("Public key already exists in authorized_keys")
                return False

            escaped_key = public_key_text.replace("'", "'\"'\"'")
            self._run_remote(ssh, f"echo '{escaped_key}' >> ~/.ssh/authorized_keys")
            self._run_remote(ssh, "chmod 600 ~/.ssh/authorized_keys")

            logger.info("Public key uploaded to remote server")
            return True
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
        """
        try:
            return self._upload_public_key(hostname, port, password)
        except (HostKeyChangedError, SSHError):
            raise
        except paramiko.AuthenticationException as e:
            logger.error(f"SSH authentication failed: {e}")
            raise SSHError(
                _(
                    "error.ssh_auth_failed_detail",
                    username=self.server_user,
                    hostname=hostname,
                )
            )
        except Exception as e:
            logger.error(f"Failed to upload public key: {e}")
            raise SSHError(_("error.ssh_upload_failed", error=e))

    def upload_public_key_with_existing_keys(
        self, hostname: str, port: int
    ) -> Optional[bool]:
        """
        Try uploading the public key using agent/default keys (no password).

        Returns:
            True if uploaded, False if already present, or None when the
            existing keys were not accepted (caller should fall back to
            password authentication)
        """
        try:
            return self._upload_public_key(hostname, port, password=None)
        except (HostKeyChangedError, SSHError):
            raise
        except paramiko.AuthenticationException:
            logger.debug("Existing keys not accepted by server")
            return None
        except Exception as e:
            # e.g. "Too many authentication failures" when the agent holds
            # more keys than the server's MaxAuthTries; fall back silently
            logger.debug(f"Existing-key upload attempt failed: {e}")
            return None

    def update_ssh_config(
        self, tunnel_info: TunnelInfo, ports: Optional[List[int]] = None
    ) -> None:
        """
        Update ~/.ssh/config with tunnel information

        Args:
            tunnel_info: TunnelInfo object with hostname and port
            ports: Optional list of local ports to forward
        """
        if not self.ssh_config_path.parent.exists():
            self.ssh_config_path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)

        # Create config file if not exists
        if not self.ssh_config_path.exists():
            self.ssh_config_path.touch(mode=0o600)
            with open(self.ssh_config_path, "w", encoding="utf-8") as f:
                f.write("# SSH config file\n")
            logger.info(f"Created SSH config file: {self.ssh_config_path}")

        # Read existing config
        with open(self.ssh_config_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Find and update/create host block
        host_block_start, host_block_end = self._find_host_block(lines)

        # Prepare new host block
        new_block = [
            f"Host {self.host_alias}\n",
            f"\tHostName {tunnel_info.hostname}\n",
            f"\tPort {tunnel_info.port}\n",
            f"\tUser {self.server_user}\n",
            f"\tIdentityFile {self.private_key_path}\n",
            f"\tPreferredAuthentications publickey\n",
            f"\tHostKeyAlias {self.host_alias}\n",
            f"\tStrictHostKeyChecking accept-new\n",
            f"\tUserKnownHostsFile {self.known_hosts_path}\n",
            f"\tServerAliveInterval 30\n",
            f"\tServerAliveCountMax 3\n",
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
        with open(self.ssh_config_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        logger.info(f"Updated SSH config: {self.ssh_config_path}")

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

    def remove_host_block(self) -> bool:
        """Remove this alias's Host block from ~/.ssh/config.

        Returns:
            True if a block was removed, False if none existed
        """
        if not self.ssh_config_path.exists():
            return False
        with open(self.ssh_config_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        start, end = self._find_host_block(lines)
        if start < 0:
            return False
        del lines[start:end]
        with open(self.ssh_config_path, "w", encoding="utf-8") as f:
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
            # Direct connection with tunnel info
            ssh_command = [
                "ssh",
                f"{self.server_user}@{tunnel_info.hostname}",
                "-p",
                str(tunnel_info.port),
                "-i",
                str(self.private_key_path),
                "-o",
                "PreferredAuthentications=publickey",
                "-o",
                f"HostKeyAlias={self.host_alias}",
                "-o",
                "StrictHostKeyChecking=accept-new",
                "-o",
                f"UserKnownHostsFile={self.known_hosts_path}",
                "-o",
                "ServerAliveInterval=30",
                "-o",
                "ServerAliveCountMax=3",
            ]
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
