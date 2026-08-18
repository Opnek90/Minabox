import React from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import { useTranslation } from 'react-i18next';
import { useServiceLogs } from '@/hooks/useServiceLogs';
import { ResponsiveDialog } from '@/components/common/ResponsiveDialog';

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

/** Parse plain (non-JSON) log lines, e.g. "INFO  [alembic.runtime.migration] Message". */
function parsePlainLogLine(line: string): ParsedLine | null {
  const s = line.trim();
  if (!s) return null;
  // Python logging style: LEVEL (optional spaces) [optional logger] rest = message
  const m = s.match(/^(DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+(?:\[[\w.]+\]\s+)?(.+)$/i);
  if (!m) return null;
  const level = m[1].toLowerCase();
  const message = m[2].trim();
  return { level, ts: '', message, data: {} };
}

/** Parse nginx combined access log: IP - - [date] "METHOD path PROTO" status size "referer" "user-agent". */
function parseNginxAccessLine(line: string): ParsedLine | null {
  const s = line.trim();
  const m = s.match(/^(\S+)\s+-\s+-\s+\[([^\]]+)\]\s+"(\w+)\s+(\S+)\s+[^"]*"\s+(\d+)\s+(\d+|-)\s+"([^"]*)"\s+"([^"]*)"$/);
  if (!m) return null;
  const [, ip, dateStr, method, path, status, size, referer, userAgent] = m;
  // Nginx date: 22/Feb/2026:14:26:41 +0000 → convert to ISO for formatLogTimestamp
  let ts = '';
  try {
    const normalized = dateStr.replace(':', ' ').replace(/\//g, ' ');
    const d = new Date(normalized);
    if (!Number.isNaN(d.getTime())) ts = d.toISOString();
  } catch {
    ts = dateStr;
  }
  const message = `${method} ${path} → ${status}`;
  const data: Record<string, unknown> = {
    ip,
    method,
    path,
    status: parseInt(status, 10),
    size: size === '-' ? undefined : parseInt(size, 10),
    referer: referer || undefined,
    user_agent: userAgent || undefined,
  };
  return { level: 'info', ts, message, data };
}

/** Parse Mosquitto broker log: unix_timestamp: Message */
function parseMosquittoLine(line: string): ParsedLine | null {
  const s = line.trim();
  const m = s.match(/^(\d+):\s*(.+)$/);
  if (!m) return null;
  const [, unixStr, message] = m;
  const unix = parseInt(unixStr!, 10);
  if (Number.isNaN(unix)) return null;
  const ts = new Date(unix * 1000).toISOString();
  let level = 'info';
  const lower = message.toLowerCase();
  if (lower.includes('error') || lower.includes('failed')) level = 'error';
  else if (lower.includes('warning') || lower.includes('disconnect')) level = 'warning';
  return { level, ts, message, data: {} };
}

type ChipColor = 'default' | 'error' | 'warning' | 'info' | 'success';

function levelColor(level: string): ChipColor {
  switch (level) {
    case 'error': case 'critical': return 'error';
    case 'warning': case 'warn':   return 'warning';
    case 'debug':                  return 'default';
    default:                       return 'info';
  }
}

/** Format log timestamp for display: UTC ISO strings are shown in user's local time. */
function formatLogTimestamp(ts: string): string {
  if (!ts || ts === '–') return ts || '–';
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'medium' });
}

/** Format parsed.data for display: key-value lines for flat/small objects, else pretty-printed JSON. */
function formatDataCell(data: Record<string, unknown>): React.ReactNode {
  const keys = Object.keys(data);
  if (keys.length === 0) return '–';
  const isFlat = keys.every((k) => {
    const v = data[k];
    return v === null || typeof v !== 'object' || (typeof v === 'object' && !Array.isArray(v) && Object.keys(v as object).length === 0);
  });
  if (isFlat && keys.length <= 8) {
    return (
      <Box component="pre" sx={{ margin: 0, fontSize: '0.75rem', whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontFamily: 'inherit' }}>
        {keys.map((k) => (
          <span key={k}>
            {k}: {String(data[k] ?? '')}
            {'\n'}
          </span>
        ))}
      </Box>
    );
  }
  return (
    <Box component="pre" sx={{ margin: 0, fontSize: '0.75rem', whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontFamily: 'inherit' }}>
      {JSON.stringify(data, null, 2)}
    </Box>
  );
}

/** Replace UTC timestamps in a raw log line with local time for display. */
function rawLineWithLocalTime(line: string): string {
  // ISO with Z: 2026-02-21T14:12:27.877216Z
  const isoZ = /(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2}):(\d{2})(\.\d+)?Z/g;
  let out = line.replace(isoZ, (_, date, h, m, s, frac) => {
    const d = new Date(`${date}T${h}:${m}:${s}${frac || ''}Z`);
    if (Number.isNaN(d.getTime())) return `${date}T${h}:${m}:${s}${frac || ''}Z`;
    return d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'medium' });
  });
  // Space-separated "YYYY-MM-DD HH:MM:SS" (ConsoleRenderer) – treat as UTC
  const spaceTs = /(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2}):(\d{2})(?=\s|\[)/;
  out = out.replace(spaceTs, (match, date, h, m, s) => {
    const d = new Date(`${date}T${h}:${m}:${s}.000Z`);
    if (Number.isNaN(d.getTime())) return match;
    return d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'medium' });
  });
  return out;
}

// ── Props ────────────────────────────────────────────────────────────────────
interface ServiceLogsModalProps {
  serviceName: string;
  open: boolean;
  onClose: () => void;
}

// ── Component ────────────────────────────────────────────────────────────────
export const ServiceLogsModal: React.FC<ServiceLogsModalProps> = ({
  serviceName,
  open,
  onClose,
}) => {
  const { t } = useTranslation('admin');
  const {
    displayLines,
    loading: logsLoading,
    error: logsError,
    autoRefresh,
    setAutoRefresh,
    refresh,
  } = useServiceLogs(serviceName, open);

  return (
    <ResponsiveDialog
      open={open}
      onClose={onClose}
      maxWidth="lg"
      fullWidth
      PaperProps={{
        sx: {
          // Feste Hoehe nur, solange der Dialog eine Karte ist – im
          // Vollbild-Sheet unterhalb `sm` fuellt er ohnehin den Schirm.
          minHeight: { xs: 'auto', sm: '60vh' },
          maxHeight: { xs: 'none', sm: '85vh' },
        },
      }}
    >
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 1, pb: 1 }}>
        <Typography variant="h6" component="span">
          {t('system.logs_title')} · {serviceName}
        </Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <FormControlLabel
            control={
              <Switch
                size="small"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
              />
            }
            label={t('system.logs_auto_refresh')}
          />
          <Button
            size="small"
            startIcon={<RefreshIcon />}
            onClick={() => void refresh()}
            disabled={logsLoading}
          >
            {t('actions.refresh', { ns: 'common' })}
          </Button>
        </Box>
      </DialogTitle>
      <DialogContent dividers sx={{ p: 0, bgcolor: 'grey.50', display: 'flex', flexDirection: 'column' }}>
        <TableContainer sx={{ flex: 1, minHeight: 320, overflow: 'auto' }}>
          {logsLoading && displayLines.length === 0 && (
            <Box sx={{ p: 2 }}>
              <Typography variant="body2" color="text.secondary">
                {t('system.logs_loading')}
              </Typography>
            </Box>
          )}
          {logsError && !logsLoading && (
            <Box sx={{ p: 2 }}>
              <Alert severity="info" sx={{ fontSize: '0.875rem' }}>
                {logsError}
              </Alert>
            </Box>
          )}
          {!logsLoading && !logsError && displayLines.length === 0 && (
            <Box sx={{ p: 2 }}>
              <Typography variant="body2" color="text.disabled">–</Typography>
            </Box>
          )}
          {!logsLoading && displayLines.length > 0 && (
            <Table size="small" stickyHeader sx={{ fontFamily: 'monospace' }}>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontWeight: 600, fontSize: '0.75rem', width: 80 }}>{t('system.logs_column_level')}</TableCell>
                  <TableCell sx={{ fontWeight: 600, fontSize: '0.75rem', width: 160 }}>{t('system.logs_column_time')}</TableCell>
                  <TableCell sx={{ fontWeight: 600, fontSize: '0.75rem', minWidth: 280 }}>{t('system.logs_column_message')}</TableCell>
                  <TableCell sx={{ fontWeight: 600, fontSize: '0.75rem', minWidth: 180 }}>{t('system.logs_column_data')}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {displayLines.map((raw, i) => {
                  const clean = stripAnsi(raw);
                  const parsed =
                    parseStructlogLine(clean) ??
                    parsePlainLogLine(clean) ??
                    parseNginxAccessLine(clean) ??
                    parseMosquittoLine(clean);
                  if (parsed) {
                    return (
                      <TableRow key={i} hover>
                        <TableCell sx={{ fontSize: '0.8rem', py: 0.5 }}>
                          <Chip
                            size="small"
                            label={parsed.level}
                            color={levelColor(parsed.level)}
                            sx={{ height: 20, fontSize: '0.7rem' }}
                          />
                        </TableCell>
                        <TableCell sx={{ fontSize: '0.75rem', color: 'text.disabled', py: 0.5, whiteSpace: 'nowrap' }}>
                          {formatLogTimestamp(parsed.ts)}
                        </TableCell>
                        <TableCell sx={{ fontSize: '0.8rem', py: 0.5, wordBreak: 'break-word' }}>
                          {parsed.message || '–'}
                        </TableCell>
                        <TableCell sx={{ fontSize: '0.75rem', py: 0.5, opacity: 0.9, verticalAlign: 'top' }}>
                          {formatDataCell(parsed.data)}
                        </TableCell>
                      </TableRow>
                    );
                  }
                  return (
                    <TableRow key={i} hover>
                      <TableCell colSpan={4} sx={{ fontSize: '0.8rem', py: 0.5, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                        {rawLineWithLocalTime(clean) || ' '}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </TableContainer>
      </DialogContent>
      <DialogActions sx={{ px: 2, py: 1.5 }}>
        <Button onClick={onClose} variant="contained">
          {t('actions.close', { ns: 'common' })}
        </Button>
      </DialogActions>
    </ResponsiveDialog>
  );
};
