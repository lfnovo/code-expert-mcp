#!/usr/bin/env python3

import requests
import yaml
import sys
from pathlib import Path


def load_target_languages(file_path):
    """Load the target programming languages from the markdown file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            # Read lines and strip whitespace, filter out empty lines
            return {line.strip() for line in f if line.strip()}
    except IOError as e:
        print(f"Error reading target languages file: {e}", file=sys.stderr)
        sys.exit(1)


def download_languages_file(url):
    """Download the languages.yml file from GitHub."""
    # Get the raw content URL
    raw_url = url.replace("github.com", "raw.githubusercontent.com").replace(
        "/blob/", "/"
    )

    try:
        response = requests.get(raw_url)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"Error downloading file: {e}", file=sys.stderr)
        sys.exit(1)


def extract_programming_languages(yaml_content, target_languages):
    """Parse YAML and extract only target programming language entries."""
    # Languages to include regardless of their type
    additional_languages = {
        # Markup languages we need
        "Astro",  # type: markup
        "Svelte",  # type: markup
        "Vue",  # type: markup
        "Sass",  # type: markup
        "SCSS",  # type: markup
        # Data/markup languages we need
        "JSON",  # type: data
        "YAML",  # type: data
        "HTML",  # type: markup
        "CSS",  # type: markup
        "Gradle",  # type: data
        "TOML",  # type: data
        "XML",  # type: data
    }

    try:
        languages = yaml.safe_load(yaml_content)
        programming_languages = {
            name: details
            for name, details in languages.items()
            if (details.get("type") == "programming" and name in target_languages)
            or name in additional_languages
        }

        # Check which target languages were not found
        found_languages = set(programming_languages.keys())
        missing_languages = (
            target_languages - found_languages - {"JSX", "Terraform", "Bash"}
        )  # Remove ones handled by other nodes
        if missing_languages:
            print("\nWarning: The following target languages were not found:")
            for lang in sorted(missing_languages):
                print(f"- {lang}")
            print(
                "\nNote: Some languages like JSX, Terraform, and Bash are handled through JavaScript, HCL, and Shell nodes respectively."
            )
            print()

        return programming_languages
    except yaml.YAMLError as e:
        print(f"Error parsing YAML: {e}", file=sys.stderr)
        sys.exit(1)


def save_yaml(data, output_file):
    """Save the filtered languages to a YAML file."""
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=False)
    except IOError as e:
        print(f"Error writing output file: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    # URL of the languages.yml file
    url = "https://github.com/github-linguist/linguist/blob/main/lib/linguist/languages.yml"

    # Get paths
    script_dir = Path(__file__).parent
    target_languages_file = script_dir / "target_programming_languages_for_include.md"
    output_file = script_dir / "programming_languages.yml"

    print("Loading target programming languages...")
    target_languages = load_target_languages(target_languages_file)

    print("Downloading languages.yml...")
    yaml_content = download_languages_file(url)

    print("Extracting target programming languages...")
    programming_languages = extract_programming_languages(
        yaml_content, target_languages
    )

    print(
        f"Saving {len(programming_languages)} programming languages to {output_file}..."
    )
    save_yaml(programming_languages, output_file)

    print("Done!")


if __name__ == "__main__":
    main()
