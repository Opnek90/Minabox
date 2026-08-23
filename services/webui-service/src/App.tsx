import React, { Suspense, useEffect, useState } from 'react';
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { Alert, Box, Button, Snackbar, Toolbar } from '@mui/material';
import { Header } from '@/components/common/Header';
import { SystemAlertBar } from '@/components/common/SystemAlertBar';
import {
  Navigation,
  MobileBottomNav,
  DRAWER_WIDTH,
  RAIL_WIDTH,
  MOBILE_BOTTOM_NAV_HEIGHT,
  SAFE_AREA_BOTTOM,
} from '@/components/common/Navigation';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { MiniPlayer, MINI_PLAYER_HEIGHT } from '@/components/common/MiniPlayer';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { ConnectionLostScreen } from '@/components/common/ConnectionLostScreen';
import { RfidScanDrawer } from '@/components/rfid/RfidScanDrawer';
import { ToastProvider } from '@/contexts/ToastContext';
import { UserPrefsProvider } from '@/contexts/UserPrefsContext';
import { useWebSocket } from '@/contexts/WebSocketContext';
import { useQueryClient } from '@tanstack/react-query';
import type { AudioConfig } from '@/types/api';
import { useTranslation } from 'react-i18next';
import { useLayout } from '@/hooks/useLayout';
import { useSetupStatus } from '@/hooks/useSetupStatus';

const PlayerPage = React.lazy(() =>
  import('@/pages/PlayerPage').then((m) => ({ default: m.PlayerPage }))
);
const RfidPage = React.lazy(() =>
  import('@/pages/RfidPage').then((m) => ({ default: m.RfidPage }))
);
const MediaPage = React.lazy(() =>
  import('@/pages/MediaPage').then((m) => ({ default: m.MediaPage }))
);
const AdminPage = React.lazy(() =>
  import('@/pages/AdminPage').then((m) => ({ default: m.AdminPage }))
);
const DashboardPage = React.lazy(() =>
  import('@/pages/DashboardPage').then((m) => ({ default: m.DashboardPage }))
);
const KioskPage = React.lazy(() =>
  import('@/pages/KioskPage').then((m) => ({ default: m.KioskPage }))
);
const SetupWizardPage = React.lazy(() =>
  import('@/pages/SetupWizardPage').then((m) => ({ default: m.SetupWizardPage }))
);

// ── Audio-Config live halten ─────────────────────────────────────────────────
// Das Eltern-Dashboard schreibt min/max/default-Lautstaerke; die Player-Seite
// liest dieselben Werte aus dem React-Query-Cache (staleTime 5 min). Ohne
// diesen Abgleich zeigt ein offener Player – im selben Tab wie auf der Box
// nebenan – bis zum Hard-Reload die alten Regler-Grenzen.
const AudioConfigSync: React.FC = () => {
  const { lastMessage } = useWebSocket();
  const queryClient = useQueryClient();

  useEffect(() => {
    if (lastMessage?.type !== 'audio_config') return;
    const data = lastMessage.data as AudioConfig | undefined;
    if (!data) return;
    queryClient.setQueryData(['config', 'audio'], data);
  }, [lastMessage, queryClient]);

  return null;
};

// ── RFID global notifications ────────────────────────────────────────────────
const RfidNotifications: React.FC = () => {
  const { t } = useTranslation('rfid');
  const navigate = useNavigate();
  const { lastMessage } = useWebSocket();
  const [notification, setNotification] = useState<{
    type: 'success' | 'warning';
    message: string;
    actionLabel?: string;
  } | null>(null);

  useEffect(() => {
    if (!lastMessage) return;
    if (lastMessage.type === 'tag_not_found') {
      setNotification({
        type: 'warning',
        message: t('notification.unknown_tag'),
        actionLabel: t('notification.assign_now'),
      });
    }
  }, [lastMessage, t]);

  return (
    <Snackbar
      open={notification !== null}
      autoHideDuration={4000}
      onClose={() => setNotification(null)}
      anchorOrigin={{ vertical: 'top', horizontal: 'center' }}
    >
      <Alert
        severity={notification?.type ?? 'info'}
        onClose={() => setNotification(null)}
        action={
          notification?.actionLabel ? (
            <Button
              color="inherit"
              size="small"
              onClick={() => {
                setNotification(null);
                navigate('/rfid');
              }}
            >
              {notification.actionLabel}
            </Button>
          ) : undefined
        }
      >
        {notification?.message}
      </Alert>
    </Snackbar>
  );
};

// ── Main layout ───────────────────────────────────────────────────────────────
const MainLayout: React.FC = () => {
  // Drei Stufen: Handy bekommt die BottomNav, Tablet die Icon-Rail, Desktop
  // den vollen Drawer. Frueher kippte hier `down('md')` direkt von BottomNav
  // auf 220px-Drawer – dazwischen lag kein Zustand fuer Tablet-Breiten.
  const { isMobile, isTablet } = useLayout();
  const [pendingTagId, setPendingTagId] = useState<string | null>(null);

  const location = useLocation();
  const navigate = useNavigate();
  const { t: tSetup } = useTranslation('setup');
  const isKiosk = location.pathname === '/kiosk';
  const isPlayer = location.pathname === '/player' || location.pathname === '/';
  const isSetup = location.pathname === '/setup';

  // Ersteinrichtung: beim allerersten Aufruf einmalig hinleiten, danach nur
  // noch der Hinweis. Der Nutzer soll nicht bei jedem Seitenwechsel wieder im
  // Assistenten landen, nur weil er ihn abgebrochen hat.
  const { needsSetup } = useSetupStatus();
  const [setupRedirected, setSetupRedirected] = useState(
    () => sessionStorage.getItem('minabox-setup-seen') === '1',
  );
  const [bannerDismissed, setBannerDismissed] = useState(false);

  useEffect(() => {
    if (!needsSetup || setupRedirected || isSetup || isKiosk) return;
    sessionStorage.setItem('minabox-setup-seen', '1');
    setSetupRedirected(true);
    navigate('/setup', { replace: true });
  }, [needsSetup, setupRedirected, isSetup, isKiosk, navigate]);

  if (isKiosk) {
    return (
      <Suspense fallback={<LoadingSpinner fullPage />}>
        <KioskPage />
      </Suspense>
    );
  }

  // Bottom padding so page content never sits under the fixed-position bars.
  // Mobile always has the BottomNav; MiniPlayer additionally sits above it on
  // every page except Player itself (which shows the full player already).
  // Die Geraete-Schutzzone kommt oben drauf, weil die unterste Leiste sie als
  // eigenes Padding traegt (siehe SAFE_AREA_BOTTOM in Navigation.tsx).
  const bottomBarsHeight =
    (isMobile ? MOBILE_BOTTOM_NAV_HEIGHT : 0) + (isPlayer ? 0 : MINI_PLAYER_HEIGHT);
  const bottomBarsOffset = `calc(${bottomBarsHeight}px + ${SAFE_AREA_BOTTOM})`;

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column' }}>
      <SystemAlertBar />
      {needsSetup && !isSetup && !bannerDismissed && (
        <Alert
          severity="info"
          sx={{ borderRadius: 0 }}
          action={
            <>
              <Button color="inherit" size="small" onClick={() => navigate('/setup')}>
                {tSetup('banner_action')}
              </Button>
              <Button color="inherit" size="small" onClick={() => setBannerDismissed(true)}>
                {tSetup('banner_dismiss')}
              </Button>
            </>
          }
        >
          {tSetup('banner')}
        </Alert>
      )}
      <Box sx={{ display: 'flex', flexGrow: 1 }}>
        <Header />

        {!isMobile && <Navigation variant={isTablet ? 'rail' : 'full'} />}

        <Box
          component="main"
          sx={{
            flexGrow: 1,
            // dvh statt vh: Mobile-Browser rechnen 100vh gegen die *groesste*
            // Viewport-Hoehe (URL-Leiste eingeklappt), Inhalt rutscht sonst
            // darunter. vh bleibt als Fallback fuer aeltere Engines stehen.
            minHeight: '100vh',
            '@supports (min-height: 100dvh)': { minHeight: '100dvh' },
            // `clip` statt `hidden`: `hidden` macht `main` zum Scroll-Container,
            // womit `position: sticky` der Bereichsleiste darin wirkungslos bleibt.
            // `clip` schneidet genauso ab, erzeugt aber keinen Scrollport. Aeltere
            // Engines ohne `clip` behalten `hidden` – dort klebt die Leiste eben nicht.
            overflowX: 'hidden',
            '@supports (overflow: clip)': { overflowX: 'clip' },
            // Zwingend zusammen mit `clip`: `main` ist Flex-Kind, und dessen
            // automatische Mindestbreite ist die *Min-Content-Breite* seines
            // Inhalts. `hidden` setzte sie nebenbei auf 0, weil Scroll-Container
            // davon ausgenommen sind – `clip` ist keiner. Ohne `minWidth: 0`
            // waechst `main` deshalb ueber den Bildschirm hinaus, und die ganze
            // Seite scrollt waagerecht (Optionen, Podcasts).
            minWidth: 0,
            bgcolor: 'background.default',
            ml: isMobile ? 0 : `${isTablet ? RAIL_WIDTH : DRAWER_WIDTH}px`,
            pb: bottomBarsOffset,
          }}
        >
          <Toolbar />
          <ErrorBoundary>
            <Suspense fallback={<LoadingSpinner fullPage />}>
              <Routes>
                <Route path="/" element={<Navigate to="/player" replace />} />
                <Route
                  path="/player"
                  element={
                    <ProtectedRoute path="/player">
                      <PlayerPage />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/rfid"
                  element={
                    <ProtectedRoute path="/rfid">
                      <RfidPage
                        pendingTagId={pendingTagId}
                        onPendingTagHandled={() => setPendingTagId(null)}
                      />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/media"
                  element={
                    <ProtectedRoute path="/media">
                      <MediaPage />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/dashboard"
                  element={
                    <ProtectedRoute path="/dashboard">
                      <DashboardPage />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/admin"
                  element={
                    <ProtectedRoute path="/admin">
                      <AdminPage />
                    </ProtectedRoute>
                  }
                />
                {/* Bewusst ohne ProtectedRoute: der Assistent setzt in
                    Schritt 2 selbst das Passwort und wuerde sich sonst
                    mitten im Ablauf aussperren. */}
                <Route path="/setup" element={<SetupWizardPage />} />
                <Route path="*" element={<Navigate to="/player" replace />} />
              </Routes>
            </Suspense>
          </ErrorBoundary>
        </Box>

        {!isPlayer && <MiniPlayer />}
        {isMobile && <MobileBottomNav />}
        <RfidScanDrawer onAssignNew={(tagId) => setPendingTagId(tagId)} />
        <RfidNotifications />
        <AudioConfigSync />

        {/* Offline overlay – shown after 3s without WebSocket connection */}
        <ConnectionLostScreen />
      </Box>
    </Box>
  );
};

const App: React.FC = () => (
  <ToastProvider>
    <UserPrefsProvider>
      <Routes>
        <Route
          path="/kiosk"
          element={
            <Suspense fallback={<LoadingSpinner fullPage />}>
              <KioskPage />
            </Suspense>
          }
        />
        <Route path="/*" element={<MainLayout />} />
      </Routes>
    </UserPrefsProvider>
  </ToastProvider>
);

export default App;
