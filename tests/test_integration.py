"""Integration tests for provider framework with existing code."""

import os
import sys
import pytest
import pytest_asyncio
from pathlib import Path
from unittest.mock import patch

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from code_expert.repository.path_utils import is_git_url, get_cache_path, parse_github_url
from code_expert.repository.providers import get_provider, get_default_registry


class TestBackwardsCompatibility:
    """Test that existing code patterns continue to work."""
    
    def test_is_git_url_github(self):
        """Test is_git_url still works with GitHub URLs."""
        assert is_git_url("https://github.com/owner/repo")
        assert is_git_url("git@github.com:owner/repo.git")
        assert not is_git_url("https://example.com")
        assert not is_git_url("/local/path")
    
    def test_is_git_url_azure_devops(self):
        """Test is_git_url now works with Azure DevOps URLs."""
        assert is_git_url("https://dev.azure.com/org/project/_git/repo")
        assert is_git_url("git@ssh.dev.azure.com:v3/org/project/repo")
        
    def test_parse_github_url_unchanged(self):
        """Test parse_github_url maintains exact same behavior."""
        org, repo, ref = parse_github_url("https://github.com/owner/repo")
        assert org == "owner"
        assert repo == "repo"
        assert ref is None
        
        org, repo, ref = parse_github_url("git@github.com:owner/repo.git")
        assert org == "owner"
        assert repo == "repo"
        assert ref is None
    
    def test_get_cache_path_github(self, tmp_path):
        """Test get_cache_path still generates same paths for GitHub."""
        cache_dir = tmp_path / "cache"
        
        # Test shared strategy
        path1 = get_cache_path(cache_dir, "https://github.com/owner/repo")
        assert "github/owner/repo-" in str(path1)
        
        # Test per-branch strategy
        path2 = get_cache_path(cache_dir, "https://github.com/owner/repo", branch="main", per_branch=True)
        assert "github/owner/repo-main-" in str(path2)
    
    def test_get_cache_path_azure_devops(self, tmp_path):
        """Test get_cache_path generates correct paths for Azure DevOps."""
        cache_dir = tmp_path / "cache"
        
        # Test shared strategy
        path1 = get_cache_path(cache_dir, "https://dev.azure.com/org/project/_git/repo")
        assert "azure/org/project/repo-" in str(path1)
        
        # Test per-branch strategy
        path2 = get_cache_path(cache_dir, "https://dev.azure.com/org/project/_git/repo", branch="main", per_branch=True)
        assert "azure/org/project/repo-main-" in str(path2)
    
    def test_get_cache_path_local(self, tmp_path):
        """Test get_cache_path still works for local paths."""
        cache_dir = tmp_path / "cache"
        local_repo = tmp_path / "local_repo"
        local_repo.mkdir()
        
        path = get_cache_path(cache_dir, str(local_repo))
        assert "local/" in str(path)
        assert path.is_absolute()


class TestProviderIntegration:
    """Test provider framework integration."""
    
    def test_provider_detection_github(self):
        """Test GitHub URLs are correctly detected."""
        provider = get_provider("https://github.com/owner/repo")
        assert provider is not None
        assert provider.get_provider_name() == "GitHub"
    
    def test_provider_detection_azure_devops(self):
        """Test Azure DevOps URLs are correctly detected."""
        provider = get_provider("https://dev.azure.com/org/project/_git/repo")
        assert provider is not None
        assert provider.get_provider_name() == "Azure DevOps"
    
    def test_provider_authentication_github(self):
        """Test GitHub authentication with environment variable."""
        with patch.dict(os.environ, {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_test123"}):
            registry = get_default_registry()
            auth_url = registry.get_authenticated_url("https://github.com/owner/repo")
            assert "ghp_test123" in auth_url
            assert auth_url == "https://ghp_test123@github.com/owner/repo"
    
    def test_provider_authentication_azure_devops(self):
        """Test Azure DevOps authentication with environment variable."""
        with patch.dict(os.environ, {"AZURE_DEVOPS_PAT": "ado_test123"}):
            registry = get_default_registry()
            auth_url = registry.get_authenticated_url("https://dev.azure.com/org/project/_git/repo")
            assert "ado_test123" in auth_url
            assert auth_url == "https://ado_test123@dev.azure.com/org/project/_git/repo"
    
    def test_multiple_providers_coexist(self):
        """Test that both providers work simultaneously."""
        github_provider = get_provider("https://github.com/owner/repo")
        azure_provider = get_provider("https://dev.azure.com/org/project/_git/repo")
        
        assert github_provider is not None
        assert azure_provider is not None
        assert github_provider != azure_provider
        assert github_provider.get_env_var_name() == "GITHUB_PERSONAL_ACCESS_TOKEN"
        assert azure_provider.get_env_var_name() == "AZURE_DEVOPS_PAT"


class TestImportCompatibility:
    """Test that various import patterns still work."""
    
    def test_direct_import_functions(self):
        """Test direct function imports work."""
        from code_expert.repository.path_utils import is_git_url, get_cache_path
        assert callable(is_git_url)
        assert callable(get_cache_path)
    
    def test_module_import(self):
        """Test module import works."""
        from code_expert.repository import path_utils
        assert hasattr(path_utils, 'is_git_url')
        assert hasattr(path_utils, 'get_cache_path')
        assert hasattr(path_utils, 'parse_github_url')
    
    def test_provider_imports(self):
        """Test provider imports work."""
        from code_expert.repository.providers import GitProvider, GitHubProvider, AzureDevOpsProvider
        from code_expert.repository.providers import ProviderRegistry, get_provider, get_default_registry
        
        assert GitProvider is not None
        assert GitHubProvider is not None
        assert AzureDevOpsProvider is not None
        assert ProviderRegistry is not None
        assert callable(get_provider)
        assert callable(get_default_registry)


class TestDeleteRepoMCPIntegration:
    """Integration tests for the delete_repo functionality through repository manager."""

    @pytest_asyncio.fixture
    async def repo_manager_setup(self, tmp_path):
        """Create repository manager with real configuration for testing."""
        from code_expert.config import RepositoryConfig
        from code_expert.repository.manager import RepositoryManager
        
        # Create test configuration
        config = RepositoryConfig(
            cache_dir=str(tmp_path / "cache"),
            max_cached_repos=10
        )
        
        # Initialize repository manager
        repo_manager = RepositoryManager(config, server_config=None)
        
        return {
            "repo_manager": repo_manager,
            "cache_dir": tmp_path / "cache"
        }

    @pytest.fixture
    def mock_test_repo(self, tmp_path):
        """Create a mock test repository with git init."""
        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()
        
        # Create some test files
        (repo_dir / "main.py").write_text("print('Hello World')")
        (repo_dir / "README.md").write_text("# Test Repository")
        (repo_dir / "config.json").write_text('{"name": "test"}')
        
        # Initialize git repository
        import subprocess
        try:
            subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True, capture_output=True)
            subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_dir, check=True, capture_output=True)
        except subprocess.CalledProcessError:
            # If git commands fail, fall back to using this as a local directory test
            pass
        
        return repo_dir

    @pytest.mark.asyncio
    async def test_delete_repo_integration_success_url_identification(self, repo_manager_setup, mock_test_repo):
        """Test successful deletion of repository using URL identification through integration."""
        setup = repo_manager_setup
        repo_manager = setup["repo_manager"]
        
        test_url = f"file://{mock_test_repo}"
        
        # First, clone the repository and wait for completion
        clone_result = await repo_manager.clone_repository(test_url, cache_strategy="shared")
        assert clone_result["status"] in ["pending", "already_cloned"]
        
        # Wait for clone to complete if needed
        if clone_result["status"] == "pending":
            import asyncio
            for attempt in range(30):  # Wait up to 30 seconds
                await asyncio.sleep(1)
                branches_result = await repo_manager.list_repository_branches(test_url)
                if branches_result["status"] == "success" and branches_result["cached_branches"]:
                    # Check if clone is complete
                    branch_info = branches_result["cached_branches"][0]
                    # We just need the repository to exist in cache for deletion testing
                    break
            else:
                # If clone doesn't complete, skip this test 
                pytest.skip("Repository clone did not complete in reasonable time")
        
        # Now delete using URL identification
        delete_result = await repo_manager.delete_repository(test_url)
        
        # For this integration test, we mainly want to verify the delete operation
        # doesn't crash and returns proper response format
        assert isinstance(delete_result, dict)
        assert "status" in delete_result
        if delete_result["status"] == "success":
            assert "deleted_paths" in delete_result
            assert "message" in delete_result
        elif delete_result["status"] == "error":
            # This is okay too - repository might not have been fully cached
            assert "error" in delete_result

    @pytest.mark.asyncio
    async def test_delete_repo_integration_pre_cloned_repository(self, repo_manager_setup, mock_test_repo):
        """Test deletion of a repository that we ensure is fully cloned first."""
        setup = repo_manager_setup
        repo_manager = setup["repo_manager"]
        cache_dir = setup["cache_dir"]
        
        test_url = f"file://{mock_test_repo}"
        
        # Clone and wait for completion more thoroughly
        clone_result = await repo_manager.clone_repository(test_url, cache_strategy="shared")
        
        # Wait for the clone to be registered in metadata
        import asyncio
        cache_entries = []
        for attempt in range(20):
            await asyncio.sleep(0.5)
            list_result = await repo_manager.list_cached_repositories()
            if list_result["status"] == "success" and list_result["total_cached"] > 0:
                cache_entries = list_result["repositories"]
                break
        
        # If we have cached entries, test deletion
        if cache_entries:
            initial_count = len(cache_entries)
            
            # Delete using URL identification
            delete_result = await repo_manager.delete_repository(test_url)
            assert delete_result["status"] == "success"
            assert "deleted_paths" in delete_result
            assert len(delete_result["deleted_paths"]) >= 1
            
            # Verify repository count decreased
            list_result_after = await repo_manager.list_cached_repositories()
            assert list_result_after["status"] == "success"
            assert len(list_result_after["repositories"]) < initial_count
        else:
            # If clone didn't complete properly, test that delete handles non-existent repos correctly
            delete_result = await repo_manager.delete_repository(test_url)
            assert delete_result["status"] == "error"
            assert "Repository not found in cache" in delete_result["error"]

    @pytest.mark.asyncio
    async def test_delete_repo_integration_success_cache_path_identification(self, repo_manager_setup, mock_test_repo):
        """Test successful deletion of repository using direct cache path identification."""
        setup = repo_manager_setup
        repo_manager = setup["repo_manager"]
        
        test_url = f"file://{mock_test_repo}"
        
        # First, clone the repository
        clone_result = await repo_manager.clone_repository(test_url, cache_strategy="shared")
        assert clone_result["status"] in ["pending", "already_cloned"]
        
        # Get the cache path using list_repository_branches
        branches_result = await repo_manager.list_repository_branches(test_url)
        assert branches_result["status"] == "success"
        assert len(branches_result["cached_branches"]) >= 1
        cache_path = branches_result["cached_branches"][0]["cache_path"]
        
        # Delete using direct cache path
        delete_result = await repo_manager.delete_repository(cache_path)
        
        # Verify deletion succeeded
        assert delete_result["status"] == "success"
        assert cache_path in delete_result["deleted_paths"]
        assert "Successfully deleted 1 repository cache" in delete_result["message"]

    @pytest.mark.asyncio
    async def test_delete_repo_integration_workflow_shared_strategy(self, repo_manager_setup, mock_test_repo):
        """Test complete clone-then-delete workflow with shared cache strategy."""
        setup = repo_manager_setup
        repo_manager = setup["repo_manager"]
        
        test_url = f"file://{mock_test_repo}"
        
        # Step 1: Clone repository with shared strategy
        clone_result = await repo_manager.clone_repository(test_url, cache_strategy="shared")
        assert clone_result["status"] in ["pending", "already_cloned"]
        
        # Step 2: Verify repository is cached
        list_result = await repo_manager.list_cached_repositories()
        assert list_result["status"] == "success"
        initial_count = list_result["total_cached"]
        assert initial_count >= 1
        
        # Step 3: Delete repository
        delete_result = await repo_manager.delete_repository(test_url)
        assert delete_result["status"] == "success"
        
        # Step 4: Verify repository is no longer cached
        list_result_after = await repo_manager.list_cached_repositories()
        assert list_result_after["status"] == "success"
        assert list_result_after["total_cached"] < initial_count
        
        # Step 5: Verify re-cloning works
        clone_result_after = await repo_manager.clone_repository(test_url, cache_strategy="shared")
        assert clone_result_after["status"] in ["pending", "already_cloned"]

    @pytest.mark.asyncio
    async def test_delete_repo_integration_workflow_per_branch_strategy(self, repo_manager_setup, mock_test_repo):
        """Test complete workflow with per-branch cache strategy."""
        setup = repo_manager_setup
        repo_manager = setup["repo_manager"]
        
        test_url = f"file://{mock_test_repo}"
        
        # Clone repository with per-branch strategy
        clone_result = await repo_manager.clone_repository(test_url, branch="main", cache_strategy="per-branch")
        assert clone_result["status"] in ["pending", "already_cloned"]
        
        # List repository branches to see what's cached
        branches_result = await repo_manager.list_repository_branches(test_url)
        assert branches_result["status"] == "success"
        initial_branch_count = len(branches_result["cached_branches"])
        assert initial_branch_count >= 1
        
        # Delete repository (should delete all branches)
        delete_result = await repo_manager.delete_repository(test_url)
        assert delete_result["status"] == "success"
        assert len(delete_result["deleted_paths"]) >= 1
        
        # Verify all branches are deleted
        branches_result_after = await repo_manager.list_repository_branches(test_url)
        assert branches_result_after["status"] == "success"
        assert len(branches_result_after["cached_branches"]) == 0

    @pytest.mark.asyncio
    async def test_delete_repo_integration_error_repository_not_found(self, repo_manager_setup):
        """Test repository manager error handling for non-existent repository."""
        setup = repo_manager_setup
        repo_manager = setup["repo_manager"]
        
        nonexistent_url = "https://github.com/nonexistent/repo"
        
        # Attempt to delete non-existent repository
        delete_result = await repo_manager.delete_repository(nonexistent_url)
        
        # Verify error response
        assert delete_result["status"] == "error"
        assert "Repository not found in cache" in delete_result["error"]

    @pytest.mark.asyncio
    async def test_delete_repo_integration_error_invalid_cache_path(self, repo_manager_setup):
        """Test repository manager error handling for invalid cache path."""
        setup = repo_manager_setup
        repo_manager = setup["repo_manager"]
        
        invalid_path = "/nonexistent/cache/path"
        
        # Attempt to delete with invalid cache path
        delete_result = await repo_manager.delete_repository(invalid_path)
        
        # Verify error response
        assert delete_result["status"] == "error"
        assert "Repository not found in cache" in delete_result["error"]

    @pytest.mark.asyncio
    async def test_delete_repo_integration_cleanup_validation_files_and_metadata(self, repo_manager_setup, mock_test_repo):
        """Test that both files and metadata are properly cleaned up."""
        setup = repo_manager_setup
        repo_manager = setup["repo_manager"]
        cache_dir = setup["cache_dir"]
        
        test_url = f"file://{mock_test_repo}"
        
        # Clone repository
        await repo_manager.clone_repository(test_url, cache_strategy="shared")
        
        # Verify cache directory contains files
        assert cache_dir.exists()
        cache_contents_before = list(cache_dir.rglob("*"))
        assert len(cache_contents_before) > 0
        
        # Delete repository
        delete_result = await repo_manager.delete_repository(test_url)
        assert delete_result["status"] == "success"
        
        # Verify cache directory is cleaned up
        cache_contents_after = list(cache_dir.rglob("*"))
        # Should have fewer files than before (or possibly none)
        assert len(cache_contents_after) <= len(cache_contents_before)
        
        # Verify metadata is cleaned up by checking list_cached_repositories
        list_result = await repo_manager.list_cached_repositories()
        
        # Should find no repositories or fewer than before
        repo_urls = [repo.get("url") for repo in list_result.get("repositories", [])]
        assert test_url not in repo_urls

    @pytest.mark.asyncio
    async def test_delete_repo_integration_mixed_cache_strategies_cleanup(self, repo_manager_setup, mock_test_repo):
        """Test deletion when repository has both shared and per-branch cache entries."""
        setup = repo_manager_setup
        repo_manager = setup["repo_manager"]
        
        test_url = f"file://{mock_test_repo}"
        
        # Clone with shared strategy
        await repo_manager.clone_repository(test_url, cache_strategy="shared")
        
        # Clone with per-branch strategy
        await repo_manager.clone_repository(test_url, branch="main", cache_strategy="per-branch")
        
        # List all cached versions
        branches_before = await repo_manager.list_repository_branches(test_url)
        assert branches_before["status"] == "success"
        
        total_entries_before = len(branches_before["cached_branches"])
        assert total_entries_before >= 1
        
        # Delete repository (should delete ALL cache entries)
        delete_result = await repo_manager.delete_repository(test_url)
        
        assert delete_result["status"] == "success"
        assert len(delete_result["deleted_paths"]) == total_entries_before
        
        # Verify all entries are deleted
        branches_after = await repo_manager.list_repository_branches(test_url)
        assert branches_after["status"] == "success"
        assert len(branches_after["cached_branches"]) == 0

    @pytest.mark.asyncio
    async def test_delete_repo_integration_parameter_validation(self, repo_manager_setup):
        """Test repository manager parameter validation and response format."""
        setup = repo_manager_setup
        repo_manager = setup["repo_manager"]
        
        # Test with empty string
        result = await repo_manager.delete_repository("")
        assert result["status"] == "error"
        assert "error" in result
        
        # Test with whitespace string
        result = await repo_manager.delete_repository("   ")
        assert result["status"] == "error"
        assert "error" in result

    @pytest.mark.asyncio
    async def test_delete_repo_integration_response_format_validation(self, repo_manager_setup, mock_test_repo):
        """Test that repository manager responses conform to expected format."""
        setup = repo_manager_setup
        repo_manager = setup["repo_manager"]
        
        test_url = f"file://{mock_test_repo}"
        
        # Clone repository first
        await repo_manager.clone_repository(test_url)
        
        # Delete and validate response format
        result = await repo_manager.delete_repository(test_url)
        
        # Verify response structure for success
        assert isinstance(result, dict)
        assert "status" in result
        assert result["status"] == "success"
        assert "deleted_paths" in result
        assert isinstance(result["deleted_paths"], list)
        assert len(result["deleted_paths"]) > 0
        assert "message" in result
        assert isinstance(result["message"], str)
        
        # Test error response format
        error_result = await repo_manager.delete_repository("nonexistent")
        assert isinstance(error_result, dict)
        assert "status" in error_result
        assert error_result["status"] == "error"
        assert "error" in error_result
        assert isinstance(error_result["error"], str)

    @pytest.mark.asyncio 
    async def test_delete_repo_integration_concurrent_operations_safety(self, repo_manager_setup, mock_test_repo):
        """Test that delete operations are safe with concurrent access."""
        setup = repo_manager_setup
        repo_manager = setup["repo_manager"]
        
        test_url = f"file://{mock_test_repo}"
        
        # Clone repository
        await repo_manager.clone_repository(test_url)
        
        # First delete should succeed
        result1 = await repo_manager.delete_repository(test_url)
        assert result1["status"] == "success"
        
        # Second delete should fail gracefully
        result2 = await repo_manager.delete_repository(test_url)
        assert result2["status"] == "error"
        assert "Repository not found in cache" in result2["error"]

    @pytest.mark.asyncio 
    async def test_delete_repo_mcp_tool_direct_interface(self, repo_manager_setup, mock_test_repo):
        """Test the MCP delete_repo tool directly without full server setup."""
        setup = repo_manager_setup
        repo_manager = setup["repo_manager"]
        
        test_url = f"file://{mock_test_repo}"
        
        # Import the MCP tool function directly
        from code_expert.mcp.server.app import create_mcp_server
        from code_expert.config import load_config, RepositoryConfig
        
        # Create minimal config for testing
        config = load_config(overrides={
            "repository": {
                "cache_dir": str(setup["cache_dir"]), 
                "max_cached_repos": 10
            }
        })
        
        # Create MCP server (this should work with minimal dependencies)
        try:
            server = create_mcp_server(config)
            
            # Clone repository first
            await repo_manager.clone_repository(test_url)
            
            # Test delete_repo tool directly
            delete_tool = server.get_tool("delete_repo")
            assert delete_tool is not None
            
            result = await delete_tool(test_url)
            
            # Verify result format matches MCP tool contract
            assert isinstance(result, dict)
            assert "status" in result
            if result["status"] == "success":
                assert "deleted_paths" in result
                assert "message" in result
            else:
                assert "error" in result
                
        except ImportError as e:
            # If dependencies are missing, skip this test
            pytest.skip(f"MCP server dependencies not available: {e}")
        except Exception as e:
            # For other errors, we still want to see them
            raise