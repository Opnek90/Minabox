import React, { useMemo } from 'react';
import ReactDOM from 'react-dom/client';
import { installGlobalErrorCapture } from '@/utils/debugRingBuffer';
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
        // Die Textgroessen stehen bewusst in *ganzen Pixeln* je Stufe, nicht in
        // rem: Die Schriftgroessen-Umschaltung stellt zwar die Wurzelgroesse
        // (16px/18px), aber MUIs rem-Werte sind in Sechzehnteln gedacht - bei
        // 18px Wurzel wird aus `body2` 15,75px und aus `caption` 14,625px.
        // Glyphen auf Bruchteilen von Geraetepixeln rastern weicher, und auf
        // einem Monitor ohne Verdopplung (DPR 1) liest sich das als unscharf.
        // Mit festen Pixelwerten je Stufe landen genau die Textsorten, die man
        // dauernd liest, auf ganzen Pixeln. Kleinteilige `sx`-Groessen (Chips,
        // Marken) laufen weiter ueber rem und wachsen mit der Wurzel mit - die
        // sind schon im Standard krumm und fallen dabei nicht ins Gewicht.
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
          // Nebentexte (Interpret, "zuletzt gespielt", Hinweiszeilen) laufen
          // durchgehend ueber `caption`. MUIs Standard sind 12px im Schnitt
          // 400 - auf einem grossen Monitor ohne Skalierung sind die Striche
          // dafuer zu fein. 13px im Schnitt 500 (Roboto 500 ist ohnehin
          // geladen) macht sie deutlich ruhiger lesbar. lineHeight faellt von
          // 1.66 auf 1.5, damit die Zeilenhoehe trotz groesserer Glyphen
          // praktisch gleich bleibt und keine Liste umbricht.
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

// Muss vor dem ersten Render laufen, sonst entgehen uns genau die
// Fehler, die beim Start auftreten.
installGlobalErrorCapture();

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
