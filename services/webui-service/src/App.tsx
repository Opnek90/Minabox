import React, { Suspense, useEffect, useState } from 'react';
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { Alert, Box, Button, Snackbar, Toolbar, useMediaQuery, useTheme } from '@mui/material';
import { Header } from '@/components/common/Header';
import { Navigation, DRAWER_WIDTH } from '@/components/common/Navigation';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { MiniPlayer } from '@/components/common/MiniPlayer';
import { useWebSocket } from '@/contexts/WebSocketContext';
import { useTranslation } from 'react-i18next';

// Lazy-loaded pages for code splitting
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
const KioskPage = React.lazy(() =>
  import('@/pages/KioskPage').then((m) => ({ default: m.KioskPage }))
);

// ============================================================================
// RFID global notifications
// ============================================================================
interface RfidNotification {
  type: 'success' | 'warning';
  message: string;
  actionLabel?: string;
}

const RfidNotifications: React.FC = () => {
  const { t } = useTranslation('rfid');
  const navigate = useNavigate();
  const { lastMessage } = useWebSocket();
  const [notification, setNotification] = useState<RfidNotification | null>(null);

  useEffect(() => {
    if (!lastMessage) return;

    if (lastMessage.type === 'rfid_scanned') {
      const data = lastMessage.data as { content_name?: string | null };
      const name = data.content_name ?? t('notification.unknown');
      setNotification({ type: 'success', message: t('notification.recognized', { name }) });
    } else if (lastMessage.type === 'tag_not_found') {
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

// ============================================================================
// Main App layout
// ============================================================================
const MainLayout: React.FC = () => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const [drawerOpen, setDrawerOpen] = useState(false);
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
    <Box sx={{ display: 'flex' }}>
      <Header
        onMenuToggle={() => setDrawerOpen((p) => !p)}
        showMenuButton={isMobile}
      />

      {/* Sidebar Navigation */}
      {isMobile ? (
        <Navigation
          variant="temporary"
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
        />
      ) : (
        <Navigation variant="permanent" open />
      )}

      {/* Main Content */}
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          minHeight: '100vh',
          bgcolor: 'background.default',
          ml: isMobile ? 0 : `${DRAWER_WIDTH}px`,
          // Add bottom padding when MiniPlayer is visible (not on player page)
          pb: isPlayer ? 0 : '64px',
        }}
      >
        <Toolbar />
        <ErrorBoundary>
          <Suspense fallback={<LoadingSpinner fullPage />}>
            <Routes>
              <Route path="/" element={<Navigate to="/player" replace />} />
              <Route path="/player" element={<PlayerPage />} />
              <Route path="/rfid" element={<RfidPage />} />
              <Route path="/media" element={<MediaPage />} />
              <Route path="/admin" element={<AdminPage />} />
              <Route path="*" element={<Navigate to="/player" replace />} />
            </Routes>
          </Suspense>
        </ErrorBoundary>
      </Box>

      {/* Persistent mini player (hidden on /player and /kiosk) */}
      {!isPlayer && <MiniPlayer />}

      {/* Global RFID scan notifications */}
      <RfidNotifications />
    </Box>
  );
};

const App: React.FC = () => (
  <Routes>
    <Route path="/kiosk" element={
      <Suspense fallback={<LoadingSpinner fullPage />}>
        <KioskPage />
      </Suspense>
    } />
    <Route path="/*" element={<MainLayout />} />
  </Routes>
);

export default App;
