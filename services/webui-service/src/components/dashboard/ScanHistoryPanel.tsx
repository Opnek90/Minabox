import React, { useCallback, useEffect, useState } from 'react';
import {
  Box,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  InputAdornment,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import DeleteSweepIcon from '@mui/icons-material/DeleteSweep';
import NfcIcon from '@mui/icons-material/Nfc';
import RefreshIcon from '@mui/icons-material/Refresh';
import SearchIcon from '@mui/icons-material/Search';
import { useTranslation } from 'react-i18next';
import { ActionButton } from '@/components/ui/ActionButton';
import { scanHistoryApi, type ScanEvent } from '@/api/scanHistory';
import { useLayout } from '@/hooks/useLayout';

const ACTION_COLORS: Record<string, 'success' | 'error' | 'warning' | 'default'> = {
  play: 'success',
  blocked: 'error',
  unassigned: 'warning',
};

export const ScanHistoryPanel: React.FC = () => {
  const { t } = useTranslation('common');
  const isMobile = useLayout().isMobile;
  const [events, setEvents] = useState<ScanEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterTagId, setFilterTagId] = useState('');
  const [clearDialogOpen, setClearDialogOpen] = useState(false);
  const [clearing, setClearing] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await scanHistoryApi.getAll(
        filterTagId.trim() ? { tag_id: filterTagId.trim(), limit: 500 } : { limit: 500 }
      );
      setEvents(data);
    } catch {
      setEvents([]);
    } finally {
      setLoading(false);
    }
  }, [filterTagId]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleClearConfirm = async () => {
    setClearing(true);
    try {
      await scanHistoryApi.clear();
      setEvents([]);
    } finally {
      setClearing(false);
      setClearDialogOpen(false);
    }
  };

  const fmt = new Intl.DateTimeFormat(undefined, {
    dateStyle: 'short',
    timeStyle: 'medium',
  });

  return (
    <Box>
      {/* Toolbar */}
      <Box
        display="flex"
        flexDirection={{ xs: 'column', sm: 'row' }}
        gap={1}
        mb={2}
        alignItems={{ xs: 'stretch', sm: 'center' }}
      >
        <TextField
          placeholder={t('dashboard.scan_history.filter_placeholder', { defaultValue: 'Nach Tag-ID filtern…' })}
          value={filterTagId}
          onChange={(e) => setFilterTagId(e.target.value)}
          size="small"
          fullWidth={isMobile}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" />
              </InputAdornment>
            ),
          }}
          sx={{ minWidth: { sm: 220 } }}
        />
        <Box display="flex" gap={1} flexShrink={0}>
          <ActionButton
            actionType="secondary"
            size="small"
            startIcon={<RefreshIcon />}
            onClick={() => void load()}
            disabled={loading}
            aria-label={t('actions.refresh', { defaultValue: 'Aktualisieren' })}
          >
            {!isMobile && t('actions.refresh', { defaultValue: 'Aktualisieren' })}
          </ActionButton>
          <ActionButton
            actionType="destructive"
            size="small"
            startIcon={<DeleteSweepIcon />}
            onClick={() => setClearDialogOpen(true)}
            disabled={events.length === 0}
            aria-label={t('dashboard.scan_history.clear', { defaultValue: 'Verlauf löschen' })}
          >
            {!isMobile && t('dashboard.scan_history.clear', { defaultValue: 'Verlauf löschen' })}
          </ActionButton>
        </Box>
      </Box>

      {/* Content */}
      {loading ? (
        <Box display="flex" justifyContent="center" py={4}>
          <CircularProgress size={32} />
        </Box>
      ) : events.length === 0 ? (
        <Box display="flex" flexDirection="column" alignItems="center" py={6} gap={1} color="text.secondary">
          <NfcIcon sx={{ fontSize: 48, opacity: 0.3 }} />
          <Typography variant="body2">
            {t('dashboard.scan_history.empty', { defaultValue: 'Noch keine Scan-Ereignisse vorhanden.' })}
          </Typography>
        </Box>
      ) : isMobile ? (
        /* Mobile: Card-Layout pro Scan-Eintrag */
        <Stack spacing={1}>
          {events.map((ev) => (
            <Paper key={ev.id} variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
              <Box display="flex" justifyContent="space-between" alignItems="flex-start" gap={1}>
                <Box minWidth={0} flex={1}>
                  <Typography variant="body2" fontWeight={600} noWrap>
                    {ev.tag_name ?? ev.tag_id}
                  </Typography>
                  {ev.tag_name && (
                    <Typography variant="caption" color="text.secondary" display="block" noWrap>
                      {ev.tag_id}
                    </Typography>
                  )}
                </Box>
                <Chip
                  label={ev.action}
                  color={ACTION_COLORS[ev.action] ?? 'default'}
                  size="small"
                  sx={{ flexShrink: 0 }}
                />
              </Box>
              <Box mt={0.75} display="flex" justifyContent="space-between" alignItems="center" gap={1}>
                <Typography variant="caption" color="text.secondary" noWrap flex={1}>
                  {ev.media_title ?? '—'}
                  {ev.media_type && ` · ${ev.media_type}`}
                </Typography>
                <Typography variant="caption" color="text.secondary" sx={{ flexShrink: 0, whiteSpace: 'nowrap' }}>
                  {fmt.format(new Date(ev.scanned_at))}
                </Typography>
              </Box>
            </Paper>
          ))}
        </Stack>
      ) : (
        /* Desktop: Tabellen-Layout */
        <TableContainer component={Paper} variant="outlined">
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('dashboard.scan_history.col_time', { defaultValue: 'Zeit' })}</TableCell>
                <TableCell>{t('dashboard.scan_history.col_tag', { defaultValue: 'Tag' })}</TableCell>
                <TableCell>{t('dashboard.scan_history.col_media', { defaultValue: 'Inhalt' })}</TableCell>
                <TableCell>{t('dashboard.scan_history.col_action', { defaultValue: 'Aktion' })}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {events.map((ev) => (
                <TableRow key={ev.id} hover>
                  <TableCell sx={{ whiteSpace: 'nowrap' }}>
                    {fmt.format(new Date(ev.scanned_at))}
                  </TableCell>
                  <TableCell>
                    {ev.tag_name ?? ev.tag_id}
                    {ev.tag_name && (
                      <Typography variant="caption" display="block" color="text.secondary">
                        {ev.tag_id}
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell>
                    {ev.media_title ?? '—'}
                    {ev.media_type && (
                      <Typography variant="caption" display="block" color="text.secondary">
                        {ev.media_type}
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell>
                    <Chip
                      label={ev.action}
                      color={ACTION_COLORS[ev.action] ?? 'default'}
                      size="small"
                    />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      <Dialog open={clearDialogOpen} onClose={() => setClearDialogOpen(false)}>
        <DialogTitle>{t('dashboard.scan_history.clear', { defaultValue: 'Verlauf löschen' })}</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {t('dashboard.scan_history.clear_confirm', {
              defaultValue: 'Möchtest du den gesamten Scan-Verlauf unwiderruflich löschen?',
            })}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <ActionButton actionType="secondary" onClick={() => setClearDialogOpen(false)} disabled={clearing}>
            {t('actions.cancel', { defaultValue: 'Abbrechen' })}
          </ActionButton>
          <ActionButton actionType="destructive" onClick={() => void handleClearConfirm()} disabled={clearing}>
            {t('actions.confirm', { defaultValue: 'Bestätigen' })}
          </ActionButton>
        </DialogActions>
      </Dialog>
    </Box>
  );
};
