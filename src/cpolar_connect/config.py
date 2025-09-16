"""
Configuration management for Cpolar Connect
"""

import json
import os
import subprocess
import keyring
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, field_validator
from rich.console import Console
from rich.table import Table
from .i18n import _
from .exceptions import ConfigError

console = Console()
logger = logging.getLogger(__name__)

class CpolarConfig(BaseModel):
    """Cpolar configuration model with validation"""
    
    # Cpolar settings
    username: str = Field(..., description="Cpolar username/email")
    base_url: str = Field(default="https://dashboard.cpolar.com", description="Cpolar base URL")
    
    # Server settings  
    server_user: str = Field(..., description="Remote server username")
    ports: List[int] = Field(default=[8888, 6666], description="Ports to map")
    auto_connect: bool = Field(default=True, description="Auto-connect after update")
    
    # SSH settings
    ssh_key_path: str = Field(default="~/.ssh/id_rsa_cpolar", description="SSH private key path")
    ssh_host_alias: str = Field(default="cpolar-server", description="SSH host alias")
    ssh_key_size: int = Field(default=2048, description="SSH key size in bits")
    
    # Logging settings
    log_level: str = Field(default="INFO", description="Logging level")
    
    # Language settings
    language: str = Field(default="zh", description="Interface language (zh/en)")
    
    @field_validator('ports')
    @classmethod
    def validate_ports(cls, v: List[int]) -> List[int]:
        """Validate port numbers"""
        for port in v:
            if not (1 <= port <= 65535):
                raise ValueError(f"Invalid port: {port}. Must be between 1-65535")
        return v
    
    @field_validator('ssh_key_size')
    @classmethod
    def validate_key_size(cls, v: int) -> int:
        """Validate SSH key size"""
        if v < 1024:
            raise ValueError("SSH key size must be at least 1024 bits")
        return v
    
    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"Invalid log level: {v}")
        return v_upper
    
    @field_validator('language')
    @classmethod
    def validate_language(cls, v: str) -> str:
        """Validate language"""
        v_lower = v.lower()
        if v_lower == "zh":
            return "zh"
        elif v_lower == "en":
            return "en"
        else:
            raise ValueError(f"Invalid language: {v}. Must be 'zh' or 'en'")

class ConfigManager:
    """Configuration manager for Cpolar Connect"""
    
    def __init__(self):
        self.config_dir = Path.home() / ".cpolar_connect"
        self.config_file = self.config_dir / "config.json"
        self.logs_dir = self.config_dir / "logs"
        
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        self._config: Optional[CpolarConfig] = None
        
        # Keyring service name for secure credential storage
        self.keyring_service = "cpolar-connect"
    
    def config_exists(self) -> bool:
        """Check if configuration file exists"""
        return self.config_file.exists()
    
    def load_config(self) -> CpolarConfig:
        """Load and validate configuration from file"""
        if not self.config_exists():
            raise ConfigError(_('error.config_not_found', path=self.config_file))
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            self._config = CpolarConfig(**config_data)
            return self._config
            
        except json.JSONDecodeError as e:
            raise ConfigError(_('error.config_invalid_json', error=e))
        except Exception as e:
            raise ConfigError(_('error.config_load_failed', error=e))
    
    def save_config(self, config: CpolarConfig) -> None:
        """Save configuration to file"""
        try:
            config_data = config.model_dump()
            
            # Write to temp file first, then rename (atomic write)
            temp_file = self.config_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2)
            
            temp_file.replace(self.config_file)
            self._config = config
            
            console.print("[dim]Configuration saved[/dim]")
            
        except Exception as e:
            raise ConfigError(_('error.config_save_failed', error=e))
    
    def create_config(self, config_data: Dict[str, Any]) -> CpolarConfig:
        """Create and save initial configuration"""
        try:
            config = CpolarConfig(**config_data)
            self.save_config(config)
            return config
            
        except Exception as e:
            raise ConfigError(_('error.config_create_failed', error=e))
    
    def get_config(self) -> CpolarConfig:
        """Get current configuration, loading if necessary"""
        if self._config is None:
            self._config = self.load_config()
        return self._config
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation"""
        config = self.get_config()
        
        # Simple dot notation support for common patterns
        if key == "cpolar.username":
            return config.username
        elif key == "cpolar.base_url":
            return config.base_url
        elif key == "server.user":
            return config.server_user
        elif key == "server.ports":
            return config.ports
        elif key == "server.auto_connect":
            return config.auto_connect
        elif key == "ssh.key_path":
            return config.ssh_key_path
        elif key == "ssh.host_alias":
            return config.ssh_host_alias
        elif key == "ssh.key_size":
            return config.ssh_key_size
        elif key == "log_level":
            return config.log_level
        else:
            # Try direct attribute access
            try:
                return getattr(config, key.replace('.', '_'))
            except AttributeError:
                if default is not None:
                    return default
                raise KeyError(_('error.config_key_not_found', key=key))
    
    def set(self, key: str, value: Any) -> None:
        """Set configuration value and save"""
        config = self.get_config()
        config_dict = config.model_dump()
        
        # Update the value
        if key == "cpolar.username":
            config_dict['username'] = value
        elif key == "cpolar.base_url":
            config_dict['base_url'] = value
        elif key == "server.user":
            config_dict['server_user'] = value
        elif key == "server.ports":
            # Handle comma-separated ports
            if isinstance(value, list):
                config_dict['ports'] = value
            elif isinstance(value, str):
                # Parse comma-separated string
                try:
                    config_dict['ports'] = [int(p.strip()) for p in value.split(',')]
                except ValueError:
                    raise ConfigError(f"Invalid port value: {value}. Must be numbers separated by commas.")
            else:
                config_dict['ports'] = [int(value)]
        elif key == "server.auto_connect":
            # Handle boolean values properly
            if isinstance(value, bool):
                config_dict['auto_connect'] = value
            elif isinstance(value, str):
                value_lower = value.lower()
                if value_lower in ['true', 'yes', '1', 'on']:
                    config_dict['auto_connect'] = True
                elif value_lower in ['false', 'no', '0', 'off']:
                    config_dict['auto_connect'] = False
                else:
                    raise ConfigError(f"Invalid boolean value: {value}. Use 'true' or 'false'.")
            else:
                config_dict['auto_connect'] = bool(value)
        elif key == "ssh.key_path":
            config_dict['ssh_key_path'] = value
        elif key == "ssh.host_alias":
            config_dict['ssh_host_alias'] = value
        elif key == "ssh.key_size":
            # Handle integer value with error checking
            try:
                config_dict['ssh_key_size'] = int(value)
            except (ValueError, TypeError):
                raise ConfigError(f"Invalid key size: {value}. Must be an integer.")
        elif key == "log_level":
            # Validate log level
            valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
            value_upper = str(value).upper()
            if value_upper in valid_levels:
                config_dict['log_level'] = value_upper
            else:
                raise ConfigError(f"Invalid log level: {value}. Must be one of: {', '.join(valid_levels)}")
        else:
            # Try direct attribute
            attr_name = key.replace('.', '_')
            if hasattr(config, attr_name):
                config_dict[attr_name] = value
            else:
                raise KeyError(_('error.config_key_not_found', key=key))
        
        # Create new config and save
        updated_config = CpolarConfig(**config_dict)
        self.save_config(updated_config)
    
    def edit(self) -> None:
        """Open configuration file in a reasonable editor per platform"""
        if not self.config_exists():
            raise ConfigError(_('cli.no_config'))

        editor = os.environ.get('EDITOR')
        argv = None
        if editor:
            argv = [editor, str(self.config_file)]
        else:
            import platform
            system = platform.system()
            if system == 'Darwin':
                argv = ['open', '-e', str(self.config_file)]
            elif system == 'Windows':
                argv = ['notepad', str(self.config_file)]
            else:
                argv = ['nano', str(self.config_file)]

        try:
            subprocess.run(argv, check=True)
            # Reload config after editing
            self._config = None
        except subprocess.CalledProcessError as e:
            raise ConfigError(_('error.config_edit_failed', error=e))
        except FileNotFoundError:
            raise ConfigError(_('error.editor_not_found', editor=argv[0]))
    
    def display(self) -> None:
        """Display current configuration"""
        config = self.get_config()
        
        table = Table(title="⚙️ Cpolar Connect Configuration", show_header=True, header_style="bold magenta")
        table.add_column("Setting", style="cyan", width=20)
        table.add_column("Value", style="white")
        
        # Add configuration rows
        table.add_row("Username", config.username)
        table.add_row("Base URL", config.base_url)
        table.add_row("Server User", config.server_user)
        table.add_row("Ports", ", ".join(str(p) for p in config.ports))
        table.add_row("Auto Connect", "✅ Yes" if config.auto_connect else "❌ No")
        table.add_row("SSH Key Path", config.ssh_key_path)
        table.add_row("SSH Host Alias", config.ssh_host_alias)
        table.add_row("SSH Key Size", f"{config.ssh_key_size} bits")
        table.add_row("Log Level", config.log_level)
        table.add_row("Language", "🇨🇳 中文" if config.language == "zh" else "🇬🇧 English")
        
        console.print(table)
        
        # Show credential status
        password_stored = self.has_stored_password(config.username)
        if password_stored is True:
            password_status = "🔐 Stored (env var)"
        elif password_stored is None:
            password_status = "🔑 May be stored in keyring"
        else:
            password_status = "❌ Not stored"
        console.print(f"\n🔑 Password Status: {password_status}")
        console.print(f"📁 Config Dir: {self.config_dir}")
    
    def get_password(self, username: str) -> Optional[str]:
        """Get password from environment or keyring
        
        Note: Environment variable is checked first to avoid keyring permission prompts.
        """
        # Try environment variable first (no permission needed)
        password = os.getenv('CPOLAR_PASSWORD')
        if password:
            return password
        
        # Try keyring (may trigger permission prompt on macOS)
        try:
            return keyring.get_password(self.keyring_service, username)
        except Exception as e:
            # Silently fail for keyring access to avoid repeated error messages
            logger.debug(f"Keyring access failed: {e}")
            return None
    
    def set_password(self, username: str, password: str) -> None:
        """Store password in keyring"""
        try:
            keyring.set_password(self.keyring_service, username, password)
            console.print(f"[green]✅ {_('info.password_stored')}[/green]")
        except Exception as e:
            raise ConfigError(_('error.password_store_failed', error=e))
    
    def has_stored_password(self, username: str) -> bool:
        """Check if password is stored (without triggering keyring access)"""
        # Check environment variable first (no permission needed)
        if os.getenv('CPOLAR_PASSWORD'):
            return True
        
        # For keyring, we can't check without accessing it
        # So we return a generic status to avoid permission prompts
        try:
            # Try to check if keyring backend is available
            backend = keyring.get_keyring()
            # Return "maybe" status for keyring without actually accessing it
            if backend and backend.__class__.__name__ != 'NullKeyring':
                return None  # Unknown status - avoid accessing keyring
            return False
        except:
            return False
    
    def clear_password(self, username: str) -> None:
        """Clear stored password"""
        try:
            keyring.delete_password(self.keyring_service, username)
            console.print(f"[green]✅ {_('info.password_cleared')}[/green]")
        except keyring.errors.PasswordDeleteError:
            console.print(f"[yellow]{_('warning.no_password')}[/yellow]")
        except Exception as e:
            console.print(f"[red]❌ {_('error.password_clear_failed', error=e)}[/red]")
    
    @property
    def config_path(self) -> Path:
        """Get configuration file path"""
        return self.config_file
    
    @property
    def logs_path(self) -> Path:
        """Get logs directory path"""
        return self.logs_dir
