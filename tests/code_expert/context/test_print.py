import pytest
from code_expert.context.extractor import RepoMapExtractor


@pytest.mark.asyncio
async def test_print_extracted_files():
    # Sample RepoMap output with indentation characters
    repo_map_output = """
    src/:
    ⋮   code_expert/:
    ⋮   │   context/:
    ⋮   │   │   extractor.py:
    ⋮   │   │   processor.py:
    ⋮   │   main.py:
    tests/:
    ⋮   code_expert/:
    ⋮   │   context/:
    ⋮   │   │   test_extractor.py:
    """

    extractor = RepoMapExtractor()
    files = await extractor.extract_files(repo_map_output)

    print("\nActual files extracted:")
    for file in sorted(files):
        print(f"  {file}")
