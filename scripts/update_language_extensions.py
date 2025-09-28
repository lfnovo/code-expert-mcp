#!/usr/bin/env python3

import subprocess
import sys
from pathlib import Path


def run_command(command: list[str], description: str, cwd: Path) -> None:
    """Run a command and handle its output and errors."""
    print(f"\n=== {description} ===")
    try:
        result = subprocess.run(
            command, check=True, capture_output=True, text=True, cwd=str(cwd)
        )
        print(result.stdout)
        if result.stderr:
            print("Warnings:", file=sys.stderr)
            print(result.stderr, file=sys.stderr)
    except subprocess.CalledProcessError as e:
        print(f"Error during {description}:", file=sys.stderr)
        print(e.stderr, file=sys.stderr)
        sys.exit(1)


def main():
    # Get absolute paths
    scripts_dir = Path(__file__).parent.absolute()

    # Step 1: Download and extract programming languages
    extract_cmd = [
        sys.executable,
        str(scripts_dir / "extract_programming_languages.py"),
    ]
    run_command(
        extract_cmd, "Downloading and extracting programming languages", scripts_dir
    )

    # Step 2: Extract file extensions
    extensions_cmd = [
        sys.executable,
        str(scripts_dir / "extract_file_extensions.py"),
        "--input",
        str(scripts_dir / "programming_languages.yml"),
        "--output",
        str(scripts_dir / "language_extensions.txt"),
        "--keep-dots",  # Keep the dots for better readability
    ]
    run_command(extensions_cmd, "Extracting unique file extensions", scripts_dir)

    print("\n=== Process completed successfully ===")
    print("Generated files in", scripts_dir)
    print("- programming_languages.yml (filtered languages)")
    print("- language_extensions.txt (unique file extensions)")


if __name__ == "__main__":
    main()
