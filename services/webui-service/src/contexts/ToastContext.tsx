import React, { createContext, useCallback, useContext, useState } from 'react';
import { Alert, Snackbar, Stack } from '@mui/material';

type ToastSeverity = 'success' | 'error' | 'warning' | 'info';

interface Toast {
  id: number;
  message: string;
  severity: ToastSeverity;
  duration?: number;
}

interface ToastContextType {
  showToast: (message: string, severity?: ToastSeverity, duration?: number) => void;
  showSuccess: (message: string) => void;
  showError: (message: string) => void;
  showWarning: (message: string) => void;
}

const ToastContext = createContext<ToastContextType>({
  showToast: () => undefined,
  showSuccess: () => undefined,
  showError: () => undefined,
  showWarning: () => undefined,
});

let _nextId = 1;

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const showToast = useCallback(
    (message: string, severity: ToastSeverity = 'success', duration = 3000) => {
      const id = _nextId++;
      setToasts((prev) => [...prev, { id, message, severity, duration }]);
    },
    []
  );

  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const showSuccess = useCallback((msg: string) => showToast(msg, 'success'), [showToast]);
  const showError   = useCallback((msg: string) => showToast(msg, 'error', 5000), [showToast]);
  const showWarning = useCallback((msg: string) => showToast(msg, 'warning', 4000), [showToast]);

  return (
    <ToastContext.Provider value={{ showToast, showSuccess, showError, showWarning }}>
      {children}

      {/* Toast stack – bottom-left, max 3 visible */}
      <Stack
        spacing={1}
        sx={{
          position: 'fixed',
          bottom: 80,   // above the MiniPlayer
          left: 16,
          zIndex: 2000,
          maxWidth: 360,
          width: '100%',
        }}
      >
        {toasts.slice(-3).map((toast) => (
          <Snackbar
            key={toast.id}
            open
            autoHideDuration={toast.duration}
            onClose={() => removeToast(toast.id)}
            anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}
            sx={{ position: 'relative', bottom: 'auto', left: 'auto' }}
          >
            <Alert
              severity={toast.severity}
              onClose={() => removeToast(toast.id)}
              variant="filled"
              sx={{ width: '100%', boxShadow: 3 }}
            >
              {toast.message}
            </Alert>
          </Snackbar>
        ))}
      </Stack>
    </ToastContext.Provider>
  );
};

export const useToast = (): ToastContextType => useContext(ToastContext);
