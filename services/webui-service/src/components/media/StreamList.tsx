import React, { useState } from 'react';
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Divider,
  IconButton,
  InputAdornment,
  List,
  ListItem,
  ListItemText,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from '@mui/material';
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import DeleteIcon from '@mui/icons-material/Delete';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import SearchIcon from '@mui/icons-material/Search';
import StreamIcon from '@mui/icons-material/Stream';
import { useTranslation } from 'react-i18next';
import { audioApi } from '@/api/audio';
import type { Stream } from '@/types/api';

type SortKey = 'title' | 'artist' | 'last_played_at';

interface StreamListProps {
  streams: Stream[];
  onDelete: (stream: Stream) => void;
}

export const StreamList: React.FC<StreamListProps> = ({ streams, onDelete }) => {
  const { t } = useTranslation('media');
  const [search, setSearch] = useState('');
  const [streamToDelete, setStreamToDelete] = useState<Stream | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>('title');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');

  const filtered = streams.filter((s) => {
    const q = search.toLowerCase();
    return (
      s.title.toLowerCase().includes(q) ||
      (s.artist ?? '').toLowerCase().includes(q)
    );
  });

  const sorted = [...filtered].sort((a, b) => {
    let aVal: string | number;
    let bVal: string | number;
    if (sortKey === 'last_played_at') {
      aVal = a.last_played_at ? new Date(a.last_played_at).getTime() : 0;
      bVal = b.last_played_at ? new Date(b.last_played_at).getTime() : 0;
    } else if (sortKey === 'artist') {
      aVal = (a.artist ?? '').toLowerCase();
      bVal = (b.artist ?? '').toLowerCase();
    } else {
      aVal = a.title.toLowerCase();
      bVal = b.title.toLowerCase();
    }
    if (aVal < bVal) return sortDir === 'asc' ? -1 : 1;
    if (aVal > bVal) return sortDir === 'asc' ? 1 : -1;
    return 0;
  });

  const handleSortKey = (_: React.MouseEvent, key: SortKey | null) => {
    if (!key) return;
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  };

  if (streams.length === 0) {
    return (
      <Box display="flex" justifyContent="center" py={6}>
        <Typography color="text.secondary">{t('streams.no_streams')}</Typography>
      </Box>
    );
  }

  return (
    <Box>
      <Box display="flex" gap={2} mb={2} flexWrap="wrap" alignItems="center">
        <TextField
          placeholder={t('streams.search_placeholder')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          size="small"
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon />
              </InputAdornment>
            ),
          }}
          sx={{ minWidth: 200 }}
        />

        <Box display="flex" alignItems="center" gap={0.5} ml="auto">
          <ToggleButtonGroup
            value={sortKey}
            exclusive
            onChange={handleSortKey}
            size="small"
          >
            <ToggleButton value="title">{t('streams.fields.title')}</ToggleButton>
            <ToggleButton value="artist">{t('streams.fields.artist')}</ToggleButton>
            <ToggleButton value="last_played_at">{t('streams.fields.last_played')}</ToggleButton>
          </ToggleButtonGroup>
          <Tooltip title={t(`streams.sort.${sortDir}`)}>
            <IconButton
              size="small"
              onClick={() => setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))}
            >
              {sortDir === 'asc' ? (
                <ArrowUpwardIcon fontSize="small" />
              ) : (
                <ArrowDownwardIcon fontSize="small" />
              )}
            </IconButton>
          </Tooltip>
        </Box>
      </Box>

      <List dense>
        {sorted.map((stream, idx) => (
          <React.Fragment key={stream.id}>
            {idx > 0 && <Divider component="li" />}
            <ListItem
              secondaryAction={
                <Box>
                  <Tooltip title={t('tracks.play')}>
                    <IconButton
                      size="small"
                      color="primary"
                      onClick={() => audioApi.play({ stream_id: stream.id })}
                    >
                      <PlayArrowIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title={t('tracks.delete')}>
                    <IconButton
                      size="small"
                      color="error"
                      onClick={() => setStreamToDelete(stream)}
                    >
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Box>
              }
            >
              <Box mr={1} color="text.secondary">
                <StreamIcon fontSize="small" />
              </Box>
              <ListItemText
                primary={stream.title}
                secondary={
                  <Box
                    component="span"
                    display="flex"
                    gap={1}
                    alignItems="center"
                    flexWrap="wrap"
                  >
                    {stream.artist && (
                      <Typography component="span" variant="caption">
                        {stream.artist}
                      </Typography>
                    )}
                    {stream.last_played_at && (
                      <Typography component="span" variant="caption" color="text.disabled">
                        ·{' '}
                        {new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' }).format(
                          -Math.round(
                            (Date.now() - new Date(stream.last_played_at).getTime()) /
                              3_600_000
                          ),
                          'hour'
                        )}
                      </Typography>
                    )}
                  </Box>
                }
              />
            </ListItem>
          </React.Fragment>
        ))}
      </List>

      <Dialog open={!!streamToDelete} onClose={() => setStreamToDelete(null)}>
        <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>
          {t('streams.delete')}
        </DialogTitle>
        <DialogContent>
          <DialogContentText>
            {t('streams.delete_confirm', {
              title: streamToDelete?.title,
            })}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setStreamToDelete(null)}>
            {t('cancel', { ns: 'common' })}
          </Button>
          <Button
            onClick={() => {
              if (streamToDelete) {
                onDelete(streamToDelete);
                setStreamToDelete(null);
              }
            }}
            color="error"
            variant="contained"
          >
            {t('delete', { ns: 'common' })}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};
