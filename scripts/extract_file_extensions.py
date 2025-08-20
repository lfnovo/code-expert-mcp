#!/usr/bin/env python3

import yaml
import argparse
from pathlib import Path
from typing import Set


def extract_extensions(yaml_data: dict) -> Set[str]:
    """Extract all unique file extensions from the YAML data."""
    extensions = set()

    for language, data in yaml_data.items():
        if isinstance(data, dict) and "extensions" in data:
            # Add all extensions from this language
            extensions.update(ext.lstrip(".") for ext in data["extensions"])

    return extensions


def main():
    parser = argparse.ArgumentParser(
        description="Extract unique file extensions from a languages YAML file"
    )
    parser.add_argument(
        "--input",
        "-i",
        default="programming_languages.yml",
        help="Input YAML file (default: programming_languages.yml)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="unique_extensions.txt",
        help="Output file for unique extensions (default: unique_extensions.txt)",
    )
    parser.add_argument(
        "--keep-dots",
        "-d",
        action="store_true",
        help="Keep the leading dots in extensions",
    )
    args = parser.parse_args()

    try:
        # Read and parse the YAML file
        print(f"Reading {args.input}...")
        with open(args.input, "r", encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f)

        # Extract unique extensions
        print("Extracting unique extensions...")
        extensions = extract_extensions(yaml_data)

        # Sort extensions
        sorted_extensions = sorted(extensions)

        # Add dots back if requested
        if args.keep_dots:
            sorted_extensions = [f".{ext}" for ext in sorted_extensions]

        # Write to output file
        print(f"Writing {len(sorted_extensions)} unique extensions to {args.output}...")
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("\n".join(sorted_extensions))
            f.write("\n")  # Add final newline

        print("Done!")
        print(f"Found {len(sorted_extensions)} unique file extensions")

    except FileNotFoundError as e:
        print(f"Error: Could not find file: {e.filename}")
        exit(1)
    except yaml.YAMLError as e:
        print(f"Error: Invalid YAML file: {e}")
        exit(1)
    except Exception as e:
        print(f"Error: An unexpected error occurred: {e}")
        exit(1)


if __name__ == "__main__":
    main()
