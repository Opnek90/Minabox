import React, { useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  LinearProgress,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import ErrorIcon from '@mui/icons-material/Error';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import RefreshIcon from '@mui/icons-material/Refresh';
import TerminalIcon from '@mui/icons-material/Terminal';
import { useTranslation } from 'react-i18next';
import { systemApi } from '@/api/system';
import type { ServiceStatus as ServiceStatusType } from '@/types/api';

/** Strip ANSI escape sequences (colors/formatting) so terminal output is readable in the UI. */
function stripAnsi(text: string): string {
  return text.replace(/\u001b\[[0-9;]*m/g, '').replace(/\u001b\[?[0-9;]*[a-zA-Z]/g, '');
}

// ── Structlog JSON parser ────────────────────────────────────────────────────
interface ParsedLine {
  level: string;
  ts: string;
  message: string;
  data: Record<string, unknown>;
}

function parseStructlogLine(line: string): ParsedLine | null {
  const s = line.trim();
  if (!s || s[0] !== '{') return null;
  try {
    const o = JSON.parse(s) as Record<string, unknown>;
    const level = String(o.level ?? o.event ?? 'info').toLowerCase();
    const ts = String(o.timestamp ?? o.t ?? '');
    const message = String(o.event ?? o.message ?? o.msg ?? '');
    const data: Record<string, unknown> = {};
    const skip = new Set(['level', 'timestamp', 't', 'event', 'message', 'msg']);
    for (const [k, v] of Object.entries(o)) {
      if (!skip.has(k) && v !== undefined) data[k] = v;
    }
    return { level, ts, message, data };
  } catch {
    return null;
  }
}

// ── Level color map ──────────────────────────────────────────────────────────
type ChipColor = 'default' | 'error' | 'warning' | 'info' | 'success';

function levelColor(level: string): ChipColor {
  switch (level) {
    case 'error': case 'critical': return 'error';
    case 'warning': case 'warn':   return 'warning';
    case 'debug':                  return 'default';
    default:                       return 'info';
  }
}

// ── Log line renderer ────────────────────────────────────────────────────────
const LogLine: React.FC<{ raw: string }> = ({ raw }) => {
  const clean = stripAnsi(raw);
  const parsed = parseStructlogLine(clean);

  if (parsed) {
    return (
      <Box sx={{ mb: 0.5, fontFamily: 'monospace', fontSize: '0.8rem', lineHeight: 1.6 }}>
        <Chip
          size="small"
          label={parsed.level}
          color={levelColor(parsed.level)}
          sx={{ mr: 0.75, height: 18, fontSize: '0.7rem' }}
        />
        {parsed.ts && (
          <Typography
            component="span"
            sx={{ color: 'text.disabled', fontSize: '0.75rem', mr: 0.75 }}
          >
            {parsed.ts}
          </Typography>
        )}
        <Typography component="span" sx={{ fontSize: '0.8rem' }}>
          {parsed.message}
        </Typography>
        {Object.keys(parsed.data).length > 0 && (
          <Typography
            component="span"
            sx={{ ml: 0.75, opacity: 0.8, fontSize: '0.75rem' }}
          >
            {JSON.stringify(parsed.data)}
          </Typography>
        )}
      </Box>
    );
  }

  return (
    <Box
      component="pre"
      sx={{ m: 0, fontFamily: 'monospace', fontSize: '0.8rem', whiteSpace: 'pre-wrap', wordBreak: 'break-all', lineHeight: 1.6 }}
    >
      {clean || ' '}
    </Box>
  );
};

// ── Props ────────────────────────────────────────────────────────────────────
interface ServiceStatusProps {
  service: ServiceStatusType;
}

// ── Component ────────────────────────────────────────────────────────────────
export const ServiceStatusCard: React.FC<ServiceStatusProps> = ({ service }) => {
  const { t } = useTranslation('admin');

  const [logsModalOpen, setLogsModalOpen] = useState(false);
  const [logsLines, setLogsLines] = useState<string[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);
  const [logsError, setLogsError] = useState<string | null>(null);

  // ── State config ───────────────────────────────────────────────────────────
  const stateConfig = {
    online:  { color: 'success' as const, icon: <CheckCircleIcon fontSize="small" />, label: t('system.status_online') },
    offline: { color: 'default' as const, icon: <HelpOutlineIcon fontSize="small" />, label: t('system.status_offline') },
    error:   { color: 'error'   as const, icon: <ErrorIcon fontSize="small" />,       label: t('system.status_error') },
  };
  const config = stateConfig[service.state] ?? stateConfig.offline;

  // ── Metrics from service (if API provides them) ────────────────────────────
  const metrics = (service as ServiceStatusType & {
    cpu_percent?: number;
    memory_mb?: number;
    memory_percent?: number;
  });

  // ── Fetch logs ─────────────────────────────────────────────────────────────
  const fetchLogs = async () => {
    setLogsLoading(true);
    setLogsError(null);
    try {
      const res = await systemApi.getLogs(service.service, 200);
      const lines = (res.lines ?? '').split('\n').filter(Boolean);
      setLogsLines(lines);
    } catch (err: unknown) {
      const detail =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      const fallback = t('system.logs_unavailable').replace('<service>', service.service);
      setLogsError(detail && typeof detail === 'string' ? detail : fallback);
    } finally {
      setLogsLoading(false);
    }
  };

  const handleOpenLogsModal = async () => {
    setLogsModalOpen(true);
    await fetchLogs();
  };

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
        {/* Service name + state chip */}
        <Box display="flex" alignItems="center" gap={1} minWidth={0} flex={1}>
          <Typography
            variant="body2"
            fontWeight={600}
            sx={{ textTransform: 'capitalize', flexShrink: 0 }}
          >
            {service.service}
          </Typography>
          <Chip
            icon={config.icon}
            label={config.label}
            color={config.color}
            size="small"
            variant="outlined"
            sx={{ flexShrink: 0 }}
          />
        </Box>

        {/* Metrics inline */}
        {(metrics.cpu_percent != null || metrics.memory_mb != null) && (
          <Stack direction="row" spacing={1.5} sx={{ flexShrink: 0 }}>
            {metrics.cpu_percent != null && (
              <Tooltip title="CPU">
                <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'nowrap' }}>
                  CPU {metrics.cpu_percent.toFixed(1)}%
                </Typography>
              </Tooltip>
            )}
            {metrics.memory_mb != null && (
              <Tooltip title="RAM">
                <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'nowrap' }}>
                  {metrics.memory_mb.toFixed(0)} MB
                  {metrics.memory_percent != null && ` (${metrics.memory_percent.toFixed(1)}%)`}
                </Typography>
              </Tooltip>
            )}
          </Stack>
        )}

        {/* Log button: opens modal */}
        <Tooltip title={t('system.view_logs')}>
          <IconButton
            size="small"
            onClick={handleOpenLogsModal}
            color="default"
            sx={{ flexShrink: 0 }}
          >
            <TerminalIcon fontSize="small" />
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

      {/* ── Logs Modal ──────────────────────────────────────────────────────── */}
      <Dialog
        open={logsModalOpen}
        onClose={() => setLogsModalOpen(false)}
        maxWidth="md"
        fullWidth
        PaperProps={{
          sx: {
            minHeight: '60vh',
            maxHeight: '85vh',
          },
        }}
      >
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', pb: 1 }}>
          <Typography variant="h6" component="span">
            {t('system.logs_title')} · {service.service}
          </Typography>
          <Button
            size="small"
            startIcon={<RefreshIcon />}
            onClick={fetchLogs}
            disabled={logsLoading}
          >
            {t('refresh', { ns: 'common' })}
          </Button>
        </DialogTitle>
        <DialogContent dividers sx={{ p: 0, bgcolor: 'grey.50', display: 'flex', flexDirection: 'column' }}>
          <Box
            sx={{
              flex: 1,
              minHeight: 320,
              overflowY: 'auto',
              p: 2,
              fontFamily: 'monospace',
            }}
          >
            {logsLoading && (
              <Typography variant="body2" color="text.secondary">
                {t('system.logs_loading')}
              </Typography>
            )}
            {logsError && !logsLoading && (
              <Alert severity="info" sx={{ fontSize: '0.875rem' }}>
                {logsError}
              </Alert>
            )}
            {!logsLoading && !logsError && logsLines.length === 0 && (
              <Typography variant="body2" color="text.disabled">–</Typography>
            )}
            {!logsLoading && logsLines.map((line, i) => (
              <LogLine key={i} raw={line} />
            ))}
          </Box>
        </DialogContent>
        <DialogActions sx={{ px: 2, py: 1.5 }}>
          <Button onClick={() => setLogsModalOpen(false)} variant="contained">
            {t('close', { ns: 'common' })}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};
