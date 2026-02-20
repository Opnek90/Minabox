import React, { useEffect, useMemo, useState } from 'react';
import {
  Box,
  Dialog,
  DialogContent,
  DialogTitle,
  IconButton,
  InputAdornment,
  List,
  ListItemButton,
  ListItemText,
  TextField,
  Typography,
  useMediaQuery,
  useTheme,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import SearchIcon from '@mui/icons-material/Search';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { audioApi } from '@/api/audio';

type CommandGroup = 'navigation' | 'playback' | 'sleep_timer';

interface CommandItem {
  id: string;
  group: CommandGroup;
  label: string;
  keywords?: string[];
  run: () => void | Promise<void>;
}

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
}

export const CommandPalette: React.FC<CommandPaletteProps> = ({ open, onClose }) => {
  const { t } = useTranslation('common');
  const theme = useTheme();
  const fullScreen = useMediaQuery(theme.breakpoints.down('sm'));
  const navigate = useNavigate();
  const [query, setQuery] = useState('');

  // Reset query when dialog closes
  useEffect(() => {
    if (!open) setQuery('');
  }, [open]);

  // Ctrl+K / Cmd+K global shortcut
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        open ? onClose() : undefined;
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, onClose]);

  const commands: CommandItem[] = useMemo(
    () => [
      // Navigation
      {
        id: 'nav-player',
        group: 'navigation',
        label: t('command_palette.nav.player'),
        keywords: ['home', 'start'],
        run: () => navigate('/player'),
      },
      {
        id: 'nav-rfid',
        group: 'navigation',
        label: t('command_palette.nav.rfid'),
        keywords: ['tags', 'karten'],
        run: () => navigate('/rfid'),
      },
      {
        id: 'nav-media',
        group: 'navigation',
        label: t('command_palette.nav.media'),
        keywords: ['bibliothek', 'library', 'musik'],
        run: () => navigate('/media'),
      },
      {
        id: 'nav-admin',
        group: 'navigation',
        label: t('command_palette.nav.admin'),
        keywords: ['settings', 'einstellungen', 'config'],
        run: () => navigate('/admin'),
      },

      // Playback
      {
        id: 'pb-play',
        group: 'playback',
        label: t('command_palette.playback.play'),
        keywords: ['start', 'abspielen'],
        run: () => audioApi.play(),
      },
      {
        id: 'pb-pause',
        group: 'playback',
        label: t('command_palette.playback.pause'),
        keywords: ['pausieren', 'stop'],
        run: () => audioApi.pause(),
      },
      {
        id: 'pb-stop',
        group: 'playback',
        label: t('command_palette.playback.stop'),
        keywords: ['stoppen', 'end'],
        run: () => audioApi.stop(),
      },
      {
        id: 'pb-next',
        group: 'playback',
        label: t('command_palette.playback.next'),
        keywords: ['skip', 'weiter', 'überspringen'],
        run: () => audioApi.next(),
      },
      {
        id: 'pb-prev',
        group: 'playback',
        label: t('command_palette.playback.previous'),
        keywords: ['back', 'zurück'],
        run: () => audioApi.previous(),
      },

      // Sleep Timer
      ...[15, 30, 45, 60].map((min) => ({
        id: `sleep-${min}`,
        group: 'sleep_timer' as CommandGroup,
        label: t('command_palette.sleep_timer.preset', { minutes: min }),
        keywords: ['timer', 'schlaf', 'sleep'],
        run: () => audioApi.startSleepTimer(min),
      })),
      {
        id: 'sleep-cancel',
        group: 'sleep_timer' as CommandGroup,
        label: t('command_palette.sleep_timer.cancel'),
        keywords: ['off', 'aus', 'deaktivieren'],
        run: () => audioApi.cancelSleepTimer(),
      },
    ],
    [t, navigate]
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter((c) => {
      const hay = [c.label, ...(c.keywords ?? [])].join(' ').toLowerCase();
      return hay.includes(q);
    });
  }, [commands, query]);

  const grouped = useMemo(() => {
    const map = new Map<CommandGroup, CommandItem[]>();
    for (const item of filtered) {
      if (!map.has(item.group)) map.set(item.group, []);
      map.get(item.group)!.push(item);
    }
    return map;
  }, [filtered]);

  const handleRun = async (cmd: CommandItem) => {
    try {
      await cmd.run();
    } finally {
      onClose();
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullScreen={fullScreen}
      maxWidth="sm"
      fullWidth
    >
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1, pr: 1 }}>
        <Typography variant="h6" sx={{ flex: 1, fontWeight: 700 }}>
          {t('command_palette.title')}
        </Typography>
        <Typography
          variant="caption"
          color="text.disabled"
          sx={{ flexShrink: 0, fontFamily: 'monospace' }}
        >
          Ctrl+K
        </Typography>
        <IconButton size="small" onClick={onClose} aria-label={t('cancel')}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>

      <DialogContent sx={{ p: 0 }}>
        {/* Search field */}
        <Box sx={{ px: 2, pt: 1, pb: 1 }}>
          <TextField
            autoFocus
            fullWidth
            size="small"
            placeholder={t('command_palette.placeholder')}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon fontSize="small" />
                </InputAdornment>
              ),
            }}
          />
        </Box>

        {/* Results grouped */}
        {grouped.size === 0 ? (
          <Typography
            variant="body2"
            color="text.disabled"
            sx={{ px: 2, py: 3, textAlign: 'center' }}
          >
            {t('actions.retry')}
          </Typography>
        ) : (
          <List dense disablePadding>
            {Array.from(grouped.entries()).map(([group, items]) => (
              <Box key={group}>
                <Typography
                  variant="overline"
                  color="text.secondary"
                  sx={{ px: 2, pt: 1.5, pb: 0.5, display: 'block', lineHeight: 1 }}
                >
                  {t(`command_palette.groups.${group}`)}
                </Typography>
                {items.map((cmd) => (
                  <ListItemButton
                    key={cmd.id}
                    onClick={() => handleRun(cmd)}
                    sx={{ px: 2, py: 0.75 }}
                  >
                    <ListItemText
                      primary={cmd.label}
                      primaryTypographyProps={{ variant: 'body2', fontWeight: 500 }}
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
