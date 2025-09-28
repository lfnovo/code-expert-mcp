"""
Code Understanding MCP Server - A modular server for codebase analysis and context generation.
"""

from .config import ServerConfig, load_config
from .logging_config import logger, setup_logging

__version__ = "0.1.0"

# Load config and set up logging when the module is imported
config = load_config()
setup_logging(config)
