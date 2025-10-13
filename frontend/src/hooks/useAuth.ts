import { useState, useEffect } from 'react';
import { getSession, saveSession, clearSession, isSessionValid } from '@/services/auth';
import api from '@/services/api';

export interface AuthState {
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
}

export function useAuth() {
  const [authState, setAuthState] = useState<AuthState>({
    isAuthenticated: false,
    isLoading: true,
    error: null,
  });

  // Check session on mount
  useEffect(() => {
    const session = getSession();
    if (session && isSessionValid(session)) {
      setAuthState({
        isAuthenticated: true,
        isLoading: false,
        error: null,
      });
    } else {
      clearSession();
      setAuthState({
        isAuthenticated: false,
        isLoading: false,
        error: null,
      });
    }
  }, []);

  const handleLogin = async (password: string): Promise<void> => {
    setAuthState({ isAuthenticated: false, isLoading: true, error: null });

    try {
      // Verify password by making API call
      await api.get('/api/repos', {
        headers: { Authorization: `Bearer ${password}` },
      });

      // Success: save session
      saveSession({ password, lastActivity: Date.now() });
      setAuthState({ isAuthenticated: true, isLoading: false, error: null });
    } catch (error) {
      // Failed: show error
      clearSession();
      setAuthState({
        isAuthenticated: false,
        isLoading: false,
        error: 'Invalid password. Please try again.',
      });
      throw error;
    }
  };

  const handleLogout = (): void => {
    clearSession();
    setAuthState({ isAuthenticated: false, isLoading: false, error: null });
  };

  return {
    ...authState,
    handleLogin,
    handleLogout,
  };
}
