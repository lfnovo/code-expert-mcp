#!/usr/bin/env python3
"""
Test script to verify AutoRefreshManager integration with RepositoryManager.
"""

import asyncio
import sys
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from code_expert.config import load_config, ServerConfig, RepositoryConfig, AutoRefreshConfig
from code_expert.repository.manager import RepositoryManager

async def test_integration():
    """Test that AutoRefreshManager integrates properly."""
    print("Testing AutoRefreshManager integration...")
    
    # Create test configuration with auto-refresh enabled
    with tempfile.TemporaryDirectory() as temp_dir:
        config = ServerConfig(
            repository=RepositoryConfig(
                cache_dir=temp_dir,
                max_cached_repos=5
            ),
            auto_refresh=AutoRefreshConfig(
                enabled=True,
                active_repo_interval_hours=1,
                inactive_repo_interval_hours=4,
                startup_delay_seconds=1,
                max_concurrent_refreshes=1
            )
        )
        
        # Test 1: Initialize RepositoryManager with auto-refresh enabled
        print("1. Testing RepositoryManager initialization with auto-refresh...")
        repo_manager = RepositoryManager(config.repository, server_config=config)
        
        if repo_manager.auto_refresh_manager:
            print("✓ AutoRefreshManager successfully initialized")
        else:
            print("✗ AutoRefreshManager not initialized")
            return False
        
        # Test 2: Start auto-refresh system
        print("2. Testing auto-refresh startup...")
        try:
            await repo_manager.start_auto_refresh()
            print("✓ Auto-refresh started successfully")
        except Exception as e:
            print(f"✗ Auto-refresh startup failed: {e}")
            return False
        
        # Test 3: Get auto-refresh status
        print("3. Testing auto-refresh status...")
        try:
            status = await repo_manager.get_auto_refresh_status()
            if status.get("status") == "running":
                print("✓ Auto-refresh status shows running")
            else:
                print(f"✓ Auto-refresh status: {status}")
        except Exception as e:
            print(f"✗ Auto-refresh status failed: {e}")
            return False
        
        # Test 4: Stop auto-refresh system
        print("4. Testing auto-refresh shutdown...")
        try:
            await repo_manager.stop_auto_refresh()
            print("✓ Auto-refresh stopped successfully")
        except Exception as e:
            print(f"✗ Auto-refresh shutdown failed: {e}")
            return False
        
        # Test 5: Test with auto-refresh disabled
        print("5. Testing with auto-refresh disabled...")
        config_disabled = ServerConfig(
            repository=RepositoryConfig(
                cache_dir=temp_dir,
                max_cached_repos=5
            ),
            auto_refresh=AutoRefreshConfig(enabled=False)
        )
        
        repo_manager_disabled = RepositoryManager(config_disabled.repository, server_config=config_disabled)
        if repo_manager_disabled.auto_refresh_manager is None:
            print("✓ AutoRefreshManager correctly disabled")
        else:
            print("✗ AutoRefreshManager should be None when disabled")
            return False
        
        print("\n✅ All tests passed! AutoRefreshManager integration is working correctly.")
        return True

async def main():
    success = await test_integration()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))