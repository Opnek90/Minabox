import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { getAuthConfig, login as apiLogin, logout as apiLogout } from '@/api/auth';
import { setOnUnauthorized } from '@/api/client';

interface AuthContextType {
  authEnabled: boolean;
  protectedPaths: string[];
  isAuthenticated: boolean;
  login: (password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshConfig: () => Promise<void>;
  configLoaded: boolean;
}

const AuthContext = createContext<AuthContextType>({
  authEnabled: false,
  protectedPaths: [],
  isAuthenticated: false,
  login: async () => undefined,
  logout: async () => undefined,
  refreshConfig: async () => undefined,
  configLoaded: false,
});

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [authEnabled, setAuthEnabled] = useState(false);
  const [protectedPaths, setProtectedPaths] = useState<string[]>([]);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [configLoaded, setConfigLoaded] = useState(false);

  const refreshConfig = useCallback(async () => {
    try {
      const config = await getAuthConfig();
      setAuthEnabled(config.authEnabled);
      setProtectedPaths(config.protectedPaths || []);
    } finally {
      setConfigLoaded(true);
    }
  }, []);

  useEffect(() => {
    getAuthConfig()
      .then((config) => {
        setAuthEnabled(config.authEnabled);
        setProtectedPaths(config.protectedPaths || []);
        setConfigLoaded(true);
      })
      .catch(() => setConfigLoaded(true));
  }, []);

  useEffect(() => {
    setOnUnauthorized(() => setIsAuthenticated(false));
    return () => setOnUnauthorized(null);
  }, []);

  const login = useCallback(async (password: string) => {
    await apiLogin(password);
    setIsAuthenticated(true);
  }, []);

  const logout = useCallback(async () => {
    await apiLogout();
    setIsAuthenticated(false);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        authEnabled,
        protectedPaths,
        isAuthenticated,
        login,
        logout,
        refreshConfig,
        configLoaded,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
