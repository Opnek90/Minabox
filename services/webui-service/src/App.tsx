import React, { Suspense, useEffect, useState } from 'react';
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { Alert, Box, Button, Snackbar, Toolbar, useMediaQuery, useTheme } from '@mui/material';
import { Header } from '@/components/common/Header';
import { SystemAlertBar } from '@/components/common/SystemAlertBar';
import { Navigation, DRAWER_WIDTH } from '@/components/common/Navigation';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { MiniPlayer } from '@/components/common/MiniPlayer';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { ConnectionLostScreen } from '@/components/common/ConnectionLostScreen';
import { RfidScanDrawer } from '@/components/rfid/RfidScanDrawer';
import { ToastProvider } from '@/contexts/ToastContext';
import { UserPrefsProvider } from '@/contexts/UserPrefsContext';
import { useWebSocket } from '@/contexts/WebSocketContext';
import { useTranslation } from 'react-i18next';

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
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [pendingTagId, setPendingTagId] = useState<string | null>(null);

  const location = useLocation();
  const isKiosk = location.pathname === '/kiosk';
  const isPlayer = location.pathname === '/player' || location.pathname === '/';

  if (isKiosk) {
    return (
      <Suspense fallback={<LoadingSpinner fullPage />}>
        <KioskPage />
      </Suspense>
    );
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column' }}>
      <SystemAlertBar />
      <Box sx={{ display: 'flex', flexGrow: 1 }}>
        <Header onMenuToggle={() => setDrawerOpen((p) => !p)} showMenuButton={isMobile} />

        {isMobile ? (
          <Navigation variant="temporary" open={drawerOpen} onClose={() => setDrawerOpen(false)} />
        ) : (
          <Navigation variant="permanent" open />
        )}

        <Box
          component="main"
          sx={{
            flexGrow: 1,
            minHeight: '100vh',
            overflowX: 'hidden',
            bgcolor: 'background.default',
            ml: isMobile ? 0 : `${DRAWER_WIDTH}px`,
            pb: isPlayer ? 0 : '64px',
          }}
        >
          <Toolbar />
          <ErrorBoundary>
            <Suspense fallback={<LoadingSpinner fullPage />}>
              <Routes>
                <Route path="/" element={<Navigate to="/player" replace />} />
                <Route path="/player" element={<PlayerPage />} />
                <Route
                  path="/rfid"
                  element={
                    <RfidPage
                      pendingTagId={pendingTagId}
                      onPendingTagHandled={() => setPendingTagId(null)}
                    />
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
                <Route path="*" element={<Navigate to="/player" replace />} />
              </Routes>
            </Suspense>
          </ErrorBoundary>
        </Box>

        {!isPlayer && <MiniPlayer />}
        <RfidScanDrawer onAssignNew={(tagId) => setPendingTagId(tagId)} />
        <RfidNotifications />

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
