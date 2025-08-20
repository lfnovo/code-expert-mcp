#!/usr/bin/env python3
"""Test Azure DevOps short URL format."""

from code_expert.repository.providers import get_provider
from code_expert.repository.path_utils import is_git_url, get_cache_path
from pathlib import Path

# Test URLs
urls = [
    "https://dev.azure.com/nordresearch/NordInvestimentos.Marilinha",  # Short format
    "https://dev.azure.com/nordresearch/NordInvestimentos.Marilinha/_git/NordInvestimentos.Marilinha",  # Full format
    "https://dev.azure.com/org/project",  # Another short format
    "https://dev.azure.com/org/project/_git/repo",  # Full format
]

print("Testing Azure DevOps URL formats:\n")
print("=" * 60)

for url in urls:
    print(f"\nURL: {url}")
    print("-" * 60)
    
    # Test if recognized as Git URL
    is_git = is_git_url(url)
    print(f"Is Git URL: {is_git}")
    
    # Test provider detection
    provider = get_provider(url)
    if provider:
        print(f"Provider: {provider.get_provider_name()}")
        
        # Test URL parsing
        try:
            components = provider.parse_url(url)
            print("Parsed components:")
            print(f"  Organization: {components.get('organization')}")
            print(f"  Project: {components.get('project')}")
            print(f"  Repository: {components.get('repo')}")
            print(f"  Ref: {components.get('ref')}")
        except Exception as e:
            print(f"Parse error: {e}")
        
        # Test cache path generation
        cache_path = get_cache_path(Path("/tmp/cache"), url)
        print(f"Cache path: {cache_path}")
        
        # Test authentication
        auth_url = provider.get_authenticated_url(url, "test_token_123")
        print(f"Auth URL: {auth_url}")
    else:
        print("No provider found!")

print("\n" + "=" * 60)
print("Test complete!")