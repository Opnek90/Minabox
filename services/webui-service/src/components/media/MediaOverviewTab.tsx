import React from 'react';
import {
  Box,
  Card,
  CardActionArea,
  CardContent,
  Chip,
  Divider,
  Grid,
  List,
  ListItem,
  ListItemAvatar,
  ListItemText,
  Avatar,
  Typography,
} from '@mui/material';
import AudiotrackIcon from '@mui/icons-material/Audiotrack';
import FolderIcon from '@mui/icons-material/Folder';
import PlaylistPlayIcon from '@mui/icons-material/PlaylistPlay';
import PodcastsIcon from '@mui/icons-material/Podcasts';
import StreamIcon from '@mui/icons-material/Stream';
import AccessTimeIcon from '@mui/icons-material/AccessTime';
import { useTranslation } from 'react-i18next';
import { audioApi } from '@/api/audio';
import type { Playlist, Podcast, Stream, Track, TrackFolder } from '@/types/api';
import { formatTime } from '@/utils/formatTime';

interface MediaOverviewTabProps {
  tracks: Track[];
  folders: TrackFolder[];
  playlists: Playlist[];
  streams: Stream[];
  podcasts: Podcast[];
  /** Switch to a specific tab index (0=Playlists,1=Tracks,2=Streams,3=Podcasts) */
  onNavigateTab: (tab: number) => void;
}

const StatCard: React.FC<{ icon: React.ReactNode; label: string; value: number; color: string; onClick: () => void }> = ({
  icon, label, value, color, onClick,
}) => (
  <Card variant="outlined" sx={{ borderRadius: 2 }}>
    <CardActionArea onClick={onClick} sx={{ p: 2, display: 'flex', alignItems: 'center', gap: 2 }}>
      <Box
        sx={{
          width: 48, height: 48, borderRadius: 2,
          bgcolor: `${color}.main`, color: `${color}.contrastText`,
          display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
        }}
      >
        {icon}
      </Box>
      <Box>
        <Typography variant="h5" fontWeight={700} lineHeight={1}>{value}</Typography>
        <Typography variant="caption" color="text.secondary">{label}</Typography>
      </Box>
    </CardActionArea>
  </Card>
);

export const MediaOverviewTab: React.FC<MediaOverviewTabProps> = ({
  tracks, folders, playlists, streams, podcasts, onNavigateTab,
}) => {
  const { t } = useTranslation('media');

  const recentTracks = [...tracks]
    .filter((tr) => tr.last_played_at != null)
    .sort((a, b) => new Date(b.last_played_at!).getTime() - new Date(a.last_played_at!).getTime())
    .slice(0, 6);

  const recentPlaylists = [...playlists]
    .filter((pl) => pl.updated_at != null)
    .sort((a, b) => new Date(b.updated_at!).getTime() - new Date(a.updated_at!).getTime())
    .slice(0, 4);

  return (
    <Box sx={{ p: { xs: 1, md: 2 } }}>
      {/* Stats */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid item xs={6} sm={3}>
          <StatCard icon={<AudiotrackIcon />} label={t('tabs.tracks')} value={tracks.length} color="primary" onClick={() => onNavigateTab(2)} />
        </Grid>
        <Grid item xs={6} sm={3}>
          <StatCard icon={<PlaylistPlayIcon />} label={t('tabs.playlists')} value={playlists.length} color="secondary" onClick={() => onNavigateTab(1)} />
        </Grid>
        <Grid item xs={6} sm={3}>
          <StatCard icon={<FolderIcon />} label={t('tabs.tracks') + ' Ordner'} value={folders.length} color="warning" onClick={() => onNavigateTab(2)} />
        </Grid>
        <Grid item xs={6} sm={3}>
          <StatCard icon={<PodcastsIcon />} label={t('tabs.podcasts')} value={podcasts.length} color="success" onClick={() => onNavigateTab(4)} />
        </Grid>
      </Grid>

      <Grid container spacing={3}>
        {/* Zuletzt gespielt */}
        {recentTracks.length > 0 && (
          <Grid item xs={12} md={6}>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1, display: 'flex', alignItems: 'center', gap: 1 }}>
              <AccessTimeIcon fontSize="small" color="action" />
              Zuletzt gespielt
            </Typography>
            <Card variant="outlined" sx={{ borderRadius: 2 }}>
              <List dense disablePadding>
                {recentTracks.map((track, i) => (
                  <React.Fragment key={track.id}>
                    <ListItem
                      secondaryAction={
                        track.duration_ms != null && (
                          <Chip label={formatTime(track.duration_ms)} size="small" variant="outlined"
                            sx={{ height: 18, fontSize: '0.65rem' }} />
                        )
                      }
                      sx={{ cursor: 'pointer', '&:hover': { bgcolor: 'action.hover' } }}
                      onClick={() => void audioApi.play({ track_id: track.id })}
                    >
                      <ListItemAvatar sx={{ minWidth: 40 }}>
                        <Avatar src={track.cover_art_url ?? undefined} variant="rounded" sx={{ width: 32, height: 32, bgcolor: 'action.selected' }}>
                          <AudiotrackIcon sx={{ fontSize: 16 }} />
                        </Avatar>
                      </ListItemAvatar>
                      <ListItemText
                        primary={track.title}
                        secondary={track.artist}
                        primaryTypographyProps={{ noWrap: true, variant: 'body2' }}
                        secondaryTypographyProps={{ noWrap: true, variant: 'caption' }}
                      />
                    </ListItem>
                    {i < recentTracks.length - 1 && <Divider component="li" />}
                  </React.Fragment>
                ))}
              </List>
            </Card>
          </Grid>
        )}

        {/* Playlists-Schnellzugriff */}
        {recentPlaylists.length > 0 && (
          <Grid item xs={12} md={6}>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1, display: 'flex', alignItems: 'center', gap: 1 }}>
              <PlaylistPlayIcon fontSize="small" color="action" />
              Playlists
            </Typography>
            <Grid container spacing={1}>
              {recentPlaylists.map((pl) => (
                <Grid item xs={6} key={pl.id}>
                  <Card
                    variant="outlined"
                    sx={{ borderRadius: 2, cursor: 'pointer', '&:hover': { bgcolor: 'action.hover' } }}
                    onClick={() => onNavigateTab(1)}
                  >
                    <CardContent sx={{ p: '12px !important', display: 'flex', alignItems: 'center', gap: 1.5 }}>
                      {pl.cover_art_url ? (
                        <Avatar src={pl.cover_art_url} variant="rounded" sx={{ width: 36, height: 36 }} />
                      ) : (
                        <Avatar variant="rounded" sx={{ width: 36, height: 36, bgcolor: 'secondary.main' }}>
                          <PlaylistPlayIcon sx={{ fontSize: 18 }} />
                        </Avatar>
                      )}
                      <Box sx={{ minWidth: 0 }}>
                        <Typography variant="body2" fontWeight={600} noWrap>{pl.name}</Typography>
                        <Typography variant="caption" color="text.secondary">
                          {pl.tracks?.length ?? 0} Tracks
                        </Typography>
                      </Box>
                    </CardContent>
                  </Card>
                </Grid>
              ))}
            </Grid>
          </Grid>
        )}

        {/* Streams & Podcasts Mini-Widget */}
        {(streams.length > 0 || podcasts.length > 0) && (
          <Grid item xs={12}>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1, display: 'flex', alignItems: 'center', gap: 1 }}>
              <StreamIcon fontSize="small" color="action" />
              Streams & Podcasts
            </Typography>
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
              {streams.slice(0, 4).map((s) => (
                <Chip
                  key={s.id}
                  icon={<StreamIcon />}
                  label={s.title}
                  onClick={() => onNavigateTab(3)}
                  variant="outlined"
                  sx={{ cursor: 'pointer' }}
                />
              ))}
              {podcasts.slice(0, 4).map((p) => (
                <Chip
                  key={p.id}
                  icon={<PodcastsIcon />}
                  label={p.title}
                  onClick={() => onNavigateTab(4)}
                  variant="outlined"
                  sx={{ cursor: 'pointer' }}
                />
              ))}
            </Box>
          </Grid>
        )}
      </Grid>
    </Box>
  );
};
