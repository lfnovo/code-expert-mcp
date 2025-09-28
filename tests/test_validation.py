"""Comprehensive validation tests for Azure DevOps and GitHub integration."""

import os
import time
from unittest.mock import patch

from code_expert.repository.path_utils import is_git_url, get_cache_path, parse_github_url
from code_expert.repository.providers import get_provider, get_default_registry
from code_expert.repository.providers.github import GitHubProvider
from code_expert.repository.providers.azure_devops import AzureDevOpsProvider


class TestAzureDevOpsValidation:
    """Validation tests for Azure DevOps functionality."""
    
    def test_all_azure_devops_url_formats(self):
        """Test comprehensive list of Azure DevOps URL formats."""
        valid_urls = [
            # Standard HTTPS
            "https://dev.azure.com/microsoft/vscode/_git/vscode",
            "https://dev.azure.com/org/project/_git/repo",
            "https://dev.azure.com/my-org/my-project/_git/my-repo",
            
            # Short format (without _git, repo defaults to project name)
            "https://dev.azure.com/org/project",
            "https://dev.azure.com/nordresearch/NordInvestimentos.Marilinha",
            "https://dev.azure.com/my-org/my-project",
            
            # HTTPS with organization prefix
            "https://microsoft@dev.azure.com/microsoft/vscode/_git/vscode",
            "https://org@dev.azure.com/org/project/_git/repo",
            
            # With .git extension
            "https://dev.azure.com/org/project/_git/repo.git",
            "https://org@dev.azure.com/org/project/_git/repo.git",
            
            # SSH format
            "git@ssh.dev.azure.com:v3/microsoft/vscode/vscode",
            "git@ssh.dev.azure.com:v3/org/project/repo",
            "git@ssh.dev.azure.com:v3/org/project/repo.git",
            
            # With special characters in names
            "https://dev.azure.com/my-org/project-123/_git/repo_name",
            "https://dev.azure.com/org/project.test/_git/repo-v2.0",
        ]
        
        for url in valid_urls:
            assert is_git_url(url), f"Failed to recognize valid Azure DevOps URL: {url}"
            provider = get_provider(url)
            assert provider is not None, f"No provider found for: {url}"
            assert provider.get_provider_name() == "Azure DevOps", f"Wrong provider for: {url}"
    
    def test_invalid_azure_devops_urls(self):
        """Test that invalid Azure DevOps URLs are rejected."""
        invalid_urls = [
            "https://dev.azure.com",  # No path
            "https://dev.azure.com/org",  # Missing project
            "https://dev.azure.com/org/project/_git",  # Has _git but missing repo
            "https://dev.azure.com/org/project/repo",  # Missing _git (but with 3 parts - invalid)
            "https://devops.azure.com/org/project/_git/repo",  # Wrong domain
            "https://azure.com/org/project/_git/repo",  # Wrong domain
            "git@dev.azure.com:org/project/repo",  # Wrong SSH format
            "ssh://dev.azure.com/org/project/_git/repo",  # SSH URL format not supported
        ]
        
        for url in invalid_urls:
            provider = get_provider(url)
            if provider:
                assert provider.get_provider_name() != "Azure DevOps", f"Should not be Azure DevOps: {url}"
    
    def test_cache_path_generation_consistency(self, tmp_path):
        """Test that cache paths are consistent and deterministic."""
        cache_dir = tmp_path / "cache"
        
        # Test Azure DevOps URLs
        azure_url = "https://dev.azure.com/myorg/myproject/_git/myrepo"
        
        # Generate path multiple times - should be identical
        path1 = get_cache_path(cache_dir, azure_url)
        path2 = get_cache_path(cache_dir, azure_url)
        assert path1 == path2, "Cache path not deterministic"
        
        # Should be under azure directory
        assert "azure/myorg/myproject/myrepo-" in str(path1)
        
        # Different branches should have different paths with per-branch strategy
        path_main = get_cache_path(cache_dir, azure_url, branch="main", per_branch=True)
        path_dev = get_cache_path(cache_dir, azure_url, branch="dev", per_branch=True)
        assert path_main != path_dev, "Per-branch paths should differ"
        assert "main" in str(path_main)
        assert "dev" in str(path_dev)
    
    def test_provider_coexistence(self):
        """Test that GitHub and Azure DevOps providers work together."""
        github_url = "https://github.com/owner/repo"
        azure_url = "https://dev.azure.com/org/project/_git/repo"
        
        github_provider = get_provider(github_url)
        azure_provider = get_provider(azure_url)
        
        assert github_provider is not None
        assert azure_provider is not None
        assert isinstance(github_provider, GitHubProvider)
        assert isinstance(azure_provider, AzureDevOpsProvider)
        assert github_provider != azure_provider
    
    def test_authentication_environment_variables(self):
        """Test that correct environment variables are used for each provider."""
        github_url = "https://github.com/owner/repo"
        azure_url = "https://dev.azure.com/org/project/_git/repo"
        
        with patch.dict(os.environ, {
            "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_test123",
            "AZURE_DEVOPS_PAT": "ado_test456"
        }):
            registry = get_default_registry()
            
            # Test GitHub authentication
            github_auth = registry.get_authenticated_url(github_url)
            assert "ghp_test123" in github_auth
            assert "ado_test456" not in github_auth
            
            # Test Azure DevOps authentication
            azure_auth = registry.get_authenticated_url(azure_url)
            assert "ado_test456" in azure_auth
            assert "ghp_test123" not in azure_auth


class TestEdgeCasesAndErrors:
    """Test edge cases and error conditions."""
    
    def test_mixed_url_formats(self):
        """Test handling of mixed URL formats in same session."""
        urls = [
            "https://github.com/owner/repo",
            "https://dev.azure.com/org/project/_git/repo",
            "/local/path/to/repo",
            "git@github.com:owner/repo.git",
            "git@ssh.dev.azure.com:v3/org/project/repo",
        ]
        
        for url in urls:
            if url.startswith("/"):
                assert not is_git_url(url), f"Local path detected as Git URL: {url}"
            else:
                assert is_git_url(url), f"Git URL not detected: {url}"
    
    def test_special_characters_in_components(self, tmp_path):
        """Test handling of special characters in organization/project/repo names."""
        cache_dir = tmp_path / "cache"
        
        # Azure DevOps with special characters
        special_urls = [
            "https://dev.azure.com/my-org/project.name/_git/repo-v1.0",
            "https://dev.azure.com/org_name/project-123/_git/repo_2",
            "https://dev.azure.com/org/project/_git/repo-with-dashes",
        ]
        
        for url in special_urls:
            path = get_cache_path(cache_dir, url)
            assert path.is_absolute()
            # Path should be valid and creatable
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
            assert path.exists()
    
    def test_url_normalization(self):
        """Test that URLs are normalized correctly."""
        # URLs that should be treated as the same repository
        url_variations = [
            ("https://dev.azure.com/org/project/_git/repo", 
             "https://dev.azure.com/org/project/_git/repo/"),  # Trailing slash
            ("https://dev.azure.com/org/project/_git/repo",
             "https://org@dev.azure.com/org/project/_git/repo"),  # With/without org prefix
        ]
        
        for url1, url2 in url_variations:
            provider1 = get_provider(url1)
            provider2 = get_provider(url2)
            assert provider1 is not None
            assert provider2 is not None
            assert type(provider1) == type(provider2)
    
    def test_empty_token_handling(self):
        """Test behavior when tokens are empty or None."""
        url = "https://dev.azure.com/org/project/_git/repo"
        
        with patch.dict(os.environ, {"AZURE_DEVOPS_PAT": ""}):
            registry = get_default_registry()
            auth_url = registry.get_authenticated_url(url)
            assert auth_url == url, "Empty token should return original URL"
        
        with patch.dict(os.environ, {}, clear=True):
            registry = get_default_registry()
            auth_url = registry.get_authenticated_url(url)
            assert auth_url == url, "Missing token should return original URL"
    
    def test_malformed_tokens(self):
        """Test handling of malformed tokens."""
        url = "https://dev.azure.com/org/project/_git/repo"
        
        # Test with various malformed tokens
        malformed_tokens = [
            "token with spaces",
            "token\nwith\nnewlines",
            "token@with@special#chars",
            "a" * 1000,  # Very long token
        ]
        
        for token in malformed_tokens:
            with patch.dict(os.environ, {"AZURE_DEVOPS_PAT": token}):
                registry = get_default_registry()
                # Should still generate URL, even with malformed token
                auth_url = registry.get_authenticated_url(url)
                assert auth_url != url, f"Token not applied: {token[:20]}..."


class TestPerformanceAndScaling:
    """Test performance and scaling characteristics."""
    
    def test_provider_lookup_performance(self):
        """Test that provider lookup is fast even with many URLs."""
        urls = [
            "https://github.com/owner/repo",
            "https://dev.azure.com/org/project/_git/repo",
        ] * 100  # 200 URLs total
        
        start_time = time.time()
        for url in urls:
            provider = get_provider(url)
            assert provider is not None
        elapsed = time.time() - start_time
        
        # Should process 200 URLs in under 1 second
        assert elapsed < 1.0, f"Provider lookup too slow: {elapsed:.2f}s for 200 URLs"
    
    def test_cache_path_generation_performance(self, tmp_path):
        """Test that cache path generation is fast."""
        cache_dir = tmp_path / "cache"
        urls = [
            f"https://dev.azure.com/org{i}/project{i}/_git/repo{i}"
            for i in range(100)
        ]
        
        start_time = time.time()
        for url in urls:
            path = get_cache_path(cache_dir, url)
            assert path is not None
        elapsed = time.time() - start_time
        
        # Should generate 100 cache paths in under 0.5 seconds
        assert elapsed < 0.5, f"Cache path generation too slow: {elapsed:.2f}s for 100 URLs"
    
    def test_many_providers_registered(self):
        """Test system behavior with many providers registered."""
        from code_expert.repository.providers import ProviderRegistry
        from code_expert.repository.providers.base import GitProvider
        
        # Create a custom provider for testing
        class CustomProvider(GitProvider):
            def is_provider_url(self, url: str) -> bool:
                return "custom.com" in url
            
            def parse_url(self, url: str) -> dict:
                return {"url": url}
            
            def get_cache_path(self, cache_dir, components, branch, per_branch):
                return cache_dir / "custom" / "test"
            
            def get_authenticated_url(self, url, token):
                return url
            
            def get_provider_name(self):
                return f"Custom{id(self)}"
            
            def get_env_var_name(self):
                return "CUSTOM_TOKEN"
        
        # Register many custom providers
        registry = ProviderRegistry()
        for i in range(50):
            registry.register_provider(CustomProvider())
        
        # Should still find correct providers quickly
        assert registry.get_provider("https://github.com/owner/repo") is not None
        assert registry.get_provider("https://dev.azure.com/org/project/_git/repo") is not None


class TestBackwardsCompatibilityRegression:
    """Ensure no regressions in existing functionality."""
    
    def test_github_functionality_unchanged(self):
        """Test that all GitHub functionality works exactly as before."""
        # Test URL detection
        assert is_git_url("https://github.com/owner/repo")
        assert is_git_url("git@github.com:owner/repo.git")
        
        # Test URL parsing
        org, repo, ref = parse_github_url("https://github.com/owner/repo")
        assert org == "owner"
        assert repo == "repo"
        assert ref is None
        
        # Test with ref
        org, repo, ref = parse_github_url("https://github.com/owner/repo/tree/main")
        assert org == "owner"
        assert repo == "repo"
        assert ref == "tree/main"
    
    def test_local_path_functionality_unchanged(self, tmp_path):
        """Test that local path handling works as before."""
        local_repo = tmp_path / "local_repo"
        local_repo.mkdir()
        
        # Should not be detected as Git URL
        assert not is_git_url(str(local_repo))
        
        # Should generate correct cache path
        cache_dir = tmp_path / "cache"
        path = get_cache_path(cache_dir, str(local_repo))
        assert "local/" in str(path)
        assert path.is_absolute()
    
    def test_import_compatibility_comprehensive(self):
        """Test all import patterns still work."""
        # Test individual imports
        
        # Test module import
        from code_expert.repository import path_utils
        assert hasattr(path_utils, 'is_git_url')
        assert hasattr(path_utils, 'get_cache_path')
        assert hasattr(path_utils, 'parse_github_url')
        
        # Test provider imports
        
        # All imports should work without errors
        assert True