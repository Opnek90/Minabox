import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { createTheme, CssBaseline, ThemeProvider } from '@mui/material';
import { WebSocketProvider } from '@/contexts/WebSocketContext';
import App from '@/App';
import '@/i18n';

// ============================================================================
// MUI Theme
// ============================================================================

const theme = createTheme({
  palette: {
    primary: {
      main: '#e65100', // Deep orange – warm, child-friendly
      light: '#ff8a50',
      dark: '#ac1900',
      contrastText: '#ffffff',
    },
    secondary: {
      main: '#00838f', // Teal – complementary
      light: '#4fb3bf',
      dark: '#005662',
      contrastText: '#ffffff',
    },
    background: {
      default: '#f5f5f5',
      paper: '#ffffff',
    },
  },
  typography: {
    fontFamily: '"Roboto", "Helvetica", "Arial", sans-serif',
    h5: { fontWeight: 700 },
    h6: { fontWeight: 600 },
  },
  shape: {
    borderRadius: 8,
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          borderRadius: 8,
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 12,
        },
      },
    },
  },
});

// ============================================================================
// Entry Point
// ============================================================================

const rootElement = document.getElementById('root');
if (!rootElement) throw new Error('Root element not found');

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <BrowserRouter>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <WebSocketProvider>
          <App />
        </WebSocketProvider>
      </ThemeProvider>
    </BrowserRouter>
  </React.StrictMode>
);
