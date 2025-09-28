"""
Provider registry for managing Git hosting providers.

This module provides a centralized registry for managing different Git hosting
providers and automatically detecting which provider to use for a given URL.
"""

import os
from typing import Dict, List, Optional

from .base import GitProvider
from .github import GitHubProvider
from .azure_devops import AzureDevOpsProvider


class ProviderRegistry:
    """Registry for managing Git hosting providers.
    
    This class provides a centralized way to register and discover Git providers
    based on URLs. It automatically detects which provider to use and provides
    a unified interface for Git operations across different hosting services.
    """

    def __init__(self):
        """Initialize the registry with default providers."""
        self._providers: List[GitProvider] = []
        self._register_default_providers()

    def _register_default_providers(self) -> None:
        """Register the default built-in providers."""
        self.register_provider(GitHubProvider())
        self.register_provider(AzureDevOpsProvider())

    def register_provider(self, provider: GitProvider) -> None:
        """Register a new Git provider.
        
        Args:
            provider: The GitProvider instance to register
            
        Raises:
            TypeError: If provider is not a GitProvider instance
        """
        if not isinstance(provider, GitProvider):
            raise TypeError(f"Provider must be a GitProvider instance, got {type(provider)}")
        
        self._providers.append(provider)

    def get_provider(self, url: str) -> Optional[GitProvider]:
        """Get the appropriate provider for a given URL.
        
        Args:
            url: The repository URL to find a provider for
            
        Returns:
            GitProvider: The provider that can handle this URL, or None if no provider found
            
        Examples:
            >>> registry = ProviderRegistry()
            >>> provider = registry.get_provider("https://github.com/owner/repo")
            >>> provider.get_provider_name()
            "GitHub"
        """
        for provider in self._providers:
            if provider.is_provider_url(url):
                return provider
        return None

    def get_providers(self) -> List[GitProvider]:
        """Get all registered providers.
        
        Returns:
            List[GitProvider]: List of all registered providers
        """
        return self._providers.copy()

    def get_provider_by_name(self, name: str) -> Optional[GitProvider]:
        """Get a provider by its name.
        
        Args:
            name: The provider name to search for
            
        Returns:
            GitProvider: The provider with the given name, or None if not found
        """
        for provider in self._providers:
            if provider.get_provider_name().lower() == name.lower():
                return provider
        return None

    def is_supported_url(self, url: str) -> bool:
        """Check if any registered provider can handle the given URL.
        
        Args:
            url: The URL to check
            
        Returns:
            bool: True if a provider can handle this URL, False otherwise
        """
        return self.get_provider(url) is not None

    def get_authenticated_url(self, url: str) -> str:
        """Get an authenticated URL using the appropriate provider.
        
        This method automatically detects the provider for the URL and uses
        the corresponding environment variable for authentication.
        
        Args:
            url: The repository URL
            
        Returns:
            str: Authenticated URL if possible, original URL otherwise
        """
        provider = self.get_provider(url)
        if not provider:
            return url
            
        token = os.environ.get(provider.get_env_var_name())
        return provider.get_authenticated_url(url, token)

    def parse_url(self, url: str) -> Optional[Dict]:
        """Parse a URL using the appropriate provider.
        
        Args:
            url: The repository URL to parse
            
        Returns:
            Dict: Parsed URL components, or None if no provider can handle the URL
        """
        provider = self.get_provider(url)
        if not provider:
            return None
            
        try:
            return provider.parse_url(url)
        except ValueError:
            return None


# Global registry instance
_default_registry = ProviderRegistry()


def get_default_registry() -> ProviderRegistry:
    """Get the default global provider registry.
    
    Returns:
        ProviderRegistry: The default registry instance
    """
    return _default_registry


def register_provider(provider: GitProvider) -> None:
    """Register a provider with the default registry.
    
    Args:
        provider: The GitProvider instance to register
    """
    _default_registry.register_provider(provider)


def get_provider(url: str) -> Optional[GitProvider]:
    """Get the appropriate provider for a URL from the default registry.
    
    Args:
        url: The repository URL
        
    Returns:
        GitProvider: The provider that can handle this URL, or None if no provider found
    """
    return _default_registry.get_provider(url)