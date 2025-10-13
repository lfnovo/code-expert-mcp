/**
 * Session stored in localStorage
 */
export interface Session {
  /** API password (REPO_API_PASSWORD) */
  password: string;
  /** Unix timestamp of last activity (milliseconds) */
  lastActivity: number;
}

/**
 * Session timeout duration: 24 hours in milliseconds
 */
export const SESSION_TIMEOUT = 24 * 60 * 60 * 1000; // 24 hours

/**
 * localStorage key for session storage
 */
export const SESSION_KEY = 'repo-manager-session';
