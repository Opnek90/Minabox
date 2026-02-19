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
import { audioApi } from '@/api/audio';

type CommandGroup = 'Navigation' | 'Playback' | 'Sleep Timer';

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
  const theme = useTheme();
  const fullScreen = useMediaQuery(theme.breakpoints.down('sm')); // responsive fullscreen pattern [web:33]
  const navigate = useNavigate();
  const [query, setQuery] = useState('');

  useEffect(() => {
    if (!open) setQuery('');
  }, [open]);

  const commands: CommandItem[] = useMemo(
    () => [
      {
        id: 'nav-player',
        group: 'Navigation',
        label: 'Player',
        keywords: ['home', 'play'],
        run: () => navigate('/player'),
      },
      { id: 'nav-rfid', group: 'Navigation', label: 'RFID', keywords: ['tags'], run: () => navigate('/rfid') },
      { id: 'nav-media', group: 'Navigation', label: 'Media', keywords: ['library'], run: () => navigate('/media') },
      { id: 'nav-admin', group: 'Navigation', label: 'Admin', keywords: ['settings', 'config'], run: () => navigate('/admin') },

      { id: 'pb-play', group: 'Playback', label: 'Play', keywords: ['start'], run: async () => audioApi.play() },
      { id: 'pb-pause', group: 'Playback', label: 'Pause', keywords: ['stop'], run: async () => audioApi.pause() },
      { id: 'pb-stop', group: 'Playback', label: 'Stop', keywords: ['end'], run: async () => audioApi.stop() },
      { id: 'pb-next', group: 'Playback', label: 'Next', keywords: ['skip'], run: async () => audioApi.next() },
      { id: 'pb-prev', group: 'Playback', label: 'Previous', keywords: ['back'], run: async () => audioApi.previous() },

      { id: 'sleep-15', group: 'Sleep Timer', label: 'Sleep timer: 15 min', keywords: ['timer'], run: async () => audioApi.startSleepTimer(15) },
      { id: 'sleep-30', group: 'Sleep Timer', label: 'Sleep timer: 30 min', run: async () => audioApi.startSleepTimer(30) },
      { id: 'sleep-45', group: 'Sleep Timer', label: 'Sleep timer: 45 min', run: async () => audioApi.startSleepTimer(45) },
      { id: 'sleep-60', group: 'Sleep Timer', label: 'Sleep timer: 60 min', run: async () => audioApi.startSleepTimer(60) },
      { id: 'sleep-cancel', group: 'Sleep Timer', label: 'Sleep timer: cancel', keywords: ['off'], run: async () => audioApi.cancelSleepTimer() },
    ],
    [navigate]
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
    <Dialog open={open} onClose={onClose} fullScreen={fullScreen} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1, pr: 1 }}>
        <Typography variant="h6" sx={{ flex: 1, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          Quick Actions
        </Typography>
        <IconButton onClick={onClose} size="small" aria-label="close">
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>

      <DialogContent sx={{ pt: 1 }}>
        <TextField
          autoFocus
          fullWidth
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search actions…"
          size="small"
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" />
              </InputAdornment>
            ),
          }}
        />

        <Box sx={{ mt: 1.5 }}>
          {filtered.length === 0 ? (
            <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
              No actions found.
            </Typography>
          ) : (
            Array.from(grouped.entries()).map(([group, items]) => (
              <Box key={group} sx={{ mt: 1 }}>
                <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700, letterSpacing: 0.6 }}>
                  {group}
                </Typography>
                <List dense sx={{ py: 0.5 }}>
                  {items.map((cmd) => (
                    <ListItemButton key={cmd.id} onClick={() => handleRun(cmd)}>
                      <ListItemText
                        primary={cmd.label}
                        primaryTypographyProps={{ noWrap: true }}
                      />
                    </ListItemButton>
                  ))}
                </List>
              </Box>
            ))
          )}
        </Box>
      </DialogContent>
    </Dialog>
  );
};
