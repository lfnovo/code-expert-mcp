"""
Comprehensive unit tests for the Git provider framework.

This module tests the Git provider framework components:
- GitHub provider implementation
- Provider registry functionality
- Edge cases and error handling
"""

import pytest
import tempfile
import hashlib
from pathlib import Path
from unittest.mock import Mock, patch

from code_expert.repository.providers.base import GitProvider
from code_expert.repository.providers.github import GitHubProvider
from code_expert.repository.providers.registry import ProviderRegistry, get_default_registry, register_provider, get_provider


class TestGitHubProvider:
    """Test suite for GitHub provider implementation."""
    
    def setup_method(self):
        """Set up test fixtures for each test method."""
        self.provider = GitHubProvider()
    
    def test_provider_name(self):
        """Test provider name is correctly returned."""
        assert self.provider.get_provider_name() == "GitHub"
    
    def test_environment_variable_name(self):
        """Test environment variable name is correctly returned."""
        assert self.provider.get_env_var_name() == "GITHUB_PERSONAL_ACCESS_TOKEN"


class TestGitHubProviderUrlDetection:
    """Test GitHub URL detection for various URL formats."""
    
    def setup_method(self):
        """Set up test fixtures for each test method."""
        self.provider = GitHubProvider()
    
    def test_is_provider_url_https_github(self):
        """Test detection of HTTPS GitHub URLs."""
        valid_urls = [
            "https://github.com/owner/repo",
            "https://github.com/owner/repo.git",
            "https://github.com/owner/repo/tree/main",
            "http://github.com/owner/repo",  # HTTP should also work
        ]
        
        for url in valid_urls:
            assert self.provider.is_provider_url(url), f"Should detect {url} as GitHub URL"
    
    def test_is_provider_url_ssh_github(self):
        """Test detection of SSH GitHub URLs."""
        valid_urls = [
            "git@github.com:owner/repo.git",
            "git@github.com:owner/repo",
            "git@github.com:organization/project.git",
        ]
        
        for url in valid_urls:
            assert self.provider.is_provider_url(url), f"Should detect {url} as GitHub URL"
    
    def test_is_provider_url_non_github(self):
        """Test rejection of non-GitHub URLs."""
        invalid_urls = [
            "https://gitlab.com/owner/repo",
            "https://bitbucket.org/owner/repo",
            "git@gitlab.com:owner/repo.git",
            "https://example.com/repo",
            "",
            None,
        ]
        
        for url in invalid_urls:
            assert not self.provider.is_provider_url(url), f"Should not detect {url} as GitHub URL"
    
    def test_is_provider_url_edge_cases(self):
        """Test URL detection with edge cases."""
        edge_cases = [
            ("https://github.com", False),  # No path
            ("https://api.github.com/repos/owner/repo", False),  # API URL
            ("https://raw.githubusercontent.com/owner/repo/main/file.txt", False),  # Raw content URL
            ("git@github.com:", False),  # Invalid SSH format
            ("malformed-url", False),  # Malformed URL
        ]
        
        for url, expected in edge_cases:
            result = self.provider.is_provider_url(url)
            assert result == expected, f"URL {url} should return {expected}, got {result}"


class TestGitHubProviderUrlParsing:
    """Test GitHub URL parsing for HTTPS and SSH formats."""
    
    def setup_method(self):
        """Set up test fixtures for each test method."""
        self.provider = GitHubProvider()
    
    def test_parse_https_url_basic(self):
        """Test parsing basic HTTPS GitHub URLs."""
        url = "https://github.com/owner/repo"
        result = self.provider.parse_url(url)
        
        expected = {
            'owner': 'owner',
            'repo': 'repo',
            'ref': None,
            'raw_url': url
        }
        assert result == expected
    
    def test_parse_https_url_with_git_extension(self):
        """Test parsing HTTPS URLs with .git extension."""
        url = "https://github.com/owner/repo.git"
        result = self.provider.parse_url(url)
        
        expected = {
            'owner': 'owner',
            'repo': 'repo',
            'ref': None,
            'raw_url': url
        }
        assert result == expected
    
    def test_parse_https_url_with_ref(self):
        """Test parsing HTTPS URLs with references."""
        test_cases = [
            ("https://github.com/owner/repo/tree/main", "tree/main"),
            ("https://github.com/owner/repo/tree/feature/new-feature", "tree/feature/new-feature"),
            ("https://github.com/owner/repo/commit/abc123", "commit/abc123"),
            ("https://github.com/owner/repo/releases/tag/v1.0.0", "releases/tag/v1.0.0"),
        ]
        
        for url, expected_ref in test_cases:
            result = self.provider.parse_url(url)
            assert result['ref'] == expected_ref, f"URL {url} should have ref {expected_ref}"
            assert result['owner'] == 'owner'
            assert result['repo'] == 'repo'
            assert result['raw_url'] == url
    
    def test_parse_ssh_url_basic(self):
        """Test parsing basic SSH GitHub URLs."""
        url = "git@github.com:owner/repo.git"
        result = self.provider.parse_url(url)
        
        expected = {
            'owner': 'owner',
            'repo': 'repo',
            'ref': None,
            'raw_url': url
        }
        assert result == expected
    
    def test_parse_ssh_url_without_git_extension(self):
        """Test parsing SSH URLs without .git extension."""
        url = "git@github.com:owner/repo"
        result = self.provider.parse_url(url)
        
        expected = {
            'owner': 'owner',
            'repo': 'repo',
            'ref': None,
            'raw_url': url
        }
        assert result == expected
    
    def test_parse_url_with_special_characters(self):
        """Test parsing URLs with special characters in owner/repo names."""
        test_cases = [
            "https://github.com/my-org/my-repo",
            "https://github.com/org_name/repo_name",
            "https://github.com/org123/repo456",
            "git@github.com:my-org/my-repo.git",
        ]
        
        for url in test_cases:
            result = self.provider.parse_url(url)
            assert result is not None, f"Should be able to parse {url}"
            assert 'owner' in result
            assert 'repo' in result
            assert 'raw_url' in result
    
    def test_parse_invalid_urls_raises_error(self):
        """Test that parsing invalid URLs raises ValueError."""
        invalid_urls = [
            "https://gitlab.com/owner/repo",  # Wrong provider
            "https://github.com",  # Missing path
            "https://github.com/owner",  # Missing repo
            "git@github.com:",  # Invalid SSH format
            "",  # Empty string
        ]
        
        for url in invalid_urls:
            with pytest.raises(ValueError, match=r"(Not a GitHub URL|Invalid GitHub URL)"):
                self.provider.parse_url(url)


class TestGitHubProviderCachePath:
    """Test cache path generation with shared and per-branch strategies."""
    
    def setup_method(self):
        """Set up test fixtures for each test method."""
        self.provider = GitHubProvider()
        self.temp_dir = Path(tempfile.mkdtemp())
        self.components = {
            'owner': 'testowner',
            'repo': 'testrepo',
            'ref': None,
            'raw_url': 'https://github.com/testowner/testrepo'
        }
    
    def teardown_method(self):
        """Clean up temporary directories."""
        import shutil
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_get_cache_path_shared_strategy(self):
        """Test cache path generation with shared strategy (default)."""
        cache_path = self.provider.get_cache_path(self.temp_dir, self.components)
        
        # Check structure: cache_dir/github/owner/repo-hash
        assert cache_path.parent.parent.parent == self.temp_dir.resolve()
        assert cache_path.parent.parent.name == "github"
        assert cache_path.parent.name == "testowner"
        assert cache_path.name.startswith("testrepo-")
        
        # Check that hash is deterministic
        expected_hash = hashlib.sha256(self.components['raw_url'].encode()).hexdigest()[:8]
        assert cache_path.name == f"testrepo-{expected_hash}"
    
    def test_get_cache_path_per_branch_strategy(self):
        """Test cache path generation with per-branch strategy."""
        branch = "main"
        cache_path = self.provider.get_cache_path(
            self.temp_dir, self.components, branch=branch, per_branch=True
        )
        
        # Check structure: cache_dir/github/owner/repo-branch-hash
        assert cache_path.parent.parent.parent == self.temp_dir.resolve()
        assert cache_path.parent.parent.name == "github"
        assert cache_path.parent.name == "testowner"
        assert cache_path.name.startswith("testrepo-main-")
        
        # Check that branch is included in hash
        url_with_branch = f"{self.components['raw_url']}@{branch}"
        expected_hash = hashlib.sha256(url_with_branch.encode()).hexdigest()[:8]
        assert cache_path.name == f"testrepo-main-{expected_hash}"
    
    def test_get_cache_path_branch_name_sanitization(self):
        """Test that branch names with special characters are sanitized."""
        test_cases = [
            ("feature/new-feature", "feature-new-feature"),
            ("hotfix\\urgent", "hotfix-urgent"),
            ("release:v1.0", "release-v1.0"),
            ("feat/issue#123", "feat-issue#123"),
        ]
        
        for original_branch, expected_safe_branch in test_cases:
            cache_path = self.provider.get_cache_path(
                self.temp_dir, self.components, branch=original_branch, per_branch=True
            )
            
            assert expected_safe_branch in cache_path.name, \
                f"Branch {original_branch} should be sanitized to {expected_safe_branch}"
    
    def test_get_cache_path_consistency(self):
        """Test that cache paths are consistent for the same inputs."""
        # Same inputs should produce same paths
        path1 = self.provider.get_cache_path(self.temp_dir, self.components)
        path2 = self.provider.get_cache_path(self.temp_dir, self.components)
        assert path1 == path2
        
        # Different branches should produce different paths in per-branch mode
        path_main = self.provider.get_cache_path(
            self.temp_dir, self.components, branch="main", per_branch=True
        )
        path_dev = self.provider.get_cache_path(
            self.temp_dir, self.components, branch="develop", per_branch=True
        )
        assert path_main != path_dev
    
    def test_get_cache_path_no_branch_per_branch_false(self):
        """Test per_branch=True with no branch falls back to shared strategy."""
        cache_path = self.provider.get_cache_path(
            self.temp_dir, self.components, branch=None, per_branch=True
        )
        
        # Should be same as shared strategy
        shared_path = self.provider.get_cache_path(self.temp_dir, self.components)
        assert cache_path == shared_path


class TestGitHubProviderAuthentication:
    """Test authentication URL generation."""
    
    def setup_method(self):
        """Set up test fixtures for each test method."""
        self.provider = GitHubProvider()
    
    def test_get_authenticated_url_https_with_token(self):
        """Test authentication URL generation for HTTPS URLs with token."""
        url = "https://github.com/owner/repo"
        token = "ghp_test_token_123"
        
        result = self.provider.get_authenticated_url(url, token)
        expected = "https://ghp_test_token_123@github.com/owner/repo"
        assert result == expected
    
    def test_get_authenticated_url_https_with_git_extension(self):
        """Test authentication URL generation for HTTPS URLs with .git extension."""
        url = "https://github.com/owner/repo.git"
        token = "ghp_test_token_123"
        
        result = self.provider.get_authenticated_url(url, token)
        expected = "https://ghp_test_token_123@github.com/owner/repo.git"
        assert result == expected
    
    def test_get_authenticated_url_ssh_with_token(self):
        """Test authentication URL generation for SSH URLs with token."""
        url = "git@github.com:owner/repo.git"
        token = "ghp_test_token_123"
        
        result = self.provider.get_authenticated_url(url, token)
        expected = "https://ghp_test_token_123@github.com/owner/repo.git"
        assert result == expected
    
    def test_get_authenticated_url_ssh_without_git_extension(self):
        """Test authentication URL generation for SSH URLs without .git extension."""
        url = "git@github.com:owner/repo"
        token = "ghp_test_token_123"
        
        result = self.provider.get_authenticated_url(url, token)
        expected = "https://ghp_test_token_123@github.com/owner/repo.git"
        assert result == expected
    
    def test_get_authenticated_url_no_token_returns_original(self):
        """Test that URLs without tokens are returned unchanged."""
        test_urls = [
            "https://github.com/owner/repo",
            "git@github.com:owner/repo.git",
        ]
        
        for url in test_urls:
            result = self.provider.get_authenticated_url(url, None)
            assert result == url
            
            result = self.provider.get_authenticated_url(url, "")
            assert result == url
    
    def test_get_authenticated_url_non_github_returns_original(self):
        """Test that non-GitHub URLs are returned unchanged even with token."""
        non_github_urls = [
            "https://gitlab.com/owner/repo",
            "git@bitbucket.org:owner/repo.git",
        ]
        
        token = "test_token"
        for url in non_github_urls:
            result = self.provider.get_authenticated_url(url, token)
            assert result == url


class TestProviderRegistry:
    """Test suite for provider registry functionality."""
    
    def setup_method(self):
        """Set up test fixtures for each test method."""
        self.registry = ProviderRegistry()
    
    def test_registry_initialization_includes_default_providers(self):
        """Test that registry is initialized with default providers."""
        providers = self.registry.get_providers()
        assert len(providers) > 0
        
        # Should include GitHub provider by default
        github_provider = self.registry.get_provider_by_name("GitHub")
        assert github_provider is not None
        assert isinstance(github_provider, GitHubProvider)
    
    def test_register_provider_success(self):
        """Test successful provider registration."""
        # Create a mock provider
        mock_provider = Mock(spec=GitProvider)
        mock_provider.get_provider_name.return_value = "TestProvider"
        
        initial_count = len(self.registry.get_providers())
        self.registry.register_provider(mock_provider)
        
        assert len(self.registry.get_providers()) == initial_count + 1
        assert mock_provider in self.registry.get_providers()
    
    def test_register_provider_invalid_type_raises_error(self):
        """Test that registering invalid provider type raises TypeError."""
        invalid_providers = [
            "not a provider",
            123,
            None,
            {},
        ]
        
        for invalid_provider in invalid_providers:
            with pytest.raises(TypeError, match="Provider must be a GitProvider instance"):
                self.registry.register_provider(invalid_provider)
    
    def test_get_provider_by_url(self):
        """Test provider lookup by URL."""
        # Test GitHub URL detection
        github_urls = [
            "https://github.com/owner/repo",
            "git@github.com:owner/repo.git",
        ]
        
        for url in github_urls:
            provider = self.registry.get_provider(url)
            assert provider is not None
            assert isinstance(provider, GitHubProvider)
    
    def test_get_provider_by_url_not_found(self):
        """Test provider lookup returns None for unsupported URLs."""
        unsupported_urls = [
            "https://gitlab.com/owner/repo",
            "https://example.com/repo",
            "",
        ]
        
        for url in unsupported_urls:
            provider = self.registry.get_provider(url)
            assert provider is None
    
    def test_get_provider_by_name(self):
        """Test provider lookup by name."""
        provider = self.registry.get_provider_by_name("GitHub")
        assert provider is not None
        assert isinstance(provider, GitHubProvider)
        
        # Test case insensitive lookup
        provider = self.registry.get_provider_by_name("github")
        assert provider is not None
        assert isinstance(provider, GitHubProvider)
    
    def test_get_provider_by_name_not_found(self):
        """Test provider lookup by name returns None for unknown providers."""
        provider = self.registry.get_provider_by_name("UnknownProvider")
        assert provider is None
    
    def test_get_providers_returns_copy(self):
        """Test that get_providers returns a copy to prevent external modification."""
        providers = self.registry.get_providers()
        original_length = len(providers)
        
        # Modify the returned list
        providers.clear()
        
        # Original registry should be unchanged
        assert len(self.registry.get_providers()) == original_length
    
    def test_is_supported_url(self):
        """Test URL support checking."""
        supported_urls = [
            "https://github.com/owner/repo",
            "git@github.com:owner/repo.git",
        ]
        
        unsupported_urls = [
            "https://gitlab.com/owner/repo",
            "invalid-url",
            "",
        ]
        
        for url in supported_urls:
            assert self.registry.is_supported_url(url), f"Should support {url}"
        
        for url in unsupported_urls:
            assert not self.registry.is_supported_url(url), f"Should not support {url}"
    
    @patch.dict('os.environ', {'GITHUB_PERSONAL_ACCESS_TOKEN': 'test_token'})
    def test_get_authenticated_url_with_token(self):
        """Test authenticated URL generation using environment variables."""
        url = "https://github.com/owner/repo"
        result = self.registry.get_authenticated_url(url)
        expected = "https://test_token@github.com/owner/repo"
        assert result == expected
    
    @patch.dict('os.environ', {}, clear=True)
    def test_get_authenticated_url_without_token(self):
        """Test authenticated URL generation without environment variables."""
        url = "https://github.com/owner/repo"
        result = self.registry.get_authenticated_url(url)
        assert result == url  # Should return original URL
    
    def test_get_authenticated_url_unsupported_provider(self):
        """Test authenticated URL generation for unsupported providers."""
        url = "https://gitlab.com/owner/repo"
        result = self.registry.get_authenticated_url(url)
        assert result == url  # Should return original URL
    
    def test_parse_url_success(self):
        """Test URL parsing using appropriate provider."""
        url = "https://github.com/owner/repo"
        result = self.registry.parse_url(url)
        
        assert result is not None
        assert result['owner'] == 'owner'
        assert result['repo'] == 'repo'
        assert result['raw_url'] == url
    
    def test_parse_url_unsupported_provider(self):
        """Test URL parsing returns None for unsupported providers."""
        url = "https://gitlab.com/owner/repo"
        result = self.registry.parse_url(url)
        assert result is None
    
    def test_parse_url_invalid_format(self):
        """Test URL parsing returns None for invalid URLs."""
        # Register a mock provider that raises ValueError
        mock_provider = Mock(spec=GitProvider)
        mock_provider.is_provider_url.return_value = True
        mock_provider.parse_url.side_effect = ValueError("Invalid URL")
        
        registry = ProviderRegistry()
        registry.register_provider(mock_provider)
        
        result = registry.parse_url("invalid-url")
        assert result is None


class TestProviderRegistryGlobalFunctions:
    """Test global registry functions."""
    
    def test_get_default_registry_returns_singleton(self):
        """Test that get_default_registry returns the same instance."""
        registry1 = get_default_registry()
        registry2 = get_default_registry()
        assert registry1 is registry2
    
    def test_register_provider_uses_default_registry(self):
        """Test that register_provider function uses default registry."""
        mock_provider = Mock(spec=GitProvider)
        mock_provider.get_provider_name.return_value = "TestProvider"
        
        initial_count = len(get_default_registry().get_providers())
        register_provider(mock_provider)
        
        # Should be registered in default registry
        assert len(get_default_registry().get_providers()) == initial_count + 1
    
    def test_get_provider_uses_default_registry(self):
        """Test that get_provider function uses default registry."""
        url = "https://github.com/owner/repo"
        provider = get_provider(url)
        
        assert provider is not None
        assert isinstance(provider, GitHubProvider)


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling across the provider framework."""
    
    def setup_method(self):
        """Set up test fixtures for each test method."""
        self.provider = GitHubProvider()
    
    def test_empty_and_none_url_handling(self):
        """Test handling of empty and None URLs."""
        edge_cases = [None, "", "   ", "\t\n"]
        
        for url in edge_cases:
            assert not self.provider.is_provider_url(url)
            
            if url:  # Skip None for parse_url as it will fail is_provider_url check
                with pytest.raises(ValueError):
                    self.provider.parse_url(url)
    
    def test_url_with_unusual_characters(self):
        """Test URLs with unusual but potentially valid characters."""
        unusual_urls = [
            "https://github.com/user-name/repo_name",
            "https://github.com/123user/456repo",
            "git@github.com:user.name/repo.name.git",
        ]
        
        for url in unusual_urls:
            if self.provider.is_provider_url(url):
                result = self.provider.parse_url(url)
                assert result is not None
                assert 'owner' in result
                assert 'repo' in result
    
    def test_very_long_urls(self):
        """Test handling of very long URLs."""
        long_owner = "a" * 100
        long_repo = "b" * 100
        long_url = f"https://github.com/{long_owner}/{long_repo}"
        
        assert self.provider.is_provider_url(long_url)
        result = self.provider.parse_url(long_url)
        assert result['owner'] == long_owner
        assert result['repo'] == long_repo
    
    def test_cache_path_with_unicode_characters(self):
        """Test cache path generation with Unicode characters in components."""
        components = {
            'owner': 'ユーザー',  # Japanese characters
            'repo': 'リポジトリ',
            'ref': None,
            'raw_url': 'https://github.com/ユーザー/リポジトリ'
        }
        
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = self.provider.get_cache_path(Path(temp_dir), components)
            assert cache_path is not None
            # Path should be valid even with Unicode characters
            assert cache_path.parent.parent.name == "github"
    
    def test_authentication_with_special_token_characters(self):
        """Test authentication URL generation with special characters in token."""
        url = "https://github.com/owner/repo"
        special_tokens = [
            "ghp_1234567890abcdef",
            "token-with-dashes",
            "token_with_underscores",
        ]
        
        for token in special_tokens:
            result = self.provider.get_authenticated_url(url, token)
            assert token in result
            assert "github.com" in result
    
    def test_branch_name_edge_cases_in_cache_path(self):
        """Test cache path generation with edge case branch names."""
        components = {
            'owner': 'owner',
            'repo': 'repo',
            'ref': None,
            'raw_url': 'https://github.com/owner/repo'
        }
        
        edge_case_branches = [
            "",  # Empty branch
            "   ",  # Whitespace only
            "very-long-branch-name-that-exceeds-normal-length-limits",
            "branch/with/many/slashes",
            "branch\\with\\backslashes",
            "branch:with:colons",
        ]
        
        with tempfile.TemporaryDirectory() as temp_dir:
            for branch in edge_case_branches:
                if branch.strip():  # Skip empty/whitespace branches
                    cache_path = self.provider.get_cache_path(
                        Path(temp_dir), components, branch=branch, per_branch=True
                    )
                    assert cache_path is not None
                    # Branch name should be sanitized in the path
                    assert "/" not in cache_path.name
                    assert "\\" not in cache_path.name
    
    def test_malformed_url_handling(self):
        """Test handling of malformed URLs that might cause parsing issues."""
        malformed_urls = [
            "https://github.com/owner",  # Missing repo
            "https://github.com/",  # Empty path
            "git@github.com:",  # Invalid SSH format
            "https://github.com//owner//repo",  # Double slashes
            "ftp://github.com/owner/repo",  # Wrong protocol
            "https://github.com/owner/repo?query=value",  # With query parameters
            "https://github.com/owner/repo#fragment",  # With fragment
        ]
        
        for url in malformed_urls:
            # Should either return False for is_provider_url or raise ValueError for parse_url
            if self.provider.is_provider_url(url):
                try:
                    result = self.provider.parse_url(url)
                    # If parsing succeeds, result should have required fields
                    assert 'owner' in result
                    assert 'repo' in result
                    assert 'raw_url' in result
                except ValueError:
                    # ValueError is acceptable for malformed URLs
                    pass
            else:
                # If not detected as provider URL, should raise ValueError when parsing
                with pytest.raises(ValueError):
                    self.provider.parse_url(url)


# Integration test to verify all components work together
class TestProviderFrameworkIntegration:
    """Integration tests for the complete provider framework."""
    
    def test_end_to_end_github_workflow(self):
        """Test complete workflow from URL detection to cache path generation."""
        url = "https://github.com/owner/repo"
        
        # Get provider from registry
        registry = ProviderRegistry()
        provider = registry.get_provider(url)
        assert provider is not None
        
        # Parse URL
        components = provider.parse_url(url)
        assert components is not None
        
        # Generate cache path
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = provider.get_cache_path(Path(temp_dir), components)
            assert cache_path is not None
            assert cache_path.parent.parent.name == "github"
        
        # Generate authenticated URL
        auth_url = provider.get_authenticated_url(url, "test_token")
        assert "test_token" in auth_url
        
        # Verify provider metadata
        assert provider.get_provider_name() == "GitHub"
        assert provider.get_env_var_name() == "GITHUB_PERSONAL_ACCESS_TOKEN"
    
    @patch.dict('os.environ', {'GITHUB_PERSONAL_ACCESS_TOKEN': 'env_token'})
    def test_registry_environment_integration(self):
        """Test registry integration with environment variables."""
        url = "https://github.com/owner/repo"
        registry = ProviderRegistry()
        
        # Should use environment variable automatically
        auth_url = registry.get_authenticated_url(url)
        assert "env_token" in auth_url
        
        # Parse URL through registry
        components = registry.parse_url(url)
        assert components is not None
        assert components['owner'] == 'owner'
        assert components['repo'] == 'repo'