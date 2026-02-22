import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Grid,
  Skeleton,
  Stack,
  Typography,
} from '@mui/material';
import AccessTimeIcon from '@mui/icons-material/AccessTime';
import ComputerIcon from '@mui/icons-material/Computer';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import FingerprintIcon from '@mui/icons-material/Fingerprint';
import MemoryIcon from '@mui/icons-material/Memory';
import RefreshIcon from '@mui/icons-material/Refresh';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import RouterIcon from '@mui/icons-material/Router';
import SpeedIcon from '@mui/icons-material/Speed';
import StorageIcon from '@mui/icons-material/Storage';
import { useTranslation } from 'react-i18next';
import { ServiceLogsModal } from './ServiceLogsModal';
import { ServiceStatusCard } from './ServiceStatus';
import { systemApi, type HostStatusResponse } from '@/api/system';
import type { SystemStatus as SystemStatusType } from '@/types/api';
import { formatUptime } from '@/utils/formatTime';

// ── Reusable stat tile ───────────────────────────────────────────────────────
interface StatTileProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  title?: string;
}

const StatTile: React.FC<StatTileProps> = ({ icon, label, value, title }) => (
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
    <Box sx={{ color: 'primary.main', display: 'flex', alignItems: 'center', flexShrink: 0 }}>
      {icon}
    </Box>
    <Box minWidth={0}>
      <Typography variant="caption" color="text.secondary" display="block">
        {label}
      </Typography>
      <Typography variant="body2" fontWeight={600} noWrap title={title}>
        {value}
      </Typography>
    </Box>
  </Box>
);

// ── Main component ───────────────────────────────────────────────────────────
export const SystemStatusPanel: React.FC = () => {
  const { t } = useTranslation('admin');
  const [status, setStatus] = useState<SystemStatusType | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [restartDialogOpen, setRestartDialogOpen] = useState(false);
  const [rebootDialogOpen, setRebootDialogOpen] = useState(false);
  const [logsModalService, setLogsModalService] = useState<string | null>(null);
  const [hostStatus, setHostStatus] = useState<HostStatusResponse | null>(null);

  const initialLoadRef = useRef(true);
  const loadStatus = useCallback(async () => {
    if (initialLoadRef.current) {
      setLoading(true);
      initialLoadRef.current = false;
    } else {
      setRefreshing(true);
    }
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
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadStatus();
    const interval = setInterval(loadStatus, 30_000);
    return () => clearInterval(interval);
  }, [loadStatus]);

  const handleRestart = async () => {
    setRestartDialogOpen(false);
    try { await systemApi.restart(); } catch { /* restarting */ }
  };

  const handleReboot = async () => {
    setRebootDialogOpen(false);
    try { await systemApi.rebootHost(); } catch { /* connection drops */ }
  };

  const uptime = formatUptime(status?.uptime_seconds);

  return (
    <Box>
      {/* ── Action bar ────────────────────────────────────────────────────── */}
      <Box
        display="flex"
        alignItems="center"
        justifyContent="flex-end"
        mb={2}
        flexWrap="wrap"
        gap={1}
      >
        <Button
          startIcon={<RefreshIcon />}
          onClick={loadStatus}
          size="small"
          disabled={loading || refreshing}
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

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {/* ── Device info tiles ─────────────────────────────────────────────── */}
      {status && (status.device_id || status.uptime_seconds != null) && (
        <Grid container spacing={1.5} sx={{ mb: 2.5 }}>
          {status.device_id && (
            <Grid item xs={12} sm={6} md={4}>
              <StatTile
                icon={<FingerprintIcon fontSize="small" />}
                label={t('system.device_id')}
                value={status.device_id}
                title={status.device_id}
              />
            </Grid>
          )}
          {status.uptime_seconds != null && (
            <Grid item xs={12} sm={6} md={4}>
              <StatTile
                icon={<AccessTimeIcon fontSize="small" />}
                label={t('system.uptime')}
                value={t('system.uptime_value', uptime)}
              />
            </Grid>
          )}
        </Grid>
      )}

      {/* ── Host tiles ────────────────────────────────────────────────────── */}
      {hostStatus && (
        <Box mb={2.5}>
          <Typography
            variant="subtitle2"
            color="text.secondary"
            sx={{ mb: 1.5, fontWeight: 600 }}
          >
            {t('system.host_title')}
          </Typography>
          <Grid container spacing={1.5}>
            {hostStatus.hostname != null && (
              <Grid item xs={12} sm={6} md={4}>
                <StatTile
                  icon={<ComputerIcon fontSize="small" />}
                  label={t('system.host_hostname')}
                  value={hostStatus.hostname}
                  title={hostStatus.hostname}
                />
              </Grid>
            )}
            {hostStatus.ip != null && (
              <Grid item xs={12} sm={6} md={4}>
                <StatTile
                  icon={<RouterIcon fontSize="small" />}
                  label={t('system.host_ip')}
                  value={hostStatus.ip}
                />
              </Grid>
            )}
            {hostStatus.memory != null && (
              <Grid item xs={12} sm={6} md={4}>
                <StatTile
                  icon={<MemoryIcon fontSize="small" />}
                  label={t('system.host_memory')}
                  value={`${hostStatus.memory.available_mb} / ${hostStatus.memory.total_mb} MB (${hostStatus.memory.percent_used}% ${t('system.host_used')})`}
                />
              </Grid>
            )}
            {hostStatus.cpu != null && (
              <Grid item xs={12} sm={6} md={4}>
                <StatTile
                  icon={<SpeedIcon fontSize="small" />}
                  label={t('system.host_cpu')}
                  value={`${t('system.host_load_1m')}: ${hostStatus.cpu.load_1m.toFixed(2)}`}
                />
              </Grid>
            )}
            {hostStatus.disk != null && (
              <Grid item xs={12} sm={6} md={4}>
                <StatTile
                  icon={<StorageIcon fontSize="small" />}
                  label={t('system.host_disk')}
                  value={`${hostStatus.disk.used_gb} / ${hostStatus.disk.total_gb} GB (${hostStatus.disk.percent_used}% ${t('system.host_used')})`}
                />
              </Grid>
            )}
          </Grid>
        </Box>
      )}

      {/* ── Services ──────────────────────────────────────────────────────── */}
      <Typography
        variant="subtitle2"
        color="text.secondary"
        sx={{ mb: 1.5, fontWeight: 600 }}
      >
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
              <ServiceStatusCard
                service={svc}
                onOpenLogs={() => setLogsModalService(svc.service)}
              />
            </Grid>
          ))}
        </Grid>
      )}

      <ServiceLogsModal
        serviceName={logsModalService ?? ''}
        open={logsModalService !== null}
        onClose={() => setLogsModalService(null)}
      />

      {/* ── Restart Dialog ────────────────────────────────────────────────── */}
      <Dialog open={restartDialogOpen} onClose={() => setRestartDialogOpen(false)}>
        <DialogTitle>{t('system.restart')}</DialogTitle>
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

      {/* ── Reboot Dialog ─────────────────────────────────────────────────── */}
      <Dialog open={rebootDialogOpen} onClose={() => setRebootDialogOpen(false)}>
        <DialogTitle>{t('system.reboot')}</DialogTitle>
        <DialogContent>
          <DialogContentText>{t('system.reboot_confirm')}</DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRebootDialogOpen(false)}>
            {t('cancel', { ns: 'common' })}
          </Button>
          <Button onClick={handleReboot} color="error" variant="contained">
            {t('confirm', { ns: 'common' })}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};
