"""
Azure DevOps provider implementation.

This module implements the GitProvider interface for Azure DevOps repositories,
supporting various URL formats and authentication methods.
"""

import hashlib
from pathlib import Path
from typing import Dict, Any, Optional
from urllib.parse import urlparse

from .base import GitProvider


class AzureDevOpsProvider(GitProvider):
    """Azure DevOps implementation of the GitProvider interface.
    
    Supports multiple Azure DevOps URL formats:
    - https://dev.azure.com/{organization}/{project}/_git/{repository}
    - https://{organization}@dev.azure.com/{organization}/{project}/_git/{repository}
    - git@ssh.dev.azure.com:v3/{organization}/{project}/{repository}
    
    Also handles URLs with .git extension and optional refs.
    """

    def is_provider_url(self, url: str) -> bool:
        """Check if the given URL is an Azure DevOps URL.
        
        Args:
            url: The URL to check
            
        Returns:
            bool: True if this is an Azure DevOps URL, False otherwise
            
        Examples:
            >>> provider = AzureDevOpsProvider()
            >>> provider.is_provider_url("https://dev.azure.com/org/project/_git/repo")
            True
            >>> provider.is_provider_url("git@ssh.dev.azure.com:v3/org/project/repo")
            True
            >>> provider.is_provider_url("https://github.com/owner/repo")
            False
        """
        if not url:
            return False

        # Handle SSH URLs
        if url.startswith("git@ssh.dev.azure.com:v3/"):
            # Must have organization/project/repository format
            path = url[len("git@ssh.dev.azure.com:v3/"):]
            parts = path.split("/")
            return len(parts) >= 3 and all(part for part in parts[:3])

        # Handle HTTPS URLs
        try:
            parsed = urlparse(url)
            if parsed.scheme in ("http", "https") and parsed.netloc.endswith("dev.azure.com"):
                # Check for valid Azure DevOps path pattern
                path_parts = parsed.path.strip("/").split("/")
                
                # Format 1: organization/project/_git/repository (explicit repo)
                if (len(path_parts) >= 4 and 
                    bool(path_parts[0]) and  # organization
                    bool(path_parts[1]) and  # project
                    path_parts[2] == "_git" and
                    bool(path_parts[3])):  # repository
                    return True
                
                # Format 2: organization/project (repo defaults to project name)
                # But reject if it has _git without a repo or has 3+ parts without _git
                if (len(path_parts) == 2 and 
                    bool(path_parts[0]) and  # organization
                    bool(path_parts[1])):  # project
                    return True
                    
            return False
        except Exception:
            return False

    def parse_url(self, url: str) -> Dict[str, Any]:
        """Parse an Azure DevOps URL into its components.
        
        Args:
            url: The Azure DevOps URL to parse
            
        Returns:
            Dict[str, Any]: Dictionary containing:
                - 'organization': Azure DevOps organization
                - 'project': Project name
                - 'repo': Repository name  
                - 'ref': Optional reference (branch, tag, commit)
                - 'raw_url': Original URL
                
        Raises:
            ValueError: If the URL is invalid or cannot be parsed
            
        Examples:
            >>> provider = AzureDevOpsProvider()
            >>> provider.parse_url("https://dev.azure.com/myorg/myproject/_git/myrepo")
            {'organization': 'myorg', 'project': 'myproject', 'repo': 'myrepo', 'ref': None, 'raw_url': '...'}
        """
        if not self.is_provider_url(url):
            raise ValueError(f"Not an Azure DevOps URL: {url}")

        # Handle SSH URLs
        if url.startswith("git@ssh.dev.azure.com:v3/"):
            path = url.split("git@ssh.dev.azure.com:v3/")[1]
            parts = path.split("/")
            if len(parts) < 3:
                raise ValueError(f"Invalid Azure DevOps SSH URL: {url}")
            
            organization = parts[0]
            project = parts[1]
            repo_part = parts[2]
            
            # Handle .git extension
            if repo_part.endswith(".git"):
                repo = repo_part[:-4]
            else:
                repo = repo_part
                
            # Check for ref (branch, tag, commit)
            ref = None
            if len(parts) > 3:
                ref = "/".join(parts[3:])
                
        else:
            # Handle HTTPS URLs
            parsed = urlparse(url)
            path = parsed.path.lstrip("/")
            parts = path.split("/")
            
            # Format 1: organization/project/_git/repository
            if len(parts) >= 4 and parts[2] == "_git":
                organization = parts[0]
                project = parts[1]
                repo_part = parts[3]
            # Format 2: organization/project (repo defaults to project name)
            elif len(parts) == 2:
                organization = parts[0]
                project = parts[1]
                repo_part = project  # Default repo name to project name
            else:
                raise ValueError(f"Invalid Azure DevOps HTTPS URL: {url}")
            
            # Handle .git extension
            if repo_part.endswith(".git"):
                repo = repo_part[:-4]
            else:
                repo = repo_part
                
            # Check for ref (branch, tag, commit)
            ref = None
            # For format 1 (with _git), ref starts at index 4
            if len(parts) >= 4 and parts[2] == "_git" and len(parts) > 4:
                ref = "/".join(parts[4:])
            # For format 2 (without _git), ref starts at index 2 (but skip if index 2 exists)
            elif len(parts) > 2 and (len(parts) < 3 or parts[2] != "_git"):
                # Don't treat the second part as ref for short format
                pass

        return {
            'organization': organization,
            'project': project,
            'repo': repo,
            'ref': ref,
            'raw_url': url
        }

    def get_cache_path(
        self, 
        cache_dir: Path, 
        components: Dict[str, Any], 
        branch: Optional[str] = None, 
        per_branch: bool = False
    ) -> Path:
        """Generate a cache path for an Azure DevOps repository.
        
        Args:
            cache_dir: Base cache directory
            components: URL components from parse_url()
            branch: Branch name (only used if per_branch=True)
            per_branch: If True, creates separate cache entries per branch
            
        Returns:
            Path: Deterministic cache path for the repository
            
        Examples:
            cache/azure/org/project/repo-12345678 (shared strategy)
            cache/azure/org/project/repo-main-87654321 (per-branch strategy)
        """
        # Ensure cache_dir is absolute
        cache_dir = Path(cache_dir).resolve()
        
        organization = components['organization']
        project = components['project']
        repo = components['repo']
        raw_url = components['raw_url']

        # Sanitize names for use in filesystem paths
        safe_org = self._sanitize_path_component(organization)
        safe_project = self._sanitize_path_component(project)
        safe_repo = self._sanitize_path_component(repo)

        # Sanitize branch name for use in filesystem paths
        safe_branch = None
        if branch and per_branch:
            safe_branch = self._sanitize_path_component(branch)

        # Include branch in hash if per_branch strategy
        if per_branch and safe_branch:
            url_with_branch = f"{raw_url}@{branch}"  # Use original branch for hash consistency
            url_hash = hashlib.sha256(url_with_branch.encode()).hexdigest()[:8]
            # Include sanitized branch name in path for clarity
            return (cache_dir / "azure" / safe_org / safe_project / f"{safe_repo}-{safe_branch}-{url_hash}").resolve()
        else:
            # Shared strategy - same path regardless of branch
            url_hash = hashlib.sha256(raw_url.encode()).hexdigest()[:8]
            return (cache_dir / "azure" / safe_org / safe_project / f"{safe_repo}-{url_hash}").resolve()

    def _sanitize_path_component(self, component: str) -> str:
        """Sanitize a path component for filesystem use.
        
        Args:
            component: The component to sanitize
            
        Returns:
            str: Sanitized component safe for filesystem paths
        """
        # Replace problematic characters for filesystem paths
        return component.replace('/', '-').replace('\\', '-').replace(':', '-').replace(' ', '_')

    def get_authenticated_url(self, url: str, token: Optional[str] = None) -> str:
        """Get an authenticated URL for Azure DevOps cloning.
        
        Args:
            url: Original Azure DevOps repository URL
            token: Azure DevOps Personal Access Token (if available)
            
        Returns:
            str: URL that can be used for authenticated operations
            
        Examples:
            >>> provider = AzureDevOpsProvider()
            >>> provider.get_authenticated_url("https://dev.azure.com/org/project/_git/repo", "pat123")
            "https://pat123@dev.azure.com/org/project/_git/repo"
            >>> provider.get_authenticated_url("https://dev.azure.com/org/project", "pat123")
            "https://pat123@dev.azure.com/org/project/_git/project"
        """
        if not self.is_provider_url(url):
            return url
            
        # Parse the URL to get components
        try:
            components = self.parse_url(url)
        except ValueError:
            return url
            
        organization = components['organization']
        project = components['project']
        repo = components['repo']
        
        # Convert SSH URLs to HTTPS for token authentication
        if url.startswith("git@ssh.dev.azure.com:v3/"):
            # Ensure .git extension for consistency
            if not repo.endswith(".git"):
                repo = repo + ".git"
            # Always use full format with _git for cloning
            if token:
                return f"https://{token}@dev.azure.com/{organization}/{project}/_git/{repo}"
            else:
                return f"https://dev.azure.com/{organization}/{project}/_git/{repo}"
        
        # Handle HTTPS URLs
        parsed = urlparse(url)
        if parsed.netloc.endswith("dev.azure.com"):
            # Remove any existing authentication from the URL
            clean_netloc = parsed.netloc
            if "@" in clean_netloc:
                clean_netloc = clean_netloc.split("@")[-1]
                
            # Check if it's a short format URL (no _git component)
            path_parts = parsed.path.strip("/").split("/")
            if len(path_parts) == 2:  # Short format: org/project
                # Convert to full format for cloning
                if token:
                    return f"https://{token}@{clean_netloc}/{organization}/{project}/_git/{repo}"
                else:
                    return f"https://{clean_netloc}/{organization}/{project}/_git/{repo}"
            else:
                # Already in full format, just add token if provided
                if token:
                    return f"https://{token}@{clean_netloc}{parsed.path}"
                else:
                    return url
            
        return url

    def get_provider_name(self) -> str:
        """Get the name of this provider.
        
        Returns:
            str: "Azure DevOps"
        """
        return "Azure DevOps"

    def get_env_var_name(self) -> str:
        """Get the environment variable name for Azure DevOps authentication.
        
        Returns:
            str: "AZURE_DEVOPS_PAT"
        """
        return "AZURE_DEVOPS_PAT"