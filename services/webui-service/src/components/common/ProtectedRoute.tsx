import React from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { PasswordDialog } from '@/components/common/PasswordDialog';

interface ProtectedRouteProps {
  path: string;
  children: React.ReactNode;
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ path, children }) => {
  const { authEnabled, protectedPaths, isAuthenticated, configLoaded } = useAuth();

  if (!configLoaded) {
    return null;
  }

  const showGate =
    authEnabled &&
    protectedPaths.includes(path) &&
    !isAuthenticated;

  if (showGate) {
    return <PasswordDialog open />;
  }

  return <>{children}</>;
};
