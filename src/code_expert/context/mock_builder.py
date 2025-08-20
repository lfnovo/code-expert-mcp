"""
Mock RepoMapBuilder to bypass aider dependency for testing.
"""

class RepoMapBuilder:
    """Mock implementation that doesn't require aider."""
    
    def __init__(self, *args, **kwargs):
        """Initialize with dummy values."""
        pass
    
    def schedule_repo_map_build(self, *args, **kwargs):
        """Mock method that does nothing."""
        pass
    
    async def get_repo_map_content(self, *args, **kwargs):
        """Mock method."""
        return {"status": "mocked", "content": "Mock content"}
    
    async def get_repo_structure(self, *args, **kwargs):
        """Mock method."""
        return {"status": "mocked", "structure": {}}