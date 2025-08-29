# OSS-251 Auto-Refresh System Implementation Plan

If you are working on this feature, make sure to update this plan.md file as you go.

## PHASE 1: Core Infrastructure and Configuration [Completed ✅]

**Goal**: Build the foundational auto-refresh system with configuration support and basic scheduling.

**Time Estimate**: 2 hours ➡️ **Actual Time**: ~1.5 hours

### Task 1.1: Extend Configuration System [Completed ✅]

**Location**: `src/code_expert/config.py`

Add auto-refresh configuration to the existing config system:
- Add `AutoRefreshConfig` dataclass with fields:
  - `enabled: bool = True`
  - `active_repo_interval_hours: int = 24` (repos with commits < 7 days)
  - `inactive_repo_interval_hours: int = 168` (repos with commits >= 7 days) 
  - `startup_delay_seconds: int = 30` (delay before first auto-refresh)
  - `max_concurrent_refreshes: int = 2` (resource limit)
  - `activity_threshold_days: int = 7` (threshold for active vs inactive)

- Integrate into `ServerConfig` with `auto_refresh: AutoRefreshConfig`
- Update default config file `src/code_expert/config/config.yaml`

**Files Modified**: 
- `src/code_expert/config.py` 
- `src/code_expert/config/config.yaml`

### Task 1.2: Create AutoRefreshManager Core [Completed ✅]

**Location**: `src/code_expert/repository/auto_refresh.py`

Build the core auto-refresh management class:
- `AutoRefreshManager` class with:
  - `__init__(config: AutoRefreshConfig, repository_manager: RepositoryManager)`
  - `start()` - Initialize background scheduling
  - `stop()` - Cleanup and shutdown
  - `schedule_repository_refresh(repo_path: str)` - Add repo to schedule
  - `_calculate_next_refresh_time(repo_path: str) -> datetime` - Based on activity
  - `_is_repository_active(repo_path: str) -> bool` - Check commit age
  - `_refresh_worker()` - Background task worker
  
- Semaphore for concurrent refresh limiting
- Queue-based scheduling using `asyncio.Queue`

**Files Created**: 
- `src/code_expert/repository/auto_refresh.py`

### Task 1.3: Integrate with RepositoryManager [Completed ✅]

**Location**: `src/code_expert/repository/manager.py`

Add auto-refresh integration to existing `RepositoryManager`:
- Add `auto_refresh_manager: Optional[AutoRefreshManager]` field
- Initialize in `__init__()` if config enabled
- Add `start_auto_refresh()` and `stop_auto_refresh()` methods
- Hook auto-refresh scheduling after successful clone/refresh in `_do_clone()` and `_do_refresh()`

**Files Modified**: 
- `src/code_expert/repository/manager.py`

### Task 1.4: Basic Activity Analysis [Completed ✅]

**Location**: `src/code_expert/repository/auto_refresh.py`

Implement repository activity detection:
- `_get_last_commit_date(repo_path: str) -> Optional[datetime]`
- Handle both Git repos and local directories
- Git: Use `git log -1 --format="%cd" --date=iso`
- Local: Use most recent file modification time
- Error handling for invalid repos

**Files Modified**: 
- `src/code_expert/repository/auto_refresh.py`

### Comments:
- **Configuration System**: Successfully extended with backward compatibility. Default values are conservative and production-ready.
- **AutoRefreshManager**: Implemented with comprehensive activity analysis covering both Git repositories and local directories. Includes robust error handling and semaphore-based concurrency control.
- **Integration**: Clean integration with RepositoryManager that preserves all existing functionality. Auto-refresh scheduling is triggered after successful clone/refresh operations.
- **Activity Analysis**: Combined with AutoRefreshManager implementation. Handles Git repos using GitPython + subprocess fallback, local dirs using file modification times.
- **Resource Management**: Implements semaphore limiting and queue-based scheduling to prevent system overload during refreshes.

## PHASE 2: Advanced Scheduling and Server Integration [Completed ✅]

**Goal**: Complete the scheduling system and integrate with MCP server startup.

**Time Estimate**: 2 hours ➡️ **Actual Time**: ~2 hours

### Task 2.1: Enhanced Scheduling Logic [Completed ✅]

**Location**: `src/code_expert/repository/auto_refresh.py`

Build the complete scheduling system:
- ✅ Persistent scheduling using repository metadata
- ✅ `_load_scheduled_refreshes()` - Restore schedules on startup with staggered execution
- ✅ Integration with `RepositoryCache` to store next refresh times in metadata
- ✅ Staggered startup refreshes to avoid system load spikes
- ✅ Persistent metadata updates for next refresh times

**Files Modified**: 
- ✅ `src/code_expert/repository/auto_refresh.py` - Added persistent scheduling logic
- ✅ `src/code_expert/repository/cache.py` - Added next_refresh_time field to RepositoryMetadata and update method

### Task 2.2: MCP Server Integration [Completed ✅]

**Location**: `src/code_expert/mcp/server/app.py`

Integrate auto-refresh with server lifecycle:
- ✅ Server lifecycle integration was already implemented in Phase 1
- ✅ Startup and shutdown hooks properly configured
- ✅ Auto-refresh management tools available via MCP
- ✅ Added `get_status()` method to AutoRefreshManager for status reporting

**Files Modified**: 
- ✅ `src/code_expert/repository/auto_refresh.py` - Added comprehensive status reporting
- ✅ MCP server integration was already complete from Phase 1

### Task 2.3: Error Handling and Recovery [Completed ✅]

**Location**: `src/code_expert/repository/auto_refresh.py`

Implement robust error handling:
- ✅ Exponential backoff for failed refreshes (30min base, max 24h delay)
- ✅ Skip repositories after 3 consecutive failures
- ✅ Comprehensive logging for refresh decisions and outcomes
- ✅ Recovery mechanism - re-enable failed repos after 72 hours
- ✅ Error count tracking and reset logic
- ✅ Detailed error statistics in status reporting

**Files Modified**: 
- ✅ `src/code_expert/repository/auto_refresh.py` - Comprehensive error handling and recovery

### Task 2.4: Resource Management [Completed ✅]

**Location**: `src/code_expert/repository/auto_refresh.py`

Add resource controls and monitoring:
- ✅ Enhanced semaphore-based concurrent refresh limiting (already present from Phase 1)
- ✅ Repository refresh status tracking (prevent duplicate refreshes)
- ✅ Integration with existing repository locks from `refresh_repository()`
- ✅ Resource usage monitoring and statistics
- ✅ Performance metrics tracking (duration, success rates)
- ✅ Resource utilization reporting in status

**Files Modified**: 
- ✅ `src/code_expert/repository/auto_refresh.py` - Added resource monitoring and performance tracking

### Comments:
- **Persistent Scheduling**: Successfully implemented with full recovery on startup. Schedules are staggered to prevent startup load spikes, and metadata is consistently updated.
- **Error Handling**: Comprehensive exponential backoff system implemented. Repositories are automatically disabled after 3 consecutive failures and re-enabled after 72 hours of no errors. All error states are tracked and reported.
- **Resource Management**: Enhanced with detailed performance monitoring, resource utilization tracking, and comprehensive statistics. Resource limits are properly enforced.
- **Server Integration**: Lifecycle integration was already solid from Phase 1. Added detailed status reporting to provide visibility into system operation.
- **Reliability**: System is designed to handle failures gracefully, recover from corrupted states, and provide detailed observability for troubleshooting.

### Key Implementation Decisions:
- **Constants**: Defined clear constants for error handling (MAX_CONSECUTIVE_FAILURES=3, MAX_BACKOFF_HOURS=24, etc.)
- **State Management**: All scheduling state is persisted in metadata for recovery
- **Performance**: Resource monitoring tracks timing and success rates for optimization
- **Recovery**: Automatic recovery mechanisms prevent permanent repository disabling
- **Observability**: Comprehensive status reporting provides visibility into all aspects of operation

## PHASE 3: Testing, Observability and Documentation [Not Started ⏳]

**Goal**: Add comprehensive testing, logging, and user documentation.

**Time Estimate**: 2 hours

### Task 3.1: Comprehensive Testing [Not Started ⏳]

**Location**: `tests/`

Create thorough test coverage:
- Unit tests for `AutoRefreshManager` scheduling logic
- Integration tests with `RepositoryManager`  
- Mock tests for Git operations and file system
- Configuration validation tests
- Concurrent refresh scenarios

**Files Created**:
- `tests/test_auto_refresh.py`
- `tests/test_auto_refresh_integration.py`

### Task 3.2: Enhanced Logging and Observability [Not Started ⏳]

**Location**: Multiple files

Add detailed logging for operations and debugging:
- Structured logging for all refresh decisions and outcomes
- Configuration validation and startup logging  
- Performance metrics (refresh times, queue lengths)
- User-friendly status messages in repository metadata

**Files Modified**: 
- `src/code_expert/repository/auto_refresh.py`
- `src/code_expert/repository/manager.py`  
- `src/code_expert/mcp/server/app.py`

### Task 3.3: Configuration Validation [Not Started ⏳]

**Location**: `src/code_expert/config.py`

Add robust configuration validation:
- Validate interval ranges (minimum 1 hour, maximum 1 week)
- Ensure reasonable concurrent refresh limits (1-10)
- Validate activity threshold (1-30 days)
- Helpful error messages for invalid configurations

**Files Modified**: 
- `src/code_expert/config.py`

### Task 3.4: Documentation and User Guide [Not Started ⏳]

**Location**: Documentation files

Create user-facing documentation:
- Update README.md with auto-refresh configuration examples
- Create configuration guide showing all options
- Document interaction with manual refresh operations
- Add troubleshooting section for common issues

**Files Modified**:
- `README.md`
- `docs/` (new configuration guide)

## Implementation Dependencies and Sequencing

### Sequential Dependencies
- **Phase 1 must complete before Phase 2**: Core infrastructure needed before server integration
- **Task 1.1 → 1.2**: Configuration must exist before AutoRefreshManager
- **Task 1.2 → 1.3**: AutoRefreshManager must exist before RepositoryManager integration
- **Task 2.1 → 2.2**: Scheduling logic must be complete before server integration

### Parallel Work Opportunities
- **Task 1.4** can be developed alongside **Task 1.2-1.3**
- **Task 3.1** and **Task 3.2** can be developed in parallel
- **Task 2.3** and **Task 2.4** can be developed simultaneously
- **Task 3.3** and **Task 3.4** are independent of each other

## Key Technical Considerations

### Architecture Decisions Validated
- ✅ Extends existing `RepositoryManager` and `RepositoryCache` (preserves current functionality)
- ✅ Uses existing async patterns and background task infrastructure  
- ✅ Leverages current file locking and concurrency controls
- ✅ Integrates with existing YAML configuration system
- ✅ Maintains compatibility with manual refresh operations

### Critical Implementation Notes
1. **Preserve Existing Functionality**: All manual refresh operations must continue working unchanged
2. **Resource Safety**: Use semaphores and existing locks to prevent system overload  
3. **Configuration Flexibility**: All timing and behavior must be user-configurable
4. **Graceful Startup**: Stagger initial refreshes to avoid startup performance impact
5. **Error Resilience**: Failed refreshes should not break the scheduling system

### Testing Strategy
- **Unit Tests**: Focus on scheduling logic and configuration validation
- **Integration Tests**: End-to-end refresh pipeline with mocked Git operations  
- **Performance Tests**: Concurrent refresh behavior under load
- **Configuration Tests**: All possible config combinations and edge cases

This implementation provides a solid foundation for automatic repository refreshes while maintaining the existing system's reliability and performance characteristics.