"""
Cpolar Connect - Easy-to-use CLI tool for cpolar tunnel management and SSH connections
"""

__version__ = "0.2.2"
__author__ = "Hoper_J"
__email__ = "hoper.hw@gmail.com"

from .config import ConfigError, ConfigManager, CpolarConfig

__all__ = [
    "ConfigManager",
    "CpolarConfig",
    "ConfigError",
    "__version__",
]
