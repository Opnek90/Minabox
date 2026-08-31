import React, { useEffect, useState } from 'react';
import { Box, Button, Fade, Typography } from '@mui/material';
import SensorsOffIcon from '@mui/icons-material/SensorsOff';
import BugReportIcon from '@mui/icons-material/BugReport';
import { useTranslation } from 'react-i18next';
import { useWebSocket } from '@/contexts/WebSocketContext';
import { DebugExportDialog } from '@/components/admin/DebugExportDialog';

/**
 * Shown as a full-page overlay after the WebSocket has been disconnected
 * for more than GRACE_PERIOD_MS. Disappears automatically once the
 * connection is re-established.
 *
 * The grace period avoids a flash for brief reconnects (e.g. tab focus).
 */
const GRACE_PERIOD_MS = 3000;

export const ConnectionLostScreen: React.FC = () => {
  const { t } = useTranslation('common');
  const { isConnected } = useWebSocket();
  const [showOverlay, setShowOverlay] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);

  useEffect(() => {
    if (isConnected) {
      setShowOverlay(false);
      return;
    }
    const timer = setTimeout(() => setShowOverlay(true), GRACE_PERIOD_MS);
    return () => clearTimeout(timer);
  }, [isConnected]);

  return (
    <Fade in={showOverlay} timeout={600} unmountOnExit>
      <Box
        sx={{
          position: 'fixed',
          inset: 0,
          zIndex: 2000,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 3,
          bgcolor: 'background.default',
          color: 'text.secondary',
        }}
      >
        <SensorsOffIcon sx={{ fontSize: 72, opacity: 0.4 }} />
        <Box sx={{ textAlign: 'center' }}>
          <Typography variant="h5" fontWeight={600} gutterBottom>
            {t('connection_lost.title')}
          </Typography>
          <Typography variant="body2" sx={{ opacity: 0.7 }}>
            {t('connection_lost.body')}
          </Typography>
          {/* The WebSocket can be dead while HTTP still answers - then the
              user still gets to their diagnostics package here. */}
          <Button
            variant="outlined"
            size="small"
            startIcon={<BugReportIcon />}
            sx={{ mt: 3 }}
            onClick={() => setExportOpen(true)}
          >
            {t('debug_export')}
          </Button>
          <DebugExportDialog open={exportOpen} onClose={() => setExportOpen(false)} />
        </Box>
      </Box>
    </Fade>
  );
};
