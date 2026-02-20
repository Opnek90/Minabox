import React, { useState } from 'react';
import {
  Box,
  Button,
  Chip,
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
import AudiotrackIcon from '@mui/icons-material/Audiotrack';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import LinkIcon from '@mui/icons-material/Link';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import SearchIcon from '@mui/icons-material/Search';
import { useTranslation } from 'react-i18next';
import { audioApi } from '@/api/audio';
import type { Track } from '@/types/api';
import { formatTime } from '@/utils/formatTime';


type SortKey = 'title' | 'artist' | 'duration_ms' | 'last_played_at';


interface TrackListProps {
  tracks: Track[];
  onDelete: (track: Track) => void;
  onEdit?: (track: Track) => void;
  selectionMode?: boolean;
  onSelect?: (track: Track) => void;
}


export const TrackList: React.FC<TrackListProps> = ({
  tracks,
  onDelete,
  onEdit,
  selectionMode = false,
  onSelect,
}) => {
  const { t } = useTranslation('media');
  const [search, setSearch] = useState('');
  const [filterSource, setFilterSource] = useState<'all' | 'file' | 'remote'>('all');
  const [trackToDelete, setTrackToDelete] = useState<Track | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>('title');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');

  const filtered = tracks.filter((tr) => {
    const q = search.toLowerCase();
    const matchesSearch =
      tr.title.toLowerCase().includes(q) ||
      (tr.artist ?? '').toLowerCase().includes(q) ||
      (tr.album ?? '').toLowerCase().includes(q);
    const matchesFilter =
      filterSource === 'all' || tr.source_type === filterSource;
    return matchesSearch && matchesFilter;
  });

  const sorted = [...filtered].sort((a, b) => {
    let aVal: string | number;
    let bVal: string | number;
    if (sortKey === 'duration_ms') {
      aVal = a.duration_ms ?? 0;
      bVal = b.duration_ms ?? 0;
    } else if (sortKey === 'last_played_at') {
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

  if (tracks.length === 0) {
    return (
      <Box display="flex" justifyContent="center" py={6}>
        <Typography color="text.secondary">{t('tracks.no_tracks')}</Typography>
      </Box>
    );
  }

  return (
    <Box>
      <Box display="flex" gap={2} mb={2} flexWrap="wrap" alignItems="center">
        <TextField
          placeholder={t('track_selector.search_placeholder')}
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
        <ToggleButtonGroup
          value={filterSource}
          exclusive
          onChange={(_, v) => v && setFilterSource(v)}
          size="small"
        >
          <ToggleButton value="all">{t('tracks.filter.all')}</ToggleButton>
          <ToggleButton value="file">{t('tracks.filter.files')}</ToggleButton>
          <ToggleButton value="remote">{t('tracks.filter.remote', { defaultValue: 'Remote' })}</ToggleButton>
        </ToggleButtonGroup>

        {/* Sort controls */}
        <Box display="flex" alignItems="center" gap={0.5} ml="auto">
          <ToggleButtonGroup
            value={sortKey}
            exclusive
            onChange={handleSortKey}
            size="small"
          >
            <ToggleButton value="title">{t('tracks.fields.title')}</ToggleButton>
            <ToggleButton value="artist">{t('tracks.fields.artist')}</ToggleButton>
            <ToggleButton value="duration_ms">{t('tracks.fields.duration')}</ToggleButton>
            <ToggleButton value="last_played_at">{t('tracks.fields.last_played')}</ToggleButton>
          </ToggleButtonGroup>
          <Tooltip
            title={t(`tracks.sort.${sortDir}`)}
          >
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
        {sorted.map((track, idx) => (
          <React.Fragment key={track.id}>
            {idx > 0 && <Divider component="li" />}
            <ListItem
              secondaryAction={
                !selectionMode && (
                  <Box>
                    <Tooltip title={t('tracks.play')}>
                      <IconButton
                        size="small"
                        color="primary"
                        onClick={() => audioApi.play({ track_id: track.id })}
                      >
                        <PlayArrowIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    {onEdit && (
                      <Tooltip title={t('tracks.edit')}>
                        <IconButton size="small" onClick={() => onEdit(track)}>
                          <EditIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    )}
                    <Tooltip title={t('tracks.delete')}>
                      <IconButton
                        size="small"
                        color="error"
                        onClick={() => setTrackToDelete(track)}
                      >
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </Box>
                )
              }
              sx={
                selectionMode
                  ? { cursor: 'pointer', '&:hover': { bgcolor: 'action.hover' } }
                  : undefined
              }
              onClick={selectionMode && onSelect ? () => onSelect(track) : undefined}
            >
              <Box mr={1} color="text.secondary">
                {track.source_type === 'remote' ? (
                  <LinkIcon fontSize="small" />
                ) : (
                  <AudiotrackIcon fontSize="small" />
                )}
              </Box>
              <ListItemText
                primary={track.title}
                secondary={
                  <Box
                    component="span"
                    display="flex"
                    gap={1}
                    alignItems="center"
                    flexWrap="wrap"
                  >
                    {track.artist && (
                      <Typography component="span" variant="caption">
                        {track.artist}
                      </Typography>
                    )}
                    {track.album && (
                      <Typography component="span" variant="caption" color="text.disabled">
                        · {track.album}
                      </Typography>
                    )}
                    {track.duration_ms != null && (
                      <Chip
                        label={formatTime(track.duration_ms)}
                        size="small"
                        variant="outlined"
                        sx={{ height: 18, fontSize: '0.65rem' }}
                      />
                    )}
                    {track.last_played_at && (
                      <Typography component="span" variant="caption" color="text.disabled">
                        ·{' '}
                        {new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' }).format(
                          -Math.round(
                            (Date.now() - new Date(track.last_played_at).getTime()) /
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

      {/* Delete Confirmation */}
      <Dialog open={!!trackToDelete} onClose={() => setTrackToDelete(null)}>
        <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>
          {t('tracks.delete')}
        </DialogTitle>
        <DialogContent>
          <DialogContentText>
            {t('tracks.delete_confirm', { title: trackToDelete?.title })}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setTrackToDelete(null)}>
            {t('cancel', { ns: 'common' })}
          </Button>
          <Button
            onClick={() => {
              if (trackToDelete) {
                onDelete(trackToDelete);
                setTrackToDelete(null);
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
