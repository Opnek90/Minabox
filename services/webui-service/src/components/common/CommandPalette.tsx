import React, { useEffect, useMemo, useState } from 'react';
import {
  Avatar,
  Box,
  Chip,
  Dialog,
  DialogContent,
  DialogTitle,
  Divider,
  IconButton,
  InputAdornment,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  TextField,
  Typography,
} from '@mui/material';
import AudiotrackIcon from '@mui/icons-material/Audiotrack';
import CloseIcon from '@mui/icons-material/Close';
import PlaylistPlayIcon from '@mui/icons-material/PlaylistPlay';
import PodcastsIcon from '@mui/icons-material/Podcasts';
import SearchIcon from '@mui/icons-material/Search';
import SettingsIcon from '@mui/icons-material/Settings';
import StreamIcon from '@mui/icons-material/Stream';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { audioApi } from '@/api/audio';
import { playlistsApi } from '@/api/playlists';
import { tracksApi } from '@/api/tracks';
import { streamsApi } from '@/api/streams';
import { podcastsApi } from '@/api/podcasts';
import { SETTINGS_SECTIONS } from '@/config/settingsIndex';
import type { Playlist, Podcast, Stream, Track } from '@/types/api';
import { useLayout } from '@/hooks/useLayout';

type CommandGroup =
  | 'navigation' | 'playback' | 'sleep_timer' | 'settings'
  | 'tracks' | 'playlists' | 'streams' | 'podcasts';

interface CommandItem {
  id: string;
  group: CommandGroup;
  label: string;
  sublabel?: string;
  icon?: React.ReactNode;
  avatarUrl?: string;
  keywords?: string[];
  run: () => void | Promise<void>;
}

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  /** Ohne diesen Callback kann Ctrl/Cmd+K die Palette nur schließen, nicht öffnen. */
  onOpen?: () => void;
}

export const CommandPalette: React.FC<CommandPaletteProps> = ({ open, onClose, onOpen }) => {
  const { t } = useTranslation('common');
  const { t: tAdmin } = useTranslation(['admin', 'setup']);
  const fullScreen = useLayout().isMobile;
  const navigate = useNavigate();
  const [query, setQuery] = useState('');

  // Media data (lazy loaded on first open)
  const [tracks, setTracks] = useState<Track[]>([]);
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  const [streams, setStreams] = useState<Stream[]>([]);
  const [podcasts, setPodcasts] = useState<Podcast[]>([]);
  const [mediaLoaded, setMediaLoaded] = useState(false);

  useEffect(() => {
    if (!open) { setQuery(''); return; }
    if (mediaLoaded) return;
    // Load media data once
    Promise.all([
      tracksApi.getAll(),
      playlistsApi.getAll(),
      streamsApi.getAll(),
      podcastsApi.list(),
    ]).then(([t, pl, st, po]) => {
      setTracks(t); setPlaylists(pl); setStreams(st); setPodcasts(po);
      setMediaLoaded(true);
    }).catch(() => {});
  }, [open, mediaLoaded]);

  // Ctrl+K / Cmd+K global shortcut – schaltet die Palette um
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        if (open) onClose();
        else onOpen?.();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, onClose, onOpen]);

  const staticCommands: CommandItem[] = useMemo(
    () => [
      { id: 'nav-player', group: 'navigation', label: t('command_palette.nav.player'), keywords: ['home', 'start'], run: () => navigate('/player') },
      { id: 'nav-rfid', group: 'navigation', label: t('command_palette.nav.rfid'), keywords: ['tags', 'karten'], run: () => navigate('/rfid') },
      { id: 'nav-media', group: 'navigation', label: t('command_palette.nav.media'), keywords: ['bibliothek', 'library', 'musik'], run: () => navigate('/media') },
      { id: 'nav-admin', group: 'navigation', label: t('command_palette.nav.admin'), keywords: ['settings', 'einstellungen', 'config'], run: () => navigate('/admin') },
      { id: 'pb-play', group: 'playback', label: t('command_palette.playback.play'), run: () => audioApi.play() },
      { id: 'pb-pause', group: 'playback', label: t('command_palette.playback.pause'), run: () => audioApi.pause() },
      { id: 'pb-stop', group: 'playback', label: t('command_palette.playback.stop'), run: () => audioApi.stop() },
      { id: 'pb-next', group: 'playback', label: t('command_palette.playback.next'), run: () => audioApi.next() },
      { id: 'pb-prev', group: 'playback', label: t('command_palette.playback.previous'), run: () => audioApi.previous() },
      ...[15, 30, 45, 60].map((min) => ({
        id: `sleep-${min}`, group: 'sleep_timer' as CommandGroup,
        label: t('command_palette.sleep_timer.preset', { minutes: min }),
        keywords: ['timer', 'schlaf', 'sleep'],
        run: () => audioApi.startSleepTimer(min),
      })),
      { id: 'sleep-cancel', group: 'sleep_timer' as CommandGroup, label: t('command_palette.sleep_timer.cancel'), run: () => audioApi.cancelSleepTimer() },
    ],
    [t, navigate]
  );

  // Jede Settings-Section ist direkt anspringbar. Gesucht wird auch über die
  // Labels der enthaltenen Felder, damit „MQTT" oder „WLAN" die Section findet,
  // ohne dass man weiß, in welcher Gruppe sie liegt.
  const settingsCommands: CommandItem[] = useMemo(
    () =>
      SETTINGS_SECTIONS.map((section) => ({
        id: `settings-${section.key}`,
        group: 'settings' as CommandGroup,
        label: tAdmin(section.titleKey),
        sublabel: tAdmin(section.groupLabelKey),
        icon: <SettingsIcon fontSize="small" />,
        keywords: section.searchKeys.map((key) => tAdmin(key)),
        run: () => navigate(`/admin?section=${section.key}`),
      })),
    [tAdmin, navigate]
  );

  const mediaCommands: CommandItem[] = useMemo(() => [
    ...tracks.map((tr) => ({
      id: `track-${tr.id}`, group: 'tracks' as CommandGroup,
      label: tr.title, sublabel: tr.artist ?? undefined,
      icon: <AudiotrackIcon fontSize="small" />,
      avatarUrl: tr.cover_art_url ?? undefined,
      run: () => audioApi.play({ track_id: tr.id }),
    })),
    ...playlists.map((pl) => ({
      id: `playlist-${pl.id}`, group: 'playlists' as CommandGroup,
      label: pl.name, sublabel: `${pl.tracks?.length ?? 0} Tracks`,
      icon: <PlaylistPlayIcon fontSize="small" />,
      avatarUrl: pl.cover_art_url ?? undefined,
      run: () => audioApi.play({ playlist_id: pl.id }),
    })),
    ...streams.map((s) => ({
      id: `stream-${s.id}`, group: 'streams' as CommandGroup,
      label: s.title,
      icon: <StreamIcon fontSize="small" />,
      run: () => audioApi.play({ stream_id: s.id }),
    })),
    ...podcasts.map((p) => ({
      id: `podcast-${p.id}`, group: 'podcasts' as CommandGroup,
      label: p.title,
      icon: <PodcastsIcon fontSize="small" />,
      run: () => navigate('/media'),
    })),
  ], [tracks, playlists, streams, podcasts, navigate]);

  const allCommands = useMemo(
    () => [...staticCommands, ...settingsCommands, ...mediaCommands],
    [staticCommands, settingsCommands, mediaCommands]
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return staticCommands; // No query: only static commands
    return allCommands.filter((c) => {
      const hay = [c.label, c.sublabel ?? '', ...(c.keywords ?? [])].join(' ').toLowerCase();
      return hay.includes(q);
    });
  }, [allCommands, staticCommands, query]);

  const grouped = useMemo(() => {
    const map = new Map<CommandGroup, CommandItem[]>();
    for (const item of filtered) {
      if (!map.has(item.group)) map.set(item.group, []);
      map.get(item.group)!.push(item);
    }
    return map;
  }, [filtered]);

  const handleRun = async (cmd: CommandItem) => {
    try { await cmd.run(); } finally { onClose(); }
  };

  const isMediaSearch = query.trim().length > 0 &&
    ['tracks', 'playlists', 'streams', 'podcasts'].some((g) => grouped.has(g as CommandGroup));

  return (
    <Dialog open={open} onClose={onClose} fullScreen={fullScreen} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1, pr: 1 }}>
        <Typography variant="h6" sx={{ flex: 1, fontWeight: 700 }}>
          {t('command_palette.title')}
        </Typography>
        <Typography variant="caption" color="text.disabled" sx={{ flexShrink: 0, fontFamily: 'monospace' }}>
          Ctrl+K
        </Typography>
        <IconButton size="small" onClick={onClose}><CloseIcon fontSize="small" /></IconButton>
      </DialogTitle>

      <DialogContent sx={{ p: 0 }}>
        <Box sx={{ px: 2, pt: 1, pb: 1 }}>
          <TextField
            autoFocus fullWidth size="small"
            placeholder={
              isMediaSearch
                ? t('command_palette.placeholder_media')
                : t('command_palette.placeholder')
            }
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            InputProps={{
              startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment>,
              endAdornment: isMediaSearch ? (
                <InputAdornment position="end">
                  <Chip label={t('navigation.media')} size="small" color="primary" variant="outlined" sx={{ height: 20, fontSize: '0.65rem' }} />
                </InputAdornment>
              ) : undefined,
            }}
          />
        </Box>

        {grouped.size === 0 ? (
          <Typography variant="body2" color="text.disabled" sx={{ px: 2, py: 3, textAlign: 'center' }}>
            {t('command_palette.no_results')}
          </Typography>
        ) : (
          <List dense disablePadding>
            {Array.from(grouped.entries()).map(([group, items], groupIdx) => (
              <Box key={group}>
                {groupIdx > 0 && <Divider />}
                <Typography variant="overline" color="text.secondary"
                  sx={{ px: 2, pt: 1.5, pb: 0.5, display: 'block', lineHeight: 1 }}>
                  {t(`command_palette.groups.${group}`, { defaultValue: group })}
                </Typography>
                {items.slice(0, 8).map((cmd) => (
                  <ListItemButton key={cmd.id} onClick={() => handleRun(cmd)} sx={{ px: 2, py: 0.75 }}>
                    {(cmd.avatarUrl || cmd.icon) && (
                      <ListItemIcon sx={{ minWidth: 36 }}>
                        {cmd.avatarUrl ? (
                          <Avatar src={cmd.avatarUrl} variant="rounded" sx={{ width: 24, height: 24 }}>
                            {cmd.icon}
                          </Avatar>
                        ) : (
                          <Box sx={{ color: 'text.secondary' }}>{cmd.icon}</Box>
                        )}
                      </ListItemIcon>
                    )}
                    <ListItemText
                      primary={cmd.label}
                      secondary={cmd.sublabel}
                      primaryTypographyProps={{ variant: 'body2', fontWeight: 500 }}
                      secondaryTypographyProps={{ variant: 'caption' }}
                    />
                  </ListItemButton>
                ))}
              </Box>
            ))}
          </List>
        )}
      </DialogContent>
    </Dialog>
  );
};
