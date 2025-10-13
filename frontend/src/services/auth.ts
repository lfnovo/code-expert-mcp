import type { Session } from '@/types/session';
import { SESSION_KEY, SESSION_TIMEOUT } from '@/types/session';

/**
 * Get session from localStorage
 */
export function getSession(): Session | null {
  const sessionStr = localStorage.getItem(SESSION_KEY);
  if (!sessionStr) return null;

  try {
    return JSON.parse(sessionStr) as Session;
  } catch {
    // Invalid session data, clear it
    clearSession();
    return null;
  }
}

/**
 * Save session to localStorage
 */
export function saveSession(session: Session): void {
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

/**
 * Clear session from localStorage
 */
export function clearSession(): void {
  localStorage.removeItem(SESSION_KEY);
}

/**
 * Check if session is still valid (within 24-hour timeout)
 */
export function isSessionValid(session: Session | null): boolean {
  if (!session) return false;

  const now = Date.now();
  const timeSinceLastActivity = now - session.lastActivity;

  return timeSinceLastActivity < SESSION_TIMEOUT;
}

/**
 * Update session activity timestamp
 */
export function updateSessionActivity(): void {
  const session = getSession();
  if (session) {
    session.lastActivity = Date.now();
    saveSession(session);
  }
}
