import React, { useCallback, useEffect, useState } from 'react';
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Grid,
  Skeleton,
  Typography,
} from '@mui/material';
import AlbumIcon from '@mui/icons-material/Album';
import DeleteSweepIcon from '@mui/icons-material/DeleteSweep';
import HeadphonesIcon from '@mui/icons-material/Headphones';
import MicIcon from '@mui/icons-material/Mic';
import RefreshIcon from '@mui/icons-material/Refresh';
import LibraryMusicIcon from '@mui/icons-material/LibraryMusic';
import RadioIcon from '@mui/icons-material/Radio';
import NfcIcon from '@mui/icons-material/Nfc';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { statsApi } from '@/api/stats';
import type { OverviewResponse } from '@/types/api';

interface StatTileProps {
  icon: React.ReactNode;
  label: string;
  value: string;
}

const StatTile: React.FC<StatTileProps> = ({ icon, label, value }) => (
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
      <Typography variant="body2" fontWeight={600} noWrap>
        {value}
      </Typography>
    </Box>
  </Box>
);

export const DashboardOverview: React.FC = () => {
  const { t } = useTranslation('common');
  const { showSuccess, showError } = useToast();
  const [data, setData] = useState<OverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [resetDialogOpen, setResetDialogOpen] = useState(false);
  const [resetting, setResetting] = useState(false);

  const load = useCallback(async () => {
    if (!data) setLoading(true);
    else setRefreshing(true);
    try {
      const res = await statsApi.getOverview();
      setData(res);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [data]);

  useEffect(() => {
    load();
    const interval = setInterval(load, 60_000);
    return () => clearInterval(interval);
  }, [load]);

  const handleResetConfirm = useCallback(async () => {
    setResetting(true);
    try {
      await statsApi.resetListeningStats();
      setResetDialogOpen(false);
      await load();
      showSuccess(t('dashboard.reset_success', { defaultValue: 'Zeiten zurückgesetzt' }));
    } catch {
      showError(t('dashboard.reset_error', { defaultValue: 'Zurücksetzen fehlgeschlagen' }));
    } finally {
      setResetting(false);
    }
  }, [load, showSuccess, showError, t]);

  if (loading && !data) {
    return (
      <Box>
        <Grid container spacing={1.5}>
          {[1, 2, 3, 4, 5, 6, 7].map((i) => (
            <Grid item xs={12} sm={6} md={4} key={i}>
              <Skeleton variant="rounded" height={56} />
            </Grid>
          ))}
        </Grid>
      </Box>
    );
  }

  const d = data!;

  return (
    <Box>
      <Box display="flex" justifyContent="flex-end" alignItems="center" gap={1} mb={1.5} flexWrap="wrap">
        <Button
          variant="outlined"
          color="error"
          size="small"
          startIcon={<DeleteSweepIcon />}
          onClick={() => setResetDialogOpen(true)}
        >
          {t('dashboard.reset_listening')}
        </Button>
        <Button
          startIcon={<RefreshIcon />}
          onClick={load}
          size="small"
          disabled={refreshing}
        >
          {t('actions.refresh')}
        </Button>
      </Box>

      <Dialog open={resetDialogOpen} onClose={() => !resetting && setResetDialogOpen(false)}>
        <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>
          {t('dashboard.reset_listening')}
        </DialogTitle>
        <DialogContent>
          <DialogContentText>
            {t('dashboard.reset_listening_confirm')}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setResetDialogOpen(false)} disabled={resetting}>
            {t('actions.cancel')}
          </Button>
          <Button variant="contained" color="error" onClick={handleResetConfirm} disabled={resetting}>
            {t('actions.confirm')}
          </Button>
        </DialogActions>
      </Dialog>
      <Grid container spacing={1.5}>
        <Grid item xs={12} sm={6} md={4}>
          <StatTile
            icon={<HeadphonesIcon fontSize="small" />}
            label={t('dashboard.minutes_today')}
            value={`${d.minutes_today.toFixed(1)} Min.`}
          />
        </Grid>
        <Grid item xs={12} sm={6} md={4}>
          <StatTile
            icon={<AlbumIcon fontSize="small" />}
            label={t('dashboard.minutes_total')}
            value={`${d.minutes_total.toFixed(1)} Min.`}
          />
        </Grid>
        {d.daily_limit_enabled && (
          <Grid item xs={12} sm={6} md={4}>
            <StatTile
              icon={<HeadphonesIcon fontSize="small" />}
              label={t('dashboard.remaining_minutes')}
              value={`${Math.max(0, Math.round(d.daily_limit_minutes - d.minutes_today))} Min.`}
            />
          </Grid>
        )}
        <Grid item xs={12} sm={6} md={4}>
          <StatTile
            icon={<NfcIcon fontSize="small" />}
            label={t('dashboard.tags_count')}
            value={String(d.tags_count)}
          />
        </Grid>
        <Grid item xs={12} sm={6} md={4}>
          <StatTile
            icon={<LibraryMusicIcon fontSize="small" />}
            label={t('dashboard.tracks_count')}
            value={String(d.tracks_count)}
          />
        </Grid>
        <Grid item xs={12} sm={6} md={4}>
          <StatTile
            icon={<RadioIcon fontSize="small" />}
            label={t('dashboard.streams_count')}
            value={String(d.streams_count)}
          />
        </Grid>
        <Grid item xs={12} sm={6} md={4}>
          <StatTile
            icon={<MicIcon fontSize="small" />}
            label={t('dashboard.podcasts_count')}
            value={String(d.podcasts_count)}
          />
        </Grid>
        <Grid item xs={12} sm={6} md={4}>
          <StatTile
            icon={<LibraryMusicIcon fontSize="small" />}
            label={t('dashboard.playlists_count')}
            value={String(d.playlists_count)}
          />
        </Grid>
      </Grid>
    </Box>
  );
};
