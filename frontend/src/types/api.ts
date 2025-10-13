import type { Repository } from './repository';

/**
 * Request body for POST /api/repos/clone
 */
export interface CloneRequest {
  /** Repository URL (required) */
  url: string;
  /** Optional branch name (defaults to repo default branch) */
  branch?: string;
  /** Cache strategy (defaults to "shared") */
  cache_strategy?: 'shared' | 'per-branch';
}

/**
 * Response from POST /api/repos/clone
 */
export interface CloneResponse {
  /** Operation status */
  status: 'pending' | 'already_cloned' | 'switched_branch';
  /** Human-readable status message */
  message: string;
  /** Optional path to cached repository */
  path?: string;
  /** Cache strategy being used */
  cache_strategy?: string;
  /** Current branch of the repository */
  current_branch?: string;
}

/**
 * Response from GET /api/repos
 */
export interface ListRepositoriesResponse {
  /** Response status */
  status: 'success';
  /** Number of repositories currently cached */
  total_cached: number;
  /** Maximum allowed cached repositories */
  max_cached_repos: number;
  /** Cache directory path */
  cache_dir: string;
  /** List of cached repositories */
  repositories: Repository[];
}

/**
 * Response from DELETE /api/repos
 */
export interface DeleteResponse {
  /** Response status */
  status: 'success';
  /** Human-readable status message */
  message: string;
  /** URL of deleted repository */
  url?: string;
  /** Path that was removed */
  cache_path?: string;
}

/**
 * Standard error response format
 */
export interface ErrorResponse {
  /** Always "error" to indicate error response */
  status: 'error';
  /** Human-readable error message */
  error: string;
  /** Optional actionable suggestion for resolution */
  suggestion?: string;
}
