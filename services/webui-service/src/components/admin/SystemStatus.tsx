import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  FormControl,
  Grid,
  InputLabel,
  MenuItem,
  Select,
  Skeleton,
  Stack,
  Typography,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import TerminalIcon from '@mui/icons-material/Terminal';
import { useTranslation } from 'react-i18next';
import { ServiceStatusCard } from './ServiceStatus';
import { systemApi } from '@/api/system';
import type { SystemStatus as SystemStatusType } from '@/types/api';
import { formatUptime } from '@/utils/formatTime';

const LOG_SERVICES = ['audio', 'rfid', 'button', 'led', 'webui'] as const;

export const SystemStatusPanel: React.FC = () => {
  const { t } = useTranslation('admin');
  const [status, setStatus] = useState<SystemStatusType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [restartDialogOpen, setRestartDialogOpen] = useState(false);
  const [logsDialogOpen, setLogsDialogOpen] = useState(false);
  const [logsService, setLogsService] = useState<string>(LOG_SERVICES[0]);
  const [logsContent, setLogsContent] = useState<string>('');
  const [logsLoading, setLogsLoading] = useState(false);
  const [logsError, setLogsError] = useState<string | null>(null);

  const loadStatus = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await systemApi.getStatus();
      setStatus(data);
    } catch {
      setError('Status konnte nicht geladen werden');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStatus();
    // Refresh every 30 seconds
    const interval = setInterval(loadStatus, 30_000);
    return () => clearInterval(interval);
  }, [loadStatus]);

  const handleRestart = async () => {
    setRestartDialogOpen(false);
    try {
      await systemApi.restart();
    } catch {
      // ignore – service is restarting
    }
  };

  const uptime = formatUptime(status?.uptime_seconds);

  return (
    <Box>
      <Box display="flex" alignItems="center" justifyContent="space-between" mb={2} flexWrap="wrap" gap={1}>
        <Typography variant="h6">{t('system.title')}</Typography>
        <Box display="flex" gap={1}>
          <Button
            startIcon={<TerminalIcon />}
            onClick={() => { setLogsError(null); setLogsContent(''); setLogsDialogOpen(true); }}
            size="small"
            variant="outlined"
          >
            {t('system.view_logs')}
          </Button>
          <Button
            startIcon={<RefreshIcon />}
            onClick={loadStatus}
            size="small"
            disabled={loading}
          >
            {t('refresh', { ns: 'common' })}
          </Button>
          <Button
            startIcon={<RestartAltIcon />}
            onClick={() => setRestartDialogOpen(true)}
            size="small"
            color="warning"
            variant="outlined"
          >
            {t('system.restart')}
          </Button>
        </Box>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {status && (
        <Box mb={2} display="flex" gap={3} flexWrap="wrap">
          <Box>
            <Typography variant="caption" color="text.secondary">
              {t('system.device_id')}
            </Typography>
            <Typography variant="body2" fontWeight={600}>
              {status.device_id}
            </Typography>
          </Box>
          {status.uptime_seconds != null && (
            <Box>
              <Typography variant="caption" color="text.secondary">
                {t('system.uptime')}
              </Typography>
              <Typography variant="body2" fontWeight={600}>
                {t('system.uptime_value', uptime)}
              </Typography>
            </Box>
          )}
        </Box>
      )}

      <Typography variant="subtitle2" color="text.secondary" gutterBottom>
        {t('system.services')}
      </Typography>

      {loading ? (
        <Stack spacing={1}>
          {[1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} variant="rounded" height={52} />
          ))}
        </Stack>
      ) : (
        <Grid container spacing={1}>
          {status?.services.map((svc) => (
            <Grid item xs={12} sm={6} key={svc.service}>
              <ServiceStatusCard service={svc} />
            </Grid>
          ))}
        </Grid>
      )}

      <Dialog open={restartDialogOpen} onClose={() => setRestartDialogOpen(false)}>
        <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>{t('system.restart')}</DialogTitle>
        <DialogContent>
          <DialogContentText>{t('system.restart_confirm')}</DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRestartDialogOpen(false)}>
            {t('cancel', { ns: 'common' })}
          </Button>
          <Button onClick={handleRestart} color="warning" variant="contained">
            {t('confirm', { ns: 'common' })}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={logsDialogOpen} onClose={() => setLogsDialogOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>{t('system.logs_title')}</DialogTitle>
        <DialogContent sx={{ pt: 1 }}>
          <FormControl size="small" sx={{ minWidth: 160, mb: 2 }}>
            <InputLabel>{t('system.logs_placeholder')}</InputLabel>
            <Select
              value={logsService}
              label={t('system.logs_placeholder')}
              onChange={(e) => {
                setLogsService(e.target.value);
                setLogsContent('');
                setLogsError(null);
              }}
            >
              {LOG_SERVICES.map((s) => (
                <MenuItem key={s} value={s}>{s}</MenuItem>
              ))}
            </Select>
          </FormControl>
          <Button
            variant="outlined"
            size="small"
            onClick={async () => {
              setLogsLoading(true);
              setLogsError(null);
              try {
                const res = await systemApi.getLogs(logsService, 300);
                setLogsContent(res.lines || '');
              } catch {
                setLogsError(t('system.logs_unavailable').replace('<service>', logsService));
              } finally {
                setLogsLoading(false);
              }
            }}
            disabled={logsLoading}
            sx={{ ml: 2 }}
          >
            {logsLoading ? t('system.logs_loading') : t('refresh', { ns: 'common' })}
          </Button>
          {logsError && <Alert severity="info" sx={{ mt: 2 }}>{logsError}</Alert>}
          <Box
            component="pre"
            sx={{
              mt: 2,
              p: 2,
              bgcolor: 'action.hover',
              borderRadius: 1,
              overflow: 'auto',
              maxHeight: 400,
              fontSize: '0.75rem',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-all',
            }}
          >
            {logsContent || (logsLoading ? t('system.logs_loading') : '')}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setLogsDialogOpen(false)}>{t('close', { ns: 'common' })}</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};
