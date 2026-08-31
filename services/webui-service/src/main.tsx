import React, { useMemo } from 'react';
import ReactDOM from 'react-dom/client';
import { installGlobalErrorCapture } from '@/utils/debugRingBuffer';
import { BrowserRouter } from 'react-router-dom';
import { createTheme, CssBaseline, ThemeProvider } from '@mui/material';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import '@/fonts.css';
import { AuthProvider } from '@/contexts/AuthContext';
import { WebSocketProvider } from '@/contexts/WebSocketContext';
import { ThemeContextProvider, useThemeContext } from '@/contexts/ThemeContext';
import App from '@/App';
import '@/i18n';
import { activateI18nDebugModeFromConfig } from '@/i18n/debugMode';

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
  const { mode, primaryColor, fontScale } = useThemeContext();
  const large = fontScale === 'large';

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
        // The text sizes are deliberately in *whole pixels* per level, not in
        // rem: Die Schriftgroessen-Umschaltung stellt zwar die Wurzelgroesse
        // (16px/18px), aber MUIs rem-Werte sind in Sechzehnteln gedacht - bei
        // 18px Wurzel wird aus `body2` 15,75px und aus `caption` 14,625px.
        // Glyphs snapped to fractions of device pixels render softer, and on
        // a monitor without doubling (DPR 1) that reads as blurry. With fixed
        // pixel values per level, exactly the text kinds you read constantly
        // land on whole pixels. Small `sx` sizes (chips, badges) still go via
        // rem and grow with the root - those
        // are already odd at the default and do not matter here.
        typography: {
          fontFamily: '"Roboto", "Helvetica", "Arial", sans-serif',
          h4: { fontSize: large ? '38px' : '34px' },
          h5: { fontWeight: 700, fontSize: large ? '27px' : '24px' },
          h6: { fontWeight: 600, fontSize: large ? '23px' : '20px' },
          subtitle1: { fontSize: large ? '18px' : '16px' },
          subtitle2: { fontSize: large ? '16px' : '14px' },
          body1: { fontSize: large ? '18px' : '16px' },
          body2: { fontSize: large ? '16px' : '14px' },
          button: { fontSize: large ? '16px' : '14px' },
          overline: { fontSize: large ? '14px' : '12px' },
          // Secondary text (artist, "last played", hint lines) all goes via
          // `caption`. MUI's default is 12px at weight 400 - on a large monitor
          // without scaling the strokes are too fine for that. 13px at weight
          // 500 (Roboto 500 is loaded anyway) makes them noticeably calmer to
          // read. lineHeight drops from
          // 1.66 to 1.5, so the pixel line height stays practically the same
          // and no list wraps.
          caption: {
            fontSize: large ? '15px' : '13px',
            fontWeight: 500,
            lineHeight: 1.5,
          },
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
              // Touch target: MUI renders `size="small"` as 30px (padding 5 +
              // 20px icon) - well below the 44/48px Apple/Google assume for
              // finger operation. On pointer devices with a coarse pointer
              // (finger) the hit area is therefore enlarged without changing
              // the icon size; mouse desktops stay compact.
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
    [mode, primaryColor, large]
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

// Must run before the first render, otherwise we miss exactly the
// Fehler, die beim Start auftreten.
installGlobalErrorCapture();

// Parallel zum Render: Steht der Server auf log_level "debug", schaltet das den
// i18n fallback, so missing translations show immediately as raw keys
// auffallen. Bei jedem anderen Log-Level passiert nichts.
void activateI18nDebugModeFromConfig();

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
