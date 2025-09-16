"""
Cpolar Connect - Easy-to-use CLI tool for cpolar tunnel management and SSH connections
"""

__version__ = "0.1.1"
__author__ = "Hoper_J"
__email__ = "hoper.hw@gmail.com"

from .config import ConfigManager, CpolarConfig, ConfigError

__all__ = [
    "ConfigManager",
    "CpolarConfig", 
    "ConfigError",
    "__version__",
]
