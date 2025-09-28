import pytest
from code_expert.context.extractor import RepoMapExtractor


@pytest.mark.asyncio
async def test_extract_files_with_indentation_format():
    # Sample RepoMap output with indentation characters
    repo_map_output = """
src/main/java/com/taskmanager/TaskManagerApplication.java:
⋮
│@SpringBootApplication
│public class TaskManagerApplication {
│    public static void main(String[] args) {
tests/java/com/taskmanager/TaskManagerApplicationTest.java:
⋮
│@SpringBootTest
│public class TaskManagerApplicationTest {
    """

    extractor = RepoMapExtractor()
    files = await extractor.extract_files(repo_map_output)

    expected_files = {
        "src/main/java/com/taskmanager/TaskManagerApplication.java",
        "tests/java/com/taskmanager/TaskManagerApplicationTest.java",
    }

    assert files == expected_files


@pytest.mark.asyncio
async def test_extract_files_empty_input():
    extractor = RepoMapExtractor()
    files = await extractor.extract_files("")
    assert files == set()


@pytest.mark.asyncio
async def test_extract_files_no_valid_paths():
    # Input with only special characters and no valid paths
    repo_map_output = """
    ⋮   │   │
    ⋮   │
    ⋮
    """
    extractor = RepoMapExtractor()
    files = await extractor.extract_files(repo_map_output)
    assert files == set()


@pytest.mark.asyncio
async def test_extract_files_mixed_format():
    # Test with mixed format including some malformed lines
    repo_map_output = """
src/file1.py:
⋮   Some content
src/file2.py:
⋮   More content
src/file3.py:
⋮   Even more content
    """

    extractor = RepoMapExtractor()
    files = await extractor.extract_files(repo_map_output)

    expected_files = {"src/file1.py", "src/file2.py", "src/file3.py"}

    assert files == expected_files
