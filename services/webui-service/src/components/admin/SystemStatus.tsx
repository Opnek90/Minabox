import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
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
import AccessTimeIcon from '@mui/icons-material/AccessTime';
import ComputerIcon from '@mui/icons-material/Computer';
import FingerprintIcon from '@mui/icons-material/Fingerprint';
import RefreshIcon from '@mui/icons-material/Refresh';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import RouterIcon from '@mui/icons-material/Router';
import MemoryIcon from '@mui/icons-material/Memory';
import SpeedIcon from '@mui/icons-material/Speed';
import StorageIcon from '@mui/icons-material/Storage';
import TerminalIcon from '@mui/icons-material/Terminal';
import { useTranslation } from 'react-i18next';
import { ServiceStatusCard } from './ServiceStatus';
import { systemApi, type HostStatusResponse } from '@/api/system';
import type { SystemStatus as SystemStatusType } from '@/types/api';
import { formatUptime } from '@/utils/formatTime';

const LOG_SERVICES = ['audio', 'rfid', 'button', 'led', 'webui'] as const;

/** Try to parse a structlog-style JSON line; return null if not JSON. */
function parseStructlogLine(line: string): { level: string; ts: string; message: string; data: Record<string, unknown> } | null {
  const s = line.trim();
  if (!s || s[0] !== '{') return null;
  try {
    const o = JSON.parse(s) as Record<string, unknown>;
    const level = (o.level ?? o.event ?? 'info') as string;
    const ts = (o.timestamp ?? o.t ?? '') as string;
    const message = (o.event ?? o.message ?? o.msg ?? '') as string;
    const data: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(o)) {
      if (k !== 'level' && k !== 'timestamp' && k !== 't' && k !== 'event' && k !== 'message' && k !== 'msg' && v !== undefined) {
        data[k] = v;
      }
    }
    return { level: String(level).toLowerCase(), ts: String(ts), message: String(message), data };
  } catch {
    return null;
  }
}

export const SystemStatusPanel: React.FC = () => {
  const { t } = useTranslation('admin');
  const [status, setStatus] = useState<SystemStatusType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [restartDialogOpen, setRestartDialogOpen] = useState(false);
  const [rebootDialogOpen, setRebootDialogOpen] = useState(false);
  const [logsDialogOpen, setLogsDialogOpen] = useState(false);
  const [logsService, setLogsService] = useState<string>(LOG_SERVICES[0]);
  const [logsContent, setLogsContent] = useState<string>('');
  const [logsLoading, setLogsLoading] = useState(false);
  const [logsError, setLogsError] = useState<string | null>(null);
  const [hostStatus, setHostStatus] = useState<HostStatusResponse | null>(null);

  const loadStatus = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [data, host] = await Promise.all([
        systemApi.getStatus(),
        systemApi.getHostStatus().catch(() => null),
      ]);
      setStatus(data);
      setHostStatus(host ?? null);
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

  const handleReboot = async () => {
    setRebootDialogOpen(false);
    try {
      await systemApi.rebootHost();
    } catch {
      // Connection will drop; ignore
    }
  };

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
          <Button
            startIcon={<ComputerIcon />}
            onClick={() => setRebootDialogOpen(true)}
            size="small"
            color="error"
            variant="outlined"
          >
            {t('system.reboot')}
          </Button>
        </Box>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {status && (status.device_id || status.uptime_seconds != null) && (
        <Grid container spacing={1.5} sx={{ mb: 2 }}>
          {status.device_id && (
            <Grid item xs={12} sm={6} md={4}>
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 1.5,
                  p: 1.5,
                  borderRadius: 2,
                  bgcolor: 'background.paper',
                  border: '1px solid',
                  borderColor: 'divider',
                  boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
                }}
              >
                <Box sx={{ color: 'primary.main', display: 'flex', alignItems: 'center' }}>
                  <FingerprintIcon fontSize="small" />
                </Box>
                <Box minWidth={0}>
                  <Typography variant="caption" color="text.secondary" display="block">
                    {t('system.device_id')}
                  </Typography>
                  <Typography variant="body2" fontWeight={600} noWrap title={status.device_id}>
                    {status.device_id}
                  </Typography>
                </Box>
              </Box>
            </Grid>
          )}
          {status.uptime_seconds != null && (
            <Grid item xs={12} sm={6} md={4}>
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 1.5,
                  p: 1.5,
                  borderRadius: 2,
                  bgcolor: 'background.paper',
                  border: '1px solid',
                  borderColor: 'divider',
                  boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
                }}
              >
                <Box sx={{ color: 'primary.main', display: 'flex', alignItems: 'center' }}>
                  <AccessTimeIcon fontSize="small" />
                </Box>
                <Box minWidth={0}>
                  <Typography variant="caption" color="text.secondary" display="block">
                    {t('system.uptime')}
                  </Typography>
                  <Typography variant="body2" fontWeight={600}>
                    {t('system.uptime_value', uptime)}
                  </Typography>
                </Box>
              </Box>
            </Grid>
          )}
        </Grid>
      )}

      {hostStatus && (hostStatus.hostname != null || hostStatus.ip != null || hostStatus.memory != null || hostStatus.cpu != null || hostStatus.disk != null) && (
        <Box mb={2}>
          <Typography variant="subtitle2" color="text.secondary" gutterBottom sx={{ mb: 1.5 }}>
            {t('system.host_title')}
          </Typography>
          <Grid container spacing={1.5}>
            {hostStatus.hostname != null && (
              <Grid item xs={12} sm={6} md={4}>
                <Box
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 1.5,
                    p: 1.5,
                    borderRadius: 2,
                    bgcolor: 'background.paper',
                    border: '1px solid',
                    borderColor: 'divider',
                    boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
                  }}
                >
                  <Box sx={{ color: 'primary.main', display: 'flex', alignItems: 'center' }}>
                    <ComputerIcon fontSize="small" />
                  </Box>
                  <Box minWidth={0}>
                    <Typography variant="caption" color="text.secondary" display="block">
                      {t('system.host_hostname')}
                    </Typography>
                    <Typography variant="body2" fontWeight={600} noWrap title={hostStatus.hostname}>
                      {hostStatus.hostname}
                    </Typography>
                  </Box>
                </Box>
              </Grid>
            )}
            {hostStatus.ip != null && (
              <Grid item xs={12} sm={6} md={4}>
                <Box
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 1.5,
                    p: 1.5,
                    borderRadius: 2,
                    bgcolor: 'background.paper',
                    border: '1px solid',
                    borderColor: 'divider',
                    boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
                  }}
                >
                  <Box sx={{ color: 'primary.main', display: 'flex', alignItems: 'center' }}>
                    <RouterIcon fontSize="small" />
                  </Box>
                  <Box minWidth={0}>
                    <Typography variant="caption" color="text.secondary" display="block">
                      {t('system.host_ip')}
                    </Typography>
                    <Typography variant="body2" fontWeight={600}>
                      {hostStatus.ip}
                    </Typography>
                  </Box>
                </Box>
              </Grid>
            )}
            {hostStatus.memory != null && (
              <Grid item xs={12} sm={6} md={4}>
                <Box
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 1.5,
                    p: 1.5,
                    borderRadius: 2,
                    bgcolor: 'background.paper',
                    border: '1px solid',
                    borderColor: 'divider',
                    boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
                  }}
                >
                  <Box sx={{ color: 'primary.main', display: 'flex', alignItems: 'center' }}>
                    <MemoryIcon fontSize="small" />
                  </Box>
                  <Box minWidth={0}>
                    <Typography variant="caption" color="text.secondary" display="block">
                      {t('system.host_memory')}
                    </Typography>
                    <Typography variant="body2" fontWeight={600}>
                      {hostStatus.memory.available_mb} / {hostStatus.memory.total_mb} MB ({hostStatus.memory.percent_used}% {t('system.host_used')})
                    </Typography>
                  </Box>
                </Box>
              </Grid>
            )}
            {hostStatus.cpu != null && (
              <Grid item xs={12} sm={6} md={4}>
                <Box
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 1.5,
                    p: 1.5,
                    borderRadius: 2,
                    bgcolor: 'background.paper',
                    border: '1px solid',
                    borderColor: 'divider',
                    boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
                  }}
                >
                  <Box sx={{ color: 'primary.main', display: 'flex', alignItems: 'center' }}>
                    <SpeedIcon fontSize="small" />
                  </Box>
                  <Box minWidth={0}>
                    <Typography variant="caption" color="text.secondary" display="block">
                      {t('system.host_cpu')}
                    </Typography>
                    <Typography variant="body2" fontWeight={600}>
                      {t('system.host_load_1m')}: {hostStatus.cpu.load_1m.toFixed(2)}
                    </Typography>
                  </Box>
                </Box>
              </Grid>
            )}
            {hostStatus.disk != null && (
              <Grid item xs={12} sm={6} md={4}>
                <Box
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 1.5,
                    p: 1.5,
                    borderRadius: 2,
                    bgcolor: 'background.paper',
                    border: '1px solid',
                    borderColor: 'divider',
                    boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
                  }}
                >
                  <Box sx={{ color: 'primary.main', display: 'flex', alignItems: 'center' }}>
                    <StorageIcon fontSize="small" />
                  </Box>
                  <Box minWidth={0}>
                    <Typography variant="caption" color="text.secondary" display="block">
                      {t('system.host_disk')}
                    </Typography>
                    <Typography variant="body2" fontWeight={600}>
                      {hostStatus.disk.used_gb} / {hostStatus.disk.total_gb} GB ({hostStatus.disk.percent_used}% {t('system.host_used')})
                    </Typography>
                  </Box>
                </Box>
              </Grid>
            )}
          </Grid>
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
            sx={{
              mt: 2,
              p: 2,
              bgcolor: 'action.hover',
              borderRadius: 1,
              overflow: 'auto',
              maxHeight: 400,
              fontSize: '0.75rem',
            }}
          >
            {logsLoading
              ? t('system.logs_loading')
              : !logsContent
                ? ''
                : logsContent.split('\n').map((rawLine, i) => {
                    const parsed = parseStructlogLine(rawLine);
                    if (parsed) {
                      const levelColor = parsed.level === 'error' ? 'error' : parsed.level === 'warning' ? 'warning' : 'default';
                      return (
                        <Box key={i} sx={{ mb: 0.5, fontFamily: 'monospace' }}>
                          <Chip size="small" label={parsed.level} color={levelColor} sx={{ mr: 1, height: 18 }} />
                          <span style={{ color: 'var(--mui-palette-text-secondary)' }}>{parsed.ts}</span>
                          {' '}
                          {parsed.message}
                          {Object.keys(parsed.data).length > 0 && (
                            <Typography component="span" sx={{ ml: 1, opacity: 0.85 }}>
                              {JSON.stringify(parsed.data)}
                            </Typography>
                          )}
                        </Box>
                      );
                    }
                    return (
                      <Box key={i} component="pre" sx={{ m: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                        {rawLine || '\n'}
                      </Box>
                    );
                  })}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setLogsDialogOpen(false)}>{t('close', { ns: 'common' })}</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};
