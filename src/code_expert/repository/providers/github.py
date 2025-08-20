"""
GitHub provider implementation.

This module implements the GitProvider interface for GitHub repositories,
extracting logic from path_utils.py and manager.py.
"""

import hashlib
from pathlib import Path
from typing import Dict, Any, Optional
from urllib.parse import urlparse

from .base import GitProvider


class GitHubProvider(GitProvider):
    """GitHub implementation of the GitProvider interface."""

    def is_provider_url(self, url: str) -> bool:
        """Check if the given URL is a GitHub URL.
        
        Args:
            url: The URL to check
            
        Returns:
            bool: True if this is a GitHub URL, False otherwise
        """
        if not url:
            return False

        # Handle SSH URLs
        if url.startswith("git@github.com:"):
            # Must have something after the colon
            path = url[len("git@github.com:"):]
            return bool(path and "/" in path)  # Must have owner/repo format

        # Handle HTTPS URLs
        try:
            parsed = urlparse(url)
            # Must be github.com AND have a path with at least owner/repo
            if parsed.scheme in ("http", "https") and parsed.netloc == "github.com":
                # Check if there's a valid path (at least /owner/repo)
                path_parts = parsed.path.strip("/").split("/")
                return len(path_parts) >= 2 and path_parts[0] and path_parts[1]
            return False
        except Exception:
            return False

    def parse_url(self, url: str) -> Dict[str, Any]:
        """Parse a GitHub URL into its components.
        
        Args:
            url: The GitHub URL to parse
            
        Returns:
            Dict[str, Any]: Dictionary containing:
                - 'owner': Repository owner/organization
                - 'repo': Repository name  
                - 'ref': Optional reference (branch, tag, commit)
                - 'raw_url': Original URL
                
        Raises:
            ValueError: If the URL is invalid or cannot be parsed
        """
        if not self.is_provider_url(url):
            raise ValueError(f"Not a GitHub URL: {url}")

        # Handle SSH URLs
        if url.startswith("git@github.com:"):
            path = url.split("git@github.com:")[1]
        else:
            # Handle HTTPS URLs
            parsed = urlparse(url)
            path = parsed.path.lstrip("/")

        # Split path into parts
        parts = path.split("/")
        if len(parts) < 2:
            raise ValueError(f"Invalid GitHub URL: {url}")

        owner = parts[0]

        # Handle .git extension and refs
        repo_part = parts[1]
        if repo_part.endswith(".git"):
            repo = repo_part[:-4]
        else:
            repo = repo_part

        # Check for ref (branch, tag, commit)
        ref = None
        if len(parts) > 2:
            ref = "/".join(parts[2:])

        return {
            'owner': owner,
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
        """Generate a cache path for a GitHub repository.
        
        Args:
            cache_dir: Base cache directory
            components: URL components from parse_url()
            branch: Branch name (only used if per_branch=True)
            per_branch: If True, creates separate cache entries per branch
            
        Returns:
            Path: Deterministic cache path for the repository
            
        Examples:
            cache/github/owner/repo-12345678 (shared strategy)
            cache/github/owner/repo-main-87654321 (per-branch strategy)
        """
        # Ensure cache_dir is absolute
        cache_dir = Path(cache_dir).resolve()
        
        owner = components['owner']
        repo = components['repo']
        raw_url = components['raw_url']

        # Sanitize branch name for use in filesystem paths
        safe_branch = None
        if branch and per_branch:
            # Replace problematic characters in branch names
            safe_branch = branch.replace('/', '-').replace('\\', '-').replace(':', '-')

        # Include branch in hash if per_branch strategy
        if per_branch and safe_branch:
            url_with_branch = f"{raw_url}@{branch}"  # Use original branch for hash consistency
            url_hash = hashlib.sha256(url_with_branch.encode()).hexdigest()[:8]
            # Include sanitized branch name in path for clarity
            return (cache_dir / "github" / owner / f"{repo}-{safe_branch}-{url_hash}").resolve()
        else:
            # Shared strategy - same path regardless of branch
            url_hash = hashlib.sha256(raw_url.encode()).hexdigest()[:8]
            return (cache_dir / "github" / owner / f"{repo}-{url_hash}").resolve()

    def get_authenticated_url(self, url: str, token: Optional[str] = None) -> str:
        """Get an authenticated URL for GitHub cloning.
        
        Args:
            url: Original GitHub repository URL
            token: GitHub personal access token (if available)
            
        Returns:
            str: URL that can be used for authenticated operations
        """
        if not token or not self.is_provider_url(url):
            return url
            
        # Convert SSH URLs to HTTPS for token authentication
        if url.startswith("git@github.com:"):
            path = url.split("git@github.com:")[1]
            # Ensure .git extension for consistency
            if not path.endswith(".git"):
                path = path + ".git"
            return f"https://{token}@github.com/{path}"
        
        # Handle HTTPS URLs
        parsed = urlparse(url)
        if parsed.hostname == "github.com":
            return f"https://{token}@github.com{parsed.path}"
            
        return url

    def get_provider_name(self) -> str:
        """Get the name of this provider.
        
        Returns:
            str: "GitHub"
        """
        return "GitHub"

    def get_env_var_name(self) -> str:
        """Get the environment variable name for GitHub authentication.
        
        Returns:
            str: "GITHUB_PERSONAL_ACCESS_TOKEN"
        """
        return "GITHUB_PERSONAL_ACCESS_TOKEN"