import sys
import pytest
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from code_expert.repository import Repository
from code_expert.repository.manager import RepositoryManager
from code_expert.config import RepositoryConfig


@pytest.fixture
def repo_with_gitignore(tmp_path):
    """Create a test repository with .gitignore."""
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()

    # Create .gitignore
    gitignore = repo_dir / ".gitignore"
    gitignore.write_text("*.pyc\n__pycache__/\nnode_modules/\n*.log")

    # Create test files
    (repo_dir / "main.py").touch()
    (repo_dir / "main.pyc").touch()
    pycache_dir = repo_dir / "__pycache__"
    pycache_dir.mkdir()
    (pycache_dir / "cache.pyc").touch()
    (repo_dir / "app.log").touch()

    return repo_dir


def test_gitignore_filtering(repo_with_gitignore):
    """Test that files are correctly filtered based on .gitignore patterns."""
    repo = Repository(
        repo_id="test", root_path=repo_with_gitignore, repo_type="local", is_git=False
    )

    # Test individual file checks
    assert not repo.is_ignored("main.py")
    assert repo.is_ignored("main.pyc")
    assert repo.is_ignored("__pycache__/cache.pyc")
    assert repo.is_ignored("app.log")
    assert repo.is_ignored("node_modules/package.json")

    # Test with Path objects
    assert not repo.is_ignored(Path("main.py"))
    assert repo.is_ignored(Path("main.pyc"))

    # Test with absolute paths
    abs_path = repo_with_gitignore / "main.pyc"
    assert repo.is_ignored(abs_path)


def test_gitignore_dynamic_update(repo_with_gitignore):
    """Test that gitignore changes are picked up without needing a new instance."""
    repo = Repository(
        repo_id="test", root_path=repo_with_gitignore, repo_type="local", is_git=False
    )

    # Initially .md files are not ignored
    assert not repo.is_ignored("README.md")

    # Add *.md to .gitignore
    gitignore_path = repo_with_gitignore / ".gitignore"
    with open(gitignore_path, "a") as f:
        f.write("\n*.md\n")

    # Should pick up the new pattern
    assert repo.is_ignored("README.md")


def test_no_gitignore_file(tmp_path):
    """Test behavior when no .gitignore file exists."""
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()
    (repo_dir / "main.py").touch()

    repo = Repository(
        repo_id="test", root_path=repo_dir, repo_type="local", is_git=False
    )

    # Nothing should be ignored when no .gitignore exists
    assert not repo.is_ignored("main.py")
    assert not repo.is_ignored("main.pyc")
    assert not repo.is_ignored("__pycache__/cache.pyc")


@pytest.fixture
def mock_config(tmp_path):
    """Create a mock RepositoryConfig for testing."""
    config = Mock(spec=RepositoryConfig)
    config.max_cached_repos = 10
    config.get_cache_dir_path.return_value = tmp_path / "cache"
    return config


@pytest.fixture
def mock_cache():
    """Create a mock RepositoryCache for testing."""
    cache = Mock()
    cache.remove_repo = AsyncMock()
    cache._file_lock = Mock()
    cache._read_metadata = Mock()
    cache._write_metadata = Mock()
    return cache


@pytest.fixture
def repository_manager(mock_config, mock_cache):
    """Create a RepositoryManager instance with mocked dependencies."""
    with patch('code_expert.repository.manager.RepositoryCache') as MockCache:
        MockCache.return_value = mock_cache
        manager = RepositoryManager(mock_config)
        manager.cache = mock_cache
        return manager


class TestDeleteRepository:
    """Test cases for the delete_repository method."""
    
    @pytest.fixture
    def mock_cache_dir(self, tmp_path):
        """Create a mock cache directory for path validation tests."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        return cache_dir
    
    @pytest.mark.asyncio
    async def test_delete_repository_url_based_success(self, repository_manager, mock_cache):
        """Test successful deletion of repository using URL with multiple cache entries."""
        repo_url = "https://github.com/user/repo.git"
        cache_path1 = "/cache/path1"
        cache_path2 = "/cache/path2"
        
        # Mock list_repository_branches to return multiple cache entries
        branches_result = {
            "status": "success",
            "cached_branches": [
                {"cache_path": cache_path1, "requested_branch": "main"},
                {"cache_path": cache_path2, "requested_branch": "dev"}
            ]
        }
        
        with patch.object(repository_manager, 'list_repository_branches', return_value=branches_result):
            # Mock cache.remove_repo to succeed
            mock_cache.remove_repo = AsyncMock()
            
            result = await repository_manager.delete_repository(repo_url)
            
            # Verify the result with updated message format
            assert result["status"] == "success"
            assert len(result["deleted_paths"]) == 2
            assert cache_path1 in result["deleted_paths"]
            assert cache_path2 in result["deleted_paths"]
            assert "Successfully deleted 2 cache entries for repository" in result["message"]
            assert repo_url in result["message"]
            
            # Verify cache.remove_repo was called for each path
            assert mock_cache.remove_repo.call_count == 2
            mock_cache.remove_repo.assert_any_call(cache_path1)
            mock_cache.remove_repo.assert_any_call(cache_path2)

    @pytest.mark.asyncio
    async def test_delete_repository_url_based_single_entry(self, repository_manager, mock_cache):
        """Test successful deletion of repository using URL with single cache entry."""
        repo_url = "https://github.com/user/repo.git"
        cache_path = "/cache/path"
        
        # Mock list_repository_branches to return single cache entry
        branches_result = {
            "status": "success",
            "cached_branches": [
                {"cache_path": cache_path, "requested_branch": "main"}
            ]
        }
        
        with patch.object(repository_manager, 'list_repository_branches', return_value=branches_result):
            # Mock cache.remove_repo to succeed
            mock_cache.remove_repo = AsyncMock()
            
            result = await repository_manager.delete_repository(repo_url)
            
            # Verify the result with updated message format
            assert result["status"] == "success"
            assert len(result["deleted_paths"]) == 1
            assert cache_path in result["deleted_paths"]
            assert "Successfully deleted 1 cache entries for repository" in result["message"]
            assert repo_url in result["message"]
            
            # Verify cache.remove_repo was called once
            mock_cache.remove_repo.assert_called_once_with(cache_path)

    @pytest.mark.asyncio
    async def test_delete_repository_cache_path_success(self, repository_manager, mock_cache, mock_cache_dir):
        """Test successful deletion using direct cache path."""
        # Create a valid cache path within the cache directory
        cache_subdir = mock_cache_dir / "github" / "user" / "repo"
        cache_subdir.mkdir(parents=True)
        git_dir = cache_subdir / ".git"
        git_dir.mkdir()
        
        cache_path = str(cache_subdir)
        
        # Mock repository_manager.cache_dir to return our mock cache directory
        repository_manager.cache_dir = mock_cache_dir
        
        # Mock cache.remove_repo to succeed
        mock_cache.remove_repo = AsyncMock()
        
        result = await repository_manager.delete_repository(cache_path)
        
        # Verify the result
        assert result["status"] == "success"
        assert len(result["deleted_paths"]) == 1
        assert cache_path in result["deleted_paths"]
        assert f"Successfully deleted repository cache at {cache_path}" in result["message"]
        
        # Verify cache.remove_repo was called once
        mock_cache.remove_repo.assert_called_once_with(cache_path)

    @pytest.mark.asyncio
    async def test_delete_repository_cache_path_is_file(self, repository_manager, mock_cache, tmp_path):
        """Test deletion when cache path exists but is a file, not directory."""
        # Create a file instead of directory
        cache_file = tmp_path / "cache_file.txt"
        cache_file.write_text("not a directory")
        
        cache_path = str(cache_file)
        
        # Mock list_repository_branches to return no results
        branches_result = {
            "status": "success",
            "cached_branches": []
        }
        
        with patch.object(repository_manager, 'list_repository_branches', return_value=branches_result):
            result = await repository_manager.delete_repository(cache_path)
            
            # Verify the result shows repository not found
            assert result["status"] == "error"
            assert "No cached entries found for repository" in result["error"]
            
            # Verify cache.remove_repo was not called
            mock_cache.remove_repo.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_repository_url_not_found(self, repository_manager, mock_cache):
        """Test deletion when repository URL is not found in cache."""
        repo_url = "https://github.com/nonexistent/repo.git"
        
        # Mock list_repository_branches to return no results
        branches_result = {
            "status": "success",
            "cached_branches": []
        }
        
        with patch.object(repository_manager, 'list_repository_branches', return_value=branches_result):
            result = await repository_manager.delete_repository(repo_url)
            
            # Verify the result with updated error message
            assert result["status"] == "error"
            assert "No cached entries found for repository" in result["error"]
            assert repo_url in result["error"]
            
            # Verify cache.remove_repo was not called
            mock_cache.remove_repo.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_repository_url_list_branches_error(self, repository_manager, mock_cache):
        """Test deletion when list_repository_branches returns an error."""
        repo_url = "https://github.com/user/repo.git"
        
        # Mock list_repository_branches to return error
        branches_result = {
            "status": "error",
            "error": "Failed to access metadata"
        }
        
        with patch.object(repository_manager, 'list_repository_branches', return_value=branches_result):
            result = await repository_manager.delete_repository(repo_url)
            
            # Verify the result with updated error message format
            assert result["status"] == "error"
            assert "Failed to query repository cache: Failed to access metadata" in result["error"]
            
            # Verify cache.remove_repo was not called
            mock_cache.remove_repo.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_repository_cache_remove_exception(self, repository_manager, mock_cache, mock_cache_dir):
        """Test handling of exception during cache.remove_repo for direct path."""
        # Create a valid cache path within the cache directory
        cache_subdir = mock_cache_dir / "github" / "user" / "repo"
        cache_subdir.mkdir(parents=True)
        git_dir = cache_subdir / ".git"
        git_dir.mkdir()
        
        cache_path = str(cache_subdir)
        
        # Mock repository_manager.cache_dir to return our mock cache directory
        repository_manager.cache_dir = mock_cache_dir
        
        # Mock cache.remove_repo to raise exception
        mock_cache.remove_repo = AsyncMock(side_effect=Exception("Permission denied"))
        
        result = await repository_manager.delete_repository(cache_path)
        
        # Verify the result shows error with updated message format
        assert result["status"] == "error"
        assert "Permission denied" in result["error"]
        
        # Verify cache.remove_repo was called
        mock_cache.remove_repo.assert_called_once_with(cache_path)

    @pytest.mark.asyncio
    async def test_delete_repository_url_partial_failure(self, repository_manager, mock_cache):
        """Test partial failure when some cache entries fail to delete."""
        repo_url = "https://github.com/user/repo.git"
        cache_path1 = "/cache/path1"
        cache_path2 = "/cache/path2"
        cache_path3 = "/cache/path3"
        
        # Mock list_repository_branches to return multiple cache entries
        branches_result = {
            "status": "success",
            "cached_branches": [
                {"cache_path": cache_path1, "requested_branch": "main"},
                {"cache_path": cache_path2, "requested_branch": "dev"},
                {"cache_path": cache_path3, "requested_branch": "feature"}
            ]
        }
        
        with patch.object(repository_manager, 'list_repository_branches', return_value=branches_result):
            # Mock cache.remove_repo to succeed for some, fail for others
            async def mock_remove_repo(path):
                if path == cache_path2:
                    raise Exception("Permission denied")
                return None
            
            mock_cache.remove_repo = AsyncMock(side_effect=mock_remove_repo)
            
            result = await repository_manager.delete_repository(repo_url)
            
            # Verify the result shows success for the successful deletions with updated message format
            assert result["status"] == "success"
            assert len(result["deleted_paths"]) == 2
            assert cache_path1 in result["deleted_paths"]
            assert cache_path3 in result["deleted_paths"]
            assert cache_path2 not in result["deleted_paths"]
            assert "Successfully deleted 2 cache entries for repository" in result["message"]
            assert "(1 entries failed to delete)" in result["message"]
            assert repo_url in result["message"]
            
            # Verify cache.remove_repo was called for all paths
            assert mock_cache.remove_repo.call_count == 3

    @pytest.mark.asyncio
    async def test_delete_repository_url_all_failures(self, repository_manager, mock_cache):
        """Test when all cache entry deletions fail."""
        repo_url = "https://github.com/user/repo.git"
        cache_path1 = "/cache/path1"
        cache_path2 = "/cache/path2"
        
        # Mock list_repository_branches to return multiple cache entries
        branches_result = {
            "status": "success",
            "cached_branches": [
                {"cache_path": cache_path1, "requested_branch": "main"},
                {"cache_path": cache_path2, "requested_branch": "dev"}
            ]
        }
        
        with patch.object(repository_manager, 'list_repository_branches', return_value=branches_result):
            # Mock cache.remove_repo to always fail
            mock_cache.remove_repo = AsyncMock(side_effect=Exception("Permission denied"))
            
            result = await repository_manager.delete_repository(repo_url)
            
            # Verify the result shows error with updated message format
            assert result["status"] == "error"
            assert "Failed to delete all cache entries for repository" in result["error"]
            assert repo_url in result["error"]
            
            # Verify cache.remove_repo was called for all paths
            assert mock_cache.remove_repo.call_count == 2

    @pytest.mark.asyncio
    async def test_delete_repository_in_memory_cleanup(self, repository_manager, mock_cache, mock_cache_dir):
        """Test that in-memory repository references are cleaned up."""
        # Create a valid cache path within the cache directory
        cache_subdir = mock_cache_dir / "github" / "user" / "repo"
        cache_subdir.mkdir(parents=True)
        git_dir = cache_subdir / ".git"
        git_dir.mkdir()
        
        cache_path = str(cache_subdir)
        
        # Mock repository_manager.cache_dir to return our mock cache directory
        repository_manager.cache_dir = mock_cache_dir
        
        # Add some in-memory repositories
        repository_manager.repositories[cache_path] = Mock()
        repository_manager.repositories["/other/path"] = Mock()
        
        # Mock cache.remove_repo to succeed
        mock_cache.remove_repo = AsyncMock()
        
        result = await repository_manager.delete_repository(cache_path)
        
        # Verify the result
        assert result["status"] == "success"
        
        # Verify in-memory reference was removed
        assert cache_path not in repository_manager.repositories
        assert "/other/path" in repository_manager.repositories  # Other references should remain

    @pytest.mark.asyncio
    async def test_delete_repository_multiple_in_memory_cleanup(self, repository_manager, mock_cache):
        """Test cleanup of multiple in-memory repository references."""
        repo_url = "https://github.com/user/repo.git"
        cache_path1 = "/cache/path1"
        cache_path2 = "/cache/path2"
        
        # Add in-memory repositories
        repository_manager.repositories[cache_path1] = Mock()
        repository_manager.repositories[cache_path2] = Mock()
        repository_manager.repositories["/other/path"] = Mock()
        
        # Mock list_repository_branches to return multiple cache entries
        branches_result = {
            "status": "success",
            "cached_branches": [
                {"cache_path": cache_path1, "requested_branch": "main"},
                {"cache_path": cache_path2, "requested_branch": "dev"}
            ]
        }
        
        with patch.object(repository_manager, 'list_repository_branches', return_value=branches_result):
            # Mock cache.remove_repo to succeed
            mock_cache.remove_repo = AsyncMock()
            
            result = await repository_manager.delete_repository(repo_url)
            
            # Verify the result
            assert result["status"] == "success"
            
            # Verify in-memory references were removed
            assert cache_path1 not in repository_manager.repositories
            assert cache_path2 not in repository_manager.repositories
            assert "/other/path" in repository_manager.repositories  # Other references should remain

    @pytest.mark.asyncio
    async def test_delete_repository_unexpected_exception(self, repository_manager):
        """Test handling of unexpected exceptions during deletion."""
        repo_identifier = "https://github.com/user/repo.git"
        
        # Mock Path to raise an unexpected exception
        with patch('code_expert.repository.manager.Path', side_effect=Exception("Unexpected error")):
            result = await repository_manager.delete_repository(repo_identifier)
            
            # Verify the result shows error
            assert result["status"] == "error"
            assert "Unexpected error" in result["error"]

    @pytest.mark.asyncio
    async def test_delete_repository_shared_cache_strategy(self, repository_manager, mock_cache):
        """Test deletion works with shared cache strategy."""
        repo_url = "https://github.com/user/repo.git"
        cache_path = "/cache/shared/path"
        
        # Mock list_repository_branches to return cache entry with shared strategy
        branches_result = {
            "status": "success",
            "cached_branches": [
                {
                    "cache_path": cache_path, 
                    "requested_branch": "main",
                    "cache_strategy": "shared"
                }
            ]
        }
        
        with patch.object(repository_manager, 'list_repository_branches', return_value=branches_result):
            # Mock cache.remove_repo to succeed
            mock_cache.remove_repo = AsyncMock()
            
            result = await repository_manager.delete_repository(repo_url)
            
            # Verify the result
            assert result["status"] == "success"
            assert len(result["deleted_paths"]) == 1
            assert cache_path in result["deleted_paths"]

    @pytest.mark.asyncio
    async def test_delete_repository_per_branch_cache_strategy(self, repository_manager, mock_cache):
        """Test deletion works with per-branch cache strategy."""
        repo_url = "https://github.com/user/repo.git"
        cache_path1 = "/cache/main/path"
        cache_path2 = "/cache/dev/path"
        
        # Mock list_repository_branches to return cache entries with per-branch strategy
        branches_result = {
            "status": "success",
            "cached_branches": [
                {
                    "cache_path": cache_path1, 
                    "requested_branch": "main",
                    "cache_strategy": "per-branch"
                },
                {
                    "cache_path": cache_path2, 
                    "requested_branch": "dev",
                    "cache_strategy": "per-branch"
                }
            ]
        }
        
        with patch.object(repository_manager, 'list_repository_branches', return_value=branches_result):
            # Mock cache.remove_repo to succeed
            mock_cache.remove_repo = AsyncMock()
            
            result = await repository_manager.delete_repository(repo_url)
            
            # Verify the result
            assert result["status"] == "success"
            assert len(result["deleted_paths"]) == 2
            assert cache_path1 in result["deleted_paths"]
            assert cache_path2 in result["deleted_paths"]

    @pytest.mark.asyncio
    async def test_delete_repository_empty_string_identifier(self, repository_manager):
        """Test handling of empty string identifier."""
        result = await repository_manager.delete_repository("")
        
        # Verify the result shows error with new error message
        assert result["status"] == "error"
        assert result["error"] == "Repository identifier cannot be empty"
        
    @pytest.mark.asyncio
    async def test_delete_repository_none_identifier(self, repository_manager):
        """Test handling of None identifier."""
        result = await repository_manager.delete_repository(None)
        
        # Verify the result shows error with new error message
        assert result["status"] == "error"
        assert result["error"] == "Repository identifier cannot be empty"
    
    @pytest.mark.asyncio
    async def test_delete_repository_whitespace_identifier(self, repository_manager):
        """Test handling of whitespace-only identifier."""
        result = await repository_manager.delete_repository("   \n\t  ")
        
        # Verify the result shows error with new error message
        assert result["status"] == "error"
        assert result["error"] == "Repository identifier cannot be empty"

    @pytest.mark.asyncio
    async def test_delete_repository_list_branches_exception(self, repository_manager, mock_cache):
        """Test handling of exception from list_repository_branches."""
        repo_url = "https://github.com/user/repo.git"
        
        with patch.object(repository_manager, 'list_repository_branches', side_effect=Exception("Metadata error")):
            # Mock Path.exists to return False for direct path check
            with patch('code_expert.repository.manager.Path') as MockPath:
                mock_path_instance = Mock()
                mock_path_instance.exists.return_value = False
                MockPath.return_value = mock_path_instance
                
                result = await repository_manager.delete_repository(repo_url)
                
                # Verify the result shows error
                assert result["status"] == "error"
                assert "Metadata error" in result["error"]
    
    # New tests for path validation
    @pytest.mark.asyncio
    async def test_delete_repository_path_outside_cache_directory(self, repository_manager, mock_cache, tmp_path):
        """Test rejection of paths outside the cache directory."""
        # Create a directory outside the cache directory
        outside_dir = tmp_path / "outside" / "repo"
        outside_dir.mkdir(parents=True)
        git_dir = outside_dir / ".git"
        git_dir.mkdir()
        
        # Mock repository_manager.cache_dir to a different directory
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        repository_manager.cache_dir = cache_dir
        
        result = await repository_manager.delete_repository(str(outside_dir))
        
        # Verify the result shows validation error
        assert result["status"] == "error"
        assert "Invalid cache path: not within repository cache directory" in result["error"]
        
        # Verify cache.remove_repo was not called
        mock_cache.remove_repo.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_delete_repository_path_no_repository_markers(self, repository_manager, mock_cache, mock_cache_dir):
        """Test rejection of paths without repository markers (.git or cache structure)."""
        # Create a directory within cache but without .git or cache structure markers
        cache_subdir = mock_cache_dir / "random" / "directory"
        cache_subdir.mkdir(parents=True)
        
        cache_path = str(cache_subdir)
        
        # Mock repository_manager.cache_dir to return our mock cache directory
        repository_manager.cache_dir = mock_cache_dir
        
        result = await repository_manager.delete_repository(cache_path)
        
        # Verify the result shows validation error
        assert result["status"] == "error"
        assert "Invalid cache path: directory does not appear to be a repository cache" in result["error"]
        
        # Verify cache.remove_repo was not called
        mock_cache.remove_repo.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_delete_repository_path_with_cache_structure_marker(self, repository_manager, mock_cache, mock_cache_dir):
        """Test acceptance of paths with cache structure markers (github, git, local, azure parents)."""
        # Create a directory within cache with cache structure marker
        cache_subdir = mock_cache_dir / "github" / "user" / "repo"
        cache_subdir.mkdir(parents=True)
        # Note: no .git directory, but has 'github' parent which is a cache structure marker
        
        cache_path = str(cache_subdir)
        
        # Mock repository_manager.cache_dir to return our mock cache directory
        repository_manager.cache_dir = mock_cache_dir
        
        # Mock cache.remove_repo to succeed
        mock_cache.remove_repo = AsyncMock()
        
        result = await repository_manager.delete_repository(cache_path)
        
        # Verify the result shows success
        assert result["status"] == "success"
        assert len(result["deleted_paths"]) == 1
        assert cache_path in result["deleted_paths"]
        
        # Verify cache.remove_repo was called
        mock_cache.remove_repo.assert_called_once_with(cache_path)
    
    @pytest.mark.asyncio
    async def test_delete_repository_path_validation_os_error(self, repository_manager, mock_cache, mock_cache_dir):
        """Test handling of OS errors during path validation."""
        # Create a valid cache path within the cache directory
        cache_subdir = mock_cache_dir / "github" / "user" / "repo"
        cache_subdir.mkdir(parents=True)
        git_dir = cache_subdir / ".git"
        git_dir.mkdir()
        
        cache_path = str(cache_subdir)
        
        # Mock repository_manager.cache_dir to return our mock cache directory
        repository_manager.cache_dir = mock_cache_dir
        
        # Mock is_relative_to to raise OSError
        with patch('pathlib.Path.is_relative_to', side_effect=OSError("Permission denied")):
            result = await repository_manager.delete_repository(cache_path)
            
            # Verify the result shows validation error
            assert result["status"] == "error"
            assert "Invalid cache path: Permission denied" in result["error"]
            
            # Verify cache.remove_repo was not called
            mock_cache.remove_repo.assert_not_called()
    
    # Tests for KeyError race condition handling
    @pytest.mark.asyncio
    async def test_delete_repository_keyerror_race_condition_direct_path(self, repository_manager, mock_cache, mock_cache_dir):
        """Test handling of KeyError race condition when removing in-memory reference for direct path."""
        # Create a valid cache path within the cache directory
        cache_subdir = mock_cache_dir / "github" / "user" / "repo"
        cache_subdir.mkdir(parents=True)
        git_dir = cache_subdir / ".git"
        git_dir.mkdir()
        
        cache_path = str(cache_subdir)
        
        # Mock repository_manager.cache_dir to return our mock cache directory
        repository_manager.cache_dir = mock_cache_dir
        
        # Add an in-memory repository first
        repository_manager.repositories[cache_path] = Mock()
        
        # Create a custom dictionary class that simulates race condition
        class RaceConditionDict(dict):
            def __delitem__(self, key):
                if key == cache_path:
                    # Remove from underlying dict first to simulate race condition
                    super().__delitem__(key)
                    raise KeyError(key)  # Then raise KeyError to simulate race condition
                super().__delitem__(key)
        
        # Replace repositories dict with our custom race condition dict
        original_repos = repository_manager.repositories.copy()
        repository_manager.repositories = RaceConditionDict(original_repos)
        
        # Mock cache.remove_repo to succeed
        mock_cache.remove_repo = AsyncMock()
        
        result = await repository_manager.delete_repository(cache_path)
        
        # Verify the result still shows success despite KeyError
        assert result["status"] == "success"
        assert len(result["deleted_paths"]) == 1
        assert cache_path in result["deleted_paths"]
        
        # Verify cache.remove_repo was called
        mock_cache.remove_repo.assert_called_once_with(cache_path)
        
        # Verify the repository was actually removed from the dict (race condition handled)
        assert cache_path not in repository_manager.repositories
    
    @pytest.mark.asyncio
    async def test_delete_repository_keyerror_race_condition_url_based(self, repository_manager, mock_cache):
        """Test handling of KeyError race condition when removing in-memory references for URL-based deletion."""
        repo_url = "https://github.com/user/repo.git"
        cache_path1 = "/cache/path1"
        cache_path2 = "/cache/path2"
        
        # Mock list_repository_branches to return multiple cache entries
        branches_result = {
            "status": "success",
            "cached_branches": [
                {"cache_path": cache_path1, "requested_branch": "main"},
                {"cache_path": cache_path2, "requested_branch": "dev"}
            ]
        }
        
        # Add in-memory repositories
        repository_manager.repositories[cache_path1] = Mock()
        repository_manager.repositories[cache_path2] = Mock()
        
        # Create a custom dictionary class that simulates race condition for cache_path2
        class RaceConditionDict(dict):
            def __delitem__(self, key):
                if key == cache_path2:
                    # Remove from underlying dict first to simulate another thread removing it
                    super().__delitem__(key)
                    raise KeyError(key)  # Then raise KeyError to simulate race condition
                super().__delitem__(key)
        
        # Replace repositories dict with our custom race condition dict
        original_repos = repository_manager.repositories.copy()
        repository_manager.repositories = RaceConditionDict(original_repos)
        
        with patch.object(repository_manager, 'list_repository_branches', return_value=branches_result):
            # Mock cache.remove_repo to succeed
            mock_cache.remove_repo = AsyncMock()
            
            result = await repository_manager.delete_repository(repo_url)
            
            # Verify the result shows success despite KeyError
            assert result["status"] == "success"
            assert len(result["deleted_paths"]) == 2
            assert cache_path1 in result["deleted_paths"]
            assert cache_path2 in result["deleted_paths"]
            
            # Verify cache.remove_repo was called for both paths
            assert mock_cache.remove_repo.call_count == 2
            
            # Verify both repositories were removed (race condition handled gracefully)
            assert cache_path1 not in repository_manager.repositories
            assert cache_path2 not in repository_manager.repositories
