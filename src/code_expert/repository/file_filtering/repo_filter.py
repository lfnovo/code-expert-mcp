"""
Centralized repository file filtering implementation.
Handles .gitignore patterns and language-specific filtering.
"""

from pathlib import Path
import pathspec
from typing import List, Optional, Set
from identify import identify
import logging

logger = logging.getLogger(__name__)


class RepoFilter:
    def __init__(self, root_path: Path):
        """
        Initialize filter with root path of cloned repository.

        Args:
            root_path: Path to root of cloned repository
        """
        self.root_path = Path(root_path)
        self.allowed_extensions = self._load_extensions()
        self.gitignore_spec = self._load_gitignore()

    def _load_gitignore(self) -> Optional[pathspec.PathSpec]:
        """Load .gitignore patterns if file exists"""
        gitignore_path = self.root_path / ".gitignore"
        if not gitignore_path.exists():
            return None

        try:
            with open(gitignore_path) as f:
                patterns = f.read().splitlines()
            return pathspec.PathSpec.from_lines(
                pathspec.patterns.GitWildMatchPattern, patterns
            )
        except Exception as e:
            logger.warning(f"Failed to load .gitignore from {gitignore_path}: {e}")
            return None

    def _load_extensions(self) -> Set[str]:
        """Load allowed extensions from the language_extensions.txt resource file"""
        resource_path = (
            Path(__file__).parent.parent.parent
            / "resources"
            / "language_extensions.txt"
        )
        try:
            with open(resource_path, "r", encoding="utf-8") as f:
                return {line.strip() for line in f if line.strip()}
        except Exception as e:
            logger.error(f"Failed to load language extensions: {e}")
            return set()

    def should_include(self, path: Path) -> bool:
        """
        Determine if file should be included based on:
        1. Not matched by .gitignore patterns (fastest check, excludes large dirs)
        2. Has allowed extension (fast string check)
        3. Is a text file (more expensive check)
        """
        try:
            # Get path relative to root for gitignore matching
            rel_path = path.relative_to(self.root_path)

            # Check gitignore patterns first for early exit
            if self.gitignore_spec and self.gitignore_spec.match_file(str(rel_path)):
                return False

            # Basic file check
            if not path.is_file():
                return False

            # Extension check
            if path.suffix.lower() not in self.allowed_extensions:
                return False

            # Text file check (most expensive)
            return "text" in identify.tags_from_path(str(path))

        except Exception as e:
            logger.warning(f"Error checking file {path}: {e}")
            return False

    def find_source_files(self, directories: Optional[List[str]] = None) -> List[str]:
        """
        Find all source files that should be included.

        Args:
            directories: Optional list of specific directories to scan

        Returns:
            List of absolute paths to included files
        """
        if directories:
            # Scan specific directories
            paths_to_scan = [self.root_path / d for d in directories]
        else:
            # Scan entire repo
            paths_to_scan = [self.root_path]

        result = []
        total_files = 0
        included_files = 0

        for path in paths_to_scan:
            for file_path in path.rglob("*"):
                total_files += 1
                if self.should_include(file_path):
                    included_files += 1
                    result.append(str(file_path))

        logger.debug(
            f"File filtering results - Total files: {total_files}, "
            f"Files matching criteria: {included_files}"
        )
        return sorted(result)

    def find_all_files(self) -> List[str]:
        """
        Find all files not ignored by .gitignore patterns.
        Does not apply extension or text file filtering.

        Returns:
            List of absolute paths to non-ignored files
        """
        result = []
        total_files = 0
        included_files = 0

        for path in self.root_path.rglob("*"):
            if path.is_file():
                total_files += 1
                # Get path relative to root for gitignore matching
                rel_path = path.relative_to(self.root_path)

                # Only check gitignore patterns
                if not (
                    self.gitignore_spec
                    and self.gitignore_spec.match_file(str(rel_path))
                ):
                    included_files += 1
                    result.append(str(path))

        logger.debug(
            f"File filtering results - Total files: {total_files}, "
            f"Files not ignored: {included_files}"
        )
        return sorted(result)
