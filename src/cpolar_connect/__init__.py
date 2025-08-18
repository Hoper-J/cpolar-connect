"""
Cpolar Connect - Easy-to-use CLI tool for cpolar tunnel management and SSH connections
"""

__version__ = "0.0.1"
__author__ = "Your Name"
__email__ = "your.email@example.com"

from .config import ConfigManager, CpolarConfig, ConfigError

__all__ = [
    "ConfigManager",
    "CpolarConfig", 
    "ConfigError",
    "__version__",
]