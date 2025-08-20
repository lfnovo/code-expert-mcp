"""
Pattern-based code search implementation.
Following pattern_search_test.py exactly.
"""

import fnmatch
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set

# Default patterns to exclude from searches
DEFAULT_EXCLUDE_DIRS = {
    # Python
    "venv/",
    "env/",
    ".env/",
    ".venv/",
    "__pycache__/",
    "*.pyc",
    ".pytest_cache/",
    ".coverage",
    "htmlcov/",
    "dist/",
    "build/",
    "*.egg-info/",
    ".tox/",
    # Java
    "target/",
    "build/",
    ".gradle/",
    "out/",
    "bin/",
    ".settings/",
    ".idea/",
    "*.class",
    "*.jar",
    "*.war",
    # Common VCS directories
    ".git/",
    ".svn/",
    ".hg/",
    # IDE and editor files
    ".vscode/",
    ".idea/",
    "*.swp",
    "*.swo",
    ".DS_Store",
    "Thumbs.db",
}


class PatternSearcher:
    """Pattern-based code search implementation."""

    def __init__(self):
        self.exclude_patterns = DEFAULT_EXCLUDE_DIRS

    def should_skip_path(self, path: str) -> bool:
        """
        Check if a path should be skipped based on exclude patterns.
        Following pattern_search_test.py implementation exactly.

        Args:
            path: Path to check

        Returns:
            True if path should be skipped, False otherwise
        """
        path_parts = path.split(os.sep)

        for pattern in self.exclude_patterns:
            # Check each part of the path against the pattern
            for part in path_parts:
                if fnmatch.fnmatch(part, pattern.rstrip("/")):
                    return True

            # Also check the full path
            if fnmatch.fnmatch(path, pattern):
                return True

        return False

    async def search_codebase(
        self,
        root_dir: str,
        search_pattern: str,
        file_pattern: Optional[str] = None,
        ignore_case: bool = False,
        max_results: Optional[int] = None,
    ) -> List[Dict]:
        """
        Search codebase for pattern matches.
        Following pattern_search_test.py implementation exactly.

        Args:
            root_dir: Root directory to search
            search_pattern: Regex pattern to search for
            file_pattern: Optional glob pattern to filter files
            ignore_case: Whether to ignore case in pattern matching
            max_results: Optional limit on number of results

        Returns:
            List of matches with file path, line number and content
        """
        flags = re.IGNORECASE if ignore_case else 0
        pattern = re.compile(search_pattern, flags)
        matches = []

        for root, dirs, files in os.walk(root_dir):
            # Skip excluded directories
            dirs[:] = [
                d for d in dirs if not self.should_skip_path(os.path.join(root, d))
            ]

            for file in files:
                # Skip excluded files
                if self.should_skip_path(os.path.join(root, file)):
                    continue

                # Apply file pattern filter if specified
                if file_pattern and not fnmatch.fnmatch(file, file_pattern):
                    continue

                path = os.path.join(root, file)
                rel_path = os.path.relpath(path, root_dir)

                try:
                    with open(path, "r", encoding="utf-8") as f:
                        for i, line in enumerate(f, 1):
                            if pattern.search(line):
                                match = {
                                    "file": rel_path,
                                    "line": i,
                                    "content": line.strip(),
                                }
                                matches.append(match)

                                if max_results and len(matches) >= max_results:
                                    return matches

                except (UnicodeDecodeError, PermissionError):
                    continue  # Skip binary/inaccessible files

        return matches
