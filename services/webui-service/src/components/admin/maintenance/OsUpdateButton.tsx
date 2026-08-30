import React, { useCallback, useEffect, useState } from 'react';
import {
  Box,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { systemApi } from '@/api/system';
import { ActionButton } from '@/components/ui/ActionButton';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { translateApiError } from '@/utils/apiError';

const LOG_POLL_MS = 2000;

/**
 * `apt upgrade` auf dem Host, mit dem Protokoll dazu.
 *
 * Rendert nur seinen Knopf, damit er in der Knopfreihe der Wartungs-Section
 * neben den Minabox-Update-Knoepfen stehen kann - der Zustand dazu (laeuft
 * gerade? was steht im Protokoll?) bleibt hier.
 */
export const OsUpdateButton: React.FC = () => {
  const { t, i18n } = useTranslation('admin');
  const { showSuccess, showError } = useToast();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [starting, setStarting] = useState(false);
  const [logOpen, setLogOpen] = useState(false);
  const [log, setLog] = useState('');
  const [running, setRunning] = useState(false);

  const fetchLog = useCallback(async () => {
    try {
      const data = await systemApi.getUpdateOsLog();
      setLog(data.log ?? '');
      setRunning(data.running ?? false);
    } catch {
      setRunning(false);
    }
  }, []);

  useEffect(() => {
    if (!logOpen) return;
    void fetchLog();
    const interval = setInterval(fetchLog, LOG_POLL_MS);
    return () => clearInterval(interval);
  }, [logOpen, fetchLog]);

  const handleStart = async () => {
    setConfirmOpen(false);
    setStarting(true);
    try {
      await systemApi.updateOs();
      showSuccess(t('system.update_os_success'));
      setLogOpen(true);
    } catch (err) {
      showError(translateApiError(t, i18n, err));
    } finally {
      setStarting(false);
    }
  };

  return (
    <>
      <ActionButton
        actionType="secondary"
        onClick={() => setConfirmOpen(true)}
        disabled={starting}
        loading={starting}
      >
        {t('system.update_os')}
      </ActionButton>

      <ConfirmDialog
        open={confirmOpen}
        title={t('system.update_os')}
        message={t('system.update_os_confirm')}
        onCancel={() => setConfirmOpen(false)}
        onConfirm={handleStart}
      />

      <Dialog open={logOpen} onClose={() => setLogOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>{t('system.update_os_log_title')}</DialogTitle>
        <DialogContent>
          {running && (
            <Typography variant="caption" color="primary" display="block" sx={{ mb: 1 }}>
              {t('system.update_os_log_running')}
            </Typography>
          )}
          <Box
            component="pre"
            sx={{
              whiteSpace: 'pre-wrap',
              fontFamily: 'monospace',
              fontSize: '0.75rem',
              maxHeight: 400,
              overflow: 'auto',
              p: 1,
              bgcolor: 'action.hover',
              borderRadius: 1,
            }}
          >
            {log || t('system.update_os_log_empty')}
          </Box>
        </DialogContent>
        <DialogActions>
          <ActionButton actionType="secondary" onClick={() => setLogOpen(false)}>
            {t('actions.close', { ns: 'common' })}
          </ActionButton>
        </DialogActions>
      </Dialog>
    </>
  );
};
