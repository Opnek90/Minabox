import React from 'react';
import { Box, Typography, useMediaQuery, useTheme } from '@mui/material';
import MusicNoteIcon from '@mui/icons-material/MusicNote';
import { useTranslation } from 'react-i18next';

interface TrackInfoProps {
  title: string | null | undefined;
  artist: string | null | undefined;
  album: string | null | undefined;
  coverArtUrl?: string | null;
  playlistName?: string | null;
  playlistCurrent?: number | null;
  playlistTotal?: number | null;
  stopped?: boolean;
}

export const TrackInfo: React.FC<TrackInfoProps> = ({
  title,
  artist,
  album,
  coverArtUrl,
  playlistName,
  playlistCurrent,
  playlistTotal,
  stopped = false,
}) => {
  const { t } = useTranslation('player');
  const theme = useTheme();
  const isSmall = useMediaQuery(theme.breakpoints.down('sm'));

  const artSize = isSmall ? 120 : 180;
  const iconSize = isSmall ? 48 : 80;
  const maxTextWidth = isSmall ? '100%' : 320;

  return (
    <Box
      display="flex"
      flexDirection="column"
      alignItems="center"
      gap={1}
      sx={{
        py: isSmall ? 1 : 2,
        px: isSmall ? 2 : 3,
        textAlign: 'center',
      }}
    >
      {/* Album Art or Placeholder */}
      <Box
        sx={{
          width: artSize,
          height: artSize,
          borderRadius: 2,
          backgroundColor: 'primary.light',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          mb: 0.5,
          boxShadow: isSmall ? 2 : 4,
          overflow: 'hidden',
        }}
      >
        {coverArtUrl ? (
          <Box
            component="img"
            src={coverArtUrl}
            alt=""
            sx={{
              width: '100%',
              height: '100%',
              objectFit: 'cover',
            }}
          />
        ) : (
          <MusicNoteIcon sx={{ fontSize: iconSize, color: 'primary.contrastText' }} />
        )}
      </Box>

      {stopped ? (
        <Typography variant="body1" color="text.secondary" sx={{ mt: 0.5 }}>
          {t('nothing_playing')}
        </Typography>
      ) : (
        <>
          <Typography
            variant={isSmall ? 'body1' : 'h5'}
            fontWeight={700}
            noWrap
            sx={{ maxWidth: maxTextWidth, width: '100%' }}
          >
            {title ?? t('unknown_track')}
          </Typography>

          <Typography variant="body2" color="text.secondary" noWrap sx={{ maxWidth: maxTextWidth, width: '100%' }}>
            {artist ?? t('unknown_artist')}
          </Typography>

          {album && (
            <Typography variant="caption" color="text.secondary" noWrap sx={{ maxWidth: maxTextWidth, width: '100%' }}>
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
