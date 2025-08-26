"""
Git provider framework for the MCP Code Expert Server.

This package provides a pluggable framework for supporting different Git hosting
providers (GitHub, GitLab, Bitbucket, etc.) through a common interface.

The framework consists of:
- GitProvider: Abstract base class defining the provider interface
- GitHubProvider: GitHub implementation
- AzureDevOpsProvider: Azure DevOps implementation
- ProviderRegistry: Central registry for managing providers
- Utility functions for common operations

Example usage:
    >>> from code_expert.repository.providers import get_provider, get_default_registry
    >>> 
    >>> # Get provider for a specific URL
    >>> provider = get_provider("https://github.com/owner/repo")
    >>> if provider:
    ...     components = provider.parse_url("https://github.com/owner/repo")
    ...     print(f"Owner: {components['owner']}, Repo: {components['repo']}")
    >>> 
    >>> # Register a custom provider
    >>> registry = get_default_registry()
    >>> registry.register_provider(MyCustomProvider())
"""

from .base import GitProvider
from .github import GitHubProvider
from .azure_devops import AzureDevOpsProvider
from .registry import ProviderRegistry, get_default_registry, register_provider, get_provider

__all__ = [
    # Core classes
    'GitProvider',
    'GitHubProvider',
    'AzureDevOpsProvider', 
    'ProviderRegistry',
    
    # Utility functions
    'get_default_registry',
    'register_provider',
    'get_provider',
]

# Version information
__version__ = '1.0.0'