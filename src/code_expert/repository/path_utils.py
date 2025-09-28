"""
Repository path handling utilities.

This module provides path utilities for repository handling with support for multiple
Git hosting providers through the provider registry. All functions maintain backwards
compatibility with existing code that imports them.

Backwards Compatibility:
- All function signatures remain exactly the same
- parse_github_url() continues to work for GitHub URLs only (as expected)
- is_git_url() now supports all registered providers (GitHub, Azure DevOps, etc.)
- get_cache_path() delegates to the appropriate provider when possible
- Falls back to original behavior when no provider matches
"""

import hashlib
import logging
from pathlib import Path
from typing import Tuple, Optional
from urllib.parse import urlparse

try:
    # Import provider registry - graceful fallback if providers module is not available
    from .providers import get_default_registry, get_provider
    _PROVIDERS_AVAILABLE = True
except ImportError:
    _PROVIDERS_AVAILABLE = False

# Set up logging
logger = logging.getLogger(__name__)


def is_git_url(path: str) -> bool:
    """Check if a path is a Git URL.
    
    Now supports all registered providers (GitHub, Azure DevOps, etc.) through
    the provider registry. Falls back to original logic if providers unavailable.
    
    Args:
        path: The path/URL to check
        
    Returns:
        bool: True if the path is recognized as a Git URL by any provider
    """
    if not path:
        return False

    logger.debug(f"Checking if path is git URL: {path}")
    
    # First check if it's a local path (not a URL)
    # Local paths should not be considered Git URLs
    if not path.startswith(('http://', 'https://', 'git@', 'ssh://')):
        # Check if it looks like a local path
        try:
            from pathlib import Path
            # If it can be resolved as a path and doesn't have URL characteristics, it's local
            if Path(path).exists() or '://' not in path:
                logger.debug(f"Path appears to be local, not a Git URL: {path}")
                return False
        except Exception:
            pass

    # Use provider registry if available
    if _PROVIDERS_AVAILABLE:
        try:
            registry = get_default_registry()
            is_supported = registry.is_supported_url(path)
            logger.debug(f"Provider registry result for '{path}': {is_supported}")
            if is_supported:
                return True
        except Exception as e:
            logger.warning(f"Provider registry check failed for '{path}': {e}")
            # Continue to fallback logic
    
    # Fallback to original logic for backwards compatibility
    # This ensures existing behavior is maintained if providers fail
    logger.debug(f"Using fallback logic for '{path}'")
    
    # Handle SSH URLs
    if path.startswith("git@"):
        logger.debug(f"Detected SSH URL: {path}")
        return True

    # Handle HTTPS URLs
    try:
        parsed = urlparse(path)
        is_git = parsed.scheme in ("http", "https") and (
            parsed.netloc == "github.com" or "git" in parsed.netloc
        )
        logger.debug(f"HTTPS URL check for '{path}': {is_git}")
        return is_git
    except Exception as e:
        logger.debug(f"URL parsing failed for '{path}': {e}")
        return False


def parse_github_url(url: str) -> Tuple[str, str, Optional[str]]:
    """Parse a GitHub URL into org, repo, and optional ref.
    
    This function maintains exact backwards compatibility and only handles GitHub URLs.
    It does NOT use the provider registry intentionally, to preserve existing behavior
    for code that specifically expects GitHub URL parsing.
    
    Args:
        url: GitHub URL to parse
        
    Returns:
        Tuple of (org, repo, ref) where ref is optional
        
    Raises:
        ValueError: If the URL is not a valid GitHub URL
    """
    logger.debug(f"Parsing GitHub URL (backwards compatibility): {url}")
    
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

    org = parts[0]

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

    logger.debug(f"Parsed GitHub URL '{url}' -> org='{org}', repo='{repo}', ref='{ref}'")
    return org, repo, ref


def get_cache_path(cache_dir: Path, repo_path: str, branch: Optional[str] = None, per_branch: bool = False) -> Path:
    """Get deterministic cache path for a repository.
    
    Now delegates to the appropriate provider when possible (GitHub, Azure DevOps, etc.)
    while maintaining full backwards compatibility. Falls back to original logic
    when no provider matches.
    
    Args:
        cache_dir: Base cache directory
        repo_path: Repository URL or path
        branch: Branch name (only used if per_branch=True)
        per_branch: If True, creates separate cache entries per branch
        
    Returns:
        Path: Deterministic cache path for the repository
        
    Examples:
        # Shared strategy (default) - same path regardless of branch
        get_cache_path(cache, "https://github.com/org/repo") 
        get_cache_path(cache, "https://github.com/org/repo", branch="main")
        get_cache_path(cache, "https://github.com/org/repo", branch="feature")
        # All return: cache/github/org/repo-12345678
        
        # Per-branch strategy - different paths for different branches
        get_cache_path(cache, "https://github.com/org/repo", branch="main", per_branch=True)
        # Returns: cache/github/org/repo-main-87654321
        
        get_cache_path(cache, "https://github.com/org/repo", branch="feature", per_branch=True)  
        # Returns: cache/github/org/repo-feature-abcdef12
        
        # Azure DevOps example (with provider support)
        get_cache_path(cache, "https://dev.azure.com/org/project/_git/repo")
        # Returns: cache/azure/org/project/repo-12345678
    """
    logger.debug(f"Getting cache path for repo_path='{repo_path}', branch='{branch}', per_branch={per_branch}")
    
    # Ensure cache_dir is absolute
    cache_dir = Path(cache_dir).resolve()

    # Sanitize branch name for use in filesystem paths
    safe_branch = None
    if branch and per_branch:
        # Replace problematic characters in branch names
        safe_branch = branch.replace('/', '-').replace('\\', '-').replace(':', '-')
        logger.debug(f"Sanitized branch name: '{branch}' -> '{safe_branch}'")

    if is_git_url(repo_path):
        # Try to use provider registry for cache path generation
        if _PROVIDERS_AVAILABLE:
            try:
                provider = get_provider(repo_path)
                if provider:
                    logger.debug(f"Found provider '{provider.get_provider_name()}' for '{repo_path}'")
                    components = provider.parse_url(repo_path)
                    if components:
                        logger.debug(f"Parsed components: {components}")
                        cache_path = provider.get_cache_path(
                            cache_dir=cache_dir,
                            components=components,
                            branch=branch,
                            per_branch=per_branch
                        )
                        logger.debug(f"Provider generated cache path: {cache_path}")
                        return cache_path
                else:
                    logger.debug(f"No provider found for '{repo_path}', falling back to original logic")
            except Exception as e:
                logger.warning(f"Provider-based cache path generation failed for '{repo_path}': {e}")
                # Continue to fallback logic
        
        # Fallback to original logic for backwards compatibility
        logger.debug(f"Using original cache path logic for '{repo_path}'")
        
        # For GitHub URLs (original logic preserved)
        try:
            org, repo, ref = parse_github_url(repo_path)
            logger.debug(f"Successfully parsed as GitHub URL: org='{org}', repo='{repo}'")
            
            # Include branch in hash if per_branch strategy
            if per_branch and safe_branch:
                url_with_branch = f"{repo_path}@{branch}"  # Use original branch for hash consistency
                url_hash = hashlib.sha256(url_with_branch.encode()).hexdigest()[:8]
                # Include sanitized branch name in path for clarity
                result_path = (cache_dir / "github" / org / f"{repo}-{safe_branch}-{url_hash}").resolve()
                logger.debug(f"GitHub per-branch cache path: {result_path}")
                return result_path
            else:
                # Shared strategy - same path regardless of branch
                url_hash = hashlib.sha256(repo_path.encode()).hexdigest()[:8]
                result_path = (cache_dir / "github" / org / f"{repo}-{url_hash}").resolve()
                logger.debug(f"GitHub shared cache path: {result_path}")
                return result_path
                
        except ValueError as e:
            logger.debug(f"Not a GitHub URL, using generic git handling: {e}")
            # Fall back to generic git handling
            if per_branch and safe_branch:
                url_with_branch = f"{repo_path}@{branch}"  # Use original branch for hash consistency
                url_hash = hashlib.sha256(url_with_branch.encode()).hexdigest()[:8]
                result_path = (cache_dir / "git" / f"{safe_branch}-{url_hash}").resolve()
                logger.debug(f"Generic git per-branch cache path: {result_path}")
                return result_path
            else:
                url_hash = hashlib.sha256(repo_path.encode()).hexdigest()[:8]
                result_path = (cache_dir / "git" / url_hash).resolve()
                logger.debug(f"Generic git shared cache path: {result_path}")
                return result_path
    else:
        # For local paths - per_branch doesn't apply to local repos
        logger.debug(f"Processing local path: {repo_path}")
        abs_path = str(Path(repo_path).resolve())
        path_hash = hashlib.sha256(abs_path.encode()).hexdigest()[:8]
        result_path = (cache_dir / "local" / path_hash).resolve()
        logger.debug(f"Local cache path: {result_path}")
        return result_path
