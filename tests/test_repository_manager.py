import pytest
from pathlib import Path
import shutil
import git
from git.repo import Repo

from code_expert.repository import Repository, RepositoryManager
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


# ... existing tests ...
