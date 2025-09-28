#!/usr/bin/env python3
"""Performance benchmarks for provider framework."""

import time
import statistics
from pathlib import Path

from code_expert.repository.path_utils import is_git_url, get_cache_path
from code_expert.repository.providers import get_provider, get_default_registry


def benchmark_url_detection(iterations=1000):
    """Benchmark URL detection performance."""
    urls = [
        "https://github.com/owner/repo",
        "https://dev.azure.com/org/project/_git/repo",
        "git@github.com:owner/repo.git",
        "git@ssh.dev.azure.com:v3/org/project/repo",
        "/local/path/to/repo",
        "https://example.com/not/a/git/url",
    ]
    
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        for url in urls:
            is_git_url(url)
        end = time.perf_counter()
        times.append(end - start)
    
    return {
        "mean": statistics.mean(times) * 1000,  # Convert to ms
        "median": statistics.median(times) * 1000,
        "stdev": statistics.stdev(times) * 1000 if len(times) > 1 else 0,
        "min": min(times) * 1000,
        "max": max(times) * 1000,
        "ops_per_sec": len(urls) * iterations / sum(times)
    }


def benchmark_provider_lookup(iterations=1000):
    """Benchmark provider lookup performance."""
    urls = [
        "https://github.com/owner/repo",
        "https://dev.azure.com/org/project/_git/repo",
        "https://gitlab.com/owner/repo",  # No provider
        "https://bitbucket.org/owner/repo",  # No provider
    ]
    
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        for url in urls:
            get_provider(url)
        end = time.perf_counter()
        times.append(end - start)
    
    return {
        "mean": statistics.mean(times) * 1000,
        "median": statistics.median(times) * 1000,
        "stdev": statistics.stdev(times) * 1000 if len(times) > 1 else 0,
        "min": min(times) * 1000,
        "max": max(times) * 1000,
        "ops_per_sec": len(urls) * iterations / sum(times)
    }


def benchmark_cache_path_generation(iterations=1000):
    """Benchmark cache path generation performance."""
    cache_dir = Path("/tmp/cache")
    urls = [
        ("https://github.com/owner/repo", None, False),
        ("https://dev.azure.com/org/project/_git/repo", None, False),
        ("https://github.com/owner/repo", "main", True),
        ("https://dev.azure.com/org/project/_git/repo", "feature/test", True),
    ]
    
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        for url, branch, per_branch in urls:
            get_cache_path(cache_dir, url, branch, per_branch)
        end = time.perf_counter()
        times.append(end - start)
    
    return {
        "mean": statistics.mean(times) * 1000,
        "median": statistics.median(times) * 1000,
        "stdev": statistics.stdev(times) * 1000 if len(times) > 1 else 0,
        "min": min(times) * 1000,
        "max": max(times) * 1000,
        "ops_per_sec": len(urls) * iterations / sum(times)
    }


def benchmark_authentication(iterations=1000):
    """Benchmark authentication URL generation performance."""
    import os
    
    # Set up test tokens
    os.environ["GITHUB_PERSONAL_ACCESS_TOKEN"] = "ghp_test_token_123"
    os.environ["AZURE_DEVOPS_PAT"] = "ado_test_token_456"
    
    urls = [
        "https://github.com/owner/repo",
        "https://dev.azure.com/org/project/_git/repo",
        "git@github.com:owner/repo.git",
        "git@ssh.dev.azure.com:v3/org/project/repo",
    ]
    
    registry = get_default_registry()
    
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        for url in urls:
            registry.get_authenticated_url(url)
        end = time.perf_counter()
        times.append(end - start)
    
    # Clean up
    os.environ.pop("GITHUB_PERSONAL_ACCESS_TOKEN", None)
    os.environ.pop("AZURE_DEVOPS_PAT", None)
    
    return {
        "mean": statistics.mean(times) * 1000,
        "median": statistics.median(times) * 1000,
        "stdev": statistics.stdev(times) * 1000 if len(times) > 1 else 0,
        "min": min(times) * 1000,
        "max": max(times) * 1000,
        "ops_per_sec": len(urls) * iterations / sum(times)
    }


def format_results(name, results):
    """Format benchmark results for display."""
    print(f"\n{name}")
    print("=" * 60)
    print(f"Mean:    {results['mean']:.3f} ms")
    print(f"Median:  {results['median']:.3f} ms")
    print(f"Std Dev: {results['stdev']:.3f} ms")
    print(f"Min:     {results['min']:.3f} ms")
    print(f"Max:     {results['max']:.3f} ms")
    print(f"Ops/sec: {results['ops_per_sec']:,.0f}")


def main():
    """Run all benchmarks."""
    print("Provider Framework Performance Benchmarks")
    print("=" * 60)
    print("Running benchmarks with 1000 iterations each...")
    
    # Warm up
    print("\nWarming up...")
    benchmark_url_detection(10)
    benchmark_provider_lookup(10)
    benchmark_cache_path_generation(10)
    benchmark_authentication(10)
    
    # Run benchmarks
    print("\nRunning benchmarks...")
    
    results = benchmark_url_detection(1000)
    format_results("URL Detection (6 URLs)", results)
    
    results = benchmark_provider_lookup(1000)
    format_results("Provider Lookup (4 URLs)", results)
    
    results = benchmark_cache_path_generation(1000)
    format_results("Cache Path Generation (4 URLs)", results)
    
    results = benchmark_authentication(1000)
    format_results("Authentication URL Generation (4 URLs)", results)
    
    print("\n" + "=" * 60)
    print("Benchmark complete!")


if __name__ == "__main__":
    main()