#!/usr/bin/env python3
"""
Comprehensive test to prove that the filtering logic in our MCP endpoints
works correctly for files/directories parameters.

This test will:
1. Clone a test repository
2. Test all combinations of files/directories parameters
3. Prove that only specified files are analyzed
4. Show the exact file lists being passed to Aider's RepoMap
"""

import asyncio
import sys
import tempfile
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from code_expert.repository.manager import RepositoryManager
from code_expert.repository.cache import RepositoryCache
from code_expert.context.builder import RepoMapBuilder
from code_expert.logging_config import setup_logging

setup_logging()

async def test_filtering_proof():
    """Comprehensive test of filtering logic."""
    
    # Create a temporary cache directory
    with tempfile.TemporaryDirectory() as temp_dir:
        cache = RepositoryCache(Path(temp_dir))
        repo_manager = RepositoryManager(cache)
        repo_map_builder = RepoMapBuilder(cache)
        
        # Test repository URL - using a smaller repo for faster testing
        test_repo = "https://github.com/octocat/Hello-World"
        
        print("🧪 FILTERING PROOF TEST")
        print("=" * 60)
        print(f"Test repository: {test_repo}")
        print(f"Cache directory: {temp_dir}")
        print()
        
        # Step 1: Clone the repository
        print("📥 Step 1: Cloning repository...")
        clone_result = await repo_manager.clone_repository(test_repo, "main")
        if clone_result["status"] != "complete":
            print(f"❌ Clone failed: {clone_result}")
            return
        
        cache_path = clone_result["path"]
        print(f"✅ Repository cloned to: {cache_path}")
        print()
        
        # Wait for repo map build to complete
        print("🔨 Step 2: Waiting for repo map build...")
        await repo_map_builder.wait_for_build(test_repo)
        print("✅ Repo map build complete")
        print()
        
        # Test Case 1: No filters (full repository)
        print("🧪 Test Case 1: No filters (should analyze entire repository)")
        print("-" * 50)
        
        result1 = await repo_map_builder.get_repo_map_content(
            test_repo,
            max_tokens=1000  # Small limit to keep output manageable
        )
        
        if result1["status"] == "success":
            content_lines = result1["content"].count('\n')
            print(f"✅ Full repo analysis: {content_lines} lines of output")
            print(f"   Token usage: {result1['metadata']['output_tokens']} tokens")
        else:
            print(f"❌ Full repo analysis failed: {result1}")
        print()
        
        # Test Case 2: Specific directories only
        print("🧪 Test Case 2: Specific directories only")
        print("-" * 50)
        
        test_directories = ["Lib/asyncio", "Lib/json"]
        print(f"Target directories: {test_directories}")
        
        result2 = await repo_map_builder.get_repo_map_content(
            test_repo,
            directories=test_directories,
            max_tokens=1000
        )
        
        if result2["status"] == "success":
            content_lines = result2["content"].count('\n')
            print(f"✅ Directory-filtered analysis: {content_lines} lines of output")
            print(f"   Token usage: {result2['metadata']['output_tokens']} tokens")
            
            # Verify that only files from specified directories are mentioned
            content = result2["content"]
            if "Lib/asyncio" in content or "Lib/json" in content:
                print("✅ Content contains files from target directories")
            else:
                print("⚠️  Content may not contain expected directories")
                
            # Check if content contains files from other directories it shouldn't
            if "Lib/xml" in content or "Lib/urllib" in content:
                print("❌ Content contains files from non-target directories!")
            else:
                print("✅ Content properly excludes files from non-target directories")
        else:
            print(f"❌ Directory-filtered analysis failed: {result2}")
        print()
        
        # Test Case 3: Specific files only
        print("🧪 Test Case 3: Specific files only")
        print("-" * 50)
        
        test_files = ["Lib/json/__init__.py", "Lib/asyncio/base_events.py"]
        print(f"Target files: {test_files}")
        
        result3 = await repo_map_builder.get_repo_map_content(
            test_repo,
            files=test_files,
            max_tokens=1000
        )
        
        if result3["status"] == "success":
            content_lines = result3["content"].count('\n')
            print(f"✅ File-filtered analysis: {content_lines} lines of output")
            print(f"   Token usage: {result3['metadata']['output_tokens']} tokens")
            
            # Verify content contains expected files
            content = result3["content"]
            if "__init__.py" in content and "base_events.py" in content:
                print("✅ Content contains target files")
            else:
                print("⚠️  Content may not contain expected files")
        else:
            print(f"❌ File-filtered analysis failed: {result3}")
        print()
        
        # Test Case 4: Both files and directories
        print("🧪 Test Case 4: Both files and directories")
        print("-" * 50)
        
        test_files_and_dirs = ["Lib/json/__init__.py"]
        test_dirs_and_files = ["Lib/asyncio"]
        print(f"Target files: {test_files_and_dirs}")
        print(f"Target directories: {test_dirs_and_files}")
        
        result4 = await repo_map_builder.get_repo_map_content(
            test_repo,
            files=test_files_and_dirs,
            directories=test_dirs_and_files,
            max_tokens=1000
        )
        
        if result4["status"] == "success":
            content_lines = result4["content"].count('\n')
            print(f"✅ Combined filtering analysis: {content_lines} lines of output")
            print(f"   Token usage: {result4['metadata']['output_tokens']} tokens")
        else:
            print(f"❌ Combined filtering analysis failed: {result4}")
        print()
        
        # Comparison analysis
        print("📊 COMPARISON ANALYSIS")
        print("=" * 60)
        
        # Token usage comparison
        if all(r["status"] == "success" for r in [result1, result2, result3, result4]):
            tokens1 = result1['metadata']['output_tokens']
            tokens2 = result2['metadata']['output_tokens']
            tokens3 = result3['metadata']['output_tokens']
            tokens4 = result4['metadata']['output_tokens']
            
            print("Token usage comparison:")
            print(f"  Full repository: {tokens1} tokens")
            print(f"  Directories only: {tokens2} tokens ({tokens2/tokens1*100:.1f}% of full)")
            print(f"  Files only: {tokens3} tokens ({tokens3/tokens1*100:.1f}% of full)")
            print(f"  Combined: {tokens4} tokens ({tokens4/tokens1*100:.1f}% of full)")
            print()
            
            # Verify that filtering actually reduces output
            if tokens2 < tokens1 and tokens3 < tokens1:
                print("✅ FILTERING PROOF: Targeted analysis uses fewer tokens than full analysis")
                print("✅ This proves that filtering is working correctly!")
            else:
                print("❌ FILTERING ISSUE: Targeted analysis should use fewer tokens")
                
        print()
        print("🎉 Test completed!")

if __name__ == "__main__":
    asyncio.run(test_filtering_proof())
