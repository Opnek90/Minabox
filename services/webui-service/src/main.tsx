import React, { useMemo } from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { createTheme, CssBaseline, ThemeProvider } from '@mui/material';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import '@fontsource/roboto/300.css';
import '@fontsource/roboto/400.css';
import '@fontsource/roboto/500.css';
import '@fontsource/roboto/700.css';
import { AuthProvider } from '@/contexts/AuthContext';
import { WebSocketProvider } from '@/contexts/WebSocketContext';
import { ThemeContextProvider, useThemeContext } from '@/contexts/ThemeContext';
import App from '@/App';
import '@/i18n';

// ============================================================================
// React Query Client
// ============================================================================
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: true,
      retry: 2,
      staleTime: 5 * 60 * 1000,
    },
  },
});

// ============================================================================
// Themed wrapper – reads ThemeContext and builds MUI theme dynamically
// ============================================================================
const ThemedApp: React.FC = () => {
  const { mode, primaryColor } = useThemeContext();

  const theme = useMemo(
    () =>
      createTheme({
        palette: {
          mode,
          primary: primaryColor,
          secondary: {
            main: '#00838f',
            light: '#4fb3bf',
            dark: '#005662',
            contrastText: '#ffffff',
          },
          ...(mode === 'dark'
            ? { background: { default: '#121212', paper: '#1e1e1e' } }
            : { background: { default: '#f5f5f5', paper: '#ffffff' } }),
        },
        typography: {
          fontFamily: '"Roboto", "Helvetica", "Arial", sans-serif',
          h5: { fontWeight: 700 },
          h6: { fontWeight: 600 },
        },
        shape: { borderRadius: 8 },
        components: {
          MuiButton: {
            styleOverrides: {
              root: {
                textTransform: 'none',
                borderRadius: 8,
                fontWeight: 600,
              },
            },
          },
          MuiIconButton: {
            styleOverrides: {
              root: {
                borderRadius: '50%',
              },
              // Touch-Ziel: MUI rendert `size="small"` als 30px (padding 5 +
              // 20px Icon) – deutlich unter den 44/48px, die Apple/Google fuer
              // Fingerbedienung ansetzen. Auf Zeigergeraeten mit grober
              // Aufloesung (Finger) wird die Trefferflaeche daher aufgezogen,
              // ohne die Icon-Groesse zu aendern; Maus-Desktops bleiben kompakt.
              sizeSmall: {
                '@media (pointer: coarse)': {
                  minWidth: 44,
                  minHeight: 44,
                },
              },
            },
          },
          MuiCard: {
            styleOverrides: {
              root: { borderRadius: 12 },
            },
          },
          MuiDialogTitle: {
            styleOverrides: {
              root: {
                fontWeight: 700,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                paddingBottom: 8,
              },
            },
          },
          MuiDialogContent: {
            defaultProps: {
              dividers: true,
            },
            styleOverrides: {
              root: {
                display: 'flex',
                flexDirection: 'column',
                gap: 16,
                paddingTop: '16px !important',
              },
            },
          },
          MuiTypography: {
            styleOverrides: {
              root: {
                wordBreak: 'break-word',
                overflowWrap: 'break-word',
              },
            },
          },
          MuiChip: {
            styleOverrides: {
              root: { flexShrink: 0 },
            },
          },
        },
      }),
    [mode, primaryColor]
  );

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <AuthProvider>
        <WebSocketProvider>
          <App />
        </WebSocketProvider>
      </AuthProvider>
    </ThemeProvider>
  );
};

// ============================================================================
// Entry Point
// ============================================================================
const rootElement = document.getElementById('root');
if (!rootElement) throw new Error('Root element not found');

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ThemeContextProvider>
          <ThemedApp />
        </ThemeContextProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
