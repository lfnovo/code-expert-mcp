"""
Comprehensive unit tests for the Azure DevOps provider implementation.

This module tests the Azure DevOps provider components:
- URL detection for various Azure DevOps URL formats
- URL parsing and component extraction 
- Cache path generation with shared and per-branch strategies
- Authentication URL generation
- Integration with provider registry
- Edge cases and error handling
"""

import pytest
import tempfile
import hashlib
from pathlib import Path
from unittest.mock import Mock, patch

from code_expert.repository.providers.base import GitProvider
from code_expert.repository.providers.azure_devops import AzureDevOpsProvider
from code_expert.repository.providers.registry import ProviderRegistry, get_default_registry


class TestAzureDevOpsProvider:
    """Test suite for Azure DevOps provider implementation."""
    
    def setup_method(self):
        """Set up test fixtures for each test method."""
        self.provider = AzureDevOpsProvider()
    
    def test_provider_name(self):
        """Test provider name is correctly returned."""
        assert self.provider.get_provider_name() == "Azure DevOps"
    
    def test_environment_variable_name(self):
        """Test environment variable name is correctly returned."""
        assert self.provider.get_env_var_name() == "AZURE_DEVOPS_PAT"


class TestAzureDevOpsProviderUrlDetection:
    """Test Azure DevOps URL detection for various URL formats."""
    
    def setup_method(self):
        """Set up test fixtures for each test method."""
        self.provider = AzureDevOpsProvider()
    
    def test_is_provider_url_https_dev_azure_com(self):
        """Test detection of HTTPS Azure DevOps URLs with dev.azure.com format."""
        valid_urls = [
            "https://dev.azure.com/myorg/myproject/_git/myrepo",
            "https://dev.azure.com/myorg/myproject/_git/myrepo.git",
            "http://dev.azure.com/myorg/myproject/_git/myrepo",  # HTTP should also work
            "https://dev.azure.com/my-org/my-project/_git/my-repo",
            "https://dev.azure.com/org123/project456/_git/repo789",
        ]
        
        for url in valid_urls:
            assert self.provider.is_provider_url(url), f"Should detect {url} as Azure DevOps URL"
    
    def test_is_provider_url_https_with_organization_prefix(self):
        """Test detection of HTTPS Azure DevOps URLs with organization prefix."""
        valid_urls = [
            "https://myorg@dev.azure.com/myorg/myproject/_git/myrepo",
            "https://org123@dev.azure.com/org123/project/_git/repo.git",
        ]
        
        for url in valid_urls:
            assert self.provider.is_provider_url(url), f"Should detect {url} as Azure DevOps URL"
    
    def test_is_provider_url_ssh_azure_devops(self):
        """Test detection of SSH Azure DevOps URLs."""
        valid_urls = [
            "git@ssh.dev.azure.com:v3/myorg/myproject/myrepo",
            "git@ssh.dev.azure.com:v3/myorg/myproject/myrepo.git",
            "git@ssh.dev.azure.com:v3/my-org/my-project/my-repo",
            "git@ssh.dev.azure.com:v3/org123/project456/repo789",
        ]
        
        for url in valid_urls:
            assert self.provider.is_provider_url(url), f"Should detect {url} as Azure DevOps URL"
    
    def test_is_provider_url_non_azure_devops(self):
        """Test rejection of non-Azure DevOps URLs."""
        invalid_urls = [
            "https://github.com/owner/repo",
            "https://gitlab.com/owner/repo",
            "https://bitbucket.org/owner/repo",
            "git@github.com:owner/repo.git",
            "git@gitlab.com:owner/repo.git",
            "https://example.com/repo",
            "",
            None,
        ]
        
        for url in invalid_urls:
            assert not self.provider.is_provider_url(url), f"Should not detect {url} as Azure DevOps URL"
    
    def test_is_provider_url_edge_cases(self):
        """Test URL detection with edge cases."""
        edge_cases = [
            ("https://dev.azure.com", False),  # No path
            ("https://dev.azure.com/org", False),  # Missing project
            ("https://dev.azure.com/org/project", True),  # Valid short format (repo defaults to project)
            ("https://dev.azure.com/org/project/_git", False),  # Missing repo
            ("https://api.dev.azure.com/org/project/_git/repo", True),  # API subdomain - valid
            ("https://api.dev.azure.com/org/project", True),  # API subdomain short format - valid
            ("git@ssh.dev.azure.com:v3/", False),  # Empty SSH path
            ("git@ssh.dev.azure.com:v3/org", False),  # Missing project/repo
            ("git@ssh.dev.azure.com:v3/org/project", False),  # Missing repo
            ("malformed-url", False),  # Malformed URL
        ]
        
        for url, expected in edge_cases:
            result = self.provider.is_provider_url(url)
            assert result == expected, f"URL {url} should return {expected}, got {result}"


class TestAzureDevOpsProviderUrlParsing:
    """Test Azure DevOps URL parsing for HTTPS and SSH formats."""
    
    def setup_method(self):
        """Set up test fixtures for each test method."""
        self.provider = AzureDevOpsProvider()
    
    def test_parse_https_url_basic(self):
        """Test parsing basic HTTPS Azure DevOps URLs."""
        url = "https://dev.azure.com/myorg/myproject/_git/myrepo"
        result = self.provider.parse_url(url)
        
        expected = {
            'organization': 'myorg',
            'project': 'myproject',
            'repo': 'myrepo',
            'ref': None,
            'raw_url': url
        }
        assert result == expected
    
    def test_parse_https_url_with_git_extension(self):
        """Test parsing HTTPS URLs with .git extension."""
        url = "https://dev.azure.com/myorg/myproject/_git/myrepo.git"
        result = self.provider.parse_url(url)
        
        expected = {
            'organization': 'myorg',
            'project': 'myproject',
            'repo': 'myrepo',
            'ref': None,
            'raw_url': url
        }
        assert result == expected
    
    def test_parse_https_url_with_organization_prefix(self):
        """Test parsing HTTPS URLs with organization prefix."""
        url = "https://myorg@dev.azure.com/myorg/myproject/_git/myrepo"
        result = self.provider.parse_url(url)
        
        expected = {
            'organization': 'myorg',
            'project': 'myproject', 
            'repo': 'myrepo',
            'ref': None,
            'raw_url': url
        }
        assert result == expected
    
    def test_parse_https_url_with_ref(self):
        """Test parsing HTTPS URLs with references."""
        test_cases = [
            ("https://dev.azure.com/org/project/_git/repo/branch/main", "branch/main"),
            ("https://dev.azure.com/org/project/_git/repo/branch/feature/new-feature", "branch/feature/new-feature"),
            ("https://dev.azure.com/org/project/_git/repo/commit/abc123", "commit/abc123"),
            ("https://dev.azure.com/org/project/_git/repo/tag/v1.0.0", "tag/v1.0.0"),
        ]
        
        for url, expected_ref in test_cases:
            result = self.provider.parse_url(url)
            assert result['ref'] == expected_ref, f"URL {url} should have ref {expected_ref}"
            assert result['organization'] == 'org'
            assert result['project'] == 'project'
            assert result['repo'] == 'repo'
            assert result['raw_url'] == url
    
    def test_parse_ssh_url_basic(self):
        """Test parsing basic SSH Azure DevOps URLs."""
        url = "git@ssh.dev.azure.com:v3/myorg/myproject/myrepo"
        result = self.provider.parse_url(url)
        
        expected = {
            'organization': 'myorg',
            'project': 'myproject',
            'repo': 'myrepo',
            'ref': None,
            'raw_url': url
        }
        assert result == expected
    
    def test_parse_ssh_url_with_git_extension(self):
        """Test parsing SSH URLs with .git extension."""
        url = "git@ssh.dev.azure.com:v3/myorg/myproject/myrepo.git"
        result = self.provider.parse_url(url)
        
        expected = {
            'organization': 'myorg',
            'project': 'myproject',
            'repo': 'myrepo',
            'ref': None,
            'raw_url': url
        }
        assert result == expected
    
    def test_parse_ssh_url_with_ref(self):
        """Test parsing SSH URLs with references."""
        url = "git@ssh.dev.azure.com:v3/myorg/myproject/myrepo/branch/main"
        result = self.provider.parse_url(url)
        
        expected = {
            'organization': 'myorg',
            'project': 'myproject',
            'repo': 'myrepo',
            'ref': 'branch/main',
            'raw_url': url
        }
        assert result == expected
    
    def test_parse_url_with_special_characters(self):
        """Test parsing URLs with special characters in organization/project/repo names."""
        test_cases = [
            "https://dev.azure.com/my-org/my-project/_git/my-repo",
            "https://dev.azure.com/org_name/project_name/_git/repo_name",
            "https://dev.azure.com/org123/project456/_git/repo789",
            "git@ssh.dev.azure.com:v3/my-org/my-project/my-repo",
        ]
        
        for url in test_cases:
            result = self.provider.parse_url(url)
            assert result is not None, f"Should be able to parse {url}"
            assert 'organization' in result
            assert 'project' in result
            assert 'repo' in result
            assert 'raw_url' in result
    
    def test_parse_invalid_urls_raises_error(self):
        """Test that parsing invalid URLs raises ValueError."""
        invalid_urls = [
            "https://github.com/owner/repo",  # Wrong provider
            "https://dev.azure.com",  # Missing path
            "https://dev.azure.com/org",  # Missing project
            # Note: "https://dev.azure.com/org/project" is now valid (short format)
            "https://dev.azure.com/org/project/_git",  # Missing repo
            "git@ssh.dev.azure.com:v3/",  # Empty SSH path
            "git@ssh.dev.azure.com:v3/org",  # Missing project/repo
            "git@ssh.dev.azure.com:v3/org/project",  # Missing repo
            "",  # Empty string
        ]
        
        for url in invalid_urls:
            with pytest.raises(ValueError, match=r"(Not an Azure DevOps URL|Invalid Azure DevOps)"):
                self.provider.parse_url(url)


class TestAzureDevOpsProviderCachePath:
    """Test cache path generation with shared and per-branch strategies."""
    
    def setup_method(self):
        """Set up test fixtures for each test method."""
        self.provider = AzureDevOpsProvider()
        self.temp_dir = Path(tempfile.mkdtemp())
        self.components = {
            'organization': 'testorg',
            'project': 'testproject',
            'repo': 'testrepo',
            'ref': None,
            'raw_url': 'https://dev.azure.com/testorg/testproject/_git/testrepo'
        }
    
    def teardown_method(self):
        """Clean up temporary directories."""
        import shutil
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_get_cache_path_shared_strategy(self):
        """Test cache path generation with shared strategy (default)."""
        cache_path = self.provider.get_cache_path(self.temp_dir, self.components)
        
        # Check structure: cache_dir/azure/organization/project/repo-hash
        assert cache_path.parent.parent.parent.parent == self.temp_dir.resolve()
        assert cache_path.parent.parent.parent.name == "azure"
        assert cache_path.parent.parent.name == "testorg"
        assert cache_path.parent.name == "testproject"
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
        
        # Check structure: cache_dir/azure/organization/project/repo-branch-hash
        assert cache_path.parent.parent.parent.parent == self.temp_dir.resolve()
        assert cache_path.parent.parent.parent.name == "azure"
        assert cache_path.parent.parent.name == "testorg"
        assert cache_path.parent.name == "testproject"
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
            ("feat issue#123", "feat_issue#123"),  # Space becomes underscore
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
    
    def test_get_cache_path_special_characters_in_components(self):
        """Test cache path generation with special characters in components."""
        special_components = {
            'organization': 'my-org',
            'project': 'my_project',
            'repo': 'my:repo',
            'ref': None,
            'raw_url': 'https://dev.azure.com/my-org/my_project/_git/my:repo'
        }
        
        cache_path = self.provider.get_cache_path(self.temp_dir, special_components)
        
        # Check that special characters are sanitized
        assert cache_path.parent.parent.name == "my-org"  # Hyphens are preserved
        assert cache_path.parent.name == "my_project"  # Underscores are preserved
        assert "my-repo" in cache_path.name  # Colons should be replaced with hyphens


class TestAzureDevOpsProviderAuthentication:
    """Test authentication URL generation."""
    
    def setup_method(self):
        """Set up test fixtures for each test method."""
        self.provider = AzureDevOpsProvider()
    
    def test_get_authenticated_url_https_with_token(self):
        """Test authentication URL generation for HTTPS URLs with token."""
        url = "https://dev.azure.com/myorg/myproject/_git/myrepo"
        token = "test_pat_token_123"
        
        result = self.provider.get_authenticated_url(url, token)
        expected = "https://test_pat_token_123@dev.azure.com/myorg/myproject/_git/myrepo"
        assert result == expected
    
    def test_get_authenticated_url_https_with_git_extension(self):
        """Test authentication URL generation for HTTPS URLs with .git extension."""
        url = "https://dev.azure.com/myorg/myproject/_git/myrepo.git"
        token = "test_pat_token_123"
        
        result = self.provider.get_authenticated_url(url, token)
        expected = "https://test_pat_token_123@dev.azure.com/myorg/myproject/_git/myrepo.git"
        assert result == expected
    
    def test_get_authenticated_url_https_with_existing_auth(self):
        """Test authentication URL generation for HTTPS URLs with existing authentication."""
        url = "https://oldtoken@dev.azure.com/myorg/myproject/_git/myrepo"
        token = "new_pat_token_123"
        
        result = self.provider.get_authenticated_url(url, token)
        expected = "https://new_pat_token_123@dev.azure.com/myorg/myproject/_git/myrepo"
        assert result == expected
    
    def test_get_authenticated_url_ssh_with_token(self):
        """Test authentication URL generation for SSH URLs with token."""
        url = "git@ssh.dev.azure.com:v3/myorg/myproject/myrepo"
        token = "test_pat_token_123"
        
        result = self.provider.get_authenticated_url(url, token)
        expected = "https://test_pat_token_123@dev.azure.com/myorg/myproject/_git/myrepo.git"
        assert result == expected
    
    def test_get_authenticated_url_ssh_with_git_extension(self):
        """Test authentication URL generation for SSH URLs with .git extension."""
        url = "git@ssh.dev.azure.com:v3/myorg/myproject/myrepo.git"
        token = "test_pat_token_123"
        
        result = self.provider.get_authenticated_url(url, token)
        expected = "https://test_pat_token_123@dev.azure.com/myorg/myproject/_git/myrepo.git"
        assert result == expected
    
    def test_get_authenticated_url_no_token_returns_original(self):
        """Test that URLs without tokens are handled correctly."""
        # HTTPS URLs should remain unchanged without token
        https_url = "https://dev.azure.com/myorg/myproject/_git/myrepo"
        result = self.provider.get_authenticated_url(https_url, None)
        assert result == https_url
        
        result = self.provider.get_authenticated_url(https_url, "")
        assert result == https_url
        
        # SSH URLs are converted to HTTPS format for consistency
        ssh_url = "git@ssh.dev.azure.com:v3/myorg/myproject/myrepo"
        result = self.provider.get_authenticated_url(ssh_url, None)
        expected = "https://dev.azure.com/myorg/myproject/_git/myrepo.git"
        assert result == expected
        
        result = self.provider.get_authenticated_url(ssh_url, "")
        assert result == expected
    
    def test_get_authenticated_url_non_azure_devops_returns_original(self):
        """Test that non-Azure DevOps URLs are returned unchanged even with token."""
        non_azure_urls = [
            "https://github.com/owner/repo",
            "git@gitlab.com:owner/repo.git",
        ]
        
        token = "test_token"
        for url in non_azure_urls:
            result = self.provider.get_authenticated_url(url, token)
            assert result == url
    
    def test_get_authenticated_url_short_format_conversion(self):
        """Test that short format URLs are converted to full format for cloning."""
        # Short format without token
        short_url = "https://dev.azure.com/myorg/myproject"
        result = self.provider.get_authenticated_url(short_url, None)
        expected = "https://dev.azure.com/myorg/myproject/_git/myproject"
        assert result == expected
        
        # Short format with token
        result_with_token = self.provider.get_authenticated_url(short_url, "test_token")
        expected_with_token = "https://test_token@dev.azure.com/myorg/myproject/_git/myproject"
        assert result_with_token == expected_with_token
        
        # Real-world example
        real_url = "https://dev.azure.com/nordresearch/NordInvestimentos.Marilinha"
        result = self.provider.get_authenticated_url(real_url, None)
        expected = "https://dev.azure.com/nordresearch/NordInvestimentos.Marilinha/_git/NordInvestimentos.Marilinha"
        assert result == expected
    
    def test_get_authenticated_url_with_special_token_characters(self):
        """Test authentication URL generation with special characters in token."""
        url = "https://dev.azure.com/myorg/myproject/_git/myrepo"
        special_tokens = [
            "token-with-dashes",
            "token_with_underscores",
            "token123456789",
            "abcdef1234567890",
        ]
        
        for token in special_tokens:
            result = self.provider.get_authenticated_url(url, token)
            assert token in result
            assert "dev.azure.com" in result


class TestAzureDevOpsProviderRegistry:
    """Test Azure DevOps provider integration with registry."""
    
    def setup_method(self):
        """Set up test fixtures for each test method."""
        self.registry = ProviderRegistry()
    
    def test_registry_includes_azure_devops_provider(self):
        """Test that registry includes Azure DevOps provider by default."""
        providers = self.registry.get_providers()
        assert len(providers) >= 2  # Should include at least GitHub and Azure DevOps
        
        azure_provider = self.registry.get_provider_by_name("Azure DevOps")
        assert azure_provider is not None
        assert isinstance(azure_provider, AzureDevOpsProvider)
    
    def test_get_provider_by_azure_devops_url(self):
        """Test provider lookup by Azure DevOps URL."""
        azure_urls = [
            "https://dev.azure.com/myorg/myproject/_git/myrepo",
            "git@ssh.dev.azure.com:v3/myorg/myproject/myrepo",
        ]
        
        for url in azure_urls:
            provider = self.registry.get_provider(url)
            assert provider is not None
            assert isinstance(provider, AzureDevOpsProvider)
    
    def test_get_provider_by_name_case_insensitive(self):
        """Test provider lookup by name is case insensitive."""
        test_cases = [
            "Azure DevOps",
            "azure devops", 
            "AZURE DEVOPS",
            "Azure devops",
        ]
        
        for name in test_cases:
            provider = self.registry.get_provider_by_name(name)
            assert provider is not None
            assert isinstance(provider, AzureDevOpsProvider)
    
    def test_is_supported_url_azure_devops(self):
        """Test URL support checking for Azure DevOps URLs."""
        supported_urls = [
            "https://dev.azure.com/myorg/myproject/_git/myrepo",
            "git@ssh.dev.azure.com:v3/myorg/myproject/myrepo",
        ]
        
        for url in supported_urls:
            assert self.registry.is_supported_url(url), f"Should support {url}"
    
    @patch.dict('os.environ', {'AZURE_DEVOPS_PAT': 'test_azure_token'})
    def test_get_authenticated_url_with_azure_token(self):
        """Test authenticated URL generation using Azure DevOps environment variable."""
        url = "https://dev.azure.com/myorg/myproject/_git/myrepo"
        result = self.registry.get_authenticated_url(url)
        expected = "https://test_azure_token@dev.azure.com/myorg/myproject/_git/myrepo"
        assert result == expected
    
    @patch.dict('os.environ', {}, clear=True)
    def test_get_authenticated_url_without_azure_token(self):
        """Test authenticated URL generation without Azure DevOps environment variable."""
        url = "https://dev.azure.com/myorg/myproject/_git/myrepo"
        result = self.registry.get_authenticated_url(url)
        assert result == url  # Should return original URL
    
    def test_parse_url_azure_devops_success(self):
        """Test URL parsing using Azure DevOps provider through registry."""
        url = "https://dev.azure.com/myorg/myproject/_git/myrepo"
        result = self.registry.parse_url(url)
        
        assert result is not None
        assert result['organization'] == 'myorg'
        assert result['project'] == 'myproject'
        assert result['repo'] == 'myrepo'
        assert result['raw_url'] == url


class TestAzureDevOpsProviderEdgeCases:
    """Test edge cases and error handling for Azure DevOps provider."""
    
    def setup_method(self):
        """Set up test fixtures for each test method."""
        self.provider = AzureDevOpsProvider()
    
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
            "https://dev.azure.com/user-name/project_name/_git/repo_name",
            "https://dev.azure.com/123org/456project/_git/789repo",
            "git@ssh.dev.azure.com:v3/user.name/project.name/repo.name",
        ]
        
        for url in unusual_urls:
            if self.provider.is_provider_url(url):
                result = self.provider.parse_url(url)
                assert result is not None
                assert 'organization' in result
                assert 'project' in result
                assert 'repo' in result
    
    def test_very_long_urls(self):
        """Test handling of very long URLs."""
        long_org = "a" * 100
        long_project = "b" * 100
        long_repo = "c" * 100
        long_url = f"https://dev.azure.com/{long_org}/{long_project}/_git/{long_repo}"
        
        assert self.provider.is_provider_url(long_url)
        result = self.provider.parse_url(long_url)
        assert result['organization'] == long_org
        assert result['project'] == long_project
        assert result['repo'] == long_repo
    
    def test_cache_path_with_unicode_characters(self):
        """Test cache path generation with Unicode characters in components."""
        components = {
            'organization': '組織',  # Japanese characters
            'project': 'プロジェクト',
            'repo': 'リポジトリ',
            'ref': None,
            'raw_url': 'https://dev.azure.com/組織/プロジェクト/_git/リポジトリ'
        }
        
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = self.provider.get_cache_path(Path(temp_dir), components)
            assert cache_path is not None
            # Path should be valid even with Unicode characters
            assert cache_path.parent.parent.parent.name == "azure"
    
    def test_branch_name_edge_cases_in_cache_path(self):
        """Test cache path generation with edge case branch names."""
        components = {
            'organization': 'org',
            'project': 'project',
            'repo': 'repo',
            'ref': None,
            'raw_url': 'https://dev.azure.com/org/project/_git/repo'
        }
        
        edge_case_branches = [
            "",  # Empty branch
            "   ",  # Whitespace only
            "very-long-branch-name-that-exceeds-normal-length-limits",
            "branch/with/many/slashes",
            "branch\\with\\backslashes",
            "branch:with:colons",
            "branch with spaces",
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
            "https://dev.azure.com/org",  # Missing project/_git/repo
            "https://dev.azure.com/org/project",  # Missing _git/repo
            "https://dev.azure.com/org/project/_git",  # Missing repo
            "https://dev.azure.com/",  # Empty path
            "git@ssh.dev.azure.com:v3/",  # Empty SSH path
            "https://dev.azure.com//org//project//_git//repo",  # Double slashes
            "ftp://dev.azure.com/org/project/_git/repo",  # Wrong protocol
            "https://dev.azure.com/org/project/_git/repo?query=value",  # With query parameters
            "https://dev.azure.com/org/project/_git/repo#fragment",  # With fragment
        ]
        
        for url in malformed_urls:
            # Should either return False for is_provider_url or raise ValueError for parse_url
            if self.provider.is_provider_url(url):
                try:
                    result = self.provider.parse_url(url)
                    # If parsing succeeds, result should have required fields
                    assert 'organization' in result
                    assert 'project' in result
                    assert 'repo' in result
                    assert 'raw_url' in result
                except ValueError:
                    # ValueError is acceptable for malformed URLs
                    pass
            else:
                # If not detected as provider URL, should raise ValueError when parsing
                with pytest.raises(ValueError):
                    self.provider.parse_url(url)
    
    def test_ssh_url_edge_cases(self):
        """Test SSH URL handling with edge cases."""
        ssh_edge_cases = [
            ("git@ssh.dev.azure.com:v3/org/project/repo/branch/main", True),  # With ref
            ("git@ssh.dev.azure.com:v3/org/project/repo.git/tag/v1.0", True),  # .git with ref
            ("git@ssh.dev.azure.com:v3/org/project/", False),  # Trailing slash, no repo
            ("git@ssh.dev.azure.com:v3/org/project/repo/", True),  # Trailing slash with repo
        ]
        
        for url, should_be_valid in ssh_edge_cases:
            result = self.provider.is_provider_url(url)
            assert result == should_be_valid, f"URL {url} should be {should_be_valid}"
            
            if should_be_valid:
                parsed = self.provider.parse_url(url)
                assert parsed is not None
                assert 'organization' in parsed
                assert 'project' in parsed
                assert 'repo' in parsed


class TestAzureDevOpsProviderIntegration:
    """Integration tests for Azure DevOps provider with complete workflow."""
    
    def test_end_to_end_azure_devops_workflow(self):
        """Test complete workflow from URL detection to cache path generation."""
        url = "https://dev.azure.com/myorg/myproject/_git/myrepo"
        
        # Get provider from registry
        registry = ProviderRegistry()
        provider = registry.get_provider(url)
        assert provider is not None
        assert isinstance(provider, AzureDevOpsProvider)
        
        # Parse URL
        components = provider.parse_url(url)
        assert components is not None
        
        # Generate cache path
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = provider.get_cache_path(Path(temp_dir), components)
            assert cache_path is not None
            assert cache_path.parent.parent.parent.name == "azure"
        
        # Generate authenticated URL
        auth_url = provider.get_authenticated_url(url, "test_token")
        assert "test_token" in auth_url
        
        # Verify provider metadata
        assert provider.get_provider_name() == "Azure DevOps"
        assert provider.get_env_var_name() == "AZURE_DEVOPS_PAT"
    
    def test_ssh_to_https_conversion_workflow(self):
        """Test SSH to HTTPS conversion workflow with authentication."""
        ssh_url = "git@ssh.dev.azure.com:v3/myorg/myproject/myrepo"
        token = "test_pat_token"
        
        # Get provider and convert to authenticated HTTPS
        registry = ProviderRegistry()
        provider = registry.get_provider(ssh_url)
        assert provider is not None
        
        auth_url = provider.get_authenticated_url(ssh_url, token)
        expected = "https://test_pat_token@dev.azure.com/myorg/myproject/_git/myrepo.git"
        assert auth_url == expected
        
        # Verify the converted URL can still be parsed
        https_components = provider.parse_url(auth_url)
        ssh_components = provider.parse_url(ssh_url)
        
        assert https_components['organization'] == ssh_components['organization']
        assert https_components['project'] == ssh_components['project']
        assert https_components['repo'] == ssh_components['repo']
    
    @patch.dict('os.environ', {'AZURE_DEVOPS_PAT': 'env_token'})
    def test_registry_environment_integration(self):
        """Test registry integration with Azure DevOps environment variables."""
        url = "https://dev.azure.com/myorg/myproject/_git/myrepo"
        registry = ProviderRegistry()
        
        # Should use environment variable automatically
        auth_url = registry.get_authenticated_url(url)
        assert "env_token" in auth_url
        
        # Parse URL through registry
        components = registry.parse_url(url)
        assert components is not None
        assert components['organization'] == 'myorg'
        assert components['project'] == 'myproject'
        assert components['repo'] == 'myrepo'
    
    def test_multiple_provider_coexistence(self):
        """Test that Azure DevOps and GitHub providers can coexist."""
        registry = ProviderRegistry()
        
        # Test Azure DevOps URL
        azure_url = "https://dev.azure.com/myorg/myproject/_git/myrepo"
        azure_provider = registry.get_provider(azure_url)
        assert azure_provider is not None
        assert isinstance(azure_provider, AzureDevOpsProvider)
        
        # Test GitHub URL (should get different provider)
        from code_expert.repository.providers.github import GitHubProvider
        github_url = "https://github.com/owner/repo"
        github_provider = registry.get_provider(github_url)
        assert github_provider is not None
        assert isinstance(github_provider, GitHubProvider)
        
        # Verify they're different instances
        assert azure_provider != github_provider
        assert azure_provider.get_provider_name() != github_provider.get_provider_name()