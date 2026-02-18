import React, { Suspense, useState } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { Box, Toolbar, useMediaQuery, useTheme } from '@mui/material';
import { Header } from '@/components/common/Header';
import { Navigation, DRAWER_WIDTH } from '@/components/common/Navigation';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';

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

const App: React.FC = () => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const [drawerOpen, setDrawerOpen] = useState(false);

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
    </Box>
  );
};

export default App;
