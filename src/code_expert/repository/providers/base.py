"""
Abstract base class for Git providers.

This module defines the interface that all Git hosting providers must implement
to be compatible with the MCP Code Expert Server.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, Optional


class GitProvider(ABC):
    """Abstract base class for Git hosting providers.
    
    This class defines the interface that all Git providers must implement
    to support different Git hosting services (GitHub, GitLab, Bitbucket, etc.).
    """

    @abstractmethod
    def is_provider_url(self, url: str) -> bool:
        """Check if the given URL belongs to this provider.
        
        Args:
            url: The URL to check
            
        Returns:
            bool: True if this provider can handle the URL, False otherwise
            
        Examples:
            >>> provider = GitHubProvider()
            >>> provider.is_provider_url("https://github.com/owner/repo")
            True
            >>> provider.is_provider_url("git@github.com:owner/repo.git")
            True
            >>> provider.is_provider_url("https://gitlab.com/owner/repo")
            False
        """
        pass

    @abstractmethod
    def parse_url(self, url: str) -> Dict[str, Any]:
        """Parse a provider URL into its components.
        
        Args:
            url: The URL to parse
            
        Returns:
            Dict[str, Any]: Dictionary containing URL components like:
                - 'owner': Repository owner/organization
                - 'repo': Repository name
                - 'ref': Optional reference (branch, tag, commit)
                - 'raw_url': Original URL
                
        Raises:
            ValueError: If the URL is invalid or cannot be parsed
            
        Examples:
            >>> provider = GitHubProvider()
            >>> provider.parse_url("https://github.com/owner/repo")
            {'owner': 'owner', 'repo': 'repo', 'ref': None, 'raw_url': '...'}
        """
        pass

    @abstractmethod
    def get_cache_path(
        self, 
        cache_dir: Path, 
        components: Dict[str, Any], 
        branch: Optional[str] = None, 
        per_branch: bool = False
    ) -> Path:
        """Generate a cache path for a repository.
        
        Args:
            cache_dir: Base cache directory
            components: URL components from parse_url()
            branch: Branch name (only used if per_branch=True)
            per_branch: If True, creates separate cache entries per branch
            
        Returns:
            Path: Deterministic cache path for the repository
            
        Examples:
            >>> provider = GitHubProvider()
            >>> components = {'owner': 'org', 'repo': 'repo', 'ref': None}
            >>> provider.get_cache_path(Path('/cache'), components)
            Path('/cache/github/org/repo-12345678')
        """
        pass

    @abstractmethod
    def get_authenticated_url(self, url: str, token: Optional[str] = None) -> str:
        """Get an authenticated URL for cloning.
        
        Args:
            url: Original repository URL
            token: Authentication token (if available)
            
        Returns:
            str: URL that can be used for authenticated operations
            
        Examples:
            >>> provider = GitHubProvider()
            >>> provider.get_authenticated_url("https://github.com/owner/repo", "token123")
            "https://token123@github.com/owner/repo"
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Get the name of this provider.
        
        Returns:
            str: Human-readable provider name
            
        Examples:
            >>> provider = GitHubProvider()
            >>> provider.get_provider_name()
            "GitHub"
        """
        pass

    @abstractmethod
    def get_env_var_name(self) -> str:
        """Get the environment variable name for the authentication token.
        
        Returns:
            str: Environment variable name containing the auth token
            
        Examples:
            >>> provider = GitHubProvider()
            >>> provider.get_env_var_name()
            "GITHUB_PERSONAL_ACCESS_TOKEN"
        """
        pass