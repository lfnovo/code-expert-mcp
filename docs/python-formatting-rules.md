# Python Formatting Rules

## Automatic Formatting Requirement

As an AI assistant, I MUST:

1. Run `black` and `isort` after EVERY Python code modification, including:
   - Creating new Python files
   - Modifying existing Python files
   - Generating Python code snippets
   - Creating/modifying Python tests

2. Apply formatting in this order:
   ```bash
   black <file_path>  # Format code style
   isort <file_path>  # Sort imports
   ```

3. For multiple files in one operation:
   ```bash
   black <directory>
   isort <directory>
   ```

4. Use project-specific configurations from pyproject.toml:
   - black: line length, target versions, etc.
   - isort: profile, line length, import order, etc.

## Implementation Details

1. When creating/modifying a single file:
   ```python
   # After generating/modifying code for src/my_module.py
   black src/my_module.py
   isort src/my_module.py
   ```

2. When working with multiple files:
   ```python
   # After generating/modifying code in src/feature/*
   black src/feature/
   isort src/feature/
   ```

3. For code snippets in responses:
   - Format the code before showing it
   - Ensure it matches project style

## Important Notes

- This is NOT optional - formatting MUST be applied every time
- No need to show formatting command output unless there are errors
- Format code BEFORE showing it to the user
- Never skip formatting even for small changes
- Apply to ALL Python files (*.py) regardless of location in project

## Examples

✅ DO Format:
- Python source files (*.py)
- Python test files
- Python scripts
- Generated code snippets

❌ DON'T Format:
- Non-Python files
- String literals within Python code
- Comments or docstrings
- Markdown code blocks that aren't being written to files 