/**
 * Clone operation status information
 */
export interface CloneStatus {
  /** Current status: pending, cloning, complete, failed */
  status: 'pending' | 'cloning' | 'complete' | 'failed';
  /** ISO 8601 timestamp when clone started */
  started_at: string | null;
  /** ISO 8601 timestamp when clone completed */
  completed_at: string | null;
  /** Error message if clone failed */
  error: string | null;
}

/**
 * Repository map generation status information
 */
export interface RepoMapStatus {
  /** Current status: pending, building, complete, failed */
  status: 'pending' | 'building' | 'complete' | 'failed';
  /** ISO 8601 timestamp when generation started */
  started_at: string | null;
  /** ISO 8601 timestamp when generation completed */
  completed_at: string | null;
  /** Error message if generation failed */
  error: string | null;
}

/**
 * Repository metadata from API
 */
export interface Repository {
  /** Full path to cached repository */
  cache_path: string;
  /** Repository URL (GitHub, Azure DevOps, etc.) */
  url: string;
  /** ISO 8601 timestamp of last access */
  last_access: string;
  /** Current branch name */
  current_branch: string;
  /** Cache strategy: shared or per-branch */
  cache_strategy: 'shared' | 'per-branch';
  /** Clone operation status */
  clone_status: CloneStatus;
  /** Repository map generation status */
  repo_map_status: RepoMapStatus;
  /** Cache size in bytes */
  cache_size_bytes: number;
  /** Cache size in megabytes */
  cache_size_mb: number;
}
