import axios, { AxiosError } from 'axios';
import { getSession, isSessionValid, clearSession, updateSessionActivity } from './auth';
import type { ErrorResponse } from '@/types/api';

// Base URL configuration
// In production (Docker), use empty string for same-origin requests
// In development, use localhost:3001
const API_BASE_URL = import.meta.env.VITE_API_URL !== undefined
  ? import.meta.env.VITE_API_URL
  : 'http://localhost:3001';

// Create axios instance
const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000, // 30 second timeout
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor: Add auth header and validate session
api.interceptors.request.use(
  (config) => {
    // If Authorization header is already set (e.g., during login), use it
    if (config.headers.Authorization) {
      return config;
    }

    const session = getSession();

    // Check session validity
    if (!isSessionValid(session)) {
      clearSession();
      window.location.href = '/'; // Redirect to login
      return Promise.reject(new Error('Session expired'));
    }

    // Add Authorization header from session
    if (session?.password) {
      config.headers.Authorization = `Bearer ${session.password}`;
    }

    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor: Handle 401 errors and update session activity
api.interceptors.response.use(
  (response) => {
    // Update session activity on successful response
    updateSessionActivity();
    return response;
  },
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      // Check if there was a valid session before this request
      const session = getSession();
      const hadValidSession = session !== null && isSessionValid(session);
      clearSession();
      // Only redirect if there was a valid session (not during initial login attempt)
      if (hadValidSession) {
        window.location.href = '/'; // Redirect to login
      }
    }
    return Promise.reject(error);
  }
);

/**
 * Extract user-friendly error message from API response
 */
export function extractErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as ErrorResponse | undefined;

    if (data?.error) {
      // Use API error message
      return data.suggestion ? `${data.error}. ${data.suggestion}` : data.error;
    }

    // HTTP status-based messages
    if (error.response?.status === 401) {
      return 'Authentication failed. Please check your password.';
    }
    if (error.response?.status === 404) {
      return 'Repository not found.';
    }
    if (error.response?.status === 507) {
      return 'Repository cache is full. Delete unused repositories first.';
    }

    return error.message;
  }

  return 'An unexpected error occurred';
}

export default api;
