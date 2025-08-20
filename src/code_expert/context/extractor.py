"""
RepoMap output processing and extraction.
Following extract_repo_files.py implementation exactly.
"""

from pathlib import Path
from typing import Set, Dict, Any, List
import re


class RepoMapExtractor:
    """Handles extraction and processing of RepoMap output."""

    async def extract_files(self, repo_map_output: str) -> Set[str]:
        """
        Extract file paths from RepoMap output following extract_repo_files.py exactly.

        Args:
            repo_map_output: Raw RepoMap output string

        Returns:
            Set of unique file paths found in the output
        """
        unique_files = set()

        # Process each line, following extract_repo_files.py implementation
        for line in repo_map_output.splitlines():
            # Skip lines with special characters used for indentation/structure
            if any(c in line for c in "⋮│"):
                continue

            # Remove colons and whitespace
            line = line.strip().rstrip(":")
            if line:
                unique_files.add(line)

        return unique_files

    async def process_repo_map(self, repo_map_output: str) -> Dict[str, Any]:
        """
        Process and structure RepoMap output for API consumption.

        Args:
            repo_map_output: Raw RepoMap output string

        Returns:
            Structured dictionary of RepoMap information
        """
        files = await self.extract_files(repo_map_output)

        # Structure the output following the example format
        return {
            "files": sorted(list(files)),
            "total_files": len(files),
            "file_types": self._count_file_types(files),
            "directories": self._extract_directories(files),
        }

    def _count_file_types(self, files: Set[str]) -> Dict[str, int]:
        """Count occurrences of each file extension."""
        extension_counts = {}
        for file in files:
            ext = Path(file).suffix
            if ext:
                # Remove the dot from extension
                ext = ext[1:]
                extension_counts[ext] = extension_counts.get(ext, 0) + 1
        return extension_counts

    def _extract_directories(self, files: Set[str]) -> List[str]:
        """Extract unique directories from file paths."""
        directories = set()
        for file in files:
            parent = str(Path(file).parent)
            if parent != ".":
                directories.add(parent)
        return sorted(list(directories))
