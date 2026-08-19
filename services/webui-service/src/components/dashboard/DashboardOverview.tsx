import React from 'react';
import {
  Box,
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
import { useDashboardOverview } from '@/hooks/useDashboardOverview';
import { ActionButton } from '@/components/ui/ActionButton';
import { useLayout } from '@/hooks/useLayout';

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
  const isMobile = useLayout().isMobile;
  const {
    data,
    loading,
    refreshing,
    resetDialogOpen,
    resetting,
    openResetDialog,
    closeResetDialog,
    load,
    confirmReset,
  } = useDashboardOverview();

  if (loading && !data) {
    return (
      <Box>
        <Grid container spacing={1.5}>
          {[1, 2, 3, 4, 5, 6, 7].map((i) => (
            <Grid item xs={6} sm={6} md={4} key={i}>
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
      {/* Action buttons: always row, text hidden on mobile */}
      <Box
        display="flex"
        flexDirection="row"
        justifyContent="flex-end"
        alignItems="center"
        gap={1}
        mb={1.5}
      >
        <ActionButton
          actionType="destructive"
          size="small"
          startIcon={<DeleteSweepIcon />}
          onClick={openResetDialog}
          aria-label={t('dashboard.reset_listening')}
        >
          {isMobile ? null : t('dashboard.reset_listening')}
        </ActionButton>
        <ActionButton
          actionType="secondary"
          size="small"
          startIcon={<RefreshIcon />}
          onClick={() => void load()}
          disabled={refreshing}
          aria-label={t('actions.refresh')}
        >
          {isMobile ? null : t('actions.refresh')}
        </ActionButton>
      </Box>

      <Dialog open={resetDialogOpen} onClose={closeResetDialog}>
        <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>
          {t('dashboard.reset_listening')}
        </DialogTitle>
        <DialogContent>
          <DialogContentText>
            {t('dashboard.reset_listening_confirm')}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <ActionButton actionType="secondary" onClick={closeResetDialog} disabled={resetting}>
            {t('actions.cancel')}
          </ActionButton>
          <ActionButton
            actionType="destructive"
            onClick={() => void confirmReset()}
            disabled={resetting}
          >
            {t('actions.confirm')}
          </ActionButton>
        </DialogActions>
      </Dialog>

      <Grid container spacing={1.5}>
        <Grid item xs={6} sm={6} md={4}>
          <StatTile
            icon={<HeadphonesIcon fontSize="small" />}
            label={t('dashboard.minutes_today')}
            value={`${d.minutes_today.toFixed(1)} Min.`}
          />
        </Grid>
        <Grid item xs={6} sm={6} md={4}>
          <StatTile
            icon={<AlbumIcon fontSize="small" />}
            label={t('dashboard.minutes_total')}
            value={`${d.minutes_total.toFixed(1)} Min.`}
          />
        </Grid>
        {d.daily_limit_enabled && (
          <Grid item xs={6} sm={6} md={4}>
            <StatTile
              icon={<HeadphonesIcon fontSize="small" />}
              label={t('dashboard.remaining_minutes')}
              value={`${Math.max(0, Math.round(d.daily_limit_minutes - d.minutes_today))} Min.`}
            />
          </Grid>
        )}
        <Grid item xs={6} sm={6} md={4}>
          <StatTile
            icon={<NfcIcon fontSize="small" />}
            label={t('dashboard.tags_count')}
            value={String(d.tags_count)}
          />
        </Grid>
        <Grid item xs={6} sm={6} md={4}>
          <StatTile
            icon={<LibraryMusicIcon fontSize="small" />}
            label={t('dashboard.tracks_count')}
            value={String(d.tracks_count)}
          />
        </Grid>
        <Grid item xs={6} sm={6} md={4}>
          <StatTile
            icon={<RadioIcon fontSize="small" />}
            label={t('dashboard.streams_count')}
            value={String(d.streams_count)}
          />
        </Grid>
        <Grid item xs={6} sm={6} md={4}>
          <StatTile
            icon={<MicIcon fontSize="small" />}
            label={t('dashboard.podcasts_count')}
            value={String(d.podcasts_count)}
          />
        </Grid>
        <Grid item xs={6} sm={6} md={4}>
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
