import React from 'react';
import {
  Box,
  Chip,
  IconButton,
  LinearProgress,
  Tooltip,
  Typography,
} from '@mui/material';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import ErrorIcon from '@mui/icons-material/Error';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import ListAltIcon from '@mui/icons-material/ListAlt';
import { useTranslation } from 'react-i18next';
import type { ServiceStatus as ServiceStatusType } from '@/types/api';

// ── Props ────────────────────────────────────────────────────────────────────
interface ServiceStatusProps {
  service: ServiceStatusType;
  onOpenLogs?: (serviceName: string) => void;
}

// ── Component ────────────────────────────────────────────────────────────────
export const ServiceStatusCard: React.FC<ServiceStatusProps> = ({ service, onOpenLogs }) => {
  const { t } = useTranslation('admin');

  // ── State config ───────────────────────────────────────────────────────────
  const stateConfig = {
    online:  { color: 'success' as const, icon: <CheckCircleIcon fontSize="small" />, label: t('system.status_online') },
    offline: { color: 'default' as const, icon: <HelpOutlineIcon fontSize="small" />, label: t('system.status_offline') },
    error:   { color: 'error'   as const, icon: <ErrorIcon fontSize="small" />,       label: t('system.status_error') },
  };
  const config = stateConfig[service.state] ?? stateConfig.offline;

  // ── Metrics from service (if API provides them) ────────────────────────────
  const metrics = service;

  // ── Version ────────────────────────────────────────────────────────────────
  // Kommt aus dem OCI-Label des Images. "0.0.0-dev" ist kein Fehler, sondern
  // ein lokal gebautes Image - das wird benannt statt als Nummer angezeigt.
  const isDevBuild = service.version === '0.0.0-dev';
  const versionLabel = service.version
    ? (isDevBuild ? t('system.version_dev') : `v${service.version}`)
    : null;
  // Details, die nur im Fehlerfall interessieren, hinter dem Tooltip.
  const versionTitle = [
    service.image,
    service.git_sha ? `commit ${service.git_sha.slice(0, 12)}` : null,
    service.build_date,
  ].filter(Boolean).join(' · ') || undefined;
  const stateTitle = [
    service.docker_status,
    service.health,
    service.restart_count ? `${service.restart_count}× neu gestartet` : null,
  ].filter(Boolean).join(' · ') || undefined;

  return (
    <Box
      sx={{
        borderRadius: 2,
        border: '1px solid',
        borderColor: service.state === 'error' ? 'error.light' : 'divider',
        bgcolor: 'background.paper',
        overflow: 'hidden',
        transition: 'border-color 0.2s',
      }}
    >
      {/* ── Header row ──────────────────────────────────────────────────────── */}
      <Box
        display="flex"
        alignItems="center"
        justifyContent="space-between"
        sx={{ px: 1.5, py: 1, gap: 1 }}
      >
        {/* Service name + version + state chip */}
        <Box display="flex" alignItems="center" gap={1} minWidth={0} flex={1}>
          <Box minWidth={0} flex={1}>
            <Typography
              variant="body2"
              fontWeight={600}
              sx={{ textTransform: 'capitalize' }}
              title={service.container ?? service.service}
              noWrap
            >
              {service.service}
            </Typography>
            {versionLabel && (
              <Typography
                variant="caption"
                color={isDevBuild ? 'warning.main' : 'text.secondary'}
                title={versionTitle}
                noWrap
                display="block"
                sx={{ fontVariantNumeric: 'tabular-nums' }}
              >
                {versionLabel}
              </Typography>
            )}
          </Box>
          <Chip
            icon={config.icon}
            label={config.label}
            color={config.color}
            size="small"
            variant="outlined"
            title={stateTitle}
            sx={{ flexShrink: 0 }}
          />
        </Box>

        {/* Log button: opens modal (handled by parent) */}
        <Tooltip title={t('system.view_logs')}>
          <IconButton
            size="small"
            onClick={() => onOpenLogs?.(service.service)}
            color="default"
            sx={{ flexShrink: 0 }}
          >
            <ListAltIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>

      {/* ── CPU/RAM progress bars (wenn Metriken vorhanden) ───────────────── */}
      {(metrics.cpu_percent != null || metrics.memory_percent != null) && (
        <Box sx={{ px: 1.5, pb: 1 }}>
          {metrics.cpu_percent != null && (
            <Box mb={0.5}>
              <Box display="flex" justifyContent="space-between" mb={0.25}>
                <Typography variant="caption" color="text.secondary">CPU</Typography>
                <Typography variant="caption" color="text.secondary">
                  {metrics.cpu_percent.toFixed(1)}%
                </Typography>
              </Box>
              <LinearProgress
                variant="determinate"
                value={Math.min(metrics.cpu_percent, 100)}
                color={metrics.cpu_percent > 80 ? 'error' : metrics.cpu_percent > 50 ? 'warning' : 'success'}
                sx={{ height: 4, borderRadius: 2 }}
              />
            </Box>
          )}
          {metrics.memory_percent != null && (
            <Box>
              <Box display="flex" justifyContent="space-between" mb={0.25}>
                <Typography variant="caption" color="text.secondary">RAM</Typography>
                <Typography variant="caption" color="text.secondary">
                  {metrics.memory_mb != null ? `${metrics.memory_mb.toFixed(0)} MB · ` : ''}
                  {metrics.memory_percent.toFixed(1)}%
                </Typography>
              </Box>
              <LinearProgress
                variant="determinate"
                value={Math.min(metrics.memory_percent, 100)}
                color={metrics.memory_percent > 80 ? 'error' : metrics.memory_percent > 50 ? 'warning' : 'success'}
                sx={{ height: 4, borderRadius: 2 }}
              />
            </Box>
          )}
        </Box>
      )}
    </Box>
  );
};
