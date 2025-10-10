"""
Core MCP server implementation using FastMCP.
"""

import logging
import sys
import asyncio
import click
from typing import List, Optional

from mcp.server.fastmcp import FastMCP
from code_expert.config import ServerConfig, load_config
from code_expert.repository import RepositoryManager
from code_expert.context.builder import RepoMapBuilder
from code_expert.repository.documentation import get_repository_documentation

# Configure logging
logging.basicConfig(
    stream=sys.stderr,
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("code_expert.mcp")


def create_mcp_server(config: ServerConfig = None) -> FastMCP:
    """Create and configure the MCP server instance"""
    if config is None:
        config = load_config()

    server = FastMCP(name=config.name)

    # Initialize core components - pass full server config for auto-refresh
    repo_manager = RepositoryManager(config.repository, server_config=config)
    repo_map_builder = RepoMapBuilder(cache=repo_manager.cache)

    # Store repo_manager on server for webhook access
    server._mcp_server.repo_manager = repo_manager

    # Register tools
    register_tools(server, repo_manager, repo_map_builder)

    # Add auto-refresh management tools
    register_auto_refresh_tools(server, repo_manager)

    # Add lifecycle hooks for auto-refresh
    add_lifecycle_hooks(server, repo_manager)

    return server


def register_tools(
    mcp_server: FastMCP,
    repo_manager: RepositoryManager,
    repo_map_builder: RepoMapBuilder,
) -> None:
    """Register all MCP tools with the server."""

    @mcp_server.tool(
        name="get_repo_file_content",
        description="""Retrieve file contents or directory listings from a repository. For files, returns the complete file content. For directories, returns a non-recursive listing of immediate files and subdirectories.

PARAMETERS:
- repo_path: Repository identifier (GitHub URL, Azure DevOps URL, or local path)
  Examples: 'https://github.com/user/repo', 'https://dev.azure.com/org/project/_git/repo', '/home/user/project'
- resource_path: (Optional) Path within the repository. Defaults to root directory if not provided.""",
    )
    async def get_repo_file_content(repo_path: str, resource_path: Optional[str] = None, branch: Optional[str] = None, cache_strategy: str = "shared") -> dict:
        """
        Retrieve file contents or directory listings from a repository.

        Args:
            repo_path (str): Path or URL to the repository
            resource_path (str, optional): Path to the target file or directory within the repository. Defaults to the repository root if not provided.
            branch (str, optional): Specific branch to read from (only used with per-branch cache strategy)
            cache_strategy (str, optional): Cache strategy - "shared" (default) or "per-branch"

        Returns:
            dict: For files:
                {
                    "type": "file",
                    "path": str,  # Relative path within repository
                    "content": str,  # Complete file contents
                    "branch": str,  # Current branch name
                    "cache_strategy": str  # Cache strategy used
                }
                For directories:
                {
                    "type": "directory",
                    "path": str,  # Relative path within repository
                    "contents": List[str],  # List of immediate files and subdirectories
                    "branch": str,  # Current branch name
                    "cache_strategy": str  # Cache strategy used
                }

        Note:
            Directory listings are not recursive - they only show immediate contents.
            To explore subdirectories, make additional calls with the subdirectory path.
        """
        try:
            if resource_path is None:
                resource_path = "."

            # Check metadata.json to ensure repository is cloned and ready
            from code_expert.repository.path_utils import get_cache_path
            cache_path = get_cache_path(
                repo_manager.cache_dir, 
                repo_path, 
                branch if cache_strategy == "per-branch" else None,
                per_branch=(cache_strategy == "per-branch")
            )
            str_path = str(cache_path.resolve())
            
            repo_status = await repo_manager.cache.get_repository_status(str_path)
            if not repo_status or "clone_status" not in repo_status:
                return {"status": "error", "error": "Repository not found. Please clone it first using clone_repo."}
            
            clone_status = repo_status["clone_status"]
            if not clone_status:
                return {"status": "error", "error": "Repository not cloned. Please clone it first using clone_repo."}
            elif clone_status.get("status") in ["cloning", "copying"]:
                return {"status": "error", "error": "Repository clone still in progress. Please wait for clone to complete."}
            elif clone_status.get("status") != "complete":
                return {"status": "error", "error": "Repository clone failed or incomplete. Please try cloning again."}
            
            # Clone is complete, create repository instance with correct cache path
            from code_expert.repository.manager import Repository
            repository = Repository(
                repo_id=str_path,
                root_path=str_path,
                repo_type="git",
                is_git=True
            )
            result = await repository.get_resource(resource_path)
            
            # Add branch and cache strategy information to response
            if isinstance(result, dict) and "type" in result:
                result["branch"] = repo_status.get("current_branch")
                result["cache_strategy"] = cache_strategy
            
            return result
        except Exception as e:
            logger.error(f"Error getting resource: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    @mcp_server.tool(
        name="refresh_repo",
        description="""⚠️ MANUAL SYNC ONLY: Update a repository with latest changes. Only use when explicitly requested by the user.

IMPORTANT:
- DO NOT use this automatically or proactively
- ONLY use when user explicitly asks to "refresh", "sync", or "update" the repository
- The initial clone already provides the latest code - no refresh needed after cloning

WHAT IT DOES:
- Git repos: Performs git pull to fetch latest commits
- Local dirs: Re-copies from source directory  
- Triggers re-analysis of changed files

PARAMETER:
- repo_path: Repository identifier (GitHub URL, Azure DevOps URL, or local path)
  Examples: 'https://github.com/user/repo', 'https://dev.azure.com/org/project/_git/repo', '/home/user/project'""",
    )
    async def refresh_repo(repo_path: str, branch: Optional[str] = None, cache_strategy: str = "shared") -> dict:
        """
        Update a previously cloned repository in MCP's cache and refresh its analysis.

        For Git repositories, performs a git pull to get latest changes.
        For local directories, copies the latest content from the source.
        Then triggers a new repository map build to ensure all analysis is based on
        the updated code.

        Args:
            repo_path (str): Path or URL matching what was originally provided to clone_repo
            branch (str, optional): Specific branch to switch to during refresh
            cache_strategy (str, optional): Cache strategy - must match original clone strategy

        Returns:
            dict: Response with format:
                {
                    "status": str,  # "pending", "switched_branch", "error"
                    "path": str,    # (On pending) Cache location being refreshed
                    "message": str, # (On pending) Status message
                    "error": str    # (On error) Error message
                    "cache_strategy": str  # Strategy used for caching
                }

        Note:
            - Repository must be previously cloned and have completed initial analysis
            - Updates MCP's cached copy, does not modify the source repository
            - Automatically triggers rebuild of repository map with updated files
            - If branch is specified, switches to that branch after pulling latest changes
            - cache_strategy should match the strategy used during original clone
            - Operation runs in background, check get_repo_map_content for status
        """
        try:
            # Validate cache_strategy
            if cache_strategy not in ["shared", "per-branch"]:
                return {"status": "error", "error": "cache_strategy must be 'shared' or 'per-branch'"}
                
            return await repo_manager.refresh_repository(repo_path, branch, cache_strategy)
        except Exception as e:
            logger.error(f"Error refreshing repository: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    @mcp_server.tool(
        name="get_repo_status",
        description="""Check if a repository is cloned and ready for analysis without triggering any operations.

USE THIS TO:
- Check if a repository needs to be cloned
- Verify if analysis is complete or in progress
- See which branch is currently active
- Understand the cache state before using other tools

RETURNS:
- is_cloned: Whether the repository exists in cache
- clone_status: Current state ('complete', 'cloning', 'failed', or None)
- analysis_status: State of code analysis ('complete', 'building', or None)
- current_branch: The active branch name
- cache_strategy: Which strategy is being used
- last_updated: When the repository was last accessed""",
    )
    async def get_repo_status(repo_path: str, branch: Optional[str] = None, cache_strategy: str = "shared") -> dict:
        """
        Check repository status without side effects.
        
        Args:
            repo_path: Repository identifier (GitHub URL, Azure DevOps URL, or local path)
            branch: Optional branch to check (for per-branch strategy)
            cache_strategy: Cache strategy to check ('shared' or 'per-branch')
            
        Returns:
            dict: Complete status information about the repository
        """
        try:
            from code_expert.repository.path_utils import get_cache_path
            
            # Get cache path based on strategy
            cache_path = get_cache_path(
                repo_manager.cache_dir,
                repo_path,
                branch if cache_strategy == "per-branch" else None,
                per_branch=(cache_strategy == "per-branch")
            )
            str_path = str(cache_path.resolve())
            
            # Get repository status from cache
            repo_status = await repo_manager.cache.get_repository_status(str_path)
            
            if not repo_status:
                return {
                    "status": "success",
                    "is_cloned": False,
                    "clone_status": None,
                    "analysis_status": None,
                    "message": "Repository not found in cache"
                }
            
            # Extract relevant status information
            clone_status = repo_status.get("clone_status", {})
            repo_map_status = repo_status.get("repo_map_status", {})
            
            return {
                "status": "success",
                "is_cloned": clone_status.get("status") == "complete",
                "clone_status": clone_status.get("status"),
                "analysis_status": repo_map_status.get("status") if repo_map_status else None,
                "current_branch": repo_status.get("current_branch"),
                "requested_branch": repo_status.get("requested_branch"),
                "cache_strategy": repo_status.get("cache_strategy", cache_strategy),
                "last_updated": repo_status.get("last_access"),
                "cache_path": str_path
            }
            
        except Exception as e:
            logger.error(f"Error getting repository status: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    @mcp_server.tool(
        name="list_repository_branches",
        description="List all cached versions of a repository across different branches. Shows information about each cached branch including paths, strategies, and metadata.",
    )
    async def list_repository_branches(repo_url: str) -> dict:
        """
        List all cached versions of a repository across different branches.

        This tool scans the MCP cache to find all entries for a given repository URL,
        showing both shared and per-branch cache entries. Useful for understanding
        what branches are available and their current status.

        Args:
            repo_url (str): Repository URL to search for (must match exact URL used in clone_repo)

        Returns:
            dict: Response with format:
                {
                    "status": "success" | "error",
                    "repo_url": str,  # Repository URL searched
                    "cached_branches": [  # List of cached branch entries
                        {
                            "requested_branch": str,  # Branch that was requested during clone
                            "current_branch": str,    # Current active branch in the cache
                            "cache_path": str,        # File system path to cached repository
                            "cache_strategy": str,    # "shared" or "per-branch"
                            "last_access": str,       # ISO timestamp of last access
                            "clone_status": dict,     # Clone operation status
                            "repo_map_status": dict   # Repository map build status
                        }
                    ],
                    "total_cached": int  # Total number of cached entries found
                }

        Note:
            - Only returns repositories that have been cloned via clone_repo
            - Useful for PR review workflows to see all available branch versions
            - Shows both active and completed cache entries
            - Helps identify which cache strategy was used for each entry
        """
        try:
            return await repo_manager.list_repository_branches(repo_url)
        except Exception as e:
            logger.error(f"Error listing repository branches: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    @mcp_server.tool(
        name="delete_repo",
        description="""Remove a cached repository from the MCP server's cache, including all associated metadata and analysis results.

⚠️ DESTRUCTIVE OPERATION: This permanently removes cached repositories and cannot be undone.

WHAT IT DOES:
- Removes ALL cached versions of the repository (shared and per-branch cache entries)
- Deletes associated metadata including clone status and analysis results
- Frees up disk space and cache slots
- Cleans up in-memory references

IDENTIFICATION METHODS:
- Repository URL: Use the same URL format provided to clone_repo
  Examples: 'https://github.com/user/repo', 'https://dev.azure.com/org/project/_git/repo'
- Direct cache path: Use the absolute file system path to the cached repository
  Example: '/path/to/cache/dir/github_com_user_repo_main'

PARAMETER:
- repo_identifier: Repository URL or direct cache path to identify which repository to delete

USE CASES:
- Clean up repositories no longer needed for analysis
- Free cache space when approaching maximum cached repositories limit
- Remove corrupted or problematic cache entries
- Cache management and maintenance operations

NOTE: After deletion, the repository will need to be re-cloned via clone_repo before it can be analyzed again.""",
    )
    async def delete_repo(repo_identifier: str) -> dict:
        """
        Delete a repository from the MCP server's cache.

        Removes cached repositories to free up space and clean up entries that are
        no longer needed. Supports identification by repository URL or direct cache path.
        This is a destructive operation that removes all cached versions and metadata.

        Args:
            repo_identifier (str): Repository identifier - either the repository URL 
                                 (matching what was used in clone_repo) or the direct 
                                 cache path to the repository

        Returns:
            dict: Response with format:
                {
                    "status": "success" | "error",
                    "deleted_paths": [str],  # (On success) List of cache paths that were deleted
                    "total_deleted": int,    # (On success) Number of cache entries removed
                    "message": str,          # (On success) Summary of deletion operation
                    "error": str             # (On error) Error message
                }

        Note:
            - This operation is irreversible - deleted cache entries cannot be recovered
            - Repository will need to be re-cloned before further analysis
            - Removes ALL cached versions including shared and per-branch entries
            - For repository URLs, finds and removes all matching cache entries
            - For direct cache paths, removes the specific cache entry
        """
        try:
            return await repo_manager.delete_repository(repo_identifier)
        except Exception as e:
            logger.error(f"Error deleting repository: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    @mcp_server.tool(
        name="list_repos",
        description="List all repositories currently in the MCP server's cache with their complete metadata including clone status, analysis status, branches, and cache sizes.",
    )
    async def list_repos() -> dict:
        """
        List all cached repositories with their metadata.
        
        Returns all available information from the cache metadata including:
        - Repository URLs and cache paths
        - Clone and analysis statuses
        - Branch information
        - Last access times
        - Cache sizes
        - Cache strategies used
        
        Returns:
            dict: Response with format:
                {
                    "status": "success" | "error",
                    "total_cached": int,  # Number of cached repositories
                    "max_cached_repos": int,  # Maximum allowed cached repos
                    "cache_dir": str,  # Cache directory path
                    "repositories": [  # List of cached repositories
                        {
                            "cache_path": str,  # File system path to cached repo
                            "url": str,  # Original repository URL or path
                            "last_access": str,  # ISO timestamp of last access
                            "branch": str,  # Branch that was requested
                            "current_branch": str,  # Currently checked out branch
                            "cache_strategy": str,  # "shared" or "per-branch"
                            "clone_status": dict,  # Clone operation status
                            "repo_map_status": dict,  # Repository analysis status
                            "cache_size_mb": float,  # Size in megabytes
                            "cache_size_bytes": int  # Size in bytes
                        }
                    ]
                }
        
        Note:
            - Repositories are sorted by last access time (most recent first)
            - Useful for cache management and understanding what's available
            - Shows both completed and in-progress operations
        """
        try:
            return await repo_manager.list_cached_repositories()
        except Exception as e:
            logger.error(f"Error listing cached repositories: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    @mcp_server.tool(
        name="clone_repo",
        description="""Initialize a repository for analysis by copying it to MCP's cache. This is a prerequisite for all other analysis tools.

WHEN TO USE:
- First time analyzing a repository
- When explicitly switching cache strategies
- NOT needed if already cloned (check with list_repos first if unsure)

RETURNS:
- 'already_cloned': Repository ready for analysis, no action needed
- 'pending': Clone started, will complete in background. You can proceed with other tools
- 'switched_branch': Branch changed successfully (shared cache only)
- 'error': Operation failed, see error message

CACHE STRATEGIES:
- 'shared' (default): One cache per repo, can switch branches in-place
- 'per-branch': Separate cache for each branch, useful for comparing branches""",
    )
    async def clone_repo(url: str, branch: Optional[str] = None, cache_strategy: str = "shared") -> dict:
        """
        Clone a repository into MCP server's cache and prepare it for analysis.

        This tool must be called before using analysis endpoints like get_source_repo_map
        or get_repo_documentation. It copies the repository into MCP's cache and
        automatically starts building a repository map in the background.

        Args:
            url (str): URL of remote repository or path to local repository to analyze
            branch (str, optional): Specific branch to clone for analysis
            cache_strategy (str, optional): Cache strategy - "shared" (default) or "per-branch"
                - "shared": One cache entry per repo, switch branches in place
                - "per-branch": Separate cache entries for each branch (useful for PR reviews)

        Returns:
            dict: Response with format:
                {
                    "status": "pending" | "already_cloned" | "switched_branch" | "error",
                    "path": str,  # Cache location where repo is being cloned
                    "message": str,  # Status message about clone and analysis
                    "cache_strategy": str,  # Strategy used for caching
                    "current_branch": str,  # (if applicable) Current active branch
                    "previous_branch": str,  # (if switched) Previous branch name
                }

        Note:
            - This is a setup operation for MCP analysis only
            - Does not modify the source repository
            - Repository map building starts automatically after clone completes
            - Use get_source_repo_map to check analysis status and retrieve results
            - Per-branch strategy allows simultaneous access to different branches
        """
        try:
            # Validate cache_strategy
            if cache_strategy not in ["shared", "per-branch"]:
                return {"status": "error", "error": "cache_strategy must be 'shared' or 'per-branch'"}
            
            # Repository clone with new dual cache strategy support
            logger.debug(f"[TRACE] clone_repo: Starting clone_repository for {url} with branch {branch} using {cache_strategy} strategy")
            result = await repo_manager.clone_repository(url, branch, cache_strategy)
            logger.debug(f"[TRACE] clone_repo: clone_repository completed for {url}")
            return result
        except Exception as e:
            logger.error(f"Error cloning repository: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    @mcp_server.tool(
        name="get_source_repo_map",
        description="""Retrieve a semantic analysis map of the repository's source code structure, including file hierarchy, functions, classes, and their relationships. Repository must be previously cloned via clone_repo.

PARAMETER:
- repo_path: Repository identifier (GitHub URL, Azure DevOps URL, or local path)
  Examples: 'https://github.com/user/repo', 'https://dev.azure.com/org/project/_git/repo', '/home/user/project'
  The format will be normalized automatically

RESPONSE CHARACTERISTICS:
1. Status Types:
- "threshold_exceeded": Indicates analysis scope exceeds processing limits
- "building": Analysis in progress
- "waiting": Waiting for prerequisite operation
- "success": Analysis complete
- "error": Operation failed

2. Resource Management:
- Repository size impacts processing time and token usage
- 'max_tokens' parameter provides approximate control of response size
    Note: Actual token count may vary slightly above or below specified limit
- File count threshold exists to prevent overload
- Processing time scales with both file count and max_tokens
    Important: Clients should adjust their timeout values proportionally when:
    * Analyzing larger numbers of files
    * Specifying higher max_tokens values
    * Working with complex repositories

3. Scope Control Options:
- 'files': Analyze specific files. If only this is provided, the entire repository will be searched for matching file names.
- 'directories': Analyze all source files within specific directories.
- If BOTH 'files' and 'directories' are provided, the tool will perform an INTERSECTION, analyzing only the files named in 'files' that are also located within the specified 'directories'.

4. Response Metadata:
- Contains processing statistics and limitation details
- Provides override_guidance when thresholds are exceeded
- Reports excluded files and completion status

NOTE: This tool supports both broad and focused analysis strategies. Response handling can be adapted based on specific use case requirements and user preferences.""",
    )
    async def get_source_repo_map(
        repo_path: str,
        directories: Optional[List[str]] = None,
        files: Optional[List[str]] = None,
        max_tokens: Optional[int] = None,
        branch: Optional[str] = None,
        cache_strategy: str = "shared",
    ) -> dict:
        """
        Retrieve a semantic analysis map of the repository's code structure.

        Returns a detailed map of the repository's structure, including file hierarchy,
        code elements (functions, classes, methods), and their relationships. Can analyze
        specific files/directories or the entire repository.

        Args:
            repo_path (str): Path or URL matching what was originally provided to clone_repo
            files (List[str], optional): Specific files to analyze. If None, analyzes all files
            directories (List[str], optional): Specific directories to analyze. If None, analyzes all directories
            max_tokens (int, optional): Limit total tokens in analysis. Useful for large repositories
            branch (str, optional): Specific branch to analyze (only used with per-branch cache strategy)
            cache_strategy (str, optional): Cache strategy - "shared" (default) or "per-branch"

        Returns:
            dict: Response with format:
                {
                    "status": str,  # "success", "building", "waiting", or "error"
                    "content": str,  # Hierarchical representation of code structure
                    "metadata": {    # Analysis metadata
                        "excluded_files_by_dir": dict,
                        "is_complete": bool,
                        "max_tokens": int
                    },
                    "message": str,  # Present for "building"/"waiting" status
                    "error": str     # Present for "error" status
                }

        Note:
            - Repository must be previously cloned using clone_repo
            - Initial analysis happens in background after clone
            - Returns "building" status while analysis is in progress
            - Content includes file structure, code elements, and their relationships
            - For large repos, consider using max_tokens or targeting specific directories
        """
        try:
            # DEBUG: Log the parameters received at MCP endpoint
            logger.debug("[MCP DEBUG] get_source_repo_map called with:")
            logger.debug(f"[MCP DEBUG]   repo_path: {repo_path}")
            logger.debug(f"[MCP DEBUG]   files: {files}")
            logger.debug(f"[MCP DEBUG]   directories: {directories}")
            logger.debug(f"[MCP DEBUG]   max_tokens: {max_tokens}")
            
            if directories is None:
                directories = []
                
            return await repo_map_builder.get_repo_map_content(
                repo_path, files=files, directories=directories, max_tokens=max_tokens,
                branch=branch, cache_strategy=cache_strategy
            )
        except Exception as e:
            logger.error(f"Error getting context: {e}", exc_info=True)
            return {
                "status": "error",
                "error": f"Unexpected error while getting repository context: {str(e)}",
            }

    @mcp_server.tool(
        name="get_repo_structure",
        description="""Retrieve directory structure and analyzable file counts for a repository to guide analysis decisions.

PARAMETER:
- repo_path: Repository identifier (GitHub URL, Azure DevOps URL, or local path)
  Examples: 'https://github.com/user/repo', 'https://dev.azure.com/org/project/_git/repo', '/home/user/project'
  The format will be normalized automatically

RESPONSE CHARACTERISTICS:
1. Directory Information:
- Lists directories containing analyzable source code
- Reports number of analyzable files per directory
- Shows directory hierarchy
- Indicates file extensions present in each location

2. Usage:
- Requires repository to be previously cloned via clone_repo
- Helps identify main code directories
- Supports planning targeted analysis
- Shows where analyzable code is located

NOTE: Use this tool to understand repository structure and choose which directories to analyze in detail.""",
    )
    async def get_repo_structure(
        repo_path: str, directories: Optional[List[str]] = None, include_files: bool = False,
        branch: Optional[str] = None, cache_strategy: str = "shared"
    ) -> dict:
        """
        Get repository structure information with optional file listings.

        Args:
            repo_path: Path/URL matching what was provided to clone_repo
            directories: Optional list of directories to limit results to
            include_files: Whether to include list of files in response

        Returns:
            dict: {
                "status": str,
                "message": str,
                "directories": [{
                    "path": str,
                    "analyzable_files": int,
                    "extensions": {
                        "py": 10,
                        "java": 5,
                        "ts": 3
                    },
                    "files": [str]  # Only present if include_files=True
                }],
                "total_analyzable_files": int
            }
        """
        try:
            # Delegate to the RepoMapBuilder service to handle all the details
            return await repo_map_builder.get_repo_structure(
                repo_path, directories=directories, include_files=include_files,
                branch=branch, cache_strategy=cache_strategy
            )
        except Exception as e:
            logger.error(f"Error getting repository structure: {e}", exc_info=True)
            return {
                "status": "error",
                "error": f"Failed to get repository structure: {str(e)}",
            }

    @mcp_server.tool(
        name="get_repo_critical_files",
        description="""Identify and analyze the most structurally significant files in a repository to guide code understanding efforts.

PARAMETER:
- repo_path: Repository identifier (GitHub URL, Azure DevOps URL, or local path)
  Examples: 'https://github.com/user/repo', 'https://dev.azure.com/org/project/_git/repo', '/home/user/project'
  The format will be normalized automatically

RESPONSE CHARACTERISTICS:
1. Analysis Metrics:
   - Calculates importance scores based on:
     * Function count (weight: 2.0)
     * Total cyclomatic complexity (weight: 1.5)
     * Maximum cyclomatic complexity (weight: 1.2)
     * Lines of code (weight: 0.05)
   - Provides detailed metrics per file
   - Ranks files by composite importance score

2. Resource Management:
   - Repository must be previously cloned via clone_repo
   - Analysis performed on-demand using Lizard
   - Efficient for both small and large codebases
   - Supports both full-repo and targeted analysis

3. Scope Control Options:
   - 'files': Analyze specific files. If only this is provided, the entire repository will be searched for matching file names.
   - 'directories': Analyze all source files within specific directories.
   - If BOTH 'files' and 'directories' are provided, the tool will perform an INTERSECTION, analyzing only the files named in 'files' that are also located within the specified 'directories'.
   - 'limit': Control maximum results returned.

4. Response Metadata:
   - Total files analyzed
   - Analysis completion status

NOTE: This tool is designed to guide initial codebase exploration by identifying structurally significant files. Results can be used to target subsequent get_source_repo_map calls for detailed analysis.""",
    )
    async def get_repo_critical_files(
        repo_path: str,
        files: Optional[List[str]] = None,
        directories: Optional[List[str]] = None,
        limit: int = 50,
        include_metrics: bool = True,
    ) -> dict:
        """
        Analyze and identify the most structurally significant files in a codebase.

        Uses code complexity metrics to calculate importance scores, helping identify
        files that are most critical for understanding the system's structure.

        Args:
            repo_path: Path/URL matching what was provided to clone_repo
            files: Optional list of specific files to analyze
            directories: Optional list of specific directories to analyze
            limit: Maximum number of files to return (default: 50)
            include_metrics: Include detailed metrics in response (default: True)

        Returns:
            dict: {
                "status": str,  # "success", "error"
                "files": [{
                    "path": str,
                    "importance_score": float,
                    "metrics": {  # Only if include_metrics=True
                        "total_ccn": int,
                        "max_ccn": int,
                        "function_count": int,
                        "nloc": int
                    }
                }],
                "total_files_analyzed": int
            }
        """
        try:
            # Import and initialize the analyzer
            from code_expert.analysis.complexity import CodeComplexityAnalyzer
            from code_expert.repository.path_utils import get_cache_path
            import git

            analyzer = CodeComplexityAnalyzer(repo_manager, repo_map_builder)
            
            # Get cache path to check for cached analysis
            cache_path = get_cache_path(repo_manager.cache_dir, repo_path)
            cache_path_str = str(cache_path.resolve())
            
            # Check if we have cached results
            with repo_manager.cache._file_lock():
                metadata_dict = repo_manager.cache._read_metadata()
                if cache_path_str in metadata_dict:
                    repo_metadata = metadata_dict[cache_path_str]
                    cached_analysis = repo_metadata.critical_files_analysis
                    
                    if cached_analysis:
                        # Check cache status
                        if cached_analysis.get("status") == "analyzing":
                            logger.info(f"Critical files analysis is in progress for {repo_path}")
                            return {
                                "status": "waiting",
                                "message": "Critical files analysis is running in background. Please try again in a few moments.",
                            }
                        
                        elif cached_analysis.get("status") == "complete":
                            # Check if cache is valid (only if specific files/directories were not provided)
                            if files is None and directories is None:
                                cached_params = cached_analysis.get("parameters", {})
                                if cached_params.get("files") is None and cached_params.get("directories") is None:
                                    # Cache is valid for this request
                                    logger.info(f"Using cached critical files analysis for {repo_path}")
                                    
                                    # Get current commit hash to verify cache validity
                                    current_commit = None
                                    try:
                                        repo = git.Repo(cache_path_str)
                                        current_commit = str(repo.head.commit.hexsha)
                                    except (git.InvalidGitRepositoryError, git.NoSuchPathError):
                                        # For local folders, we'll trust the cache
                                        # (could enhance with better directory hash comparison)
                                        pass
                                    
                                    cached_commit = cached_analysis.get("commit_hash")
                                    
                                    # If commits match (or it's a local folder), use cache
                                    if current_commit is None or current_commit == cached_commit:
                                        cached_results = cached_analysis.get("results", {})
                                        files_list = cached_results.get("files", [])
                                        
                                        # Apply limit if specified
                                        limited_files = files_list[:limit] if limit > 0 else files_list
                                        
                                        return {
                                            "status": "success",
                                            "files": limited_files,
                                            "total_files_analyzed": cached_results.get("total_files_analyzed", 0),
                                            "files_with_analysis": cached_results.get("files_with_analysis", 0),
                                            "files_without_analysis": cached_results.get("files_without_analysis", 0),
                                            "results_truncated": limit > 0 and len(files_list) > limit,
                                            "_cache_used": True,  # Debug flag
                                            "_cached_at": cached_analysis.get("analyzed_at"),
                                        }
                                    else:
                                        logger.info("Cache is stale (commit changed), running fresh analysis")

            # Before running fresh analysis, check if clone/copy just completed
            # to avoid duplicate analysis while background task is starting
            with repo_manager.cache._file_lock():
                metadata_dict = repo_manager.cache._read_metadata()
                if cache_path_str in metadata_dict:
                    repo_metadata = metadata_dict[cache_path_str]
                    clone_status = repo_metadata.clone_status
                    
                    # Check if clone completed very recently (within last 30 seconds)
                    if clone_status and clone_status.get("status") == "complete":
                        completed_at = clone_status.get("completed_at")
                        if completed_at:
                            from datetime import datetime, timedelta
                            try:
                                completed_time = datetime.fromisoformat(completed_at)
                                if datetime.now() - completed_time < timedelta(seconds=30):
                                    # Clone just completed, background analysis should be starting
                                    logger.info("Repository was just cloned/copied, background analysis should be starting")
                                    return {
                                        "status": "waiting", 
                                        "message": "Repository setup just completed. Critical files analysis is starting in background. Please try again in a few moments.",
                                    }
                            except:
                                pass
            
            # No valid cache found or cache is stale/incomplete, run fresh analysis
            logger.info(f"Running fresh critical files analysis for {repo_path}")
            return await analyzer.analyze_repo_critical_files(
                repo_path=repo_path,
                files=files,
                directories=directories,
                limit=limit,
                include_metrics=include_metrics,
            )
        except Exception as e:
            logger.error(
                f"Unexpected error in get_repo_critical_files: {str(e)}", exc_info=True
            )
            return {
                "status": "error",
                "error": f"An unexpected error occurred: {str(e)}",
            }

    @mcp_server.tool(
        name="get_repo_documentation",
        description="""Retrieve and analyze documentation files from a repository, including README files, API docs, design documents, and other documentation. Repository must be previously cloned via clone_repo.

PARAMETER:
- repo_path: Repository identifier (GitHub URL, Azure DevOps URL, or local path)
  Examples: 'https://github.com/user/repo', 'https://dev.azure.com/org/project/_git/repo', '/home/user/project'""",
    )
    async def get_repo_documentation(repo_path: str) -> dict:
        """
        Retrieve and analyze repository documentation files.

        Searches for and analyzes documentation within the repository, including:
        - README files
        - API documentation
        - Design documents
        - User guides
        - Installation instructions
        - Other documentation files

        Args:
            repo_path (str): Path or URL matching what was originally provided to clone_repo

        Returns:
            dict: Documentation analysis results with format:
                {
                    "status": str,  # "success", "error", or "waiting"
                    "message": str,  # Only for error/waiting status
                    "documentation": {  # Only for success status
                        "files": [
                            {
                                "path": str,      # Relative path in repo
                                "category": str,  # readme, api, docs, etc.
                                "format": str     # markdown, rst, etc.
                            }
                        ],
                        "directories": [
                            {
                                "path": str,
                                "doc_count": int
                            }
                        ],
                        "stats": {
                            "total_files": int,
                            "by_category": dict,
                            "by_format": dict
                        }
                    }
                }
        """
        try:
            # Call documentation backend module (thin endpoint)
            # Note: The documentation function doesn't use branch/cache_strategy parameters
            return await get_repository_documentation(repo_path)
        except Exception as e:
            logger.error(
                f"Error retrieving repository documentation: {e}", exc_info=True
            )
            return {
                "status": "error",
                "message": f"Failed to retrieve repository documentation: {str(e)}",
            }

def register_auto_refresh_tools(server: FastMCP, repo_manager: RepositoryManager) -> None:
    """Register auto-refresh management tools."""
    
    @server.tool(
        name="get_auto_refresh_status",
        description="""Get the current status of the auto-refresh system.
        
        Returns information about:
        - Whether auto-refresh is enabled and running
        - Number of repositories scheduled for refresh
        - Next scheduled refresh times
        - Configuration settings
        - Recent refresh activity
        """
    )
    async def get_auto_refresh_status() -> dict:
        """Get auto-refresh system status."""
        try:
            return await repo_manager.get_auto_refresh_status()
        except Exception as e:
            logger.error(f"Error getting auto-refresh status: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}
    
    @server.tool(
        name="start_auto_refresh",
        description="""Manually start the auto-refresh system if it's not already running.
        
        This is typically not needed as auto-refresh starts automatically with the server,
        but can be useful for recovery scenarios or manual management.
        """
    )
    async def start_auto_refresh() -> dict:
        """Manually start auto-refresh system."""
        try:
            await repo_manager.start_auto_refresh()
            return {"status": "success", "message": "Auto-refresh system started"}
        except Exception as e:
            logger.error(f"Error starting auto-refresh: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}
    
    @server.tool(
        name="stop_auto_refresh",
        description="""Manually stop the auto-refresh system.
        
        This will cancel all scheduled refreshes and stop the background worker.
        Repositories will no longer be automatically refreshed until the system is restarted.
        """
    )
    async def stop_auto_refresh() -> dict:
        """Manually stop auto-refresh system."""
        try:
            await repo_manager.stop_auto_refresh()
            return {"status": "success", "message": "Auto-refresh system stopped"}
        except Exception as e:
            logger.error(f"Error stopping auto-refresh: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

def add_lifecycle_hooks(server: FastMCP, repo_manager: RepositoryManager) -> None:
    """Add server lifecycle hooks for auto-refresh management."""
    
    # Store original lifecycle methods if they exist
    original_on_startup = getattr(server, '_on_startup', None)
    original_on_shutdown = getattr(server, '_on_shutdown', None)
    
    async def on_startup():
        """Start auto-refresh system when server starts."""
        try:
            if original_on_startup:
                await original_on_startup()
            
            # Start auto-refresh system
            await repo_manager.start_auto_refresh()
            logger.info("Server startup completed with auto-refresh system")
        except Exception as e:
            logger.error(f"Error during server startup: {e}")
    
    async def on_shutdown():
        """Cleanup auto-refresh system when server shuts down."""
        try:
            # Stop auto-refresh system first
            await repo_manager.stop_auto_refresh()
            
            # Cleanup repositories
            await repo_manager.cleanup()
            
            if original_on_shutdown:
                await original_on_shutdown()
                
            logger.info("Server shutdown completed")
        except Exception as e:
            logger.error(f"Error during server shutdown: {e}")
    
    # Set the lifecycle hooks
    server._on_startup = on_startup
    server._on_shutdown = on_shutdown

# Create server instance that can be imported by MCP CLI
server = create_mcp_server()


@click.command()
@click.option("--port", default=3001, help="Port to listen on for SSE")
@click.option(
    "--transport",
    type=click.Choice(["stdio", "sse"]),
    default="stdio",
    help="Transport type (stdio or sse)",
)
@click.option(
    "--cache-dir",
    help="Directory to store repository cache",
)
@click.option(
    "--max-cached-repos",
    type=int,
    help="Maximum number of cached repositories",
)
def main(
    port: int, transport: str, cache_dir: str = None, max_cached_repos: int = None
) -> int:
    """Run the server with specified transport."""
    try:
        # Create overrides dict from command line args
        overrides = {}
        if cache_dir or max_cached_repos:
            overrides["repository"] = {}
            if cache_dir:
                overrides["repository"]["cache_dir"] = cache_dir
            if max_cached_repos:
                overrides["repository"]["max_cached_repos"] = max_cached_repos

        # Create server with command line overrides
        config = load_config(overrides=overrides)
        
        global server
        server = create_mcp_server(config)

        if transport == "stdio":
            asyncio.run(server.run_stdio_async())
        else:
            server.settings.port = port
            asyncio.run(server.run_sse_async())
        return 0
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        return 0
    except Exception as e:
        logger.error(f"Failed to start server: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
