"""
Configuration management for Cpolar Connect
"""

import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator

from .exceptions import ConfigError
from .i18n import _

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://dashboard.cpolar.com"

# Sentinel to distinguish "no default given" from an explicit default of None
_MISSING = object()

ACCOUNTS_DIR_NAME = "accounts"
DEFAULT_ACCOUNT = "default"
RESERVED_ACCOUNT_NAMES = frozenset(
    {"current", "logs", "accounts", "config.json", ".password", "known_hosts"}
)
_ACCOUNT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _root_dir() -> Path:
    return Path.home() / ".cpolar_connect"


def validate_account_name(name: str) -> str:
    """Validate an account name used as a path component and alias source."""
    if not name or name in RESERVED_ACCOUNT_NAMES or not _ACCOUNT_NAME_RE.match(name):
        raise ConfigError(_("error.invalid_account_name", name=name))
    accounts_dir = _root_dir() / ACCOUNTS_DIR_NAME
    resolved = (accounts_dir / name).resolve()
    if resolved.parent != accounts_dir.resolve():
        raise ConfigError(_("error.invalid_account_name", name=name))
    return name


def read_current_account() -> Optional[str]:
    """Read the current-account file; empty/missing means unset."""
    current_file = _root_dir() / "current"
    if not current_file.exists():
        return None
    try:
        name = current_file.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return name or None


def write_current_account(name: str) -> None:
    """Atomically record the current account (temp + replace)."""
    validate_account_name(name)
    current_file = _root_dir() / "current"
    current_file.parent.mkdir(parents=True, exist_ok=True)
    temp = current_file.with_suffix(".tmp")
    temp.write_text(name + "\n", encoding="utf-8")
    temp.replace(current_file)


def resolve_account(explicit: Optional[str]) -> str:
    """Resolve the account: explicit (-a) > CPOLAR_ACCOUNT > current > default."""
    name = explicit or os.getenv("CPOLAR_ACCOUNT") or read_current_account()
    if name is None:
        return DEFAULT_ACCOUNT
    return validate_account_name(name)


class CpolarConfig(BaseModel):
    """Cpolar configuration model with validation"""

    # Cpolar settings
    username: str = Field(..., description="Cpolar username/email")
    base_url: str = Field(default=DEFAULT_BASE_URL, description="Cpolar base URL")

    # Server settings
    server_user: str = Field(..., description="Remote server username")
    ports: List[int] = Field(default=[8888, 6666], description="Ports to map")
    auto_connect: bool = Field(default=True, description="Auto-connect after update")

    # SSH settings
    ssh_key_path: str = Field(
        default="~/.ssh/id_rsa_cpolar", description="SSH private key path"
    )
    ssh_host_alias: str = Field(default="cpolar-server", description="SSH host alias")
    ssh_key_size: int = Field(default=2048, description="SSH key size in bits")

    # Logging settings
    log_level: str = Field(default="INFO", description="Logging level")

    # Language settings
    language: str = Field(default="zh", description="Interface language (zh/en)")

    @field_validator("ports")
    @classmethod
    def validate_ports(cls, v: List[int]) -> List[int]:
        """Validate port numbers"""
        for port in v:
            if not (1 <= port <= 65535):
                raise ValueError(f"Invalid port: {port}. Must be between 1-65535")
        return v

    @field_validator("ssh_key_size")
    @classmethod
    def validate_key_size(cls, v: int) -> int:
        """Validate SSH key size"""
        if v < 1024:
            raise ValueError("SSH key size must be at least 1024 bits")
        return v

    @field_validator("ssh_host_alias")
    @classmethod
    def validate_ssh_host_alias(cls, v: str) -> str:
        """Alias is written verbatim into ~/.ssh/config; keep it inert."""
        if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", v):
            raise ValueError(f"Invalid ssh_host_alias: {v!r}")
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"Invalid log level: {v}")
        return v_upper

    @field_validator("language")
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

    def __init__(self, account: Optional[str] = None):
        self.account = validate_account_name(account) if account else DEFAULT_ACCOUNT
        self.config_dir = _root_dir()
        self.accounts_dir = self.config_dir / ACCOUNTS_DIR_NAME
        self.account_dir = self.accounts_dir / self.account
        self.config_file = self.account_dir / "config.json"
        self.password_file = self.account_dir / ".password"
        self.known_hosts_file = self.account_dir / "known_hosts"
        self.logs_dir = self.config_dir / "logs"

        self.logs_dir.mkdir(parents=True, exist_ok=True)
        try:
            # The dir holds secrets (.password) and integrity-sensitive files
            self.config_dir.chmod(0o700)
        except OSError as e:
            logger.debug(f"Could not tighten config dir permissions: {e}")

        self._config: Optional[CpolarConfig] = None

    def _ensure_account_dir(self) -> None:
        """Create the account directory with owner-only permissions."""
        self.account_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.account_dir.chmod(0o700)
        self.accounts_dir.chmod(0o700)

    def list_accounts(self) -> List[Dict[str, Any]]:
        """List accounts with name, username, alias and current marker."""
        current = read_current_account() or DEFAULT_ACCOUNT
        result: List[Dict[str, Any]] = []
        if not self.accounts_dir.exists():
            return result
        for entry in sorted(self.accounts_dir.iterdir()):
            if not entry.is_dir():
                continue
            try:
                validate_account_name(entry.name)
            except ConfigError:
                logger.warning(f"Skipping invalid account dir: {entry.name}")
                continue
            info: Dict[str, Any] = {
                "name": entry.name,
                "username": "",
                "ssh_host_alias": "",
                "is_current": entry.name == current,
            }
            cfg_file = entry / "config.json"
            if cfg_file.exists():
                try:
                    data = json.loads(cfg_file.read_text(encoding="utf-8"))
                    info["username"] = data.get("username", "")
                    info["ssh_host_alias"] = data.get("ssh_host_alias", "cpolar-server")
                except (OSError, json.JSONDecodeError):
                    pass
            result.append(info)
        return result

    def remove_account(self, name: str) -> None:
        """Delete an account directory (config, password, host keys)."""
        validate_account_name(name)
        target = self.accounts_dir / name
        if not target.is_dir():
            raise ConfigError(_("error.account_not_found", name=name))
        shutil.rmtree(target)

    def find_alias_conflict(self, alias: str) -> Optional[str]:
        """Return the name of another account already using this alias."""
        for info in self.list_accounts():
            if info["name"] != self.account and info["ssh_host_alias"] == alias:
                return info["name"]
        return None

    # Migration order is load-bearing: config.json moves last and acts as
    # the commit point, so any interrupted state still triggers a re-run.
    _MIGRATION_ORDER = (".password", "known_hosts", "config.json")

    def ensure_migrated(self) -> bool:
        """Migrate the legacy single-account layout into accounts/default.

        Idempotent and safe to re-run after interruption or concurrently.
        Returns True if any migration work happened.
        """
        legacy = [f for f in self._MIGRATION_ORDER if (self.config_dir / f).exists()]
        if not legacy:
            return False

        default_dir = self.accounts_dir / DEFAULT_ACCOUNT
        default_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
        default_dir.chmod(0o700)
        self.accounts_dir.chmod(0o700)

        old_known_hosts = self.config_dir / "known_hosts"
        new_known_hosts = default_dir / "known_hosts"

        for name in self._MIGRATION_ORDER:
            src = self.config_dir / name
            dst = default_dir / name
            if not src.exists():
                continue
            if dst.exists():
                # Never overwrite; keep the legacy file for the user to judge
                bak = self.config_dir / f"{name}.pre-migration.bak"
                src.rename(bak)
                logger.warning(
                    f"Migration target {dst} already exists; "
                    f"kept legacy file as {bak}"
                )
                continue
            try:
                src.rename(dst)
            except FileNotFoundError:
                continue  # concurrent migrator won; treat as done
            if name in (".password", "known_hosts"):
                dst.chmod(0o600)

        if read_current_account() is None:
            write_current_account(DEFAULT_ACCOUNT)

        self._rewrite_ssh_config_path(old_known_hosts, new_known_hosts)
        logger.info("Migrated legacy layout to accounts/default")
        return True

    def _rewrite_ssh_config_path(self, old_path: Path, new_path: Path) -> None:
        """Point existing ~/.ssh/config Host blocks at the migrated file.

        v0.2.4 wrote the absolute known_hosts path into the user's Host
        block; without this rewrite, direct `ssh <alias>` would silently
        re-TOFU against a missing file.
        """
        ssh_config = Path.home() / ".ssh" / "config"
        if not ssh_config.exists():
            return
        try:
            content = ssh_config.read_text(encoding="utf-8")
            needle = f"UserKnownHostsFile {old_path}"
            if needle not in content:
                return
            ssh_config.write_text(
                content.replace(needle, f"UserKnownHostsFile {new_path}"),
                encoding="utf-8",
            )
            logger.info("Rewrote UserKnownHostsFile path in ~/.ssh/config")
        except OSError as e:
            logger.warning(f"Could not rewrite ~/.ssh/config: {e}")

    def config_exists(self) -> bool:
        """Check if configuration file exists"""
        return self.config_file.exists()

    def load_config(self) -> CpolarConfig:
        """Load and validate configuration from file"""
        if not self.config_exists():
            raise ConfigError(_("error.config_not_found", path=self.config_file))

        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                config_data = json.load(f)

            self._config = CpolarConfig(**config_data)
            return self._config

        except json.JSONDecodeError as e:
            raise ConfigError(_("error.config_invalid_json", error=e))
        except Exception as e:
            raise ConfigError(_("error.config_load_failed", error=e))

    def save_config(self, config: CpolarConfig) -> None:
        """Save configuration to file"""
        try:
            self._ensure_account_dir()
            config_data = config.model_dump()

            # Write to temp file first, then rename (atomic write)
            temp_file = self.config_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=2)

            temp_file.replace(self.config_file)
            self._config = config

        except Exception as e:
            raise ConfigError(_("error.config_save_failed", error=e))

    def create_config(self, config_data: Dict[str, Any]) -> CpolarConfig:
        """Create and save initial configuration"""
        try:
            config = CpolarConfig(**config_data)
            self.save_config(config)
            return config

        except Exception as e:
            raise ConfigError(_("error.config_create_failed", error=e))

    def get_config(self) -> CpolarConfig:
        """Get current configuration, loading if necessary"""
        if self._config is None:
            self._config = self.load_config()
        return self._config

    def get(self, key: str, default: Any = _MISSING) -> Any:
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
                return getattr(config, key.replace(".", "_"))
            except AttributeError:
                if default is not _MISSING:
                    return default
                raise KeyError(_("error.config_key_not_found", key=key))

    def set(self, key: str, value: Any) -> None:
        """Set configuration value and save"""
        config = self.get_config()
        config_dict = config.model_dump()

        # Update the value
        if key == "cpolar.username":
            config_dict["username"] = value
        elif key == "cpolar.base_url":
            config_dict["base_url"] = value
        elif key == "server.user":
            config_dict["server_user"] = value
        elif key == "server.ports":
            # Handle comma-separated ports
            if isinstance(value, list):
                config_dict["ports"] = value
            elif isinstance(value, str):
                # Parse comma-separated string
                try:
                    config_dict["ports"] = [int(p.strip()) for p in value.split(",")]
                except ValueError:
                    raise ConfigError(
                        f"Invalid port value: {value}. Must be numbers separated by commas."
                    )
            else:
                config_dict["ports"] = [int(value)]
        elif key == "server.auto_connect":
            # Handle boolean values properly
            if isinstance(value, bool):
                config_dict["auto_connect"] = value
            elif isinstance(value, str):
                value_lower = value.lower()
                if value_lower in ["true", "yes", "1", "on"]:
                    config_dict["auto_connect"] = True
                elif value_lower in ["false", "no", "0", "off"]:
                    config_dict["auto_connect"] = False
                else:
                    raise ConfigError(
                        f"Invalid boolean value: {value}. Use 'true' or 'false'."
                    )
            else:
                config_dict["auto_connect"] = bool(value)
        elif key == "ssh.key_path":
            config_dict["ssh_key_path"] = value
        elif key == "ssh.host_alias":
            config_dict["ssh_host_alias"] = value
        elif key == "ssh.key_size":
            # Handle integer value with error checking
            try:
                config_dict["ssh_key_size"] = int(value)
            except (ValueError, TypeError):
                raise ConfigError(f"Invalid key size: {value}. Must be an integer.")
        elif key == "log_level":
            # Validate log level
            valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
            value_upper = str(value).upper()
            if value_upper in valid_levels:
                config_dict["log_level"] = value_upper
            else:
                raise ConfigError(
                    f"Invalid log level: {value}. Must be one of: {', '.join(valid_levels)}"
                )
        else:
            # Try direct attribute
            attr_name = key.replace(".", "_")
            if hasattr(config, attr_name):
                config_dict[attr_name] = value
            else:
                raise KeyError(_("error.config_key_not_found", key=key))

        # Alias uniqueness across accounts (host key trust model)
        new_alias = config_dict.get("ssh_host_alias")
        if new_alias and new_alias != config.ssh_host_alias:
            conflict = self.find_alias_conflict(new_alias)
            if conflict:
                raise ConfigError(
                    _("error.alias_conflict", alias=new_alias, other=conflict)
                )

        # Create new config and save
        try:
            updated_config = CpolarConfig(**config_dict)
        except ValidationError as e:
            raise ConfigError(_("config.invalid", error=e))
        self.save_config(updated_config)

    def edit(self) -> None:
        """Open configuration file in a reasonable editor per platform"""
        if not self.config_exists():
            raise ConfigError(_("cli.no_config"))

        editor = os.environ.get("EDITOR")
        argv = None
        if editor:
            argv = [editor, str(self.config_file)]
        else:
            import platform

            system = platform.system()
            if system == "Darwin":
                argv = ["open", "-e", str(self.config_file)]
            elif system == "Windows":
                argv = ["notepad", str(self.config_file)]
            else:
                argv = ["nano", str(self.config_file)]

        try:
            subprocess.run(argv, check=True)
            # Reload config after editing
            self._config = None
        except subprocess.CalledProcessError as e:
            raise ConfigError(_("error.config_edit_failed", error=e))
        except FileNotFoundError:
            raise ConfigError(_("error.editor_not_found", editor=argv[0]))

    def get_display_data(self) -> Dict[str, Any]:
        """Get configuration data for display"""
        config = self.get_config()
        password_status = self._get_password_status(config.username)
        return {
            "account": self.account,
            "username": config.username,
            "base_url": config.base_url,
            "server_user": config.server_user,
            "ports": config.ports,
            "auto_connect": config.auto_connect,
            "ssh_key_path": config.ssh_key_path,
            "ssh_host_alias": config.ssh_host_alias,
            "ssh_key_size": config.ssh_key_size,
            "log_level": config.log_level,
            "language": config.language,
            "password_status": password_status,
            "config_dir": str(self.account_dir),
        }

    def _get_password_status(self, username: str) -> str:
        """Get password storage status key for i18n"""
        if os.getenv("CPOLAR_PASSWORD"):
            return "env"
        if self.password_file.exists():
            return "file"
        return "none"

    def get_password(self, username: str) -> Optional[str]:
        """Get password from environment variable or password file.

        Priority:
        1. CPOLAR_PASSWORD environment variable
        2. Password stored in the account's .password file
        """
        # Try environment variable first
        password = os.getenv("CPOLAR_PASSWORD")
        if password:
            return password

        # Try password file
        if self.password_file.exists():
            try:
                return self.password_file.read_text(encoding="utf-8").strip()
            except Exception as e:
                logger.debug(f"Failed to read password file: {e}")
                return None

        return None

    def set_password(self, username: str, password: str) -> None:
        """Store password in a file created with owner-only permissions"""
        try:
            self._ensure_account_dir()
            # O_CREAT with mode 0o600 avoids a transient window where the
            # file exists with umask-default (possibly world-readable) bits
            fd = os.open(
                self.password_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(password)
            # Normalize permissions for files created by older versions
            self.password_file.chmod(0o600)
        except Exception as e:
            raise ConfigError(_("error.password_store_failed", error=e))

    def has_stored_password(self, username: str) -> bool:
        """Check if password is stored"""
        if os.getenv("CPOLAR_PASSWORD"):
            return True
        return self.password_file.exists()

    def clear_password(self, username: str) -> bool:
        """Clear stored password file.

        Returns:
            True if password was cleared, False if no password was stored
        """
        if not self.password_file.exists():
            return False
        try:
            self.password_file.unlink()
            return True
        except Exception as e:
            raise ConfigError(_("error.password_clear_failed", error=e))

    def clear_host_keys(self) -> bool:
        """Remove stored server host keys.

        Returns:
            True if host keys were cleared, False if none were stored
        """
        if not self.known_hosts_file.exists():
            return False
        try:
            self.known_hosts_file.unlink()
            return True
        except OSError as e:
            raise ConfigError(_("error.hostkey_clear_failed", error=e))

    @property
    def config_path(self) -> Path:
        """Get configuration file path"""
        return self.config_file

    @property
    def logs_path(self) -> Path:
        """Get logs directory path"""
        return self.logs_dir
