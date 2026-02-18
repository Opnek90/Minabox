import React from 'react';
import { Box, Typography } from '@mui/material';
import MusicNoteIcon from '@mui/icons-material/MusicNote';
import { useTranslation } from 'react-i18next';

interface TrackInfoProps {
  title: string | null | undefined;
  artist: string | null | undefined;
  album: string | null | undefined;
  playlistName?: string | null;
  playlistCurrent?: number | null;
  playlistTotal?: number | null;
  stopped?: boolean;
}

export const TrackInfo: React.FC<TrackInfoProps> = ({
  title,
  artist,
  album,
  playlistName,
  playlistCurrent,
  playlistTotal,
  stopped = false,
}) => {
  const { t } = useTranslation('player');

  return (
    <Box
      display="flex"
      flexDirection="column"
      alignItems="center"
      gap={1}
      sx={{ py: 2, px: 3, textAlign: 'center' }}
    >
      {/* Album Art Placeholder */}
      <Box
        sx={{
          width: 180,
          height: 180,
          borderRadius: 3,
          backgroundColor: 'primary.light',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          mb: 1,
          boxShadow: 4,
        }}
      >
        <MusicNoteIcon sx={{ fontSize: 80, color: 'primary.contrastText' }} />
      </Box>

      {stopped ? (
        <Typography variant="body1" color="text.secondary" sx={{ mt: 1 }}>
          {t('nothing_playing')}
        </Typography>
      ) : (
        <>
          <Typography variant="h5" fontWeight={700} noWrap sx={{ maxWidth: 320 }}>
            {title ?? t('unknown_track')}
          </Typography>

          <Typography variant="body1" color="text.secondary" noWrap sx={{ maxWidth: 320 }}>
            {artist ?? t('unknown_artist')}
          </Typography>

          {album && (
            <Typography variant="body2" color="text.secondary" noWrap sx={{ maxWidth: 320 }}>
              {album}
            </Typography>
          )}

          {playlistName && (
            <Typography variant="caption" color="text.secondary">
              {t('playlist_name', { name: playlistName })}
              {playlistCurrent != null && playlistTotal != null && (
                <> · {t('playlist_info', { current: playlistCurrent, total: playlistTotal })}</>
              )}
            </Typography>
          )}
        </>
      )}
    </Box>
  );
};
