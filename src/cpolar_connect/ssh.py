"""
SSH management module for Cpolar Connect
"""

import os
import stat
import subprocess
import logging
from pathlib import Path
from typing import Optional, Tuple, List
import paramiko
from rich.console import Console
from rich.prompt import Prompt
from getpass import getpass

from .config import CpolarConfig
from .tunnel import TunnelInfo
from .exceptions import SSHError
from .i18n import _

console = Console()
logger = logging.getLogger(__name__)


class SSHManager:
    """Manage SSH keys and connections"""
    
    def __init__(self, config: CpolarConfig):
        """
        Initialize SSH manager with configuration
        
        Args:
            config: CpolarConfig object
        """
        self.config = config
        self.private_key_path = Path(os.path.expanduser(config.ssh_key_path))
        self.public_key_path = Path(str(self.private_key_path) + ".pub")
        self.ssh_dir = self.private_key_path.parent
        self.ssh_config_path = Path.home() / ".ssh" / "config"
        self.host_alias = config.ssh_host_alias
        self.server_user = config.server_user
        self.key_size = config.ssh_key_size
    
    def ensure_ssh_directory(self) -> None:
        """Ensure .ssh directory exists with correct permissions"""
        if not self.ssh_dir.exists():
            try:
                self.ssh_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
                logger.info(f"Created SSH directory: {self.ssh_dir}")
            except Exception as e:
                logger.error(f"Failed to create SSH directory: {e}")
                raise SSHError(_('error.ssh_dir_failed', error=e))
    
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
            console.print(f"[dim]{_('ssh.key_exists', path=self.private_key_path)}[/dim]")
            
            # Ensure public key exists
            if not self.public_key_path.exists():
                self._regenerate_public_key()
            
            return False
        
        # Generate new key pair
        console.print(f"[yellow]{_('ssh.generating_key')}[/yellow]")
        
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
            
            console.print(f"[green]✅ {_('ssh.generating_key')}[/green]")
            
            logger.info(f"Generated new SSH key pair at {self.private_key_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to generate SSH key: {e}")
            raise SSHError(_('error.ssh_key_gen_failed', error=e))
    
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
            raise SSHError(_('error.ssh_pubkey_regen_failed', error=e))
    
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
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            ssh.connect(
                hostname=hostname,
                port=port,
                username=self.server_user,
                pkey=key,
                timeout=timeout
            )
            ssh.close()
            
            logger.info("SSH key authentication successful")
            return True
            
        except paramiko.AuthenticationException:
            logger.warning("SSH key authentication failed")
            return False
        except Exception as e:
            logger.error(f"SSH connection test failed: {e}")
            return False
    
    def upload_public_key(self, hostname: str, port: int, password: Optional[str] = None) -> None:
        """
        Upload public key to remote server's authorized_keys
        
        Args:
            hostname: Remote hostname
            port: SSH port
            password: Server password (will prompt if not provided)
        """
        # Read public key
        if not self.public_key_path.exists():
            raise SSHError(_('error.ssh_pubkey_not_found', path=self.public_key_path))
        
        with open(self.public_key_path, "r", encoding="utf-8") as f:
            public_key_text = f.read().strip()
        
        # Get password if not provided
        if not password:
            console.print(f"[yellow]🔑 {_('ssh.need_password_for_key_upload')}[/yellow]")
            password = getpass(f"Enter password for {self.server_user}@{hostname}: ")
        
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        console.print(f"[yellow]{_('ssh.uploading_key')}[/yellow]")
        
        try:
            # Connect with password
            console.print(f"[dim]{_('ssh.trying_connect', username=self.server_user, hostname=hostname)}[/dim]")
            ssh.connect(
                hostname=hostname,
                port=port,
                username=self.server_user,
                password=password,
                timeout=30,  # Increase timeout for slow connections
                allow_agent=False,
                look_for_keys=False
            )
            
            # Ensure .ssh directory exists
            stdin, stdout, stderr = ssh.exec_command("mkdir -p ~/.ssh && chmod 700 ~/.ssh")
            stdout.read()
            
            # Check if key already exists
            stdin, stdout, stderr = ssh.exec_command("cat ~/.ssh/authorized_keys 2>/dev/null || true")
            existing_keys = stdout.read().decode('utf-8')
            
            if public_key_text in existing_keys:
                console.print(f"[yellow]⚠️ {_('warning.ssh_key_exists')}[/yellow]")
            else:
                # Append public key
                escaped_key = public_key_text.replace("'", "'\"'\"'")
                command = f"echo '{escaped_key}' >> ~/.ssh/authorized_keys"
                stdin, stdout, stderr = ssh.exec_command(command)
                
                # Set permissions
                ssh.exec_command("chmod 600 ~/.ssh/authorized_keys")
                
                console.print(f"[green]{_('ssh.key_uploaded')}[/green]")
                logger.info("Public key uploaded to remote server")
            
            ssh.close()
            
        except paramiko.AuthenticationException as e:
            logger.error(f"SSH authentication failed: {e}")
            error_msg = _('error.ssh_auth_failed_detail', username=self.server_user, hostname=hostname)
            console.print(f"[red]❌ {error_msg}[/red]")
            console.print(f"[yellow]💡 {_('hint.check_username_password')}[/yellow]")
            console.print(f"[yellow]💡 {_('hint.run_doctor')}[/yellow]")
            raise SSHError(error_msg)
        except Exception as e:
            logger.error(f"Failed to upload public key: {e}")
            raise SSHError(_('error.ssh_upload_failed', error=e))
    
    def update_ssh_config(self, tunnel_info: TunnelInfo, ports: Optional[List[int]] = None) -> None:
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
        host_block_start = -1
        host_block_end = -1
        
        for i, line in enumerate(lines):
            if line.strip() == f"Host {self.host_alias}":
                host_block_start = i
                # Find end of this host block
                for j in range(i + 1, len(lines)):
                    if lines[j].strip().startswith("Host "):
                        host_block_end = j
                        break
                else:
                    host_block_end = len(lines)
                break
        
        # Prepare new host block
        new_block = [
            f"\nHost {self.host_alias}\n",
            f"\tHostName {tunnel_info.hostname}\n",
            f"\tPort {tunnel_info.port}\n",
            f"\tUser {self.server_user}\n",
            f"\tIdentityFile {self.private_key_path}\n",
            f"\tPreferredAuthentications publickey\n",
            f"\tStrictHostKeyChecking no\n",
            f"\tUserKnownHostsFile /dev/null\n"
        ]
        
        # Add port forwarding if specified
        if ports:
            for port in ports:
                new_block.append(f"\tLocalForward {port} localhost:{port}\n")
        
        # Update or append host block
        if host_block_start >= 0:
            # Replace existing block
            lines[host_block_start:host_block_end] = new_block
            console.print(f"[green]{_('ssh.config_updated')}[/green]")
        else:
            # Append new block
            lines.extend(new_block)
            console.print(f"[green]{_('ssh.config_updated')}[/green]")
        
        # Write updated config
        with open(self.ssh_config_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        
        logger.info(f"Updated SSH config: {self.ssh_config_path}")
        console.print(f"[dim]Config updated: {self.ssh_config_path}[/dim]")
    
    def connect(self, tunnel_info: Optional[TunnelInfo] = None, ports: Optional[List[int]] = None) -> None:
        """
        Connect to server using SSH
        
        Args:
            tunnel_info: Optional TunnelInfo (uses config alias if not provided)
            ports: Optional list of ports to forward
        """
        if tunnel_info:
            # Direct connection with tunnel info
            ssh_command = [
                "ssh",
                f"{self.server_user}@{tunnel_info.hostname}",
                "-p", str(tunnel_info.port),
                "-i", str(self.private_key_path),
                "-o", "PreferredAuthentications=publickey",
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null"
            ]
        else:
            # Use configured alias
            ssh_command = ["ssh", self.host_alias]
        
        # Add port forwarding
        if ports:
            for port in ports:
                ssh_command.extend(["-L", f"{port}:localhost:{port}"])
        
        # Execute SSH command
        console.print(f"[cyan]🔗 {_('ssh.connecting')}[/cyan]")
        console.print(f"[dim]Command: {' '.join(ssh_command)}[/dim]")
        
        try:
            # Use subprocess to maintain interactive session
            result = subprocess.run(ssh_command)
            
            if result.returncode != 0:
                logger.warning(f"SSH exited with code {result.returncode}")
            
        except KeyboardInterrupt:
            console.print(f"\n[yellow]{_('warning.connection_interrupted')}[/yellow]")
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            raise SSHError(_('error.ssh_connect_failed', error=e))
    
    def setup_and_connect(self, tunnel_info: TunnelInfo, password: Optional[str] = None) -> None:
        """
        Complete setup and connection flow
        
        Args:
            tunnel_info: TunnelInfo with connection details
            password: Optional server password
        """
        # 1. Generate SSH key if needed
        self.generate_ssh_key()
        
        # 2. Test connection
        if not self.test_ssh_connection(tunnel_info.hostname, tunnel_info.port):
            console.print(f"[yellow]⚠️ {_('warning.ssh_auth_failed')}[/yellow]")
            
            # 3. Upload public key if needed
            self.upload_public_key(tunnel_info.hostname, tunnel_info.port, password)
            
            # 4. Test again
            if not self.test_ssh_connection(tunnel_info.hostname, tunnel_info.port):
                raise SSHError(_('error.ssh_auth_failed'))
        
        # 5. Update SSH config
        self.update_ssh_config(tunnel_info, self.config.ports)
        
        # 6. Connect
        if self.config.auto_connect:
            self.connect(tunnel_info, self.config.ports)
        else:
            console.print(f"\n[green]✅ SSH configuration updated. Connect manually with:[/green]")
            console.print(f"[cyan]ssh {self.host_alias}[/cyan]")