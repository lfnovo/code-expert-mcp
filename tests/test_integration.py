"""Integration tests for provider framework with existing code."""

import os
from pathlib import Path
import pytest
from unittest.mock import patch

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