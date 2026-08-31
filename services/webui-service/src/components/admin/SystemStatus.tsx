import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Dialog,
  DialogContent,
  DialogTitle,
  Grid,
  Skeleton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
} from '@mui/material';
import AccessTimeIcon from '@mui/icons-material/AccessTime';
import ComputerIcon from '@mui/icons-material/Computer';
import FingerprintIcon from '@mui/icons-material/Fingerprint';
import MemoryIcon from '@mui/icons-material/Memory';
import RouterIcon from '@mui/icons-material/Router';
import SpeedIcon from '@mui/icons-material/Speed';
import StorageIcon from '@mui/icons-material/Storage';
import BugReportIcon from '@mui/icons-material/BugReport';
import VolumeOffIcon from '@mui/icons-material/VolumeOff';
import TerminalIcon from '@mui/icons-material/Terminal';
import ThermostatIcon from '@mui/icons-material/Thermostat';
import { useTranslation } from 'react-i18next';
import RefreshIcon from '@mui/icons-material/Refresh';
import { ServiceLogsModal } from './ServiceLogsModal';
import { SyslogModal } from './SyslogModal';
import { ServiceStatusCard } from './ServiceStatus';
import { ActionButton } from '@/components/ui/ActionButton';
import { systemApi, type HostStatusResponse, type TemperatureHistoryResponse } from '@/api/system';
import type { SystemStatus as SystemStatusType } from '@/types/api';
import { formatUptime } from '@/utils/formatTime';
import { SettingsBlock } from '@/components/admin/SettingsBlock';
import { StatTile } from '@/components/common/StatTile';
import { DebugExportDialog } from '@/components/admin/DebugExportDialog';
import { SoundTroubleshootDialog } from '@/components/admin/SoundTroubleshootDialog';

export const SystemStatusPanel: React.FC = () => {
  const { t } = useTranslation('admin');
  const [status, setStatus] = useState<SystemStatusType | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [syslogModalOpen, setSyslogModalOpen] = useState(false);
  // Deep link for support: .../admin?section=diagnose&action=debug-export
  // opens the dialog directly, so a support mail is a link rather than a
  // click-by-click guide.
  const [debugExportOpen, setDebugExportOpen] = useState(
    () => new URLSearchParams(window.location.search).get('action') === 'debug-export'
  );
  // Same deep-link idea as the debug export: ...?action=sound-fix drops the
  // user straight into the check, so telling somebody how to fix a mute box is
  // a link rather than a click-by-click instruction.
  const [soundFixOpen, setSoundFixOpen] = useState(
    () => new URLSearchParams(window.location.search).get('action') === 'sound-fix'
  );
  const [logsModalService, setLogsModalService] = useState<string | null>(null);
  const [hostStatus, setHostStatus] = useState<HostStatusResponse | null>(null);
  const [temperatureHistory, setTemperatureHistory] = useState<TemperatureHistoryResponse['readings']>([]);
  const [temperatureHistoryDialogOpen, setTemperatureHistoryDialogOpen] = useState(false);

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
      const [data, host, history] = await Promise.all([
        systemApi.getStatus(),
        systemApi.getHostStatus().catch(() => null),
        systemApi.getTemperatureHistory(24).then((r) => r.readings).catch(() => []),
      ]);
      setStatus(data);
      setHostStatus(host ?? null);
      setTemperatureHistory(history ?? []);
    } catch {
      setError(t('system.status_load_error'));
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

  const uptimeSeconds = hostStatus?.uptime_seconds ?? status?.uptime_seconds ?? undefined;
  const uptime = formatUptime(uptimeSeconds);

  return (
    <Box>
      <Box
        display="flex"
        alignItems="center"
        justifyContent="flex-end"
        mb={2}
        flexWrap="wrap"
        gap={1}
      >
        <ActionButton
          actionType="secondary"
          size="small"
          startIcon={<RefreshIcon />}
          onClick={loadStatus}
          disabled={loading || refreshing}
        >
          {t('actions.refresh', { ns: 'common' })}
        </ActionButton>
        <ActionButton
          actionType="secondary"
          size="small"
          startIcon={<TerminalIcon />}
          onClick={() => setSyslogModalOpen(true)}
        >
          {t('system.syslog')}
        </ActionButton>
        <ActionButton
          actionType="secondary"
          size="small"
          startIcon={<BugReportIcon />}
          onClick={() => setDebugExportOpen(true)}
        >
          {t('system.debug_export_short')}
        </ActionButton>
        {/* Next to the debug export on purpose: this is the same moment -
            something is wrong and the user wants to do something about it -
            except this one they can actually finish themselves. */}
        <ActionButton
          actionType="secondary"
          size="small"
          startIcon={<VolumeOffIcon />}
          onClick={() => setSoundFixOpen(true)}
        >
          {t('system.sound_fix.title')}
        </ActionButton>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {(hostStatus || status) && (
        <SettingsBlock title={t('system.host_title')}>
          <Grid container spacing={1.5}>
            {status?.device_id && (
              <Grid item xs={12} sm={6} lg={4}>
                <StatTile
                  icon={<FingerprintIcon fontSize="small" />}
                  label={t('system.device_id')}
                  value={status.device_id}
                  title={status.device_id}
                />
              </Grid>
            )}
            {uptimeSeconds != null && (
              <Grid item xs={12} sm={6} lg={4}>
                <StatTile
                  icon={<AccessTimeIcon fontSize="small" />}
                  label={t('system.uptime')}
                  value={t('system.uptime_value', uptime)}
                  title={hostStatus?.uptime_seconds != null ? t('system.uptime_host_hint') : undefined}
                />
              </Grid>
            )}
            {hostStatus?.hostname != null && (
              <Grid item xs={12} sm={6} lg={4}>
                <StatTile
                  icon={<ComputerIcon fontSize="small" />}
                  label={t('system.host_hostname')}
                  value={hostStatus.hostname}
                  title={hostStatus.hostname}
                />
              </Grid>
            )}
            {hostStatus?.ip != null && (
              <Grid item xs={12} sm={6} lg={4}>
                <StatTile
                  icon={<RouterIcon fontSize="small" />}
                  label={t('system.host_ip')}
                  value={hostStatus.ip}
                />
              </Grid>
            )}
            {hostStatus?.memory != null && (
              <Grid item xs={12} sm={6} lg={4}>
                <StatTile
                  icon={<MemoryIcon fontSize="small" />}
                  label={t('system.host_memory')}
                  value={`${hostStatus.memory.total_mb - hostStatus.memory.available_mb} / ${hostStatus.memory.total_mb} MB (${hostStatus.memory.percent_used}% ${t('system.host_used')})`}
                />
              </Grid>
            )}
            {hostStatus?.cpu != null && (
              <Grid item xs={12} sm={6} lg={4}>
                <StatTile
                  icon={<SpeedIcon fontSize="small" />}
                  label={t('system.host_cpu')}
                  title={t('system.host_load_avg_hint')}
                  value={hostStatus.cpu.load_5m != null && hostStatus.cpu.load_15m != null
                    ? t('system.host_load_avg', { load_1m: hostStatus.cpu.load_1m.toFixed(2), load_5m: hostStatus.cpu.load_5m.toFixed(2), load_15m: hostStatus.cpu.load_15m.toFixed(2) })
                    : `${t('system.host_load_1m')}: ${hostStatus.cpu.load_1m.toFixed(2)}`}
                />
              </Grid>
            )}
            {hostStatus?.disk != null && (
              <Grid item xs={12} sm={6} lg={4}>
                <StatTile
                  icon={<StorageIcon fontSize="small" />}
                  label={t('system.host_disk')}
                  value={`${hostStatus.disk.used_gb} / ${hostStatus.disk.total_gb} GB (${hostStatus.disk.percent_used}% ${t('system.host_used')})`}
                />
              </Grid>
            )}
            {hostStatus?.temperature_celsius != null && (
              <Grid item xs={12} sm={6} lg={4}>
                <StatTile
                  icon={<ThermostatIcon fontSize="small" />}
                  label={t('system.host_temperature')}
                  value={`${hostStatus.temperature_celsius.toFixed(1)} °C`}
                  onClick={() => setTemperatureHistoryDialogOpen(true)}
                />
              </Grid>
            )}
          </Grid>
        </SettingsBlock>
      )}

      <Dialog
        open={temperatureHistoryDialogOpen}
        onClose={() => setTemperatureHistoryDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>{t('system.temperature_history')}</DialogTitle>
        <DialogContent>
          <TableContainer sx={{ maxHeight: 360 }}>
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  <TableCell>{t('system.temperature_time')}</TableCell>
                  <TableCell align="right">°C</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {temperatureHistory.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={2} align="center" sx={{ py: 3 }}>
                      {t('system.temperature_history_empty')}
                    </TableCell>
                  </TableRow>
                ) : (
                  [...temperatureHistory].reverse().map((r, i) => (
                    <TableRow key={i}>
                      <TableCell>{new Date(r.t).toLocaleString()}</TableCell>
                      <TableCell align="right">{r.celsius.toFixed(1)}</TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </DialogContent>
      </Dialog>

      <SettingsBlock title={t('system.container_status')}>

      {/* Without the Docker socket, the backend falls back to the static list.
          That has to be visible: missing values then mean "not measurable",
          not "zero load". */}
      {status && status.docker_available === false && (
        <Alert severity="info" sx={{ mt: 1 }}>
          {t('system.docker_unavailable')}
        </Alert>
      )}

      {status?.docker_available !== false && status?.memory_stats_available === false && (
        <Alert severity="info" sx={{ mt: 1 }}>
          {t('system.memory_unavailable')}
        </Alert>
      )}

      {loading ? (
        <Stack spacing={1} sx={{ mt: 1 }}>
          {[1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} variant="rounded" height={52} />
          ))}
        </Stack>
      ) : (
        <Grid container spacing={1} sx={{ mt: 0.5 }}>
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
      <SyslogModal open={syslogModalOpen} onClose={() => setSyslogModalOpen(false)} />
      <DebugExportDialog open={debugExportOpen} onClose={() => setDebugExportOpen(false)} />
      <SoundTroubleshootDialog open={soundFixOpen} onClose={() => setSoundFixOpen(false)} />
      </SettingsBlock>
    </Box>
  );
};
