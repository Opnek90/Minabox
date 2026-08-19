import React from 'react';
import {
  Avatar,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  Grid,
  List,
  ListItem,
  ListItemAvatar,
  ListItemText,
  Typography,
} from '@mui/material';
import AudiotrackIcon from '@mui/icons-material/Audiotrack';
import PlaylistPlayIcon from '@mui/icons-material/PlaylistPlay';
import PodcastsIcon from '@mui/icons-material/Podcasts';
import StreamIcon from '@mui/icons-material/Stream';
import AccessTimeIcon from '@mui/icons-material/AccessTime';
import NewReleasesIcon from '@mui/icons-material/NewReleases';
import { useTranslation } from 'react-i18next';
import { audioApi } from '@/api/audio';
import type { Playlist, Podcast, Stream, Track } from '@/types/api';
import { formatTime } from '@/utils/formatTime';

interface MediaOverviewTabProps {
  tracks: Track[];
  playlists: Playlist[];
  streams: Stream[];
  podcasts: Podcast[];
  onNavigateTab: (tab: number) => void;
}

/**
 * Startbereich der Mediathek: was zuletzt lief und was neu dazugekommen ist.
 *
 * Frueher stand hier zusaetzlich eine Reihe Kacheln "Symbol + Zahl + Name" je
 * Bereich. Seit die Bereichsleiste genau das dauerhaft zeigt – Symbol, Name und
 * Menge, einen Tipp entfernt – waren die Kacheln eine Dublette der Leiste
 * direkt darueber, ebenso die Podcast-Chips zum Podcast-Bereich. Uebrig bleibt,
 * was es sonst nirgends gibt: die juengste Aktivitaet.
 *
 * Alle drei Bloecke rechnen aus Daten, die `MediaPage` ohnehin geladen hat –
 * die Seite loest keinen zusaetzlichen Aufruf aus.
 */

/** Gemeinsame Zeilenform fuer Tracks, Streams und Podcasts. */
interface Entry {
  key: string;
  title: string;
  subtitle: string | null;
  cover: string | null;
  icon: React.ReactNode;
  durationMs: number | null;
  play: () => void;
  /** Zeitstempel, nach denen die beiden Bloecke sortieren. */
  played: string | null;
  added: string | null;
}

/** Sortiert absteigend nach einem der beiden Zeitstempel. */
const newestBy = (field: 'played' | 'added') => (a: Entry, b: Entry): number =>
  new Date(b[field]!).getTime() - new Date(a[field]!).getTime();

const EntryList: React.FC<{ entries: Entry[] }> = ({ entries }) => (
  <Card variant="outlined" sx={{ borderRadius: 2 }}>
    <List dense disablePadding>
      {entries.map((entry, i) => (
        <React.Fragment key={entry.key}>
          <ListItem
            secondaryAction={
              entry.durationMs != null && (
                <Chip
                  label={formatTime(entry.durationMs)}
                  size="small"
                  variant="outlined"
                  sx={{ height: 18, fontSize: '0.65rem' }}
                />
              )
            }
            sx={{ cursor: 'pointer', '&:hover': { bgcolor: 'action.hover' } }}
            onClick={entry.play}
          >
            <ListItemAvatar sx={{ minWidth: 40 }}>
              <Avatar
                src={entry.cover ?? undefined}
                variant="rounded"
                sx={{ width: 32, height: 32, bgcolor: 'action.selected' }}
              >
                {entry.icon}
              </Avatar>
            </ListItemAvatar>
            <ListItemText
              primary={entry.title}
              secondary={entry.subtitle}
              primaryTypographyProps={{ noWrap: true, variant: 'body2' }}
              secondaryTypographyProps={{ noWrap: true, variant: 'caption' }}
            />
          </ListItem>
          {i < entries.length - 1 && <Divider component="li" />}
        </React.Fragment>
      ))}
    </List>
  </Card>
);

const BlockHeading: React.FC<{
  icon: React.ReactNode;
  title: string;
  action?: { label: string; onClick: () => void };
}> = ({ icon, title, action }) => (
  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
    {icon}
    <Typography variant="subtitle1" fontWeight={600}>
      {title}
    </Typography>
    {action && (
      <Button size="small" onClick={action.onClick} sx={{ ml: 'auto' }}>
        {action.label}
      </Button>
    )}
  </Box>
);

export const MediaOverviewTab: React.FC<MediaOverviewTabProps> = ({
  tracks, playlists, streams, podcasts, onNavigateTab,
}) => {
  const { t } = useTranslation('media');

  // Tracks, Streams und Podcasts tragen alle `last_played_at` und `created_at`;
  // die Bloecke mischen sie deshalb, statt nur Tracks zu zeigen.
  const entries: Entry[] = [
    ...tracks.map((tr) => ({
      key: `track-${tr.id}`,
      title: tr.title,
      subtitle: tr.artist ?? t('overview.kind_track'),
      cover: tr.cover_art_url ?? null,
      icon: <AudiotrackIcon sx={{ fontSize: 16 }} />,
      durationMs: tr.duration_ms,
      play: () => void audioApi.play({ track_id: tr.id }),
      played: tr.last_played_at,
      added: tr.created_at,
    })),
    ...streams.map((st) => ({
      key: `stream-${st.id}`,
      title: st.title,
      subtitle: st.artist ?? t('overview.kind_stream'),
      cover: st.cover_art_url,
      icon: <StreamIcon sx={{ fontSize: 16 }} />,
      durationMs: null,
      play: () => void audioApi.play({ stream_id: st.id }),
      played: st.last_played_at,
      added: st.created_at,
    })),
    ...podcasts.map((pod) => ({
      key: `podcast-${pod.id}`,
      title: pod.title,
      subtitle: pod.latest_episode_title ?? t('overview.kind_podcast'),
      cover: pod.cover_art_url,
      icon: <PodcastsIcon sx={{ fontSize: 16 }} />,
      durationMs: null,
      play: () => void audioApi.play({ podcast_id: pod.id }),
      played: pod.last_played_at,
      added: pod.created_at,
    })),
  ];

  const recentlyPlayed = entries
    .filter((e) => e.played != null)
    .sort(newestBy('played'))
    .slice(0, 6);

  const recentlyAdded = entries
    .filter((e) => e.added != null)
    .sort(newestBy('added'))
    .slice(0, 6);

  const recentPlaylists = [...playlists]
    .filter((pl) => pl.updated_at != null)
    .sort((a, b) => new Date(b.updated_at!).getTime() - new Date(a.updated_at!).getTime())
    .slice(0, 4);

  const isEmpty =
    recentlyPlayed.length === 0 && recentlyAdded.length === 0 && recentPlaylists.length === 0;

  if (isEmpty) {
    return (
      <Box sx={{ p: 4, textAlign: 'center' }}>
        <Typography color="text.secondary">{t('overview.empty')}</Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ p: { xs: 1, md: 2 } }}>
      <Grid container spacing={3}>
        {recentlyPlayed.length > 0 && (
          <Grid item xs={12} md={6}>
            <BlockHeading
              icon={<AccessTimeIcon fontSize="small" color="action" />}
              title={t('overview.recently_played')}
            />
            <EntryList entries={recentlyPlayed} />
          </Grid>
        )}

        {recentlyAdded.length > 0 && (
          <Grid item xs={12} md={6}>
            <BlockHeading
              icon={<NewReleasesIcon fontSize="small" color="action" />}
              title={t('overview.recently_added')}
              action={{ label: t('overview.show_all'), onClick: () => onNavigateTab(2) }}
            />
            <EntryList entries={recentlyAdded} />
          </Grid>
        )}

        {recentPlaylists.length > 0 && (
          <Grid item xs={12}>
            <BlockHeading
              icon={<PlaylistPlayIcon fontSize="small" color="action" />}
              title={t('overview.playlists_updated')}
              action={{ label: t('overview.show_all'), onClick: () => onNavigateTab(1) }}
            />
            <Grid container spacing={1}>
              {recentPlaylists.map((pl) => (
                <Grid item xs={6} md={3} key={pl.id}>
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
                          {t('overview.track_count', { count: pl.tracks?.length ?? 0 })}
                        </Typography>
                      </Box>
                    </CardContent>
                  </Card>
                </Grid>
              ))}
            </Grid>
          </Grid>
        )}
      </Grid>
    </Box>
  );
};
